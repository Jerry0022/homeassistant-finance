"""Series detection, contract derivations, reserves and pot coverage."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.finance_dashboard.account_identity import account_key
from custom_components.finance_dashboard.contracts import (
    Contract,
    ContractError,
    ContractStore,
    build_contracts,
    build_reserves,
    category_defaults,
    next_notice_deadline,
    special_termination_default,
)
from custom_components.finance_dashboard.pots import Pot, pot_coverage
from custom_components.finance_dashboard.recurring import (
    add_months,
    detect_recurring,
    detect_series,
    plan_amount,
)


def txn(day: str, amount: float, name: str = "Acme", category: str = "other", **extra):
    return {
        "_status": "booked",
        "bookingDate": day,
        "creditorName": name,
        "transactionAmount": {"amount": str(amount), "currency": "EUR"},
        "category": category,
        **extra,
    }


def monthly(amounts, name="Netflix", start=date(2026, 1, 10), **kw):
    return [txn(add_months(start, i).isoformat(), a, name, **kw) for i, a in enumerate(amounts)]


TODAY = date(2026, 6, 15)


def test_monthly_series_and_next_date():
    (s,) = detect_series(monthly([-10, -10, -10, -10, -10]), today=TODAY)
    assert s["interval"] == "monthly"
    assert s["next_expected"] == "2026-06-10"
    assert s["annual_cost"] == 120.0


def test_missing_and_ended_state():
    rows = monthly([-10, -10, -10])  # last: 2026-03-10, next 04-10
    (s,) = detect_series(rows, today=date(2026, 4, 20))
    assert s["status"] == "missing"
    (s,) = detect_series(rows, today=date(2026, 8, 1))
    assert s["status"] == "ended"
    (s,) = detect_series(rows, today=date(2026, 4, 12))
    assert s["status"] == "active"


@pytest.mark.parametrize(
    ("rows", "interval"),
    [
        ([txn(f"2026-01-{d:02d}", -5) for d in (1, 8, 15, 22, 29)], "weekly"),
        (
            [txn("2025-01-05", -90), txn("2025-04-05", -90), txn("2025-07-05", -90)],
            "quarterly",
        ),
        ([txn("2025-01-05", -300), txn("2025-07-05", -300)], "half_yearly"),
        ([txn("2024-03-01", -480), txn("2025-03-01", -480)], "yearly"),
    ],
)
def test_other_intervals(rows, interval):
    (s,) = detect_series(rows, today=date(2026, 12, 31))
    assert s["interval"] == interval


def test_irregular_gaps_rejected():
    rows = [txn("2026-01-01", -10), txn("2026-01-20", -10), txn("2026-04-02", -10)]
    assert detect_series(rows, today=TODAY) == []


def test_tolerances_configurable():
    rows = monthly([-10, -13, -17])  # two +30 % steps
    assert detect_series(rows, today=TODAY) == []
    assert len(detect_series(rows, today=TODAY, amount_tolerance=0.4)) == 1


def test_price_change_detected_with_step_beyond_tolerance():
    (s,) = detect_series(monthly([-10, -10, -10, -15]), today=TODAY)
    pc = s["price_change"]
    assert pc["increase"] is True
    assert pc["previous"] == -10.0 and pc["last"] == -15.0
    assert pc["change_pct"] == 50.0


def test_plan_modes():
    amounts = [-10.0, -12.0, -20.0, -14.0]
    assert plan_amount(amounts) == 20.0
    assert plan_amount(amounts, "average") == 14.0
    assert plan_amount(amounts, "last") == 14.0
    assert plan_amount(amounts, "median") == 13.0
    assert plan_amount(amounts, "fixed", 99) == 99.0


def test_plan_mode_override_applies():
    rows = monthly([-10, -12, -11])
    (a,) = detect_series(rows, today=TODAY)
    (b,) = detect_series(
        rows, today=TODAY, overrides={a["id"]: {"plan_mode": "fixed", "plan_fixed_amount": 50}}
    )
    assert a["plan_amount"] == -12.0 and b["plan_amount"] == -50.0


def test_legacy_monthly_detector_untouched():
    out = detect_recurring([dict(t, _status="booked") for t in monthly([-10, -10, -10])])
    assert out and out[0]["frequency"] == "monthly"


def test_add_months_clamps():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)


def test_category_defaults():
    assert category_defaults("insurance")["notice_value"] == 3
    assert category_defaults("telecom")["min_term_months"] == 24
    assert category_defaults("subscriptions")["notice_value"] == 0
    assert category_defaults("whatever")["renewal_months"] == 1


def test_notice_deadline_end_of_term_and_rollover():
    # 1y term from 2026-01-01, 3 months notice -> term end 2027-01-01, deadline 2026-10-01
    d, eff = next_notice_deadline(
        date(2026, 1, 1), 12, 12, 3, "months", "end_of_term", date(2026, 6, 15)
    )
    assert (d, eff) == (date(2026, 10, 1), date(2027, 1, 1))
    # deadline passed -> next renewal period
    d, _ = next_notice_deadline(
        date(2026, 1, 1), 12, 12, 3, "months", "end_of_term", date(2026, 11, 1)
    )
    assert d == date(2027, 10, 1)


def test_notice_deadline_end_of_month_reference():
    d, eff = next_notice_deadline(
        date(2026, 1, 10), 24, 12, 1, "months", "end_of_month", date(2026, 6, 1)
    )
    assert eff == date(2028, 1, 31) and d == date(2027, 12, 31)


def test_special_termination_pattern():
    even = monthly([-10, -10, -15])
    (s,) = detect_series(even, today=TODAY)
    assert special_termination_default(s) is True
    # amount, day and gap all vary -> usage-based billing
    messy = [
        txn("2026-01-03", -30),
        txn("2026-02-12", -45),
        txn("2026-03-27", -38),
    ]
    s2 = {
        "dates": [t["bookingDate"] for t in messy],
        "amounts": [-30, -45, -38],
    }
    assert special_termination_default(s2) is False


def test_build_contracts_sorted_and_flags(monkeypatch):
    store = ContractStore.__new__(ContractStore)
    store.contracts, store.notified = {}, set()
    rows = monthly([-10, -10, -10, -15], name="Strom AG", category="utilities") + monthly(
        [-9.99] * 4, name="Streamingdienst", category="subscriptions"
    )
    out = build_contracts(rows, store, today=TODAY)
    assert {c["creditor"] for c in out} == {"strom ag", "streamingdienst"}
    deadlines = [c["next_deadline"] for c in out]
    assert deadlines == sorted(deadlines)
    strom = next(c for c in out if c["creditor"] == "strom ag")
    assert strom["special_termination_available"] is True
    assert strom["contract"]["notice_unit"] == "months"
    store.contracts[strom["id"]] = Contract(strom["id"], special_termination=False)
    out = build_contracts(rows, store, today=TODAY)
    assert next(c for c in out if c["id"] == strom["id"])["special_termination_available"] is False


def test_contract_validation():
    c = Contract("s_x")
    c.apply({"min_term_months": 12, "notice_unit": "weeks", "start": "2026-01-01"})
    assert c.min_term_months == 12
    for bad in (
        {"notice_unit": "years"},
        {"start": "nope"},
        {"min_term_months": -1},
        {"min_term_months": True},
        {"plan_mode": "fixed"},
        {"bogus": 1},
        {"special_termination": "yes"},
    ):
        with pytest.raises(ContractError):
            Contract("s_x").apply(bad)


def test_reserves_from_irregular_series():
    store = ContractStore.__new__(ContractStore)
    store.contracts, store.notified = {}, set()
    rows = [
        txn("2025-03-01", -120, "Haftpflicht", "insurance"),
        txn("2026-03-01", -120, "Haftpflicht", "insurance"),
    ] + monthly([-10] * 4, name="Netflix")
    res = build_reserves(build_contracts(rows, store, today=TODAY))
    assert [i["creditor"] for i in res["items"]] == ["haftpflicht"]
    assert res["items"][0]["monthly_reserve"] == 10.0
    assert res["total_monthly"] == 10.0


def test_pot_coverage():
    acc = {"id": "u1", "iban": "DE89370400440532013000", "name": "Spar", "savings": True}
    key = account_key(acc)
    pots = [
        Pot(id="a", name="Urlaub", cycle_budget=300, kind="reserve", account_key=key),
        Pot(id="b", name="Auto", cycle_budget=200, kind="reserve", account_key=key),
        Pot(id="c", name="Food", cycle_budget=400, kind="spend", account_key=key),
        Pot(id="d", name="Orphan", cycle_budget=50, kind="reserve"),
    ]

    def bal(amount):
        return {"u1": {"balances": [{"balanceType": "closingBooked", "balanceAmount": {"amount": amount}}]}}

    short = pot_coverage(pots, [acc], bal("420.00"))
    row = short["accounts"][0]
    assert row["virtual_total"] == 500.0 and row["status"] == "shortfall"
    assert row["top_up"] == 80.0 and short["unassigned_pots"] == 1 and row["savings"]
    ok = pot_coverage(pots, [acc], bal("500.00"))
    assert ok["status"] == "covered" and ok["total_top_up"] == 0.0
    assert pot_coverage(pots, [acc], {})["accounts"][0]["status"] == "unknown"


def test_pot_account_key_roundtrip():
    p = Pot.from_dict({"name": "X", "kind": "reserve", "account_key": " k1 "})
    assert Pot.from_dict(p.to_dict()).account_key == "k1"


async def test_notice_due_event_fires_once(monkeypatch):
    from custom_components.finance_dashboard import contracts as mod

    store = ContractStore.__new__(ContractStore)
    store.contracts, store.notified = {}, set()

    async def _noop():
        return None

    store.async_save = _noop

    async def _get(_hass):
        return store

    monkeypatch.setattr(mod, "async_get_store", _get)
    fired = []

    class Bus:
        def async_fire(self, event, data):
            fired.append((event, data))

    hass = type("H", (), {"bus": Bus()})()
    rows = monthly([-30] * 4, name="Versicherung", category="insurance", start=date(2026, 3, 10))
    from custom_components.finance_dashboard.recurring import series_id

    sid = series_id("versicherung", True)
    store.contracts[sid] = Contract(sid, start="2025-10-01")
    today = date(2026, 6, 20)
    n = await mod.async_fire_notice_due(hass, rows, today=today)
    assert n == 1 and fired[0][0] == "finance_dashboard_notice_due"
    assert "amount" not in fired[0][1]
    assert await mod.async_fire_notice_due(hass, rows, today=today) == 0
