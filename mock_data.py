import random
import uuid
from datetime import datetime, timezone
from app.models import _col
from dotenv import load_dotenv

load_dotenv()
col = _col()

# Generate 20 dummy participants
dummy_docs = []
for i in range(20):
    group = random.choice(["A", "B"])
    doc = {
        "session_token": str(uuid.uuid4()),
        "group_assignment": group,
        "created_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
        "demographics": {
            "program": random.choice(["btech_cs", "mtech", "bba", "bsc_math"]),
            "year_of_study": random.choice(["1", "2", "3", "4", "postgrad"]),
            "sc_exposure": random.choice(["none", "1_2_courses", "extensive"]),
            "ai_familiarity": random.choice(["never", "rarely", "regularly", "expert"]),
            "gender": random.choice(["male", "female", "prefer_not_to_say"])
        },
        "scenario_orders": {"stage1": [1,3,5,9], "stage2": [2,6,7,10], "stage3": [4,8,11,12]},
        "progress": {"tutorial_passed": True, "completed": True},
        "responses": [],
        "trust_ratings": [],
        "comprehension": {
            "answers": {
                "item_1": random.choice(["A", "B", "C"]),
                "item_2": random.choice(["PASS", "FAIL"]),
                "item_4": random.randint(30, 80),
                "item_5": random.choice(["numerical", "visual", "llm"])
            },
            "scores": {
                "item_1_correct": random.random() > 0.3,
                "item_2_correct": random.random() > 0.4,
                "item_4_correct": random.random() > 0.5
            },
            "submitted_at": datetime.now(timezone.utc).isoformat()
        }
    }
    dummy_docs.append(doc)

if dummy_docs:
    col.insert_many(dummy_docs)
    print(f"Inserted {len(dummy_docs)} mock participants for visualization testing.")
