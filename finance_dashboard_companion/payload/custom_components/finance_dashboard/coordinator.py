"""DataUpdateCoordinator for Finance Dashboard.

Centralises all Enable Banking API calls so that:
- No entity ever calls the API directly
- All updates happen on a fixed 10-minute schedule
- Rate limits are respected (transactions refreshed only when stale)
- A single coordinator failure does not orphan individual entities
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Balance + summary: every 10 minutes
COORDINATOR_UPDATE_INTERVAL = timedelta(minutes=10)

# Only re-fetch raw transactions if cache is older than 6 hours
TRANSACTION_REFRESH_STALENESS = timedelta(hours=6)


class FinanceDashboardCoordinator(DataUpdateCoordinator):
    """Fetch balances and monthly summary on a fixed schedule.

    Entities read from coordinator.data — they never call the banking
    API themselves.  Structure of coordinator.data:
    {
        "balances": {account_id: {..., "balances": [...]}},
        "summary":  {month, year, total_income, total_expenses, ...},
    }
    """

    def __init__(self, hass: HomeAssistant, manager) -> None:
        """Initialise coordinator with a reference to the manager."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=COORDINATOR_UPDATE_INTERVAL,
        )
        self._manager = manager
        self._first_update = True

    async def _async_update_data(self) -> dict:
        """Called by HA every 10 minutes (and on demand via async_refresh)."""
        try:
            # Refresh raw transactions only when the cache is stale.
            # Balance calls happen on every cycle; transaction fetches are
            # kept infrequent to stay within API rate limits.
            # On first coordinator cycle, always refresh to ensure fresh data
            # even if cached _last_refresh appears recent from a prior session.
            last = self._manager._last_refresh
            force_first = self._first_update
            self._first_update = False
            if force_first or last is None or (datetime.now() - last) > TRANSACTION_REFRESH_STALENESS:
                _LOGGER.debug("Transaction cache stale — refreshing from API")
                await self._manager.async_refresh_transactions()

            balances = await self._manager.async_get_balance()
            summary = await self._manager.async_get_monthly_summary()

            rate_limited = self._manager.rate_limited_until
            return {
                "balances": balances,
                "summary": summary,
                "rate_limited_until": rate_limited.isoformat() if rate_limited else None,
            }
        except Exception as exc:
            raise UpdateFailed(f"Finance data update failed: {exc}") from exc
