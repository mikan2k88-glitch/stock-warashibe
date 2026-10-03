from data.stock_data_adapter import Bar
from metrics.evaluator import evaluate_capital_path
from risk.policy_engine import evaluate_trade
from simulation.trading_simulator import simulate_one_trade
from strategies.momentum import MomentumStrategy
from strategies.random_strategy import RandomStrategy


def bars():
    return [
        Bar("2026-01-01", 100, 102, 99, 100, 50_000),
        Bar("2026-01-02", 101, 104, 100, 102, 55_000),
        Bar("2026-01-03", 103, 106, 102, 105, 60_000),
        Bar("2026-01-04", 106, 109, 105, 108, 70_000),
    ]


def test_policy_allows_normal_liquid_data():
    assert evaluate_trade(bars()[:3]).allowed is True


def test_momentum_trade_grows_capital():
    result = simulate_one_trade("TEST", bars(), 30_000, MomentumStrategy(), fee_rate=0.0)
    assert result is not None
    assert result.capital_after > result.capital_before


def test_random_is_reproducible():
    a = RandomStrategy(seed=7).evaluate(bars()[:3])
    b = RandomStrategy(seed=7).evaluate(bars()[:3])
    assert a == b


def test_metrics_drawdown():
    result = evaluate_capital_path([30_000, 33_000, 31_000, 35_000])
    assert result["final_capital"] == 35_000
    assert result["max_drawdown"] > 0


def test_demo_comparison_has_three_strategies():
    from backtest.demo_runner import run_demo_comparison

    result = run_demo_comparison()
    assert result["starting_capital"] == 30_000
    assert len(result["strategies"]) == 3


def test_synthetic_scenario_suite():
    from backtest.scenario_runner import run_all_scenarios

    results = run_all_scenarios()
    assert [r["scenario"] for r in results] == [
        "uptrend",
        "downtrend",
        "reversal",
        "weak_reversal",
        "moderate_reversal",
        "shallow_reversal",
        "micro_reversal",
        "thin_volume_reversal",
        "sideways",
    ]


def generation_four_baseline():
    return {
        "strategy_key": "mean_reversion_secondary_volume:g4",
        "strategy_name": "mean_reversion_secondary_volume",
        "generation": 4,
        "config": {
            "minimum_volume_ratio": 1.20,
            "deep_discount_threshold": 0.04,
            "moderate_discount_threshold": 0.03,
            "secondary_volume_ratio": 1.09,
        },
    }


def generation_five_baseline():
    return {
        "strategy_key": "mean_reversion_band_volume:g5",
        "strategy_name": "mean_reversion_band_volume",
        "generation": 5,
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


def test_generation_five_candidate_passes_quality_guard():
    from backtest.hypothesis_runner import run_hypothesis_ab_test

    result = run_hypothesis_ab_test(
        {
            "rule": "allow_shallow_discount_band_with_tertiary_volume",
            "minimum_volume_ratio": 1.20,
            "deep_discount_threshold": 0.04,
            "moderate_discount_threshold": 0.03,
            "secondary_volume_ratio": 1.09,
            "shallow_discount_threshold": 0.025,
            "shallow_discount_ceiling": 0.035,
            "tertiary_volume_ratio": 1.08,
        },
        baseline_spec=generation_four_baseline(),
    )

    assert result["observed"]["shallow_reversal_improved"] is True
    assert result["quality_guard"]["accepted"] is True
    assert result["quality_guard"]["quality_score"] >= 300
    assert result["verdict"] == "validated"


def test_micro_gain_is_rejected_by_quality_guard():
    from backtest.hypothesis_runner import run_hypothesis_ab_test

    result = run_hypothesis_ab_test(
        {
            "rule": "lower_shallow_discount_floor",
            "minimum_volume_ratio": 1.20,
            "deep_discount_threshold": 0.04,
            "moderate_discount_threshold": 0.03,
            "secondary_volume_ratio": 1.09,
            "shallow_discount_threshold": 0.02,
            "shallow_discount_ceiling": 0.035,
            "tertiary_volume_ratio": 1.08,
        },
        baseline_spec=generation_five_baseline(),
    )

    assert result["observed"]["micro_reversal_improved"] is True
    assert result["quality_guard"]["criteria_passed"] is True
    assert result["quality_guard"]["positive_gain"] < 300
    assert "material_gain_below_threshold" in result["quality_guard"]["reasons"]
    assert result["verdict"] == "rejected"


def test_thin_volume_micro_gain_is_rejected_by_quality_guard():
    from backtest.hypothesis_runner import run_hypothesis_ab_test

    result = run_hypothesis_ab_test(
        {
            "rule": "lower_tertiary_volume_ratio",
            "minimum_volume_ratio": 1.20,
            "deep_discount_threshold": 0.04,
            "moderate_discount_threshold": 0.03,
            "secondary_volume_ratio": 1.09,
            "shallow_discount_threshold": 0.025,
            "shallow_discount_ceiling": 0.035,
            "tertiary_volume_ratio": 1.075,
        },
        baseline_spec=generation_five_baseline(),
    )

    assert result["observed"]["thin_volume_reversal_improved"] is True
    assert result["quality_guard"]["criteria_passed"] is True
    assert result["quality_guard"]["positive_gain"] < 300
    assert result["verdict"] == "rejected"


def test_strategy_registry_builds_generation_five():
    from strategies.registry import build_strategy

    strategy = build_strategy(generation_five_baseline())
    assert strategy.name == "mean_reversion_band_volume"
    assert strategy.tertiary_volume_ratio == 1.08


def test_csv_provider_rejects_duplicate_dates(tmp_path):
    from data.providers import CsvDailyBarProvider
    from data.validation import DataValidationError

    path = tmp_path / "bad.csv"
    path.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-01,100,101,99,100,10000\n"
        "2026-01-02,100,101,99,100,10000\n"
        "2026-01-02,100,101,99,100,10000\n"
        "2026-01-04,100,101,99,100,10000\n"
        "2026-01-05,100,101,99,100,10000\n",
        encoding="utf-8",
    )

    try:
        CsvDailyBarProvider(path).load("TEST")
    except DataValidationError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate dates must fail closed")


def test_guarded_execution_uses_next_bar_and_round_lot():
    from backtest.readiness_gate import default_fixture_path, SYNTHETIC_CHAMPION_SPEC
    from data.providers import CsvDailyBarProvider
    from simulation.realistic_execution import simulate_guarded_next_bar_trade
    from strategies.registry import build_strategy

    bars = CsvDailyBarProvider(default_fixture_path()).load("FIXTURE")
    result = simulate_guarded_next_bar_trade(
        "FIXTURE",
        bars,
        30_000,
        build_strategy(SYNTHETIC_CHAMPION_SPEC),
    )

    assert result is not None
    assert result.decision_date == bars[2].date
    assert result.entry_date == bars[3].date
    assert result.exit_date == bars[4].date
    assert result.shares % 100 == 0
    assert result.buy_price > result.raw_entry_price
    assert result.sell_price < result.raw_exit_price


def test_real_data_readiness_gate_is_ready_without_live_data():
    from backtest.readiness_gate import run_real_data_readiness_gate

    result = run_real_data_readiness_gate()
    assert result["status"] == "ready_for_historical_backtest"
    assert result["live_trading"] is False
    assert result["real_market_data_connected"] is False
    assert all(result["checks"].values())


def test_remote_market_parser_uses_unadjusted_ohlc_and_hash():
    from datetime import date

    from data.remote_market_data import parse_market_csv

    text = (
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-01-01,100,102,99,101,100,10000\n"
        "2026-01-02,99,100,97,98,97,12000\n"
        "2026-01-03,97,99,95,96,95,13000\n"
        "2026-01-04,98,101,97,100,99,14000\n"
        "2026-01-05,101,103,100,102,101,15000\n"
    )
    batch = parse_market_csv(
        text,
        symbol="9432.T",
        source_url="https://example.test/9432.csv",
        as_of=date(2026, 1, 5),
    )
    assert batch.bars[0].close == 101
    assert batch.adjusted_close[0] == 100
    assert batch.price_mode == "unadjusted_ohlc"
    assert len(batch.source_sha256) == 64


def test_corporate_action_guard_fails_closed():
    from datetime import date

    from data.remote_market_data import CorporateActionDetected, parse_market_csv

    text = (
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-01-01,100,102,99,100,100,10000\n"
        "2026-01-02,100,102,99,100,100,10000\n"
        "2026-01-03,50,51,49,50,100,10000\n"
        "2026-01-04,51,52,50,51,102,10000\n"
        "2026-01-05,52,53,51,52,104,10000\n"
    )
    try:
        parse_market_csv(
            text,
            symbol="TEST",
            source_url="https://example.test/split.csv",
            as_of=date(2026, 1, 5),
        )
    except CorporateActionDetected:
        pass
    else:
        raise AssertionError("corporate action must fail closed")


def test_historical_runner_keeps_champion_frozen_and_oos_only():
    from data.remote_market_data import parse_market_csv
    from backtest.historical_runner import run_historical_market_backtest

    rows = ["Date,Open,High,Low,Close,Adj Close,Volume"]
    closes = [155, 153, 150, 151, 154, 152, 149, 151, 153, 150, 148, 151, 154, 152, 149, 152, 155, 153, 150, 154]
    for index, close in enumerate(closes, start=1):
        day = f"2026-01-{index:02d}"
        open_price = close + 1
        rows.append(
            f"{day},{open_price},{open_price + 2},{close - 2},{close},{close},{1000000 + index}"
        )
    batch = parse_market_csv(
        "\n".join(rows) + "\n",
        symbol="9432.T",
        source_url="https://example.test/9432.csv",
    )

    result = run_historical_market_backtest(batch=batch)
    assert result["live_trading"] is False
    assert result["summary"]["champion_strategy"] == "mean_reversion_band_volume:g5"
    assert result["split"]["in_sample_used_for_tuning"] is False
    assert result["split"]["out_of_sample_start"] > result["split"]["in_sample_end"]
    assert result["price_policy"]["lot_size"] == 100
    assert len(result["source"]["sha256"]) == 64
    assert len(result["strategies"]) == 2


def test_remote_market_parser_drops_small_number_of_incomplete_rows():
    from datetime import date

    from data.remote_market_data import parse_market_csv

    text = (
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2026-01-01,100,102,99,101,101,10000\n"
        "2026-01-02,99,100,97,98,98,12000\n"
        "2026-01-03,97,99,95,96,96,13000\n"
        "2026-01-04,98,101,97,100,100,14000\n"
        "2026-01-05,101,103,100,102,102,15000\n"
        "2026-01-06,102,104,101,103,103,16000\n"
        "2026-01-07,103,105,102,104,104,17000\n"
        "2026-01-08,104,106,103,105,105,18000\n"
        "2026-01-09,105,107,104,106,106,19000\n"
        "2026-01-10,106,108,105,107,107,20000\n"
        "2026-01-11,107,109,106,108,108,21000\n"
        "2026-01-12,108,110,107,109,109,22000\n"
        "2026-01-13,109,111,108,110,110,23000\n"
        "2026-01-14,110,112,109,111,111,24000\n"
        "2026-01-15,111,113,110,112,112,25000\n"
        "2026-01-16,112,114,111,113,113,26000\n"
        "2026-01-17,113,115,112,114,114,27000\n"
        "2026-01-18,114,116,113,115,115,28000\n"
        "2026-01-19,115,117,114,116,116,29000\n"
        "2026-01-20,116,118,115,117,117,30000\n"
        "2026-01-21,117,119,116,118,118,31000\n"
        "2026-01-22,118,120,117,119,119,32000\n"
        "2026-01-23,119,121,118,120,120,33000\n"
        "2026-01-24,120,122,119,121,121,34000\n"
        "2026-01-25,121,123,120,122,122,35000\n"
        "2026-01-26,122,124,121,123,123,36000\n"
        "2026-01-27,123,125,122,124,124,37000\n"
        "2026-01-28,124,126,123,125,125,38000\n"
        "2026-01-29,125,127,124,126,126,39000\n"
        "2026-01-30,126,128,125,127,127,40000\n"
        "2026-01-31,127,129,126,128,128,41000\n"
        "2026-02-01,128,130,127,129,129,42000\n"
        "2026-02-02,129,131,128,130,130,43000\n"
        "2026-02-03,130,132,129,131,131,44000\n"
        "2026-02-04,131,133,130,132,132,45000\n"
        "2026-02-05,132,134,131,133,133,46000\n"
        "2026-02-06,133,135,132,134,134,47000\n"
        "2026-02-07,134,136,133,135,135,48000\n"
        "2026-02-08,135,137,134,136,136,49000\n"
        "2026-02-09,136,138,135,137,137,50000\n"
        "2026-02-10,137,139,136,138,138,51000\n"
        "2026-02-11,138,140,137,139,139,52000\n"
        "2026-02-12,139,141,138,140,140,53000\n"
        "2026-02-13,140,142,139,141,141,54000\n"
        "2026-02-14,141,143,140,142,142,55000\n"
        "2026-02-15,142,144,141,143,143,56000\n"
        "2026-02-16,143,145,142,144,144,57000\n"
        "2026-02-17,144,146,143,145,145,58000\n"
        "2026-02-18,145,147,144,146,146,59000\n"
        "2026-02-19,146,148,145,147,147,60000\n"
        "2026-02-20,147,149,146,148,148,61000\n"
        "2026-02-21,,,,,,\n"
    )
    batch = parse_market_csv(
        text,
        symbol="9432.T",
        source_url="https://example.test/9432.csv",
        as_of=date(2026, 2, 21),
    )
    assert batch.dropped_incomplete_rows == 1
    assert len(batch.bars) == 51


def _fake_market_batch(symbol, closes, start_day=1):
    import hashlib

    from data.remote_market_data import MarketDataBatch
    from data.stock_data_adapter import Bar

    bars = []
    for index, close in enumerate(closes, start=start_day):
        month = 1 + (index - 1) // 28
        day = 1 + (index - 1) % 28
        date_value = f"2026-{month:02d}-{day:02d}"
        bars.append(
            Bar(
                date_value,
                close + 0.5,
                close + 1.0,
                close - 1.0,
                close,
                1_000_000 + index,
            )
        )
    digest = hashlib.sha256(symbol.encode()).hexdigest()
    return MarketDataBatch(
        symbol=symbol,
        bars=tuple(bars),
        adjusted_close=tuple(float(x) for x in closes),
        source_url=f"https://example.test/{symbol}",
        source_sha256=digest,
    )


def test_yahoo_chart_parser_handles_null_row():
    import json
    from datetime import date, datetime, timedelta, UTC

    from data.yahoo_chart_provider import parse_yahoo_chart_json

    start = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [
        int((start + timedelta(days=index)).timestamp())
        for index in range(21)
    ]
    opens = [100 + index * 0.1 for index in range(21)]
    highs = [value + 1 for value in opens]
    lows = [value - 1 for value in opens]
    closes = [value + 0.2 for value in opens]
    volumes = [10_000 + index for index in range(21)]
    adjclose = list(closes)
    for values in (opens, highs, lows, closes, volumes, adjclose):
        values[10] = None

    payload = {
        "chart": {
            "error": None,
            "result": [{
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{
                        "open": opens,
                        "high": highs,
                        "low": lows,
                        "close": closes,
                        "volume": volumes,
                    }],
                    "adjclose": [{"adjclose": adjclose}],
                },
            }],
        }
    }
    batch = parse_yahoo_chart_json(
        json.dumps(payload).encode(),
        symbol="TEST.T",
        source_url="https://example.test/chart",
        as_of=date(2026, 1, 21),
    )
    assert len(batch.bars) == 20
    assert batch.dropped_incomplete_rows == 1
    assert len(batch.source_sha256) == 64

def test_multistock_validation_filters_unaffordable_without_performance_selection():
    from datetime import date

    from backtest.multi_stock_runner import run_multi_stock_validation

    closes = [
        150, 149, 147, 148, 151, 149, 146, 148, 150, 147,
        145, 148, 151, 149, 146, 149, 152, 150, 147, 151,
        149, 146, 148, 150, 147, 145, 148, 151, 149, 146,
        149, 152, 150, 147, 151, 149, 146, 148, 150, 147,
    ]
    batches = {
        "A.T": _fake_market_batch("A.T", closes),
        "B.T": _fake_market_batch("B.T", [x + 20 for x in closes]),
        "C.T": _fake_market_batch("C.T", [x - 20 for x in closes]),
        "EXP.T": _fake_market_batch("EXP.T", [500 + (x - 150) for x in closes]),
    }

    class Provider:
        def load_batch(self, symbol, as_of=None):
            return batches[symbol]

    result = run_multi_stock_validation(
        provider=Provider(),
        symbols=("A.T", "B.T", "C.T", "EXP.T"),
        as_of=date(2026, 2, 20),
    )
    assert result["summary"]["eligible_stock_count"] == 3
    assert result["universe"]["performance_used_for_selection"] is False
    assert "EXP.T" not in result["universe"]["eligible_symbols"]
    assert any(
        row["reason"] == "unaffordable_100_share_lot"
        for row in result["universe"]["excluded"]
    )
    assert len(result["per_symbol"]) == 3
    assert len(result["strategies"]) == 2


def test_walk_forward_window_slices_are_non_overlapping_oos_steps():
    from backtest.walk_forward_runner import _window_slices

    windows = _window_slices(360)
    assert len(windows) == 4
    assert windows[0] == (0, 180, 120)
    assert windows[1] == (60, 240, 120)
    assert windows[-1] == (180, 360, 120)


def test_walk_forward_validation_reports_stability_without_tuning():
    from datetime import date

    from backtest.walk_forward_runner import run_walk_forward_validation

    closes = []
    for block in range(9):
        base = 150 + block * 2
        closes.extend([
            base + 4, base + 2, base, base + 1, base + 3,
            base + 1, base - 1, base + 1, base + 3, base,
        ])

    # 90 bars are not enough for the production window size, so repeat to 360.
    closes = (closes * 4)[:360]
    batches = {
        "A.T": _fake_market_batch("A.T", closes),
        "B.T": _fake_market_batch("B.T", [x + 20 for x in closes]),
        "C.T": _fake_market_batch("C.T", [x - 20 for x in closes]),
    }

    class Provider:
        def load_batch(self, symbol, as_of=None):
            return batches[symbol]

    result = run_walk_forward_validation(
        provider=Provider(),
        symbols=("A.T", "B.T", "C.T"),
        as_of=date(2027, 1, 1),
    )

    assert result["live_trading"] is False
    assert result["walk_forward"]["parameter_tuning"] is False
    assert result["walk_forward"]["champion_frozen"] == "mean_reversion_band_volume:g5"
    assert result["summary"]["eligible_symbol_count"] == 3
    assert result["summary"]["evaluated_window_count"] >= 9
    assert 0 <= result["summary"]["positive_window_ratio"] <= 1
    assert 0 <= result["summary"]["outperformed_benchmark_window_ratio"] <= 1
    assert result["summary"]["champion_return_stdev"] >= 0
