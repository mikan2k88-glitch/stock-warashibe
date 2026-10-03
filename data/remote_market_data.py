from __future__ import annotations

import csv
import hashlib
import io
import urllib.request
from dataclasses import dataclass
from datetime import date

from data.stock_data_adapter import Bar
from data.validation import DataValidationError, validate_daily_bars


DEFAULT_JP_SOURCE_URL = (
    "https://raw.githubusercontent.com/SeedFlora/idx-daily-data/"
    "refs/heads/main/data/9432.T.csv"
)


@dataclass(frozen=True)
class MarketDataBatch:
    symbol: str
    bars: tuple[Bar, ...]
    adjusted_close: tuple[float, ...]
    source_url: str
    source_sha256: str
    price_mode: str = "unadjusted_ohlc"


class CorporateActionDetected(DataValidationError):
    pass


def parse_market_csv(
    text: str,
    *,
    symbol: str,
    source_url: str,
    as_of: date | None = None,
) -> MarketDataBatch:
    rows = []
    adjusted = []

    reader = csv.DictReader(io.StringIO(text))
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise DataValidationError("market csv is missing required OHLCV columns")

    for row in reader:
        raw_date = str(row["Date"]).strip()
        if not raw_date:
            continue
        bar = Bar(
            date=raw_date,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(float(row["Volume"])),
        )
        rows.append(bar)
        adj_value = row.get("Adj Close")
        adjusted.append(float(adj_value) if adj_value not in (None, "") else bar.close)

    validate_daily_bars(rows, as_of=as_of)
    _guard_corporate_actions(rows, adjusted)

    return MarketDataBatch(
        symbol=symbol,
        bars=tuple(rows),
        adjusted_close=tuple(adjusted),
        source_url=source_url,
        source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _guard_corporate_actions(
    bars: list[Bar],
    adjusted_close: list[float],
) -> None:
    if len(bars) != len(adjusted_close):
        raise DataValidationError("adjusted-close length mismatch")

    for index in range(1, len(bars)):
        previous = bars[index - 1]
        current = bars[index]
        previous_adj = adjusted_close[index - 1]
        current_adj = adjusted_close[index]

        raw_move = abs(current.close / previous.close - 1.0)
        adjusted_move = abs(current_adj / previous_adj - 1.0)

        if raw_move > 0.45 and adjusted_move < 0.20:
            raise CorporateActionDetected(
                f"possible split/corporate action near {current.date}"
            )

        previous_ratio = previous_adj / previous.close
        current_ratio = current_adj / current.close
        if abs(current_ratio / previous_ratio - 1.0) > 0.20:
            raise CorporateActionDetected(
                f"abrupt adjustment-factor change near {current.date}"
            )


@dataclass(frozen=True)
class RemoteCsvDailyBarProvider:
    source_url: str = DEFAULT_JP_SOURCE_URL
    timeout_seconds: int = 20

    def load_batch(
        self,
        symbol: str,
        *,
        as_of: date | None = None,
    ) -> MarketDataBatch:
        request = urllib.request.Request(
            self.source_url,
            headers={"User-Agent": "stock-warashibe/0.3 historical-research"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            text = response.read().decode("utf-8-sig")

        return parse_market_csv(
            text,
            symbol=symbol,
            source_url=self.source_url,
            as_of=as_of,
        )

    def load(self, symbol: str) -> list[Bar]:
        return list(self.load_batch(symbol, as_of=date.today()).bars)
