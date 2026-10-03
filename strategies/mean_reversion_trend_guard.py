from statistics import mean

from data.stock_data_adapter import Bar
from strategies.base import Signal


class MeanReversionTrendGuardStrategy:
    name = "mean_reversion_trend_guard"

    def evaluate(self, bars: list[Bar]) -> Signal:
        recent = bars[-3:]
        avg = mean(bar.close for bar in recent)
        last = recent[-1].close
        discount = (avg - last) / avg

        slope = recent[-1].close - recent[0].close
        if slope < 0:
            return Signal(
                score=discount,
                action="skip",
                reason=f"trend_guard_blocked slope={slope:.4f} discount={discount:.4f}",
            )

        action = "buy" if discount > 0 else "skip"
        return Signal(
            score=discount,
            action=action,
            reason=f"trend_guard_allowed slope={slope:.4f} discount={discount:.4f}",
        )
