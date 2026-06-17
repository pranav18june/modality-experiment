"""
MongoDB database helpers for the modality experiment.

All participant data is stored in a single `participants` collection.
Each document represents one participant's complete experiment session,
with responses, trust ratings, and comprehension embedded as arrays.

Document shape:
  {
    _id:              ObjectId,
    session_token:    str (UUID-v4),
    group_assignment: "A" | "B",
    created_at:       datetime (UTC),
    completed_at:     datetime | None,
    demographics: {
      program, year_of_study, sc_exposure, ai_familiarity, gender
    },
    scenario_orders: { stage1: [int], stage2: [int], stage3: [int] },
    progress: { tutorial_passed: bool, completed: bool },
    responses: [
      { scenario_id, stage, position_in_stage, modality,
        rop_adjustment, ss_adjustment, confidence,
        time_on_task_seconds, submitted_at }
    ],
    trust_ratings: [
      { stage, trust_1, trust_2, trust_3, submitted_at }
    ],
    comprehension: {
      answers: { item_1..item_5 },
      scores:  { item_1_correct, item_2_correct, item_4_correct },
      submitted_at
    }
  }

Public API is identical to the previous sqlite3 version so routes.py
requires only minimal changes.
"""

import os
import json
import random
from datetime import datetime, timezone
from functools import lru_cache

from bson import ObjectId
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

# ── Modality sequence per group ─────────────────────────────────────────────
GROUP_MODALITY = {
    "A": {1: "numerical", 2: "visual", 3: "llm"},
    "B": {1: "llm",       2: "visual", 3: "numerical"},
}

# Scenario IDs per stage (from generator output)
STAGE_SCENARIOS = {
    1: [1, 3, 5, 9],
    2: [2, 6, 7, 10],
    3: [4, 8, 11, 12],
}


# ── MongoDB connection (lazy singleton) ──────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client() -> MongoClient:
    """
    Return a cached MongoClient.  lru_cache ensures only one client is
    created per process, which is the correct pattern for serverless
    functions (each Vercel instance is a single process).
    """
    uri = os.environ.get("MONGO_URI")
    if not uri:
        raise RuntimeError(
            "MONGO_URI environment variable is not set. "
            "Add it to your .env file or Vercel environment variables."
        )
    return MongoClient(
        uri, 
        serverSelectionTimeoutMS=5000, 
        maxIdleTimeMS=10000  # Prevent AWS/Vercel from dropping idle connections
    )


def _db():
    """Return the experiment database handle."""
    return _get_client()["modality_experiment"]


def _col():
    """Return the participants collection handle."""
    return _db()["participants"]


def init_db():
    """
    Ensure indexes exist on the participants collection.
    Called once at app startup via app/__init__.py.
    MongoDB creates collections on first write, so no table creation needed.
    """
    col = _col()
    col.create_index([("session_token", ASCENDING)], unique=True, background=True)


# ── Participant helpers ──────────────────────────────────────────────────────

def create_participant(session_token: str, group: str, scenario_orders: dict) -> str:
    """
    Insert a new participant document and return its string id.
    Returns a hex string (MongoDB ObjectId) instead of an integer.
    """
    orders = {}
    for stage, ids in STAGE_SCENARIOS.items():
        shuffled = ids[:]
        random.shuffle(shuffled)
        orders[stage] = shuffled

    doc = {
        "session_token":    session_token,
        "group_assignment": group,
        "created_at":       datetime.now(timezone.utc),
        "completed_at":     None,
        "demographics":     {},
        "scenario_orders": {
            "stage1": orders[1],
            "stage2": orders[2],
            "stage3": orders[3],
        },
        "progress": {
            "tutorial_passed": False,
            "completed":       False,
        },
        "responses":      [],
        "trust_ratings":  [],
        "comprehension":  None,
    }

    result = _col().insert_one(doc)
    return str(result.inserted_id)


def get_participant(pid: str) -> dict | None:
    """
    Fetch a participant by their string ObjectId.
    Returns a plain dict with a flattened structure compatible with routes.py,
    mirroring the old SQLite row dict shape.
    """
    try:
        doc = _col().find_one({"_id": ObjectId(pid)})
    except Exception:
        return None

    if not doc:
        return None

    return _flatten_doc(doc)


def _flatten_doc(doc: dict) -> dict:
    """
    Convert the nested MongoDB document into the flat dict shape that
    routes.py expects (matching the old sqlite3.Row dict interface).
    """
    progress = doc.get("progress", {})
    demo     = doc.get("demographics", {})
    orders   = doc.get("scenario_orders", {})

    return {
        "id":                 str(doc["_id"]),
        "session_token":      doc.get("session_token"),
        "group_assignment":   doc.get("group_assignment"),
        "created_at":         doc.get("created_at"),
        "completed_at":       doc.get("completed_at"),
        # Demographics (flat)
        "program":            demo.get("program"),
        "year_of_study":      demo.get("year_of_study"),
        "sc_exposure":        demo.get("sc_exposure"),
        "ai_familiarity":     demo.get("ai_familiarity"),
        "gender":             demo.get("gender"),
        # Scenario orders (as JSON strings to match old behaviour)
        "scenario_order_s1":  json.dumps(orders.get("stage1", STAGE_SCENARIOS[1])),
        "scenario_order_s2":  json.dumps(orders.get("stage2", STAGE_SCENARIOS[2])),
        "scenario_order_s3":  json.dumps(orders.get("stage3", STAGE_SCENARIOS[3])),
        # Progress flags (int 0/1 to match old SQLite INTEGER columns)
        "tutorial_passed":    1 if progress.get("tutorial_passed") else 0,
        "completed":          1 if progress.get("completed") else 0,
    }


def update_demographics(pid: str, data: dict):
    _col().update_one(
        {"_id": ObjectId(pid)},
        {"$set": {
            "demographics.program":        data.get("program"),
            "demographics.year_of_study":  data.get("year_of_study"),
            "demographics.sc_exposure":    data.get("sc_exposure"),
            "demographics.ai_familiarity": data.get("ai_familiarity"),
            "demographics.gender":         data.get("gender"),
        }},
    )


def mark_tutorial_passed(pid: str):
    _col().update_one(
        {"_id": ObjectId(pid)},
        {"$set": {"progress.tutorial_passed": True}},
    )


def mark_completed(pid: str):
    _col().update_one(
        {"_id": ObjectId(pid)},
        {"$set": {
            "progress.completed": True,
            "completed_at":       datetime.now(timezone.utc),
        }},
    )


def get_scenario_order(pid: str, stage: int) -> list[int]:
    """Return the randomised scenario ID list for a given stage."""
    p = get_participant(pid)
    if not p:
        return STAGE_SCENARIOS[stage]
    key = f"scenario_order_s{stage}"
    return json.loads(p[key])


# ── Response helpers ─────────────────────────────────────────────────────────

def save_response(pid: str, scenario_id: int, stage: int, position: int,
                  modality: str, rop: float, ss: float,
                  confidence: int, elapsed_seconds: float):
    """Append a task response to the participant's responses array."""
    _col().update_one(
        {"_id": ObjectId(pid)},
        {"$push": {"responses": {
            "scenario_id":          scenario_id,
            "stage":                stage,
            "position_in_stage":    position,
            "modality":             modality,
            "rop_adjustment":       rop,
            "ss_adjustment":        ss,
            "confidence":           confidence,
            "time_on_task_seconds": elapsed_seconds,
            "submitted_at":         datetime.now(timezone.utc),
        }}},
    )


def count_responses(pid: str, stage: int) -> int:
    """Count responses already saved for a given stage."""
    pipeline = [
        {"$match": {"_id": ObjectId(pid)}},
        {"$project": {
            "count": {
                "$size": {
                    "$filter": {
                        "input": "$responses",
                        "cond":  {"$eq": ["$$this.stage", stage]},
                    }
                }
            }
        }},
    ]
    result = list(_col().aggregate(pipeline))
    return result[0]["count"] if result else 0


def has_trust_for_stage(pid: str, stage: int) -> bool:
    """Check whether a trust rating already exists for a given stage."""
    doc = _col().find_one(
        {"_id": ObjectId(pid), "trust_ratings.stage": stage},
        {"_id": 1},
    )
    return doc is not None


def get_participant_responses(pid: str) -> list[dict]:
    """
    Return the raw list of response dicts for a participant.
    Used by routes.debrief() to compute the performance score.
    Each dict has keys: scenario_id, rop_adjustment, ss_adjustment.
    """
    try:
        doc = _col().find_one({"_id": ObjectId(pid)}, {"responses": 1})
    except Exception:
        return []
    if not doc:
        return []
    return doc.get("responses", [])


# ── Trust rating helpers ─────────────────────────────────────────────────────

def save_trust(pid: str, stage: int, t1: int, t2: int, t3: int):
    """Append a post-stage trust rating to the participant's trust_ratings array."""
    _col().update_one(
        {"_id": ObjectId(pid)},
        {"$push": {"trust_ratings": {
            "stage":       stage,
            "trust_1":     t1,
            "trust_2":     t2,
            "trust_3":     t3,
            "submitted_at": datetime.now(timezone.utc),
        }}},
    )


# ── Comprehension helpers ────────────────────────────────────────────────────

COMP_ANSWERS = {
    "item_1": "B",
    "item_2": "FAIL",
    "item_4": "182",
}


def save_comprehension(pid: str, answers: dict):
    i1 = answers.get("item_1", "").strip().upper()
    i2 = answers.get("item_2", "").strip().upper()
    i4 = answers.get("item_4", "").strip()

    i1_correct = 1 if i1 == COMP_ANSWERS["item_1"] else 0
    i2_correct = 1 if i2 == COMP_ANSWERS["item_2"] else 0
    try:
        i4_val     = float(i4)
        i4_correct = 1 if 70 <= i4_val <= 80 else 0
    except (ValueError, TypeError):
        i4_correct = 0

    _col().update_one(
        {"_id": ObjectId(pid)},
        {"$set": {"comprehension": {
            "answers": {
                "item_1": answers.get("item_1"),
                "item_2": answers.get("item_2"),
                "item_3": answers.get("item_3"),
                "item_4": answers.get("item_4"),
                "item_5": answers.get("item_5"),
                "item_5_reason": answers.get("item_5_reason"),
            },
            "scores": {
                "item_1_correct": i1_correct,
                "item_2_correct": i2_correct,
                "item_4_correct": i4_correct,
            },
            "submitted_at": datetime.now(timezone.utc),
        }}},
    )


# ── Admin / export helpers ───────────────────────────────────────────────────

def export_responses_csv() -> str:
    """Return full joined dataset as CSV string."""
    import csv
    import io

    buf     = io.StringIO()
    writer  = None
    headers = [
        "participant_id", "session_token", "group_assignment",
        "program", "year_of_study", "sc_exposure", "ai_familiarity", "gender",
        "tutorial_passed", "completed",
        "scenario_id", "stage", "position_in_stage", "modality",
        "rop_adjustment", "ss_adjustment", "confidence",
        "time_on_task_seconds", "submitted_at",
    ]

    for doc in _col().find({}, {"comprehension": 0}).sort("_id", ASCENDING):
        pid        = str(doc["_id"])
        demo       = doc.get("demographics", {})
        progress   = doc.get("progress", {})
        token      = doc.get("session_token", "")
        group      = doc.get("group_assignment", "")
        prog       = demo.get("program", "")
        yos        = demo.get("year_of_study", "")
        sc_exp     = demo.get("sc_exposure", "")
        ai_fam     = demo.get("ai_familiarity", "")
        gender     = demo.get("gender", "")
        tut_passed = 1 if progress.get("tutorial_passed") else 0
        completed  = 1 if progress.get("completed") else 0

        for r in doc.get("responses", []):
            row = {
                "participant_id":        pid,
                "session_token":         token,
                "group_assignment":      group,
                "program":               prog,
                "year_of_study":         yos,
                "sc_exposure":           sc_exp,
                "ai_familiarity":        ai_fam,
                "gender":                gender,
                "tutorial_passed":       tut_passed,
                "completed":             completed,
                "scenario_id":           r.get("scenario_id"),
                "stage":                 r.get("stage"),
                "position_in_stage":     r.get("position_in_stage"),
                "modality":              r.get("modality"),
                "rop_adjustment":        r.get("rop_adjustment"),
                "ss_adjustment":         r.get("ss_adjustment"),
                "confidence":            r.get("confidence"),
                "time_on_task_seconds":  r.get("time_on_task_seconds"),
                "submitted_at":          r.get("submitted_at", ""),
            }
            if writer is None:
                writer = csv.DictWriter(buf, fieldnames=headers)
                writer.writeheader()
            writer.writerow(row)

    return buf.getvalue()


def export_participants_csv() -> str:
    """Return participants table as CSV string."""
    import csv
    import io

    buf     = io.StringIO()
    writer  = None
    headers = [
        "participant_id", "group_assignment", "program", "year_of_study",
        "sc_exposure", "ai_familiarity", "gender",
        "tutorial_passed", "completed", "created_at", "completed_at",
        "comp_item_1", "comp_item_2", "comp_item_3", "comp_item_4", "comp_item_5", "comp_item_5_reason",
        "comp_score_1", "comp_score_2", "comp_score_4",
        "trust_s1_q1", "trust_s1_q2", "trust_s1_q3",
        "trust_s2_q1", "trust_s2_q2", "trust_s2_q3",
        "trust_s3_q1", "trust_s3_q2", "trust_s3_q3",
    ]

    for doc in _col().find({}, {"responses": 0}).sort("_id", ASCENDING):
        demo     = doc.get("demographics", {})
        progress = doc.get("progress", {})
        comp     = doc.get("comprehension", {})
        comp_ans = comp.get("answers", {})
        comp_scr = comp.get("scores", {})
        
        row = {
            "participant_id":   str(doc["_id"]),
            "group_assignment": doc.get("group_assignment", ""),
            "program":          demo.get("program", ""),
            "year_of_study":    demo.get("year_of_study", ""),
            "sc_exposure":      demo.get("sc_exposure", ""),
            "ai_familiarity":   demo.get("ai_familiarity", ""),
            "gender":           demo.get("gender", ""),
            "tutorial_passed":  1 if progress.get("tutorial_passed") else 0,
            "completed":        1 if progress.get("completed") else 0,
            "created_at":       doc.get("created_at", ""),
            "completed_at":     doc.get("completed_at", ""),
            "comp_item_1":      comp_ans.get("item_1", ""),
            "comp_item_2":      comp_ans.get("item_2", ""),
            "comp_item_3":      comp_ans.get("item_3", ""),
            "comp_item_4":      comp_ans.get("item_4", ""),
            "comp_item_5":      comp_ans.get("item_5", ""),
            "comp_item_5_reason": comp_ans.get("item_5_reason", ""),
            "comp_score_1":     comp_scr.get("item_1_correct", ""),
            "comp_score_2":     comp_scr.get("item_2_correct", ""),
            "comp_score_4":     comp_scr.get("item_4_correct", ""),
        }

        # Add trust ratings flatly
        trusts = doc.get("trust_ratings", [])
        for t in trusts:
            st = t.get("stage")
            if st in [1, 2, 3]:
                row[f"trust_s{st}_q1"] = t.get("trust_1", "")
                row[f"trust_s{st}_q2"] = t.get("trust_2", "")
                row[f"trust_s{st}_q3"] = t.get("trust_3", "")

        if writer is None:
            writer = csv.DictWriter(buf, fieldnames=headers)
            writer.writeheader()
        writer.writerow(row)

    return buf.getvalue()


def admin_summary() -> dict:
    """Return aggregate counts for the admin dashboard."""
    pipeline = [
        {"$facet": {
            "total":     [{"$count": "n"}],
            "completed": [{"$match": {"progress.completed": True}},  {"$count": "n"}],
            "group_a":   [{"$match": {"group_assignment": "A"}},     {"$count": "n"}],
            "group_b":   [{"$match": {"group_assignment": "B"}},     {"$count": "n"}],
            "n_resp":    [{"$project": {"c": {"$size": "$responses"}}},
                          {"$group": {"_id": None, "total": {"$sum": "$c"}}}],
        }}
    ]
    result   = list(_col().aggregate(pipeline))[0]

    def _n(facet):
        return result[facet][0]["n"] if result[facet] else 0

    total_resp = result["n_resp"][0]["total"] if result["n_resp"] else 0
    total      = _n("total")
    completed  = _n("completed")

    return {
        "total_participants": total,
        "completed":          completed,
        "in_progress":        total - completed,
        "group_a":            _n("group_a"),
        "group_b":            _n("group_b"),
        "total_responses":    total_resp,
    }


def get_visualization_data() -> dict:
    """Return aggregated data for admin visualisations."""
    pipeline = [
        {"$match": {"progress.completed": True}},
        {"$facet": {
            "gender": [
                {"$group": {"_id": "$demographics.gender", "count": {"$sum": 1}}}
            ],
            "program": [
                {"$group": {"_id": "$demographics.program", "count": {"$sum": 1}}}
            ],
            "year_of_study": [
                {"$group": {"_id": "$demographics.year_of_study", "count": {"$sum": 1}}}
            ],
            "ai_familiarity": [
                {"$group": {"_id": "$demographics.ai_familiarity", "count": {"$sum": 1}}}
            ],
            "sc_exposure": [
                {"$group": {"_id": "$demographics.sc_exposure", "count": {"$sum": 1}}}
            ],
            "modality_pref": [
                {"$group": {"_id": "$comprehension.answers.item_5", "count": {"$sum": 1}}}
            ],
            "comp_scores": [
                {"$group": {
                    "_id": None,
                    "item_1_correct": {"$sum": {"$cond": ["$comprehension.scores.item_1_correct", 1, 0]}},
                    "item_2_correct": {"$sum": {"$cond": ["$comprehension.scores.item_2_correct", 1, 0]}},
                    "item_4_correct": {"$sum": {"$cond": ["$comprehension.scores.item_4_correct", 1, 0]}},
                    "total": {"$sum": 1}
                }}
            ]
        }}
    ]
    
    result = list(_col().aggregate(pipeline))
    if not result:
        return {}
        
    data = result[0]
    
    def format_facet(facet_name):
        return {
            "labels": [str(d["_id"]).title().replace('_', ' ') if d["_id"] else "Unknown" for d in data.get(facet_name, [])],
            "values": [d["count"] for d in data.get(facet_name, [])]
        }
        
    vis_data = {
        "gender": format_facet("gender"),
        "program": format_facet("program"),
        "year_of_study": format_facet("year_of_study"),
        "ai_familiarity": format_facet("ai_familiarity"),
        "sc_exposure": format_facet("sc_exposure"),
        "modality_pref": format_facet("modality_pref"),
        "comp_scores": {"labels": [], "values": []}
    }
    
    if data.get("comp_scores") and len(data["comp_scores"]) > 0:
        cs = data["comp_scores"][0]
        total = cs["total"]
        if total > 0:
            vis_data["comp_scores"] = {
                "labels": ["Q1 (Disruption)", "Q2 (Threshold)", "Q4 (Safety Stock)"],
                "values": [
                    round((cs["item_1_correct"] / total) * 100, 1),
                    round((cs["item_2_correct"] / total) * 100, 1),
                    round((cs["item_4_correct"] / total) * 100, 1)
                ]
            }
            
    return vis_data
