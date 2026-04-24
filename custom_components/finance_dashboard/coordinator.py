"""DataUpdateCoordinator for Finance Dashboard.

Centralises all Enable Banking API calls so that:
- No entity ever calls the API directly
- Updates only happen on manual refresh (service call or UI button)
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

# Only re-fetch raw transactions if cache is older than 6 hours
TRANSACTION_REFRESH_STALENESS = timedelta(hours=6)


class FinanceDashboardCoordinator(DataUpdateCoordinator):
    """Fetch balances and monthly summary on manual refresh only.

    Entities read from coordinator.data — they never call the banking
    API themselves.  Structure of coordinator.data:
    {
        "balances": {account_id: {..., "balances": [...]}},
        "summary":  {month, year, total_income, total_expenses, ...},
    }
    """

    def __init__(self, hass: HomeAssistant, manager) -> None:
        """Initialise coordinator with a reference to the manager.

        update_interval is None — API calls only happen on manual refresh
        (service call or UI button). Entities receive cached data from
        the initial startup refresh and subsequent manual refreshes.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self._manager = manager

    async def async_load_cached(self) -> None:
        """Populate coordinator data from cache only — zero API calls.

        Used on startup to feed entities with cached transactions/balances
        without hitting the banking API. The user must click "Aktualisieren"
        to trigger real API calls.

        If the cache load fails, we still publish an empty snapshot so
        entities render ``unknown`` (cache miss) instead of ``unavailable``
        (no coordinator data at all). A fresh refresh heals both states.
        """
        try:
            summary = await self._manager.async_get_monthly_summary()
            rate_limited = self._manager.rate_limited_until
            self.async_set_updated_data({
                "balances": self._manager.get_cached_balances(),
                "summary": summary,
                "rate_limited_until": rate_limited.isoformat() if rate_limited else None,
                "refresh_status": self._manager.get_refresh_status(),
            })
            _LOGGER.debug("Loaded cached data into coordinator (no API calls)")
        except Exception:
            _LOGGER.exception("Failed to load cached data into coordinator")
            # Publish an empty shell so entities have a valid (even if
            # empty) coordinator.data dict to read from. Without this,
            # sensors stay permanently unavailable after a cache-load
            # error, and no user action can revive them short of a
            # full restart.
            try:
                self.async_set_updated_data({
                    "balances": {},
                    "summary": {},
                    "rate_limited_until": None,
                    "refresh_status": self._manager.get_refresh_status(),
                })
            except Exception:
                _LOGGER.exception(
                    "Fallback empty-snapshot publish also failed"
                )

    async def _async_update_data(self) -> dict:
        """Called on demand via async_refresh() (manual refresh only).

        This method is ONLY reached when the user explicitly triggers
        a refresh (UI button or service call). It never runs automatically.

        Cache-read only: balances and summary are read from the manager's
        in-memory cache — no live API calls. Live fetches happen inside
        ``manager.async_refresh_transactions`` (which also refreshes
        balances) and are gated by an explicit user trigger.
        """
        try:
            balances = await self._manager.async_get_balance()
            summary = await self._manager.async_get_monthly_summary()

            rate_limited = self._manager.rate_limited_until
            return {
                "balances": balances,
                "summary": summary,
                "rate_limited_until": (
                    rate_limited.isoformat() if rate_limited else None
                ),
                "refresh_status": self._manager.get_refresh_status(),
            }
        except Exception as exc:
            raise UpdateFailed(f"Finance data update failed: {exc}") from exc
