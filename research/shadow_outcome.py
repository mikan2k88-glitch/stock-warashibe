from __future__ import annotations

from dataclasses import dataclass

from config import (
    DEFAULT_FEE_RATE,
    DEFAULT_SLIPPAGE_RATE,
    STARTING_CAPITAL,
)


SHADOW_HORIZON_TRADING_DAYS = 5


@dataclass(frozen=True)
class AdaptiveExitPolicy:
    max_holding_days: int = 10
    hard_stop_loss_pct: float = 0.07
    profit_target_pct: float | None = None
    trailing_activation_pct: float = 0.04
    trailing_stop_pct: float = 0.025


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


def evaluate_adaptive_exit_challenger(
    observation: dict,
    batch,
    *,
    policy: AdaptiveExitPolicy | None = None,
) -> dict:
    """Research-only adaptive exit with next-open execution.

    Each exit decision uses information available only after a daily close.
    To avoid look-ahead, a triggered decision executes at the next trading
    day's open rather than at the same close that triggered it.
    """
    policy = policy or AdaptiveExitPolicy()
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
    if available_future < 2:
        return {
            "ready": False,
            "reason": "insufficient_future_bars",
            "available_future_bars": available_future,
        }

    entry_index = observation_index + 1
    entry_bar = bars[entry_index]
    shares = int(observation.get("shares") or 100)
    raw_entry = float(entry_bar.open)
    entry_execution = raw_entry * (1 + DEFAULT_SLIPPAGE_RATE)
    entry_notional = entry_execution * shares
    executable = (
        entry_notional * (1 + DEFAULT_FEE_RATE)
        <= STARTING_CAPITAL
    )

    last_decision_index = min(
        len(bars) - 2,
        entry_index + policy.max_holding_days - 1,
    )
    peak_close = float(entry_bar.close)
    exit_index = None
    decision_date = None
    exit_reason = None
    holding_days = 0

    for index in range(entry_index, last_decision_index + 1):
        bar = bars[index]
        close = float(bar.close)
        peak_close = max(peak_close, close)
        holding_days = index - entry_index + 1

        return_from_entry = (close / raw_entry) - 1.0
        drawdown_from_peak = (close / peak_close) - 1.0
        peak_return = (peak_close / raw_entry) - 1.0

        if return_from_entry <= -policy.hard_stop_loss_pct:
            exit_index = index + 1
            decision_date = bar.date
            exit_reason = "hard_stop_loss"
            break
        if (
            policy.profit_target_pct is not None
            and return_from_entry >= policy.profit_target_pct
        ):
            exit_index = index + 1
            decision_date = bar.date
            exit_reason = "profit_target"
            break
        if (
            peak_return >= policy.trailing_activation_pct
            and drawdown_from_peak <= -policy.trailing_stop_pct
        ):
            exit_index = index + 1
            decision_date = bar.date
            exit_reason = "trailing_profit_protection"
            break
        if holding_days >= policy.max_holding_days:
            exit_index = index + 1
            decision_date = bar.date
            exit_reason = "maximum_holding_period"
            break

    if exit_index is None:
        return {
            "ready": False,
            "reason": "adaptive_exit_not_matured",
            "available_future_bars": available_future,
            "required_holding_days": policy.max_holding_days,
        }

    exit_bar = bars[exit_index]
    raw_exit = float(exit_bar.open)
    exit_execution = raw_exit * (1 - DEFAULT_SLIPPAGE_RATE)
    exit_notional = exit_execution * shares
    fees = (
        entry_notional * DEFAULT_FEE_RATE
        + exit_notional * DEFAULT_FEE_RATE
    )
    gross_pnl = exit_notional - entry_notional
    net_pnl = gross_pnl - fees
    signal = str(observation.get("signal") or "skip")

    return {
        "ready": True,
        "status": "evaluated",
        "mode": "adaptive_exit_challenger",
        "execution_policy": "daily_close_decision_next_open_execution",
        "signal": signal,
        "entry_date": entry_bar.date,
        "decision_date": decision_date,
        "exit_date": exit_bar.date,
        "exit_reason": exit_reason,
        "holding_trading_days": holding_days,
        "raw_entry_open": round(raw_entry, 6),
        "raw_exit_open": round(raw_exit, 6),
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
        "policy": {
            "max_holding_days": policy.max_holding_days,
            "hard_stop_loss_pct": policy.hard_stop_loss_pct,
            "profit_target_pct": policy.profit_target_pct,
            "trailing_activation_pct": policy.trailing_activation_pct,
            "trailing_stop_pct": policy.trailing_stop_pct,
        },
    }
