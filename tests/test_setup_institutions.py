"""Tests for the setup-client quota gate (``api/_helpers``).

The in-panel wizard and its views are gone (banks link through config
subentries).  The helper stays, and one invariant is load-bearing: the
``/aspsps`` catalog is served by Enable Banking, not by a bank, so it must
NOT be gated by the 4/day per-ASPSP quota.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


class _FakeHass:
    def __init__(self):
        self.data = {}


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
