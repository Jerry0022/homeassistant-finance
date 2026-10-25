"""Sensor platform for Finance.

Entities (all read the shared coordinator / manager cache — never the bank):

* per account: balance, available balance (only if the bank reports one),
  last update (diagnostic)
* per bank: consent valid until, consent state, fetch budget used today,
  blocked until, last error (the last four diagnostic)
* main device: total balance (optional) and the monthly summary
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .account_identity import account_key, balance_unique_id
from .balances import amount_of, pick_available, pick_balance
from .const import BANK_ERROR_OPTIONS, CONSENT_STATES, DOMAIN
from .coordinator import FinanceDashboardCoordinator
from .entity import (
    FinanceMainEntity,
    account_device_info,
    async_bank_layout,
    bank_device_info,
)
from .runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

# Cache-only platform: no entity ever talks to the bank.
PARALLEL_UPDATES = 0


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def classify_error(error: str | None) -> str:
    """Map the budget's class-level error text onto a translatable code."""
    if not error:
        return "none"
    text = str(error)
    if text in ("consent_expired", "rate_limited"):
        return text
    if text in ("http_401", "http_403"):
        return "unauthorized"
    if text.startswith("http_5"):
        return "server_error"
    lowered = text.lower()
    if any(m in lowered for m in ("timeout", "connect", "client", "network", "dns")):
        return "network"
    return "other"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Finance sensors from a config entry."""
    runtime = get_runtime(entry)
    coordinator: FinanceDashboardCoordinator = runtime.coordinator
    manager = runtime.manager
    accounts = entry.data.get("accounts", [])

    # Bank entities first: account devices reference the bank device (via_device).
    known_available: set[str] = set()
    pending_available: list[tuple[Any, dict[str, Any], str]] = []

    for bank in await async_bank_layout(manager, entry):
        entities: list[SensorEntity] = [
            BankConsentValidUntilSensor(coordinator, bank.bank_id, bank.title),
            BankConsentStateSensor(coordinator, bank.bank_id, bank.title),
            BankBudgetUsedSensor(coordinator, bank.bank_id, bank.title),
            BankBlockedUntilSensor(coordinator, bank.bank_id, bank.title),
            BankLastErrorSensor(coordinator, bank.bank_id, bank.title),
        ]
        for account in bank.accounts:
            entities.append(
                AccountBalanceSensor(coordinator, entry, account, bank.bank_id, bank.title)
            )
            entities.append(AccountLastUpdateSensor(coordinator, account, bank.bank_id, bank.title))
            if _provides_available(coordinator, account):
                known_available.add(account_key(account))
                entities.append(
                    AccountAvailableBalanceSensor(coordinator, account, bank.bank_id, bank.title)
                )
            else:
                pending_available.append((bank, account, bank.title))
        _add(async_add_entities, entities, bank.subentry_id)

    main: list[SensorEntity] = []
    if entry.options.get("enable_total_balance_sensor", False):
        main.append(TotalBalanceSensor(coordinator, entry, accounts))
    main.append(MonthlySummarySensor(coordinator, entry))
    async_add_entities(main, update_before_add=False)

    if pending_available:
        # A bank may only reveal an available balance on a later fetch.
        def _add_when_reported() -> None:
            for item in list(pending_available):
                bank, account, title = item
                key = account_key(account)
                if key in known_available or not _provides_available(coordinator, account):
                    continue
                known_available.add(key)
                pending_available.remove(item)
                _add(
                    async_add_entities,
                    [AccountAvailableBalanceSensor(coordinator, account, bank.bank_id, title)],
                    bank.subentry_id,
                )

        entry.async_on_unload(coordinator.async_add_listener(_add_when_reported))


def _add(async_add_entities: AddEntitiesCallback, entities: list, subentry_id: str | None) -> None:
    if subentry_id:
        async_add_entities(entities, update_before_add=False, config_subentry_id=subentry_id)
    else:
        async_add_entities(entities, update_before_add=False)


def _raw_balances(
    coordinator: FinanceDashboardCoordinator, account_uid: str
) -> list[dict[str, Any]]:
    if not coordinator.data:
        return []
    return (coordinator.data.get("balances", {}).get(account_uid) or {}).get("balances", [])


def _provides_available(coordinator: FinanceDashboardCoordinator, account: dict[str, Any]) -> bool:
    return pick_available(_raw_balances(coordinator, account["id"])) is not None


# ---------------------------------------------------------------------------
# Account sensors
# ---------------------------------------------------------------------------


class _AccountEntity(CoordinatorEntity[FinanceDashboardCoordinator], SensorEntity):
    """Base for entities on an account device."""

    _attr_has_entity_name = True
    _suffix = ""

    def __init__(
        self,
        coordinator: FinanceDashboardCoordinator,
        account: dict[str, Any],
        bank_id: str | None,
        bank_title: str,
    ) -> None:
        super().__init__(coordinator)
        self._account = account
        self._account_id = account["id"]
        self._key = account_key(account)
        self._attr_device_info = account_device_info(account, bank_id, bank_title)
        self._attr_unique_id = f"{DOMAIN}_{self._key}{self._suffix}"
        self._currency = account.get("currency", "EUR")

    def _balances(self) -> list[dict[str, Any]]:
        return _raw_balances(self.coordinator, self._account_id)


class AccountBalanceSensor(_AccountEntity):
    """Booked balance of one account (ISO currency, TOTAL state class)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_translation_key = "balance"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: FinanceDashboardCoordinator,
        entry: ConfigEntry,
        account: dict[str, Any],
        bank_id: str | None = None,
        bank_title: str = "",
    ) -> None:
        super().__init__(coordinator, account, bank_id, bank_title)
        self._entry = entry
        # Identity is the account, not the Enable Banking session uid — the
        # uid changes on every re-link and used to spawn duplicate entities.
        self._attr_unique_id = balance_unique_id(DOMAIN, account)
        self._attr_native_unit_of_measurement = self._currency

        iban = account.get("iban", "")
        iban_masked = f"****{iban[-4:]}" if len(iban) >= 4 else ""
        self._base_attrs = {
            "iban_masked": iban_masked,
            "institution": account.get("institution", ""),
            "account_type": account.get("type", "personal"),
            "person": account.get("person", ""),
            "ha_users": [u.get("name", "") for u in account.get("ha_users", [])],
            "custom_name": account.get("custom_name", ""),
            "currency": self._currency,
        }
        logo = account.get("logo", "")
        if logo:
            self._attr_entity_picture = logo

    @property
    def available(self) -> bool:
        return super().available and pick_balance(self._balances()) is not None

    @property
    def native_value(self) -> float | None:
        return amount_of(pick_balance(self._balances()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(self._base_attrs)
        balance = pick_balance(self._balances())
        if balance:
            attrs["balance_type"] = balance.get("balanceType", "unknown")
            attrs["reference_date"] = balance.get("referenceDate", "")
        return attrs

    @staticmethod
    def _pick_balance(balances: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Kept for callers/tests; see :func:`balances.pick_balance`."""
        return pick_balance(balances)


class AccountAvailableBalanceSensor(_AccountEntity):
    """Available balance — only exists for banks that report one."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_translation_key = "available_balance"
    _attr_suggested_display_precision = 2
    _suffix = "_available_balance"

    def __init__(self, coordinator, account, bank_id=None, bank_title="") -> None:
        super().__init__(coordinator, account, bank_id, bank_title)
        self._attr_native_unit_of_measurement = self._currency

    @property
    def available(self) -> bool:
        return super().available and pick_available(self._balances()) is not None

    @property
    def native_value(self) -> float | None:
        return amount_of(pick_available(self._balances()))


class AccountLastUpdateSensor(_AccountEntity):
    """When the bank last delivered a balance for this account."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_update"
    _suffix = "_last_update"

    @property
    def _latest(self) -> datetime | None:
        manager = self.coordinator.manager
        points = manager.get_balance_history(self._key)
        stamps = [d for d in (_parse_dt(p.get("at")) for p in points) if d]
        return max(stamps) if stamps else None

    @property
    def available(self) -> bool:
        return super().available and self._latest is not None

    @property
    def native_value(self) -> datetime | None:
        return self._latest


# ---------------------------------------------------------------------------
# Bank sensors
# ---------------------------------------------------------------------------


class _BankEntity(CoordinatorEntity[FinanceDashboardCoordinator], SensorEntity):
    """Base for entities on a bank device."""

    _attr_has_entity_name = True
    _suffix = ""

    def __init__(self, coordinator: FinanceDashboardCoordinator, bank_id: str, title: str) -> None:
        super().__init__(coordinator)
        self._bank_id = bank_id
        self._attr_device_info = bank_device_info(bank_id, title)
        self._attr_unique_id = f"{DOMAIN}_bank_{bank_id}{self._suffix}"

    def _status(self) -> dict[str, Any] | None:
        for status in self.coordinator.manager.get_bank_status():
            if status.get("bank_id") == self._bank_id:
                return status
        return None

    @property
    def available(self) -> bool:
        return super().available and self._status() is not None


class BankConsentValidUntilSensor(_BankEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "consent_valid_until"
    _suffix = "_consent_valid_until"

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> datetime | None:
        status = self._status()
        return _parse_dt(status.get("consent_valid_until")) if status else None


class BankConsentStateSensor(_BankEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(CONSENT_STATES)
    _attr_translation_key = "consent_state"
    _suffix = "_consent_state"

    @property
    def native_value(self) -> str | None:
        status = self._status()
        state = status.get("consent_state") if status else None
        return state if state in CONSENT_STATES else None


class BankBudgetUsedSensor(_BankEntity):
    """Background fetches spent today (the bank allows 4)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "budget_used"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _suffix = "_budget_used"

    @property
    def native_value(self) -> int | None:
        status = self._status()
        return status.get("budget_used_today") if status else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self._status() or {}
        return {"limit": status.get("budget_limit")}


class BankBlockedUntilSensor(_BankEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "blocked_until"
    _suffix = "_blocked_until"

    @property
    def native_value(self) -> datetime | None:
        status = self._status()
        return _parse_dt(status.get("blocked_until")) if status else None


class BankLastErrorSensor(_BankEntity):
    """Class of the last failure, translated; never a bank payload."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(BANK_ERROR_OPTIONS)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_error"
    _suffix = "_last_error"

    @property
    def native_value(self) -> str | None:
        status = self._status()
        return classify_error(status.get("last_error")) if status else None


# ---------------------------------------------------------------------------
# Main-device sensors
# ---------------------------------------------------------------------------


class TotalBalanceSensor(FinanceMainEntity, SensorEntity):
    """Aggregated balance across all linked accounts."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_translation_key = "total_balance"

    def __init__(
        self,
        coordinator: FinanceDashboardCoordinator,
        entry: ConfigEntry,
        accounts: list[dict[str, Any]],
    ) -> None:
        super().__init__(coordinator, entry)
        self._accounts = accounts
        self._attr_unique_id = f"{DOMAIN}_total_balance"
        self._attr_native_unit_of_measurement = entry.options.get("currency", "EUR")
        self._attr_suggested_display_precision = 2

    def _amounts(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for account in self._accounts:
            iban = account.get("iban", "")
            masked = f"****{iban[-4:]}" if len(iban) >= 4 else "?"
            amount = amount_of(pick_balance(_raw_balances(self.coordinator, account["id"])))
            if amount is not None:
                out[masked] = amount
        return out

    @property
    def available(self) -> bool:
        return super().available and bool(self._amounts())

    @property
    def native_value(self) -> float | None:
        amounts = self._amounts()
        return sum(amounts.values()) if amounts else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"accounts": self._amounts(), "account_count": len(self._accounts)}


class MonthlySummarySensor(FinanceMainEntity, SensorEntity):
    """Monthly spending summary with category breakdown."""

    _attr_translation_key = "monthly_summary"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: FinanceDashboardCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_monthly_summary"
        self._attr_native_unit_of_measurement = entry.options.get("currency", "EUR")
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Current-month balance (income - expenses)."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("summary", {}).get("balance", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Full summary plus refresh status (durable across page reloads)."""
        if not self.coordinator.data:
            return {}
        summary = self.coordinator.data.get("summary", {})
        status = self.coordinator.data.get("refresh_status", {}) or {}
        return {
            "total_income": summary.get("total_income", 0),
            "total_expenses": summary.get("total_expenses", 0),
            "categories": summary.get("categories", {}),
            "transaction_count": summary.get("transaction_count", 0),
            "month": summary.get("month", 0),
            "year": summary.get("year", 0),
            "fixed_costs": summary.get("fixed_costs", 0),
            "variable_costs": summary.get("variable_costs", 0),
            "household": summary.get("household"),
            "recurring": summary.get("recurring", []),
            "last_refresh": summary.get("last_refresh"),
            "rate_limited_until": summary.get("rate_limited_until"),
            "last_refresh_stats": status.get("stats", {}),
            "is_refreshing": status.get("is_refreshing", False),
            "cache_age_seconds": status.get("cache_age_seconds"),
            "cache_is_stale": status.get("cache_is_stale", False),
            "demo_mode": status.get("demo_mode", False),
        }
