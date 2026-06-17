from app.routes import bp
from app.models import get_participant_responses
import json
import os

with open("data/scenarios.json") as f:
    scenarios = json.load(f)

sc = scenarios[0]

opt_rop = sc["optimal_rop_pct"]
opt_ss  = sc["optimal_ss_pct"]

print("opt_rop:", opt_rop, type(opt_rop))

row = {"rop_adjustment": 10.0, "ss_adjustment": 5.0, "scenario_id": 1}

acc_rop = abs(row["rop_adjustment"] - opt_rop) / abs(opt_rop) if opt_rop != 0 else abs(row["rop_adjustment"])
acc_ss = abs(row["ss_adjustment"] - opt_ss) / abs(opt_ss) if opt_ss != 0 else abs(row["ss_adjustment"])
score = (acc_rop + acc_ss) / 2
print("Score:", score)

