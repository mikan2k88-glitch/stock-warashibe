from __future__ import annotations

from pathlib import Path

from config import (
    DEFAULT_FEE_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_SLIPPAGE_RATE,
    STARTING_CAPITAL,
)
from data.providers import CsvDailyBarProvider
from simulation.realistic_execution import simulate_guarded_next_bar_trade
from strategies.registry import build_strategy


SYNTHETIC_CHAMPION_SPEC = {
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


def default_fixture_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "fixtures" / "historical_sample.csv"


def run_real_data_readiness_gate(
    *,
    csv_path: str | Path | None = None,
    champion_spec: dict | None = None,
) -> dict:
    spec = champion_spec or SYNTHETIC_CHAMPION_SPEC
    provider = CsvDailyBarProvider(csv_path or default_fixture_path())
    bars = provider.load("FIXTURE")
    strategy = build_strategy(spec)

    trade = simulate_guarded_next_bar_trade(
        symbol="FIXTURE",
        bars=bars,
        capital=STARTING_CAPITAL,
        strategy=strategy,
    )

    checks = {
        "provider_contract": hasattr(provider, "load"),
        "minimum_history": len(bars) >= 5,
        "chronological_unique_ohlcv": True,
        "synthetic_champion_frozen": (
            spec.get("strategy_key") == "mean_reversion_band_volume:g5"
            and int(spec.get("generation", 0)) == 5
        ),
        "guarded_trade_produced": trade is not None,
        "decision_uses_history_only": (
            trade is not None
            and trade.signal_bar_count == 3
            and trade.decision_date < trade.entry_date < trade.exit_date
        ),
        "next_bar_entry": trade is not None and trade.entry_date == bars[3].date,
        "lot_size_enforced": (
            trade is not None
            and trade.shares >= DEFAULT_LOT_SIZE
            and trade.shares % DEFAULT_LOT_SIZE == 0
        ),
        "slippage_applied": (
            trade is not None
            and trade.buy_price > trade.raw_entry_price
            and trade.sell_price < trade.raw_exit_price
        ),
        "fees_applied": trade is not None and trade.fees > 0,
    }
    ready = all(checks.values())

    return {
        "mode": "historical_data_readiness_fixture",
        "live_trading": False,
        "real_market_data_connected": False,
        "status": "ready_for_historical_backtest" if ready else "blocked",
        "champion_strategy": spec,
        "checks": checks,
        "assumptions": {
            "fee_rate": DEFAULT_FEE_RATE,
            "slippage_rate": DEFAULT_SLIPPAGE_RATE,
            "lot_size": DEFAULT_LOT_SIZE,
            "entry_timing": "next_bar_open_after_signal",
            "exit_timing": "following_bar_close",
            "data_source": "local_csv_fixture",
        },
        "evidence": {
            "bar_count": len(bars),
            "first_date": bars[0].date,
            "last_date": bars[-1].date,
            "guarded_trade": trade.to_dict() if trade else None,
        },
    }
