from __future__ import annotations

from dataclasses import asdict
from datetime import date

from backtest.readiness_gate import SYNTHETIC_CHAMPION_SPEC
from config import (
    DEFAULT_FEE_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_SLIPPAGE_RATE,
    STARTING_CAPITAL,
)
from data.remote_market_data import MarketDataBatch, RemoteCsvDailyBarProvider
from metrics.evaluator import evaluate_capital_path
from simulation.realistic_execution import simulate_guarded_next_bar_trade
from strategies.registry import build_strategy


DEFAULT_SYMBOL = "9432.T"
IN_SAMPLE_RATIO = 0.70


def _strategy_walk_forward(
    batch: MarketDataBatch,
    *,
    split_index: int,
    champion_spec: dict,
) -> dict:
    bars = list(batch.bars)
    strategy = build_strategy(champion_spec)
    capital = float(STARTING_CAPITAL)
    capital_path = [capital]
    trades = []

    decision_index = max(2, split_index)
    while decision_index + 2 < len(bars):
        trade = simulate_guarded_next_bar_trade(
            symbol=batch.symbol,
            bars=bars,
            capital=capital,
            strategy=strategy,
            decision_index=decision_index,
        )
        if trade is None:
            decision_index += 1
            continue

        trades.append(trade.to_dict())
        capital = trade.capital_after
        capital_path.append(capital)
        decision_index += 2

    metrics = evaluate_capital_path(capital_path)
    wins = sum(1 for trade in trades if trade["net_pnl"] > 0)
    metrics.update(
        {
            "trade_count": len(trades),
            "win_rate": round(wins / len(trades), 6) if trades else 0.0,
        }
    )
    return {
        "strategy": champion_spec["strategy_key"],
        "traded": bool(trades),
        "metrics": metrics,
        "trade": trades[0] if trades else None,
        "trades": trades,
    }


def _buy_hold_benchmark(
    batch: MarketDataBatch,
    *,
    split_index: int,
) -> dict:
    bars = list(batch.bars)
    entry_index = min(split_index + 1, len(bars) - 1)
    raw_entry = bars[entry_index].open
    raw_exit = bars[-1].close
    buy_price = raw_entry * (1 + DEFAULT_SLIPPAGE_RATE)
    sell_price = raw_exit * (1 - DEFAULT_SLIPPAGE_RATE)

    affordable = int(STARTING_CAPITAL // buy_price)
    shares = (affordable // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE

    if shares < DEFAULT_LOT_SIZE:
        metrics = evaluate_capital_path([STARTING_CAPITAL, STARTING_CAPITAL])
        metrics.update({"trade_count": 0, "win_rate": 0.0})
        return {
            "strategy": "buy_hold_100_lot_benchmark",
            "traded": False,
            "metrics": metrics,
            "trade": None,
            "trades": [],
        }

    buy_value = shares * buy_price
    sell_value = shares * sell_price
    fees = (buy_value + sell_value) * DEFAULT_FEE_RATE
    gross_pnl = sell_value - buy_value
    net_pnl = gross_pnl - fees
    capital_after = round(STARTING_CAPITAL + net_pnl, 2)

    trade = {
        "symbol": batch.symbol,
        "decision_date": bars[split_index].date,
        "entry_date": bars[entry_index].date,
        "exit_date": bars[-1].date,
        "raw_entry_price": round(raw_entry, 4),
        "buy_price": round(buy_price, 4),
        "raw_exit_price": round(raw_exit, 4),
        "sell_price": round(sell_price, 4),
        "shares": shares,
        "lot_size": DEFAULT_LOT_SIZE,
        "fees": round(fees, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "capital_before": STARTING_CAPITAL,
        "capital_after": capital_after,
    }
    metrics = evaluate_capital_path([STARTING_CAPITAL, capital_after])
    metrics.update(
        {
            "trade_count": 1,
            "win_rate": 1.0 if net_pnl > 0 else 0.0,
        }
    )
    return {
        "strategy": "buy_hold_100_lot_benchmark",
        "traded": True,
        "metrics": metrics,
        "trade": trade,
        "trades": [trade],
    }


def run_historical_market_backtest(
    batch: MarketDataBatch | None = None,
    *,
    champion_spec: dict | None = None,
    as_of: date | None = None,
) -> dict:
    spec = champion_spec or SYNTHETIC_CHAMPION_SPEC
    market_batch = batch or RemoteCsvDailyBarProvider().load_batch(
        DEFAULT_SYMBOL,
        as_of=as_of or date.today(),
    )
    bars = list(market_batch.bars)

    split_index = max(3, int(len(bars) * IN_SAMPLE_RATIO))
    if split_index + 2 >= len(bars):
        raise ValueError("historical dataset is too short for out-of-sample backtest")

    champion = _strategy_walk_forward(
        market_batch,
        split_index=split_index,
        champion_spec=spec,
    )
    benchmark = _buy_hold_benchmark(
        market_batch,
        split_index=split_index,
    )

    return {
        "mode": "historical_market_data_backtest",
        "data_source": "public_daily_snapshot_yahoo_via_seedflora",
        "starting_capital": STARTING_CAPITAL,
        "live_trading": False,
        "symbol": market_batch.symbol,
        "price_policy": {
            "execution_prices": "unadjusted_ohlc",
            "adjusted_close_use": "corporate_action_detection_only",
            "fee_rate": DEFAULT_FEE_RATE,
            "slippage_rate": DEFAULT_SLIPPAGE_RATE,
            "lot_size": DEFAULT_LOT_SIZE,
        },
        "split": {
            "method": "chronological_70_30",
            "in_sample_ratio": IN_SAMPLE_RATIO,
            "in_sample_start": bars[0].date,
            "in_sample_end": bars[split_index - 1].date,
            "out_of_sample_start": bars[split_index].date,
            "out_of_sample_end": bars[-1].date,
            "in_sample_used_for_tuning": False,
        },
        "source": {
            "url": market_batch.source_url,
            "sha256": market_batch.source_sha256,
            "bar_count": len(bars),
            "first_date": bars[0].date,
            "last_date": bars[-1].date,
            "dropped_incomplete_rows": market_batch.dropped_incomplete_rows,
        },
        "summary": {
            "champion_strategy": spec["strategy_key"],
            "champion_final_capital": champion["metrics"]["final_capital"],
            "benchmark_final_capital": benchmark["metrics"]["final_capital"],
            "strategy_count": 2,
            "not_live_trading": True,
            "not_investment_advice": True,
        },
        "strategies": [champion, benchmark],
    }
