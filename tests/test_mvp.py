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
        "cost_churn",
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
    assert result["summary"]["champion_strategy"] == "mean_reversion_cost_floor:g6"
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
    from datetime import date, timedelta

    from data.remote_market_data import MarketDataBatch
    from data.stock_data_adapter import Bar

    bars = []
    start_date = date(2026, 1, 1) + timedelta(days=start_day - 1)
    for offset, close in enumerate(closes):
        date_value = (start_date + timedelta(days=offset)).isoformat()
        bars.append(
            Bar(
                date_value,
                close + 0.5,
                close + 1.0,
                close - 1.0,
                close,
                1_000_000 + offset + start_day,
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
        as_of=date(2026, 2, 9),
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
    assert result["walk_forward"]["champion_frozen"] == "mean_reversion_cost_floor:g6"
    assert result["summary"]["eligible_symbol_count"] == 3
    assert result["summary"]["evaluated_window_count"] >= 9
    assert 0 <= result["summary"]["positive_window_ratio"] <= 1
    assert 0 <= result["summary"]["outperformed_benchmark_window_ratio"] <= 1
    assert result["summary"]["champion_return_stdev"] >= 0


def test_regime_classifier_uses_predeclared_thresholds():
    from backtest.strategy_diagnosis import classify_regime
    from data.stock_data_adapter import Bar

    history = [
        Bar("2026-01-01", 100, 101, 99, 100, 1000),
        Bar("2026-01-02", 102, 103, 101, 102, 1000),
        Bar("2026-01-03", 104, 105, 103, 104, 1000),
        Bar("2026-01-04", 106, 107, 105, 106, 1000),
    ]
    test = [
        Bar("2026-01-05", 106, 107, 105, 106, 1200),
        Bar("2026-01-06", 107, 108, 106, 107, 1200),
        Bar("2026-01-07", 108, 109, 107, 108, 1200),
        Bar("2026-01-08", 109, 110, 108, 109, 1200),
    ]
    regime = classify_regime(history, test)
    assert regime["trend"] == "up"
    assert regime["volatility"] == "low"
    assert regime["volume"] == "expanding"


def test_strategy_diagnosis_keeps_g5_frozen_and_produces_research_input():
    from datetime import date

    from backtest.strategy_diagnosis import run_strategy_diagnosis

    closes = []
    for block in range(9):
        base = 150 + block * 2
        closes.extend([
            base + 4, base + 2, base, base + 1, base + 3,
            base + 1, base - 1, base + 1, base + 3, base,
        ])
    closes = (closes * 4)[:360]

    batches = {
        "A.T": _fake_market_batch("A.T", closes),
        "B.T": _fake_market_batch("B.T", [x + 20 for x in closes]),
        "C.T": _fake_market_batch("C.T", [x - 20 for x in closes]),
    }

    class Provider:
        def load_batch(self, symbol, as_of=None):
            return batches[symbol]

    result = run_strategy_diagnosis(
        provider=Provider(),
        symbols=("A.T", "B.T", "C.T"),
        as_of=date(2027, 1, 1),
    )

    assert result["live_trading"] is False
    assert result["diagnosis"]["parameter_tuning"] is False
    assert result["diagnosis"]["champion_frozen"] == "mean_reversion_cost_floor:g6"
    assert result["diagnosis"]["window_count"] >= 9
    assert result["diagnosis"]["research_input"]["automatic_strategy_change"] is False
    assert "primary_hypothesis" in result["diagnosis"]["research_input"]
    assert set(result["diagnosis"]["grouped_regimes"]) == {
        "trend", "volatility", "volume"
    }
    assert len(result["strategies"]) == 2


def test_cost_floor_candidate_improves_cost_churn_and_preserves_core():
    from backtest.hypothesis_runner import run_hypothesis_ab_test

    proposed = {
        **generation_five_baseline()["config"],
        "rule": "require_cost_coverage_on_negative_slope",
        "candidate_strategy_name": "mean_reversion_cost_floor",
        "baseline_strategy_key": "mean_reversion_band_volume:g5",
        "baseline_generation": 5,
        "edge_multiple": 2.0,
        "live_trading": False,
    }
    result = run_hypothesis_ab_test(
        proposed,
        baseline_spec=generation_five_baseline(),
    )
    assert result["observed"]["cost_churn_improved"] is True
    assert result["quality_guard"]["accepted"] is True
    assert result["verdict"] == "validated"


def test_diagnosis_bridge_predeclares_three_cost_multiples():
    from research.hypothesis_bridge import build_diagnosis_bridge

    diagnosis = {
        "mode": "historical_strategy_diagnosis",
        "summary": {"diagnosed_window_count": 30},
        "diagnosis": {
            "champion_frozen": "mean_reversion_band_volume:g5",
            "parameter_tuning": False,
            "research_input": {
                "automatic_strategy_change": False,
                "loss_window_count": 20,
                "high_frequency_loss_count": 7,
                "mean_cost_drag_ratio": 0.02466,
                "primary_hypothesis": (
                    "investigate_turnover_and_entry_quality_before_new_generation"
                ),
            },
        },
    }
    items = build_diagnosis_bridge(diagnosis)
    assert [item["proposed_change"]["edge_multiple"] for item in items] == [
        2.0, 3.0, 4.0
    ]
    assert all(item["baseline_generation"] == 5 for item in items)
    assert all(item["proposed_change"]["live_trading"] is False for item in items)


def test_generation_candidate_validation_never_auto_promotes():
    from datetime import date

    from backtest.generation_candidate_validator import (
        run_generation_candidate_validation,
    )

    closes = []
    for block in range(9):
        base = 150 + block * 2
        closes.extend([
            base + 4, base + 2, base, base + 1, base + 3,
            base + 1, base - 1, base + 1, base + 3, base,
        ])
    closes = (closes * 4)[:360]
    batches = {
        "A.T": _fake_market_batch("A.T", closes),
        "B.T": _fake_market_batch("B.T", [x + 20 for x in closes]),
        "C.T": _fake_market_batch("C.T", [x - 20 for x in closes]),
    }

    class Provider:
        def load_batch(self, symbol, as_of=None):
            return batches[symbol]

    diagnosis = {
        "mode": "historical_strategy_diagnosis",
        "summary": {"diagnosed_window_count": 12},
        "diagnosis": {
            "champion_frozen": "mean_reversion_band_volume:g5",
            "parameter_tuning": False,
            "research_input": {
                "automatic_strategy_change": False,
                "loss_window_count": 8,
                "high_frequency_loss_count": 3,
                "mean_cost_drag_ratio": 0.02,
                "primary_hypothesis": (
                    "investigate_turnover_and_entry_quality_before_new_generation"
                ),
            },
        },
    }
    result = run_generation_candidate_validation(
        diagnosis,
        provider=Provider(),
        symbols=("A.T", "B.T", "C.T"),
        as_of=date(2027, 1, 1),
    )
    assert result["automatic_promotion"] is False
    assert result["proposed_generation"] == 6
    assert len(result["bridge_candidates"]) == 3
    assert len(result["historical_evaluations"]) == 3
    assert result["status"] in {"validated_candidate", "no_validated_candidate"}


def test_promotion_decision_requires_dual_gate_and_active_baseline():
    from backtest.promotion_decision import build_promotion_request

    candidate = {
        "candidate_key": "mean_reversion_cost_floor:g6-candidate-x4",
        "status": "validated_candidate",
        "selected": True,
        "baseline_strategy_key": "mean_reversion_band_volume:g5",
        "baseline_generation": 5,
        "proposed_generation": 6,
        "historical_evaluation": {"accepted": True},
        "synthetic_evaluation": {"quality_guard": {"accepted": True}},
    }
    active = {
        "strategy_key": "mean_reversion_band_volume:g5",
        "generation": 5,
    }
    request = build_promotion_request(candidate, active)
    assert request["candidate_key"] == candidate["candidate_key"]
    assert request["expected_generation"] == 6
    assert request["live_trading"] is False


def test_promotion_decision_rejects_unselected_candidate():
    import pytest

    from backtest.promotion_decision import build_promotion_request

    candidate = {
        "candidate_key": "mean_reversion_cost_floor:g6-candidate-x3",
        "status": "rejected",
        "selected": False,
        "baseline_strategy_key": "mean_reversion_band_volume:g5",
        "baseline_generation": 5,
        "proposed_generation": 6,
        "historical_evaluation": {"accepted": False},
        "synthetic_evaluation": {"quality_guard": {"accepted": False}},
    }
    active = {
        "strategy_key": "mean_reversion_band_volume:g5",
        "generation": 5,
    }
    with pytest.raises(ValueError):
        build_promotion_request(candidate, active)


def test_current_champion_is_promoted_generation_six():
    from backtest.champion_spec import CURRENT_CHAMPION_SPEC

    assert CURRENT_CHAMPION_SPEC["strategy_key"] == "mean_reversion_cost_floor:g6"
    assert CURRENT_CHAMPION_SPEC["generation"] == 6
    assert CURRENT_CHAMPION_SPEC["config"]["edge_multiple"] == 4.0


def test_g6_post_promotion_synthetic_regression_passes():
    from backtest.champion_regression import run_champion_synthetic_regression

    result = run_champion_synthetic_regression()
    assert result["status"] == "passed"
    assert result["checks"]["generation_is_six"] is True
    assert result["checks"]["core_scenarios_preserved"] is True
    assert result["checks"]["cost_churn_improved"] is True
    assert result["live_trading"] is False


def test_coverage_guard_requires_long_non_stale_history():
    from datetime import date, timedelta

    from data.coverage_guard import assess_coverage
    from data.remote_market_data import MarketDataBatch
    from data.stock_data_adapter import Bar

    start = date(2023, 1, 1)
    bars = []
    for index in range(800):
        day = start + timedelta(days=index)
        close = 100 + (index % 7) * 0.1
        bars.append(Bar(day.isoformat(), close, close + 1, close - 1, close, 10000))
    batch = MarketDataBatch(
        symbol="TEST.T",
        bars=tuple(bars),
        adjusted_close=tuple(bar.close for bar in bars),
        source_url="https://example.test/test",
        source_sha256="a" * 64,
    )
    result = assess_coverage(
        batch,
        as_of=date.fromisoformat(bars[-1].date),
    )
    assert result["accepted"] is False
    assert result["checks"]["minimum_bars"] is True
    assert result["checks"]["minimum_calendar_span"] is False


def test_robustness_gate_blocks_paper_trading_without_point_in_time_universe():
    from datetime import date, timedelta

    from backtest.robustness_runner import run_robustness_validation
    from backtest.robustness_universe import UniverseMember
    from data.remote_market_data import MarketDataBatch
    from data.stock_data_adapter import Bar

    start = date(2022, 1, 1)
    members = tuple(
        UniverseMember(f"T{index}.T", f"sector-{index % 4}")
        for index in range(8)
    )
    batches = {}
    for member_index, member in enumerate(members):
        bars = []
        for index in range(1200):
            day = start + timedelta(days=index)
            close = 120 + member_index * 2 + ((index % 20) - 10) * 0.2
            bars.append(
                Bar(
                    day.isoformat(),
                    close + 0.1,
                    close + 1,
                    close - 1,
                    close,
                    100000 + index,
                )
            )
        batches[member.symbol] = MarketDataBatch(
            symbol=member.symbol,
            bars=tuple(bars),
            adjusted_close=tuple(bar.close for bar in bars),
            source_url=f"https://example.test/{member.symbol}",
            source_sha256=(str(member_index + 1) * 64)[:64],
        )

    class Provider:
        def load_batch(self, symbol, as_of=None):
            return batches[symbol]

    as_of = date.fromisoformat(next(iter(batches.values())).bars[-1].date)
    result = run_robustness_validation(
        provider=Provider(),
        universe=members,
        as_of=as_of,
    )
    assert result["summary"]["eligible_symbol_count"] == 8
    assert result["summary"]["sector_count"] == 4
    assert result["robustness"]["parameter_tuning"] is False
    assert result["robustness"]["gate"]["hard_checks"]["point_in_time_universe_verified"] is False
    assert result["robustness"]["gate"]["paper_trading_allowed"] is False
    assert result["summary"]["gate_decision"] == "research_hold_bias_guard"


def test_point_in_time_provenance_fails_closed_without_historical_membership():
    from data.universe_provenance import assess_point_in_time_readiness

    result = assess_point_in_time_readiness(
        current_manifest_frozen=True,
        current_universe_size=20,
        delisted_records_loaded=0,
        historical_membership_snapshots_loaded=0,
        paid_source_enabled=False,
    )
    assert result["verified"] is False
    assert result["decision"] == "point_in_time_data_required"
    assert result["checks"]["paid_source_not_auto_enabled"] is True


def test_robustness_failure_diagnosis_prioritizes_bias_and_dispersion():
    from research.robustness_failure_diagnosis import diagnose_robustness_failure

    robustness = {
        "summary": {
            "champion_strategy": "mean_reversion_cost_floor:g6",
            "champion_mean_return": -0.013,
            "positive_window_ratio": 0.39,
            "outperformed_benchmark_window_ratio": 0.48,
            "champion_return_stdev": 0.21,
        },
        "robustness": {
            "gate": {
                "decision": "research_hold_bias_guard",
                "soft_score": 20,
                "soft_checks": {
                    "mean_return_not_below_minus_1pct": False,
                    "positive_window_ratio_at_least_40pct": False,
                    "benchmark_outperform_ratio_at_least_45pct": True,
                    "return_stdev_below_20pct": False,
                },
            },
            "sector_metrics": [
                {
                    "sector": "financials",
                    "mean_champion_return": -0.09,
                    "mean_excess_return": -0.08,
                    "window_count": 5,
                }
            ],
        },
    }
    provenance = {"verified": False}
    result = diagnose_robustness_failure(robustness, provenance)
    assert result["paper_trading_allowed"] is False
    assert result["automatic_strategy_change"] is False
    assert "point_in_time_universe_unverified" in result["root_causes"]
    assert "high_return_dispersion" in result["root_causes"]
    assert result["priority_actions"][0] == "reconstruct_point_in_time_universe"


def test_delisted_parser_extracts_official_style_rows():
    from datetime import date

    from data.jpx_delisted import parse_delisted_html

    raw = b"""
    <table><tbody>
      <tr><td>Oct. 1, 2026</td><td>Example Corp</td><td>1234</td><td>Standard</td><td>Acquisition</td></tr>
    </tbody></table>
    """
    rows = parse_delisted_html(raw, as_of=date(2026, 10, 4))
    assert len(rows) == 1
    assert rows[0].symbol == "1234.T"
    assert rows[0].delisted_at == "2026-10-01"


def test_paper_readiness_fails_closed_when_research_gate_is_on_hold():
    from paper.readiness import assess_paper_readiness

    retest = {
        "status": "research_hold",
        "point_in_time_verified": False,
        "robustness_gate_score": 20,
        "minimum_gate_score": 70,
    }
    result = assess_paper_readiness(
        retest,
        data_fresh=True,
        active_strategy_key="mean_reversion_cost_floor:g6",
    )
    assert result["status"] == "blocked"
    assert result["paper_trading_allowed"] is False
    assert result["live_trading_allowed"] is False


def test_paper_accounting_round_trip_updates_capital_without_live_order():
    from paper.accounting import close_position, open_position

    opened = open_position(
        capital=30000,
        symbol="9432.T",
        shares=100,
        fill_price=150.0,
    )
    closed = close_position(opened, exit_price=155.0)
    assert closed["paper_only"] is True
    assert closed["position_open"] is False
    assert closed["capital_after"] > closed["capital_before"]


def test_approval_request_uses_8888_and_never_creates_live_order():
    from paper.notifications import build_approval_request

    candidate = {
        "selected": {
            "symbol": "9432.T",
            "shares": 100,
            "close": 150.0,
            "lot_cost": 15000.0,
            "reason": "test",
        }
    }
    proposal = {
        "status": "proposed",
        "order": {"live_order": False},
    }
    request = build_approval_request(
        candidate,
        proposal,
        request_key="test-request",
        session_key="test-session",
    )
    assert request["status"] == "pending"
    assert request["approval_code_hint"] == "8888"
    assert request["payload"]["live_order"] is False


def test_live_readiness_never_enables_live_trading_automatically():
    from paper.live_readiness import assess_live_readiness

    paper = {"paper_trading_allowed": True}
    result = assess_live_readiness(
        paper,
        closed_paper_trades=20,
        paper_days=30,
        broker_connected=False,
        live_secret_configured=False,
    )
    assert result["status"] == "ready_for_human_gate"
    assert result["research_ready_for_human_gate"] is True
    assert result["human_gate_required"] is True
    assert result["live_trading_allowed"] is False


def test_listed_workbook_parser_filters_domestic_prime_standard_growth():
    import io
    from datetime import date

    from openpyxl import Workbook

    from data.jpx_listed import parse_listed_workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Code", "Issue Name", "Market/Products"])
    ws.append(["2026-08-31", 9432, "NTT", "Prime Market (Domestic Stocks)"])
    ws.append(["2026-08-31", 1305, "ETF", "ETFs"])
    ws.append(["2026-08-31", 9999, "Foreign", "Standard Market (Foreign Stocks)"])
    buf = io.BytesIO()
    wb.save(buf)

    rows = parse_listed_workbook(buf.getvalue(), snapshot_date=date(2026, 8, 31))
    assert [row.code for row in rows] == ["9432"]


def test_historical_membership_reconstruction_can_verify_complete_public_events():
    from datetime import date

    from data.jpx_delisted import DelistedIssue
    from data.jpx_listed import ListedIssue
    from data.jpx_new_listings import NewListingIssue
    from research.historical_membership import reconstruct_historical_membership

    current = [
        ListedIssue(str(1000 + i), f"Current {i}", "Prime Market (Domestic Stocks)", "2026-08-31")
        for i in range(1000)
    ]
    current.append(
        ListedIssue("2001", "New Co", "Growth Market (Domestic Stocks)", "2026-08-31")
    )
    new = [
        NewListingIssue("2022-02-01", "New Co", "2001", "Growth", "test"),
    ]
    delisted = [
        DelistedIssue("2023-03-01", "Old Co", "3001", "Standard", "test"),
    ]
    result = reconstruct_historical_membership(
        current,
        new,
        delisted,
        snapshot_date=date(2026, 8, 31),
        source_completeness_verified=True,
    )
    assert result["historical_membership_snapshot_count"] >= 48
    assert result["point_in_time"]["verified"] is True
    assert result["status"] == "verified_public_reconstruction"


def test_shadow_validation_records_research_only_observations():
    from research.shadow_validation import build_shadow_observations

    robustness = {
        "live_trading": False,
        "summary": {"champion_strategy": "mean_reversion_cost_floor:g6"},
        "per_symbol": [
            {
                "symbol": "9432.T",
                "sector": "telecom",
                "source_sha256": "a" * 64,
                "latest_snapshot": {
                    "date": "2026-10-02",
                    "close": 150.0,
                    "action": "buy",
                    "score": 0.02,
                    "reason": "test",
                },
            }
        ],
    }
    result = build_shadow_observations(robustness)
    assert result["endpoint"] == "032"
    assert result["prospective_only"] is True
    assert result["parameter_tuning"] is False
    assert result["paper_order_created"] is False
    assert result["live_trading"] is False
    assert result["observations"][0]["observation_key"] == "g6-shadow:9432.T:2026-10-02"
    assert result["observations"][0]["shares"] == 100


def test_shadow_outcome_evaluator_waits_for_five_future_bars():
    from types import SimpleNamespace

    from data.stock_data_adapter import Bar
    from research.shadow_outcome import evaluate_shadow_observation

    bars = [
        Bar(date=f"2026-10-0{day}", open=100.0, high=101.0, low=99.0, close=100.0, volume=100000)
        for day in range(1, 6)
    ]
    batch = SimpleNamespace(bars=bars, source_sha256="b" * 64)
    observation = {
        "observation_date": "2026-10-01",
        "signal": "buy",
        "shares": 100,
    }
    result = evaluate_shadow_observation(observation, batch)
    assert result["ready"] is False
    assert result["reason"] == "insufficient_future_bars"
    assert result["available_future_bars"] == 4


def test_shadow_outcome_evaluator_uses_next_open_and_fifth_future_close():
    from types import SimpleNamespace

    from data.stock_data_adapter import Bar
    from research.shadow_outcome import evaluate_shadow_observation

    bars = [
        Bar(date=f"2026-10-0{day}", open=100.0 + day, high=103.0 + day, low=99.0, close=101.0 + day, volume=100000)
        for day in range(1, 7)
    ]
    batch = SimpleNamespace(bars=bars, source_sha256="c" * 64)
    observation = {
        "observation_date": "2026-10-01",
        "signal": "buy",
        "shares": 100,
    }
    result = evaluate_shadow_observation(observation, batch)
    assert result["ready"] is True
    assert result["entry_date"] == "2026-10-02"
    assert result["exit_date"] == "2026-10-06"
    assert result["horizon_trading_days"] == 5
    assert result["counterfactual_only"] is False
    assert result["paper_order_created"] is False
    assert result["live_trading"] is False


def test_shadow_readiness_collects_until_30_days_and_20_buys():
    from research.shadow_readiness import aggregate_shadow_readiness

    observations = [
        {
            "observation_date": "2026-10-02",
            "signal": "buy",
            "status": "pending",
            "outcome": {},
        }
    ]
    result = aggregate_shadow_readiness(observations)
    assert result["endpoint"] == "034"
    assert result["status"] == "collecting"
    assert result["observation_days"] == 1
    assert result["evaluated_buy_signals"] == 0
    assert result["sufficient_evidence"] is False


def test_prospective_acceptance_passes_only_predeclared_forward_thresholds():
    from research.prospective_acceptance import assess_prospective_acceptance

    readiness = {
        "sufficient_evidence": True,
        "metrics": {
            "win_rate": 0.55,
            "mean_return_on_starting_capital": 0.01,
            "cumulative_net_pnl": 1000.0,
            "worst_return_on_starting_capital": -0.02,
            "max_drawdown_proxy_ratio": -0.05,
        },
    }
    result = assess_prospective_acceptance(readiness)
    assert result["endpoint"] == "035"
    assert result["accepted"] is True
    assert result["decision"] == "prospective_g6_accepted"
    assert result["paper_trading_allowed"] is False


def test_shadow_failure_does_not_call_insufficient_sample_a_strategy_failure():
    from research.shadow_failure_diagnosis import diagnose_shadow_failure

    readiness = {"sufficient_evidence": False}
    acceptance = {"accepted": False, "status": "collecting"}
    result = diagnose_shadow_failure(readiness, acceptance)
    assert result["endpoint"] == "036"
    assert result["classification"] == "collect_more_forward_evidence"
    assert result["g7_generation_allowed"] is False
    assert result["automatic_strategy_change"] is False


def test_paper_reopen_gate_requires_forward_acceptance_and_keeps_live_disabled():
    from paper.reopen_gate import assess_paper_reopen_gate

    readiness = {"sufficient_evidence": True}
    acceptance = {"accepted": True}
    result = assess_paper_reopen_gate(
        readiness,
        acceptance,
        point_in_time_verified=True,
        data_fresh=True,
        active_strategy_key="mean_reversion_cost_floor:g6",
    )
    assert result["endpoint"] == "037"
    assert result["status"] == "reopened"
    assert result["paper_trading_allowed"] is True
    assert result["live_trading_allowed"] is False
    assert result["human_gate_required"] is True


def test_paper_session_start_stays_blocked_until_endpoint_037_reopens():
    from paper.session import build_paper_session_start

    result = build_paper_session_start(
        {"paper_trading_allowed": False, "decision": "waiting"},
        existing_sessions=[],
        run_id="1",
        strategy_key="mean_reversion_cost_floor:g6",
    )
    assert result["endpoint"] == "038"
    assert result["status"] == "blocked"
    assert result["session"] is None
    assert result["live_trading"] is False


def test_paper_session_start_is_idempotent_when_reopened():
    from paper.session import build_paper_session_start

    existing = {
        "session_key": "paper-live-sim-old",
        "strategy_key": "mean_reversion_cost_floor:g6",
        "starting_capital": 30000,
        "current_capital": 30000,
        "status": "active",
        "readiness": {},
        "ledger": {},
        "live_trading": False,
    }
    result = build_paper_session_start(
        {"paper_trading_allowed": True},
        existing_sessions=[existing],
        run_id="2",
        strategy_key="mean_reversion_cost_floor:g6",
    )
    assert result["status"] == "idempotent_existing_session"
    assert result["session"]["session_key"] == existing["session_key"]


def test_paper_lifecycle_proposes_only_paper_order_when_session_active():
    from paper.lifecycle import plan_or_advance_paper_lifecycle

    session_result = {
        "session": {
            "session_key": "paper-test",
            "current_capital": 30000,
            "status": "active",
        }
    }
    observations = [{
        "observation_date": "2026-10-02",
        "symbol": "9432.T",
        "signal": "buy",
        "score": 0.1,
        "reference_close": 150.0,
        "lot_cost": 15000.0,
        "shares": 100,
        "reason": "test",
    }]
    result = plan_or_advance_paper_lifecycle(
        session_result,
        existing_orders=[],
        observations=observations,
    )
    assert result["endpoint"] == "039"
    assert result["status"] == "proposed"
    assert result["order"]["approval_required"] is False
    assert result["order"]["live_order"] is False
    assert result["paper_only"] is True


def test_paper_performance_requires_20_trades_and_30_days():
    from datetime import date

    from paper.performance import build_paper_performance

    session_result = {
        "session": {
            "session_key": "paper-test",
            "strategy_key": "mean_reversion_cost_floor:g6",
            "starting_capital": 30000,
            "created_at": "2026-09-01T00:00:00Z",
        }
    }
    orders = [
        {
            "session_key": "paper-test",
            "status": "closed",
            "net_pnl": 10.0,
            "capital_after": 30000 + (index + 1) * 10,
            "closed_at": f"2026-09-{(index % 20) + 1:02d}T00:00:00Z",
        }
        for index in range(20)
    ]
    result = build_paper_performance(
        session_result,
        orders=orders,
        as_of=date(2026, 10, 4),
    )
    assert result["endpoint"] == "040"
    assert result["status"] == "qualified"
    assert result["closed_trades"] == 20
    assert result["paper_days"] >= 30


def test_live_readiness_recheck_only_prepares_human_gate():
    from paper.live_readiness_recheck import assess_live_readiness_recheck

    result = assess_live_readiness_recheck(
        {"paper_trading_allowed": True},
        {"status": "qualified", "closed_trades": 20, "paper_days": 30},
    )
    assert result["endpoint"] == "041"
    assert result["status"] == "ready_for_human_gate"
    assert result["research_ready_for_human_gate"] is True
    assert result["live_trading_allowed"] is False
    assert result["broker_connected"] is False


def test_human_gate_package_never_auto_approves():
    from paper.human_gate_package import build_human_gate_package

    package = build_human_gate_package(
        {"status": "ready_for_human_gate", "research_ready_for_human_gate": True, "checks": {}},
        package_key="human-gate-test",
    )
    assert package["endpoint"] == "042"
    assert package["status"] == "ready_for_review"
    assert package["explicit_human_approval"] is False
    assert package["live_trading_allowed"] is False
    assert package["safeguards"]["approval_code_required"] == "8888"


def test_real_trial_adapter_never_sends_live_order():
    from broker.human_gated_adapter import HumanGatedRealTrialAdapter

    package = {
        "package_key": "human-gate-test",
        "strategy_key": "mean_reversion_cost_floor:g6",
        "status": "ready_for_review",
        "limits": {
            "maximum_initial_capital_yen": 30000,
            "shares_per_order": 100,
        },
    }
    adapter = HumanGatedRealTrialAdapter()
    blocked = adapter.prepare(
        package,
        explicit_human_approval=False,
        broker_connected=False,
    )
    assert blocked["endpoint"] == "043"
    assert blocked["status"] == "blocked"
    assert blocked["live_order_sent"] is False
    assert blocked["trial_payload"]["network_order_transmission_implemented"] is False

    manual = adapter.prepare(
        package,
        symbol="9432.T",
        explicit_human_approval=True,
        broker_connected=True,
    )
    assert manual["status"] == "ready_for_manual_execution"
    assert manual["live_order_sent"] is False
    assert manual["live_trading_allowed"] is False


def test_runtime_status_reports_collecting_without_false_live_progression():
    from datetime import date
    from operations.status_monitor import build_runtime_status

    context = {
        "shadow_readiness": {
            "status": "collecting",
            "observation_days": 1,
            "evaluated_buy_signals": 0,
            "reopen_gate": {
                "status": "blocked",
                "decision": "waiting",
                "paper_trading_allowed": False,
            },
        },
        "observations": [
            {"observation_date": "2026-10-02"}
        ],
        "paper_sessions": [],
        "paper_orders": [],
        "active_strategy": {
            "strategy_key": "mean_reversion_cost_floor:g6"
        },
        "latest_performance": {"status": "blocked"},
        "live_trading_allowed": False,
        "broker_connected": False,
    }
    result = build_runtime_status(
        context,
        as_of=date(2026, 10, 4),
        run_id="test",
    )
    assert result["endpoint"] == "044"
    assert result["status"] == "collecting"
    assert result["summary"]["paper_trading_allowed"] is False
    assert result["summary"]["live_trading_allowed"] is False


def test_alert_engine_opens_critical_if_paper_session_started_early():
    from datetime import date
    from operations.alert_engine import build_runtime_alerts

    context = {
        "shadow_readiness": {
            "reopen_gate": {"paper_trading_allowed": False}
        },
        "observations": [],
        "paper_sessions": [
            {"session_key": "bad", "status": "active"}
        ],
        "paper_orders": [],
    }
    runtime_status = {
        "checks": {"active_strategy_is_g6": True, "shadow_readiness_present": True},
        "summary": {"latest_observation_age_days": 0, "active_strategy": "mean_reversion_cost_floor:g6"},
    }
    integrity = {"status": "collecting", "failures": []}
    alerts = build_runtime_alerts(
        context,
        runtime_status,
        integrity,
        as_of=date(2026, 10, 4),
        run_id="test",
    )
    early = next(row for row in alerts if row["alert_key"] == "runtime:paper_started_early")
    assert early["status"] == "open"
    assert early["severity"] == "critical"


def test_evidence_integrity_collects_before_sample_minimum():
    from datetime import date
    from operations.evidence_integrity import audit_evidence_integrity

    observations = [
        {
            "observation_key": "g6-shadow:9432.T:2026-10-02",
            "observation_date": "2026-10-02",
            "symbol": "9432.T",
            "sector": "telecom",
            "signal": "buy",
            "status": "pending",
            "source_sha256": "a" * 64,
            "live_trading": False,
            "outcome": {},
        }
    ]
    result = audit_evidence_integrity(
        observations,
        as_of=date(2026, 10, 4),
        run_id="test",
    )
    assert result["endpoint"] == "046"
    assert result["status"] == "collecting"
    assert all(result["checks"].values())
    assert result["sample_ready"] is False


def test_evidence_integrity_fails_duplicate_symbol_date():
    from datetime import date
    from operations.evidence_integrity import audit_evidence_integrity

    base = {
        "observation_date": "2026-10-02",
        "symbol": "9432.T",
        "sector": "telecom",
        "signal": "skip",
        "status": "pending",
        "source_sha256": "a" * 64,
        "live_trading": False,
        "outcome": {},
    }
    observations = [
        {"observation_key": "one", **base},
        {"observation_key": "two", **base},
    ]
    result = audit_evidence_integrity(
        observations,
        as_of=date(2026, 10, 4),
        run_id="test",
    )
    assert result["status"] == "failed"
    assert result["checks"]["symbol_date_pairs_unique"] is False


def test_transition_controller_waits_until_reopen_and_integrity_pass():
    from operations.transition_controller import run_transition_controller

    context = {
        "shadow_readiness": {
            "reopen_gate": {"paper_trading_allowed": False}
        },
        "active_strategy": {
            "strategy_key": "mean_reversion_cost_floor:g6"
        },
        "paper_sessions": [],
        "live_trading_allowed": False,
        "broker_connected": False,
    }
    result = run_transition_controller(
        context,
        {"status": "collecting"},
        [],
        run_id="test",
    )
    assert result["endpoint"] == "047"
    assert result["status"] == "blocked"
    assert result["decision"] == "waiting_for_paper_gate_reopen"
    assert result["session"] is None
    assert result["live_trading_allowed"] is False


def test_transition_controller_can_start_paper_but_never_live():
    from operations.transition_controller import run_transition_controller

    context = {
        "shadow_readiness": {
            "reopen_gate": {"paper_trading_allowed": True}
        },
        "active_strategy": {
            "strategy_key": "mean_reversion_cost_floor:g6"
        },
        "paper_sessions": [],
        "live_trading_allowed": False,
        "broker_connected": False,
    }
    result = run_transition_controller(
        context,
        {"status": "passed"},
        [],
        run_id="test",
    )
    assert result["status"] == "applied"
    assert result["session"]["status"] == "active"
    assert result["session"]["live_trading"] is False
    assert result["live_trading_allowed"] is False
    assert result["broker_connected"] is False


def test_operational_burnin_collects_before_five_observation_days():
    from datetime import date
    from operations.burnin import evaluate_operational_burnin

    context = {
        "observations": [{"observation_date": "2026-10-02"}],
        "runtime_history": [{"created_at": "2026-10-02T17:20:00Z", "status": "collecting"}],
        "integrity_history": [{"created_at": "2026-10-02T17:20:00Z", "status": "collecting"}],
    }
    result = evaluate_operational_burnin(context, as_of=date(2026, 10, 5), run_id="test")
    assert result["endpoint"] == "048"
    assert result["status"] == "collecting"
    assert result["observed_business_days"] == 1
    assert result["live_trading"] is False


def test_operational_burnin_passes_five_clean_observation_days():
    from datetime import date
    from operations.burnin import evaluate_operational_burnin

    dates = ["2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07"]
    context = {
        "observations": [{"observation_date": value} for value in dates],
        "runtime_history": [{"created_at": value + "T17:20:00Z", "status": "collecting"} for value in dates],
        "integrity_history": [{"created_at": value + "T17:20:00Z", "status": "collecting"} for value in dates],
    }
    result = evaluate_operational_burnin(context, as_of=date(2026, 10, 7), run_id="test")
    assert result["status"] == "passed"
    assert all(result["checks"].values())


def test_recovery_controller_retries_only_transient_non_live_categories():
    from operations.recovery_controller import build_recovery_plan

    alerts = [{"status": "open", "severity": "warning", "category": "data_freshness"}]
    result = build_recovery_plan(alerts, {"status": "collecting"}, {"status": "collecting"}, run_id="test")
    assert result["endpoint"] == "049"
    assert result["status"] == "retrying"
    assert result["safe_actions"][0]["maximum_attempts"] == 3
    assert result["retry_policy"]["never_retry_live_order"] is True
    assert result["live_trading_allowed"] is False


def test_recovery_controller_blocks_live_safety_failure():
    from operations.recovery_controller import build_recovery_plan

    alerts = [{"status": "open", "severity": "critical", "category": "live_safety"}]
    result = build_recovery_plan(alerts, {"status": "collecting"}, {"status": "degraded"}, run_id="test")
    assert result["status"] == "blocked"
    assert result["safe_actions"] == []
    assert result["broker_connected"] is False


def test_runtime_status_route_fails_closed_when_dashboard_unavailable(monkeypatch):
    import app as app_module

    def fail():
        raise RuntimeError("down")

    monkeypatch.setattr(app_module, "fetch_runtime_dashboard", fail)
    client = app_module.app.test_client()
    response = client.get("/status/runtime")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["endpoint"] == "050"
    assert payload["live_trading_allowed"] is False
    assert payload["broker_connected"] is False
