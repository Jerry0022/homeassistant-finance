"""Workbook sources for the budget-plan import: uploads and Google Sheets links.

Both paths end in raw ``.xlsx`` bytes that :func:`spreadsheet_import.parse_workbook`
parses in memory. Nothing is written to disk.

SECURITY: the Google Sheets path is the only external call besides Enable
Banking and the opt-in AI categorisation. It is user-triggered, sends nothing
but the sheet id the user pasted, and never fetches the pasted URL itself: only
the spreadsheet id is taken from it and the export URL is built here, against a
fixed host. So a pasted link cannot point the integration at another host
(no SSRF), and redirects away from Google are refused.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
from typing import Any
from urllib.parse import urlsplit

MAX_WORKBOOK_BYTES = 5 * 1024 * 1024
GOOGLE_FETCH_TIMEOUT_SECONDS = 20

_GOOGLE_HOST = "docs.google.com"
_SHEET_PATH = re.compile(r"^/spreadsheets/d/([A-Za-z0-9_-]{20,})(?:/|$)")
# Every .xlsx is a zip archive.
_ZIP_MAGIC = b"PK\x03\x04"


class SheetSourceError(ValueError):
    """A workbook source was rejected; the message is safe to show the user."""


def google_sheet_id(url: str) -> str:
    """Extract the spreadsheet id from a Google Sheets link.

    Only ``https://docs.google.com/spreadsheets/d/<id>/...`` is accepted.
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or (parts.hostname or "").lower() != _GOOGLE_HOST:
        raise SheetSourceError("Only Google Sheets links (docs.google.com) are supported")
    match = _SHEET_PATH.match(parts.path)
    if not match:
        raise SheetSourceError("The link does not point to a Google spreadsheet")
    return match.group(1)


def google_export_url(sheet_id: str) -> str:
    """The xlsx export URL for a spreadsheet id."""
    return f"https://{_GOOGLE_HOST}/spreadsheets/d/{sheet_id}/export?format=xlsx"


def check_workbook_bytes(data: bytes) -> bytes:
    """Reject empty, oversized or non-xlsx payloads before parsing."""
    if not data:
        raise SheetSourceError("The file is empty")
    if len(data) > MAX_WORKBOOK_BYTES:
        raise SheetSourceError("The file is larger than 5 MB")
    if not data.startswith(_ZIP_MAGIC):
        raise SheetSourceError("The file is not an .xlsx workbook")
    return data


def decode_upload(content_base64: str) -> bytes:
    """Decode a base64 upload and validate it as a workbook."""
    raw = (content_base64 or "").strip()
    # A data URL prefix (FileReader.readAsDataURL) is tolerated.
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    # Cheap size check before decoding: base64 is 4/3 of the payload.
    if len(raw) > MAX_WORKBOOK_BYTES * 4 // 3 + 4:
        raise SheetSourceError("The file is larger than 5 MB")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as err:
        raise SheetSourceError("The upload could not be read") from err
    return check_workbook_bytes(data)


async def fetch_google_sheet(session: Any, url: str) -> bytes:
    """Download a Google spreadsheet as xlsx.

    The sheet must be shared as "anyone with the link"; otherwise Google
    answers with its sign-in page (HTML), which is reported as not shared.
    """
    export_url = google_export_url(google_sheet_id(url))
    not_shared = SheetSourceError(
        "The sheet is not shared via link. In Google Sheets choose "
        "Share → General access → Anyone with the link."
    )
    try:
        async with asyncio.timeout(GOOGLE_FETCH_TIMEOUT_SECONDS):
            async with session.get(export_url, allow_redirects=True) as resp:
                # Google serves the export from googleusercontent.com after a
                # redirect; anything else (a sign-in page) means not shared.
                final_host = (resp.url.host or "").lower()
                if not (
                    final_host == _GOOGLE_HOST
                    or final_host.endswith(".googleusercontent.com")
                ):
                    raise not_shared
                if resp.status in (401, 403, 404):
                    raise not_shared
                if resp.status != 200:
                    raise SheetSourceError(
                        f"Google Sheets answered with HTTP {resp.status}"
                    )
                if "text/html" in (resp.headers.get("Content-Type") or "").lower():
                    raise not_shared
                if (resp.content_length or 0) > MAX_WORKBOOK_BYTES:
                    raise SheetSourceError("The file is larger than 5 MB")
                data = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_WORKBOOK_BYTES:
                        raise SheetSourceError("The file is larger than 5 MB")
    except TimeoutError as err:
        raise SheetSourceError("Google Sheets did not answer in time") from err
    data = bytes(data)
    if data and not data.startswith(_ZIP_MAGIC):
        raise not_shared
    return check_workbook_bytes(data)
