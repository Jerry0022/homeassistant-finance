"""Finance HTTP API — module package.

Exposes ``async_register_api`` as the single entry point for registering
all HTTP endpoints.  Consumers that previously imported from the flat
``api.py`` module can continue to use::

    from .api import async_register_api

because this package's ``__init__`` re-exports the same name.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from ._helpers import _get_manager, _get_setup_client, _validate_oauth_state
from .data import (
    FinanceDashboardBalanceView,
    FinanceDashboardSummaryView,
    FinanceDashboardTransactionsView,
    FinanceDashboardTransferChainsView,
)
from .demo import FinanceDashboardDemoDataView, FinanceDashboardDemoToggleView
from .refresh import (
    FinanceDashboardRefreshStatusView,
    FinanceDashboardRefreshTriggerView,
)
from .setup import (
    FinanceDashboardOAuthCallbackView,
    FinanceDashboardSetupAuthorizeView,
    FinanceDashboardSetupCompleteView,
    FinanceDashboardSetupInstitutionsView,
    FinanceDashboardSetupStatusView,
    FinanceDashboardSetupUpdateAccountsView,
    FinanceDashboardSetupUsersView,
)
from .static import FinanceDashboardStaticView

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "async_register_api",
    # Helpers (re-exported for backwards-compat with tests that import from .api)
    "_get_manager",
    "_get_setup_client",
    "_validate_oauth_state",
    # Setup wizard
    "FinanceDashboardSetupStatusView",
    "FinanceDashboardSetupUsersView",
    "FinanceDashboardSetupInstitutionsView",
    "FinanceDashboardSetupAuthorizeView",
    "FinanceDashboardSetupCompleteView",
    "FinanceDashboardSetupUpdateAccountsView",
    "FinanceDashboardOAuthCallbackView",
    # Data endpoints
    "FinanceDashboardBalanceView",
    "FinanceDashboardTransactionsView",
    "FinanceDashboardSummaryView",
    "FinanceDashboardTransferChainsView",
    # Refresh
    "FinanceDashboardRefreshStatusView",
    "FinanceDashboardRefreshTriggerView",
    # Static
    "FinanceDashboardStaticView",
    # Demo
    "FinanceDashboardDemoToggleView",
    "FinanceDashboardDemoDataView",
]


async def async_register_api(hass: HomeAssistant) -> None:
    """Register all Finance HTTP API endpoints."""
    hass.http.register_view(FinanceDashboardOAuthCallbackView())
    hass.http.register_view(FinanceDashboardStaticView())
    hass.http.register_view(FinanceDashboardBalanceView())
    hass.http.register_view(FinanceDashboardTransactionsView())
    hass.http.register_view(FinanceDashboardSummaryView())
    hass.http.register_view(FinanceDashboardRefreshStatusView())
    hass.http.register_view(FinanceDashboardRefreshTriggerView())
    # Setup wizard endpoints
    hass.http.register_view(FinanceDashboardSetupStatusView())
    hass.http.register_view(FinanceDashboardSetupInstitutionsView())
    hass.http.register_view(FinanceDashboardSetupAuthorizeView())
    hass.http.register_view(FinanceDashboardSetupCompleteView())
    hass.http.register_view(FinanceDashboardSetupUsersView())
    hass.http.register_view(FinanceDashboardSetupUpdateAccountsView())
    hass.http.register_view(FinanceDashboardTransferChainsView())
    hass.http.register_view(FinanceDashboardDemoToggleView())
    hass.http.register_view(FinanceDashboardDemoDataView())
    _LOGGER.debug("Finance API endpoints registered")
