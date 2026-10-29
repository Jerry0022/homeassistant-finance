"""Pot cycle history and the carry-over accept/drop decision. Invented figures only."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.finance_dashboard.budget_plan import BudgetPlan
from custom_components.finance_dashboard.home import build_home
from custom_components.finance_dashboard.pots import (
    Pot,
    PotStore,
    pot_cycle_history,
    pot_status,
    week_status,
)
from tests.fakes import FakeStore
from tests.test_home import ACCOUNTS, NOW, POTS, TXS, _Json, _manager, _request, _tx

CYCLE = (date(2026, 4, 1), date(2026, 4, 30))  # 30 days, 300 budget -> 10 per day


def _pot() -> Pot:
    return Pot(id="p", name="Food", owner="shared", cycle_budget=300.0, category_keys=["food"])


def _b(day: int, amount: float, *, month: int = 4, pending: bool = False) -> dict:
    return {"date": date(2026, month, day), "amount": amount, "category": "food",
            "pending": pending, "label": "x"}


def _home(txs, pots) -> dict:
    return build_home(
        accounts=ACCOUNTS, transactions=txs, plan=BudgetPlan(), pots=pots,
        recurring=[], banks=[], as_of=NOW, now=NOW, person="Anna", view="person", horizon="cycle",
    )


def test_pot_rows_carry_cycle_history_from_the_same_cycle_rule() -> None:
    fun = _home([*TXS, _tx("a1", -40.0, "leisure", 10, "Hobby", month=3)], POTS)["pots"][0]
    assert fun["history"] == [
        {"start": "2026-03-01", "end": "2026-03-31", "budget": 150.0, "spent": 40.0, "carry": 110.0}
    ]
    assert fun["week_start"] == "2026-04-13" and fun["carry_decision"] is None


def test_history_is_empty_without_bookings_and_capped_at_six() -> None:
    assert _home([], POTS)["pots"][0]["history"] == []
    incomes = [_tx("a1", 3100, "income", 1, month=m) for m in range(1, 5)]
    # Jan..Apr salaries -> only 3 finished cycles (Jan, Feb, Mar), never more than 6.
    assert len(_home(incomes, POTS)["pots"][0]["history"]) == 3


def test_pot_cycle_history_closing_balance_ignores_pending() -> None:
    rows = pot_cycle_history(
        _pot(), [_b(5, 120.0, month=3), _b(6, 400.0, month=3, pending=True)],
        [(date(2026, 3, 1), date(2026, 3, 31))],
    )
    assert rows == [{"start": "2026-03-01", "end": "2026-03-31", "budget": 300.0,
                     "spent": 120.0, "carry": 180.0}]


def test_drop_removes_week_carry_from_balance_and_week_status() -> None:
    pot, today = _pot(), date(2026, 4, 15)  # week starts 13th
    base = pot_status(pot, [_b(2, 50.0)], CYCLE, today)
    assert base["carry_in_week"] == 70.0 and base["carry_decision"] is None
    ws_base = week_status([pot], [_b(2, 50.0)], CYCLE, today)
    pot.carry_decisions = {"2026-04-13": "drop"}
    dropped = pot_status(pot, [_b(2, 50.0)], CYCLE, today)
    assert dropped["balance"] == pytest.approx(base["balance"] - 70.0)
    assert dropped["carry_decision"] == "drop"
    ws = week_status([pot], [_b(2, 50.0)], CYCLE, today)
    assert ws["carry_over"] == pytest.approx(ws_base["carry_over"] - 70.0)
    pot.carry_decisions = {"2026-04-06": "drop"}  # another week: no effect
    assert pot_status(pot, [_b(2, 50.0)], CYCLE, today)["balance"] == base["balance"]


def test_dropped_carry_reaches_the_home_row() -> None:
    pot = Pot("fun", "Anna Fun", "Anna", 300.0, ["leisure"])
    before = _home(TXS, [pot])["pots"][0]
    pot.carry_decisions = {"2026-04-13": "drop"}
    after = _home(TXS, [pot])["pots"][0]
    assert before["carry_in_week"] > 0 and after["carry_decision"] == "drop"
    assert after["balance"] == pytest.approx(before["balance"] - before["carry_in_week"])


@pytest.mark.asyncio
async def test_carry_decision_is_idempotent_persisted_and_survives_pot_edit() -> None:
    with patch("custom_components.finance_dashboard.pots.Store", FakeStore):
        store = PotStore(MagicMock())
        await store.async_load()
        pot = await store.async_upsert(Pot.from_dict({"name": "Food"}), replace_existing=False)
        monday = date(2026, 4, 13)
        assert await store.async_set_carry_decision(pot.id, monday, "drop") is True
        assert await store.async_set_carry_decision(pot.id, monday, "drop") is True
        assert pot.carry_decisions == {"2026-04-13": "drop"}
        assert await store.async_set_carry_decision(pot.id, monday, "accept") is True
        assert pot.carry_decisions == {"2026-04-13": "accept"}
        assert await store.async_set_carry_decision("nope", monday, "drop") is False
        with pytest.raises(ValueError):
            await store.async_set_carry_decision(pot.id, monday, "bogus")
        edited = Pot.from_dict({"id": pot.id, "name": "Food 2"})  # PUT without decisions
        await store.async_upsert(edited, replace_existing=True)
        assert store.get(pot.id).carry_decisions == {"2026-04-13": "accept"}
        again = PotStore(MagicMock())
        again._store = store._store
        assert (await again.async_load())[0].carry_decisions == {"2026-04-13": "accept"}


def test_carry_decisions_input_is_sanitised() -> None:
    pot = Pot.from_dict({"name": "X", "carry_decisions": {
        "2026-04-13": "drop", "2026-04-14": "drop", "junk": "drop", "2026-04-06": "evil"}})
    assert pot.carry_decisions == {"2026-04-13": "drop"}  # Monday + valid action only


@pytest.mark.asyncio
@pytest.mark.parametrize(("is_admin", "body", "expected"), [
    (True, {"id": "fun", "action": "drop"}, 200),
    (True, {"id": "fun", "action": "bogus"}, 400),
    (True, {"id": "nope", "action": "accept"}, 404),
    (False, {"id": "fun", "action": "drop"}, 403),
])
async def test_pot_carry_endpoint_is_admin_only(is_admin, body, expected) -> None:
    from custom_components.finance_dashboard.api import FinanceDashboardPotCarryView

    view = FinanceDashboardPotCarryView()
    view.json = _Json().json
    mgr = _manager()
    mgr.async_set_pot_carry = AsyncMock(
        side_effect=lambda pid, act: (
            {"pot_id": pid, "week_start": "2026-04-13", "action": act} if pid == "fun" else None
        )
    )
    user = SimpleNamespace(id="u", name="n", is_admin=is_admin)
    with patch("custom_components.finance_dashboard.api.home._get_manager", return_value=mgr):
        resp = await view.post(_request(user, body=body))
    assert resp._status == expected
