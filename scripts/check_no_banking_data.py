#!/usr/bin/env python3
"""Pre-commit hook: block real financial data from being committed.

Scans staged files for IBAN patterns, long numeric account IDs, and
EUR-denominated amounts.  Exits with code 1 (blocking the commit) if a
real-looking pattern is found.

Allowlisted test data:
  - DE89370400440532013000  (officially published test IBAN per Deutsche Bank)

Allowlisted paths (never blocked):
  - tests/            — test fixtures may contain the canonical test IBAN
  - docs/concepts/    — design documents with example values
  - BUILDLOG.md       — audit reports reference safe examples
  - Files whose first 200 bytes contain "test data" or "example data"
    (case-insensitive) are skipped.
"""

from __future__ import annotations

import re
import sys

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# DE IBAN — 2-char country code + 2 check digits + 18 alphanumeric chars
_RE_IBAN = re.compile(r'\bDE\d{20}\b')

# Long numeric strings typical of account numbers (16–19 digits).
# Only block these when NOT surrounded by quotes/brackets that indicate
# they are already-masked demo/test values.
_RE_ACCOUNT = re.compile(r'(?<!["\'\[*#])\b\d{16,19}\b(?!["\'\]*#])')

# EUR amounts — "1234.56 EUR", "99,99€", etc.
_RE_AMOUNT = re.compile(r'\b\d+[.,]\d{2}\s*(?:EUR|€)\b', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Allowlists
# ---------------------------------------------------------------------------

# Officially published test IBAN (safe to commit in test fixtures)
_ALLOWED_IBANS: set[str] = {
    "DE89370400440532013000",
}

_ALLOWED_PATH_PREFIXES = (
    "tests/",
    "tests\\",
    "docs/concepts/",
    "docs\\concepts\\",
    "BUILDLOG.md",
)

_ALLOWED_CONTENT_MARKERS = (
    "test data",
    "example data",
    "testdata",
    "demo data",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_binary(path: str) -> bool:
    """Return True if the file looks binary (no-op it)."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def _has_content_marker(path: str) -> bool:
    """Return True if the file explicitly declares itself as test/example data."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(200).decode("utf-8", errors="replace").lower()
        return any(marker in header for marker in _ALLOWED_CONTENT_MARKERS)
    except OSError:
        return False


def _is_allowlisted_path(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(norm.startswith(p.replace("\\", "/")) or norm == p.rstrip("/")
               for p in _ALLOWED_PATH_PREFIXES)


# ---------------------------------------------------------------------------
# Main scan logic
# ---------------------------------------------------------------------------


def scan_file(path: str) -> list[str]:
    """Return list of violation strings for *path*, or empty list if clean."""
    if _is_binary(path):
        return []
    if _is_allowlisted_path(path):
        return []
    if _has_content_marker(path):
        return []

    violations: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, start=1):
                # --- IBAN check ---
                for m in _RE_IBAN.finditer(line):
                    iban = m.group(0)
                    if iban not in _ALLOWED_IBANS:
                        violations.append(
                            f"BLOCK: {path}:{lineno} contains IBAN pattern '{iban}'"
                        )

                # --- Long account number check ---
                for m in _RE_ACCOUNT.finditer(line):
                    # Skip pure years / version numbers (≤ 4 chars context)
                    digit_str = m.group(0)
                    violations.append(
                        f"BLOCK: {path}:{lineno} contains long numeric "
                        f"account-id pattern '{digit_str[:8]}...' "
                        f"(16-19 digit string)"
                    )

                # --- EUR amount check ---
                for m in _RE_AMOUNT.finditer(line):
                    violations.append(
                        f"BLOCK: {path}:{lineno} contains EUR amount "
                        f"pattern '{m.group(0)}'"
                    )
    except OSError as exc:
        violations.append(f"BLOCK: {path}: could not read file ({exc})")

    return violations


def main(argv: list[str]) -> int:
    """Entry point — returns exit code."""
    files = argv[1:]  # pre-commit passes filenames as positional args
    if not files:
        return 0

    all_violations: list[str] = []
    for path in files:
        all_violations.extend(scan_file(path))

    for v in all_violations:
        print(v, file=sys.stderr)

    if all_violations:
        print(
            f"\npre-commit: {len(all_violations)} potential banking data "
            "pattern(s) found. Remove the data or add the file to the "
            "allowlist in scripts/check_no_banking_data.py.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
