"""Income cycles — a person's and the household's budget period.

A cycle is not a calendar month: it starts when the main income arrives and
runs until the day before the next one.

Rules (decided with the user, see ``docs/dev/household-model.md``):

- **Person**: the cycle runs from the person's *earliest highest income* to the
  next one. "Highest" means an income of at least ``SALARY_AMOUNT_RATIO`` of the
  largest income seen (so a salary is found even when it varies slightly, while
  small refunds are ignored). Incomes within the ±5-day salary tolerance of each
  other are one salary event; the earliest of them marks the start.
- **Household**: the highest income of all persons sets the cycle start, unless
  another person's salary falls within the 7 days *before* it - then that
  earlier one is the start (both salaries belong to the same budget round).

All functions are pure: no I/O, no clock. ``today`` is always passed in.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from statistics import median

from .month_cycle import SALARY_TOLERANCE_DAYS

# An income counts as "the salary" from this fraction of the largest income on.
SALARY_AMOUNT_RATIO = 0.8
# A household salary this many days (or fewer) before the highest one pulls the
# cycle start forward.
HOUSEHOLD_ANCHOR_WINDOW_DAYS = 7
# Used when only one salary event is known and the interval cannot be measured.
DEFAULT_CYCLE_DAYS = 30

Income = tuple[date, float]


def salary_starts(incomes: list[Income]) -> list[date]:
    """Dates on which a new salary cycle began, ascending.

    Args:
        incomes: ``(booking_date, amount)`` of incoming money, amount positive.
    """
    positive = [(d, float(a)) for d, a in incomes if float(a) > 0]
    if not positive:
        return []
    top = max(a for _, a in positive)
    events = sorted(d for d, a in positive if a >= top * SALARY_AMOUNT_RATIO)
    starts: list[date] = []
    for d in events:
        if starts and (d - starts[-1]).days <= SALARY_TOLERANCE_DAYS:
            continue  # same salary event, keep the earliest
        starts.append(d)
    return starts


def calendar_cycle(today: date) -> tuple[date, date]:
    """Calendar month containing ``today`` (fallback when no salary is known)."""
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last)


def _typical_length(starts: list[date]) -> int:
    gaps = [(b - a).days for a, b in zip(starts, starts[1:], strict=False)]
    return max(1, round(median(gaps))) if gaps else DEFAULT_CYCLE_DAYS


def cycle_windows(starts: list[date]) -> list[tuple[date, date]]:
    """Closed ``(start, end)`` windows between consecutive starts."""
    return [(a, b - timedelta(days=1)) for a, b in zip(starts, starts[1:], strict=False)]


def _window(starts: list[date], today: date) -> tuple[date, date] | None:
    """Cycle ``(start, end)`` containing ``today`` from known start dates."""
    past = [s for s in starts if s <= today]
    if not past:
        return None
    start = past[-1]
    future = [s for s in starts if s > today]
    if future:
        end = future[0] - timedelta(days=1)
    else:
        end = start + timedelta(days=_typical_length(starts) - 1)
    # The expected next salary is overdue: the cycle runs on until it lands.
    return start, max(end, today)


def person_cycle(incomes: list[Income], today: date) -> tuple[date, date]:
    """``(start, end)`` of the person's current cycle, both inclusive.

    Falls back to the calendar month when no salary is known yet.
    """
    return _window(salary_starts(incomes), today) or calendar_cycle(today)


def household_starts(person_incomes: dict[str, list[Income]]) -> list[tuple[date, str]]:
    """Household cycle starts ``(date, anchor person)``, ascending.

    Every salary event of the person with the highest income opens a cycle; an
    earlier salary of someone else within the 7 days before it moves the start.
    """
    per_person = {name: salary_starts(inc) for name, inc in person_incomes.items()}
    per_person = {name: s for name, s in per_person.items() if s}
    if not per_person:
        return []

    def _top(name: str) -> float:
        return max((float(a) for _, a in person_incomes[name] if float(a) > 0), default=0.0)

    main = max(per_person, key=lambda n: (_top(n), n))
    out: list[tuple[date, str]] = []
    for anchor_date in per_person[main]:
        start, who = anchor_date, main
        for name, starts in per_person.items():
            if name == main:
                continue
            for d in starts:
                if 0 < (anchor_date - d).days <= HOUSEHOLD_ANCHOR_WINDOW_DAYS and d < start:
                    start, who = d, name
        out.append((start, who))
    return out


def household_cycle(
    person_incomes: dict[str, list[Income]], today: date
) -> tuple[date, date, str | None]:
    """``(start, end, anchor_person)`` of the household's current cycle."""
    starts = household_starts(person_incomes)
    window = _window([s for s, _ in starts], today)
    if window is None:
        start, end = calendar_cycle(today)
        return start, end, None
    anchor = next(who for s, who in starts if s == window[0])
    return window[0], window[1], anchor
