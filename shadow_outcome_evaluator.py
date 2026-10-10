from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from statistics import mean

from data.yahoo_chart_provider import YahooChartDailyBarProvider
from research.shadow_outcome import (
    AdaptiveExitPolicy,
    evaluate_adaptive_exit_challenger,
    evaluate_shadow_observation,
)


STORE_URL = "https://bittxuhjejaokfgmymkw.supabase.co/functions/v1/stock-warashibe-shadow-store"
OIDC_AUDIENCE = "stock-warashibe-supabase"
ADAPTIVE_EXIT_FROZEN_AFTER = "2026-10-10"
ADAPTIVE_MIN_OBSERVATION_DAYS = 30
ADAPTIVE_MIN_PAIRED_BUY_SIGNALS = 20

ADAPTIVE_EXIT_POLICIES = {
    "A": AdaptiveExitPolicy(
        max_holding_days=10,
        hard_stop_loss_pct=0.07,
        profit_target_pct=None,
        trailing_activation_pct=0.04,
        trailing_stop_pct=0.025,
    ),
    "B": AdaptiveExitPolicy(
        max_holding_days=10,
        hard_stop_loss_pct=0.07,
        profit_target_pct=None,
        trailing_activation_pct=0.04,
        trailing_stop_pct=0.02,
    ),
    "C": AdaptiveExitPolicy(
        max_holding_days=10,
        hard_stop_loss_pct=0.07,
        profit_target_pct=None,
        trailing_activation_pct=0.04,
        trailing_stop_pct=0.015,
    ),
    "D": AdaptiveExitPolicy(
        max_holding_days=12,
        hard_stop_loss_pct=0.05,
        profit_target_pct=None,
        trailing_activation_pct=0.04,
        trailing_stop_pct=0.015,
    ),
}


def get_oidc_token() -> str:
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    separator = "&" if "?" in request_url else "?"
    url = f"{request_url}{separator}audience={OIDC_AUDIENCE}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {request_token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)["value"]


def post_json(token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        STORE_URL,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def _aggregate_results(results: list[dict]) -> dict:
    ready = [row for row in results if row.get("ready") is True]
    pnls = [float(row["net_pnl"]) for row in ready]
    holds = [
        int(row["holding_trading_days"])
        for row in ready
        if row.get("holding_trading_days") is not None
    ]
    return {
        "matured_count": len(ready),
        "mean_net_pnl": round(mean(pnls), 4) if pnls else None,
        "cumulative_net_pnl": round(sum(pnls), 2) if pnls else 0.0,
        "win_rate": (
            round(sum(value > 0 for value in pnls) / len(pnls), 6)
            if pnls
            else None
        ),
        "average_holding_days": round(mean(holds), 4) if holds else None,
    }


def _paired_comparison(
    observations: list[dict],
    challenger_results: dict[str, dict],
) -> dict:
    deltas = []
    candidate_wins = 0
    for observation in observations:
        key = str(observation["observation_key"])
        baseline = observation.get("outcome") or {}
        challenger = challenger_results.get(key) or {}
        if baseline.get("status") != "evaluated" or challenger.get("ready") is not True:
            continue
        delta = float(challenger["net_pnl"]) - float(baseline["net_pnl"])
        deltas.append(delta)
        candidate_wins += int(delta > 0)
    return {
        "paired_count": len(deltas),
        "candidate_win_count": candidate_wins,
        "candidate_win_ratio": (
            round(candidate_wins / len(deltas), 6) if deltas else None
        ),
        "mean_net_pnl_delta_vs_fixed5": (
            round(mean(deltas), 4) if deltas else None
        ),
        "cumulative_net_pnl_delta_vs_fixed5": round(sum(deltas), 2),
    }


def _adaptive_readiness(
    prospective_buys: list[dict],
    by_policy: dict,
) -> dict:
    observation_days = len({
        str(row.get("observation_date") or "")
        for row in prospective_buys
        if row.get("observation_date")
    })
    paired_counts = [
        int((row.get("paired_vs_fixed5") or {}).get("paired_count") or 0)
        for row in by_policy.values()
    ]
    paired_count = min(paired_counts) if paired_counts else 0
    sufficient = (
        observation_days >= ADAPTIVE_MIN_OBSERVATION_DAYS
        and paired_count >= ADAPTIVE_MIN_PAIRED_BUY_SIGNALS
    )

    ranked = []
    for label, row in by_policy.items():
        paired = row.get("paired_vs_fixed5") or {}
        ranked.append({
            "label": label,
            "paired_count": int(paired.get("paired_count") or 0),
            "candidate_win_ratio": paired.get("candidate_win_ratio"),
            "mean_net_pnl_delta_vs_fixed5": paired.get(
                "mean_net_pnl_delta_vs_fixed5"
            ),
            "cumulative_net_pnl_delta_vs_fixed5": paired.get(
                "cumulative_net_pnl_delta_vs_fixed5"
            ),
        })
    ranked.sort(
        key=lambda row: (
            -(float(row["candidate_win_ratio"]) if row["candidate_win_ratio"] is not None else -1.0),
            -(float(row["mean_net_pnl_delta_vs_fixed5"]) if row["mean_net_pnl_delta_vs_fixed5"] is not None else -1e18),
            row["label"],
        )
    )

    leader = ranked[0] if sufficient and ranked else None
    leader_positive = bool(
        leader
        and float(leader.get("candidate_win_ratio") or 0) > 0.5
        and float(leader.get("mean_net_pnl_delta_vs_fixed5") or 0) > 0
        and float(leader.get("cumulative_net_pnl_delta_vs_fixed5") or 0) > 0
    )
    return {
        "status": "ready_for_review" if sufficient else "collecting",
        "observation_days": observation_days,
        "minimum_observation_days": ADAPTIVE_MIN_OBSERVATION_DAYS,
        "paired_buy_signals": paired_count,
        "minimum_paired_buy_signals": ADAPTIVE_MIN_PAIRED_BUY_SIGNALS,
        "sufficient_evidence": sufficient,
        "leader": leader,
        "leader_positive_vs_fixed5": leader_positive,
        "automatic_adoption": False,
        "human_review_required": True,
        "next_action": (
            "human_review_of_frozen_candidates"
            if sufficient
            else "continue_future_only_collection"
        ),
    }


def build_adaptive_exit_evidence(
    *,
    token: str,
    provider,
    batches: dict,
) -> dict:
    readiness = post_json(token, {"action": "readiness_data"})
    observations = readiness.get("observations") or []
    prospective_buys = [
        row
        for row in observations
        if str(row.get("signal") or "") == "buy"
        and str(row.get("observation_date") or "") > ADAPTIVE_EXIT_FROZEN_AFTER
    ]

    by_policy = {}
    for label, policy in ADAPTIVE_EXIT_POLICIES.items():
        results = {}
        for observation in prospective_buys:
            symbol = str(observation["symbol"])
            if symbol not in batches:
                batches[symbol] = provider.load_batch(symbol, as_of=date.today())
            results[str(observation["observation_key"])] = (
                evaluate_adaptive_exit_challenger(
                    observation,
                    batches[symbol],
                    policy=policy,
                )
            )
        by_policy[label] = {
            "policy": {
                "max_holding_days": policy.max_holding_days,
                "hard_stop_loss_pct": policy.hard_stop_loss_pct,
                "profit_target_pct": policy.profit_target_pct,
                "trailing_activation_pct": policy.trailing_activation_pct,
                "trailing_stop_pct": policy.trailing_stop_pct,
            },
            "metrics": _aggregate_results(list(results.values())),
            "paired_vs_fixed5": _paired_comparison(
                prospective_buys,
                results,
            ),
        }

    baseline_matured = [
        row
        for row in prospective_buys
        if (row.get("outcome") or {}).get("status") == "evaluated"
    ]
    baseline_pnls = [
        float((row.get("outcome") or {})["net_pnl"])
        for row in baseline_matured
    ]
    readiness = _adaptive_readiness(prospective_buys, by_policy)
    return {
        "frozen_after_date": ADAPTIVE_EXIT_FROZEN_AFTER,
        "prospective_rule": "observation_date_strictly_after_freeze_date",
        "candidate_set": "fixed5+A+B+C+D",
        "candidate_D_origin": "recent_30_trading_day_retrospective_diagnostic",
        "execution_policy": "daily_close_decision_next_open_execution",
        "strategy_key": "mean_reversion_cost_floor:g6",
        "prospective_buy_signal_count": len(prospective_buys),
        "fixed5_matured_count": len(baseline_matured),
        "fixed5_cumulative_net_pnl": round(sum(baseline_pnls), 2),
        "challengers": by_policy,
        "readiness": readiness,
        "automatic_adoption": False,
        "paper_gate_reopened": False,
        "paper_trading_allowed": False,
        "live_trading_allowed": False,
    }


def main() -> int:
    token = get_oidc_token()
    pending_response = post_json(token, {"action": "pending"})
    pending = pending_response.get("pending") or []

    provider = YahooChartDailyBarProvider(range_value="2y")
    batches = {}
    outcomes = []
    deferred = []

    for observation in pending:
        symbol = str(observation["symbol"])
        if symbol not in batches:
            batches[symbol] = provider.load_batch(symbol, as_of=date.today())

        result = evaluate_shadow_observation(
            observation,
            batches[symbol],
        )
        if not result["ready"]:
            deferred.append({
                "observation_key": observation["observation_key"],
                "symbol": symbol,
                **result,
            })
            continue

        outcomes.append({
            "observation_key": observation["observation_key"],
            "outcome": result,
        })

    stored = post_json(
        token,
        {
            "action": "update_outcomes",
            "outcomes": outcomes,
        },
    )

    adaptive_evidence = build_adaptive_exit_evidence(
        token=token,
        provider=provider,
        batches=batches,
    )
    adaptive_stored = post_json(
        token,
        {
            "action": "store_adaptive_exit_comparison",
            "evidence": adaptive_evidence,
        },
    )

    print(json.dumps({
        "development_endpoint": "033",
        "mode": "shadow_outcome_evaluator",
        "pending_count": len(pending),
        "matured_count": len(outcomes),
        "deferred_count": len(deferred),
        "deferred_reasons": {
            reason: sum(1 for row in deferred if row["reason"] == reason)
            for reason in sorted({row["reason"] for row in deferred})
        },
        "stored": stored,
        "adaptive_exit_comparison": adaptive_evidence,
        "adaptive_stored": adaptive_stored,
        "paper_order_created": False,
        "live_trading": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
