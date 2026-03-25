"""Finance — Home Assistant Integration.

Provides a secure finance overview with live banking data via Enable Banking
Open Banking API (PSD2). Tracks accounts, transactions, and household budgets.

SECURITY: No financial data is ever stored in git or logs.
All credentials and sessions are stored in HA's encrypted .storage/ directory.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
]

_LOGGER = logging.getLogger(__name__)

type FinanceDashboardConfigEntry = ConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Finance integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: FinanceDashboardConfigEntry
) -> bool:
    """Migrate old config entries to current version."""
    if config_entry.version < 2:
        _LOGGER.info(
            "Migrating Finance config entry from v%d to v3 "
            "(GoCardless -> Enable Banking panel-driven setup)",
            config_entry.version,
        )
        new_data = {**config_entry.data}
        new_data.pop("requisition_id", None)
        new_data.pop("agreement_id", None)
        new_data["session_id"] = None
        new_data["configured"] = False
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=3
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            "reconfigure_required",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="reconfigure_required",
        )
        _LOGGER.info("Migration to v3 complete — user must set up bank in panel")

    elif config_entry.version == 2:
        _LOGGER.info(
            "Migrating Finance config entry from v2 to v3 "
            "(panel-driven bank setup)"
        )
        new_data = {**config_entry.data}
        # Keep existing configured state — if bank was connected, it stays
        if not new_data.get("configured"):
            new_data["configured"] = False
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=3
        )
        _LOGGER.info("Migration to v3 complete")

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: FinanceDashboardConfigEntry
) -> bool:
    """Set up Finance from a config entry."""
    ir.async_delete_issue(hass, DOMAIN, "restart_required")

    # Store entry reference for setup API endpoints
    hass.data[DOMAIN]["entry"] = entry

    # Register sidebar panel (always — even before bank is connected)
    from .panel import async_register_panel

    await async_register_panel(hass)

    # Register HTTP endpoints (always — includes setup endpoints)
    from .api import async_register_api

    await async_register_api(hass)

    # Poll for add-on restart marker (always — even before bank is connected)
    async def _poll_restart_marker(_now) -> None:
        marker_path = Path(
            hass.config.path(
                ".storage/finance_dashboard_restart_needed.json"
            )
        )
        if marker_path.exists():
            import json

            try:
                data = json.loads(marker_path.read_text())
                marker_path.unlink()
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    "restart_required",
                    is_fixable=True,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="restart_required",
                    translation_placeholders={
                        "version": data.get("version", "unknown")
                    },
                )
            except Exception:
                _LOGGER.exception("Failed to process restart marker")

    # Check immediately on startup, then poll every 60s
    await _poll_restart_marker(None)
    entry.async_on_unload(
        async_track_time_interval(
            hass, _poll_restart_marker, timedelta(seconds=60)
        )
    )

    is_configured = entry.data.get("configured", False)

    if is_configured:
        # Full initialization: manager, services, sensors
        from .manager import FinanceDashboardManager

        manager = FinanceDashboardManager(hass, entry)
        await manager.async_initialize()
        hass.data[DOMAIN][entry.entry_id] = manager

        await _async_register_services(hass, manager)

        # Forward platform setup
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORMS
        )

        # Initial data refresh (runs in background so setup isn't blocked)
        async def _initial_refresh() -> None:
            try:
                await manager.async_refresh_transactions()
                _LOGGER.info("Initial transaction refresh complete")
            except Exception:
                _LOGGER.exception("Initial data refresh failed")

        hass.async_create_task(_initial_refresh())

        _LOGGER.info(
            "Finance fully loaded (bank connected)"
        )
    else:
        _LOGGER.info(
            "Finance loaded — awaiting bank setup in panel"
        )

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FinanceDashboardConfigEntry
) -> bool:
    """Unload a config entry."""
    is_configured = entry.data.get("configured", False)

    if is_configured:
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, PLATFORMS
        )
        if unload_ok:
            manager = hass.data[DOMAIN].pop(entry.entry_id, None)
            if manager:
                await manager.async_shutdown()
    else:
        unload_ok = True

    hass.data[DOMAIN].pop("entry", None)

    from .panel import async_unregister_panel

    await async_unregister_panel(hass)

    return unload_ok


async def _async_register_services(
    hass: HomeAssistant, manager
) -> None:
    """Register integration services."""
    from .const import (
        SERVICE_REFRESH_ACCOUNTS,
        SERVICE_REFRESH_TRANSACTIONS,
        SERVICE_GET_BALANCE,
        SERVICE_GET_SUMMARY,
        SERVICE_CATEGORIZE,
        SERVICE_SET_BUDGET_LIMIT,
        SERVICE_EXPORT_CSV,
    )

    async def handle_refresh_accounts(call) -> None:
        await manager.async_refresh_accounts()

    async def handle_refresh_transactions(call) -> None:
        await manager.async_refresh_transactions()

    async def handle_get_balance(call) -> dict:
        return await manager.async_get_balance()

    async def handle_get_summary(call) -> dict:
        return await manager.async_get_monthly_summary()

    async def handle_categorize(call) -> None:
        await manager.async_categorize_transactions()

    async def handle_set_budget_limit(call) -> None:
        category = call.data.get("category")
        limit = call.data.get("limit")
        if category and limit is not None:
            await manager.async_set_budget_limit(
                category, float(limit)
            )

    async def handle_export_csv(call) -> dict:
        path = await manager.async_export_csv(
            date_from=call.data.get("date_from"),
            date_to=call.data.get("date_to"),
            categories=call.data.get("categories"),
        )
        return {"path": path}

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_ACCOUNTS, handle_refresh_accounts
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_TRANSACTIONS,
        handle_refresh_transactions,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_BALANCE, handle_get_balance
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_SUMMARY, handle_get_summary
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CATEGORIZE, handle_categorize
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_BUDGET_LIMIT, handle_set_budget_limit
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_CSV, handle_export_csv
    )
