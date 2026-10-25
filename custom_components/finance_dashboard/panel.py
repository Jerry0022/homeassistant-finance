"""Frontend delivery for Finance: one component kit, two shells.

* Static mount  - the whole ``frontend/`` directory under ``FRONTEND_URL_BASE``.
* Sidebar panel - ``panel_custom`` (admin-only; individual transactions are
  admin data, so the full-page shell is too).
* Lovelace cards - the kit module is added to every dashboard with
  ``frontend.add_extra_js_url`` so the cards appear in the card picker without
  a hand-added Lovelace resource.

Every URL carries ``?v=<VERSION>``: the static path is served with long cache
headers, so the query string is what makes an update reach the browser.
Registration is idempotent (config-entry reloads) and fully reversible.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    CARDS_MODULE_PATH,
    DOMAIN,
    FRONTEND_URL_BASE,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_MODULE_PATH,
    PANEL_TITLE,
    PANEL_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_STATIC_FLAG = "frontend_static_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register static files, the sidebar panel and the auto-loaded cards."""
    store = hass.data.setdefault(DOMAIN, {})

    # Static paths cannot be unregistered, so mount exactly once per process.
    if not store.get(_STATIC_FLAG):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL_BASE, str(_FRONTEND_DIR), True)]
        )
        store[_STATIC_FLAG] = True

    # Cards: a set add is naturally idempotent.
    frontend.add_extra_js_url(hass, CARDS_MODULE_PATH)

    # Panel: async_register_built_in_panel raises on a duplicate path.
    if PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_COMPONENT_NAME,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=PANEL_MODULE_PATH,
            require_admin=True,
            config_panel_domain=DOMAIN,
        )
    _LOGGER.debug("Finance frontend registered (panel /%s, cards via %s)", PANEL_URL_PATH, CARDS_MODULE_PATH)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel and the auto-loaded card module (static mount stays)."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    try:
        frontend.remove_extra_js_url(hass, CARDS_MODULE_PATH)
    except KeyError:
        _LOGGER.debug("Card module was not registered, nothing to remove")
