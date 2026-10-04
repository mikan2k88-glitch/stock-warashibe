from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html.parser import HTMLParser


JPX_NEW_LISTING_URLS = (
    "https://www.jpx.co.jp/english/listing/stocks/new/",
    "https://www.jpx.co.jp/english/listing/stocks/new/00-archives-01.html",
    "https://www.jpx.co.jp/english/listing/stocks/new/00-archives-02.html",
    "https://www.jpx.co.jp/english/listing/stocks/new/00-archives-03.html",
    "https://www.jpx.co.jp/english/listing/stocks/new/00-archives-04.html",
)


@dataclass(frozen=True)
class NewListingIssue:
    listed_at: str
    company_name: str
    code: str
    market_segment: str
    source_url: str

    @property
    def symbol(self) -> str:
        return f"{self.code}.T"

    def to_dict(self) -> dict:
        return asdict(self) | {"symbol": self.symbol}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_tr = False
        self.in_td = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_tr = True
            self.current_row = []
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_cell = []

    def handle_data(self, data):
        if self.in_td:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            self.current_row.append(" ".join("".join(self.current_cell).split()))
            self.in_td = False
        elif tag == "tr" and self.in_tr:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_tr = False


def _parse_date(value: str) -> str | None:
    value = " ".join(value.replace("\xa0", " ").split())
    for pattern in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def parse_new_listing_html(
    raw: bytes,
    *,
    source_url: str,
    start_date: date,
    as_of: date,
) -> list[NewListingIssue]:
    parser = _TableParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    rows: list[NewListingIssue] = []
    seen: set[tuple[str, str]] = set()

    for row in parser.rows:
        if len(row) < 5:
            continue
        listed_at = _parse_date(row[0])
        if not listed_at:
            continue
        listed_date = date.fromisoformat(listed_at)
        if listed_date < start_date or listed_date > as_of:
            continue
        code = row[3].strip()
        market = row[4].strip()
        lower = market.lower()
        if not code or "pro market" in lower:
            continue
        if not any(label in lower for label in (
            "prime", "standard", "growth", "1st section", "2nd section",
            "mothers", "jasdaq"
        )):
            continue
        key = (code, listed_at)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            NewListingIssue(
                listed_at=listed_at,
                company_name=row[2].strip(),
                code=code,
                market_segment=market,
                source_url=source_url,
            )
        )
    return rows


def fetch_new_listing_history(
    *,
    start_date: date,
    as_of: date,
    timeout_seconds: int = 20,
) -> tuple[list[NewListingIssue], list[dict]]:
    all_rows: list[NewListingIssue] = []
    sources: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for url in JPX_NEW_LISTING_URLS:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 stock-warashibe point-in-time/0.7"},
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read()
        rows = parse_new_listing_html(
            raw,
            source_url=url,
            start_date=start_date,
            as_of=as_of,
        )
        sources.append({
            "url": url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": len(rows),
        })
        for row in rows:
            key = (row.code, row.listed_at)
            if key not in seen:
                seen.add(key)
                all_rows.append(row)

    all_rows.sort(key=lambda row: (row.listed_at, row.code))
    return all_rows, sources
