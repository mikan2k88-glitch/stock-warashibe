from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from data.stock_data_adapter import Bar, load_daily_csv
from data.validation import validate_daily_bars


class DailyBarProvider(Protocol):
    def load(self, symbol: str) -> list[Bar]:
        ...


@dataclass(frozen=True)
class CsvDailyBarProvider:
    path: str | Path

    def load(self, symbol: str) -> list[Bar]:
        del symbol
        bars = load_daily_csv(self.path)
        validate_daily_bars(bars)
        return bars
