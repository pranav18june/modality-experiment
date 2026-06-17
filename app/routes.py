"""
All Flask routes for the modality experiment.

Flow:
  / → /consent → /tutorial → /task (stage 1–3, 4 scenarios each)
    → /trust/<stage> → /comprehension → /debrief
  /admin                — password-gated summary + CSV export
"""

import json
import os
import uuid
from functools import wraps

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, jsonify, Response, abort,
)

from .models import (
    GROUP_MODALITY, STAGE_SCENARIOS,
    create_participant, get_participant, update_demographics,
    mark_tutorial_passed, mark_completed,
    get_scenario_order, save_response, count_responses, has_trust_for_stage,
    save_trust, save_comprehension,
    get_participant_responses,
    export_responses_csv, export_participants_csv, admin_summary,
)

bp = Blueprint("main", __name__)

# ── Load scenario fixtures once at import time ─────────────────────────────
_SCENARIOS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios.json")
_SCENARIOS: dict[int, dict] = {}

def _load_scenarios():
    global _SCENARIOS
    if not _SCENARIOS and os.path.exists(_SCENARIOS_PATH):
        with open(_SCENARIOS_PATH) as f:
            for sc in json.load(f):
                _SCENARIOS[sc["id"]] = sc

_load_scenarios()


def scenario_by_id(sid: int) -> dict:
    return _SCENARIOS.get(sid, {})


# ── Session helpers ────────────────────────────────────────────────────────

def _pid() -> int | None:
    return session.get("pid")


def _require_participant(f):
    """Redirect to consent if no active participant session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _pid():
            return redirect(url_for("main.consent"))
        return f(*args, **kwargs)
    return decorated


def _next_url_after_response(pid: int, stage: int, position: int) -> str:
    """
    After saving a response, decide where to go next:
      - more scenarios in this stage → back to /task
      - last scenario in stage, no trust yet → /trust/<stage>
      - after trust → next stage or comprehension
    """
    scenarios_in_stage = len(STAGE_SCENARIOS[stage])  # always 4

    if position + 1 < scenarios_in_stage:
        # More scenarios in this stage
        session["scenario_position"] = position + 1
        return url_for("main.task")
    else:
        # Last scenario in stage — go to trust rating
        return url_for("main.trust_rating", stage=stage)


# ── Landing / redirect ─────────────────────────────────────────────────────

@bp.route("/")
def index():
    if _pid():
        return render_template("resume_prompt.html")
    return redirect(url_for("main.consent"))


@bp.route("/restart")
def restart():
    session.clear()
    return redirect(url_for("main.consent"))


# ── Consent + demographics ─────────────────────────────────────────────────

@bp.route("/consent", methods=["GET", "POST"])
def consent():
    if request.method == "POST":
        # Assign group (alternating A/B for balance)
        from .models import admin_summary as _sum
        counts = _sum()
        group = "A" if counts["group_a"] <= counts["group_b"] else "B"

        token = str(uuid.uuid4())
        pid   = create_participant(token, group, {})

        # Save demographics
        update_demographics(pid, {
            "program":       request.form.get("program"),
            "year_of_study": request.form.get("year_of_study"),
            "sc_exposure":   request.form.get("sc_exposure"),
            "ai_familiarity":request.form.get("ai_familiarity"),
            "gender":        request.form.get("gender"),
        })

        session["pid"]               = pid
        session["group"]             = group
        session["stage"]             = 1
        session["scenario_position"] = 0
        session.permanent            = True

        return redirect(url_for("main.tutorial"))

    return render_template("consent.html")


# ── Tutorial ───────────────────────────────────────────────────────────────

@bp.route("/tutorial")
@_require_participant
def tutorial():
    p = get_participant(_pid())
    if p and p["tutorial_passed"]:
        return redirect(url_for("main.task"))
    # Pick two practice scenarios (mild ones, IDs 1 & 2) for the tutorial
    practice = [scenario_by_id(1), scenario_by_id(2)]
    return render_template("tutorial.html", practice=practice)


@bp.route("/tutorial/complete", methods=["POST"])
@_require_participant
def tutorial_complete():
    """Accept tutorial quiz answers; pass if score >= 3/4."""
    answers = request.get_json(force=True) or {}
    correct = {
        "q1": "b",   # ROP adjusts reorder trigger
        "q2": "c",   # SS is the buffer stock
        "q3": "b",   # bullwhip > 1 means amplification
        "q4": "a",   # FAIL means disruption threshold breached
    }
    score = sum(1 for k, v in correct.items() if answers.get(k, "").lower() == v)
    passed = score >= 3

    if passed:
        mark_tutorial_passed(_pid())

    return jsonify({"passed": passed, "score": score, "total": 4})


# ── Main experiment task ───────────────────────────────────────────────────

@bp.route("/task")
@_require_participant
def task():
    p = get_participant(_pid())
    if not p or not p["tutorial_passed"]:
        return redirect(url_for("main.tutorial"))

    stage    = session.get("stage", 1)
    position = session.get("scenario_position", 0)
    group    = session.get("group", p["group_assignment"])
    modality = GROUP_MODALITY[group][stage]

    # Get this participant's ordered scenario list for this stage
    ordered_ids = get_scenario_order(_pid(), stage)
    if position >= len(ordered_ids):
        return redirect(url_for("main.trust_rating", stage=stage))

    sc_id    = ordered_ids[position]
    scenario = scenario_by_id(sc_id)

    return render_template(
        "task.html",
        scenario   = scenario,
        modality   = modality,
        stage      = stage,
        position   = position,
        total      = len(ordered_ids),
        group      = group,
        # Strip heavy series from numerical/LLM panels (only needed for visual)
        sc_json    = json.dumps({
            k: v for k, v in scenario.items()
            if k not in ("narrative",)   # keep all except raw narrative in JSON
        }),
    )


@bp.route("/task/response", methods=["POST"])
@_require_participant
def task_response():
    pid      = _pid()
    stage    = session.get("stage", 1)
    position = session.get("scenario_position", 0)

    p        = get_participant(pid)
    group    = session.get("group", p["group_assignment"])
    modality = GROUP_MODALITY[group][stage]

    ordered_ids = get_scenario_order(pid, stage)
    sc_id       = ordered_ids[position]

    try:
        rop      = float(request.form.get("rop_adjustment", 0))
        ss       = float(request.form.get("ss_adjustment", 0))
        conf     = int(request.form.get("confidence", 4))
        elapsed  = float(request.form.get("elapsed_seconds", 0))
    except (ValueError, TypeError):
        rop, ss, conf, elapsed = 0.0, 0.0, 4, 0.0

    # Clamp values to sensible range
    rop     = max(-30.0, min(150.0, rop))
    ss      = max(-30.0, min(150.0, ss))
    conf    = max(1, min(7, conf))
    elapsed = max(0.0, elapsed)

    save_response(pid, sc_id, stage, position, modality, rop, ss, conf, elapsed)

    next_url = _next_url_after_response(pid, stage, position)
    return redirect(next_url)


# ── Trust rating (post-stage) ──────────────────────────────────────────────

@bp.route("/trust/<int:stage>", methods=["GET", "POST"])
@_require_participant
def trust_rating(stage: int):
    if request.method == "POST":
        try:
            t1 = int(request.form.get("trust_1", 4))
            t2 = int(request.form.get("trust_2", 4))
            t3 = int(request.form.get("trust_3", 4))
        except (ValueError, TypeError):
            t1 = t2 = t3 = 4

        t1 = max(1, min(7, t1))
        t2 = max(1, min(7, t2))
        t3 = max(1, min(7, t3))

        save_trust(_pid(), stage, t1, t2, t3)

        # Advance to next stage or comprehension
        if stage < 3:
            session["stage"]             = stage + 1
            session["scenario_position"] = 0
            return redirect(url_for("main.task"))
        else:
            return redirect(url_for("main.comprehension"))

    p        = get_participant(_pid())
    group    = session.get("group", p["group_assignment"])
    modality = GROUP_MODALITY[group][stage]
    return render_template("trust.html", stage=stage, modality=modality)


# ── Comprehension check ────────────────────────────────────────────────────

@bp.route("/comprehension", methods=["GET", "POST"])
@_require_participant
def comprehension():
    if request.method == "POST":
        answers = {
            "item_1": request.form.get("item_1", ""),
            "item_2": request.form.get("item_2", ""),
            "item_3": request.form.get("item_3", ""),
            "item_4": request.form.get("item_4", ""),
            "item_5": request.form.get("item_5", ""),
            "item_5_reason": request.form.get("item_5_reason", ""),
        }
        save_comprehension(_pid(), answers)
        mark_completed(_pid())
        return redirect(url_for("main.debrief"))

    return render_template("comprehension.html")


# ── Debrief ────────────────────────────────────────────────────────────────

@bp.route("/debrief")
@_require_participant
def debrief():
    pid   = _pid()
    group = session.get("group", "A")

    # Compute simple performance score (mean accuracy across responses)
    rows = get_participant_responses(pid)

    scores = []
    for row in rows:
        sc = scenario_by_id(row["scenario_id"])
        if sc:
            opt_rop = sc["optimal_rop_pct"]
            opt_ss  = sc["optimal_ss_pct"]
            if opt_rop != 0:
                acc_rop = abs(row["rop_adjustment"] - opt_rop) / abs(opt_rop)
            else:
                acc_rop = abs(row["rop_adjustment"])
            if opt_ss != 0:
                acc_ss = abs(row["ss_adjustment"] - opt_ss) / abs(opt_ss)
            else:
                acc_ss = abs(row["ss_adjustment"])
            scores.append((acc_rop + acc_ss) / 2)

    mean_error = round(sum(scores) / len(scores) * 100, 1) if scores else None

    session.clear()
    return render_template("debrief.html", mean_error=mean_error, group=group)


# ── Admin ──────────────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "research2025")


@bp.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["admin_auth"] = True
            return redirect(url_for("main.admin"))
        return render_template("admin.html", auth=False, error=True, summary=None)

    if not session.get("admin_auth"):
        return render_template("admin.html", auth=False, error=False, summary=None, vis_data=None)

    from .models import admin_summary, get_visualization_data, get_all_participants_summary
    summary = admin_summary()
    vis_data = get_visualization_data()
    participants = get_all_participants_summary()
    return render_template("admin.html", auth=True, error=False, summary=summary, vis_data=vis_data, participants=participants)

@bp.route("/admin/participant/<pid>")
def admin_participant(pid):
    if not session.get("admin_auth"):
        abort(403)
    from .models import get_participant_raw, get_scenario_order
    p = get_participant_raw(pid)
    if not p:
        abort(404)
    # We will pass the raw participant to the template
    return render_template("admin_participant.html", p=p)


@bp.route("/admin/export/responses")
def export_responses():
    if not session.get("admin_auth"):
        abort(403)
    csv_data = export_responses_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=experiment_responses.csv"},
    )


@bp.route("/admin/export/participants")
def export_participants():
    if not session.get("admin_auth"):
        abort(403)
    csv_data = export_participants_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=participants.csv"},
    )


# ── API: scenario data for charts (called by JS) ───────────────────────────

@bp.route("/api/scenario/<int:sid>")
@_require_participant
def api_scenario(sid: int):
    sc = scenario_by_id(sid)
    if not sc:
        return jsonify({"error": "not found"}), 404
    # Return only chart-relevant fields to keep payload small
    return jsonify({
        "id":               sc["id"],
        "name":             sc["name"],
        "demand_series":    sc["demand_series"],
        "ma30_series":      sc["ma30_series"],
        "disruption_start": sc["disruption_start"],
        "disruption_end":   sc["disruption_end"],
        "baseline_inventory": sc["baseline_inventory"],
        "disruption_inventory": sc["disruption_inventory"],
    })
