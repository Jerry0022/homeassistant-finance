"""Number platform — budget limit entities per category.

Creates one Number entity per spending category, allowing users
to set budget limits directly from their HA dashboard.
When spending exceeds the limit, an fd_budget_exceeded event fires.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_CATEGORIES, DOMAIN

_LOGGER = logging.getLogger(__name__)

CATEGORY_ICONS = {
    "housing": "mdi:home",
    "food": "mdi:food",
    "transport": "mdi:bus",
    "insurance": "mdi:shield-check",
    "subscriptions": "mdi:youtube-subscription",
    "loans": "mdi:bank",
    "utilities": "mdi:flash",
    "income": "mdi:cash-plus",
    "transfers": "mdi:bank-transfer",
    "other": "mdi:dots-horizontal",
    "cleaning": "mdi:broom",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up budget limit number entities."""
    entities = []
    for category in DEFAULT_CATEGORIES:
        entities.append(BudgetLimitNumber(entry, category))

    async_add_entities(entities, update_before_add=True)


class BudgetLimitNumber(NumberEntity):
    """Number entity for a category budget limit."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "EUR"
    _attr_has_entity_name = True

    def __init__(
        self, entry: ConfigEntry, category: str
    ) -> None:
        """Initialize budget limit number."""
        self._entry = entry
        self._category = category
        self._attr_unique_id = f"{DOMAIN}_budget_{category}"
        self._attr_name = f"Budget {category.replace('_', ' ').title()}"
        self._attr_icon = CATEGORY_ICONS.get(category, "mdi:cash")
        # Default value: 0 = no limit set
        self._attr_native_value = 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Update the budget limit."""
        self._attr_native_value = value
        _LOGGER.debug(
            "Budget limit for %s set to %.2f EUR",
            self._category,
            value,
        )
