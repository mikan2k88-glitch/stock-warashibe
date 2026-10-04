from __future__ import annotations

import hashlib
import io
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from html.parser import HTMLParser

from openpyxl import load_workbook


JPX_LISTED_PAGE_URL = "https://www.jpx.co.jp/english/markets/statistics-equities/misc/01.html"


@dataclass(frozen=True)
class ListedIssue:
    code: str
    company_name: str
    market_segment: str
    snapshot_date: str

    @property
    def symbol(self) -> str:
        return f"{self.code}.T"

    def to_dict(self) -> dict:
        return asdict(self) | {"symbol": self.symbol}


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_data(self, data):
        self.text_parts.append(data)


def _normalize_code(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _snapshot_date_from_text(text: str) -> date:
    match = re.search(
        r"List of TSE-listed Issues\s*\(([A-Z][a-z]{2})\.\s*(\d{4})\)",
        " ".join(text.split()),
    )
    if not match:
        raise ValueError("JPX listed-issues snapshot month not found")
    month = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }[match.group(1)]
    year = int(match.group(2))
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return next_month.fromordinal(next_month.toordinal() - 1)


def parse_listed_page(raw: bytes) -> tuple[str, date]:
    parser = _PageParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    xlsx = next(
        (
            urllib.parse.urljoin(JPX_LISTED_PAGE_URL, href)
            for href in parser.links
            if href.lower().endswith(".xlsx") and "data_e" in href.lower()
        ),
        None,
    )
    if not xlsx:
        raise ValueError("JPX listed-issues Excel link not found")
    snapshot = _snapshot_date_from_text(" ".join(parser.text_parts))
    return xlsx, snapshot


def _find_header(ws) -> tuple[int, dict[str, int]]:
    for row_index in range(1, min(ws.max_row, 20) + 1):
        values = [
            str(ws.cell(row_index, col).value or "").strip()
            for col in range(1, ws.max_column + 1)
        ]
        normalized = {value.lower(): idx + 1 for idx, value in enumerate(values) if value}
        code_col = next((col for label, col in normalized.items() if label == "code"), None)
        name_col = next(
            (col for label, col in normalized.items() if "issue name" in label or label == "name"),
            None,
        )
        market_col = next(
            (col for label, col in normalized.items() if "market" in label and "product" in label),
            None,
        )
        if code_col and name_col and market_col:
            return row_index, {"code": code_col, "name": name_col, "market": market_col}
    raise ValueError("JPX listed-issues workbook header not found")


def parse_listed_workbook(raw: bytes, *, snapshot_date: date) -> list[ListedIssue]:
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    header_row, cols = _find_header(ws)
    issues: list[ListedIssue] = []
    seen: set[str] = set()

    for row in range(header_row + 1, ws.max_row + 1):
        code = _normalize_code(ws.cell(row, cols["code"]).value)
        name = str(ws.cell(row, cols["name"]).value or "").strip()
        market = str(ws.cell(row, cols["market"]).value or "").strip()
        lower = market.lower()
        if not code or not name:
            continue
        if not any(label in lower for label in ("prime", "standard", "growth")):
            continue
        if "foreign" in lower or "pro market" in lower:
            continue
        if code in seen:
            continue
        seen.add(code)
        issues.append(
            ListedIssue(
                code=code,
                company_name=name,
                market_segment=market,
                snapshot_date=snapshot_date.isoformat(),
            )
        )
    return issues


def fetch_current_listed_issues(
    *,
    timeout_seconds: int = 30,
) -> tuple[list[ListedIssue], dict]:
    req = urllib.request.Request(
        JPX_LISTED_PAGE_URL,
        headers={"User-Agent": "Mozilla/5.0 stock-warashibe point-in-time/0.7"},
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        page_raw = response.read()

    xlsx_url, snapshot_date = parse_listed_page(page_raw)
    req = urllib.request.Request(
        xlsx_url,
        headers={"User-Agent": "Mozilla/5.0 stock-warashibe point-in-time/0.7"},
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        workbook_raw = response.read()

    issues = parse_listed_workbook(workbook_raw, snapshot_date=snapshot_date)
    return issues, {
        "page_url": JPX_LISTED_PAGE_URL,
        "xlsx_url": xlsx_url,
        "snapshot_date": snapshot_date.isoformat(),
        "page_sha256": hashlib.sha256(page_raw).hexdigest(),
        "workbook_sha256": hashlib.sha256(workbook_raw).hexdigest(),
        "record_count": len(issues),
    }
