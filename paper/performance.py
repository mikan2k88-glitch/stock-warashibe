from __future__ import annotations

from datetime import date
from statistics import mean


def build_paper_performance(
    session_result: dict,
    *,
    orders: list[dict],
    as_of: date,
) -> dict:
    session = session_result.get("session")
    if not session:
        return {
            "endpoint": "040",
            "status": "blocked",
            "session_key": None,
            "strategy_key": "mean_reversion_cost_floor:g6",
            "paper_days": 0,
            "closed_trades": 0,
            "metrics": {},
            "evidence": {"reason": "no_active_paper_session"},
            "live_trading": False,
        }

    relevant = [
        row for row in orders
        if row.get("session_key") == session["session_key"]
    ]
    closed = [
        row for row in relevant
        if row.get("status") == "closed"
        and row.get("net_pnl") is not None
    ]
    pnls = [float(row["net_pnl"]) for row in closed]
    wins = sum(pnl > 0 for pnl in pnls)

    created = str(session.get("created_at") or "")
    try:
        created_date = date.fromisoformat(created[:10])
        paper_days = max(0, (as_of - created_date).days + 1)
    except ValueError:
        paper_days = 0

    capital_history = [float(session.get("starting_capital") or 0.0)]
    for row in sorted(closed, key=lambda x: str(x.get("closed_at") or "")):
        if row.get("capital_after") is not None:
            capital_history.append(float(row["capital_after"]))

    peak = capital_history[0] if capital_history else 0.0
    max_drawdown = 0.0
    for value in capital_history:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value - peak) / peak)

    qualified = len(closed) >= 20 and paper_days >= 30
    return {
        "endpoint": "040",
        "status": "qualified" if qualified else "collecting",
        "session_key": session["session_key"],
        "strategy_key": session["strategy_key"],
        "paper_days": paper_days,
        "closed_trades": len(closed),
        "metrics": {
            "win_rate": round(wins / len(closed), 6) if closed else None,
            "mean_net_pnl": round(mean(pnls), 2) if pnls else None,
            "cumulative_net_pnl": round(sum(pnls), 2),
            "ending_capital": round(
                capital_history[-1] if capital_history else 0.0,
                2,
            ),
            "max_drawdown": round(max_drawdown, 6),
        },
        "evidence": {
            "minimum_20_closed_trades": len(closed) >= 20,
            "minimum_30_paper_days": paper_days >= 30,
            "open_orders": sum(
                row.get("status") in {"proposed", "filled"}
                for row in relevant
            ),
            "paper_only": True,
        },
        "live_trading": False,
    }
