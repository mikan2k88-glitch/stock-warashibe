from __future__ import annotations


def diagnose_shadow_failure(readiness: dict, acceptance: dict) -> dict:
    if readiness.get("sufficient_evidence") is not True:
        return {
            "endpoint": "036",
            "status": "insufficient_evidence",
            "classification": "collect_more_forward_evidence",
            "failed_checks": [],
            "automatic_strategy_change": False,
            "g7_generation_allowed": False,
            "paper_trading_allowed": False,
            "rationale": (
                "The shadow sample has not reached the predeclared evidence minimum, "
                "so this is not classified as a G6 strategy failure."
            ),
        }

    if acceptance.get("accepted") is True:
        return {
            "endpoint": "036",
            "status": "no_failure",
            "classification": "prospective_gate_passed",
            "failed_checks": [],
            "automatic_strategy_change": False,
            "g7_generation_allowed": False,
            "paper_trading_allowed": False,
            "rationale": "No shadow failure diagnosis is required because the prospective gate passed.",
        }

    failed = [
        name
        for name, passed in (acceptance.get("checks") or {}).items()
        if passed is False
    ]
    categories = []
    if "win_rate_at_least_45pct" in failed:
        categories.append("low_forward_win_rate")
    if "mean_return_non_negative" in failed or "cumulative_net_pnl_positive" in failed:
        categories.append("negative_forward_edge")
    if "worst_return_above_minus_5pct" in failed:
        categories.append("severe_single_shadow_loss")
    if "drawdown_proxy_above_minus_10pct" in failed:
        categories.append("shadow_drawdown_instability")

    return {
        "endpoint": "036",
        "status": "diagnosed",
        "classification": "prospective_g6_failure",
        "failed_checks": failed,
        "failure_categories": categories,
        "automatic_strategy_change": False,
        "g7_generation_allowed": False,
        "paper_trading_allowed": False,
        "next_action": (
            "Open a new research hypothesis only after the forward failure evidence "
            "is reviewed; do not retune G6 in place."
        ),
        "rationale": "Sufficient independent evidence exists and the prospective G6 gate failed.",
    }
