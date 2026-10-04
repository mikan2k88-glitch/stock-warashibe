from __future__ import annotations

MIN_MATERIAL_GAIN = 300.0
MIN_QUALITY_SCORE = 300.0
COMPLEXITY_PENALTY_PER_NEW_PARAMETER = 75.0

_META_KEYS = {
    "rule",
    "baseline_strategy_key",
    "baseline_generation",
    "live_trading",
    "phase",
    "derived_from_rejected_rule",
    "candidate_strategy_name",
}


def evaluate_quality(
    comparisons: list[dict],
    baseline_spec: dict | None,
    proposed_change: dict,
    criteria_passed: bool,
) -> dict:
    deltas = [float(row["delta_final_capital"]) for row in comparisons]
    positive_gain = round(sum(max(delta, 0.0) for delta in deltas), 2)
    regression_loss = round(sum(max(-delta, 0.0) for delta in deltas), 2)
    behavior_changed = any(abs(delta) >= 0.01 for delta in deltas)

    baseline_config = (baseline_spec or {}).get("config") or {}
    tuning_keys = {
        key for key in proposed_change
        if key not in _META_KEYS
    }
    added_parameters = sorted(tuning_keys - set(baseline_config))
    complexity_penalty = round(
        len(added_parameters) * COMPLEXITY_PENALTY_PER_NEW_PARAMETER,
        2,
    )
    quality_score = round(
        positive_gain - regression_loss - complexity_penalty,
        2,
    )

    reasons = []
    if not criteria_passed:
        reasons.append("acceptance_criteria_failed")
    if not behavior_changed:
        reasons.append("equivalent_behavior")
    if positive_gain < MIN_MATERIAL_GAIN:
        reasons.append("material_gain_below_threshold")
    if regression_loss > 0.0:
        reasons.append("regression_detected")
    if quality_score < MIN_QUALITY_SCORE:
        reasons.append("quality_score_below_threshold")

    accepted = not reasons
    return {
        "accepted": accepted,
        "criteria_passed": criteria_passed,
        "behavior_changed": behavior_changed,
        "positive_gain": positive_gain,
        "regression_loss": regression_loss,
        "minimum_material_gain": MIN_MATERIAL_GAIN,
        "added_parameters": added_parameters,
        "complexity_penalty": complexity_penalty,
        "minimum_quality_score": MIN_QUALITY_SCORE,
        "quality_score": quality_score,
        "reasons": reasons,
    }
