from __future__ import annotations

from datetime import date


def _days_since(value: str | None, *, as_of: date) -> int | None:
    if not value:
        return None
    try:
        return max(0, (as_of - date.fromisoformat(str(value)[:10])).days)
    except ValueError:
        return None


def build_runtime_status(context: dict, *, as_of: date, run_id: str) -> dict:
    shadow = context.get("shadow_readiness") or {}
    reopen = shadow.get("reopen_gate") or {}
    observations = list(context.get("observations") or [])
    sessions = list(context.get("paper_sessions") or [])
    orders = list(context.get("paper_orders") or [])
    active_strategy = context.get("active_strategy") or {}
    performance = context.get("latest_performance") or {}

    latest_observation_date = max(
        (str(row.get("observation_date") or "") for row in observations),
        default="",
    ) or None
    observation_age_days = _days_since(latest_observation_date, as_of=as_of)

    active_sessions = [
        row for row in sessions
        if row.get("status") in {"ready", "active"}
    ]
    live_orders = [
        row for row in orders
        if row.get("live_order") is True
    ]

    checks = {
        "active_strategy_is_g6": (
            active_strategy.get("strategy_key") == "mean_reversion_cost_floor:g6"
        ),
        "shadow_readiness_present": bool(shadow),
        "shadow_observations_present": bool(observations),
        "latest_observation_not_stale": (
            observation_age_days is not None and observation_age_days <= 5
        ),
        "no_live_orders": not live_orders,
        "no_paper_session_before_reopen": (
            reopen.get("paper_trading_allowed") is True
            or not active_sessions
        ),
        "live_trading_disabled": context.get("live_trading_allowed") is False,
        "broker_not_connected": context.get("broker_connected") is False,
    }

    critical = {
        "active_strategy_is_g6",
        "shadow_readiness_present",
        "no_live_orders",
        "no_paper_session_before_reopen",
        "live_trading_disabled",
        "broker_not_connected",
    }
    critical_failures = [
        name for name in critical if checks.get(name) is not True
    ]

    if critical_failures:
        status = "degraded"
    elif reopen.get("paper_trading_allowed") is True:
        status = "healthy"
    elif shadow.get("status") in {"collecting", "rejected", "blocked"}:
        status = "collecting"
    else:
        status = "blocked"

    summary = {
        "endpoint": "044",
        "active_strategy": active_strategy.get("strategy_key"),
        "shadow_status": shadow.get("status"),
        "shadow_observation_days": shadow.get("observation_days", 0),
        "shadow_evaluated_buy_signals": shadow.get("evaluated_buy_signals", 0),
        "paper_gate_status": reopen.get("status"),
        "paper_gate_decision": reopen.get("decision"),
        "paper_trading_allowed": reopen.get("paper_trading_allowed") is True,
        "active_paper_sessions": len(active_sessions),
        "paper_performance_status": performance.get("status"),
        "paper_days": performance.get("paper_days", 0),
        "closed_paper_trades": performance.get("closed_trades", 0),
        "latest_observation_date": latest_observation_date,
        "latest_observation_age_days": observation_age_days,
        "live_order_count": len(live_orders),
        "live_trading_allowed": False,
        "broker_connected": False,
    }
    return {
        "endpoint": "044",
        "snapshot_key": f"runtime-status-{run_id}",
        "status": status,
        "summary": summary,
        "checks": checks,
        "critical_failures": critical_failures,
    }
