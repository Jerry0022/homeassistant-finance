"""R11 — Pre-commit banking data hook tests.

Three cases:
  1. Clean file → no violations
  2. File with real IBAN → blocked
  3. File with the allowlisted test IBAN DE89370400440532013000 → allowed
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Import the hook module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import check_no_banking_data as hook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tmp(content: str) -> str:
    """Write *content* to a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    except Exception:
        os.unlink(path)
        raise
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_clean_file_no_violations() -> None:
    """A file with no banking data must produce zero violations."""
    path = _write_tmp("Hello, world!\nThis is a clean file.\n")
    try:
        violations = hook.scan_file(path)
        assert violations == [], f"Unexpected violations: {violations}"
    finally:
        os.unlink(path)


def test_real_iban_is_blocked() -> None:
    """A file containing a real-looking DE IBAN must be blocked."""
    # DE12500105170648489890 — fictional but structurally valid IBAN
    path = _write_tmp("account_iban: DE12500105170648489890\n")
    try:
        violations = hook.scan_file(path)
        assert len(violations) >= 1, "Expected at least one violation for real IBAN"
        assert any("IBAN" in v for v in violations)
    finally:
        os.unlink(path)


def test_allowlisted_test_iban_is_allowed() -> None:
    """The canonical public test IBAN must NOT be blocked."""
    path = _write_tmp("test_iban: DE89370400440532013000\n")
    try:
        violations = hook.scan_file(path)
        iban_violations = [v for v in violations if "IBAN" in v]
        assert iban_violations == [], (
            f"Test IBAN DE89370400440532013000 was wrongly blocked: {iban_violations}"
        )
    finally:
        os.unlink(path)


def test_allowlisted_tests_path_is_skipped() -> None:
    """Files under tests/ must be skipped entirely."""
    # Simulate a path under tests/
    violations = hook.scan_file.__func__ if hasattr(hook.scan_file, "__func__") else hook.scan_file
    # Override path prefix check directly
    assert hook._is_allowlisted_path("tests/test_fixtures.py")
    assert hook._is_allowlisted_path("tests\\test_fixtures.py")
    assert not hook._is_allowlisted_path("custom_components/finance_dashboard/manager.py")


def test_main_returns_0_for_clean_files() -> None:
    """main() must return 0 when all files are clean."""
    path = _write_tmp("nothing financial here\n")
    try:
        rc = hook.main(["hook", path])
        assert rc == 0
    finally:
        os.unlink(path)


def test_main_returns_1_for_dirty_files() -> None:
    """main() must return 1 when a real IBAN is found."""
    path = _write_tmp("iban=DE12500105170648489890\n")
    try:
        rc = hook.main(["hook", path])
        assert rc == 1
    finally:
        os.unlink(path)
