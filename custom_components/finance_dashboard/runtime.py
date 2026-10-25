"""Typed per-entry runtime state and lookup helpers.

``entry.runtime_data`` is the source of truth for the manager and coordinator.
``hass.data[DOMAIN]`` is still populated (see ``__init__``) because the HTTP
views look the manager up there; :func:`get_manager` resolves both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import FinanceDashboardCoordinator
    from .manager import FinanceDashboardManager


@dataclass
class FinanceDashboardData:
    """Objects that live as long as the config entry is loaded."""

    manager: FinanceDashboardManager
    coordinator: FinanceDashboardCoordinator


def get_runtime(entry: ConfigEntry) -> FinanceDashboardData | None:
    """Return the entry's runtime data, or None when it is not set up."""
    return getattr(entry, "runtime_data", None)


def get_manager(hass: HomeAssistant, entry: ConfigEntry | None = None) -> Any:
    """Find the manager via runtime_data, falling back to ``hass.data``."""
    if entry is not None:
        runtime = get_runtime(entry)
        if runtime is not None:
            return runtime.manager
        return hass.data.get(DOMAIN, {}).get(entry.entry_id)
    domain_data = hass.data.get(DOMAIN, {})
    for value in domain_data.values():
        if hasattr(value, "get_bank_status"):
            return value
    return None
