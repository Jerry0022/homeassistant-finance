"""Recurring transaction detection.

Auto-detects monthly recurring payments by analyzing:
- Same creditor/debtor appearing multiple months
- Similar amounts (±10% tolerance)
- Regular timing pattern

Detected recurring transactions become "Fixkosten" and are
assigned to their logical month (with bank day correction).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Amount tolerance for "same" recurring payment
AMOUNT_TOLERANCE = 0.10  # ±10%

# Minimum occurrences to consider a pattern recurring
MIN_OCCURRENCES = 2


def detect_recurring(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect recurring payment patterns in transaction history.

    Groups transactions by creditor name, then checks for monthly
    recurrence with similar amounts.

    Returns:
        List of detected recurring patterns:
        [
            {
                "creditor": "Vermieter GmbH",
                "average_amount": -1590.02,
                "frequency": "monthly",
                "expected_day": 1,
                "occurrences": 3,
                "category": "housing",
                "last_seen": "2026-03-01",
                "confirmed": False,
            }
        ]
    """
    # Group by creditor name (normalized)
    by_creditor: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for txn in transactions:
        if txn.get("_status") != "booked":
            continue

        creditor = _normalize_name(
            txn.get("creditorName", "")
            or txn.get("debtorName", "")
        )
        if not creditor:
            continue

        by_creditor[creditor].append(txn)

    # Analyze each creditor group for recurring pattern
    patterns = []
    for creditor, txns in by_creditor.items():
        if len(txns) < MIN_OCCURRENCES:
            continue

        pattern = _analyze_pattern(creditor, txns)
        if pattern:
            patterns.append(pattern)

    # Sort by absolute amount (largest first)
    patterns.sort(
        key=lambda p: abs(p["average_amount"]), reverse=True
    )

    _LOGGER.info("Detected %d recurring patterns", len(patterns))
    return patterns


def _analyze_pattern(
    creditor: str, transactions: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Analyze a creditor's transactions for recurring pattern."""
    amounts = []
    dates = []

    for txn in transactions:
        amount = float(
            txn.get("transactionAmount", {}).get("amount", 0)
        )
        booking_str = txn.get("bookingDate", "")
        if not booking_str:
            continue

        try:
            booking = datetime.strptime(booking_str, "%Y-%m-%d")
            amounts.append(amount)
            dates.append(booking)
        except ValueError:
            continue

    if len(amounts) < MIN_OCCURRENCES:
        return None

    # Check amount consistency (±10%)
    avg_amount = sum(amounts) / len(amounts)
    if avg_amount == 0:
        return None

    amount_consistent = all(
        abs(a - avg_amount) / abs(avg_amount) <= AMOUNT_TOLERANCE
        for a in amounts
    )
    if not amount_consistent:
        return None

    # Check monthly frequency — transactions should be ~30 days apart
    dates.sort()
    if len(dates) >= 2:
        intervals = [
            (dates[i + 1] - dates[i]).days
            for i in range(len(dates) - 1)
        ]
        avg_interval = sum(intervals) / len(intervals)

        # Monthly: 25-35 days between occurrences
        if not (25 <= avg_interval <= 35):
            return None

    # Detect expected day of month
    days = [d.day for d in dates]
    expected_day = _most_common(days)

    return {
        "creditor": creditor,
        "average_amount": round(avg_amount, 2),
        "frequency": "monthly",
        "expected_day": expected_day,
        "occurrences": len(amounts),
        "category": transactions[0].get("category", "other"),
        "last_seen": max(dates).strftime("%Y-%m-%d"),
        "confirmed": False,
    }


def _normalize_name(name: str) -> str:
    """Normalize creditor/debtor name for grouping."""
    if not name:
        return ""
    # Lowercase, strip extra spaces
    return " ".join(name.lower().strip().split())


def _most_common(values: list[int]) -> int:
    """Return the most common value in a list."""
    if not values:
        return 1
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)
