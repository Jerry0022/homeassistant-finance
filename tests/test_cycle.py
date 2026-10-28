"""Income cycle rule (person + household 7-day rule). All figures invented."""

from __future__ import annotations

from datetime import date

from custom_components.finance_dashboard.cycle import (
    household_cycle,
    person_cycle,
    salary_starts,
)


def _d(m: int, d: int, y: int = 2026) -> date:
    return date(y, m, d)


def test_person_cycle_runs_from_highest_income_to_next() -> None:
    incomes = [(_d(3, 1), 3000.0), (_d(4, 1), 3000.0), (_d(5, 1), 3000.0), (_d(4, 10), 40.0)]
    assert person_cycle(incomes, _d(4, 20)) == (_d(4, 1), _d(4, 30))


def test_person_cycle_ignores_small_incomes_and_takes_earliest_of_event() -> None:
    # Salary split over two bookings 3 days apart (within the ±5 tolerance).
    incomes = [(_d(4, 1), 3000.0), (_d(4, 4), 2900.0), (_d(5, 1), 3000.0), (_d(4, 15), 100.0)]
    assert salary_starts(incomes) == [_d(4, 1), _d(5, 1)]


def test_person_cycle_open_end_uses_typical_length_and_overdue_extends() -> None:
    incomes = [(_d(3, 1), 3000.0), (_d(4, 1), 3000.0)]
    assert person_cycle(incomes, _d(4, 10)) == (_d(4, 1), _d(5, 1))  # 31-day gap
    assert person_cycle(incomes, _d(5, 5)) == (_d(4, 1), _d(5, 5))  # overdue salary


def test_person_cycle_calendar_fallback_without_income() -> None:
    assert person_cycle([], _d(2, 10)) == (_d(2, 1), _d(2, 28))


def _household(anna_day: int, max_day: int):
    anna = [(date(2026, m, anna_day), 3100.0) for m in (3, 4, 5)]
    max_ = [(date(2026, m, max_day), 2400.0) for m in (3, 4, 5)]
    return {"Anna": anna, "Max": max_}


def test_household_start_is_highest_income() -> None:
    start, end, anchor = household_cycle(_household(1, 15), _d(4, 20))
    assert (start, end, anchor) == (_d(4, 1), _d(4, 30), "Anna")


def test_household_other_salary_within_7_days_before_moves_start() -> None:
    # Max is paid on the 25th: 6 days before Anna's 1st -> Max sets the start.
    start, end, anchor = household_cycle(_household(1, 26), _d(4, 10))
    # Anna 1 Apr, Max 26 Mar (6 days before) -> cycle starts 26 Mar.
    assert (start, anchor) == (_d(3, 26), "Max")
    assert end == _d(4, 25)


def test_household_edge_exactly_7_days_counts_8_days_does_not() -> None:
    seven = household_cycle(_household(8, 1), _d(4, 20))  # 1st is 7 days before 8th
    assert (seven[0], seven[2]) == (_d(4, 1), "Max")
    eight = household_cycle(_household(9, 1), _d(4, 20))  # 8 days before
    assert (eight[0], eight[2]) == (_d(4, 9), "Anna")


def test_household_same_day_salary_keeps_main_anchor() -> None:
    start, _, anchor = household_cycle(_household(1, 1), _d(4, 10))
    assert (start, anchor) == (_d(4, 1), "Anna")


def test_household_other_salary_after_main_does_not_move_start() -> None:
    start, _, anchor = household_cycle(_household(1, 3), _d(4, 10))
    assert (start, anchor) == (_d(4, 1), "Anna")


def test_household_calendar_fallback() -> None:
    start, end, anchor = household_cycle({}, _d(6, 10))
    assert (start, end, anchor) == (_d(6, 1), _d(6, 30), None)
