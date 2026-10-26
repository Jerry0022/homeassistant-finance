"""Balance statistics, diagnostics redaction and the options flow (fakes)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from custom_components.finance_dashboard import balance_statistics as stats
from custom_components.finance_dashboard.account_identity import account_key

IBAN = "DE89370400440532013000"
ACCOUNT = {"id": "uid-1", "iban": IBAN, "name": "Giro", "institution": "Testbank", "currency": "EUR"}


def _pt(at, type_, amount):
    return {"at": at, "type": type_, "amount": amount, "currency": "EUR"}


HISTORY = [
    # two types in one snapshot: booked wins over available
    _pt("2026-05-01T08:05:00+00:00", "ITAV", "999"),
    _pt("2026-05-01T08:05:00+00:00", "CLBD", "100"),
    # later snapshot in the same hour wins
    _pt("2026-05-01T08:50:00+00:00", "CLBD", "110"),
    _pt("2026-05-01T10:00:00+02:00", "CLBD", "120"),  # = 08:00 UTC -> same hour
    _pt("2026-05-02T09:30:00+00:00", "CLBD", "130"),
]


def test_statistic_id_is_sanitized():
    assert stats.statistic_id_for("AB-12 cd") == "finance_dashboard:balance_ab_12_cd"


def test_hourly_points_last_value_per_hour_and_booked_preferred():
    points, currency = stats.hourly_points(HISTORY)
    assert currency == "EUR"
    assert [h for h, _ in points] == [
        datetime(2026, 5, 1, 8, tzinfo=UTC),
        datetime(2026, 5, 2, 9, tzinfo=UTC),
    ]
    # 08:50 CLBD=110 is the latest instant in the 08:xx hour (10:00+02:00 is 08:00)
    assert [v for _, v in points] == [110.0, 130.0]
    assert all(h.tzinfo is not None and h.minute == 0 for h, _ in points)


def test_hourly_points_watermark_resends_only_last_hour_onwards():
    points, _ = stats.hourly_points(HISTORY, datetime(2026, 5, 2, 9, tzinfo=UTC))
    assert [v for _, v in points] == [130.0]


def test_metadata_feature_detects_new_fields():
    meta = stats._metadata("finance_dashboard:balance_x", "n", "EUR")
    assert meta["has_sum"] is False
    assert meta["source"] == "finance_dashboard"
    assert meta["unit_of_measurement"] == "EUR"
    from homeassistant.components.recorder.models import StatisticMetaData

    declared = StatisticMetaData.__annotations__
    assert ("unit_class" in meta) == ("unit_class" in declared)
    assert ("mean_type" in meta) == ("mean_type" in declared)
    if "mean_type" not in declared:
        assert meta["has_mean"] is False


class _Manager:
    _accounts = [ACCOUNT]

    def get_balance_history(self, key):
        assert key == account_key(ACCOUNT)
        return HISTORY


@pytest.mark.asyncio
async def test_import_sends_hourly_statistics_once(monkeypatch):
    from homeassistant.components import recorder
    from homeassistant.components.recorder import statistics as rec_stats

    sent: list = []
    monkeypatch.setattr(
        rec_stats, "async_add_external_statistics", lambda hass, meta, data: sent.append((meta, data))
    )

    async def _no_last(hass, statistic_id):
        return None

    monkeypatch.setattr(stats, "_last_imported", _no_last)
    monkeypatch.setattr(recorder, "get_instance", lambda hass: None)
    hass = SimpleNamespace(config=SimpleNamespace(components={"recorder"}))
    manager = _Manager()

    assert await stats.async_import_balance_statistics(hass, manager) == 2
    meta, data = sent[0]
    assert meta["statistic_id"] == f"finance_dashboard:balance_{account_key(ACCOUNT)}"
    assert meta["source"] == "finance_dashboard"
    assert meta["has_sum"] is False
    assert [d["state"] for d in data] == [110.0, 130.0]

    # second run: watermark is the last hour, only that hour is re-sent (upsert)
    assert await stats.async_import_balance_statistics(hass, manager) == 1
    assert [d["state"] for d in sent[1][1]] == [130.0]


@pytest.mark.asyncio
async def test_import_is_a_noop_without_recorder():
    hass = SimpleNamespace(config=SimpleNamespace(components=set()))
    assert await stats.async_import_balance_statistics(hass, _Manager()) == 0


@pytest.mark.asyncio
async def test_import_never_raises(monkeypatch):
    from homeassistant.components.recorder import statistics as rec_stats

    def boom(*a, **k):
        raise RuntimeError("recorder exploded")

    monkeypatch.setattr(rec_stats, "async_add_external_statistics", boom)

    async def _no_last(hass, statistic_id):
        return None

    monkeypatch.setattr(stats, "_last_imported", _no_last)
    hass = SimpleNamespace(config=SimpleNamespace(components={"recorder"}))
    assert await stats.async_import_balance_statistics(hass, _Manager()) == 0


# -- diagnostics --------------------------------------------------------------


class _Ledger:
    def account_keys(self):
        return [account_key(ACCOUNT)]

    def transactions(self, key):
        return [{"transactionAmount": {"amount": "-12.34"}, "remittanceInformation": ["Miete"]}] * 3


class _DiagManager:
    demo_mode = False
    _accounts = [ACCOUNT]
    _ledger = _Ledger()
    last_refresh_stats = {"outcome": "ok", "accounts": 1}

    def get_bank_status(self):
        return [
            {
                "bank_id": "b1",
                "title": "Testbank",
                "budget_used_today": 1,
                "budget_limit": 4,
                "last_error": None,
                "consent_state": "ok",
            }
        ]

    def get_balance_history(self, key):
        return HISTORY


@pytest.mark.asyncio
async def test_diagnostics_redacts_identity_secrets_and_money():
    from custom_components.finance_dashboard import diagnostics

    entry = SimpleNamespace(
        entry_id="e1",
        data={
            "application_id": "app-123-secret",
            "private_key": "-----BEGIN PRIVATE KEY-----abc",
            "accounts": [ACCOUNT],
        },
        options={"raw_retention_days": 400},
        subentries={
            "b1": SimpleNamespace(
                subentry_type="bank",
                data={
                    "aspsp_name": "Testbank",
                    "accounts": [{"uid": "uid-1", "identity_key": "secretkey"}],
                    "session_id": "sess-xyz",
                },
            )
        },
        runtime_data=None,
    )
    hass = SimpleNamespace(data={"finance_dashboard": {"e1": _DiagManager()}})
    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(result, default=str)

    for secret in (IBAN, "app-123-secret", "BEGIN PRIVATE", "sess-xyz", "secretkey", "Testbank", "-12.34"):
        assert secret not in dumped, secret
    assert result["manager"]["ledger_transactions"] == [3]
    assert result["manager"]["balance_points"] == [len(HISTORY)]
    assert result["manager"]["banks"][0]["budget_used_today"] == 1
    assert result["entry"]["options"] == {"raw_retention_days": 400}
    assert result["stores"]["ledger"] and result["stores"]["raw"]


# -- options flow -------------------------------------------------------------


def _flow(options=None):
    from custom_components.finance_dashboard.config_flow import FinanceDashboardOptionsFlow

    entry = SimpleNamespace(options=options or {}, data={})
    return FinanceDashboardOptionsFlow(entry), entry


@pytest.mark.asyncio
async def test_options_form_defaults_for_existing_installs():
    flow, _ = _flow({})
    result = await flow.async_step_init(None)
    schema = result["data_schema"].schema
    defaults = {str(k): k.default() for k in schema}
    assert defaults["raw_retention_days"] == 400
    assert defaults["show_household"] is True


@pytest.mark.asyncio
async def test_options_retention_has_a_floor_of_30_days():
    import voluptuous as vol

    flow, _ = _flow({})
    result = await flow.async_step_init(None)
    schema = result["data_schema"]
    base = {str(k): k.default() for k in schema.schema}
    assert schema({**base, "raw_retention_days": 30})["raw_retention_days"] == 30
    with pytest.raises(vol.Invalid):
        schema({**base, "raw_retention_days": 29})


@pytest.mark.asyncio
async def test_options_submit_keeps_options_the_form_does_not_show():
    flow, _ = _flow({"daily_refresh_hour": 5, "show_household": True})
    result = await flow.async_step_init({"show_household": False, "raw_retention_days": 90})
    assert result["data"] == {
        "daily_refresh_hour": 5,
        "show_household": False,
        "raw_retention_days": 90,
    }
