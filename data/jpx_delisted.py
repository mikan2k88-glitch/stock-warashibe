from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html.parser import HTMLParser


JPX_DELISTED_URL = "https://www.jpx.co.jp/english/listing/stocks/delisted/index.html"
JPX_DELISTED_URLS = (
    JPX_DELISTED_URL,
    "https://www.jpx.co.jp/english/listing/stocks/delisted/archives-01.html",
    "https://www.jpx.co.jp/english/listing/stocks/delisted/archives-02.html",
    "https://www.jpx.co.jp/english/listing/stocks/delisted/archives-03.html",
    "https://www.jpx.co.jp/english/listing/stocks/delisted/archives-04.html",
)


@dataclass(frozen=True)
class DelistedIssue:
    delisted_at: str
    company_name: str
    code: str
    market_segment: str
    reason: str

    @property
    def symbol(self) -> str:
        return f"{self.code}.T"

    @property
    def lifecycle_key(self) -> str:
        return f"jpx-delisted:{self.code}:{self.delisted_at}"

    def to_dict(self) -> dict:
        return asdict(self) | {
            "symbol": self.symbol,
            "lifecycle_key": self.lifecycle_key,
            "lifecycle_status": "delisted",
            "source_key": "jpx_delisted",
            "source_url": JPX_DELISTED_URL,
        }


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
            value = " ".join("".join(self.current_cell).split())
            self.current_row.append(value)
            self.in_td = False
        elif tag == "tr" and self.in_tr:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_tr = False


def _parse_date(value: str) -> str | None:
    normalized = " ".join(value.replace("\xa0", " ").split())
    for pattern in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(normalized, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def parse_delisted_html(raw: bytes, *, as_of: date | None = None) -> list[DelistedIssue]:
    parser = _TableParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    cutoff = as_of or date.today()
    issues: list[DelistedIssue] = []
    seen: set[tuple[str, str]] = set()

    for row in parser.rows:
        if len(row) < 5:
            continue
        parsed_date = _parse_date(row[0])
        code = row[2].strip()
        if parsed_date is None or not code:
            continue
        if date.fromisoformat(parsed_date) > cutoff:
            continue
        key = (code, parsed_date)
        if key in seen:
            continue
        seen.add(key)
        issues.append(
            DelistedIssue(
                delisted_at=parsed_date,
                company_name=row[1].strip(),
                code=code,
                market_segment=row[3].strip(),
                reason=row[4].strip(),
            )
        )

    issues.sort(key=lambda issue: (issue.delisted_at, issue.code), reverse=True)
    return issues


def fetch_delisted_issues(
    *,
    as_of: date | None = None,
    timeout_seconds: int = 20,
) -> tuple[list[DelistedIssue], dict]:
    request = urllib.request.Request(
        JPX_DELISTED_URL,
        headers={
            "User-Agent": "Mozilla/5.0 stock-warashibe research/0.6",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    issues = parse_delisted_html(raw, as_of=as_of)
    return issues, {
        "url": JPX_DELISTED_URL,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "record_count": len(issues),
    }



def fetch_delisted_issues_history(
    *,
    start_date: date,
    as_of: date,
    timeout_seconds: int = 20,
) -> tuple[list[DelistedIssue], list[dict]]:
    all_rows: list[DelistedIssue] = []
    sources: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for url in JPX_DELISTED_URLS:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 stock-warashibe point-in-time/0.7",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()

        rows = parse_delisted_html(raw, as_of=as_of)
        filtered = [
            row for row in rows
            if date.fromisoformat(row.delisted_at) >= start_date
        ]
        sources.append({
            "url": url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": len(filtered),
        })
        for row in filtered:
            key = (row.code, row.delisted_at)
            if key not in seen:
                seen.add(key)
                all_rows.append(row)

    all_rows.sort(key=lambda row: (row.delisted_at, row.code))
    return all_rows, sources
