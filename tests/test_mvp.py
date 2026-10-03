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
    assert len(result["strategies"]) == 2
