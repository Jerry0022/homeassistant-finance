"""Button platform — manual refresh.

The button is a user-triggered live fetch, but it carries NO PSU headers: a
button press has no HTTP request behind it, and inventing ``Psu-Ip-Address``
values is forbidden.  It is therefore a *background* call and spends one of
the bank's 4 daily slots per account (a bank that is blocked or spent is
skipped, the rest still run).  The panel's refresh is attended and free; use
that when you are sitting in front of it.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FinanceDashboardCoordinator
from .entity import FinanceMainEntity
from .runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the refresh button."""
    runtime = get_runtime(entry)
    async_add_entities([RefreshButton(runtime.coordinator, entry)])


class RefreshButton(FinanceMainEntity, ButtonEntity):
    """Fetch fresh balances and transactions (background, spends budget)."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: FinanceDashboardCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_refresh"

    @property
    def available(self) -> bool:
        # Pressing must work even before the first cache snapshot exists.
        return True

    async def async_press(self) -> None:
        manager = self.coordinator.manager
        if manager.demo_mode:
            raise HomeAssistantError("Refresh is disabled while demo mode is active")
        # No psu_ip on purpose: no request context means background.
        try:
            await manager.async_refresh_transactions()
        except Exception as err:
            _LOGGER.exception("Button refresh failed")
            raise HomeAssistantError("Refresh failed — see the log") from err
        await self.coordinator.async_refresh()
