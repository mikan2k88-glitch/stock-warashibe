import random

from data.stock_data_adapter import Bar
from strategies.base import Signal


class RandomStrategy:
    name = "random"

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def evaluate(self, bars: list[Bar]) -> Signal:
        score = self._rng.random()
        action = "buy" if score >= 0.5 else "skip"
        return Signal(score=score, action=action, reason="seeded random baseline")
