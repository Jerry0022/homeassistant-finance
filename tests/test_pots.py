"""Pots: model, store, status thresholds, carry-over and week status. Invented figures."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from custom_components.finance_dashboard.pots import (
    Pot,
    PotStore,
    pot_status,
    status_for,
    week_status,
)
from tests.fakes import FakeStore

# Cycle of 30 days, pot budget 300 -> 10 EUR per day.
CYCLE = (date(2026, 4, 1), date(2026, 4, 30))


def _pot(budget: float = 300.0, kind: str = "spend") -> Pot:
    return Pot(id="p", name="Food", owner="shared", cycle_budget=budget,
               category_keys=["food"], kind=kind)


def _b(day: int, amount: float, *, pending: bool = False, month: int = 4) -> dict:
    return {"date": date(2026, month, day), "amount": amount, "category": "food",
            "pending": pending, "label": "x"}


def test_balance_carries_unspent_days_forward_inside_the_cycle() -> None:
    # Day 10: 100 earned, 40 spent -> 60 available.
    st = pot_status(_pot(), [_b(3, 40.0)], CYCLE, date(2026, 4, 10))
    assert st["balance"] == 60.0
    assert st["per_day_typical"] == 10.0
    assert st["linear_to_date"] == 100.0
    assert st["spent"] == 40.0


def test_balance_resets_at_cycle_start() -> None:
    # Previous-cycle spending (in March) does not touch the new cycle.
    st = pot_status(_pot(), [_b(28, 500.0, month=3)], CYCLE, date(2026, 4, 1))
    assert st["balance"] == 10.0
    assert st["spent"] == 0.0


def test_status_thresholds_are_ten_percent() -> None:
    assert status_for(100.0, 100.0) == "good"
    assert status_for(110.0, 100.0) == "knapp"
    assert status_for(110.01, 100.0) == "over"
    assert status_for(0.01, 0.0) == "over"


def test_pot_status_values_good_knapp_over() -> None:
    today = date(2026, 4, 10)  # linear 100
    assert pot_status(_pot(), [_b(2, 100.0)], CYCLE, today)["status"] == "good"
    assert pot_status(_pot(), [_b(2, 108.0)], CYCLE, today)["status"] == "knapp"
    assert pot_status(_pot(), [_b(2, 130.0)], CYCLE, today)["status"] == "over"


def test_pending_bookings_are_not_spent() -> None:
    st = pot_status(_pot(), [_b(10, 50.0, pending=True)], CYCLE, date(2026, 4, 10))
    assert st["spent"] == 0.0


def test_carry_in_week_only_counts_earlier_weeks_of_the_cycle() -> None:
    # 2026-04-13 is a Monday; before it: 12 days earned = 120, spent 30.
    st = pot_status(_pot(), [_b(5, 30.0), _b(14, 20.0)], CYCLE, date(2026, 4, 15))
    assert st["carry_in_week"] == 90.0
    # First week of the cycle: nothing carried in.
    first = pot_status(_pot(), [_b(2, 5.0)], CYCLE, date(2026, 4, 2))
    assert first["carry_in_week"] == 0.0


def test_reserve_pot_accumulates_like_a_spend_pot() -> None:
    st = pot_status(_pot(150.0, "reserve"), [], CYCLE, date(2026, 4, 10))
    assert st["balance"] == 50.0


def test_week_status_daily_actual_and_carry() -> None:
    pots = [_pot()]
    bookings = [_b(5, 30.0), _b(14, 12.0), _b(15, 8.0)]
    ws = week_status(pots, bookings, CYCLE, date(2026, 4, 15))  # Wed
    assert ws["start"] == "2026-04-13" and ws["end"] == "2026-04-19"
    assert [d["actual"] for d in ws["days"]][:3] == [0.0, 12.0, 8.0]
    assert ws["daily_budget"] == 10.0
    assert ws["carry_over"] == 90.0  # 12 earlier days x 10 minus 30
    assert ws["days"][3]["future"] is True


def test_week_carry_never_reaches_before_the_cycle_start() -> None:
    # Overspend in March must not leak into the first week of April.
    ws = week_status([_pot()], [_b(28, 900.0, month=3)], CYCLE, date(2026, 4, 2))
    assert ws["carry_over"] == 0.0
    assert [d["in_cycle"] for d in ws["days"]][:2] == [False, False]  # Mon/Tue 30/31 Mar


def test_zero_carry_line_is_clamped_at_zero_when_carry_eats_the_week() -> None:
    # Overspent 400 in the first 12 days -> carry deeply negative.
    bookings = [_b(3, 400.0)]
    ws = week_status([_pot()], bookings, CYCLE, date(2026, 4, 15))
    assert ws["carry_over"] < -70
    assert ws["week_budget"] == 0.0
    assert ws["zero_carry_line"] == [0.0] * 7
    assert ws["linear_line"] == [0.0] * 7


def test_zero_carry_line_is_linear_when_budget_left() -> None:
    ws = week_status([_pot()], [], CYCLE, date(2026, 4, 15))
    assert ws["zero_carry_line"][:3] == [10.0, 20.0, 30.0]
    assert ws["zero_carry_line"][6] == 70.0


def test_week_upcoming_includes_pending_with_flag() -> None:
    bookings = [_b(16, 25.0, pending=True), _b(15, 4.0)]
    ws = week_status([_pot()], bookings, CYCLE, date(2026, 4, 15))
    assert ws["upcoming"]["sum"] == 25.0
    assert ws["upcoming"]["items"][0]["pending"] is True


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""},
        {"name": "x", "cycle_budget": -1},
        {"name": "x", "cycle_budget": "abc"},
        {"name": "x", "kind": "bogus"},
        {"name": "x", "category_keys": "food"},
    ],
)
def test_pot_validation_rejects_bad_input(bad: dict) -> None:
    with pytest.raises(ValueError):
        Pot.from_dict(bad)


@pytest.mark.asyncio
async def test_pot_store_roundtrip_and_unique_ids() -> None:
    with patch("custom_components.finance_dashboard.pots.Store", FakeStore):
        store = PotStore(MagicMock())
        await store.async_load()
        a = await store.async_upsert(Pot.from_dict({"name": "Food", "owner": "Anna"}),
                                     replace_existing=False)
        b = await store.async_upsert(Pot.from_dict({"name": "Food", "owner": "Anna"}),
                                     replace_existing=False)
        assert a.id != b.id
        again = PotStore(MagicMock())
        again._store = store._store
        assert len(await again.async_load()) == 2
        assert await store.async_delete(a.id) is True
        assert await store.async_delete("nope") is False
