"""Budget plan endpoints — the migrated spreadsheet model.

All read endpoints are pure cache reads and never touch the banking API.

Provides:
- BudgetPlanView       — income breakdown, cost ledger, split result
- TransferPlanView     — the monthly transfer choreography
- PlanVsActualView     — planned vs. actually booked, per category and position
- BenchmarkView        — our ratios against German national averages
- PlanPositionView     — create/update/delete a cost position (admin)
- PlanIncomeView       — set a person's income entry (admin)
- PlanImportView       — import a household workbook (admin)

PRIVACY: individual cost positions name what a specific person spends money on,
so the itemised ledger is admin-only — the same rule the transactions endpoint
follows. Non-admin users receive the aggregates and the shared positions, which
is what the household agreed on collectively.

SECURITY: the import endpoint reads a file path supplied by the caller. Paths
are validated against Home Assistant's allowlist (``allowlist_external_dirs``),
so the endpoint cannot be used to read arbitrary files from the host.
"""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN, OWNER_SHARED
from ._helpers import _get_manager

_LOGGER = logging.getLogger(__name__)


def _month_year(request: web.Request) -> tuple[int | None, int | None]:
    """Read optional ``month``/``year`` query parameters.

    Invalid values fall back to None (current month) instead of erroring — a
    stray query string must not break the dashboard.
    """

    def _parse(name: str, low: int, high: int) -> int | None:
        raw = request.query.get(name)
        if not raw:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if low <= value <= high else None

    return (_parse("month", 1, 12), _parse("year", 1970, 2200))


def _is_admin(request: web.Request) -> bool:
    """Whether the calling user is a Home Assistant admin."""
    user = request.get("hass_user")
    return bool(user and user.is_admin)


class FinanceDashboardBudgetPlanView(HomeAssistantView):
    """Income breakdown, cost ledger and resulting split."""

    url = f"/api/{DOMAIN}/budget_plan"
    name = f"api:{DOMAIN}:budget_plan"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return the plan for the requested month (cache read)."""
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        month, year = _month_year(request)
        view = manager.get_budget_plan_view(month, year)

        if not _is_admin(request):
            # Aggregates and shared positions only — individual positions are
            # another person's private spending.
            view = dict(view)
            view["positions"] = [
                position
                for position in view.get("positions", [])
                if position.get("owner") == OWNER_SHARED
            ]
            view["restricted"] = True

        return self.json(view)


class FinanceDashboardTransferPlanView(HomeAssistantView):
    """The monthly transfer choreography."""

    url = f"/api/{DOMAIN}/transfer_plan"
    name = f"api:{DOMAIN}:transfer_plan"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return the transfer plan for the requested month (cache read)."""
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        month, year = _month_year(request)
        return self.json(manager.get_transfer_plan(month, year))


class FinanceDashboardPlanVsActualView(HomeAssistantView):
    """Planned figures against what the bank actually booked."""

    url = f"/api/{DOMAIN}/plan_vs_actual"
    name = f"api:{DOMAIN}:plan_vs_actual"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return the plan-vs-actual comparison (cache read)."""
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        month, year = _month_year(request)
        result = manager.get_plan_vs_actual(month, year)

        if not _is_admin(request):
            result = dict(result)
            result.pop("positions", None)
            result["restricted"] = True

        return self.json(result)


class FinanceDashboardBenchmarkView(HomeAssistantView):
    """Our spending ratios against German national averages."""

    url = f"/api/{DOMAIN}/benchmark"
    name = f"api:{DOMAIN}:benchmark"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return benchmark comparisons (cache read, no external fetch)."""
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        month, year = _month_year(request)
        return self.json(await manager.async_get_benchmarks(month, year))


class FinanceDashboardPlanPositionView(HomeAssistantView):
    """Create, update or delete a single cost position."""

    url = f"/api/{DOMAIN}/budget_plan/position"
    name = f"api:{DOMAIN}:budget_plan:position"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Create or update a cost position (admin only)."""
        hass = request.app["hass"]
        if not _is_admin(request):
            return self.json({"error": "Admin required"}, status_code=403)
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        try:
            data = await request.json()
        except ValueError:
            return self.json({"error": "Invalid JSON"}, status_code=400)

        try:
            position = await manager.async_set_cost_position(data)
        except ValueError as err:
            return self.json({"error": str(err)}, status_code=400)
        except Exception:
            _LOGGER.exception("Saving cost position failed")
            return self.json({"error": "Saving the position failed"}, status_code=500)

        return self.json({"ok": True, "position": position})

    async def delete(self, request: web.Request) -> web.Response:
        """Delete a cost position by id (admin only)."""
        hass = request.app["hass"]
        if not _is_admin(request):
            return self.json({"error": "Admin required"}, status_code=403)
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        position_id = request.query.get("id")
        if not position_id:
            return self.json({"error": "Missing id"}, status_code=400)

        removed = await manager.async_delete_cost_position(position_id)
        if not removed:
            return self.json({"error": "Unknown position"}, status_code=404)
        return self.json({"ok": True})


class FinanceDashboardPlanIncomeView(HomeAssistantView):
    """Set a person's planned income."""

    url = f"/api/{DOMAIN}/budget_plan/income"
    name = f"api:{DOMAIN}:budget_plan:income"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Create or update one person's income entry (admin only)."""
        hass = request.app["hass"]
        if not _is_admin(request):
            return self.json({"error": "Admin required"}, status_code=403)
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        try:
            data = await request.json()
        except ValueError:
            return self.json({"error": "Invalid JSON"}, status_code=400)

        try:
            entry = await manager.async_set_income(data)
        except ValueError as err:
            return self.json({"error": str(err)}, status_code=400)
        except Exception:
            _LOGGER.exception("Saving income entry failed")
            return self.json({"error": "Saving the income entry failed"}, status_code=500)

        return self.json({"ok": True, "income": entry})


class FinanceDashboardPlanImportView(HomeAssistantView):
    """Import a household workbook into the budget plan."""

    url = f"/api/{DOMAIN}/budget_plan/import"
    name = f"api:{DOMAIN}:budget_plan:import"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Replace the plan with the contents of a workbook (admin only).

        The path must lie inside a directory Home Assistant is configured to
        allow (``allowlist_external_dirs``) or inside the config directory.
        Without that check this endpoint would read any file on the host.
        """
        hass = request.app["hass"]
        if not _is_admin(request):
            return self.json({"error": "Admin required"}, status_code=403)
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        try:
            data = await request.json()
        except ValueError:
            return self.json({"error": "Invalid JSON"}, status_code=400)

        path = str(data.get("path") or "").strip()
        if not path:
            return self.json({"error": "Missing path"}, status_code=400)

        if not hass.config.is_allowed_path(path):
            _LOGGER.warning("Spreadsheet import rejected — path not allowed")
            return self.json(
                {
                    "error": (
                        "Path not allowed. Add its directory to "
                        "allowlist_external_dirs in configuration.yaml, or place "
                        "the file in the config directory."
                    )
                },
                status_code=400,
            )

        try:
            report = await manager.async_import_spreadsheet(path)
        except FileNotFoundError:
            return self.json({"error": "File not found"}, status_code=404)
        except ImportError as err:
            return self.json({"error": str(err)}, status_code=500)
        except ValueError as err:
            return self.json({"error": str(err)}, status_code=400)
        except Exception:
            _LOGGER.exception("Spreadsheet import failed")
            return self.json({"error": "Import failed — see the log"}, status_code=500)

        return self.json({"ok": True, "report": report})
