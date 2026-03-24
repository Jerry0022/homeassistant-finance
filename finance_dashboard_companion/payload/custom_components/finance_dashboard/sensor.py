"""Sensor platform for Finance Dashboard.

Creates sensor entities for:
- Account balances (one per linked bank account, with bank logo)
- Total balance (optional, aggregated across all accounts)
- Monthly summary (income, expenses, category breakdown)
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Finance Dashboard sensors from a config entry."""
    manager = hass.data[DOMAIN][entry.entry_id]
    accounts = entry.data.get("accounts", [])

    entities: list[SensorEntity] = []

    # One sensor per linked account
    for account in accounts:
        entities.append(
            AccountBalanceSensor(manager, entry, account)
        )

    # Optional aggregate total balance sensor
    if entry.options.get("enable_total_balance_sensor", False):
        entities.append(
            TotalBalanceSensor(manager, entry, accounts)
        )

    # Monthly summary sensor
    entities.append(MonthlySummarySensor(manager, entry))

    async_add_entities(entities, update_before_add=True)


class AccountBalanceSensor(SensorEntity):
    """Sensor for a single bank account balance."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_has_entity_name = True

    def __init__(
        self,
        manager,
        entry: ConfigEntry,
        account: dict[str, Any],
    ) -> None:
        """Initialize the account balance sensor."""
        self._manager = manager
        self._entry = entry
        self._account = account
        self._account_id = account["id"]

        # Build a readable name from account info
        name = account.get("name", "Account")
        institution = account.get("institution", "")
        iban = account.get("iban", "")
        iban_masked = (
            f"****{iban[-4:]}" if len(iban) >= 4 else ""
        )

        self._attr_name = f"{institution} {name}"
        self._attr_unique_id = f"{DOMAIN}_{self._account_id}_balance"
        self._attr_native_unit_of_measurement = account.get(
            "currency", "EUR"
        )
        self._attr_suggested_display_precision = 2

        # Bank logo as entity picture
        logo = account.get("logo", "")
        if logo:
            self._attr_entity_picture = logo

        # Extra attributes
        self._attr_extra_state_attributes = {
            "iban_masked": iban_masked,
            "institution": institution,
            "account_type": account.get("type", "personal"),
            "person": account.get("person", ""),
            "currency": account.get("currency", "EUR"),
        }

    async def async_update(self) -> None:
        """Fetch latest balance from GoCardless."""
        try:
            client = await self._manager._async_get_client()
            if not client:
                return

            balances = await client.async_get_balances(self._account_id)
            if balances:
                # Prefer closingBooked, fall back to first available
                balance = self._pick_balance(balances)
                if balance:
                    amount = balance.get("balanceAmount", {})
                    self._attr_native_value = float(
                        amount.get("amount", 0)
                    )
                    self._attr_extra_state_attributes["balance_type"] = (
                        balance.get("balanceType", "unknown")
                    )
                    self._attr_extra_state_attributes["reference_date"] = (
                        balance.get("referenceDate", "")
                    )
        except Exception:
            _LOGGER.exception(
                "Failed to update balance for %s", self._account_id
            )

    @staticmethod
    def _pick_balance(
        balances: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Pick the most useful balance type."""
        # Priority: closingBooked > interimAvailable > interimBooked > first
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


class TotalBalanceSensor(SensorEntity):
    """Aggregated balance across all linked accounts."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_has_entity_name = True
    _attr_name = "Total Balance"
    _attr_icon = "mdi:sigma"

    def __init__(
        self,
        manager,
        entry: ConfigEntry,
        accounts: list[dict[str, Any]],
    ) -> None:
        """Initialize the total balance sensor."""
        self._manager = manager
        self._entry = entry
        self._accounts = accounts
        self._attr_unique_id = f"{DOMAIN}_total_balance"
        self._attr_native_unit_of_measurement = entry.options.get(
            "currency", "EUR"
        )
        self._attr_suggested_display_precision = 2

    async def async_update(self) -> None:
        """Sum balances across all accounts."""
        try:
            client = await self._manager._async_get_client()
            if not client:
                return

            total = 0.0
            account_balances = {}

            for account in self._accounts:
                acc_id = account["id"]
                balances = await client.async_get_balances(acc_id)
                if balances:
                    balance = AccountBalanceSensor._pick_balance(balances)
                    if balance:
                        amount = float(
                            balance.get("balanceAmount", {}).get(
                                "amount", 0
                            )
                        )
                        total += amount
                        iban = account.get("iban", "")
                        masked = (
                            f"****{iban[-4:]}" if len(iban) >= 4 else "?"
                        )
                        account_balances[masked] = amount

            self._attr_native_value = total
            self._attr_extra_state_attributes = {
                "accounts": account_balances,
                "account_count": len(self._accounts),
            }
        except Exception:
            _LOGGER.exception("Failed to update total balance")


class MonthlySummarySensor(SensorEntity):
    """Monthly spending summary with category breakdown."""

    _attr_has_entity_name = True
    _attr_name = "Monthly Summary"
    _attr_icon = "mdi:chart-bar"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, manager, entry: ConfigEntry) -> None:
        """Initialize the monthly summary sensor."""
        self._manager = manager
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_monthly_summary"
        self._attr_native_unit_of_measurement = entry.options.get(
            "currency", "EUR"
        )
        self._attr_suggested_display_precision = 2

    async def async_update(self) -> None:
        """Calculate monthly summary."""
        try:
            summary = await self._manager.async_get_monthly_summary()
            if summary:
                self._attr_native_value = summary.get("balance", 0)
                self._attr_extra_state_attributes = {
                    "total_income": summary.get("total_income", 0),
                    "total_expenses": summary.get("total_expenses", 0),
                    "categories": summary.get("categories", {}),
                    "transaction_count": summary.get(
                        "transaction_count", 0
                    ),
                    "month": summary.get("month", 0),
                    "year": summary.get("year", 0),
                }
        except Exception:
            _LOGGER.exception("Failed to update monthly summary")
