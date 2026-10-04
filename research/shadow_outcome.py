from __future__ import annotations

from config import (
    DEFAULT_FEE_RATE,
    DEFAULT_SLIPPAGE_RATE,
    STARTING_CAPITAL,
)


SHADOW_HORIZON_TRADING_DAYS = 5


def evaluate_shadow_observation(
    observation: dict,
    batch,
    *,
    horizon_trading_days: int = SHADOW_HORIZON_TRADING_DAYS,
) -> dict:
    bars = list(batch.bars)
    observation_date = str(observation["observation_date"])
    observation_index = next(
        (index for index, bar in enumerate(bars) if bar.date == observation_date),
        None,
    )
    if observation_index is None:
        return {
            "ready": False,
            "reason": "observation_date_not_found",
            "available_future_bars": 0,
        }

    available_future = len(bars) - observation_index - 1
    if available_future < horizon_trading_days:
        return {
            "ready": False,
            "reason": "insufficient_future_bars",
            "available_future_bars": available_future,
        }

    entry_bar = bars[observation_index + 1]
    exit_bar = bars[observation_index + horizon_trading_days]
    shares = int(observation.get("shares") or 100)

    raw_entry = float(entry_bar.open)
    raw_exit = float(exit_bar.close)
    entry_execution = raw_entry * (1 + DEFAULT_SLIPPAGE_RATE)
    exit_execution = raw_exit * (1 - DEFAULT_SLIPPAGE_RATE)

    entry_notional = entry_execution * shares
    exit_notional = exit_execution * shares
    fees = (
        entry_notional * DEFAULT_FEE_RATE
        + exit_notional * DEFAULT_FEE_RATE
    )
    gross_pnl = exit_notional - entry_notional
    net_pnl = gross_pnl - fees
    executable = (
        entry_notional * (1 + DEFAULT_FEE_RATE)
        <= STARTING_CAPITAL
    )

    signal = str(observation.get("signal") or "skip")
    return {
        "ready": True,
        "status": "evaluated",
        "horizon_trading_days": horizon_trading_days,
        "signal": signal,
        "entry_date": entry_bar.date,
        "exit_date": exit_bar.date,
        "raw_entry_open": round(raw_entry, 6),
        "raw_exit_close": round(raw_exit, 6),
        "entry_execution_price": round(entry_execution, 6),
        "exit_execution_price": round(exit_execution, 6),
        "shares": shares,
        "entry_notional": round(entry_notional, 2),
        "exit_notional": round(exit_notional, 2),
        "fees": round(fees, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "return_on_starting_capital": round(net_pnl / STARTING_CAPITAL, 6),
        "executable_with_starting_capital": executable,
        "counterfactual_only": signal != "buy",
        "paper_order_created": False,
        "live_trading": False,
        "source_sha256": batch.source_sha256,
    }
