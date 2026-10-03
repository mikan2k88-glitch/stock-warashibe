from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime

from data.remote_market_data import MarketDataBatch, _guard_corporate_actions
from data.stock_data_adapter import Bar
from data.validation import DataValidationError, validate_daily_bars


YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def _build_url(symbol: str, range_value: str = "2y") -> str:
    encoded = urllib.parse.quote(symbol, safe=".-")
    query = urllib.parse.urlencode(
        {
            "range": range_value,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    return f"{YAHOO_CHART_BASE}/{encoded}?{query}"


def parse_yahoo_chart_json(
    raw: bytes,
    *,
    symbol: str,
    source_url: str,
    as_of: date | None = None,
) -> MarketDataBatch:
    payload = json.loads(raw.decode("utf-8"))
    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        raise DataValidationError(f"yahoo chart error: {error}")

    results = chart.get("result") or []
    if not results:
        raise DataValidationError("yahoo chart returned no result")

    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    if not quotes:
        raise DataValidationError("yahoo chart returned no quote series")

    quote = quotes[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    adj_sets = indicators.get("adjclose") or []
    adjcloses = (adj_sets[0].get("adjclose") or []) if adj_sets else closes

    lengths = [len(timestamps), len(opens), len(highs), len(lows), len(closes), len(volumes)]
    if not lengths or len(set(lengths)) != 1:
        raise DataValidationError("yahoo chart arrays are misaligned")

    bars: list[Bar] = []
    adjusted: list[float] = []
    dropped = 0

    for index, timestamp in enumerate(timestamps):
        values = [opens[index], highs[index], lows[index], closes[index], volumes[index]]
        if any(value is None for value in values):
            dropped += 1
            continue

        day = datetime.fromtimestamp(int(timestamp), tz=UTC).date()
        if as_of is not None and day > as_of:
            raise DataValidationError("future bars are not allowed")

        close = float(closes[index])
        adj_value = (
            adjcloses[index]
            if index < len(adjcloses) and adjcloses[index] is not None
            else close
        )
        bars.append(
            Bar(
                date=day.isoformat(),
                open=float(opens[index]),
                high=float(highs[index]),
                low=float(lows[index]),
                close=close,
                volume=int(float(volumes[index])),
            )
        )
        adjusted.append(float(adj_value))

    total = len(timestamps)
    if total and dropped / total > 0.05:
        raise DataValidationError(f"too many incomplete yahoo rows: {dropped}/{total}")

    validate_daily_bars(bars, as_of=as_of)
    _guard_corporate_actions(bars, adjusted)

    return MarketDataBatch(
        symbol=symbol,
        bars=tuple(bars),
        adjusted_close=tuple(adjusted),
        source_url=source_url,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        dropped_incomplete_rows=dropped,
    )


@dataclass(frozen=True)
class YahooChartDailyBarProvider:
    range_value: str = "2y"
    timeout_seconds: int = 20

    def load_batch(
        self,
        symbol: str,
        *,
        as_of: date | None = None,
    ) -> MarketDataBatch:
        source_url = _build_url(symbol, self.range_value)
        request = urllib.request.Request(
            source_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 stock-warashibe historical-research/0.4"
                ),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read()

        return parse_yahoo_chart_json(
            raw,
            symbol=symbol,
            source_url=source_url,
            as_of=as_of,
        )
