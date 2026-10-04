from backtest.historical_gate import assess_historical_gate


def _validation(*, point_in_time: bool = False, survivor_safe: bool = False) -> dict:
    symbols = ["A.T", "B.T", "C.T"]
    return {
        "mode": "historical_walk_forward_validation",
        "live_trading": False,
        "walk_forward": {
            "parameter_tuning": False,
            "champion_frozen": "mean_reversion_cost_floor:g6",
            "eligible_symbols": symbols,
            "point_in_time_universe": point_in_time,
            "survivor_bias_eliminated": survivor_safe,
        },
        "source": {
            "per_symbol_sha256": {
                symbol: str(index + 1) * 64
                for index, symbol in enumerate(symbols)
            }
        },
        "summary": {
            "champion_strategy": "mean_reversion_cost_floor:g6",
            "eligible_symbol_count": 3,
            "evaluated_window_count": 12,
            "positive_window_ratio": 0.58,
            "outperformed_benchmark_window_ratio": 0.51,
            "champion_mean_return": 0.012,
            "benchmark_mean_return": 0.009,
        },
    }


def test_endpoint_051_uses_historical_evidence_without_opening_paper_gate():
    result = assess_historical_gate(_validation())

    assert result["endpoint"] == "051"
    assert result["status"] == "research_usable_not_promotion_ready"
    assert result["historical_research_usable"] is True
    assert result["historical_gate_passed"] is False
    assert result["safety"]["paper_gate_reopened"] is False
    assert result["safety"]["paper_trading_allowed_by_endpoint_051"] is False
    assert result["safety"]["live_trading_allowed"] is False
    assert result["safety"]["automatic_strategy_change"] is False


def test_endpoint_051_can_pass_historical_gate_but_still_cannot_open_paper():
    result = assess_historical_gate(
        _validation(point_in_time=True, survivor_safe=True)
    )

    assert result["status"] == "passed"
    assert result["historical_gate_passed"] is True
    assert result["next_requirement"] == "prospective_shadow_gate_037"
    assert result["safety"]["paper_gate_reopened"] is False
    assert result["safety"]["broker_connection_allowed"] is False


def test_endpoint_051_blocks_low_quality_historical_evidence():
    validation = _validation()
    validation["summary"]["evaluated_window_count"] = 4

    result = assess_historical_gate(validation)

    assert result["status"] == "blocked"
    assert result["historical_research_usable"] is False
    assert result["evidence_checks"]["minimum_evaluated_windows"] is False
    assert result["next_requirement"] == "repair_historical_evidence_quality"
