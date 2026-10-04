from __future__ import annotations

CURRENT_CHAMPION_SPEC = {
    "strategy_key": "mean_reversion_cost_floor:g6",
    "strategy_name": "mean_reversion_cost_floor",
    "generation": 6,
    "rule": "require_cost_coverage_on_negative_slope",
    "config": {
        "minimum_volume_ratio": 1.20,
        "deep_discount_threshold": 0.04,
        "moderate_discount_threshold": 0.03,
        "secondary_volume_ratio": 1.09,
        "shallow_discount_threshold": 0.025,
        "shallow_discount_ceiling": 0.035,
        "tertiary_volume_ratio": 1.08,
        "edge_multiple": 4.0,
    },
}

GENERATION_FIVE_SPEC = {
    "strategy_key": "mean_reversion_band_volume:g5",
    "strategy_name": "mean_reversion_band_volume",
    "generation": 5,
    "rule": "allow_shallow_discount_band_with_tertiary_volume",
    "config": {
        "minimum_volume_ratio": 1.20,
        "deep_discount_threshold": 0.04,
        "moderate_discount_threshold": 0.03,
        "secondary_volume_ratio": 1.09,
        "shallow_discount_threshold": 0.025,
        "shallow_discount_ceiling": 0.035,
        "tertiary_volume_ratio": 1.08,
    },
}
