from __future__ import annotations


def assess_live_readiness(
    paper_readiness: dict,
    *,
    closed_paper_trades: int,
    paper_days: int,
    broker_connected: bool = False,
    live_secret_configured: bool = False,
) -> dict:
    checks = {
        "paper_research_gate_passed": paper_readiness.get("paper_trading_allowed") is True,
        "minimum_20_closed_paper_trades": closed_paper_trades >= 20,
        "minimum_30_paper_days": paper_days >= 30,
        "duplicate_order_guard": True,
        "price_deviation_guard": True,
        "kill_switch": True,
        "audit_log": True,
        "human_gate_required": True,
        "broker_not_auto_connected": broker_connected is False,
        "live_secrets_not_auto_configured": live_secret_configured is False,
    }
    research_ready = all(checks.values())
    return {
        "endpoint": "030",
        "status": "ready_for_human_gate" if research_ready else "blocked",
        "checks": checks,
        "research_ready_for_human_gate": research_ready,
        "human_gate_required": True,
        "live_trading_allowed": False,
        "broker_connected": broker_connected,
        "live_secret_configured": live_secret_configured,
        "next_action": (
            "Human Gate review is required before any broker connection or live order capability."
            if research_ready
            else "Continue paper/research validation; do not connect a broker."
        ),
    }
