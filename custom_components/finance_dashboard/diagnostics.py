"""Diagnostics download — counts and health, never financial content.

Only structure is reported (bank status, how many accounts/transactions, store
versions, options).  Anything that could identify a person, an account or a
session is redacted on top of that, as a second line of defence.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    LEDGER_STORAGE_MINOR_VERSION,
    LEDGER_STORAGE_VERSION,
    RAW_STORAGE_MINOR_VERSION,
    RAW_STORAGE_VERSION,
    VERSION,
)
from .runtime import get_manager

TO_REDACT = {
    # identity
    "iban",
    "bban",
    "name",
    "custom_name",
    "title",
    "aspsp_name",
    "institution",
    "person",
    "ha_users",
    "owner",
    "uid",
    "id",
    "key",
    "identity_key",
    "account_id",
    "resource_id",
    "logo",
    # secrets
    "session_id",
    "access_token",
    "refresh_token",
    "token",
    "code",
    "application_id",
    "app_id",
    "kid",
    "private_key",
    "private_key_pem",
    "psu_ip",
    # money and payment details
    "amount",
    "balanceAmount",
    "transactionAmount",
    "remittanceInformation",
    "creditor",
    "debtor",
    "creditorAccount",
    "debtorAccount",
    "note",
}


def _collect(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    manager = get_manager(hass, entry)
    data: dict[str, Any] = {
        "version": VERSION,
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
            "subentries": [
                {"type": s.subentry_type, "data": dict(s.data)}
                for s in (getattr(entry, "subentries", None) or {}).values()
            ],
        },
        "stores": {
            "ledger": [LEDGER_STORAGE_VERSION, LEDGER_STORAGE_MINOR_VERSION],
            "raw": [RAW_STORAGE_VERSION, RAW_STORAGE_MINOR_VERSION],
        },
    }
    if manager is None:
        data["manager"] = None
        return data

    ledger = manager._ledger
    keys = list(ledger.account_keys())
    data["manager"] = {
        "demo_mode": manager.demo_mode,
        "accounts": len(manager._accounts),
        "ledger_accounts": len(keys),
        # Counts per account by position only; the account keys are IBAN derived.
        "ledger_transactions": [len(ledger.transactions(k)) for k in keys],
        "balance_points": [len(manager.get_balance_history(k)) for k in keys],
        "banks": manager.get_bank_status(),
        "last_refresh_stats": manager.last_refresh_stats,
    }
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for the config entry."""
    return async_redact_data(_collect(hass, entry), TO_REDACT)
