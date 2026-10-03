from statistics import mean

from data.stock_data_adapter import Bar
from strategies.base import Signal


class MeanReversionBandVolumeStrategy:
    name = "mean_reversion_band_volume"

    def __init__(
        self,
        minimum_volume_ratio: float = 1.20,
        deep_discount_threshold: float = 0.04,
        moderate_discount_threshold: float = 0.03,
        secondary_volume_ratio: float = 1.09,
        shallow_discount_threshold: float = 0.025,
        shallow_discount_ceiling: float = 0.035,
        tertiary_volume_ratio: float = 1.08,
    ):
        self.minimum_volume_ratio = minimum_volume_ratio
        self.deep_discount_threshold = deep_discount_threshold
        self.moderate_discount_threshold = moderate_discount_threshold
        self.secondary_volume_ratio = secondary_volume_ratio
        self.shallow_discount_threshold = shallow_discount_threshold
        self.shallow_discount_ceiling = shallow_discount_ceiling
        self.tertiary_volume_ratio = tertiary_volume_ratio

    def evaluate(self, bars: list[Bar]) -> Signal:
        recent = bars[-3:]
        avg = mean(bar.close for bar in recent)
        last = recent[-1].close
        discount = (avg - last) / avg
        slope = recent[-1].close - recent[0].close

        if slope < 0:
            first_volume = max(recent[0].volume, 1)
            volume_ratio = recent[-1].volume / first_volume
            protected = (
                volume_ratio >= self.minimum_volume_ratio
                or discount >= self.deep_discount_threshold
                or (
                    discount >= self.moderate_discount_threshold
                    and volume_ratio >= self.secondary_volume_ratio
                )
                or (
                    self.shallow_discount_threshold
                    <= discount
                    < self.shallow_discount_ceiling
                    and volume_ratio >= self.tertiary_volume_ratio
                )
            )
            if not protected:
                return Signal(
                    score=discount,
                    action="skip",
                    reason=(
                        f"band_volume_blocked slope={slope:.4f} "
                        f"volume_ratio={volume_ratio:.4f} "
                        f"discount={discount:.4f}"
                    ),
                )

        action = "buy" if discount > 0 else "skip"
        return Signal(
            score=discount,
            action=action,
            reason=f"band_volume_allowed slope={slope:.4f} discount={discount:.4f}",
        )
