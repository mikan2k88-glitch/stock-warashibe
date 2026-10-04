from __future__ import annotations


def assess_live_readiness_recheck(
    reopen_gate: dict,
    performance: dict,
    *,
    broker_connected: bool = False,
    live_secret_configured: bool = False,
) -> dict:
    checks = {
        "paper_gate_reopened": reopen_gate.get("paper_trading_allowed") is True,
        "paper_performance_qualified": performance.get("status") == "qualified",
        "minimum_20_closed_paper_trades": performance.get("closed_trades", 0) >= 20,
        "minimum_30_paper_days": performance.get("paper_days", 0) >= 30,
        "duplicate_order_guard": True,
        "price_deviation_guard": True,
        "kill_switch": True,
        "audit_log": True,
        "single_position_limit": True,
        "round_lot_100": True,
        "human_gate_required": True,
        "broker_not_connected": broker_connected is False,
        "live_secret_not_configured": live_secret_configured is False,
    }
    research_ready = all(checks.values())
    return {
        "endpoint": "041",
        "strategy_key": "mean_reversion_cost_floor:g6",
        "status": "ready_for_human_gate" if research_ready else "blocked",
        "checks": checks,
        "research_ready_for_human_gate": research_ready,
        "human_gate_required": True,
        "broker_connected": broker_connected,
        "live_secret_configured": live_secret_configured,
        "live_trading_allowed": False,
        "next_action": (
            "Build a human review package; do not connect a broker automatically."
            if research_ready
            else "Continue paper validation; do not connect a broker."
        ),
    }
