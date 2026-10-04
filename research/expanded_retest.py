from __future__ import annotations


def build_expanded_retest(
    robustness_result: dict,
    lifecycle_snapshot: dict,
    tail_diagnosis: dict,
    sector_diagnosis: dict,
) -> dict:
    point_in_time = lifecycle_snapshot["point_in_time"]
    original_gate = robustness_result["robustness"]["gate"]
    lifecycle_partial = (
        lifecycle_snapshot["delisted_record_count"] > 0
        and lifecycle_snapshot["current_snapshot_count"] > 0
    )

    checks = {
        "g6_frozen": robustness_result["robustness"]["champion_frozen"]
        == "mean_reversion_cost_floor:g6",
        "parameter_tuning_disabled": robustness_result["robustness"]["parameter_tuning"] is False,
        "expanded_universe": robustness_result["summary"]["eligible_symbol_count"] >= 8,
        "long_coverage": robustness_result["summary"]["evaluated_window_count"] >= 80,
        "delisted_lifecycle_loaded": lifecycle_snapshot["delisted_record_count"] > 0,
        "lifecycle_partial_reconstruction": lifecycle_partial,
        "point_in_time_verified": point_in_time["verified"],
        "robustness_soft_score_pass": original_gate["soft_score"] >= original_gate["minimum_soft_score"],
        "tail_risk_diagnosed": tail_diagnosis["status"] == "diagnosed",
        "sector_risk_diagnosed": sector_diagnosis["status"] == "diagnosed",
    }

    passed = all(checks.values())
    return {
        "endpoint": "024",
        "status": "passed" if passed else "research_hold",
        "checks": checks,
        "robustness_gate_score": original_gate["soft_score"],
        "minimum_gate_score": original_gate["minimum_soft_score"],
        "point_in_time_verified": point_in_time["verified"],
        "delisted_record_count": lifecycle_snapshot["delisted_record_count"],
        "paper_trading_allowed": passed,
        "automatic_strategy_change": False,
        "live_trading": False,
        "rationale": (
            "Expanded re-test passed all predeclared evidence gates."
            if passed
            else "Expanded re-test remains on hold: point-in-time membership and/or robustness thresholds are incomplete."
        ),
    }
