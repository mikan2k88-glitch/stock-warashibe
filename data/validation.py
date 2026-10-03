from __future__ import annotations

from datetime import date

from data.stock_data_adapter import Bar


class DataValidationError(ValueError):
    pass


def validate_daily_bars(
    bars: list[Bar],
    *,
    as_of: date | None = None,
) -> None:
    if len(bars) < 5:
        raise DataValidationError("at least 5 daily bars are required for guarded backtest")

    parsed_dates = []
    for bar in bars:
        try:
            parsed = date.fromisoformat(bar.date)
        except ValueError as exc:
            raise DataValidationError(f"invalid ISO date: {bar.date}") from exc
        parsed_dates.append(parsed)

        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            raise DataValidationError(f"non-positive price on {bar.date}")
        if bar.volume <= 0:
            raise DataValidationError(f"non-positive volume on {bar.date}")
        if bar.high < max(bar.open, bar.close, bar.low):
            raise DataValidationError(f"invalid high on {bar.date}")
        if bar.low > min(bar.open, bar.close, bar.high):
            raise DataValidationError(f"invalid low on {bar.date}")

    if parsed_dates != sorted(parsed_dates):
        raise DataValidationError("bars must be strictly chronological")
    if len(parsed_dates) != len(set(parsed_dates)):
        raise DataValidationError("duplicate bar dates are not allowed")
    if as_of is not None and parsed_dates[-1] > as_of:
        raise DataValidationError("future bars are not allowed")
