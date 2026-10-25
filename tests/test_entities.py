"""Entity layer: unique_id stability, device tree, availability, button, setup.

Runs against fakes (no hass, no config subentries) so it works on HA 2025.1.
Real registry behaviour (config_subentry_id grouping, removal cascade) needs
HA >= 2026.3 and is listed in the hand-off notes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.finance_dashboard import sensor as sensor_mod
from custom_components.finance_dashboard.account_identity import account_key
from custom_components.finance_dashboard.const import DOMAIN

ACCOUNT = {
    "id": "uid-session-1",
    "iban": "DE89370400440532013000",
    "name": "Giro",
    "institution": "Testbank",
    "currency": "EUR",
    "type": "personal",
}
BANK_ID = "01SUBENTRY"


class FakeManager:
    demo_mode = False

    def __init__(self, balances=True, status=True, available=False):
        self._accounts = [ACCOUNT]
        self.status = status
        self.refresh_calls: list[tuple] = []
        self.history = [
            {"at": "2026-05-01T08:15:00+00:00", "type": "CLBD", "amount": "10.5", "currency": "EUR"}
        ]

    def get_bank_status(self):
        if not self.status:
            return []
        return [
            {
                "bank_id": BANK_ID,
                "title": "Testbank",
                "budget_used_today": 2,
                "budget_limit": 4,
                "blocked_until": None,
                "last_success": "2026-05-01T08:15:00+00:00",
                "last_error": "http_401",
                "consent_valid_until": "2026-09-01T00:00:00+00:00",
                "consent_state": "ok",
            }
        ]

    def get_balance_history(self, key):
        return list(self.history)

    async def _async_bank_targets(self):
        return [{"bank_id": BANK_ID, "title": "Testbank", "accounts": [ACCOUNT], "valid_until": None}]

    async def async_refresh_transactions(self, *args, **kwargs):
        self.refresh_calls.append((args, kwargs))
        return []


class FakeCoordinator:
    last_update_success = True

    def __init__(self, manager, balances=None):
        self.manager = manager
        self.data = (
            {
                "balances": {
                    ACCOUNT["id"]: {
                        "balances": balances
                        or [{"balanceType": "CLBD", "balanceAmount": {"amount": "10.50"}}]
                    }
                },
                "summary": {},
            }
            if balances != "none"
            else None
        )
        self.listeners: list = []
        self.refreshed = 0

    def async_add_listener(self, cb, context=None):
        self.listeners.append(cb)
        return lambda: self.listeners.remove(cb)

    async def async_refresh(self):
        self.refreshed += 1


class FakeEntry:
    entry_id = "entry1"
    options: dict = {}  # noqa: RUF012
    data = {"accounts": [ACCOUNT]}  # noqa: RUF012
    subentries: dict = {}  # noqa: RUF012

    def __init__(self, manager, coordinator):
        from custom_components.finance_dashboard.runtime import FinanceDashboardData

        self.runtime_data = FinanceDashboardData(manager=manager, coordinator=coordinator)
        self.unloaders: list = []

    def async_on_unload(self, fn):
        self.unloaders.append(fn)


def _coord(**kw):
    return FakeCoordinator(FakeManager(), **kw)


# -- unique ids -------------------------------------------------------------


def test_balance_unique_id_is_unchanged():
    """The balance sensor id must stay what earlier versions registered."""
    entry = FakeEntry(FakeManager(), _coord())
    ent = sensor_mod.AccountBalanceSensor(entry.runtime_data.coordinator, entry, ACCOUNT, BANK_ID, "Testbank")
    assert ent.unique_id == f"{DOMAIN}_{account_key(ACCOUNT)}_balance"


def test_unique_id_schemes():
    c = _coord()
    key = account_key(ACCOUNT)
    assert sensor_mod.AccountAvailableBalanceSensor(c, ACCOUNT, BANK_ID, "T").unique_id == (
        f"{DOMAIN}_{key}_available_balance"
    )
    assert sensor_mod.AccountLastUpdateSensor(c, ACCOUNT, BANK_ID, "T").unique_id == (
        f"{DOMAIN}_{key}_last_update"
    )
    assert sensor_mod.BankConsentStateSensor(c, BANK_ID, "T").unique_id == (
        f"{DOMAIN}_bank_{BANK_ID}_consent_state"
    )
    assert sensor_mod.BankBudgetUsedSensor(c, BANK_ID, "T").unique_id == (
        f"{DOMAIN}_bank_{BANK_ID}_budget_used"
    )


def test_unique_id_survives_relink():
    """A new session uid must not change the entity identity."""
    relinked = {**ACCOUNT, "id": "uid-session-2"}
    c = _coord()
    a = sensor_mod.AccountLastUpdateSensor(c, ACCOUNT, BANK_ID, "T")
    b = sensor_mod.AccountLastUpdateSensor(c, relinked, BANK_ID, "T")
    assert a.unique_id == b.unique_id


# -- devices ------------------------------------------------------------------


def test_account_device_hangs_under_bank_device():
    c = _coord()
    acct = sensor_mod.AccountBalanceSensor(c, FakeEntry(c.manager, c), ACCOUNT, BANK_ID, "Testbank")
    bank = sensor_mod.BankConsentStateSensor(c, BANK_ID, "Testbank")
    assert (DOMAIN, f"account_{account_key(ACCOUNT)}") in acct.device_info["identifiers"]
    assert acct.device_info["via_device"] == (DOMAIN, f"bank_{BANK_ID}")
    assert bank.device_info["identifiers"] == {(DOMAIN, f"bank_{BANK_ID}")}
    assert bank.device_info["manufacturer"] == "Testbank"
    assert str(bank.device_info["entry_type"]) .endswith("service")


def test_aggregates_live_on_main_device():
    c = _coord()
    entry = FakeEntry(c.manager, c)
    total = sensor_mod.TotalBalanceSensor(c, entry, [ACCOUNT])
    summary = sensor_mod.MonthlySummarySensor(c, entry)
    assert total.device_info["identifiers"] == {(DOMAIN, "main_entry1")}
    assert summary.device_info == total.device_info


def test_entities_have_translation_keys_and_entity_names():
    c = _coord()
    entry = FakeEntry(c.manager, c)
    ents = [
        sensor_mod.AccountBalanceSensor(c, entry, ACCOUNT, BANK_ID, "T"),
        sensor_mod.BankLastErrorSensor(c, BANK_ID, "T"),
        sensor_mod.MonthlySummarySensor(c, entry),
    ]
    for ent in ents:
        assert ent.has_entity_name is True
        assert ent.translation_key


# -- availability and values --------------------------------------------------


def test_balance_unavailable_without_data():
    c = _coord(balances="none")
    ent = sensor_mod.AccountBalanceSensor(c, FakeEntry(c.manager, c), ACCOUNT, BANK_ID, "T")
    assert ent.available is False
    c2 = _coord()
    ent2 = sensor_mod.AccountBalanceSensor(c2, FakeEntry(c2.manager, c2), ACCOUNT, BANK_ID, "T")
    assert ent2.available is True
    assert ent2.native_value == 10.5
    assert ent2.native_unit_of_measurement == "EUR"


def test_available_balance_only_from_available_types():
    only_booked = _coord()
    ent = sensor_mod.AccountAvailableBalanceSensor(only_booked, ACCOUNT, BANK_ID, "T")
    assert ent.available is False
    both = _coord(
        balances=[
            {"balanceType": "CLBD", "balanceAmount": {"amount": "10"}},
            {"balanceType": "ITAV", "balanceAmount": {"amount": "250.25"}},
        ]
    )
    ent = sensor_mod.AccountAvailableBalanceSensor(both, ACCOUNT, BANK_ID, "T")
    assert ent.available is True
    assert ent.native_value == 250.25


def test_bank_entities_unavailable_when_bank_unknown():
    c = FakeCoordinator(FakeManager(status=False))
    for cls in (sensor_mod.BankConsentStateSensor, sensor_mod.BankLastErrorSensor):
        assert cls(c, BANK_ID, "T").available is False


def test_bank_sensor_values():
    c = _coord()
    assert sensor_mod.BankBudgetUsedSensor(c, BANK_ID, "T").native_value == 2
    assert sensor_mod.BankBudgetUsedSensor(c, BANK_ID, "T").extra_state_attributes == {"limit": 4}
    assert sensor_mod.BankConsentStateSensor(c, BANK_ID, "T").native_value == "ok"
    assert sensor_mod.BankLastErrorSensor(c, BANK_ID, "T").native_value == "unauthorized"
    assert sensor_mod.BankBlockedUntilSensor(c, BANK_ID, "T").native_value is None
    valid = sensor_mod.BankConsentValidUntilSensor(c, BANK_ID, "T").native_value
    assert valid == datetime(2026, 9, 1, tzinfo=UTC)
    last = sensor_mod.AccountLastUpdateSensor(c, ACCOUNT, BANK_ID, "T")
    assert last.native_value == datetime(2026, 5, 1, 8, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "none"),
        ("consent_expired", "consent_expired"),
        ("rate_limited", "rate_limited"),
        ("http_403", "unauthorized"),
        ("http_503", "server_error"),
        ("ClientConnectorError", "network"),
        ("http_418", "other"),
    ],
)
def test_classify_error(raw, expected):
    assert sensor_mod.classify_error(raw) == expected
    from custom_components.finance_dashboard.const import BANK_ERROR_OPTIONS

    assert expected in BANK_ERROR_OPTIONS


# -- platform setup -----------------------------------------------------------


@pytest.mark.asyncio
async def test_sensor_setup_groups_under_bank_subentry():
    manager = FakeManager()
    coordinator = FakeCoordinator(manager)
    entry = FakeEntry(manager, coordinator)
    calls: list[tuple[list, str | None]] = []

    def add(entities, update_before_add=False, config_subentry_id=None):
        calls.append((list(entities), config_subentry_id))

    await sensor_mod.async_setup_entry(None, entry, add)

    bank_calls = [c for c in calls if c[1] == BANK_ID]
    assert len(bank_calls) == 1
    names = {type(e).__name__ for e in bank_calls[0][0]}
    assert {"BankConsentStateSensor", "AccountBalanceSensor", "AccountLastUpdateSensor"} <= names
    assert "AccountAvailableBalanceSensor" not in names  # bank reports none yet
    # banks first so the account devices' via_device exists
    assert type(bank_calls[0][0][0]).__name__.startswith("Bank")
    main_calls = [c for c in calls if c[1] is None]
    assert {type(e).__name__ for e in main_calls[0][0]} == {"MonthlySummarySensor"}

    # the bank starts reporting an available balance -> entity appears later
    coordinator.data["balances"][ACCOUNT["id"]]["balances"].append(
        {"balanceType": "ITAV", "balanceAmount": {"amount": "5"}}
    )
    for cb in list(coordinator.listeners):
        cb()
    assert any(
        type(e).__name__ == "AccountAvailableBalanceSensor" and sub == BANK_ID
        for ents, sub in calls
        for e in ents
    )


# -- button -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_button_is_background_without_psu_headers():
    from custom_components.finance_dashboard.button import RefreshButton

    manager = FakeManager()
    coordinator = FakeCoordinator(manager)
    button = RefreshButton(coordinator, FakeEntry(manager, coordinator))
    assert button.unique_id == f"{DOMAIN}_refresh"
    await button.async_press()
    assert manager.refresh_calls == [((), {})]  # no psu_ip, not scheduled
    assert coordinator.refreshed == 1


@pytest.mark.asyncio
async def test_refresh_button_refuses_in_demo_mode():
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.finance_dashboard.button import RefreshButton

    manager = FakeManager()
    manager.demo_mode = True
    coordinator = FakeCoordinator(manager)
    button = RefreshButton(coordinator, FakeEntry(manager, coordinator))
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    assert manager.refresh_calls == []


def test_cache_only_platforms_do_not_parallelise():
    from custom_components.finance_dashboard import button, number, select

    for mod in (sensor_mod, button, number, select):
        assert mod.PARALLEL_UPDATES == 0


def test_select_options_are_stable_slugs():
    from custom_components.finance_dashboard.select import REMAINDER_MODES, SPLIT_MODELS

    assert all(k == v for k, v in {**SPLIT_MODELS, **REMAINDER_MODES}.items())
    assert "pooled_equal" in SPLIT_MODELS


def test_number_has_translation_and_main_device():
    from custom_components.finance_dashboard.number import BudgetLimitNumber

    num = BudgetLimitNumber(FakeEntry(FakeManager(), _coord()), "housing")
    assert num.unique_id == f"{DOMAIN}_budget_housing"
    assert num.translation_key == "budget_limit"
    assert num.device_info["identifiers"] == {(DOMAIN, "main_entry1")}
