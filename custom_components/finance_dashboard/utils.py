"""Shared helpers for the Finance integration.

Keep this module dependency-free (only stdlib + typing) so it can be
imported from api.py, manager.py, sensor.py, demo.py without pulling
Home Assistant or the Enable Banking client as a side-effect.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# IBAN masking — single source of truth
# ---------------------------------------------------------------------------

# Separate fallbacks so callers can signal different "no data" states without
# branching at every call site.
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
# Cache-age helpers
# ---------------------------------------------------------------------------

# Threshold in seconds — above this the UI should surface a "stale cache"
# warning. 24h matches the Enable Banking rate-limit cadence: users who hit
# the 4/day quota would otherwise see yesterday's data without any hint.
CACHE_STALE_SECONDS = 24 * 3600


def cache_age_seconds(last_refresh: datetime | None) -> int | None:
    """Return the age (in seconds) of the cache, or None if never refreshed."""
    if last_refresh is None:
        return None
    return int((datetime.now() - last_refresh).total_seconds())


def is_cache_stale(last_refresh: datetime | None) -> bool:
    """True when the cache is older than CACHE_STALE_SECONDS (or empty)."""
    age = cache_age_seconds(last_refresh)
    if age is None:
        return False  # Empty cache is a different state than "stale"
    return age > CACHE_STALE_SECONDS


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
