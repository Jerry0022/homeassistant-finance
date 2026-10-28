"""Persons & accounts assignments: endpoint gating, validation, persistence, resolve."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.finance_dashboard.account_identity import account_key
from custom_components.finance_dashboard.budget_plan import BudgetPlan
from custom_components.finance_dashboard.home import resolve_person, setup_block
from custom_components.finance_dashboard.manager import (
    AssignmentError,
    FinanceDashboardManager,
)

ACCS = [
    {"id": "s1", "iban": "DE00 0000 0000 0000 0001 23", "institution": "FakeBank", "name": "Giro"},
    {"id": "s2", "iban": "DE00 0000 0000 0000 0004 56", "institution": "FakeBank",
     "custom_name": "Joint"},
]
USERS = [
    SimpleNamespace(id="u1", name="Anna", is_admin=True, is_active=True, system_generated=False),
    SimpleNamespace(id="u2", name="Max", is_admin=False, is_active=True, system_generated=False),
    SimpleNamespace(id="u3", name="Sys", is_admin=False, is_active=True, system_generated=True),
    SimpleNamespace(id="u4", name="Old", is_admin=False, is_active=False, system_generated=False),
]


def _mgr(persons=None, demo=False):
    data = {"accounts": [dict(a) for a in ACCS]}
    if persons is not None:
        data["persons"] = persons
    entry = SimpleNamespace(data=data)
    hass = MagicMock()

    def _update(e, data):
        e.data = data

    hass.config_entries.async_update_entry.side_effect = _update
    mgr = SimpleNamespace(
        _entry=entry, _hass=hass, _demo_mode=demo, _accounts=entry.data["accounts"],
        budget_plan=BudgetPlan(persons=["Anna", "Max"]),
    )
    mgr.persons = FinanceDashboardManager.persons.fget(mgr)
    return mgr


def _set(mgr, body):
    FinanceDashboardManager.async_set_assignments(mgr, body, USERS)


def test_get_flags_users_and_masks_iban() -> None:
    mgr = _mgr([{"name": "Anna", "ha_users": ["u1"]}])
    out = FinanceDashboardManager.get_assignments(mgr, USERS)
    reasons = {u["id"]: (u["suggested"], u["reason"]) for u in out["ha_users"]}
    assert reasons == {
        "u1": (True, "person"), "u2": (True, "active_user"),
        "u3": (False, "system"), "u4": (False, "inactive"),
    }
    assert [a["iban_last4"] for a in out["accounts"]] == ["0123", "0456"]
    assert out["accounts"][1]["name"] == "Joint"
    assert out["plan_persons"] == ["Anna", "Max"]
    assert "DE00" not in str(out)


def test_put_persists_and_updates_memory() -> None:
    mgr = _mgr()
    k0, k1 = account_key(ACCS[0]), account_key(ACCS[1])
    _set(mgr, {
        "persons": [{"name": " Anna ", "ha_users": ["u1"]}, {"name": "Max", "ha_users": []}],
        "accounts": [{"key": k0, "owner": "Anna"}, {"key": k1, "owner": "shared"}],
    })
    saved = mgr._entry.data
    assert saved["persons"][0] == {"name": "Anna", "ha_users": ["u1"]}
    a0, a1 = saved["accounts"]
    assert (a0["type"], a0["person"], a0["ha_users"]) == ("personal", "Anna", ["u1"])
    assert (a1["type"], a1["person"]) == ("shared", "")
    assert mgr._accounts is saved["accounts"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"persons": [{"name": " "}], "accounts": []}, "invalid_person_name"),
        ({"persons": [{"name": "x" * 41}], "accounts": []}, "invalid_person_name"),
        ({"persons": [{"name": "A"}, {"name": "a"}], "accounts": []}, "duplicate_person"),
        ({"persons": [{"name": "A", "ha_users": ["nope"]}], "accounts": []}, "unknown_ha_user"),
        ({"persons": [{"name": "A", "ha_users": ["u1"]}, {"name": "B", "ha_users": ["u1"]}],
          "accounts": []}, "ha_user_reused"),
        ({"persons": [], "accounts": [{"key": "zzz", "owner": ""}]}, "unknown_account"),
        ({"persons": [], "accounts": [{"key": account_key(ACCS[0]), "owner": "Ghost"}]},
         "unknown_owner"),
        ({"persons": "x", "accounts": []}, "invalid_body"),
    ],
)
def test_put_validation(body, code) -> None:
    mgr = _mgr()
    with pytest.raises(AssignmentError) as exc:
        _set(mgr, body)
    assert exc.value.code == code
    mgr._hass.config_entries.async_update_entry.assert_not_called()


def test_resolve_person_via_persons_without_accounts() -> None:
    user = SimpleNamespace(id="u2", name="whatever")
    assert resolve_person(user, [], [{"name": "Max", "ha_users": ["u2"]}]) == "Max"
    assert resolve_person(user, [], []) is None
    legacy = [{"type": "personal", "person": "Anna", "ha_users": ["u2"]}]
    assert resolve_person(user, legacy, []) == "Anna"


def test_setup_block_counts() -> None:
    accs = [{"type": "personal", "person": "Anna"}, {"type": "shared"}, {"type": "personal"}]
    out = setup_block(accs, [{"name": "Max", "ha_users": []}], 3, user_mapped=True)
    assert out == {"persons": 2, "user_mapped": True, "accounts_total": 3,
                   "accounts_assigned": 2, "pots": 3}


def test_demo_home_has_setup() -> None:
    from custom_components.finance_dashboard.demo import generate_demo_home

    out = generate_demo_home(person="Anna", view="household", horizon="cycle")
    assert out["setup"]["persons"] == 2 and out["setup"]["user_mapped"] is True


@pytest.mark.asyncio
async def test_view_requires_admin_and_returns_payload() -> None:
    from custom_components.finance_dashboard.api.assignments import (
        FinanceDashboardAssignmentsView,
    )

    class _J:
        def json(self, data, status_code=200):
            return SimpleNamespace(_data=data, _status=status_code)

    view = FinanceDashboardAssignmentsView()
    view.json = _J().json

    def _req(admin, body=None):
        req = MagicMock()
        user = SimpleNamespace(is_admin=admin)
        req.get.side_effect = lambda k, d=None: user if k == "hass_user" else d
        hass = MagicMock()
        hass.auth.async_get_users = AsyncMock(return_value=USERS)
        req.app = {"hass": hass}
        req.json = AsyncMock(return_value=body)
        return req

    resp = await view.get(_req(False))
    assert (resp._status, resp._data["error"]) == (403, "admin_required")
    resp = await view.put(_req(False, {}))
    assert resp._status == 403

    mgr = _mgr()
    mgr.get_assignments = lambda users: FinanceDashboardManager.get_assignments(mgr, users)
    mgr.async_set_assignments = lambda d, u: FinanceDashboardManager.async_set_assignments(
        mgr, d, u
    )
    target = "custom_components.finance_dashboard.api.assignments._get_manager"
    with patch(target, return_value=mgr):
        resp = await view.get(_req(True))
        assert resp._status == 200 and len(resp._data["accounts"]) == 2
        resp = await view.put(_req(True, {"persons": [{"name": ""}], "accounts": []}))
        assert resp._status == 400 and resp._data["error"] == "invalid_person_name"
