from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from data.stock_data_adapter import Bar


@dataclass(frozen=True)
class Signal:
    score: float
    action: str
    reason: str


class Strategy(Protocol):
    name: str

    def evaluate(self, bars: list[Bar]) -> Signal: ...
