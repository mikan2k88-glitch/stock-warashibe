from __future__ import annotations

from dataclasses import asdict, dataclass

from config import DEFAULT_FEE_RATE
from data.stock_data_adapter import Bar
from risk.policy_engine import evaluate_trade


@dataclass(frozen=True)
class TradeResult:
    symbol: str
    buy_price: float
    sell_price: float
    shares: int
    gross_pnl: float
    fees: float
    net_pnl: float
    capital_before: float
    capital_after: float
    holding_days: int

    def to_dict(self) -> dict:
        return asdict(self)


def simulate_one_trade(
    symbol: str,
    bars: list[Bar],
    capital: float,
    strategy,
    fee_rate: float = DEFAULT_FEE_RATE,
) -> TradeResult | None:
    policy = evaluate_trade(bars[:3])
    if not policy.allowed:
        return None
    signal = strategy.evaluate(bars[:3])
    if signal.action != "buy":
        return None

    buy_price = bars[2].close
    sell_price = bars[-1].close
    shares = int(capital // buy_price)
    if shares < 1:
        return None

    buy_value = shares * buy_price
    sell_value = shares * sell_price
    fees = (buy_value + sell_value) * fee_rate
    gross_pnl = sell_value - buy_value
    net_pnl = gross_pnl - fees
    return TradeResult(
        symbol=symbol,
        buy_price=buy_price,
        sell_price=sell_price,
        shares=shares,
        gross_pnl=round(gross_pnl, 2),
        fees=round(fees, 2),
        net_pnl=round(net_pnl, 2),
        capital_before=round(capital, 2),
        capital_after=round(capital + net_pnl, 2),
        holding_days=max(1, len(bars) - 3),
    )
