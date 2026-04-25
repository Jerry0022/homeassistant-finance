"""Sidebar panel registration for Finance — uses ha-customapps PanelRegistrar."""

from __future__ import annotations

import logging

from ha_customapps.panel import PanelRegistrar
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
    f"{STATIC_BASE}/fd-shared-styles.js",
    f"{STATIC_BASE}/fd-data-provider.js",
    f"{STATIC_BASE}/fd-stat-card.js",
    f"{STATIC_BASE}/fd-person-card.js",
    f"{STATIC_BASE}/fd-donut-chart.js",
    f"{STATIC_BASE}/fd-header.js",
    f"{STATIC_BASE}/fd-stats-row.js",
    f"{STATIC_BASE}/fd-household-section.js",
    f"{STATIC_BASE}/fd-category-section.js",
    f"{STATIC_BASE}/fd-cost-distribution.js",
    f"{STATIC_BASE}/fd-recurring-list.js",
    f"{STATIC_BASE}/fd-transactions-log.js",
    f"{STATIC_BASE}/fd-budget-config.js",
    f"{STATIC_BASE}/fd-categorize.js",
    f"{STATIC_BASE}/fd-setup-wizard.js",
    f"{STATIC_BASE}/finance-status-chip.js",
]


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Finance sidebar panel."""
    try:
        registrar = PanelRegistrar(
            hass=hass,
            domain=DOMAIN,
            panel_component=PANEL_COMPONENT_NAME,
            panel_title=PANEL_TITLE,
            panel_icon=PANEL_ICON,
            panel_url_path=PANEL_URL_PATH,
            module_url=PANEL_MODULE_PATH,
            frontend_dir=hass.config.path("custom_components", DOMAIN, "frontend"),
            lovelace_urls=LOVELACE_COMPONENTS,
        )
        await registrar.async_register()
        _LOGGER.debug("Finance panel registered at /%s", PANEL_URL_PATH)
    except Exception:
        _LOGGER.exception("Failed to register Finance panel")


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister custom sidebar panel."""
    from homeassistant.components import panel_custom

    try:
        panel_custom.async_unregister_panel(hass, PANEL_URL_PATH)
    except Exception:
        _LOGGER.debug("Panel was not registered, nothing to remove")
