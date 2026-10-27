"""Per-bank budget, two-layer storage, consent issues and migrations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.finance_dashboard.account_identity import account_key, identity_key
from custom_components.finance_dashboard.data_store import (
    EncryptedStore,
    Ledger,
    RawArchive,
    StorageDecryptError,
    fingerprint,
    is_pending_match,
)
from custom_components.finance_dashboard.enablebanking_client import (
    EnableBankingClient,
    RateLimitExceeded,
)
from custom_components.finance_dashboard.fetch_budget import FetchBudget
from tests.fakes import FakeCred, FakeEncryptedStore, FakeStore

NOW = datetime(2026, 3, 10, 6, 30, tzinfo=UTC)


def tx(tid="", date="2026-03-01", amount="-10.00", who="Shop", ref="card", status="BOOK"):
    return {
        "transactionId": tid,
        "bookingDate": date,
        "transactionAmount": {"amount": amount, "currency": "EUR"},
        "creditorName": who,
        "remittanceInformationUnstructured": ref,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Budget gating
# ---------------------------------------------------------------------------


def test_scheduled_background_may_use_one_of_four():
    b = FetchBudget()
    assert b.decide("bank", attended=False, scheduled=True, now=NOW).allowed
    b.record_attempt("bank", "acc", attended=False, now=NOW)
    again = b.decide("bank", attended=False, scheduled=True, now=NOW)
    assert not again.allowed and again.reason == "budget_exhausted"
    # a non-scheduled background caller may still use the other slots
    assert b.decide("bank", attended=False, scheduled=False, now=NOW).allowed


def test_background_hard_cap_is_four_per_account_per_utc_day():
    b = FetchBudget()
    for _ in range(4):
        b.record_attempt("bank", "acc", attended=False, now=NOW)
    assert not b.decide("bank", attended=False, now=NOW).allowed
    assert b.used_today("bank", NOW) == 4
    tomorrow = NOW + timedelta(days=1)
    assert b.used_today("bank", tomorrow) == 0
    assert b.decide("bank", attended=False, now=tomorrow).allowed


def test_attended_is_never_capped_or_blocked_but_debounced():
    b = FetchBudget()
    for _ in range(10):
        b.record_attempt("bank", "acc", attended=False, now=NOW)
    b.block("bank", now=NOW)
    first = b.decide("bank", attended=True, now=NOW)
    assert first.allowed  # exhausted AND blocked, attended still passes
    b.record_attempt("bank", "", attended=True, now=NOW)
    assert b.decide("bank", attended=True, now=NOW + timedelta(seconds=30)).reason == "debounced"
    assert b.decide("bank", attended=True, now=NOW + timedelta(seconds=61)).allowed
    # attended calls never consumed background budget
    assert b.used_today("bank", NOW) == 10


def test_429_blocks_only_that_bank_for_six_hours():
    b = FetchBudget()
    until = b.block("a", now=NOW)
    assert until - NOW == timedelta(hours=6)
    assert b.decide("a", attended=False, now=NOW).reason == "blocked"
    assert b.decide("b", attended=False, now=NOW).allowed
    assert b.decide("a", attended=False, now=NOW + timedelta(hours=6, seconds=1)).allowed
    # Retry-After wins
    assert b.block("a", retry_after_seconds=120, now=NOW) - NOW == timedelta(seconds=120)


def test_budget_day_follows_local_time_not_utc():
    # 00:19 in Berlin is still yesterday in UTC: the 06:30 call of the day
    # before must not show as "today" any more.
    from zoneinfo import ZoneInfo

    b = FetchBudget(tz=ZoneInfo("Europe/Berlin"))
    scheduled = datetime(2026, 10, 27, 5, 30, tzinfo=UTC)  # 06:30 local
    after_midnight = datetime(2026, 10, 27, 23, 19, tzinfo=UTC)  # 00:19 local
    b.record_attempt("bank", "acc", attended=False, now=scheduled)
    assert b.used_today("bank", scheduled) == 1
    assert b.used_today("bank", after_midnight) == 0


def test_status_exposes_last_manual_fetch():
    # Attended fetches never count against the budget, so the status has to
    # show them separately, or a manual refresh looks like it never happened.
    b = FetchBudget()
    assert b.status("bank", now=NOW)["last_attended_at"] is None
    b.record_attempt("bank", "", attended=True, now=NOW)
    status = b.status("bank", now=NOW)
    assert status["budget_used_today"] == 0
    assert status["last_attended_at"] == NOW.isoformat()


def test_budget_state_round_trips_and_exposes_status():
    b = FetchBudget()
    b.record_attempt("bank", "acc", attended=False, now=NOW)
    b.record_success("bank", NOW)
    b.record_error("bank", "http_500")
    b.block("bank", now=NOW)
    restored = FetchBudget()
    restored.load(b.to_dict())
    status = restored.status("bank", consent_valid_until="2026-06-01T00:00:00+00:00", now=NOW)
    assert status["budget_used_today"] == 1
    assert status["budget_limit"] == 4
    assert status["blocked_until"] is not None
    assert status["last_error"] == "http_500"
    assert status["consent_valid_until"].startswith("2026-06")


# ---------------------------------------------------------------------------
# Pagination loop guard
# ---------------------------------------------------------------------------


def _client(responses):
    client = EnableBankingClient.__new__(EnableBankingClient)
    calls = []

    async def fake_request(method, endpoint, **kwargs):
        calls.append(endpoint)
        return responses(len(calls))

    client._async_request = fake_request
    return client, calls


@pytest.mark.asyncio
async def test_account_details_uses_the_details_endpoint_and_nested_iban():
    # Enable Banking has no bare /accounts/{id}; it answered 404 and broke
    # every bank link right after the PSU authorised it.
    client, calls = _client(
        lambda n: {
            "account_id": {"iban": "DE00123456780000000000"},
            "name": "Girokonto",
            "currency": "EUR",
            "product": "Giro",
        }
    )
    details = await client.async_get_account_details("uid-1")
    assert calls == ["/accounts/uid-1/details"]
    assert details["account"]["iban"] == "DE00123456780000000000"
    assert details["account"]["name"] == "Girokonto"


@pytest.mark.asyncio
async def test_pagination_follows_keys_without_a_page_cap():
    pages = 25
    client, calls = _client(
        lambda n: {
            "transactions": [{"entry_reference": f"t{n}", "booking_date": "2026-03-01",
                              "transaction_amount": {"amount": "1", "currency": "EUR"},
                              "credit_debit_indicator": "DBIT", "status": "BOOK"}],
            "continuation_key": f"k{n}" if n < pages else None,
        }
    )
    result = await client.async_get_transactions("uid")
    assert len(result["booked"]) == pages and not result["truncated"]
    assert len(calls) == pages


@pytest.mark.asyncio
async def test_pagination_stops_on_repeated_continuation_key():
    client, calls = _client(lambda n: {"transactions": [], "continuation_key": "same"})
    result = await client.async_get_transactions("uid")
    assert result["truncated"] is True
    assert len(calls) == 2  # second response repeats the key -> stop


@pytest.mark.asyncio
async def test_pagination_stops_after_page_limit():
    client, calls = _client(lambda n: {"transactions": [], "continuation_key": f"k{n}"})
    result = await client.async_get_transactions("uid")
    assert result["truncated"] is True
    assert len(calls) == 200


@pytest.mark.asyncio
async def test_background_calls_carry_no_psu_headers():
    seen = {}

    class Resp:
        ok = True
        status = 200

        async def json(self):
            return []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Sess:
        def request(self, method, url, headers=None, **kw):
            seen.update(headers)
            return Resp()

    client = EnableBankingClient.__new__(EnableBankingClient)
    client._session = Sess()
    client._generate_jwt = lambda: "jwt"
    await client.async_get_balances("uid")
    assert "Psu-Ip-Address" not in seen and "Psu-User-Agent" not in seen
    await client.async_get_balances("uid", psu_ip="10.0.0.5")
    assert seen["Psu-Ip-Address"] == "10.0.0.5" and "Psu-User-Agent" in seen


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def test_ledger_dedupes_by_id_and_strips_derived_fields():
    led = Ledger(None)
    t = tx("a")
    t["category"] = "food"
    t["_account_person"] = "x"
    led.ingest("k", [t, dict(t)], [], date_from="2026-02-01")
    led.ingest("k", [tx("a"), tx("b", date="2026-03-02")], [], date_from="2026-02-01")
    stored = led.transactions("k")
    assert sorted(x["transactionId"] for x in stored) == ["a", "b"]
    assert all("category" not in x and "_account_person" not in x for x in stored)


def test_ledger_fingerprint_fallback_and_identical_payments_survive():
    led = Ledger(None)
    one = tx("", date="2026-03-01", amount="-3.50", who="Cafe", ref="coffee")
    led.ingest("k", [one, dict(one)], [], date_from="2026-02-01")
    assert len(led.transactions("k")) == 2  # two real identical payments
    led.ingest("k", [one, dict(one)], [], date_from="2026-02-01")
    assert len(led.transactions("k")) == 2  # re-fetch is idempotent
    assert fingerprint(one) == fingerprint(dict(one))
    assert fingerprint(one) != fingerprint(tx("", amount="-3.51", who="Cafe", ref="coffee"))


def test_pending_replaced_by_booked_counterpart():
    led = Ledger(None)
    pend = tx("", date="2026-03-01", amount="-20.00", who="Shop", ref="x", status="PDNG")
    led.ingest("k", [], [pend], date_from="2026-02-01")
    assert [t["_status"] for t in led.transactions("k")] == ["pending"]
    booked = tx("b1", date="2026-03-03", amount="-20.00", who="Shop", ref="x")
    assert is_pending_match(pend, booked)
    led.ingest("k", [booked], [pend], date_from="2026-02-01")
    assert [t["_status"] for t in led.transactions("k")] == ["booked"]
    far = tx("b2", date="2026-03-09", amount="-20.00", who="Shop", ref="x")
    assert not is_pending_match(pend, far)


def test_ledger_drops_reversals_inside_window_but_not_when_truncated():
    led = Ledger(None)
    led.ingest("k", [tx("old", date="2026-01-01"), tx("gone", date="2026-03-01")], [],
               date_from="2025-12-01")
    led.ingest("k", [], [], date_from="2026-02-20")
    assert [t["transactionId"] for t in led.transactions("k")] == ["old"]
    led.ingest("k", [tx("x", date="2026-03-01")], [], date_from="2025-12-01")
    led.ingest("k", [], [], date_from="2026-02-20", truncated=True)
    assert "x" in [t["transactionId"] for t in led.transactions("k")]


def test_incremental_window_uses_last_booked_minus_overlap():
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    mgr = FinanceDashboardManager.__new__(FinanceDashboardManager)
    mgr._ledger = Ledger(None)
    recent = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d")
    mgr._ledger.ingest("k", [tx("a", date=recent)], [], date_from="2000-01-01")
    start = mgr._fetch_date_from("k", None)
    expected = (datetime.fromisoformat(recent) - timedelta(days=7)).strftime("%Y-%m-%d")
    assert start == expected
    first = mgr._fetch_date_from("fresh", None)
    assert (datetime.now(UTC) - datetime.fromisoformat(first).replace(tzinfo=UTC)).days in (90, 91)
    assert mgr._fetch_date_from("k", 400) < start


def test_balance_series_one_point_per_type_per_fetch():
    led = Ledger(None)
    bals = [
        {"balanceType": "closingBooked", "balanceAmount": {"amount": "10.00", "currency": "EUR"}},
        {"balanceType": "expected", "balanceAmount": {"amount": "8.00", "currency": "EUR"}},
    ]
    led.add_balances("k", bals, "2026-03-01T06:00:00+00:00")
    led.add_balances("k", bals, "2026-03-02T06:00:00+00:00")
    assert len(led.balance_series("k")) == 4


# ---------------------------------------------------------------------------
# Encryption + versioned stores + raw archive
# ---------------------------------------------------------------------------


def _enc_store(cred, migrate=None, version=1, minor=1):
    store = EncryptedStore(MagicMock(), cred, "k", version, minor, migrate)
    store._store = FakeStore()
    return store


@pytest.mark.asyncio
async def test_encrypted_store_round_trip_is_not_plaintext():
    cred = FakeCred()
    store = _enc_store(cred)
    await store.async_save({"iban": "DE00123456780000000000", "n": 1})
    on_disk = store._store._data
    assert "DE00" not in str(on_disk)
    assert await store.async_load() == {"iban": "DE00123456780000000000", "n": 1}


@pytest.mark.asyncio
async def test_wrong_key_raises_decrypt_error():
    store = _enc_store(FakeCred())
    await store.async_save({"a": 1})
    other = _enc_store(FakeCred())
    other._store = store._store
    with pytest.raises(StorageDecryptError):
        await other.async_load()


@pytest.mark.asyncio
async def test_envelope_migration_decrypts_migrates_and_reencrypts():
    cred = FakeCred()

    async def migrate(major, minor, payload):
        payload["migrated_from"] = [major, minor]
        return payload

    store = _enc_store(cred, migrate=migrate, version=2)
    old = {"enc": cred.encrypt_json({"x": 1})}
    new = await store.async_migrate_envelope(1, 1, old)
    assert cred.decrypt_json(new["enc"]) == {"x": 1, "migrated_from": [1, 1]}


@pytest.mark.asyncio
async def test_raw_archive_snapshots_chunk_by_month_and_prune():
    cred = FakeCred()
    archive = RawArchive(MagicMock(), cred, retention_days=400)
    archive._index_store = FakeStore()
    stores: dict[str, EncryptedStore] = {}

    def month_store(month):
        if month not in stores:
            stores[month] = _enc_store(cred)
        return stores[month]

    archive._month_store = month_store

    def snap(at):
        return RawArchive.make_snapshot(
            bank="b", account="u", kind="balances", attended=False, http_status=200,
            response={"balances": [{"x": 1}]}, fetched_at=at,
        )

    now = datetime(2026, 3, 10, tzinfo=UTC)
    archive.record(snap("2026-03-01T06:00:00+00:00"))
    archive.record(snap("2026-02-01T06:00:00+00:00"))
    archive.record(snap("2024-12-01T06:00:00+00:00"))  # > 400 days old
    await archive.async_flush(now)
    assert set(stores) >= {"2026_03", "2026_02"}
    got = await archive.async_read_month("2026_03")
    assert got[0]["response"] == {"balances": [{"x": 1}]} and got[0]["attended"] is False
    assert "2024_12" not in (await archive._index_store.async_load())["months"]


# ---------------------------------------------------------------------------
# Credential manager: per-bank sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bank_sessions_are_encrypted_and_independent():
    from cryptography.fernet import Fernet, MultiFernet

    from custom_components.finance_dashboard.credential_manager import CredentialManager

    cm = CredentialManager.__new__(CredentialManager)
    cm._hass = MagicMock()
    cm._token_store = FakeStore()
    cm._audit_store = FakeStore()
    cm._fernet = MultiFernet([Fernet(Fernet.generate_key())])
    cm._last_activity = 0.0
    cm._session_active = False

    await cm.async_store_bank_session("sub1", "SECRET-1", "2026-09-01T00:00:00+00:00")
    await cm.async_store_bank_session("sub2", "SECRET-2", "2026-10-01T00:00:00+00:00")
    assert "SECRET" not in str(cm._token_store._data)
    assert (await cm.async_get_bank_session("sub1"))["session_id"] == "SECRET-1"
    assert (await cm.async_get_bank_session("sub2"))["valid_until"].startswith("2026-10")
    await cm.async_remove_bank_session("sub1")
    assert await cm.async_get_bank_session("sub1") is None
    assert await cm.async_get_bank_session("sub2") is not None
    # round trip of the generic helpers
    assert cm.decrypt_json(cm.encrypt_json({"a": 1})) == {"a": 1}


# ---------------------------------------------------------------------------
# Manager: per-bank refresh, migrations, consent
# ---------------------------------------------------------------------------


def _account(uid, iban, bank_name="Bank"):
    return {"id": uid, "iban": iban, "name": f"acc-{uid}", "institution": bank_name,
            "currency": "EUR"}


class FakeClient:
    def __init__(self, behaviour=None):
        self.behaviour = behaviour or {}
        self.tx_calls = []

    async def async_get_transactions(self, uid, date_from, date_to, psu_ip=None, on_response=None):
        self.tx_calls.append((uid, date_from, psu_ip))
        action = self.behaviour.get(uid)
        if isinstance(action, Exception):
            raise action
        body = {"transactions": [{"entry_reference": f"{uid}-1"}]}
        if on_response:
            on_response("transactions", 200, body)
        return {"booked": [tx(f"{uid}-1", date="2026-03-01")], "pending": [], "truncated": False}

    async def async_get_balances(self, uid, psu_ip=None, on_response=None):
        return [{"balanceType": "closingBooked",
                 "balanceAmount": {"amount": "5.00", "currency": "EUR"}}]


def _sub(sub_id, uids, valid_until="2026-12-01T00:00:00+00:00", name="Bank"):
    return SimpleNamespace(
        subentry_id=sub_id,
        subentry_type="bank",
        title=name,
        data={"aspsp_name": name, "valid_until": valid_until,
              "accounts": [{"uid": u, "identity_key": ""} for u in uids]},
    )


def _manager(subs, accounts, client):
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    entry = SimpleNamespace(data={"accounts": accounts}, options={},
                            subentries={s.subentry_id: s for s in subs}, entry_id="e")
    hass = MagicMock()
    hass.data = {}
    mgr = FinanceDashboardManager(hass, entry)
    mgr._ledger = Ledger(FakeEncryptedStore())
    mgr._transfer_override_store = FakeStore()
    cred = AsyncMock()
    cred.async_get_bank_session.side_effect = lambda sid: {
        "session_id": "s", "valid_until": next(
            s.data["valid_until"] for s in subs if s.subentry_id == sid)}
    mgr._credential_manager = cred
    mgr._banking_client = client
    mgr._categorizer = MagicMock()
    mgr._categorizer.categorize.return_value = "other"
    return mgr


@pytest.mark.asyncio
async def test_bank_linked_without_entry_accounts_is_still_fetched():
    # 0.16.0/0.16.1 wrote the subentry refs but not entry.data["accounts"]:
    # the refresh then "reached no account" and showed 0 transactions.
    client = FakeClient()
    sub = _sub("b1", ["u1", "u2"], name="DKB")
    mgr = _manager([sub], [], client)
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")
    assert {call[0] for call in client.tx_calls} == {"u1", "u2"}
    targets = await mgr._async_bank_targets()
    assert [a["name"] for a in targets[0]["accounts"]] == ["DKB 1", "DKB 2"]


@pytest.mark.asyncio
async def test_fetch_window_never_ends_in_the_banks_future():
    # 2026-10-28 00:19 Berlin = 2026-10-27 23:19 UTC.  A local date_to of
    # 2026-10-28 made PayPal answer HTTP 422 for every refresh until 01:00.
    from zoneinfo import ZoneInfo

    from homeassistant.util import dt as dt_util

    class DateClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.windows = []

        async def async_get_transactions(self, uid, date_from, date_to, psu_ip=None,
                                         on_response=None):
            self.windows.append((date_from, date_to))
            return await super().async_get_transactions(uid, date_from, date_to, psu_ip,
                                                        on_response)

    utc_now = datetime(2026, 10, 27, 23, 19, tzinfo=UTC)
    local_now = utc_now.astimezone(ZoneInfo("Europe/Berlin"))
    client = DateClient()
    mgr = _manager([_sub("b1", ["u1"])], [_account("u1", "DE111")], client)
    with patch.object(dt_util, "utcnow", return_value=utc_now), \
            patch.object(dt_util, "now", return_value=local_now):
        await mgr.async_refresh_transactions(days=90, psu_ip="10.0.0.9")
    assert client.windows, "the account was not fetched"
    for date_from, date_to in client.windows:
        assert date_to == "2026-10-27"
        assert date_from <= date_to


@pytest.mark.asyncio
async def test_429_blocks_only_the_affected_bank():
    accounts = [_account("u1", "DE111"), _account("u2", "DE222")]
    client = FakeClient({"u1": RateLimitExceeded("429")})
    mgr = _manager([_sub("b1", ["u1"]), _sub("b2", ["u2"])], accounts, client)
    await mgr.async_refresh_transactions()
    status = {s["bank_id"]: s for s in mgr.get_bank_status()}
    assert status["b1"]["blocked_until"] is not None
    assert status["b2"]["blocked_until"] is None and status["b2"]["last_success"]
    assert mgr.last_refresh_stats["outcome"] == "rate_limited"
    assert mgr.rate_limited_until is None  # b2 is still fetchable
    # next background refresh skips b1 without calling it
    client.tx_calls.clear()
    await mgr.async_refresh_transactions()
    assert all(call[0] != "u1" for call in client.tx_calls)
    # ...but an attended refresh is not gated
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")
    assert any(call[0] == "u1" and call[2] == "10.0.0.9" for call in client.tx_calls)


@pytest.mark.asyncio
async def test_scheduled_refresh_uses_one_slot_and_attended_is_debounced():
    accounts = [_account("u1", "DE111")]
    client = FakeClient()
    mgr = _manager([_sub("b1", ["u1"])], accounts, client)
    await mgr.async_refresh_transactions(scheduled=True)
    assert mgr.get_bank_status()[0]["budget_used_today"] == 1
    client.tx_calls.clear()
    await mgr.async_refresh_transactions(scheduled=True)  # second scheduled: refused
    assert client.tx_calls == []
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")
    assert len(client.tx_calls) == 1
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")  # debounced
    assert len(client.tx_calls) == 1
    assert mgr.get_bank_status()[0]["budget_used_today"] == 1


@pytest.mark.asyncio
async def test_refresh_fills_ledger_derives_views_and_persists_encrypted_state():
    accounts = [_account("u1", "DE111")]
    mgr = _manager([_sub("b1", ["u1"])], accounts, FakeClient())
    await mgr.async_refresh_transactions()
    key = account_key(accounts[0])
    assert [t["transactionId"] for t in mgr.get_ledger_transactions(key)] == ["u1-1"]
    assert mgr._tx_by_account["u1"][0]["_account_name"] == "acc-u1"
    assert "category" not in mgr.get_ledger_transactions(key)[0]
    assert len(mgr.get_balance_history(key)) == 1
    saved = mgr._ledger._store._data
    assert saved["meta"]["bank_budget"]["b1"]["last_success"]


@pytest.mark.asyncio
async def test_401_marks_consent_expired_issue():
    accounts = [_account("u1", "DE111")]
    err = aiohttp.ClientResponseError(MagicMock(), (), status=401)
    mgr = _manager([_sub("b1", ["u1"])], accounts, FakeClient({"u1": err}))
    with patch("homeassistant.helpers.issue_registry.async_create_issue") as create, patch(
        "homeassistant.helpers.issue_registry.async_delete_issue"
    ):
        await mgr.async_refresh_transactions()
    ids = [c.args[2] for c in create.call_args_list]
    assert "consent_expired_b1" in ids
    kwargs = next(c.kwargs for c in create.call_args_list if c.args[2] == "consent_expired_b1")
    assert kwargs["is_fixable"] is True and kwargs["translation_key"] == "consent_expired"
    assert set(kwargs["translation_placeholders"]) == {"bank"}


@pytest.mark.asyncio
async def test_consent_issues_expiring_expired_and_cleared_on_renewal():
    soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    far = (datetime.now(UTC) + timedelta(days=90)).isoformat()
    subs = [_sub("a", ["u1"], soon), _sub("b", ["u2"], past), _sub("c", ["u3"], far)]
    accounts = [_account("u1", "DE1"), _account("u2", "DE2"), _account("u3", "DE3")]
    mgr = _manager(subs, accounts, FakeClient())
    with patch("homeassistant.helpers.issue_registry.async_create_issue") as create, patch(
        "homeassistant.helpers.issue_registry.async_delete_issue"
    ) as delete:
        await mgr.async_update_consent_issues()
    created = {c.args[2]: c.kwargs for c in create.call_args_list}
    assert set(created) == {"consent_expiring_a", "consent_expired_b"}
    assert created["consent_expiring_a"]["severity"].name == "WARNING"
    assert created["consent_expired_b"]["severity"].name == "ERROR"
    deleted = {c.args[2] for c in delete.call_args_list}
    assert {"consent_expiring_c", "consent_expired_c"} <= deleted
    # renewal: expired bank gets a new valid_until -> issues removed
    subs[1].data["valid_until"] = far
    with patch("homeassistant.helpers.issue_registry.async_create_issue") as create, patch(
        "homeassistant.helpers.issue_registry.async_delete_issue"
    ) as delete:
        await mgr.async_update_consent_issues()
    assert "consent_expired_b" in {c.args[2] for c in delete.call_args_list}
    assert "consent_expired_b" not in {c.args[2] for c in create.call_args_list}


@pytest.mark.asyncio
async def test_expired_consent_skips_the_bank():
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    client = FakeClient()
    mgr = _manager([_sub("b1", ["u1"], past)], [_account("u1", "DE1")], client)
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")
    assert client.tx_calls == []
    assert mgr.last_refresh_stats["outcome"] == "error"


@pytest.mark.asyncio
async def test_legacy_session_migrates_to_one_bank_subentry(monkeypatch):
    import homeassistant.config_entries as ce

    class FakeSubentry:
        def __init__(self, data, subentry_type, title, unique_id):
            self.data, self.subentry_type, self.title = data, subentry_type, title
            self.subentry_id = "NEWID"

    monkeypatch.setattr(ce, "ConfigSubentry", FakeSubentry, raising=False)
    accounts = [_account("u1", "DE111", "DKB")]
    mgr = _manager([], accounts, FakeClient())
    mgr._credential_manager.async_get_session.return_value = {
        "session_id": "legacy-s", "valid_until": "2026-12-01T00:00:00+00:00"}
    new_id = await mgr.async_migrate_legacy_session()
    assert new_id == "NEWID"
    mgr._credential_manager.async_store_bank_session.assert_awaited_once_with(
        "NEWID", "legacy-s", "2026-12-01T00:00:00+00:00")
    entry, sub = mgr._hass.config_entries.async_add_subentry.call_args.args
    assert sub.subentry_type == "bank" and sub.data["aspsp_name"] == "DKB"
    assert sub.data["accounts"] == [{"uid": "u1", "identity_key": account_key(accounts[0])}]


@pytest.mark.asyncio
async def test_without_subentries_the_legacy_bank_keeps_working():
    client = FakeClient()
    mgr = _manager([], [_account("u1", "DE111")], client)
    mgr._credential_manager.async_get_session.return_value = None
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")
    assert len(client.tx_calls) == 1
    assert mgr.get_bank_status()[0]["bank_id"] == "legacy"


@pytest.mark.asyncio
async def test_plaintext_cache_migrates_into_ledger_and_is_deleted():
    accounts = [_account("u1", "DE111")]
    mgr = _manager([], accounts, FakeClient())
    mgr._credential_manager.async_initialize = AsyncMock()
    legacy = {
        "tx_by_account": {"u1": [dict(tx("t1"), category="food", _status="booked",
                                       _account_person="a")]},
        "balances": {}, "last_refresh": "2026-03-01T06:00:00+00:00", "last_refresh_stats": {},
    }
    mgr._transaction_store = FakeStore()
    mgr._transaction_store._data = legacy
    with patch("custom_components.finance_dashboard.credential_manager.CredentialManager",
               return_value=mgr._credential_manager), patch(
        "custom_components.finance_dashboard.categorizer.TransactionCategorizer",
        return_value=mgr._categorizer):
        await mgr.async_initialize()
    assert mgr._transaction_store.removed is True
    stored = mgr._ledger._store._data
    assert "category" not in stored["accounts"][account_key(accounts[0])]["transactions"][0]
    assert mgr._tx_by_account["u1"][0]["transactionId"] == "t1"
    assert str(mgr._last_refresh).startswith("2026-03-01")


# ---------------------------------------------------------------------------
# Identity for IBAN-less accounts
# ---------------------------------------------------------------------------


def test_iban_identity_is_unchanged():
    a = {"institution": "DKB", "iban": "de89 3704 0044 0532 0130 00", "id": "uid-1"}
    b = {"institution": "DKB", "iban": "DE89370400440532013000", "id": "uid-2"}
    assert identity_key(a) == identity_key(b)
    import hashlib
    assert identity_key(a) == hashlib.sha256(
        b"iban|DKB|DE89370400440532013000").hexdigest()[:16]


def test_card_without_iban_is_stable_across_relinks():
    first = {"institution": "DKB", "iban": "", "id": "uid-A", "name": "Visa Card",
             "currency": "EUR", "account_type": "CARD"}
    second = dict(first, id="uid-B")
    assert identity_key(first) == identity_key(second)
    assert identity_key(first) != identity_key(dict(first, name="Other Card"))
    assert identity_key(first) != identity_key(dict(first, institution="ING"))


def test_card_identification_beats_name_and_pan_is_normalised():
    a = {"institution": "DKB", "iban": "", "id": "1", "identification": "4999 **** 1234",
         "name": "Visa"}
    b = {"institution": "DKB", "iban": "", "id": "2", "identification": "4999****1234",
         "name": "Renamed"}
    assert identity_key(a) == identity_key(b)
    assert account_key(dict(a, key="stored")) == "stored"


@pytest.mark.asyncio
async def test_orphan_bank_sessions_are_removed():
    subs = [_sub("a", ["u1"]), _sub("b", ["u2"])]
    mgr = _manager(subs, [_account("u1", "DE1"), _account("u2", "DE2")], FakeClient())
    assert await mgr.async_prune_orphan_sessions() == []
    del mgr._entry.subentries["b"]
    assert await mgr.async_prune_orphan_sessions() == ["b"]
    mgr._credential_manager.async_remove_bank_session.assert_awaited_once_with("b")
    assert await mgr.async_prune_orphan_sessions() == []
