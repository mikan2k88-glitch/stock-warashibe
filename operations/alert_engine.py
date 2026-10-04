from __future__ import annotations

from datetime import date


ALERT_SPECS = {
    "strategy_mismatch": ("critical", "strategy", "Active strategy is not G6."),
    "missing_shadow_state": ("critical", "shadow", "Shadow readiness state is missing."),
    "stale_shadow_data": ("warning", "data_freshness", "Latest shadow observation is stale."),
    "paper_started_early": ("critical", "gate", "Paper session exists before the paper gate reopened."),
    "live_order_detected": ("critical", "live_safety", "A live order flag was detected."),
    "integrity_failure": ("critical", "evidence", "Evidence integrity audit failed."),
    "aged_pending_outcomes": ("warning", "shadow", "Shadow outcomes have remained pending too long."),
}


def _resolved(name: str, run_id: str, message: str) -> dict:
    severity, category, _ = ALERT_SPECS[name]
    return {
        "alert_key": f"runtime:{name}",
        "severity": severity,
        "category": category,
        "status": "resolved",
        "message": message,
        "evidence": {"run_id": run_id},
        "resolved_at": date.today().isoformat() + "T00:00:00Z",
    }


def build_runtime_alerts(
    context: dict,
    runtime_status: dict,
    integrity: dict,
    *,
    as_of: date,
    run_id: str,
) -> list[dict]:
    observations = list(context.get("observations") or [])
    sessions = list(context.get("paper_sessions") or [])
    orders = list(context.get("paper_orders") or [])
    reopen = (context.get("shadow_readiness") or {}).get("reopen_gate") or {}

    latest_observation_age = runtime_status["summary"].get(
        "latest_observation_age_days"
    )
    aged_pending = []
    for row in observations:
        if row.get("status") != "pending":
            continue
        try:
            age = (as_of - date.fromisoformat(str(row["observation_date"])[:10])).days
        except (ValueError, KeyError):
            continue
        if age > 14:
            aged_pending.append(row.get("observation_key"))

    active_sessions = [
        row for row in sessions
        if row.get("status") in {"ready", "active"}
    ]
    live_orders = [
        row.get("order_key")
        for row in orders
        if row.get("live_order") is True
    ]

    conditions = {
        "strategy_mismatch": (
            runtime_status["checks"].get("active_strategy_is_g6") is not True,
            {"active_strategy": runtime_status["summary"].get("active_strategy")},
        ),
        "missing_shadow_state": (
            runtime_status["checks"].get("shadow_readiness_present") is not True,
            {},
        ),
        "stale_shadow_data": (
            latest_observation_age is None or latest_observation_age > 5,
            {"latest_observation_age_days": latest_observation_age},
        ),
        "paper_started_early": (
            bool(active_sessions) and reopen.get("paper_trading_allowed") is not True,
            {"active_session_keys": [row.get("session_key") for row in active_sessions]},
        ),
        "live_order_detected": (
            bool(live_orders),
            {"order_keys": live_orders},
        ),
        "integrity_failure": (
            integrity.get("status") == "failed",
            {"failures": integrity.get("failures") or []},
        ),
        "aged_pending_outcomes": (
            bool(aged_pending),
            {"observation_keys": aged_pending[:20], "count": len(aged_pending)},
        ),
    }

    alerts = []
    for name, (triggered, evidence) in conditions.items():
        severity, category, message = ALERT_SPECS[name]
        if triggered:
            alerts.append({
                "alert_key": f"runtime:{name}",
                "severity": severity,
                "category": category,
                "status": "open",
                "message": message,
                "evidence": evidence | {"run_id": run_id},
                "resolved_at": None,
            })
        else:
            alerts.append(_resolved(name, run_id, f"Resolved: {message}"))
    return alerts
