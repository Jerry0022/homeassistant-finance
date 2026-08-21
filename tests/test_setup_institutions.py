"""Tests for the setup-wizard institution catalog endpoint.

The bank list is the entry point of the whole product: when it fails the
user cannot connect anything.  Two properties are load-bearing.

1. The ``/aspsps`` catalog is served by Enable Banking, not by a bank, so
   it must NOT be gated by the 4/day per-ASPSP quota.  Gating it locked a
   rate-limited user out of adding any new bank.
2. A catalog fetch failure must degrade to the cached list rather than to
   an empty list, and must say so.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeStore:
    """Minimal stand-in for homeassistant.helpers.storage.Store."""

    def __init__(self, data=None):
        self.data = data
        self.saved = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.saved = data
        self.data = data


class _FakeHass:
    def __init__(self):
        self.data = {}


class _FakeRequest:
    def __init__(self, hass):
        self.app = {"hass": hass}


class _FakeManager:
    """Manager that reports itself as rate-limited."""

    def __init__(self, until):
        self.rate_limited_until = until

    async def async_make_setup_call(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("catalog must not be routed through the quota gate")


def _view():
    from custom_components.finance_dashboard.api.setup import (
        FinanceDashboardSetupInstitutionsView,
    )

    return FinanceDashboardSetupInstitutionsView()


def _body(response) -> dict:
    """Decode a HomeAssistantView JSON response body."""
    return json.loads(response.body)


@pytest.fixture
def patched(monkeypatch):
    """Patch the catalog store and client factory; return the knobs."""
    from custom_components.finance_dashboard.api import _helpers, setup

    state = {"store": _FakeStore(), "institutions": [], "error": None, "calls": 0}

    def _fake_store(hass):
        return state["store"]

    class _FakeClient:
        async def async_get_institutions(self, country):
            state["calls"] += 1
            if state["error"] is not None:
                raise state["error"]
            return state["institutions"]

    async def _fake_get_client(hass, *, enforce_rate_limit=True):
        state["enforce_rate_limit"] = enforce_rate_limit
        if enforce_rate_limit:
            from custom_components.finance_dashboard.enablebanking_client import (
                RateLimitExceeded,
            )

            raise RateLimitExceeded("quota gate hit")
        return _FakeClient()

    monkeypatch.setattr(_helpers, "_institution_store", _fake_store)
    monkeypatch.setattr(setup, "_get_setup_client", _fake_get_client)
    return state


# ---------------------------------------------------------------------------
# 1. Rate limit must not block the catalog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalog_served_while_rate_limited(patched):
    """A rate-limited user must still get the bank list.

    Regression: _get_setup_client enforced the ASPSP quota for the catalog,
    so after four refreshes the user could not add a bank until midnight.
    """
    hass = _FakeHass()
    hass.data["finance_dashboard"] = {
        "entry": None,
        "_global_rate_limit_until": (datetime.now(UTC) + timedelta(hours=5)).isoformat(),
    }
    patched["institutions"] = [{"id": "DKB", "name": "DKB", "bic": "BYLADEM1001"}]

    response = await _view().get(_FakeRequest(hass))
    body = _body(response)

    assert patched["enforce_rate_limit"] is False
    assert "error" not in body
    assert [i["name"] for i in body["institutions"]] == ["DKB"]


@pytest.mark.asyncio
async def test_catalog_not_routed_through_manager_quota_gate(patched):
    """The manager's quota proxy must not be used for the catalog."""
    hass = _FakeHass()
    # _FakeManager.async_make_setup_call raises if the endpoint routes through it
    hass.data["finance_dashboard"] = {
        "entry": None,
        "manager": _FakeManager(datetime.now(UTC) + timedelta(hours=5)),
    }
    patched["institutions"] = [{"id": "DKB", "name": "DKB"}]

    body = _body(await _view().get(_FakeRequest(hass)))
    assert body["institutions"]


# ---------------------------------------------------------------------------
# 2. Cache behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_cache_skips_api_call(patched):
    """A cache within TTL must be served without touching the API."""
    patched["store"] = _FakeStore(
        {
            "institutions": [{"id": "DKB", "name": "DKB"}],
            "cached_at": datetime.now(UTC).isoformat(),
        }
    )

    body = _body(await _view().get(_FakeRequest(_FakeHass())))

    assert patched["calls"] == 0
    assert body["institutions"][0]["name"] == "DKB"
    # A fresh cache is not a degraded state — no staleness hint
    assert "cached_at" not in body


@pytest.mark.asyncio
async def test_stale_cache_used_when_api_fails(patched):
    """An API failure must degrade to the stale list, flagged as cached."""
    stale_at = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    patched["store"] = _FakeStore(
        {"institutions": [{"id": "DKB", "name": "DKB"}], "cached_at": stale_at}
    )
    patched["error"] = Exception("500 upstream exploded")

    body = _body(await _view().get(_FakeRequest(_FakeHass())))

    assert body["institutions"][0]["name"] == "DKB"
    assert body["cached_at"] == stale_at
    assert "error" not in body


@pytest.mark.asyncio
async def test_empty_api_result_falls_back_to_cache(patched):
    """An empty list is a failure, not a valid answer — DE always has banks."""
    stale_at = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    patched["store"] = _FakeStore(
        {"institutions": [{"id": "DKB", "name": "DKB"}], "cached_at": stale_at}
    )
    patched["institutions"] = []

    body = _body(await _view().get(_FakeRequest(_FakeHass())))
    assert body["institutions"][0]["name"] == "DKB"


@pytest.mark.asyncio
async def test_error_surfaces_when_no_cache(patched):
    """Without a cache the real cause must reach the frontend."""
    patched["error"] = Exception("401 unauthorized")

    body = _body(await _view().get(_FakeRequest(_FakeHass())))

    assert body["error_type"] == "invalid_credentials"
    assert "institutions" not in body


@pytest.mark.asyncio
async def test_successful_fetch_is_cached(patched):
    """A successful fetch must persist so the next outage has a fallback."""
    patched["institutions"] = [{"id": "DKB", "name": "DKB"}]

    await _view().get(_FakeRequest(_FakeHass()))

    assert patched["store"].saved is not None
    assert patched["store"].saved["institutions"][0]["name"] == "DKB"
    assert patched["store"].saved["cached_at"]


# ---------------------------------------------------------------------------
# 3. The quota gate itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_setup_client_gate_is_opt_out(monkeypatch):
    """_get_setup_client must skip the quota gate when asked to.

    This is the invariant at the source: everything that does not talk to a
    bank (the catalog) passes enforce_rate_limit=False and must survive an
    active rate limit.
    """
    from custom_components.finance_dashboard.api import _helpers
    from custom_components.finance_dashboard.enablebanking_client import RateLimitExceeded

    hass = _FakeHass()
    hass.data["finance_dashboard"] = {
        "_global_rate_limit_until": (datetime.now(UTC) + timedelta(hours=5)).isoformat(),
    }

    class _FakeCredMgr:
        def __init__(self, hass):
            pass

        async def async_initialize(self):
            return None

        async def async_get_api_credentials(self):
            return {"application_id": "app", "private_key_pem": "pem"}

    monkeypatch.setattr(
        "custom_components.finance_dashboard.credential_manager.CredentialManager",
        _FakeCredMgr,
    )
    monkeypatch.setattr(
        "custom_components.finance_dashboard.enablebanking_client.EnableBankingClient",
        lambda *a, **kw: object(),
    )
    # _helpers imports async_get_clientsession at module level — patch it there
    monkeypatch.setattr(_helpers, "async_get_clientsession", lambda hass: None)

    # Gate enforced (default) — still blocked, the quota is real for ASPSP calls
    with pytest.raises(RateLimitExceeded):
        await _helpers._get_setup_client(hass)

    # Gate opted out — the catalog must get through
    assert await _helpers._get_setup_client(hass, enforce_rate_limit=False) is not None
