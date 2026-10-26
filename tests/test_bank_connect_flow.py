"""Tests for the bank-connect flow: helpers, subentry flow, main reconfigure, repairs.

The dev environment may run an HA release without config subentries
(< 2025.2).  The flow classes are therefore driven at unit level: HA's
``FlowHandler`` result builders are replaced by tiny recorders, so these tests
pin OUR logic (step order, data shape, secrets handling), not HA internals.
End-to-end behaviour needs a real HA >= 2025.2 and a bank (see the PR notes).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest

from custom_components.finance_dashboard import config_flow, connect, repairs
from custom_components.finance_dashboard.account_identity import identity_key
from custom_components.finance_dashboard.enablebanking_client import RateLimitExceeded

IBAN = "DE89370400440532013000"


def _hass(components=()):
    hass = MagicMock()
    hass.config.components = set(components)
    hass.data = {}
    return hass


def _client():
    c = MagicMock()
    c.async_get_institutions = AsyncMock(return_value=[{"name": "Sparkasse"}, {"name": "ING"}])
    c.async_create_auth = AsyncMock(
        return_value={"url": "https://bank.example/auth", "auth_id": "a"}
    )
    c.async_create_session = AsyncMock(
        return_value={
            "session_id": "SESSION-SECRET",
            "accounts": [{"id": "uid-1", "iban": IBAN, "name": "Giro", "currency": "EUR"}],
        }
    )
    c.async_get_account_details = AsyncMock(return_value={"account": {"iban": IBAN}})
    c.async_close = AsyncMock()
    return c


# --------------------------------------------------------------------------
# connect helpers
# --------------------------------------------------------------------------


def test_redirect_url_prefers_my():
    assert connect.get_redirect_url(_hass({"my"})) == "https://my.home-assistant.io/redirect/oauth"


def test_redirect_url_fallback_uses_configured_url(monkeypatch):
    monkeypatch.setattr(connect, "get_url", lambda hass, prefer_external=True: "https://ha.example")
    assert connect.get_redirect_url(_hass()) == "https://ha.example/auth/external/callback"


def test_redirect_url_empty_without_any_url(monkeypatch):
    def boom(hass, prefer_external=True):
        raise connect.NoURLAvailableError

    monkeypatch.setattr(connect, "get_url", boom)
    assert connect.get_redirect_url(_hass()) == ""


def test_state_is_core_compatible_jwt():
    hass = _hass()
    token = connect.encode_state(hass, "flow-1", "https://r")
    decoded = jwt.decode(token, hass.data["oauth2_jwt_secret"], algorithms=["HS256"])
    assert decoded == {"flow_id": "flow-1", "redirect_uri": "https://r"}


async def test_start_authorization_sends_my_redirect_and_state():
    hass, client = _hass({"my"}), _client()
    url, valid_until = await connect.async_start_authorization(hass, client, "f1", "ING", "DE")
    assert url == "https://bank.example/auth"
    kwargs = client.async_create_auth.call_args.kwargs
    assert kwargs["redirect_url"] == connect.MY_REDIRECT_URL
    assert kwargs["aspsp_name"] == "ING" and kwargs["valid_until"] == valid_until
    secret = hass.data["oauth2_jwt_secret"]
    assert jwt.decode(kwargs["state"], secret, algorithms=["HS256"])["flow_id"] == "f1"


async def test_start_authorization_without_url_fails_cleanly(monkeypatch):
    monkeypatch.setattr(connect, "get_redirect_url", lambda hass: "")
    with pytest.raises(connect.ConnectError) as err:
        await connect.async_start_authorization(_hass(), _client(), "f", "ING", "DE")
    assert err.value.reason == "no_url_available"


async def test_probe_accounts_returns_identity_not_iban():
    out = await connect.async_probe_accounts(
        _client(), "Sparkasse", [{"id": "uid-1", "iban": "", "name": "x"}]
    )
    expected = identity_key({"institution_id": "Sparkasse", "iban": IBAN, "id": "uid-1"})
    assert out == [{"uid": "uid-1", "identity_key": expected}]
    assert IBAN not in repr(out)


async def test_probe_accounts_rate_limit_does_not_block_linking():
    client = _client()
    client.async_get_account_details = AsyncMock(side_effect=RateLimitExceeded("limit"))
    out = await connect.async_probe_accounts(client, "Sparkasse", [{"id": "uid-1", "iban": IBAN}])
    assert out[0]["identity_key"] == identity_key(
        {"institution_id": "Sparkasse", "iban": IBAN, "id": "uid-1"}
    )


async def test_probe_accounts_failure_aborts():
    client = _client()
    client.async_get_account_details = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(connect.ConnectError) as err:
        await connect.async_probe_accounts(client, "ING", [{"id": "u", "iban": IBAN}])
    assert err.value.reason == "unknown"


async def test_complete_session_requires_accounts():
    client = _client()
    client.async_create_session = AsyncMock(return_value={"session_id": "s", "accounts": []})
    with pytest.raises(connect.ConnectError) as err:
        await connect.async_complete_session(client, "code")
    assert err.value.reason == "no_accounts"


async def test_bridge_delegates_unknown_flow_to_subentries():
    from homeassistant.data_entry_flow import UnknownFlow

    hass = _hass()
    original = AsyncMock(side_effect=UnknownFlow)
    hass.config_entries.flow.async_configure = original
    hass.config_entries.flow._finance_callback_bridge = False
    sub = MagicMock()
    sub.async_get = MagicMock()
    sub.async_configure = AsyncMock(return_value="resumed")
    hass.config_entries.subentries = sub
    connect.install_callback_bridge(hass)
    connect.install_callback_bridge(hass)  # idempotent
    assert await hass.config_entries.flow.async_configure("fid", {"code": "c"}) == "resumed"
    sub.async_configure.assert_awaited_once_with("fid", {"code": "c"})
    sub.async_get.side_effect = UnknownFlow
    with pytest.raises(UnknownFlow):
        await hass.config_entries.flow.async_configure("other", {})


# --------------------------------------------------------------------------
# Subentry flow (unit level)
# --------------------------------------------------------------------------


@pytest.fixture
def flow_cls(monkeypatch):
    cls = config_flow.BankSubentryFlow
    rec = lambda kind: lambda self, **kw: {"type": kind, **kw}  # noqa: E731
    monkeypatch.setattr(cls, "async_show_form", rec("form"), raising=False)
    monkeypatch.setattr(cls, "async_abort", rec("abort"), raising=False)
    monkeypatch.setattr(cls, "async_external_step", rec("external"), raising=False)
    monkeypatch.setattr(cls, "async_external_step_done", rec("external_done"), raising=False)
    monkeypatch.setattr(
        cls,
        "async_update_and_abort",
        lambda self, e, s, **kw: {"type": "update", **kw},
        raising=False,
    )
    monkeypatch.setattr(config_flow, "install_callback_bridge", lambda hass: None)
    if config_flow.ConfigSubentry is Any:  # HA without subentries: minimal stand-in

        def fake_subentry(**kw):
            return SimpleNamespace(subentry_id=uuid.uuid4().hex, **kw)

        monkeypatch.setattr(config_flow, "ConfigSubentry", fake_subentry)
    return cls


def _flow(flow_cls, client, entry=None, cred=None, reconf=None):
    f = flow_cls()
    f.hass = _hass({"my"})
    f.flow_id = "flow-1"
    f._client = client
    f._get_entry = lambda: entry or SimpleNamespace(subentries={})
    f._get_reconfigure_subentry = lambda: reconf
    return f


@pytest.fixture
def cred(monkeypatch):
    c = MagicMock()
    c.async_store_bank_session = AsyncMock()
    c.async_remove_bank_session = AsyncMock()
    monkeypatch.setattr(config_flow, "async_credentials", AsyncMock(return_value=c))
    return c


async def test_new_bank_full_flow(flow_cls, cred):
    client = _client()
    f = _flow(flow_cls, client)

    r = await f.async_step_user()
    assert r["step_id"] == "user" and "redirect_url" in r["description_placeholders"]
    assert r["description_placeholders"]["redirect_url"] == connect.MY_REDIRECT_URL

    r = await f.async_step_user({"aspsp_country": "de"})
    assert r["step_id"] == "bank"
    client.async_get_institutions.assert_awaited_once_with("DE")

    r = await f.async_step_bank({"aspsp_name": "Sparkasse"})
    assert r["type"] == "external" and r["url"] == "https://bank.example/auth"

    r = await f.async_step_authorize({"state": {}, "code": "CODE"})
    assert r["type"] == "external_done" and r["next_step_id"] == "finish"

    r = await f.async_step_finish()
    assert r == {"type": "abort", "reason": "bank_connected"}

    entry_added = f.hass.config_entries.async_add_subentry.call_args.args[1]
    data = dict(entry_added.data)
    assert set(data) == {"aspsp_name", "aspsp_country", "valid_until", "accounts"}
    assert data["accounts"][0]["uid"] == "uid-1"
    assert IBAN not in repr(data) and "SESSION-SECRET" not in repr(data)
    cred.async_store_bank_session.assert_awaited_once_with(
        entry_added.subentry_id, "SESSION-SECRET", data["valid_until"]
    )
    # session stored BEFORE the subentry (and its reload listeners) exist
    assert entry_added.unique_id == "DE:Sparkasse"
    # the full account records land in the entry, which the manager fetches from
    stored = f.hass.config_entries.async_update_entry.call_args.kwargs["data"]["accounts"]
    assert stored[0]["id"] == "uid-1" and stored[0]["iban"] == IBAN
    assert stored[0]["key"] == data["accounts"][0]["identity_key"]


async def test_duplicate_bank_is_rejected(flow_cls):
    entry = SimpleNamespace(subentries={"x": SimpleNamespace(unique_id="DE:ING")})
    f = _flow(flow_cls, _client(), entry=entry)
    f._country = "DE"
    r = await f.async_step_bank({"aspsp_name": "ING"})
    assert r == {"type": "abort", "reason": "already_configured"}


async def test_rejected_authorization_aborts(flow_cls):
    f = _flow(flow_cls, _client())
    await f.async_step_authorize({"state": {}, "error": "access_denied"})
    r = await f.async_step_finish()
    assert r == {"type": "abort", "reason": "authorization_rejected"}


async def test_failed_test_call_creates_nothing(flow_cls, cred):
    client = _client()
    client.async_get_account_details = AsyncMock(side_effect=RuntimeError("x"))
    f = _flow(flow_cls, client)
    f._code, f._aspsp_name = "CODE", "ING"
    r = await f.async_step_finish()
    assert r == {"type": "abort", "reason": "unknown"}
    cred.async_store_bank_session.assert_not_awaited()
    f.hass.config_entries.async_add_subentry.assert_not_called()


async def test_reconfigure_updates_existing_subentry(flow_cls, cred):
    sub = SimpleNamespace(
        subentry_id="SUB1", title="ING", data={"aspsp_name": "ING", "aspsp_country": "DE"}
    )
    f = _flow(flow_cls, _client(), reconf=sub)
    r = await f.async_step_reconfigure()
    assert r["step_id"] == "reconfigure" and r["description_placeholders"]["bank"] == "ING"
    r = await f.async_step_reconfigure({})
    assert r["type"] == "external"
    await f.async_step_authorize({"state": {}, "code": "C"})
    r = await f.async_step_finish()
    assert r["type"] == "update" and r["data"]["accounts"][0]["uid"] == "uid-1"
    cred.async_store_bank_session.assert_awaited_once()
    assert cred.async_store_bank_session.call_args.args[0] == "SUB1"
    f.hass.config_entries.async_add_subentry.assert_not_called()


# --------------------------------------------------------------------------
# Main entry credentials
# --------------------------------------------------------------------------


async def test_validate_credentials_paths(monkeypatch):
    assert await config_flow._async_validate_credentials(_hass(), "", "") == "missing_credentials"

    import custom_components.finance_dashboard.enablebanking_client as ebc

    def bad_key(*a, **k):
        raise ValueError("bad pem")

    monkeypatch.setattr(ebc, "EnableBankingClient", bad_key)
    assert (
        await config_flow._async_validate_credentials(_hass(), "id", "pem") == "invalid_key_format"
    )

    client = _client()
    monkeypatch.setattr(ebc, "EnableBankingClient", lambda *a, **k: client)
    assert await config_flow._async_validate_credentials(_hass(), "id", "pem") is None
    client.async_get_institutions = AsyncMock(return_value=[])
    assert await config_flow._async_validate_credentials(_hass(), "id", "pem") == "no_institutions"


def test_main_flow_exposes_bank_subentry_and_reconfigure():
    flow_cls = config_flow.FinanceDashboardConfigFlow
    types = flow_cls.async_get_supported_subentry_types(MagicMock())
    assert types == {"bank": config_flow.BankSubentryFlow}
    assert hasattr(flow_cls, "async_step_reconfigure")


# --------------------------------------------------------------------------
# Repairs
# --------------------------------------------------------------------------


def test_subentry_id_from_issue():
    assert repairs.subentry_id_from_issue("consent_expiring_ABC") == "ABC"
    assert repairs.subentry_id_from_issue("consent_expired_ABC") == "ABC"
    assert repairs.subentry_id_from_issue("credentials_missing") is None


async def test_fix_flow_guides_to_integration_page():
    hass = _hass()
    entry = SimpleNamespace(
        entry_id="E1",
        subentries={"ABC": SimpleNamespace(title="ING", data={"aspsp_name": "ING"})},
    )
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    flow = await repairs.async_create_fix_flow(hass, "consent_expired_ABC", None)
    flow.hass = hass
    flow.async_show_form = lambda **kw: {"type": "form", **kw}
    flow.async_abort = lambda **kw: {"type": "abort", **kw}
    r = await flow.async_step_init()
    assert r["description_placeholders"]["bank"] == "ING"
    assert "E1" in r["description_placeholders"]["link"]
    assert (await flow.async_step_init({}))["reason"] == "continue_in_integrations"

    hass.config_entries.async_entries = MagicMock(return_value=[])
    assert (await flow.async_step_init())["reason"] == "bank_not_found"


async def test_fix_flow_rejects_unknown_issue():
    with pytest.raises(ValueError):
        await repairs.async_create_fix_flow(_hass(), "something_else", None)


# --------------------------------------------------------------------------
# Old linking views are gone, startup registration still fine
# --------------------------------------------------------------------------


async def test_link_views_removed_and_registration_works():
    from custom_components.finance_dashboard import api
    from custom_components.finance_dashboard.api import _helpers

    assert not hasattr(_helpers, "_validate_oauth_state")
    hass = MagicMock()
    await api.async_register_api(hass)
    urls = {c.args[0].url for c in hass.http.register_view.call_args_list}
    assert not any("oauth/callback" in u or "/setup/" in u for u in urls)
    assert "/api/finance_dashboard/bank_status" in urls
