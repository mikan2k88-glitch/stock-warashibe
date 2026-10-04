from __future__ import annotations

from statistics import mean

from config import DEFAULT_FEE_RATE, DEFAULT_SLIPPAGE_RATE
from data.stock_data_adapter import Bar
from strategies.base import Signal
from strategies.mean_reversion_band_volume import MeanReversionBandVolumeStrategy


class MeanReversionCostFloorStrategy:
    name = "mean_reversion_cost_floor"

    def __init__(
        self,
        minimum_volume_ratio: float = 1.20,
        deep_discount_threshold: float = 0.04,
        moderate_discount_threshold: float = 0.03,
        secondary_volume_ratio: float = 1.09,
        shallow_discount_threshold: float = 0.025,
        shallow_discount_ceiling: float = 0.035,
        tertiary_volume_ratio: float = 1.08,
        edge_multiple: float = 2.0,
    ):
        self.edge_multiple = edge_multiple
        self.base = MeanReversionBandVolumeStrategy(
            minimum_volume_ratio=minimum_volume_ratio,
            deep_discount_threshold=deep_discount_threshold,
            moderate_discount_threshold=moderate_discount_threshold,
            secondary_volume_ratio=secondary_volume_ratio,
            shallow_discount_threshold=shallow_discount_threshold,
            shallow_discount_ceiling=shallow_discount_ceiling,
            tertiary_volume_ratio=tertiary_volume_ratio,
        )

    @property
    def minimum_cost_covered_discount(self) -> float:
        round_trip_cost = 2 * DEFAULT_FEE_RATE + 2 * DEFAULT_SLIPPAGE_RATE
        return round_trip_cost * self.edge_multiple

    def evaluate(self, bars: list[Bar]) -> Signal:
        base_signal = self.base.evaluate(bars)
        if base_signal.action != "buy":
            return base_signal

        recent = bars[-3:]
        avg = mean(bar.close for bar in recent)
        last = recent[-1].close
        slope = recent[-1].close - recent[0].close
        discount = (avg - last) / avg if avg else 0.0

        if slope < 0 and discount < self.minimum_cost_covered_discount:
            return Signal(
                score=discount,
                action="skip",
                reason=(
                    "cost_floor_blocked "
                    f"slope={slope:.4f} discount={discount:.4f} "
                    f"minimum={self.minimum_cost_covered_discount:.4f}"
                ),
            )

        return Signal(
            score=base_signal.score,
            action="buy",
            reason=(
                "cost_floor_allowed "
                f"discount={discount:.4f} "
                f"minimum={self.minimum_cost_covered_discount:.4f}"
            ),
        )
