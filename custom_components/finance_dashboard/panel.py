"""Sidebar panel registration for Finance."""

from __future__ import annotations

import logging

from homeassistant.components import panel_custom
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_MODULE_PATH,
    PANEL_TITLE,
    PANEL_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

STATIC_BASE = f"/api/{DOMAIN}/static"
LOVELACE_COMPONENTS = [
    f"{STATIC_BASE}/fd-budget-config.js",
    f"{STATIC_BASE}/fd-categorize.js",
]


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Finance sidebar panel.

    Creates a sidebar entry that loads the finance dashboard
    web component from the integration's static files.
    """
    try:
        # Register static file path for frontend assets
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_BASE,
                    hass.config.path(
                        "custom_components", DOMAIN, "frontend"
                    ),
                    True,  # Enable caching (matches YouTube Music Connector)
                )
            ]
        )

        # Register the sidebar panel via panel_custom API
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name=PANEL_COMPONENT_NAME,
            frontend_url_path=PANEL_URL_PATH,
            module_url=PANEL_MODULE_PATH,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            require_admin=False,
            config={"domain": DOMAIN},
        )

        # Register Lovelace card JS for automations
        for url in LOVELACE_COMPONENTS:
            add_extra_js_url(hass, url)

        _LOGGER.debug(
            "Finance panel registered at /%s", PANEL_URL_PATH
        )
    except Exception:
        _LOGGER.exception("Failed to register Finance panel")


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister custom sidebar panel."""
    try:
        panel_custom.async_unregister_panel(hass, PANEL_URL_PATH)
    except Exception:
        _LOGGER.debug("Panel was not registered, nothing to remove")
