from __future__ import annotations

from paper.session import build_paper_session_start


def run_transition_controller(
    context: dict,
    integrity: dict,
    alerts: list[dict],
    *,
    run_id: str,
) -> dict:
    shadow = context.get("shadow_readiness") or {}
    reopen = shadow.get("reopen_gate") or {}
    active_strategy = context.get("active_strategy") or {}
    sessions = list(context.get("paper_sessions") or [])

    open_critical_alerts = [
        row
        for row in alerts
        if row.get("status") == "open"
        and row.get("severity") == "critical"
    ]

    checks = {
        "paper_gate_reopened": reopen.get("paper_trading_allowed") is True,
        "evidence_integrity_passed": integrity.get("status") == "passed",
        "no_open_critical_alerts": not open_critical_alerts,
        "active_strategy_is_g6": (
            active_strategy.get("strategy_key") == "mean_reversion_cost_floor:g6"
        ),
        "live_trading_disabled": context.get("live_trading_allowed") is False,
        "broker_not_connected": context.get("broker_connected") is False,
    }

    existing_active = next(
        (
            row
            for row in sessions
            if row.get("status") in {"ready", "active"}
        ),
        None,
    )

    if existing_active:
        status = "idempotent"
        decision = "paper_session_already_active"
        session_result = {
            "status": "idempotent_existing_session",
            "session": existing_active,
        }
    elif all(checks.values()):
        session_result = build_paper_session_start(
            reopen,
            existing_sessions=sessions,
            run_id=run_id,
            strategy_key=str(active_strategy.get("strategy_key") or ""),
        )
        status = "applied" if session_result.get("session") else "blocked"
        decision = (
            "paper_session_started"
            if status == "applied"
            else "paper_session_start_failed_closed"
        )
    else:
        session_result = {
            "status": "blocked",
            "session": None,
        }
        status = "blocked"
        if reopen.get("paper_trading_allowed") is not True:
            decision = "waiting_for_paper_gate_reopen"
        elif integrity.get("status") != "passed":
            decision = "blocked_by_evidence_integrity"
        elif open_critical_alerts:
            decision = "blocked_by_runtime_alert"
        else:
            decision = "blocked_by_transition_safety_check"

    session = session_result.get("session")
    return {
        "endpoint": "047",
        "transition_key": f"shadow-to-paper-{run_id}",
        "from_state": "shadow_validation",
        "to_state": "paper_session",
        "status": status,
        "decision": decision,
        "checks": checks,
        "action": {
            "session_key": session.get("session_key") if session else None,
            "session_created": status == "applied",
            "existing_session_reused": status == "idempotent",
            "live_trading": False,
            "broker_connected": False,
        },
        "session": session if status == "applied" else None,
        "live_trading_allowed": False,
        "broker_connected": False,
        "rationale": (
            "Paper transition is applied only after endpoint 037 reopens, "
            "evidence integrity passes, and no critical runtime alert is open."
        ),
    }
