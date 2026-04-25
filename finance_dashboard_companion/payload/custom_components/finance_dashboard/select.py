"""Select platform — split model selector entity.

Allows switching the budget split model directly from the dashboard
without going into integration settings.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

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


class _OptionsBackedSelect(SelectEntity):
    """Base class for selects whose state lives in ``entry.options``.

    Handles:
    - Initial option from entry.options
    - Reactive sync when the options flow updates the entry
    """

    _option_key: str = ""
    _default_key: str = ""
    _label_map: dict[str, str] = {}  # noqa: RUF012

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize with the current entry option."""
        self._entry = entry
        self._attr_options = list(self._label_map.values())
        current = entry.options.get(self._option_key, self._default_key)
        self._attr_current_option = self._label_map.get(current, self._label_map[self._default_key])
        self._unsub_update: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Listen for options changes so the entity stays in sync."""
        await super().async_added_to_hass()
        self._unsub_update = self._entry.add_update_listener(self._async_entry_updated)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the update listener on teardown."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None

    async def _async_entry_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Refresh current option when the entry options change externally."""
        current = entry.options.get(self._option_key, self._default_key)
        label = self._label_map.get(current, self._label_map[self._default_key])
        if label != self._attr_current_option:
            self._attr_current_option = label
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Persist the selected option back into the entry."""
        # Reverse lookup: display name → storage key
        key = next(
            (k for k, v in self._label_map.items() if v == option),
            self._default_key,
        )
        self._attr_current_option = option
        _LOGGER.info(
            "%s changed to: %s (%s)",
            self._option_key,
            option,
            key,
        )
        new_options = dict(self._entry.options)
        new_options[self._option_key] = key
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()


class SplitModelSelect(_OptionsBackedSelect):
    """Select entity for choosing the budget split model."""

    _attr_has_entity_name = True
    _attr_name = "Split Model"
    _attr_icon = "mdi:scale-balance"
    _option_key = "split_model"
    _default_key = "proportional"
    _label_map = SPLIT_MODELS

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize split model select."""
        super().__init__(entry)
        self._attr_unique_id = f"{DOMAIN}_split_model"


class RemainderModeSelect(_OptionsBackedSelect):
    """Select entity for remainder split mode."""

    _attr_has_entity_name = True
    _attr_name = "Remainder Mode"
    _attr_icon = "mdi:arrow-split-vertical"
    _option_key = "remainder_mode"
    _default_key = "none"
    _label_map = REMAINDER_MODES

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize remainder mode select."""
        super().__init__(entry)
        self._attr_unique_id = f"{DOMAIN}_remainder_mode"
