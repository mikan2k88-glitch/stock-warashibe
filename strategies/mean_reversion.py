from statistics import mean

from data.stock_data_adapter import Bar
from strategies.base import Signal


class MeanReversionStrategy:
    name = "mean_reversion"

    def evaluate(self, bars: list[Bar]) -> Signal:
        avg = mean(bar.close for bar in bars[-3:])
        last = bars[-1].close
        discount = (avg - last) / avg
        action = "buy" if discount > 0 else "skip"
        return Signal(score=discount, action=action, reason=f"discount_to_3bar_mean={discount:.4f}")
