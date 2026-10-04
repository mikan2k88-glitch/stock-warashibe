from __future__ import annotations

from config import DEFAULT_FEE_RATE


def open_position(
    *,
    capital: float,
    symbol: str,
    shares: int,
    fill_price: float,
) -> dict:
    buy_value = shares * fill_price
    fees = buy_value * DEFAULT_FEE_RATE
    required = buy_value + fees
    if required > capital:
        raise ValueError("insufficient paper capital")
    return {
        "capital_before": round(capital, 2),
        "cash_after_entry": round(capital - required, 2),
        "symbol": symbol,
        "shares": shares,
        "entry_price": round(fill_price, 4),
        "entry_fees": round(fees, 2),
        "position_open": True,
    }


def close_position(position: dict, *, exit_price: float) -> dict:
    sell_value = position["shares"] * exit_price
    exit_fees = sell_value * DEFAULT_FEE_RATE
    final_capital = position["cash_after_entry"] + sell_value - exit_fees
    pnl = final_capital - position["capital_before"]
    return {
        "endpoint": "029",
        "symbol": position["symbol"],
        "shares": position["shares"],
        "entry_price": position["entry_price"],
        "exit_price": round(exit_price, 4),
        "entry_fees": position["entry_fees"],
        "exit_fees": round(exit_fees, 2),
        "net_pnl": round(pnl, 2),
        "capital_before": position["capital_before"],
        "capital_after": round(final_capital, 2),
        "position_open": False,
        "paper_only": True,
    }
