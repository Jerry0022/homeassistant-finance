"""Month cycle logic — calendar vs. salary-based periods.

Handles:
- Calendar month: 1st to last day
- Salary-based: from salary date to next salary date
- Logical month assignment for recurring costs (bank day correction)
- Salary date tolerance window (±5 days)

The core problem: "Month" in budgeting is not always a calendar month.
A salary arriving on the 25th of the previous month may "belong" to the
current month's budget. Recurring costs like rent may shift by a few
days due to weekends/bank holidays.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Tolerance window for salary date detection
SALARY_TOLERANCE_DAYS = 5


def get_month_range(
    target_month: int,
    target_year: int,
    cycle_mode: str = "calendar",
    salary_day: int = 25,
) -> tuple[date, date]:
    """Get the date range for a budget month.

    Args:
        target_month: Month number (1-12)
        target_year: Year
        cycle_mode: "calendar" or "salary"
        salary_day: Day of month when salary typically arrives

    Returns:
        Tuple of (start_date, end_date) inclusive
    """
    if cycle_mode == "salary":
        return _salary_month_range(target_month, target_year, salary_day)
    return _calendar_month_range(target_month, target_year)


def _calendar_month_range(month: int, year: int) -> tuple[date, date]:
    """Standard calendar month: 1st to last day."""
    start = date(year, month, 1)
    # Last day = first of next month - 1 day
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _salary_month_range(month: int, year: int, salary_day: int) -> tuple[date, date]:
    """Salary-based month: from salary date to next salary date - 1.

    For month=3, salary_day=25:
    Start = Feb 25 (salary for March arrived)
    End = Mar 24 (day before next salary)
    """
    # Start: salary_day of previous month
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    # Clamp salary_day to valid range for the month
    import calendar

    max_day_prev = calendar.monthrange(prev_year, prev_month)[1]
    clamped_start = min(salary_day, max_day_prev)
    start = date(prev_year, prev_month, clamped_start)

    # End: salary_day - 1 of current month
    max_day_curr = calendar.monthrange(year, month)[1]
    clamped_end = min(salary_day, max_day_curr)
    end = date(year, month, clamped_end) - timedelta(days=1)

    return start, end


def assign_logical_month(
    transaction: dict[str, Any],
    recurring_pattern: dict[str, Any] | None = None,
) -> tuple[int, int] | None:
    """Assign a transaction to its logical budget month.

    For recurring transactions (rent, subscriptions), the logical month
    may differ from the booking date due to bank day shifts.

    Example: Rent normally on 1st of month. Feb 28 booking (Saturday
    pushed to Friday) → logical month = March.

    Args:
        transaction: Transaction dict with bookingDate
        recurring_pattern: If known recurring, contains expected_day

    Returns:
        (month, year) tuple or None if no adjustment needed
    """
    booking_date_str = transaction.get("bookingDate", "")
    if not booking_date_str:
        return None

    try:
        booking = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    if not recurring_pattern:
        # Not a known recurring transaction — use actual booking date
        return booking.month, booking.year

    expected_day = recurring_pattern.get("expected_day", 1)

    # Check if this booking is within the tolerance window of the
    # expected day, but in the wrong month (bank day shift)
    if booking.day >= 25 and expected_day <= 5:
        # Booking at end of month, but expected at start of next month
        # → Assign to next month
        if booking.month == 12:
            return 1, booking.year + 1
        return booking.month + 1, booking.year

    if booking.day <= 5 and expected_day >= 25:
        # Booking at start of month, but expected at end of previous month
        # → Assign to previous month
        if booking.month == 1:
            return 12, booking.year - 1
        return booking.month - 1, booking.year

    # Within same month — no adjustment
    return booking.month, booking.year


def is_salary_candidate(
    transaction: dict[str, Any],
    expected_day: int,
    expected_amount: float | None = None,
) -> bool:
    """Check if a transaction looks like a salary payment.

    Uses ±5 day tolerance window and positive amount check.

    Args:
        transaction: Transaction dict
        expected_day: Expected day of month for salary
        expected_amount: Optional expected amount for validation

    Returns:
        True if transaction matches salary pattern
    """
    amount = float(transaction.get("transactionAmount", {}).get("amount", 0))
    if amount <= 0:
        return False  # Salary must be incoming (positive)

    booking_date_str = transaction.get("bookingDate", "")
    if not booking_date_str:
        return False

    try:
        booking = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except ValueError:
        return False

    # Check if within ±5 day tolerance of expected day
    day_diff = abs(booking.day - expected_day)
    # Handle month boundary (e.g., expected 28, actual 2 of next month)
    if day_diff > 15:
        day_diff = 31 - day_diff  # Wrap around

    if day_diff > SALARY_TOLERANCE_DAYS:
        return False

    # Optional: check amount within ±20% of expected
    if expected_amount and expected_amount > 0:
        amount_diff = abs(amount - expected_amount) / expected_amount
        if amount_diff > 0.20:
            return False

    return True


def detect_salary_day(
    transactions: list[dict[str, Any]],
    min_amount: float = 1000.0,
) -> int | None:
    """Auto-detect the typical salary arrival day from transaction history.

    Looks for the most common day-of-month for large incoming transactions.

    Args:
        transactions: List of transactions (booked)
        min_amount: Minimum amount to consider as salary

    Returns:
        Most likely salary day (1-31) or None if no pattern found
    """
    day_counts: dict[int, int] = {}

    for txn in transactions:
        amount = float(txn.get("transactionAmount", {}).get("amount", 0))
        if amount < min_amount:
            continue

        booking_date_str = txn.get("bookingDate", "")
        if not booking_date_str:
            continue

        try:
            day = datetime.strptime(booking_date_str, "%Y-%m-%d").day
            day_counts[day] = day_counts.get(day, 0) + 1
        except ValueError:
            continue

    if not day_counts:
        return None

    # Find the most common day
    best_day = max(day_counts, key=day_counts.get)

    # Only return if it appears at least twice (pattern confidence)
    if day_counts[best_day] >= 2:
        return best_day
    return None
