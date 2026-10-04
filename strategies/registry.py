from __future__ import annotations

from strategies.mean_reversion import MeanReversionStrategy
from strategies.mean_reversion_adaptive_confirmation import (
    MeanReversionAdaptiveConfirmationStrategy,
)
from strategies.mean_reversion_band_volume import MeanReversionBandVolumeStrategy
from strategies.mean_reversion_cost_floor import MeanReversionCostFloorStrategy
from strategies.mean_reversion_secondary_volume import (
    MeanReversionSecondaryVolumeStrategy,
)
from strategies.mean_reversion_volume_confirmation import (
    MeanReversionVolumeConfirmationStrategy,
)


def build_strategy(spec: dict | None = None):
    if not spec:
        return MeanReversionStrategy()

    name = str(spec.get("strategy_name") or "mean_reversion")
    config = spec.get("config") or {}

    if name == "mean_reversion":
        return MeanReversionStrategy()

    if name == "mean_reversion_volume_confirmation":
        return MeanReversionVolumeConfirmationStrategy(
            minimum_volume_ratio=float(config.get("minimum_volume_ratio", 1.20))
        )

    if name == "mean_reversion_adaptive_confirmation":
        return MeanReversionAdaptiveConfirmationStrategy(
            minimum_volume_ratio=float(config.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(config.get("deep_discount_threshold", 0.04)),
        )

    if name == "mean_reversion_secondary_volume":
        return MeanReversionSecondaryVolumeStrategy(
            minimum_volume_ratio=float(config.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(config.get("deep_discount_threshold", 0.04)),
            moderate_discount_threshold=float(
                config.get("moderate_discount_threshold", 0.03)
            ),
            secondary_volume_ratio=float(config.get("secondary_volume_ratio", 1.09)),
        )

    if name == "mean_reversion_cost_floor":
        return MeanReversionCostFloorStrategy(
            minimum_volume_ratio=float(config.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(config.get("deep_discount_threshold", 0.04)),
            moderate_discount_threshold=float(
                config.get("moderate_discount_threshold", 0.03)
            ),
            secondary_volume_ratio=float(config.get("secondary_volume_ratio", 1.09)),
            shallow_discount_threshold=float(
                config.get("shallow_discount_threshold", 0.025)
            ),
            shallow_discount_ceiling=float(
                config.get("shallow_discount_ceiling", 0.035)
            ),
            tertiary_volume_ratio=float(config.get("tertiary_volume_ratio", 1.08)),
            edge_multiple=float(config.get("edge_multiple", 2.0)),
        )

    if name == "mean_reversion_band_volume":
        return MeanReversionBandVolumeStrategy(
            minimum_volume_ratio=float(config.get("minimum_volume_ratio", 1.20)),
            deep_discount_threshold=float(config.get("deep_discount_threshold", 0.04)),
            moderate_discount_threshold=float(
                config.get("moderate_discount_threshold", 0.03)
            ),
            secondary_volume_ratio=float(config.get("secondary_volume_ratio", 1.09)),
            shallow_discount_threshold=float(
                config.get("shallow_discount_threshold", 0.025)
            ),
            shallow_discount_ceiling=float(
                config.get("shallow_discount_ceiling", 0.035)
            ),
            tertiary_volume_ratio=float(config.get("tertiary_volume_ratio", 1.08)),
        )

    raise ValueError(f"unsupported registered strategy: {name}")
