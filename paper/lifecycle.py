from __future__ import annotations

from datetime import date

from config import DEFAULT_FEE_RATE, DEFAULT_LOT_SIZE, DEFAULT_SLIPPAGE_RATE


def _latest_buy_candidate(
    observations: list[dict],
    *,
    capital: float,
) -> dict | None:
    eligible = [
        row
        for row in observations
        if row.get("signal") == "buy"
        and float(row.get("lot_cost") or 0.0) <= capital
        and int(row.get("shares") or DEFAULT_LOT_SIZE) == DEFAULT_LOT_SIZE
    ]
    if not eligible:
        return None

    latest_date = max(str(row.get("observation_date") or "") for row in eligible)
    same_day = [
        row for row in eligible
        if str(row.get("observation_date") or "") == latest_date
    ]
    same_day.sort(
        key=lambda row: (-float(row.get("score") or 0.0), str(row.get("symbol") or ""))
    )
    return same_day[0]


def _find_date_index(bars, target: str) -> int | None:
    return next(
        (index for index, bar in enumerate(bars) if bar.date == target),
        None,
    )


def advance_paper_order(order: dict, batch) -> dict:
    bars = list(batch.bars)
    decision_date = str(order["decision_date"])
    decision_index = _find_date_index(bars, decision_date)
    if decision_index is None:
        return order

    payload = dict(order.get("order_payload") or {})
    capital_before = float(payload.get("capital_before") or 0.0)
    shares = int(order.get("shares") or DEFAULT_LOT_SIZE)

    if order.get("status") == "proposed":
        if decision_index + 1 >= len(bars):
            return order
        entry_bar = bars[decision_index + 1]
        fill_price = float(entry_bar.open) * (1 + DEFAULT_SLIPPAGE_RATE)
        entry_notional = fill_price * shares
        entry_fee = entry_notional * DEFAULT_FEE_RATE
        if entry_notional + entry_fee > capital_before:
            return {
                **order,
                "status": "cancelled",
                "order_payload": {
                    **payload,
                    "cancel_reason": "insufficient_paper_capital_at_fill",
                },
            }
        payload.update({
            "capital_before": capital_before,
            "entry_date": entry_bar.date,
            "entry_fee": round(entry_fee, 2),
            "cash_after_entry": round(
                capital_before - entry_notional - entry_fee,
                2,
            ),
            "source_sha256": batch.source_sha256,
        })
        return {
            **order,
            "status": "filled",
            "fill_price": round(fill_price, 6),
            "fees": round(entry_fee, 2),
            "filled_at": entry_bar.date + "T00:00:00Z",
            "order_payload": payload,
        }

    if order.get("status") == "filled":
        entry_date = str(payload.get("entry_date") or "")
        entry_index = _find_date_index(bars, entry_date)
        if entry_index is None or entry_index + 5 >= len(bars):
            return order
        exit_bar = bars[entry_index + 5]
        exit_price = float(exit_bar.close) * (1 - DEFAULT_SLIPPAGE_RATE)
        exit_notional = exit_price * shares
        exit_fee = exit_notional * DEFAULT_FEE_RATE
        cash_after_entry = float(payload["cash_after_entry"])
        capital_after = cash_after_entry + exit_notional - exit_fee
        net_pnl = capital_after - capital_before
        payload.update({
            "exit_date": exit_bar.date,
            "exit_fee": round(exit_fee, 2),
            "paper_only": True,
            "live_order": False,
        })
        return {
            **order,
            "status": "closed",
            "exit_price": round(exit_price, 6),
            "fees": round(float(order.get("fees") or 0.0) + exit_fee, 2),
            "net_pnl": round(net_pnl, 2),
            "capital_after": round(capital_after, 2),
            "closed_at": exit_bar.date + "T00:00:00Z",
            "order_payload": payload,
        }

    return order


def plan_or_advance_paper_lifecycle(
    session_result: dict,
    *,
    existing_orders: list[dict],
    observations: list[dict],
    batch=None,
) -> dict:
    session = session_result.get("session")
    if not session or session.get("status") != "active":
        return {
            "endpoint": "039",
            "status": "blocked",
            "reason": session_result.get("reason") or "paper_session_not_active",
            "order": None,
            "paper_only": True,
            "live_order": False,
        }

    open_order = next(
        (
            row
            for row in existing_orders
            if row.get("session_key") == session["session_key"]
            and row.get("status") in {"proposed", "filled"}
        ),
        None,
    )
    if open_order:
        advanced = (
            advance_paper_order(open_order, batch)
            if batch is not None
            else open_order
        )
        return {
            "endpoint": "039",
            "status": advanced.get("status"),
            "reason": None,
            "order": advanced,
            "paper_only": True,
            "live_order": False,
        }

    candidate = _latest_buy_candidate(
        observations,
        capital=float(session["current_capital"]),
    )
    if candidate is None:
        return {
            "endpoint": "039",
            "status": "no_candidate",
            "reason": "no_affordable_buy_signal",
            "order": None,
            "paper_only": True,
            "live_order": False,
        }

    order_key = (
        f"{session['session_key']}:paper:"
        f"{candidate['symbol']}:{candidate['observation_date']}"
    )
    order = {
        "order_key": order_key,
        "session_key": session["session_key"],
        "symbol": candidate["symbol"],
        "decision_date": candidate["observation_date"],
        "side": "buy",
        "shares": DEFAULT_LOT_SIZE,
        "expected_price": float(candidate["reference_close"]),
        "fill_price": None,
        "exit_price": None,
        "fees": 0.0,
        "net_pnl": None,
        "capital_after": None,
        "status": "proposed",
        "approval_required": False,
        "approved_at": None,
        "filled_at": None,
        "closed_at": None,
        "order_payload": {
            "capital_before": float(session["current_capital"]),
            "signal_score": float(candidate.get("score") or 0.0),
            "reason": candidate.get("reason"),
            "paper_only": True,
            "live_order": False,
            "auto_simulation": True,
            "exit_horizon_trading_days": 5,
        },
        "live_order": False,
    }
    return {
        "endpoint": "039",
        "status": "proposed",
        "reason": None,
        "order": order,
        "paper_only": True,
        "live_order": False,
    }
