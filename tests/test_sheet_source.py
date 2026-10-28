"""Tests for the budget-plan import sources: uploads and Google Sheets links.

All amounts are invented. No network: the Google download runs against a fake
aiohttp session.
"""

from __future__ import annotations

import base64
import io
from typing import Any

import pytest

from custom_components.finance_dashboard.sheet_source import (
    MAX_WORKBOOK_BYTES,
    SheetSourceError,
    check_workbook_bytes,
    decode_upload,
    fetch_google_sheet,
    google_export_url,
    google_sheet_id,
)

SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz_0123456789-ab"


def _workbook_bytes() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Breakdown Kosten"
    ws.append(["Position", "Alex", "Sam", "Gemeinsam"])
    ws.append(["Miete", None, None, 1200])
    ws.append(["Handy", 20, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Link parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?usp=sharing",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        f"  https://DOCS.google.com/spreadsheets/d/{SHEET_ID}/  ",
    ],
)
def test_sheet_id_from_share_links(url: str) -> None:
    assert google_sheet_id(url) == SHEET_ID


@pytest.mark.parametrize(
    "url",
    [
        "",
        f"http://docs.google.com/spreadsheets/d/{SHEET_ID}/edit",
        f"https://evil.example/spreadsheets/d/{SHEET_ID}/edit",
        f"https://docs.google.com.evil.example/spreadsheets/d/{SHEET_ID}",
        f"https://user@evil.example/spreadsheets/d/{SHEET_ID}",
        f"https://docs.google.com/document/d/{SHEET_ID}/edit",
        "https://docs.google.com/spreadsheets/d/short/edit",
        "file:///etc/passwd",
    ],
)
def test_foreign_links_are_rejected(url: str) -> None:
    with pytest.raises(SheetSourceError):
        google_sheet_id(url)


def test_export_url_is_built_not_taken_from_input() -> None:
    assert google_export_url(SHEET_ID) == (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
    )


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


def test_upload_accepts_plain_and_data_url_base64() -> None:
    data = b"PK\x03\x04rest-of-zip"
    encoded = base64.b64encode(data).decode()
    assert decode_upload(encoded) == data
    assert decode_upload(f"data:application/octet-stream;base64,{encoded}") == data


@pytest.mark.parametrize(
    "payload",
    ["", "not base64 !!", base64.b64encode(b"<html>nope</html>").decode()],
)
def test_upload_rejects_garbage(payload: str) -> None:
    with pytest.raises(SheetSourceError):
        decode_upload(payload)


def test_size_cap() -> None:
    with pytest.raises(SheetSourceError, match="5 MB"):
        check_workbook_bytes(b"PK\x03\x04" + b"0" * MAX_WORKBOOK_BYTES)
    oversized = base64.b64encode(b"PK\x03\x04" + b"0" * MAX_WORKBOOK_BYTES).decode()
    with pytest.raises(SheetSourceError, match="5 MB"):
        decode_upload(oversized)


# ---------------------------------------------------------------------------
# Google download
# ---------------------------------------------------------------------------


class _URL:
    def __init__(self, host: str) -> None:
        self.host = host


class _Content:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def iter_chunked(self, size: int):
        for i in range(0, len(self._body), size):
            yield self._body[i : i + size]


class _Response:
    def __init__(self, body: bytes, status: int, ctype: str, host: str) -> None:
        self.status = status
        self.headers = {"Content-Type": ctype}
        self.url = _URL(host)
        self.content_length = len(body)
        self.content = _Content(body)

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.requested: list[str] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.requested.append(url)
        return self.response


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def test_fetch_downloads_export_only() -> None:
    body = b"PK\x03\x04workbook"
    session = _Session(_Response(body, 200, XLSX, "doc-0g-docs.googleusercontent.com"))
    data = await fetch_google_sheet(
        session, f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"
    )
    assert data == body
    assert session.requested == [google_export_url(SHEET_ID)]


@pytest.mark.parametrize(
    ("body", "status", "ctype", "host"),
    [
        # Private sheet: Google answers with its sign-in page.
        (b"<html>login</html>", 200, "text/html; charset=utf-8", "accounts.google.com"),
        (b"<html>login</html>", 200, "text/html; charset=utf-8", "docs.google.com"),
        (b"", 403, XLSX, "docs.google.com"),
        (b"not a zip", 200, "application/octet-stream", "docs.google.com"),
    ],
)
async def test_fetch_reports_unshared_sheet(
    body: bytes, status: int, ctype: str, host: str
) -> None:
    session = _Session(_Response(body, status, ctype, host))
    with pytest.raises(SheetSourceError, match="not shared"):
        await fetch_google_sheet(
            session, f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        )


async def test_fetch_refuses_foreign_link_without_request() -> None:
    session = _Session(_Response(b"PK\x03\x04", 200, XLSX, "docs.google.com"))
    with pytest.raises(SheetSourceError):
        await fetch_google_sheet(session, "https://evil.example/x.xlsx")
    assert session.requested == []


async def test_fetch_size_cap() -> None:
    body = b"PK\x03\x04" + b"0" * MAX_WORKBOOK_BYTES
    session = _Session(_Response(body, 200, XLSX, "docs.google.com"))
    with pytest.raises(SheetSourceError, match="5 MB"):
        await fetch_google_sheet(
            session, f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        )


# ---------------------------------------------------------------------------
# Parsing from bytes
# ---------------------------------------------------------------------------


def test_parse_workbook_from_bytes() -> None:
    from custom_components.finance_dashboard.const import OWNER_SHARED
    from custom_components.finance_dashboard.spreadsheet_import import parse_workbook

    plan, report = parse_workbook(_workbook_bytes())
    owners = {p.name: p.owner for p in plan.positions}
    assert owners == {"Miete": OWNER_SHARED, "Handy": "Alex"}
    assert report.positions_imported == 2


def test_parse_workbook_rejects_corrupt_bytes() -> None:
    pytest.importorskip("openpyxl")
    from custom_components.finance_dashboard.spreadsheet_import import parse_workbook

    with pytest.raises(ValueError):
        parse_workbook(b"PK\x03\x04 truncated")
