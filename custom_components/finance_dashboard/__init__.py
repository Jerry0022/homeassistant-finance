"""Finance Dashboard — Home Assistant Integration.

Provides a secure finance overview with live banking data via the Enable
Banking PSD2 Open Banking API (JWT-signed RS256). Tracks accounts,
transactions, and household budgets.

SECURITY: No financial data is ever stored in git or logs.
All credentials and tokens are stored in HA's encrypted .storage/ directory.
Live banking calls are gated behind explicit user-triggered paths
(refresh button, service call, setup bootstrap) to respect Enable
Banking's 4/day/ASPSP rate limit.
"""

from __future__ import annotations

import logging

from ha_customapps.restart import RestartNotifier
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, SupportsResponse

from .const import (
    DOMAIN,
    SERVICE_TOGGLE_DEMO,
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
    # Restart notification via ha-customapps (marker polling + Repairs issue)
    notifier = RestartNotifier(hass, DOMAIN)
    await notifier.async_setup(entry)

    # Initialize the manager (core business logic)
    from .manager import FinanceDashboardManager

    manager = FinanceDashboardManager(hass, entry)
    await manager.async_initialize()

    # Create the coordinator — single source of truth for all entities.
    # Entities read from coordinator.data instead of calling the API directly.
    from .coordinator import FinanceDashboardCoordinator

    coordinator = FinanceDashboardCoordinator(hass, manager)

    # Initialize demo mode from options
    if entry.options.get("demo_mode", False):
        manager.set_demo_mode(True)

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

    # Forward platform setup — sensors/numbers/selects will register themselves
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Load cached data into coordinator — NO external API calls.
    # Entities are populated immediately from the transaction cache
    # that was loaded in manager.async_initialize(). The user must
    # click "Aktualisieren" to trigger real banking API calls.
    # Run for ALL entry states (configured / pending / demo) so sensors
    # always have a valid coordinator snapshot — without this,
    # half-configured setups leave entities permanently "unavailable"
    # until a full HA restart.
    async def _initial_load() -> None:
        try:
            await coordinator.async_load_cached()
            _LOGGER.info("Initial cached data loaded (no API calls)")
        except Exception:
            _LOGGER.exception("Initial cached data load failed")

    if hass.is_running:
        hass.async_create_task(_initial_load())
    else:
        hass.bus.async_listen_once(
            "homeassistant_started",
            lambda _event: hass.async_create_task(_initial_load()),
        )

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

    async def handle_refresh_accounts(call) -> dict:
        await manager.async_refresh_accounts()
        # Keep entity state in lockstep with the account metadata we
        # just refreshed — otherwise the next dashboard render reads
        # stale account data from the coordinator and the user sees
        # no change despite a successful service call.
        try:
            await coordinator.async_refresh()
        except Exception:
            _LOGGER.exception(
                "Coordinator refresh after refresh_accounts failed"
            )
        return manager.get_refresh_status()

    async def handle_refresh_transactions(call) -> dict:
        """User-triggered refresh — returns stats so automations and
        the frontend can surface "5 Konten, 243 Tx, 2 neu" instead
        of a silent OK."""
        await manager.async_refresh_transactions()
        # Push fresh data to all entities via coordinator
        await coordinator.async_refresh()
        return manager.get_refresh_status()

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

    async def handle_toggle_demo(call) -> None:
        # R14: admin-only gate — toggling demo mode modifies global state
        # and replaces cached transaction data.
        from homeassistant.exceptions import HomeAssistantError

        if not call.context or not call.context.user_id:
            raise HomeAssistantError("admin_required")
        user = await hass.auth.async_get_user(call.context.user_id)
        if user is None or not user.is_admin:
            raise HomeAssistantError("admin_required")

        enabled = not manager.demo_mode
        if enabled:
            # Back up real data before overwriting with demo
            manager._demo_backup_transactions = list(manager._transactions)
            manager._demo_backup_tx_by_account = dict(manager._tx_by_account)
            manager._demo_backup_balances = dict(manager._balances)
            manager._demo_backup_last_refresh = manager._last_refresh
        else:
            # Restore real data when disabling demo
            if hasattr(manager, "_demo_backup_transactions"):
                manager._transactions = manager._demo_backup_transactions
                manager._tx_by_account = manager._demo_backup_tx_by_account
                manager._balances = manager._demo_backup_balances
                manager._last_refresh = manager._demo_backup_last_refresh
        manager.set_demo_mode(enabled)
        await coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_ACCOUNTS,
        handle_refresh_accounts,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_TRANSACTIONS,
        handle_refresh_transactions,
        supports_response=SupportsResponse.OPTIONAL,
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
    hass.services.async_register(
        DOMAIN, SERVICE_TOGGLE_DEMO, handle_toggle_demo
    )
