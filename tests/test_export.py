"""Tests for CSV export and TTL cleanup (coverage gap fill).

Covers:
1. _write_csv: standard transactions + header order
2. _write_csv: empty list yields header-only CSV
3. _write_csv: German umlauts and special chars survive UTF-8 BOM encoding
4. _write_csv: nested transactionAmount dict extracted correctly
5. _write_csv: missing keys fall back to documented defaults
6. _cleanup_old_exports: removes files older than TTL, keeps fresh ones
7. _cleanup_old_exports: missing directory is a no-op (doesn't raise)
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from custom_components.finance_dashboard.export import (
    EXPORT_TTL_HOURS,
    _cleanup_old_exports,
    _write_csv,
)

# ---------------------------------------------------------------------------
# _write_csv
# ---------------------------------------------------------------------------

def test_write_csv_standard_row(tmp_path: Path):
    """Happy: writes header + one row with all 7 columns populated."""
    fp = tmp_path / "out.csv"
    txns = [
        {
            "bookingDate": "2026-05-10",
            "transactionAmount": {"amount": "-49.99", "currency": "EUR"},
            "creditorName": "Amazon",
            "remittanceInformationUnstructured": "Order 123",
            "category": "subscriptions",
            "_status": "booked",
        }
    ]
    _write_csv(fp, txns)

    content = fp.read_text(encoding="utf-8-sig")
    lines = content.strip().split("\n")
    assert lines[0] == "date;amount;currency;creditor;description;category;status"
    assert "2026-05-10;-49.99;EUR;Amazon;Order 123;subscriptions;booked" in lines[1]


def test_write_csv_empty_list_writes_header_only(tmp_path: Path):
    """Edge: empty input → only header row."""
    fp = tmp_path / "empty.csv"
    _write_csv(fp, [])
    content = fp.read_text(encoding="utf-8-sig")
    lines = [line for line in content.strip().split("\n") if line]
    assert len(lines) == 1
    assert lines[0].startswith("date;amount;currency")


def test_write_csv_umlauts_roundtrip(tmp_path: Path):
    """Edge: German chars survive the UTF-8 BOM encoding."""
    fp = tmp_path / "umlauts.csv"
    txns = [
        {
            "bookingDate": "2026-05-10",
            "transactionAmount": {"amount": "-12.50", "currency": "EUR"},
            "creditorName": "Müller Gärtnerei",
            "remittanceInformationUnstructured": "Rechnung Ü-Ber Größe",
            "category": "other",
            "_status": "booked",
        }
    ]
    _write_csv(fp, txns)

    content = fp.read_text(encoding="utf-8-sig")
    assert "Müller Gärtnerei" in content
    assert "Größe" in content


def test_write_csv_missing_keys_fall_back_to_defaults(tmp_path: Path):
    """Edge: minimal txn dict uses documented defaults."""
    fp = tmp_path / "min.csv"
    txns = [{"bookingDate": "2026-05-10"}]  # everything else missing
    _write_csv(fp, txns)

    content = fp.read_text(encoding="utf-8-sig")
    row = content.strip().split("\n")[1]
    # amount=0, currency=EUR, creditor="", description="", category=other, status=booked
    assert row == "2026-05-10;0;EUR;;;other;booked"


def test_write_csv_handles_pending_status(tmp_path: Path):
    """Edge: _status="pending" forwarded; nested amount handled."""
    fp = tmp_path / "pending.csv"
    txns = [
        {
            "bookingDate": "2026-05-12",
            "transactionAmount": {"amount": "100.00", "currency": "USD"},
            "creditorName": "Stripe",
            "category": "income",
            "_status": "pending",
        }
    ]
    _write_csv(fp, txns)
    row = fp.read_text(encoding="utf-8-sig").strip().split("\n")[1]
    assert ";USD;" in row
    assert row.endswith(";pending")


# ---------------------------------------------------------------------------
# _cleanup_old_exports
# ---------------------------------------------------------------------------

def test_cleanup_removes_files_older_than_ttl(tmp_path: Path):
    """Happy: stale exports get unlinked, fresh ones survive."""
    old = tmp_path / "finance_export_old.csv"
    fresh = tmp_path / "finance_export_fresh.csv"
    old.write_text("stale")
    fresh.write_text("fresh")

    # Backdate `old` past the TTL boundary
    stale_age = (EXPORT_TTL_HOURS + 1) * 3600
    past_ts = time.time() - stale_age
    os.utime(old, (past_ts, past_ts))

    _cleanup_old_exports(tmp_path)

    assert not old.exists()
    assert fresh.exists()


def test_cleanup_ignores_non_matching_filenames(tmp_path: Path):
    """Edge: only finance_export_*.csv files are touched."""
    unrelated = tmp_path / "other.csv"
    unrelated.write_text("keep me")
    # Even backdated, unrelated files must stay
    past = time.time() - 10 * 3600
    os.utime(unrelated, (past, past))

    _cleanup_old_exports(tmp_path)

    assert unrelated.exists()


def test_cleanup_swallows_oserror_on_unlink(tmp_path: Path, monkeypatch):
    """Edge: PermissionError from unlink() is swallowed; loop continues.

    Monkeypatches Path.unlink to raise PermissionError, then verifies that
    _cleanup_old_exports does not propagate and that a second (writable)
    file is still cleaned up afterwards.
    """
    locked = tmp_path / "finance_export_locked.csv"
    other = tmp_path / "finance_export_other.csv"
    locked.write_text("locked")
    other.write_text("other")
    past = time.time() - (EXPORT_TTL_HOURS + 1) * 3600
    os.utime(locked, (past, past))
    os.utime(other, (past, past))

    original_unlink = Path.unlink

    def _selective_unlink(self: Path, *args, **kwargs):
        if self.name == "finance_export_locked.csv":
            raise PermissionError(f"locked: {self}")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _selective_unlink)

    # Must not raise — even though one unlink fails, the loop continues
    _cleanup_old_exports(tmp_path)

    # Locked file remained (unlink raised), other was cleaned up
    assert locked.exists()
    assert not other.exists()


def test_cleanup_swallows_valueerror_on_corrupt_mtime(tmp_path: Path, monkeypatch):
    """Edge: OverflowError/ValueError from corrupt st_mtime doesn't abort.

    Some filesystems (FAT32, network shares) can return mtime values that
    overflow datetime.fromtimestamp(). The cleanup must keep going.
    """
    target = tmp_path / "finance_export_corrupt.csv"
    target.write_text("x")

    import datetime as _dt

    real_fromtimestamp = _dt.datetime.fromtimestamp
    call_count = {"n": 0}

    def _bad_fromtimestamp(ts):
        call_count["n"] += 1
        # First call (for the test file) raises; subsequent calls pass through.
        if call_count["n"] == 1:
            raise OverflowError("mtime out of range")
        return real_fromtimestamp(ts)

    monkeypatch.setattr(
        "custom_components.finance_dashboard.export.datetime",
        type("_DT", (), {
            "fromtimestamp": staticmethod(_bad_fromtimestamp),
            "now": _dt.datetime.now,
        }),
    )

    # Must not raise
    _cleanup_old_exports(tmp_path)
    # File survives because mtime parse failed before unlink could fire
    assert target.exists()
