from __future__ import annotations


MIN_WIN_RATE = 0.45
MIN_MEAN_RETURN = 0.0
MIN_CUMULATIVE_NET_PNL = 0.0
MIN_WORST_RETURN = -0.05
MIN_DRAWDOWN_PROXY_RATIO = -0.10


def assess_prospective_acceptance(readiness: dict) -> dict:
    metrics = readiness.get("metrics") or {}

    if readiness.get("sufficient_evidence") is not True:
        return {
            "endpoint": "035",
            "status": "collecting",
            "decision": "insufficient_forward_evidence",
            "accepted": False,
            "checks": {
                "sufficient_evidence": False,
            },
            "rationale": (
                "Prospective G6 acceptance cannot be judged until the predeclared "
                "30 observation days and 20 evaluated buy signals are available."
            ),
            "paper_trading_allowed": False,
            "automatic_strategy_change": False,
            "live_trading": False,
        }

    checks = {
        "sufficient_evidence": True,
        "win_rate_at_least_45pct": float(metrics["win_rate"]) >= MIN_WIN_RATE,
        "mean_return_non_negative": (
            float(metrics["mean_return_on_starting_capital"]) >= MIN_MEAN_RETURN
        ),
        "cumulative_net_pnl_positive": (
            float(metrics["cumulative_net_pnl"]) > MIN_CUMULATIVE_NET_PNL
        ),
        "worst_return_above_minus_5pct": (
            float(metrics["worst_return_on_starting_capital"]) >= MIN_WORST_RETURN
        ),
        "drawdown_proxy_above_minus_10pct": (
            float(metrics["max_drawdown_proxy_ratio"]) >= MIN_DRAWDOWN_PROXY_RATIO
        ),
    }
    accepted = all(checks.values())
    return {
        "endpoint": "035",
        "status": "accepted" if accepted else "rejected",
        "decision": (
            "prospective_g6_accepted"
            if accepted
            else "prospective_g6_rejected"
        ),
        "accepted": accepted,
        "checks": checks,
        "thresholds": {
            "minimum_observation_days": 30,
            "minimum_evaluated_buy_signals": 20,
            "minimum_win_rate": MIN_WIN_RATE,
            "minimum_mean_return": MIN_MEAN_RETURN,
            "minimum_cumulative_net_pnl": MIN_CUMULATIVE_NET_PNL,
            "minimum_worst_return": MIN_WORST_RETURN,
            "minimum_drawdown_proxy_ratio": MIN_DRAWDOWN_PROXY_RATIO,
        },
        "rationale": (
            "Independent forward evidence passed all predeclared G6 acceptance criteria."
            if accepted
            else "Independent forward evidence is sufficient but one or more predeclared performance criteria failed."
        ),
        "paper_trading_allowed": False,
        "automatic_strategy_change": False,
        "live_trading": False,
    }
