from data.stock_data_adapter import Bar
from strategies.base import Signal


class MomentumStrategy:
    name = "momentum"

    def evaluate(self, bars: list[Bar]) -> Signal:
        start = bars[-3].close
        end = bars[-1].close
        change = (end / start) - 1.0
        action = "buy" if change > 0 else "skip"
        return Signal(score=change, action=action, reason=f"3-bar return={change:.4f}")
