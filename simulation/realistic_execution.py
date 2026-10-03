from __future__ import annotations

from dataclasses import asdict, dataclass

from config import DEFAULT_FEE_RATE, DEFAULT_LOT_SIZE, DEFAULT_SLIPPAGE_RATE
from data.stock_data_adapter import Bar
from data.validation import validate_daily_bars
from risk.policy_engine import evaluate_trade


@dataclass(frozen=True)
class GuardedTradeResult:
    symbol: str
    decision_date: str
    entry_date: str
    exit_date: str
    signal_bar_count: int
    raw_entry_price: float
    buy_price: float
    raw_exit_price: float
    sell_price: float
    shares: int
    lot_size: int
    fees: float
    gross_pnl: float
    net_pnl: float
    capital_before: float
    capital_after: float

    def to_dict(self) -> dict:
        return asdict(self)


def simulate_guarded_next_bar_trade(
    symbol: str,
    bars: list[Bar],
    capital: float,
    strategy,
    *,
    decision_index: int = 2,
    fee_rate: float = DEFAULT_FEE_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
    lot_size: int = DEFAULT_LOT_SIZE,
) -> GuardedTradeResult | None:
    validate_daily_bars(bars)

    if decision_index < 2:
        raise ValueError("decision_index must leave at least 3 history bars")
    entry_index = decision_index + 1
    exit_index = decision_index + 2
    if exit_index >= len(bars):
        raise ValueError("entry and exit bars must occur after the decision bar")
    if lot_size < 1:
        raise ValueError("lot_size must be positive")

    history = bars[: decision_index + 1]
    policy = evaluate_trade(history)
    if not policy.allowed:
        return None

    signal = strategy.evaluate(history)
    if signal.action != "buy":
        return None

    raw_entry_price = bars[entry_index].open
    raw_exit_price = bars[exit_index].close
    buy_price = raw_entry_price * (1 + slippage_rate)
    sell_price = raw_exit_price * (1 - slippage_rate)

    affordable_shares = int(capital // buy_price)
    shares = (affordable_shares // lot_size) * lot_size
    if shares < lot_size:
        return None

    buy_value = shares * buy_price
    sell_value = shares * sell_price
    fees = (buy_value + sell_value) * fee_rate
    gross_pnl = sell_value - buy_value
    net_pnl = gross_pnl - fees

    return GuardedTradeResult(
        symbol=symbol,
        decision_date=bars[decision_index].date,
        entry_date=bars[entry_index].date,
        exit_date=bars[exit_index].date,
        signal_bar_count=len(history),
        raw_entry_price=round(raw_entry_price, 4),
        buy_price=round(buy_price, 4),
        raw_exit_price=round(raw_exit_price, 4),
        sell_price=round(sell_price, 4),
        shares=shares,
        lot_size=lot_size,
        fees=round(fees, 2),
        gross_pnl=round(gross_pnl, 2),
        net_pnl=round(net_pnl, 2),
        capital_before=round(capital, 2),
        capital_after=round(capital + net_pnl, 2),
    )
