"""Full-history backfill, lifelong retention and rebuild from the raw archive."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.finance_dashboard.const import (
    HISTORY_BACKFILL_DAYS,
    PROCESSING_VERSION,
    STORAGE_KEY_LEDGER_BACKUP,
)
from custom_components.finance_dashboard.data_store import (
    EncryptedStore,
    Ledger,
    RawArchive,
    StorageDecryptError,
)
from custom_components.finance_dashboard.enablebanking_client import EnableBankingClient
from custom_components.finance_dashboard.reprocess import merge_uncovered, replay
from tests.fakes import FakeCred, FakeEncryptedStore, FakeStore


def tx(tid, date, amount="-10.00"):
    return {
        "transactionId": tid,
        "bookingDate": date,
        "transactionAmount": {"amount": amount, "currency": "EUR"},
        "creditorName": "Shop",
        "remittanceInformationUnstructured": "ref",
    }


def eb_tx(ref, date, amount="10.00", status="BOOK"):
    """A transaction as Enable Banking sends it (raw)."""
    return {
        "entry_reference": ref,
        "booking_date": date,
        "transaction_amount": {"amount": amount, "currency": "EUR"},
        "credit_debit_indicator": "DBIT",
        "status": status,
        "creditor": {"name": "Shop"},
        "remittance_information": ["ref"],
    }


def _archive(cred=None, retention=0):
    cred = cred or FakeCred()
    archive = RawArchive(MagicMock(), cred, retention_days=retention)
    archive._index_store = FakeStore()
    stores: dict[str, EncryptedStore] = {}

    def month_store(month):
        if month not in stores:
            store = EncryptedStore(MagicMock(), cred, month, 1, 1)
            store._store = FakeStore()
            stores[month] = store
        return stores[month]

    archive._month_store = month_store
    archive.stores = stores
    return archive


# ---------------------------------------------------------------------------
# Ledger: lifelong, and never shortened by a short bank answer
# ---------------------------------------------------------------------------


def test_short_answer_to_a_long_request_keeps_older_history():
    led = Ledger(None)
    led.ingest(
        "k", [tx("2019", "2019-05-01"), tx("2025", "2025-12-01")], [], date_from="2019-01-01"
    )
    # A later ten-year request that the bank answers with only recent months.
    led.ingest("k", [tx("2026", "2026-02-01")], [], date_from="2016-03-01")
    ids = {t["transactionId"] for t in led.transactions("k")}
    # 2025-12-01 lies before the earliest date the bank reported (2026-02-01):
    # absence there proves nothing, so it stays — as does 2019.
    assert ids == {"2019", "2025", "2026"}


def test_reversal_inside_the_reported_span_is_still_dropped():
    led = Ledger(None)
    led.ingest("k", [tx("a", "2026-02-01"), tx("gone", "2026-02-10")], [], date_from="2026-01-01")
    led.ingest("k", [tx("a", "2026-02-01")], [], date_from="2026-01-01")
    assert [t["transactionId"] for t in led.transactions("k")] == ["a"]


def test_balance_series_is_lifelong():
    led = Ledger(None)
    bal = [{"balanceType": "CLBD", "balanceAmount": {"amount": "1", "currency": "EUR"}}]
    for i in range(6000):
        led.add_balances("k", bal, f"2016-01-01T00:00:{i:05d}")
    assert len(led.balance_series("k")) == 6000


@pytest.mark.asyncio
async def test_raw_archive_keeps_everything_by_default():
    archive = _archive()
    archive.record(
        RawArchive.make_snapshot(
            bank="b",
            account="u",
            kind="balances",
            attended=True,
            http_status=200,
            response={"balances": []},
            fetched_at="2014-01-01T00:00:00+00:00",
        )
    )
    await archive.async_flush(datetime(2026, 3, 1, tzinfo=UTC))
    assert await archive.async_read_month("2014_01")
    assert [s["fetched_at"][:4] for s in await archive.async_read_all()] == ["2014"]


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def _snap(kind, response, at, meta=None, account="u1"):
    return RawArchive.make_snapshot(
        bank="b",
        account=account,
        kind=kind,
        attended=True,
        http_status=200,
        response=response,
        fetched_at=at,
        meta=meta,
    )


def test_replay_groups_pages_and_honours_the_window():
    m1 = {"account_key": "K", "fetch_id": "f1", "date_from": "2025-01-01"}
    m2 = {"account_key": "K", "fetch_id": "f2", "date_from": "2026-01-25"}
    snaps = [
        _snap(
            "transactions",
            {"transactions": [eb_tx("r1", "2026-02-01")], "continuation_key": "c"},
            "2026-02-02T10:00:00",
            m1,
        ),
        _snap(
            "transactions",
            {"transactions": [eb_tx("r2", "2026-01-30"), eb_tx("p1", "2026-02-02", status="PDNG")]},
            "2026-02-02T10:00:01",
            m1,
        ),
        _snap(
            "transactions_window",
            {"date_from": "2025-01-01", "truncated": False},
            "2026-02-02T10:00:02",
            m1,
        ),
        _snap(
            "balances",
            {
                "balances": [
                    {"balance_type": "CLBD", "balance_amount": {"amount": "9", "currency": "EUR"}}
                ]
            },
            "2026-02-02T10:00:03",
            m1,
        ),
        # Second fetch: r2 was reversed by the bank.
        _snap(
            "transactions", {"transactions": [eb_tx("r1", "2026-02-01")]}, "2026-02-09T10:00:00", m2
        ),
        _snap(
            "transactions_window",
            {"date_from": "2026-01-25", "truncated": False},
            "2026-02-09T10:00:01",
            m2,
        ),
    ]
    accounts, coverage, stats = replay(snaps, {})
    txs = accounts["K"]["transactions"]
    assert [t["transactionId"] for t in txs] == ["r1"]
    assert txs[0]["transactionAmount"]["amount"] == "-10.00"  # same normalisation as live
    assert accounts["K"]["balances"][0]["type"] == "CLBD"
    # The first window asked from 2025-01-01 but the bank only reported from
    # 2026-01-30 (> 31 days later), so it is evidence from there; the second,
    # ordinary window covers its full span from 2026-01-25.
    assert coverage["K"] == "2026-01-25"
    assert stats["windows"] == 2 and stats["skipped"] == 0


def test_replay_treats_an_unclosed_window_and_legacy_pages_as_merge_only():
    snaps = [
        # legacy snapshot without meta: uid resolved through the current accounts
        _snap(
            "transactions",
            {"transactions": [eb_tx("old", "2025-06-01")]},
            "2025-06-02T00:00:00",
            None,
            account="legacy-uid",
        ),
        # crash mid-fetch: pages without a closing window marker
        _snap(
            "transactions",
            {"transactions": [eb_tx("new", "2026-02-01")]},
            "2026-02-02T00:00:00",
            {"account_key": "K", "fetch_id": "x", "date_from": "2020-01-01"},
        ),
        _snap(
            "transactions", {"transactions": []}, "2026-02-03T00:00:00", None, account="unknown-uid"
        ),
    ]
    accounts, _coverage, stats = replay(snaps, {"legacy-uid": "K"})
    assert {t["transactionId"] for t in accounts["K"]["transactions"]} == {"old", "new"}
    assert stats["skipped"] == 1


def test_merge_keeps_history_the_archive_does_not_cover():
    old = {
        "K": {
            "transactions": [
                {**tx("legacy", "2020-01-01"), "_status": "booked", "_ledger_id": "id:legacy"},
                {**tx("stale", "2026-02-05"), "_status": "booked", "_ledger_id": "id:stale"},
            ],
            "balances": [{"at": "2020-01-01T00:00:00", "type": "CLBD", "amount": "1"}],
        },
        "OTHER": {
            "transactions": [{**tx("o", "2021-01-01"), "_status": "booked", "_ledger_id": "id:o"}],
            "balances": [],
        },
    }
    new = {
        "K": {
            "transactions": [
                {**tx("r1", "2026-02-01"), "_status": "booked", "_ledger_id": "id:r1"}
            ],
            "balances": [{"at": "2026-02-02T00:00:00", "type": "CLBD", "amount": "9"}],
        }
    }
    carried = merge_uncovered(old, new, {"K": "2026-01-01"})
    assert [t["transactionId"] for t in new["K"]["transactions"]] == ["r1", "legacy"]
    assert [p["at"][:4] for p in new["K"]["balances"]] == ["2020", "2026"]
    assert new["OTHER"]["transactions"][0]["transactionId"] == "o"
    assert carried == 2


# ---------------------------------------------------------------------------
# Manager: backfill on the live path, rebuild on version change
# ---------------------------------------------------------------------------


def _client(responses):
    """Real EnableBankingClient whose HTTP layer answers from ``responses``."""
    client = EnableBankingClient.__new__(EnableBankingClient)
    client.calls = []

    async def request(method, path, psu_ip=None, psu_ua=None, **_):
        client.calls.append(path)
        for match, answer in responses:
            if match(path):
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(path)

    client._async_request = request
    return client


def _manager(client, raw=None):
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    sub = SimpleNamespace(
        subentry_id="b1",
        subentry_type="bank",
        title="DKB",
        data={
            "aspsp_name": "DKB",
            "valid_until": "2026-12-01T00:00:00+00:00",
            "accounts": [{"uid": "u1", "identity_key": "iban:DE00"}],
        },
    )
    entry = SimpleNamespace(
        data={"accounts": [{"id": "u1", "iban": "DE00", "key": "iban:DE00", "name": "Giro"}]},
        options={},
        subentries={"b1": sub},
        entry_id="e",
    )
    hass = MagicMock()
    hass.data = {}
    mgr = FinanceDashboardManager(hass, entry)
    mgr._ledger = Ledger(FakeEncryptedStore())
    mgr._transfer_override_store = FakeStore()
    cred = AsyncMock()
    cred.async_get_bank_session.return_value = {
        "session_id": "s",
        "valid_until": "2026-12-01T00:00:00+00:00",
    }
    backups: dict[str, FakeEncryptedStore] = {}

    def encrypted_store(key, *args, **kwargs):
        return backups.setdefault(key, FakeEncryptedStore())

    cred.encrypted_store = encrypted_store
    cred.backups = backups
    mgr._credential_manager = cred
    mgr._banking_client = client
    mgr._categorizer = MagicMock()
    mgr._categorizer.categorize.return_value = "other"
    mgr._raw = raw
    return mgr


def _bad_period():
    return aiohttp.ClientResponseError(MagicMock(), (), status=422)


@pytest.mark.asyncio
async def test_first_attended_fetch_asks_for_full_history_and_steps_down():
    tx_page = {"transactions": [eb_tx("r1", "2024-11-02"), eb_tx("r2", "2026-03-01")]}
    rejected = {str(d) for d in HISTORY_BACKFILL_DAYS[:2]}
    state = {"n": 0}

    def too_long(path):
        if "/transactions" not in path:
            return False
        state["n"] += 1
        return state["n"] <= len(rejected)

    client = _client(
        [
            (too_long, _bad_period()),
            (lambda p: "/transactions" in p, tx_page),
            (lambda p: "/balances" in p, {"balances": []}),
        ]
    )
    raw = _archive()
    mgr = _manager(client, raw)
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")

    tx_calls = [c for c in client.calls if "/transactions" in c]
    assert len(tx_calls) == 3  # 3650 and 730 rejected, 365 accepted
    hist = mgr._ledger.meta["history"]["iban:DE00"]
    assert hist["backfilled"] and hist["earliest_booked"] == "2024-11-02"

    # The archive carries everything a replay needs.
    snaps = await raw.async_read_all()
    window = [s for s in snaps if s["kind"] == "transactions_window"]
    assert len(window) == 1 and window[0]["meta"]["account_key"] == "iban:DE00"

    # Done for this session; a re-link (new consent) opens the history again.
    assert not mgr._needs_backfill("iban:DE00", "2026-12-01T00:00:00+00:00")
    assert mgr._needs_backfill("iban:DE00", "2027-06-01T00:00:00+00:00")
    assert mgr._fetch_date_from("iban:DE00", None) > "2026-01-01"  # incremental next


@pytest.mark.asyncio
async def test_background_refresh_never_backfills():
    client = _client(
        [
            (lambda p: "/transactions" in p, {"transactions": []}),
            (lambda p: "/balances" in p, {"balances": []}),
        ]
    )
    mgr = _manager(client)
    await mgr.async_refresh_transactions(scheduled=True)
    assert len([c for c in client.calls if "/transactions" in c]) == 1
    assert "iban:DE00" not in (mgr._ledger.meta.get("history") or {})


@pytest.mark.asyncio
async def test_rebuild_on_version_change_backs_up_and_matches_live():
    page = {"transactions": [eb_tx("r1", "2026-02-01"), eb_tx("r2", "2026-02-03")]}
    client = _client(
        [
            (lambda p: "/transactions" in p, page),
            (
                lambda p: "/balances" in p,
                {
                    "balances": [
                        {
                            "balance_type": "CLBD",
                            "balance_amount": {"amount": "5", "currency": "EUR"},
                        }
                    ]
                },
            ),
        ]
    )
    raw = _archive()
    mgr = _manager(client, raw)
    await mgr.async_refresh_transactions(psu_ip="10.0.0.9")
    await raw.async_flush()
    live = mgr._ledger.transactions("iban:DE00")

    # An older processing version wrote this ledger, plus a pre-archive tx.
    mgr._ledger.meta["processing_version"] = PROCESSING_VERSION - 1
    mgr._ledger.data["accounts"]["iban:DE00"]["transactions"].append(
        {**tx("pre", "2019-01-01"), "_status": "booked", "_ledger_id": "id:pre"}
    )
    result = await mgr.async_reprocess()

    assert result["outcome"] == "rebuilt"
    assert mgr._ledger.meta["processing_version"] == PROCESSING_VERSION
    rebuilt = mgr._ledger.transactions("iban:DE00")
    assert [t["_ledger_id"] for t in rebuilt] == [t["_ledger_id"] for t in live] + ["id:pre"]
    backup = mgr._credential_manager.backups[f"{STORAGE_KEY_LEDGER_BACKUP}{PROCESSING_VERSION - 1}"]
    assert any(
        t["_ledger_id"] == "id:pre"
        for t in (await backup.async_load())["accounts"]["iban:DE00"]["transactions"]
    )
    # No bank call during the rebuild.
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_rebuild_is_skipped_when_current_and_aborts_on_unreadable_archive():
    raw = _archive()
    mgr = _manager(_client([]), raw)
    mgr._ledger.meta["processing_version"] = PROCESSING_VERSION
    assert (await mgr.async_reprocess())["outcome"] == "current"

    mgr._ledger.meta["processing_version"] = 0
    mgr._ledger.data["accounts"]["K"] = {"transactions": [{"_ledger_id": "keep"}], "balances": []}
    raw.async_read_all = AsyncMock(side_effect=StorageDecryptError("raw: InvalidToken"))
    result = await mgr.async_reprocess()
    assert result["outcome"] == "error"
    assert mgr._ledger.data["accounts"]["K"]["transactions"] == [{"_ledger_id": "keep"}]
    assert mgr._ledger.meta["processing_version"] == 0  # retried next start
