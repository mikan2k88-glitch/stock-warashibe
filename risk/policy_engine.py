from __future__ import annotations

from dataclasses import dataclass

from config import MAX_DAILY_MOVE, MIN_VOLUME
from data.stock_data_adapter import Bar


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate_trade(bars: list[Bar]) -> PolicyDecision:
    last = bars[-1]
    prev = bars[-2]
    if last.volume < MIN_VOLUME:
        return PolicyDecision(False, "insufficient_liquidity")
    if prev.close <= 0 or last.close <= 0:
        return PolicyDecision(False, "invalid_price")
    move = abs(last.close / prev.close - 1.0)
    if move > MAX_DAILY_MOVE:
        return PolicyDecision(False, "extreme_daily_move")
    return PolicyDecision(True, "allowed")
