from __future__ import annotations

from strategies.mean_reversion import MeanReversionStrategy
from strategies.mean_reversion_adaptive_confirmation import (
    MeanReversionAdaptiveConfirmationStrategy,
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

    raise ValueError(f"unsupported registered strategy: {name}")
