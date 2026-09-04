"""Shared helpers for the Finance integration.

Keep this module dependency-free (only stdlib + typing) so it can be
imported from api/, manager/, sensor.py, demo.py without pulling Home
Assistant or the Enable Banking client as a side-effect.

Scope note: cache-age / staleness are intentionally NOT computed here.
``manager.get_refresh_status()`` is the single hardened source of truth
for ``cache_age_seconds`` / ``cache_is_stale`` (see the manager's
``_CACHE_STALE_THRESHOLD_SECONDS``); the diagnostics widget and state
banner reuse those values instead of a parallel threshold.
"""

from __future__ import annotations

from typing import Any, Iterable


# ---------------------------------------------------------------------------
# IBAN masking — single source of truth for UI-facing masking
# ---------------------------------------------------------------------------

# Separate fallbacks so callers can signal different "no data" states without
# branching at every call site. (Log-body PII stripping is a separate concern
# handled by ``enablebanking_client._sanitize_log``.)
IBAN_MASK_DEFAULT = "****"
IBAN_MASK_UNKNOWN = "?"


def mask_iban(iban: str | None, fallback: str = IBAN_MASK_DEFAULT) -> str:
    """Return the last-4 masked form of an IBAN.

    Used in API responses, sensor attributes, demo data, and the
    diagnostics widget so all of them speak the same format.
    """
    if not iban:
        return fallback
    value = str(iban).strip()
    if len(value) >= 4:
        return f"****{value[-4:]}"
    return fallback


# ---------------------------------------------------------------------------
# Transaction helpers
# ---------------------------------------------------------------------------


def count_uncategorized(
    transactions: Iterable[dict[str, Any]],
    default_category: str = "other",
) -> int:
    """Count transactions that still carry the default / missing category.

    The dashboard uses this to surface a prominent banner when a user
    has many transactions that need manual categorisation.
    """
    count = 0
    for txn in transactions:
        cat = txn.get("category") or default_category
        if cat == default_category:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Error truncation — keeps logs + API responses bounded
# ---------------------------------------------------------------------------

ERROR_MAX_LEN = 200


def shorten_error(msg: Any, max_len: int = ERROR_MAX_LEN) -> str:
    """Coerce an exception or object to a bounded error string."""
    text = str(msg) if msg is not None else ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
