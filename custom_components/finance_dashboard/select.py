"""Select platform — split model selector entity.

Allows switching the budget split model directly from the dashboard
without going into integration settings.
"""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SPLIT_MODELS = {
    "equal": "Equal (50/50)",
    "proportional": "Proportional (by income)",
    "custom": "Custom (manual %)",
}

REMAINDER_MODES = {
    "none": "No split (each keeps own)",
    "equal_split": "Equal distribution",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up split model select entities."""
    async_add_entities(
        [
            SplitModelSelect(entry),
            RemainderModeSelect(entry),
        ],
        update_before_add=True,
    )


class SplitModelSelect(SelectEntity):
    """Select entity for choosing the budget split model."""

    _attr_has_entity_name = True
    _attr_name = "Split Model"
    _attr_icon = "mdi:scale-balance"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize split model select."""
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_split_model"
        self._attr_options = list(SPLIT_MODELS.values())
        current = entry.options.get("split_model", "proportional")
        self._attr_current_option = SPLIT_MODELS.get(
            current, SPLIT_MODELS["proportional"]
        )

    async def async_select_option(self, option: str) -> None:
        """Handle split model change."""
        # Reverse lookup: display name → key
        key = next(
            (k for k, v in SPLIT_MODELS.items() if v == option),
            "proportional",
        )
        self._attr_current_option = option
        _LOGGER.info("Split model changed to: %s (%s)", option, key)

        # Update the config entry options
        new_options = dict(self._entry.options)
        new_options["split_model"] = key
        self.hass.config_entries.async_update_entry(
            self._entry, options=new_options
        )


class RemainderModeSelect(SelectEntity):
    """Select entity for remainder split mode."""

    _attr_has_entity_name = True
    _attr_name = "Remainder Mode"
    _attr_icon = "mdi:arrow-split-vertical"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize remainder mode select."""
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_remainder_mode"
        self._attr_options = list(REMAINDER_MODES.values())
        current = entry.options.get("remainder_mode", "none")
        self._attr_current_option = REMAINDER_MODES.get(
            current, REMAINDER_MODES["none"]
        )

    async def async_select_option(self, option: str) -> None:
        """Handle remainder mode change."""
        key = next(
            (k for k, v in REMAINDER_MODES.items() if v == option),
            "none",
        )
        self._attr_current_option = option
        _LOGGER.info("Remainder mode changed to: %s (%s)", option, key)

        new_options = dict(self._entry.options)
        new_options["remainder_mode"] = key
        self.hass.config_entries.async_update_entry(
            self._entry, options=new_options
        )
