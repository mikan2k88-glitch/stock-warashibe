from __future__ import annotations

from statistics import mean

from config import STARTING_CAPITAL


MIN_OBSERVATION_DAYS = 30
MIN_EVALUATED_BUY_SIGNALS = 20


def aggregate_shadow_readiness(observations: list[dict]) -> dict:
    observation_days = sorted(
        {
            str(row["observation_date"])
            for row in observations
            if row.get("observation_date")
        }
    )

    evaluated_buys = []
    for row in observations:
        if row.get("status") != "evaluated" or row.get("signal") != "buy":
            continue
        outcome = row.get("outcome") or {}
        if outcome.get("ready") is not True:
            continue
        if outcome.get("executable_with_starting_capital") is not True:
            continue
        if outcome.get("counterfactual_only") is True:
            continue
        evaluated_buys.append(row)

    evaluated_buys.sort(
        key=lambda row: (
            str((row.get("outcome") or {}).get("exit_date") or ""),
            str(row.get("symbol") or ""),
        )
    )

    pnl_values = [
        float((row.get("outcome") or {}).get("net_pnl") or 0.0)
        for row in evaluated_buys
    ]
    returns = [
        float((row.get("outcome") or {}).get("return_on_starting_capital") or 0.0)
        for row in evaluated_buys
    ]

    cumulative_pnl = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnl_values:
        cumulative_pnl += pnl
        peak = max(peak, cumulative_pnl)
        max_drawdown = min(max_drawdown, cumulative_pnl - peak)

    wins = sum(pnl > 0 for pnl in pnl_values)
    evidence_checks = {
        "minimum_30_observation_days": len(observation_days) >= MIN_OBSERVATION_DAYS,
        "minimum_20_evaluated_buy_signals": (
            len(evaluated_buys) >= MIN_EVALUATED_BUY_SIGNALS
        ),
    }
    sufficient = all(evidence_checks.values())

    return {
        "endpoint": "034",
        "status": "ready_for_acceptance" if sufficient else "collecting",
        "strategy_key": "mean_reversion_cost_floor:g6",
        "observation_days": len(observation_days),
        "first_observation_date": observation_days[0] if observation_days else None,
        "last_observation_date": observation_days[-1] if observation_days else None,
        "evaluated_buy_signals": len(evaluated_buys),
        "sufficient_evidence": sufficient,
        "evidence_checks": evidence_checks,
        "metrics": {
            "win_rate": round(wins / len(pnl_values), 6) if pnl_values else None,
            "mean_net_pnl": round(mean(pnl_values), 2) if pnl_values else None,
            "cumulative_net_pnl": round(sum(pnl_values), 2),
            "mean_return_on_starting_capital": (
                round(mean(returns), 6) if returns else None
            ),
            "worst_return_on_starting_capital": (
                round(min(returns), 6) if returns else None
            ),
            "max_drawdown_proxy_yen": round(max_drawdown, 2),
            "max_drawdown_proxy_ratio": round(max_drawdown / STARTING_CAPITAL, 6),
        },
        "paper_order_created": False,
        "live_trading": False,
    }
