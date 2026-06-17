"""
Entry point for the modality experiment platform.
Ensures scenario data exists before starting Flask.
"""
from dotenv import load_dotenv
load_dotenv()

import os
import sys

DATA_DIR       = os.path.join(os.path.dirname(__file__), "data")
SCENARIOS_PATH = os.path.join(DATA_DIR, "scenarios.json")


def ensure_scenarios():
    if not os.path.exists(SCENARIOS_PATH):
        print("scenarios.json not found — generating now...")
        os.makedirs(DATA_DIR, exist_ok=True)
        from src.scenario_generator import generate_all_scenarios
        generate_all_scenarios(SCENARIOS_PATH)
        print("Done.\n")


def create_app():
    ensure_scenarios()
    from app import create_app as _create
    return _create()


app = create_app()

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f"\n  Modality Experiment Platform")
    print(f"  Running on http://127.0.0.1:{port}")
    print(f"  Admin panel: http://127.0.0.1:{port}/admin\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
