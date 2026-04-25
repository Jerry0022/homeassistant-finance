"""R9 — /refresh endpoint must require admin.

Tests the is_admin check on FinanceDashboardRefreshTriggerView.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_request(is_admin: bool) -> MagicMock:
    user = MagicMock()
    user.is_admin = is_admin
    request = MagicMock()
    request.get.side_effect = lambda key, default=None: user if key == "hass_user" else default
    hass = MagicMock()
    hass.data = {}
    request.app = {"hass": hass}
    return request


class _FakeJsonMixin:
    """Minimal stand-in for HomeAssistantView.json()."""

    def json(self, data, status_code=200):
        resp = MagicMock()
        resp._data = data
        resp._status = status_code
        return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_non_admin_gets_403() -> None:
    """Non-admin request to /refresh must return 403 admin_required."""
    from custom_components.finance_dashboard.api import FinanceDashboardRefreshTriggerView

    view = FinanceDashboardRefreshTriggerView()
    view.json = _FakeJsonMixin().json  # inject minimal json helper

    request = _make_request(is_admin=False)
    response = await view.post(request)

    assert response._status == 403, (
        f"Expected 403, got {response._status}"
    )
    assert response._data.get("error") == "admin_required", (
        f"Expected error='admin_required', got {response._data}"
    )


@pytest.mark.asyncio
async def test_refresh_missing_user_gets_403() -> None:
    """Request without hass_user must return 403."""
    from custom_components.finance_dashboard.api import FinanceDashboardRefreshTriggerView

    view = FinanceDashboardRefreshTriggerView()
    view.json = _FakeJsonMixin().json

    request = MagicMock()
    request.get.return_value = None  # no hass_user
    hass = MagicMock()
    hass.data = {}
    request.app = {"hass": hass}

    response = await view.post(request)

    assert response._status == 403


@pytest.mark.asyncio
async def test_refresh_admin_passes_gating() -> None:
    """Admin request must pass the is_admin gate (not get 403)."""
    from custom_components.finance_dashboard.api import (
        FinanceDashboardRefreshTriggerView,
        _get_manager,
    )

    view = FinanceDashboardRefreshTriggerView()
    view.json = _FakeJsonMixin().json

    request = _make_request(is_admin=True)

    # Patch _get_manager to return None so we get a clean 404 (not 403)
    with patch(
        "custom_components.finance_dashboard.api._get_manager",
        return_value=None,
    ):
        response = await view.post(request)

    # Should be 404 (not configured) — NOT 403 (admin gate)
    assert response._status == 404, (
        f"Expected 404 (no manager), got {response._status}"
    )
