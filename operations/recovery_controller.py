from __future__ import annotations


TRANSIENT_ALERT_CATEGORIES = {"data_freshness", "shadow"}
HARD_BLOCK_CATEGORIES = {"live_safety", "gate", "strategy", "evidence"}


def build_recovery_plan(
    alerts: list[dict],
    burnin: dict,
    runtime_status: dict,
    *,
    run_id: str,
) -> dict:
    open_alerts = [row for row in alerts if row.get("status") == "open"]
    triggers = []
    safe_actions = []

    for row in open_alerts:
        category = str(row.get("category") or "unknown")
        triggers.append(category)
        if category in TRANSIENT_ALERT_CATEGORIES:
            safe_actions.append({
                "action": "retry_idempotent_pipeline",
                "category": category,
                "maximum_attempts": 3,
                "delay_seconds": 20,
            })

    if runtime_status.get("status") == "degraded":
        triggers.append("runtime_degraded")

    hard_block = any(
        str(row.get("category") or "") in HARD_BLOCK_CATEGORIES
        and row.get("severity") == "critical"
        for row in open_alerts
    )
    if hard_block:
        status = "blocked"
    elif safe_actions:
        status = "retrying"
    elif burnin.get("status") == "failed":
        status = "blocked"
        triggers.append("burnin_failed")
    else:
        status = "idle"

    return {
        "endpoint": "049",
        "audit_key": f"recovery-{run_id}",
        "status": status,
        "trigger_categories": sorted(set(triggers)),
        "safe_actions": safe_actions,
        "retry_policy": {
            "maximum_attempts": 3,
            "delay_seconds": 20,
            "exponential_backoff": False,
            "idempotent_commands_only": True,
            "never_retry_live_order": True,
            "never_change_strategy": True,
            "never_connect_broker": True,
        },
        "evidence": {
            "open_alert_count": len(open_alerts),
            "burnin_status": burnin.get("status"),
            "runtime_status": runtime_status.get("status"),
        },
        "paper_trading_allowed": False,
        "live_trading_allowed": False,
        "broker_connected": False,
    }
