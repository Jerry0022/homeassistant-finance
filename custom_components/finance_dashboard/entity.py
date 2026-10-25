"""Shared entity plumbing: device registry layout and the bank/account layout.

Device tree::

    main service device ("Finance Dashboard")   aggregates, household, refresh
    └── bank device   (DOMAIN, bank_<subentry_id>)   manufacturer = ASPSP name
        └── account device (DOMAIN, account_<identity key>)   via bank

Bank devices and the entities on them belong to the bank's config subentry,
so removing a bank in the UI removes its devices and entities with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .account_identity import account_key
from .const import DOMAIN, LEGACY_BANK_ID
from .coordinator import FinanceDashboardCoordinator


def main_device_identifier(entry: ConfigEntry) -> tuple[str, str]:
    return (DOMAIN, f"main_{entry.entry_id}")


def bank_device_identifier(bank_id: str) -> tuple[str, str]:
    return (DOMAIN, f"bank_{bank_id}")


def account_device_identifier(key: str) -> tuple[str, str]:
    return (DOMAIN, f"account_{key}")


def main_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={main_device_identifier(entry)},
        name="Finance Dashboard",
        manufacturer="Finance Dashboard",
        entry_type=DeviceEntryType.SERVICE,
    )


def bank_device_info(bank_id: str, title: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={bank_device_identifier(bank_id)},
        name=title or "Bank",
        manufacturer=title or None,
        model="Enable Banking (PSD2)",
        entry_type=DeviceEntryType.SERVICE,
    )


def account_device_info(account: dict[str, Any], bank_id: str | None, title: str) -> DeviceInfo:
    name = account.get("custom_name") or account.get("name") or "Account"
    institution = account.get("institution") or title
    info = DeviceInfo(
        identifiers={account_device_identifier(account_key(account))},
        name=f"{institution} {name}".strip(),
        manufacturer=institution or None,
        model=str(account.get("type") or "account"),
        entry_type=DeviceEntryType.SERVICE,
    )
    if bank_id:
        info["via_device"] = bank_device_identifier(bank_id)
    return info


@dataclass
class BankLayout:
    """One bank with its accounts, as entities see it."""

    bank_id: str
    title: str
    accounts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def subentry_id(self) -> str | None:
        """The config subentry id; None for the virtual legacy bank."""
        return None if self.bank_id == LEGACY_BANK_ID else self.bank_id


async def async_bank_layout(manager: Any, entry: ConfigEntry) -> list[BankLayout]:
    """Banks and their accounts.  Cache/credential reads only — no bank calls."""
    targets = await manager._async_bank_targets()
    layout = [
        BankLayout(t["bank_id"], t.get("title") or "", list(t.get("accounts") or []))
        for t in targets
    ]
    placed = {account_key(a) for bank in layout for a in bank.accounts}
    orphans = [a for a in entry.data.get("accounts", []) if account_key(a) not in placed]
    if orphans:
        # Accounts no bank claims keep their balance sensor under the legacy id.
        legacy = next((b for b in layout if b.bank_id == LEGACY_BANK_ID), None)
        if legacy is None:
            legacy = BankLayout(LEGACY_BANK_ID, orphans[0].get("institution") or "Bank")
            layout.append(legacy)
        legacy.accounts.extend(orphans)
    return layout


class FinanceMainEntity(CoordinatorEntity[FinanceDashboardCoordinator]):
    """Entity on the main service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FinanceDashboardCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = main_device_info(entry)

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data is not None)
