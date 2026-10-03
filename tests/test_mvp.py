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
        "sideways",
    ]


def test_generation_five_band_volume_candidate():
    from backtest.hypothesis_runner import run_hypothesis_ab_test

    baseline = {
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
        baseline_spec=baseline,
    )

    assert result["baseline_strategy"]["generation"] == 4
    assert result["observed"]["shallow_reversal_improved"] is True
    assert result["observed"]["downtrend_preserved"] is True
    assert result["observed"]["reversal_preserved"] is True
    assert result["observed"]["weak_reversal_preserved"] is True
    assert result["observed"]["moderate_reversal_preserved"] is True
    assert result["observed"]["sideways_preserved"] is True
    assert result["verdict"] == "validated"


def test_strategy_registry_builds_generation_five():
    from strategies.registry import build_strategy

    strategy = build_strategy(
        {
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
    )
    assert strategy.name == "mean_reversion_band_volume"
    assert strategy.tertiary_volume_ratio == 1.08
