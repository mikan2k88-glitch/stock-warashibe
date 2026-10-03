from statistics import mean

from data.stock_data_adapter import Bar
from strategies.base import Signal


class MeanReversionVolumeConfirmationStrategy:
    name = "mean_reversion_volume_confirmation"

    def __init__(self, minimum_volume_ratio: float = 1.20):
        self.minimum_volume_ratio = minimum_volume_ratio

    def evaluate(self, bars: list[Bar]) -> Signal:
        recent = bars[-3:]
        avg = mean(bar.close for bar in recent)
        last = recent[-1].close
        discount = (avg - last) / avg
        slope = recent[-1].close - recent[0].close

        if slope < 0:
            first_volume = max(recent[0].volume, 1)
            volume_ratio = recent[-1].volume / first_volume
            if volume_ratio < self.minimum_volume_ratio:
                return Signal(
                    score=discount,
                    action="skip",
                    reason=(
                        f"volume_confirmation_blocked slope={slope:.4f} "
                        f"volume_ratio={volume_ratio:.4f} discount={discount:.4f}"
                    ),
                )

        action = "buy" if discount > 0 else "skip"
        return Signal(
            score=discount,
            action=action,
            reason=f"volume_confirmation_allowed slope={slope:.4f} discount={discount:.4f}",
        )
