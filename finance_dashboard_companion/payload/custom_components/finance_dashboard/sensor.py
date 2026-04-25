"""Sensor platform for Finance.

Creates sensor entities for:
- Account balances (one per linked bank account, with bank logo)
- Total balance (optional, aggregated across all accounts)
- Monthly summary (income, expenses, category breakdown)

All entities read from the shared DataUpdateCoordinator — no entity
ever calls the banking API directly.  This prevents rate-limit
exhaustion that occurred when HA polled each entity every 30 seconds.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FinanceDashboardCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Finance sensors from a config entry."""
    coordinator: FinanceDashboardCoordinator = hass.data[DOMAIN].get(
        f"{entry.entry_id}_coordinator"
    )
    accounts = entry.data.get("accounts", [])

    entities: list[SensorEntity] = []

    for account in accounts:
        entities.append(AccountBalanceSensor(coordinator, entry, account))

    if entry.options.get("enable_total_balance_sensor", False):
        entities.append(TotalBalanceSensor(coordinator, entry, accounts))

    entities.append(MonthlySummarySensor(coordinator, entry))

    # update_before_add=False: coordinator drives the first refresh
    async_add_entities(entities, update_before_add=False)


class AccountBalanceSensor(CoordinatorEntity[FinanceDashboardCoordinator], SensorEntity):
    """Sensor for a single bank account balance.

    State = latest closing/available balance (EUR or account currency).
    Data comes from coordinator — no direct API calls.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FinanceDashboardCoordinator,
        entry: ConfigEntry,
        account: dict[str, Any],
    ) -> None:
        """Initialise the account balance sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._account = account
        self._account_id = account["id"]

        custom_name = account.get("custom_name", "")
        name = custom_name or account.get("name", "Account")
        institution = account.get("institution", "")
        iban = account.get("iban", "")
        iban_masked = f"****{iban[-4:]}" if len(iban) >= 4 else ""

        self._attr_name = f"{institution} {name}"
        self._attr_unique_id = f"{DOMAIN}_{self._account_id}_balance"
        self._attr_native_unit_of_measurement = account.get("currency", "EUR")
        self._attr_suggested_display_precision = 2
        self._iban_masked = iban_masked
        self._institution = institution

        logo = account.get("logo", "")
        if logo:
            self._attr_entity_picture = logo

        ha_users = account.get("ha_users", [])
        ha_user_names = [u.get("name", "") for u in ha_users]
        self._base_attrs = {
            "iban_masked": iban_masked,
            "institution": institution,
            "account_type": account.get("type", "personal"),
            "person": account.get("person", ""),
            "ha_users": ha_user_names,
            "custom_name": custom_name,
            "currency": account.get("currency", "EUR"),
        }

    @property
    def native_value(self) -> float | None:
        """Return the latest balance from coordinator data."""
        raw = self._raw_balances()
        if not raw:
            return None
        balance = self._pick_balance(raw)
        if balance:
            return float(balance.get("balanceAmount", {}).get("amount", 0))
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extended attributes including balance type and date."""
        attrs = dict(self._base_attrs)
        raw = self._raw_balances()
        if raw:
            balance = self._pick_balance(raw)
            if balance:
                attrs["balance_type"] = balance.get("balanceType", "unknown")
                attrs["reference_date"] = balance.get("referenceDate", "")
        return attrs

    def _raw_balances(self) -> list[dict[str, Any]]:
        """Extract the raw balance list for this account from coordinator data."""
        if not self.coordinator.data:
            return []
        acc_data = self.coordinator.data.get("balances", {}).get(self._account_id, {})
        return acc_data.get("balances", [])

    @staticmethod
    def _pick_balance(balances: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Pick the most useful balance type."""
        priority = [
            "closingBooked",
            "interimAvailable",
            "interimBooked",
            "closingAvailable",
        ]
        by_type = {b["balanceType"]: b for b in balances}
        for bt in priority:
            if bt in by_type:
                return by_type[bt]
        return balances[0] if balances else None


class TotalBalanceSensor(CoordinatorEntity[FinanceDashboardCoordinator], SensorEntity):
    """Aggregated balance across all linked accounts."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_has_entity_name = True
    _attr_name = "Total Balance"
    _attr_icon = "mdi:sigma"

    def __init__(
        self,
        coordinator: FinanceDashboardCoordinator,
        entry: ConfigEntry,
        accounts: list[dict[str, Any]],
    ) -> None:
        """Initialise the total balance sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._accounts = accounts
        self._attr_unique_id = f"{DOMAIN}_total_balance"
        self._attr_native_unit_of_measurement = entry.options.get("currency", "EUR")
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Sum balances from coordinator data (no API call)."""
        if not self.coordinator.data:
            return None
        balances_data = self.coordinator.data.get("balances", {})
        total = 0.0
        for account in self._accounts:
            acc_id = account["id"]
            raw = balances_data.get(acc_id, {}).get("balances", [])
            if raw:
                balance = AccountBalanceSensor._pick_balance(raw)
                if balance:
                    total += float(balance.get("balanceAmount", {}).get("amount", 0))
        return total

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Per-account breakdown."""
        if not self.coordinator.data:
            return {}
        balances_data = self.coordinator.data.get("balances", {})
        per_account: dict[str, float] = {}
        for account in self._accounts:
            acc_id = account["id"]
            iban = account.get("iban", "")
            masked = f"****{iban[-4:]}" if len(iban) >= 4 else "?"
            raw = balances_data.get(acc_id, {}).get("balances", [])
            if raw:
                balance = AccountBalanceSensor._pick_balance(raw)
                if balance:
                    per_account[masked] = float(balance.get("balanceAmount", {}).get("amount", 0))
        return {
            "accounts": per_account,
            "account_count": len(self._accounts),
        }


class MonthlySummarySensor(CoordinatorEntity[FinanceDashboardCoordinator], SensorEntity):
    """Monthly spending summary with category breakdown."""

    _attr_has_entity_name = True
    _attr_name = "Monthly Summary"
    _attr_icon = "mdi:chart-bar"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: FinanceDashboardCoordinator, entry: ConfigEntry) -> None:
        """Initialise the monthly summary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_monthly_summary"
        self._attr_native_unit_of_measurement = entry.options.get("currency", "EUR")
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return current-month balance (income - expenses)."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("summary", {}).get("balance", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full summary breakdown."""
        if not self.coordinator.data:
            return {}
        summary = self.coordinator.data.get("summary", {})
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
        }
