from __future__ import annotations


def assess_paper_readiness(
    expanded_retest: dict,
    *,
    data_fresh: bool,
    active_strategy_key: str,
) -> dict:
    checks = {
        "expanded_retest_passed": expanded_retest["status"] == "passed",
        "point_in_time_verified": expanded_retest["point_in_time_verified"] is True,
        "robustness_score_passed": (
            expanded_retest["robustness_gate_score"]
            >= expanded_retest["minimum_gate_score"]
        ),
        "data_fresh": data_fresh,
        "active_strategy_is_g6": active_strategy_key == "mean_reversion_cost_floor:g6",
        "human_approval_required": True,
        "live_trading_disabled": True,
    }
    allowed = all(checks.values())
    return {
        "endpoint": "025",
        "status": "ready" if allowed else "blocked",
        "checks": checks,
        "paper_trading_allowed": allowed,
        "live_trading_allowed": False,
        "human_approval_required": True,
        "reason": None if allowed else "predeclared_research_or_bias_gate_not_satisfied",
    }
