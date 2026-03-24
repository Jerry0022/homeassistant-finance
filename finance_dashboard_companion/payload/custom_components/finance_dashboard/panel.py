"""Sidebar panel registration for Finance Dashboard."""

from __future__ import annotations

import logging

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_ICON,
    PANEL_MODULE_PATH,
    PANEL_TITLE,
    PANEL_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Finance Dashboard sidebar panel.

    Creates a sidebar entry that loads the finance dashboard
    web component from the integration's static files.
    """
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL.lstrip("/"),
        config={
            "_panel_custom": {
                "name": "finance-dashboard-panel",
                "module_url": PANEL_MODULE_PATH,
                "embed_iframe": False,
            }
        },
        require_admin=False,
    )
    _LOGGER.debug("Finance Dashboard panel registered at %s", PANEL_URL)
