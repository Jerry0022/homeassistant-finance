"""GUARDIAN — Cache-vs-Live-Boundary contract test.

NEVER remove or weaken these assertions.
The separation of cache reads from live Enable Banking API calls is a
Hard-Constraint defined in CLAUDE.md:

    "Cache reads (HTTP endpoints, sensor attributes, coordinator state)
     are unbounded. Live Enable-Banking calls are ONLY allowed from
     explicit user-triggered paths."

FinanceDashboardCoordinator._async_update_data() MUST read exclusively
from the manager's in-memory cache.  It must NEVER call any live API
method on the EnableBankingClient — not even once.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_mock_manager() -> MagicMock:
    """Return a MagicMock that quacks like FinanceDashboardManager.

    All async methods that the coordinator calls are mocked to return
    safe empty values so the coordinator can complete without importing
    the full HA dependency tree.
    """
    manager = MagicMock()
    manager.async_get_balance = AsyncMock(return_value={})
    manager.async_get_monthly_summary = AsyncMock(return_value={})
    manager.rate_limited_until = None
    manager.get_refresh_status = MagicMock(return_value={})
    manager.get_cached_balances = MagicMock(return_value={})
    return manager


def _build_mock_client() -> MagicMock:
    """Return a MagicMock for EnableBankingClient with all live async methods.

    These are the methods that make outbound HTTP calls to the banking API.
    The test asserts that NONE of them are ever invoked by the coordinator.

    List derived from custom_components/finance_dashboard/enablebanking_client.py
    — every public async method that ultimately calls _async_request().
    """
    client = MagicMock()

    # All live network methods — must NEVER be called by coordinator
    client.async_test_connection = AsyncMock()
    client.async_get_institutions = AsyncMock()
    client.async_create_auth = AsyncMock()
    client.async_create_session = AsyncMock()
    client.async_get_account_details = AsyncMock()
    client.async_get_balances = AsyncMock()
    client.async_get_transactions = AsyncMock()

    return client


# ---------------------------------------------------------------------------
# The Guardian tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_coordinator_update_data_never_calls_live_api() -> None:
    """GUARDIAN — coordinator._async_update_data() must never call live API.

    Calls _async_update_data() 5 times (simulating repeated coordinator
    refreshes) and asserts that zero calls reached EnableBankingClient's
    live methods.  One call would be enough to burn a daily API quota slot.
    """
    # We import here (not at module level) so that missing HA packages do
    # not prevent the test file from being collected at all.
    from custom_components.finance_dashboard.coordinator import (
        FinanceDashboardCoordinator,
    )

    mock_hass = MagicMock()
    mock_hass.loop = MagicMock()
    mock_hass.bus = MagicMock()
    mock_hass.bus.async_listen = MagicMock(return_value=lambda: None)

    manager = _build_mock_manager()
    client = _build_mock_client()

    # Attach client to manager so a coordinator that accidentally
    # delegates to manager._client would still be caught.
    manager._client = client

    coordinator = FinanceDashboardCoordinator(hass=mock_hass, manager=manager)

    # Run _async_update_data() 5× — simulates repeated manual refreshes
    CALL_COUNT = 5
    for _ in range(CALL_COUNT):
        await coordinator._async_update_data()

    # --- Assertions: zero live API calls ---
    live_methods = [
        ("async_test_connection", client.async_test_connection),
        ("async_get_institutions", client.async_get_institutions),
        ("async_create_auth", client.async_create_auth),
        ("async_create_session", client.async_create_session),
        ("async_get_account_details", client.async_get_account_details),
        ("async_get_balances", client.async_get_balances),
        ("async_get_transactions", client.async_get_transactions),
    ]
    for method_name, mock_method in live_methods:
        assert mock_method.call_count == 0, (
            f"BOUNDARY VIOLATION: EnableBankingClient.{method_name} was called "
            f"{mock_method.call_count} time(s) by coordinator._async_update_data(). "
            f"The coordinator must only read from manager cache — never hit the live API."
        )


@pytest.mark.asyncio
async def test_coordinator_async_load_cached_never_calls_live_api() -> None:
    """GUARDIAN — coordinator.async_load_cached() must never call live API.

    async_load_cached() is the startup path that populates entities from
    cache without contacting the bank.  If it accidentally called a live
    method, we would burn API quota on every HA restart.
    """
    from custom_components.finance_dashboard.coordinator import (
        FinanceDashboardCoordinator,
    )

    mock_hass = MagicMock()
    mock_hass.loop = MagicMock()
    mock_hass.bus = MagicMock()
    mock_hass.bus.async_listen = MagicMock(return_value=lambda: None)

    manager = _build_mock_manager()
    client = _build_mock_client()
    manager._client = client

    coordinator = FinanceDashboardCoordinator(hass=mock_hass, manager=manager)

    # Patch async_set_updated_data so we don't need a real HA event loop
    coordinator.async_set_updated_data = MagicMock()

    await coordinator.async_load_cached()

    live_methods = [
        ("async_test_connection", client.async_test_connection),
        ("async_get_institutions", client.async_get_institutions),
        ("async_create_auth", client.async_create_auth),
        ("async_create_session", client.async_create_session),
        ("async_get_account_details", client.async_get_account_details),
        ("async_get_balances", client.async_get_balances),
        ("async_get_transactions", client.async_get_transactions),
    ]
    for method_name, mock_method in live_methods:
        assert mock_method.call_count == 0, (
            f"BOUNDARY VIOLATION: EnableBankingClient.{method_name} was called "
            f"during async_load_cached(). This path must be 100% cache-read only."
        )


@pytest.mark.asyncio
async def test_coordinator_update_interval_is_none() -> None:
    """GUARDIAN — update_interval must be None (no background polling).

    A non-None update_interval would cause HA to poll the banking API
    automatically, violating the 4/day/ASPSP rate limit hard constraint.
    """
    from custom_components.finance_dashboard.coordinator import (
        FinanceDashboardCoordinator,
    )

    mock_hass = MagicMock()
    mock_hass.loop = MagicMock()
    mock_hass.bus = MagicMock()
    mock_hass.bus.async_listen = MagicMock(return_value=lambda: None)

    manager = _build_mock_manager()
    coordinator = FinanceDashboardCoordinator(hass=mock_hass, manager=manager)

    assert coordinator.update_interval is None, (
        "BOUNDARY VIOLATION: coordinator.update_interval is not None. "
        "Setting a polling interval would cause automatic background API calls "
        "and exhaust the 4/day/ASPSP Enable Banking rate limit."
    )
