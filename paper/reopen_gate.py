from __future__ import annotations


def assess_paper_reopen_gate(
    readiness: dict,
    acceptance: dict,
    *,
    point_in_time_verified: bool,
    data_fresh: bool,
    active_strategy_key: str,
) -> dict:
    checks = {
        "shadow_evidence_sufficient": readiness.get("sufficient_evidence") is True,
        "prospective_g6_accepted": acceptance.get("accepted") is True,
        "point_in_time_verified": point_in_time_verified is True,
        "data_fresh": data_fresh is True,
        "active_strategy_is_g6": active_strategy_key == "mean_reversion_cost_floor:g6",
        "human_approval_required": True,
        "live_trading_disabled": True,
    }
    allowed = all(checks.values())

    if allowed:
        decision = "paper_gate_reopened"
        rationale = (
            "Independent forward evidence passed and the non-performance safety "
            "checks remain satisfied. Paper trading may begin, but live trading remains disabled."
        )
    elif readiness.get("sufficient_evidence") is not True:
        decision = "paper_gate_waiting_for_shadow_evidence"
        rationale = "Paper trading remains blocked until the forward sample reaches 30 days and 20 evaluated buy signals."
    elif acceptance.get("accepted") is not True:
        decision = "paper_gate_blocked_by_prospective_failure"
        rationale = "Paper trading remains blocked because the independent prospective G6 acceptance gate failed."
    else:
        decision = "paper_gate_blocked_by_safety_check"
        rationale = "Paper trading remains blocked because a non-performance safety check failed."

    return {
        "endpoint": "037",
        "status": "reopened" if allowed else "blocked",
        "decision": decision,
        "checks": checks,
        "paper_trading_allowed": allowed,
        "live_trading_allowed": False,
        "human_gate_required": True,
        "automatic_strategy_change": False,
        "rationale": rationale,
    }
