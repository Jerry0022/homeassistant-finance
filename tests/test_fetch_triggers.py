"""Fetch triggers: only explicit import, setup and the daily schedule hit the bank."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "finance_dashboard"

LIVE_CALLS = {"async_refresh_transactions", "async_refresh_accounts", "_async_get_client"}
# Modules that host an explicit/scheduled entry point (or the manager itself).
ALLOWED = {
    "__init__.py",  # services + scheduled daily refresh
    "button.py",  # user button
    "api/refresh.py",  # explicit import endpoint
    "manager/__init__.py",
    "manager/_refresh.py",
}


def test_live_calls_only_from_known_trigger_modules():
    offenders = []
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(PKG).as_posix()
        if rel in ALLOWED:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in LIVE_CALLS:
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, f"unreviewed live-fetch call sites: {offenders}"


def test_coordinator_and_get_views_never_fetch():
    for rel in ("coordinator.py",):
        src = (PKG / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in LIVE_CALLS, f"{rel}:{node.lineno}"
    for path in (PKG / "api").glob("*.py"):
        if path.name == "refresh.py":
            continue
        src = path.read_text(encoding="utf-8")
        for name in LIVE_CALLS:
            assert name not in src, f"{path.name} references {name}"


def test_reprocess_core_has_no_client_access():
    src = (PKG / "manager" / "_persistence.py").read_text(encoding="utf-8")
    for name in LIVE_CALLS:
        assert name not in src


def _request(body, is_admin=True):
    user = MagicMock(is_admin=is_admin)
    request = MagicMock()
    request.get.side_effect = lambda k, d=None: user if k == "hass_user" else d
    request.app = {"hass": MagicMock(data={})}
    request.remote = "10.0.0.5"
    if isinstance(body, Exception):
        request.json = AsyncMock(side_effect=body)
    else:
        request.json = AsyncMock(return_value=body)
    return request


def _view(cls):
    view = cls()
    view.json = lambda data, status_code=200: MagicMock(_data=data, _status=status_code)
    return view


def _manager():
    manager = MagicMock()
    manager.rate_limited_until = None
    manager.async_refresh_transactions = AsyncMock()
    manager.async_refresh_accounts = AsyncMock()
    manager.async_reprocess_and_derive = AsyncMock(return_value={"outcome": "rebuilt"})
    manager.get_refresh_status.return_value = {}
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [{}, None, [], {"trigger": "panel_open"}, {"trigger": ""}, ValueError("no body")]
)
async def test_post_refresh_without_explicit_trigger_never_calls_bank(body):
    from custom_components.finance_dashboard.api import FinanceDashboardRefreshTriggerView

    manager = _manager()
    with patch("custom_components.finance_dashboard.api.refresh._get_manager", return_value=manager):
        response = await _view(FinanceDashboardRefreshTriggerView).post(_request(body))

    assert response._status == 400
    assert response._data["reason"] == "explicit_trigger_required"
    manager.async_refresh_transactions.assert_not_called()
    manager.async_refresh_accounts.assert_not_called()


@pytest.mark.asyncio
async def test_post_refresh_with_explicit_trigger_calls_bank_attended():
    from custom_components.finance_dashboard.api import FinanceDashboardRefreshTriggerView

    manager = _manager()
    with patch("custom_components.finance_dashboard.api.refresh._get_manager", return_value=manager):
        response = await _view(FinanceDashboardRefreshTriggerView).post(
            _request({"trigger": "user_import"})
        )

    assert response._data["ok"] is True
    manager.async_refresh_transactions.assert_awaited_once_with(psu_ip="10.0.0.5")


@pytest.mark.asyncio
async def test_reprocess_never_calls_bank():
    from custom_components.finance_dashboard.api.refresh import FinanceDashboardReprocessView

    manager = _manager()
    with patch("custom_components.finance_dashboard.api.refresh._get_manager", return_value=manager):
        response = await _view(FinanceDashboardReprocessView).post(_request({}))

    assert response._data["ok"] is True
    manager.async_reprocess_and_derive.assert_awaited_once()
    manager.async_refresh_transactions.assert_not_called()
    manager.async_refresh_accounts.assert_not_called()
