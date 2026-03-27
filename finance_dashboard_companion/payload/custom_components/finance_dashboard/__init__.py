"""Finance Dashboard — Home Assistant Integration.

Provides a secure finance overview with live banking data via GoCardless/Nordigen
Open Banking API. Tracks accounts, transactions, and household budgets.

SECURITY: No financial data is ever stored in git or logs.
All credentials and tokens are stored in HA's encrypted .storage/ directory.
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

from .const import (
    DOMAIN,
    STORAGE_KEY_AUDIT,
    STORAGE_VERSION,
)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
]

_LOGGER = logging.getLogger(__name__)

type FinanceDashboardConfigEntry = ConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Finance Dashboard integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: FinanceDashboardConfigEntry
) -> bool:
    """Set up Finance Dashboard from a config entry."""
    # Clean up stale restart issues from previous sessions
    ir.async_delete_issue(hass, DOMAIN, "restart_required")

    # Initialize the manager (core business logic)
    from .manager import FinanceDashboardManager

    manager = FinanceDashboardManager(hass, entry)
    await manager.async_initialize()

    # Create the coordinator — single source of truth for all entities.
    # Entities read from coordinator.data instead of calling the API directly.
    from .coordinator import FinanceDashboardCoordinator

    coordinator = FinanceDashboardCoordinator(hass, manager)

    hass.data[DOMAIN][entry.entry_id] = manager
    hass.data[DOMAIN][f"{entry.entry_id}_coordinator"] = coordinator
    hass.data[DOMAIN]["entry"] = entry

    # Register services (pass coordinator so refresh service can push updates)
    await _async_register_services(hass, manager, coordinator)

    # Register sidebar panel
    from .panel import async_register_panel

    await async_register_panel(hass)

    # Register HTTP endpoints
    from .api import async_register_api

    await async_register_api(hass)

    # Poll for add-on restart marker (every 60 seconds)
    async def _poll_restart_marker(_now) -> None:
        marker_path = Path(
            hass.config.path(".storage/finance_dashboard_restart_needed.json")
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

    entry.async_on_unload(
        async_track_time_interval(
            hass, _poll_restart_marker, timedelta(seconds=60)
        )
    )

    # Forward platform setup — sensors/numbers/selects will register themselves
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Kick off the first coordinator refresh once HA is fully started.
    # This populates entities with live data immediately without blocking startup.
    if entry.data.get("configured"):
        async def _initial_refresh(_event=None) -> None:
            try:
                await coordinator.async_refresh()
                _LOGGER.info("Initial coordinator refresh completed")
            except Exception:
                _LOGGER.exception("Initial coordinator refresh failed")

        hass.bus.async_listen_once("homeassistant_started", _initial_refresh)

    _LOGGER.info("Finance Dashboard v%s loaded", entry.version)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FinanceDashboardConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        manager = hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_coordinator", None)
        if manager:
            await manager.async_shutdown()
        # Clean up entry reference if it matches
        if hass.data.get(DOMAIN, {}).get("entry") is entry:
            hass.data[DOMAIN].pop("entry", None)
    return unload_ok


async def _async_register_services(
    hass: HomeAssistant, manager, coordinator
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
        # Push fresh data to all entities via coordinator
        await coordinator.async_refresh()

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
            await manager.async_set_budget_limit(category, float(limit))

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
        DOMAIN, SERVICE_REFRESH_TRANSACTIONS, handle_refresh_transactions
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
