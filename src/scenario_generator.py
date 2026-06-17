"""
Synthetic supply chain disruption scenario generator.
Produces 12 calibrated scenarios (3 severity × 2 ambiguity × 2 per cell)
for the modality experiment.

Reuses numpy/pandas approach from SCADE's generate_data.py but pivots to
demand time-series instead of procurement event logs.
"""

import numpy as np
import json
from pathlib import Path

# ── Constants ───────────────────────────────────────────────────────────────
SEED            = 42
N_DAYS          = 180
BASELINE_DAYS   = 60       # pre-disruption period
LEAD_TIME       = 10       # days (fixed for comparability across scenarios)
SERVICE_LEVEL_Z = 1.645    # 95% service level
BASE_MEAN       = 100.0    # baseline daily demand (units)
BASE_STD        = 15.0     # baseline daily demand std

SEVERITY_PARAMS = {
    "mild":     {"shock_mult": 1.22, "cv_mult": 1.35, "duration": 30, "recovery": 25},
    "moderate": {"shock_mult": 1.42, "cv_mult": 1.85, "duration": 45, "recovery": 35},
    "severe":   {"shock_mult": 1.78, "cv_mult": 2.55, "duration": 60, "recovery": 50},
}

# AI heuristic shock-cut suggestions per severity (shown in all 3 modalities)
AI_SUGGESTIONS = {
    "mild":     {"rop_pct": 18.0, "ss_pct": 22.0},
    "moderate": {"rop_pct": 36.0, "ss_pct": 46.0},
    "severe":   {"rop_pct": 63.0, "ss_pct": 79.0},
}

# 12 scenario archetypes — balanced stage assignment is baked in at the end
ARCHETYPES = [
    # --- Mild / Clear (2) ---
    {
        "id": 1, "severity": "mild", "ambiguity": "clear",
        "type": "port_delay", "name": "Port Congestion Delay",
        "stage_assignment": 1,
        "narrative_archetype": "A regional port is experiencing heavy congestion due to a labour slowdown. Container dwell times have increased by 40%, delaying inbound shipments. The signal is unambiguous: residuals spiked sharply on Day 61 and have remained elevated.",
    },
    {
        "id": 2, "severity": "mild", "ambiguity": "clear",
        "type": "supplier_stockout_minor", "name": "Minor Supplier Stockout",
        "stage_assignment": 2,
        "narrative_archetype": "A tier-2 supplier of a key sub-component has reported a 3-week stockout due to raw material shortages. Impact is contained to a single SKU family. Disruption onset was abrupt and clearly visible in the residual series.",
    },
    # --- Mild / Ambiguous (2) ---
    {
        "id": 3, "severity": "mild", "ambiguity": "ambiguous",
        "type": "seasonal_overlap", "name": "Seasonal Demand Overlap",
        "stage_assignment": 1,
        "narrative_archetype": "A mild demand uptick is coinciding with a routine seasonal peak. It is unclear whether the elevated residuals reflect the start of a genuine disruption or normal seasonal variation. The disruption window boundary is indistinct.",
    },
    {
        "id": 4, "severity": "mild", "ambiguity": "ambiguous",
        "type": "promotional_uplift", "name": "Promotional Demand Spike",
        "stage_assignment": 3,
        "narrative_archetype": "A downstream retailer ran an unscheduled promotional campaign, causing a moderate demand spike. The spike partially overlaps with a pre-existing upward trend, making it difficult to isolate the incremental disruption effect.",
    },
    # --- Moderate / Clear (2) ---
    {
        "id": 5, "severity": "moderate", "ambiguity": "clear",
        "type": "weather_event", "name": "Regional Weather Event",
        "stage_assignment": 1,
        "narrative_archetype": "Severe flooding has disrupted road freight networks in the supplier's manufacturing region. Logistics lead times have doubled and inbound volumes have halved. The demand residual spike is sharp, unambiguous, and coincides precisely with the weather event date.",
    },
    {
        "id": 6, "severity": "moderate", "ambiguity": "clear",
        "type": "regulatory_change", "name": "Regulatory Import Restriction",
        "stage_assignment": 2,
        "narrative_archetype": "A new import tariff on a key raw material category was announced and implemented with 2 weeks' notice. Supply costs have risen 28% and some suppliers have temporarily suspended shipments. The disruption boundary is clear.",
    },
    # --- Moderate / Ambiguous (2) ---
    {
        "id": 7, "severity": "moderate", "ambiguity": "ambiguous",
        "type": "geopolitical_tension", "name": "Geopolitical Trade Tension",
        "stage_assignment": 2,
        "narrative_archetype": "Escalating trade disputes have introduced uncertainty across multiple supplier geographies. Some shipments are delayed, others rerouted. The aggregate demand signal shows elevated variance and a moderate upward residual, but the disruption onset is gradual and partly masked by normal demand fluctuation.",
    },
    {
        "id": 8, "severity": "moderate", "ambiguity": "ambiguous",
        "type": "logistics_disruption", "name": "Multi-Modal Logistics Failure",
        "stage_assignment": 3,
        "narrative_archetype": "Simultaneous capacity constraints across air and sea freight have extended lead times by 15–35 days depending on the lane. The bullwhip effect is amplifying upstream. The signal blends genuine supply constraint with demand variability from safety-stocking by downstream buyers.",
    },
    # --- Severe / Clear (2) ---
    {
        "id": 9, "severity": "severe", "ambiguity": "clear",
        "type": "factory_shutdown", "name": "Supplier Factory Shutdown",
        "stage_assignment": 1,
        "narrative_archetype": "The primary supplier has issued a force majeure notice and suspended all production for an estimated 6–8 weeks due to a major equipment failure. Inbound supply has dropped to zero. The disruption is confirmed, acute, and unambiguous — residuals have spiked to 3.8σ above baseline.",
    },
    {
        "id": 10, "severity": "severe", "ambiguity": "clear",
        "type": "demand_spike", "name": "Emergency Demand Surge",
        "stage_assignment": 2,
        "narrative_archetype": "A public health advisory has triggered an emergency demand surge for the product category, with orders increasing 80% above baseline within 72 hours. The signal is clear: a step-change disruption with no ambiguity about onset. The challenge is calibrating the correct inventory response.",
    },
    # --- Severe / Ambiguous (2) ---
    {
        "id": 11, "severity": "severe", "ambiguity": "ambiguous",
        "type": "demonetization_shock", "name": "Demonetization-Type Policy Shock",
        "stage_assignment": 3,
        "narrative_archetype": "A sudden government monetary policy announcement has disrupted consumer purchasing patterns and payment flows across the supply chain. Both demand and supply sides are affected simultaneously. The magnitude and duration of impact are uncertain; early indicators show high variance with a downward-then-upward residual pattern.",
    },
    {
        "id": 12, "severity": "severe", "ambiguity": "ambiguous",
        "type": "multifactor_disruption", "name": "Multi-Factor Supply Collapse",
        "stage_assignment": 3,
        "narrative_archetype": "Multiple concurrent shocks — a supplier insolvency, a logistics strike, and an unexpected demand rally — are interacting non-linearly. The compound disruption signal is extremely high variance. The bullwhip ratio is at 3.1x and it is unclear which factor is driving the dominant residual.",
    },
]


def _compute_optimal_inventory(demand_series, lead_time=LEAD_TIME, z=SERVICE_LEVEL_Z):
    """Compute optimal ROP and SS from a demand series."""
    mu    = float(np.mean(demand_series))
    sigma = float(np.std(demand_series, ddof=1))
    ss    = z * sigma * np.sqrt(lead_time)
    rop   = mu * lead_time + ss
    return {
        "mean":  round(mu, 2),
        "std":   round(sigma, 2),
        "ss":    round(ss, 2),
        "rop":   round(rop, 2),
    }


def _compute_metrics(baseline_series, disruption_series):
    """Compute disruption metrics: r(t) peak, CV window, bullwhip ratio, Pass/Fail."""
    baseline_mean = np.mean(baseline_series)
    baseline_std  = np.std(baseline_series, ddof=1)

    # Normalized residual for last value in disruption window (peak)
    r_t_peak      = float((np.max(disruption_series) - baseline_mean) / baseline_std)
    # Also store full r(t) series for numerical panel
    r_t_series    = [(float(d) - baseline_mean) / baseline_std for d in disruption_series]

    cv_baseline   = float(baseline_std / baseline_mean)
    cv_window     = float(np.std(disruption_series, ddof=1) / np.mean(disruption_series))
    bullwhip      = round(cv_window / cv_baseline, 3)

    # Pass/Fail: bullwhip > 1.4 triggers disruption flag
    pass_fail     = "FAIL" if bullwhip > 1.4 else "PASS"

    return {
        "normalized_residual_peak":   round(r_t_peak, 3),
        "r_t_series":                 [round(x, 3) for x in r_t_series],
        "cv_baseline":                round(cv_baseline, 3),
        "cv_window":                  round(cv_window, 3),
        "bullwhip_ratio":             bullwhip,
        "disruption_window_days":     len(disruption_series),
        "pass_fail":                  pass_fail,
    }


def _seasonal_pattern(t, amplitude=8.0, period=90):
    """Mild sinusoidal seasonality."""
    return amplitude * np.sin(2 * np.pi * t / period)


def generate_scenario(archetype: dict, rng: np.random.Generator) -> dict:
    """
    Generate one scenario's full time series and all derived quantities.
    Returns a rich dict ready for JSON serialisation.
    """
    sev    = archetype["severity"]
    amb    = archetype["ambiguity"]
    params = SEVERITY_PARAMS[sev]

    # ── Build baseline demand (60 days, with mild seasonality + noise) ──────
    t_base   = np.arange(BASELINE_DAYS)
    baseline = (
        BASE_MEAN
        + _seasonal_pattern(t_base)
        + rng.normal(0, BASE_STD, BASELINE_DAYS)
    )
    baseline = np.clip(baseline, 10, None)

    # ── Disruption onset: clear = sharp step, ambiguous = gradual ramp ──────
    dur       = params["duration"]
    rec_days  = params["recovery"]
    shock_m   = params["shock_mult"]
    cv_m      = params["cv_mult"]
    dist_std  = BASE_STD * cv_m   # increased variability during disruption

    t_dis     = np.arange(dur)
    if amb == "clear":
        # Sharp onset: full shock from day 1
        shock_envelope = shock_m * np.ones(dur)
    else:
        # Gradual ramp: linear ramp over first 1/3, then plateau
        ramp_len = dur // 3
        ramp     = np.linspace(1.0, shock_m, ramp_len)
        plateau  = shock_m * np.ones(dur - ramp_len)
        shock_envelope = np.concatenate([ramp, plateau])

    disruption = (
        BASE_MEAN * shock_envelope
        + _seasonal_pattern(t_dis + BASELINE_DAYS)
        + rng.normal(0, dist_std, dur)
    )
    disruption = np.clip(disruption, 10, None)

    # ── Recovery: exponential decay back to baseline ─────────────────────────
    t_rec    = np.arange(rec_days)
    decay    = np.exp(-t_rec / (rec_days / 3))
    excess   = (shock_m - 1.0) * BASE_MEAN
    recovery = (
        BASE_MEAN + excess * decay
        + _seasonal_pattern(t_rec + BASELINE_DAYS + dur)
        + rng.normal(0, BASE_STD, rec_days)
    )
    recovery = np.clip(recovery, 10, None)

    # Pad remainder of 180 days with normal demand
    remaining = N_DAYS - BASELINE_DAYS - dur - rec_days
    if remaining > 0:
        t_rem  = np.arange(remaining)
        normal_tail = (
            BASE_MEAN
            + _seasonal_pattern(t_rem + BASELINE_DAYS + dur + rec_days)
            + rng.normal(0, BASE_STD, remaining)
        )
        normal_tail = np.clip(normal_tail, 10, None)
        full_series = np.concatenate([baseline, disruption, recovery, normal_tail])
    else:
        full_series = np.concatenate([baseline, disruption, recovery])[:N_DAYS]

    # Moving average (30-day) for visual modality baseline overlay
    ma30 = np.convolve(full_series, np.ones(30) / 30, mode="same")
    # Edge-correct: first 29 days use expanding mean
    for i in range(29):
        ma30[i] = np.mean(full_series[:i+1])

    # ── Inventory calculations ───────────────────────────────────────────────
    baseline_inv   = _compute_optimal_inventory(baseline)
    disruption_inv = _compute_optimal_inventory(disruption)

    # % adjustments from baseline to optimal disruption values
    optimal_rop_pct = round((disruption_inv["rop"] - baseline_inv["rop"]) / baseline_inv["rop"] * 100, 2)
    optimal_ss_pct  = round((disruption_inv["ss"]  - baseline_inv["ss"])  / baseline_inv["ss"]  * 100, 2)

    # ── Disruption metrics ───────────────────────────────────────────────────
    metrics = _compute_metrics(baseline, disruption)

    # ── AI suggestion ────────────────────────────────────────────────────────
    ai_sug = AI_SUGGESTIONS[sev]

    # ── Slider calibration (visible range for UI: anchored around AI suggestion) ─
    # Range is AI suggestion ± 40pp, clamped to reasonable bounds
    rop_range = [
        max(-30.0, round(ai_sug["rop_pct"] - 40, 0)),
        min(150.0, round(ai_sug["rop_pct"] + 50, 0)),
    ]
    ss_range = [
        max(-30.0, round(ai_sug["ss_pct"] - 40, 0)),
        min(150.0, round(ai_sug["ss_pct"] + 50, 0)),
    ]

    # ── LLM narrative (pre-generated, simulating GPT-4.1 output) ────────────
    narrative = _build_narrative(archetype, metrics, ai_sug, baseline_inv, disruption_inv,
                                  optimal_rop_pct, optimal_ss_pct)

    # ── Comprehension check data (scenario 1 is used in comprehension) ───────
    # These are fixed values used in post-task comprehension items 1-4

    return {
        "id":           archetype["id"],
        "name":         archetype["name"],
        "severity":     sev,
        "ambiguity":    amb,
        "type":         archetype["type"],
        "stage_assignment": archetype["stage_assignment"],
        "description":  archetype["narrative_archetype"],

        # Full time series (180 days)
        "demand_series":     [round(float(x), 1) for x in full_series],
        "ma30_series":       [round(float(x), 1) for x in ma30],

        # Disruption window indices
        "disruption_start":  BASELINE_DAYS,
        "disruption_end":    BASELINE_DAYS + dur,
        "lead_time":         LEAD_TIME,

        # Inventory model outputs
        "baseline_inventory":   baseline_inv,
        "disruption_inventory": disruption_inv,
        "optimal_rop_pct":      optimal_rop_pct,
        "optimal_ss_pct":       optimal_ss_pct,

        # AI suggestion (shown on all modality panels)
        "ai_suggested_rop_pct": ai_sug["rop_pct"],
        "ai_suggested_ss_pct":  ai_sug["ss_pct"],

        # Slider range for UI
        "slider_rop_range":  rop_range,
        "slider_ss_range":   ss_range,

        # Disruption metrics for numerical modality panel
        "metrics": metrics,

        # LLM narrative for LLM modality panel
        "narrative": narrative,
    }


def _build_narrative(arch, metrics, ai_sug, base_inv, dis_inv, rop_pct, ss_pct) -> str:
    """
    Build a structured LLM-style narrative explanation.
    Simulates GPT-4.1 output (temp=0) with the PACIS prompt architecture.
    """
    sev   = arch["severity"]
    amb   = arch["ambiguity"]
    atype = arch["type"]
    name  = arch["name"]

    severity_text = {
        "mild":     "minor",
        "moderate": "moderate",
        "severe":   "severe",
    }[sev]

    ambiguity_text = {
        "clear":     "The disruption signal is clear and unambiguous.",
        "ambiguous": "The disruption onset is gradual and partially overlaps with background demand variation, introducing uncertainty about its precise magnitude.",
    }[amb]

    # Half-life estimate (time to 50% recovery)
    half_life = {
        "mild":     "approximately 12–18 days",
        "moderate": "approximately 20–30 days",
        "severe":   "approximately 35–55 days",
    }[sev]

    archetype_analogy = {
        "port_delay":            "This pattern is consistent with a Port Congestion archetype — a supply-side delay with contained demand impact.",
        "supplier_stockout_minor": "This resembles a Single-Supplier Stockout — limited in scope and typically self-correcting once the supplier restocks.",
        "seasonal_overlap":      "This resembles a Seasonal Demand Overlay — elevated baseline complicates isolation of the true disruption component.",
        "promotional_uplift":    "This matches a Demand Amplification archetype — a short-lived demand spike driven by downstream retailer action.",
        "weather_event":         "This is consistent with a Regional Infrastructure Disruption — supply-side capacity loss with predictable recovery trajectory.",
        "regulatory_change":     "This matches a Policy Shock archetype — a step-change in operating costs with persistent (not transient) inventory implications.",
        "geopolitical_tension":  "This resembles a Geopolitical Risk Cascade — multi-geography impact with high uncertainty about duration and resolution.",
        "logistics_disruption":  "This is consistent with a Systemic Logistics Constraint — demand appears stable but effective supply availability is compromised.",
        "factory_shutdown":      "This is a Force Majeure Supply Stoppage — the most acute disruption archetype, requiring immediate safety stock uplift.",
        "demand_spike":          "This matches an Emergency Demand Surge — supply chain must respond to a step-change in downstream pull within 72–96 hours.",
        "demonetization_shock":  "This resembles a Macro-Economic Policy Shock — simultaneous disruption to both demand patterns and payment flows, historically characterized by high short-term variance followed by gradual normalization.",
        "multifactor_disruption":"This is a Compound Disruption — multiple independent shocks have combined non-linearly. Historical analogues suggest high estimation error; conservative inventory uplifts are advisable.",
    }.get(atype, "This disruption does not cleanly match a single historical archetype.")

    narrative = f"""DISRUPTION ANALYSIS — AI RECOMMENDATION
════════════════════════════════════════

SHOCK SUMMARY
Disruption type: {name}
Severity classification: {severity_text.upper()}
Signal clarity: {"CLEAR" if amb == "clear" else "AMBIGUOUS"}

{ambiguity_text}

KEY INDICATORS
• Normalized residual (peak): {metrics['normalized_residual_peak']:.2f}σ above baseline
• Coefficient of variation (disruption window): {metrics['cv_window']:.3f}
• Bullwhip variance ratio: {metrics['bullwhip_ratio']:.2f}x baseline CV
• Disruption window: {metrics['disruption_window_days']} days
• AI classification: {metrics['pass_fail']} — {"disruption confirmed" if metrics['pass_fail'] == 'FAIL' else "borderline — monitor"}

ARCHETYPE CLASSIFICATION
{archetype_analogy}

HALF-LIFE ESTIMATE
Expected time to 50% demand normalization: {half_life}.
This estimate assumes no secondary shocks and is conditional on the archetype classification above.

RECOMMENDED INVENTORY ADJUSTMENT
Based on the shock magnitude, variance ratio, and archetype half-life, the system recommends:
  • Reorder Point (ROP): increase by {ai_sug['rop_pct']:.0f}%
  • Safety Stock (SS):   increase by {ai_sug['ss_pct']:.0f}%

REASONING
{"The numerical anchor is firm: a " + str(metrics['normalized_residual_peak']) + "σ residual with a bullwhip ratio of " + str(metrics['bullwhip_ratio']) + "x warrants a precautionary uplift proportional to the observed variance expansion." if amb == "clear" else "Given ambiguity in disruption onset, the recommendation is calibrated conservatively — the upper bound of the disruption range is used to avoid stockout risk. If subsequent data clarifies the signal as lower-severity, adjustments can be reversed within 7–10 days."}

NOTE: This recommendation represents the AI system's best estimate given available data. The final adjustment decision rests with the planner. Use your judgment to accept, modify, or override.
"""
    return narrative.strip()


def generate_all_scenarios(output_path: str = None) -> list:
    """Generate all 12 scenarios and return as a list of dicts."""
    rng       = np.random.default_rng(SEED)
    scenarios = []

    for arch in ARCHETYPES:
        # Give each scenario a slightly different seed offset for independence
        scenario_rng = np.random.default_rng(SEED + arch["id"] * 137)
        sc           = generate_scenario(arch, scenario_rng)
        scenarios.append(sc)
        print(f"  Generated scenario {sc['id']:2d}: {sc['name']:<40} "
              f"opt_rop={sc['optimal_rop_pct']:+.1f}%  opt_ss={sc['optimal_ss_pct']:+.1f}%")

    # Group by stage for convenience
    by_stage = {1: [], 2: [], 3: []}
    for sc in scenarios:
        by_stage[sc["stage_assignment"]].append(sc["id"])

    print(f"\nStage assignments: {by_stage}")

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(scenarios, f, indent=2)
        print(f"\nSaved to {output_path}")

    return scenarios


if __name__ == "__main__":
    print("Generating 12 supply chain disruption scenarios...\n")
    generate_all_scenarios("data/scenarios.json")
