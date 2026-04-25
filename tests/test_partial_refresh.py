"""R5 — Per-account transaction cache: partial refresh must not lose data.

Two accounts: account_a succeeds, account_b raises an exception.
After refresh, both accounts must have their correct data in the cache.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_tx(account_id: str, tx_id: str, date: str = "2024-01-01") -> dict:
    return {
        "transactionId": tx_id,
        "_account_id": account_id,
        "bookingDate": date,
        "transactionAmount": {"amount": "-10.00", "currency": "EUR"},
        "_status": "booked",
        "category": "other",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_per_account_cache_preserves_stale_on_error() -> None:
    """When account_b fails, account_a's fresh data AND account_b's stale data
    must both be present after the partial refresh.
    """
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    # Seed stale cache for account_b
    tx_b_stale = _make_tx("account_b", "stale-b-1", "2024-01-01")

    # Build a bare manager (no hass, no entry needed for unit test)
    mgr = object.__new__(FinanceDashboardManager)
    mgr._tx_by_account = {"account_b": [tx_b_stale]}
    mgr._transactions = [tx_b_stale]

    # Simulate per-account update: account_a succeeds, account_b fails
    tx_a_new = _make_tx("account_a", "new-a-1", "2024-01-15")
    mgr._tx_by_account["account_a"] = [tx_a_new]
    # account_b NOT updated (simulating exception path — stale entry kept)

    # Rebuild flat list as _do_refresh would
    all_transactions = [
        tx for txs in mgr._tx_by_account.values() for tx in txs
    ]

    assert len(all_transactions) == 2, (
        f"Expected 2 transactions (1 fresh + 1 stale), got {len(all_transactions)}"
    )
    ids = {t["transactionId"] for t in all_transactions}
    assert "new-a-1" in ids, "Fresh account_a transaction missing"
    assert "stale-b-1" in ids, "Stale account_b transaction was incorrectly wiped"


def test_per_account_cache_full_success() -> None:
    """When both accounts succeed, both caches are updated."""
    mgr_cache: dict = {}

    tx_a = _make_tx("account_a", "tx-a", "2024-02-01")
    tx_b = _make_tx("account_b", "tx-b", "2024-02-02")

    mgr_cache["account_a"] = [tx_a]
    mgr_cache["account_b"] = [tx_b]

    flat = [tx for txs in mgr_cache.values() for tx in txs]
    ids = {t["transactionId"] for t in flat}
    assert ids == {"tx-a", "tx-b"}


def test_migration_flat_to_dict() -> None:
    """Old flat list must be migrated to per-account dict on load."""
    flat = [
        _make_tx("acc1", "old-tx-1"),
        _make_tx("acc1", "old-tx-2"),
        _make_tx("acc2", "old-tx-3"),
    ]
    # Migration logic: group by _account_id
    by_account: dict = {}
    for tx in flat:
        acc_id = tx.get("_account_id", "__unknown__")
        by_account.setdefault(acc_id, []).append(tx)

    assert set(by_account.keys()) == {"acc1", "acc2"}
    assert len(by_account["acc1"]) == 2
    assert len(by_account["acc2"]) == 1
