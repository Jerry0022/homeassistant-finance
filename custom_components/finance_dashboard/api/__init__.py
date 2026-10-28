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

from ._helpers import _get_manager, _get_setup_client
from .assignments import FinanceDashboardAssignmentsView
from .contracts import (
    FinanceDashboardAccountSavingsView,
    FinanceDashboardContractsView,
    FinanceDashboardContractView,
    FinanceDashboardReservesView,
)
from .data import (
    FinanceDashboardBalanceView,
    FinanceDashboardBankStatusView,
    FinanceDashboardSettingsView,
    FinanceDashboardSummaryView,
    FinanceDashboardTransactionsView,
    FinanceDashboardTransferChainsView,
)
from .demo import FinanceDashboardDemoDataView, FinanceDashboardDemoToggleView
from .home import FinanceDashboardHomeView, FinanceDashboardPotsView
from .plan import (
    FinanceDashboardBenchmarkView,
    FinanceDashboardBudgetPlanView,
    FinanceDashboardPlanImportView,
    FinanceDashboardPlanIncomeView,
    FinanceDashboardPlanPositionView,
    FinanceDashboardPlanVsActualView,
    FinanceDashboardTransferPlanView,
)
from .refresh import (
    FinanceDashboardRefreshStatusView,
    FinanceDashboardRefreshTriggerView,
)

_LOGGER = logging.getLogger(__name__)

__all__ = [  # noqa: RUF022  # grouped by category, not alphabetical
    "async_register_api",
    # Helpers (re-exported for backwards-compat with tests that import from .api)
    "_get_manager",
    "_get_setup_client",
    # Data endpoints
    "FinanceDashboardBalanceView",
    "FinanceDashboardBankStatusView",
    "FinanceDashboardSettingsView",
    "FinanceDashboardTransactionsView",
    "FinanceDashboardSummaryView",
    "FinanceDashboardTransferChainsView",
    # Budget plan (migrated spreadsheet model)
    "FinanceDashboardBudgetPlanView",
    "FinanceDashboardTransferPlanView",
    "FinanceDashboardPlanVsActualView",
    "FinanceDashboardBenchmarkView",
    "FinanceDashboardPlanPositionView",
    "FinanceDashboardPlanIncomeView",
    "FinanceDashboardPlanImportView",
    # Home screen + pots
    "FinanceDashboardHomeView",
    "FinanceDashboardPotsView",
    "FinanceDashboardAssignmentsView",
    "FinanceDashboardContractsView",
    "FinanceDashboardContractView",
    "FinanceDashboardReservesView",
    "FinanceDashboardAccountSavingsView",
    # Refresh
    "FinanceDashboardRefreshStatusView",
    "FinanceDashboardRefreshTriggerView",
    # Demo
    "FinanceDashboardDemoToggleView",
    "FinanceDashboardDemoDataView",
]


async def async_register_api(hass: HomeAssistant) -> None:
    """Register all Finance HTTP API endpoints."""
    hass.http.register_view(FinanceDashboardBalanceView())
    hass.http.register_view(FinanceDashboardTransactionsView())
    hass.http.register_view(FinanceDashboardSummaryView())
    hass.http.register_view(FinanceDashboardRefreshStatusView())
    hass.http.register_view(FinanceDashboardRefreshTriggerView())
    # Bank linking lives in the config subentry flow (Settings -> Devices & services)
    hass.http.register_view(FinanceDashboardBankStatusView())
    hass.http.register_view(FinanceDashboardSettingsView())
    hass.http.register_view(FinanceDashboardTransferChainsView())
    hass.http.register_view(FinanceDashboardDemoToggleView())
    hass.http.register_view(FinanceDashboardDemoDataView())
    # Budget plan endpoints (migrated spreadsheet model)
    hass.http.register_view(FinanceDashboardBudgetPlanView())
    hass.http.register_view(FinanceDashboardTransferPlanView())
    hass.http.register_view(FinanceDashboardPlanVsActualView())
    hass.http.register_view(FinanceDashboardBenchmarkView())
    hass.http.register_view(FinanceDashboardPlanPositionView())
    hass.http.register_view(FinanceDashboardPlanIncomeView())
    hass.http.register_view(FinanceDashboardPlanImportView())
    hass.http.register_view(FinanceDashboardHomeView())
    hass.http.register_view(FinanceDashboardPotsView())
    hass.http.register_view(FinanceDashboardAssignmentsView())
    hass.http.register_view(FinanceDashboardContractsView())
    hass.http.register_view(FinanceDashboardContractView())
    hass.http.register_view(FinanceDashboardReservesView())
    hass.http.register_view(FinanceDashboardAccountSavingsView())
    _LOGGER.debug("Finance API endpoints registered")
