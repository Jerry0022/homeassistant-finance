"""R8 — Corrupt storage file must not crash async_initialize.

Simulates a JSONDecodeError from the storage layer and verifies the
manager starts cleanly with empty state and raises a repair issue.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    return hass


def _make_mock_entry() -> MagicMock:
    entry = MagicMock()
    entry.data = {"accounts": []}
    entry.options = {}
    return entry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupt_storage_does_not_raise() -> None:
    """async_initialize must complete without raising when storage is corrupt."""
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    hass = _make_mock_hass()
    entry = _make_mock_entry()

    # Mock CredentialManager and TransactionCategorizer so we don't need HA
    with (
        patch(
            "custom_components.finance_dashboard.credential_manager.CredentialManager"
        ) as MockCred,
        patch(
            "custom_components.finance_dashboard.categorizer.TransactionCategorizer"
        ) as MockCat,
    ):
        mock_cred_inst = AsyncMock()
        MockCred.return_value = mock_cred_inst
        MockCat.return_value = MagicMock()

        mgr = FinanceDashboardManager(hass, entry)

        # Inject corrupt storage — Store.async_load raises JSONDecodeError
        mgr._transaction_store = AsyncMock()
        mgr._transaction_store.async_load.side_effect = json.JSONDecodeError(
            "Expecting value", "", 0
        )

        # Patch repair issue creation so it doesn't call real HA helpers
        with patch.object(mgr, "_raise_storage_corrupt_issue") as mock_repair:
            # Must NOT raise
            await mgr.async_initialize()

        # Manager must start with empty state
        assert mgr._transactions == [], (
            "Expected empty transactions after corrupt storage"
        )
        assert mgr._tx_by_account == {}, (
            "Expected empty tx_by_account after corrupt storage"
        )

        # Repair issue must have been raised
        mock_repair.assert_called_once()
        call_args = mock_repair.call_args
        assert call_args is not None
        # First arg is storage_key, second is error_class
        error_class_arg = call_args[0][1] if call_args[0] else call_args[1].get("error_class", "")
        assert error_class_arg == "JSONDecodeError", (
            f"Expected error_class='JSONDecodeError', got '{error_class_arg}'"
        )


@pytest.mark.asyncio
async def test_valid_storage_loads_normally() -> None:
    """async_initialize with valid storage must populate transactions."""
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    hass = _make_mock_hass()
    entry = _make_mock_entry()

    valid_cache = {
        "tx_by_account": {
            "acc1": [
                {
                    "transactionId": "t1",
                    "_account_id": "acc1",
                    "bookingDate": "2024-01-01",
                }
            ]
        },
        "balances": {},
        "last_refresh": "2024-01-01T12:00:00",
        "last_refresh_stats": {},
    }

    with (
        patch(
            "custom_components.finance_dashboard.credential_manager.CredentialManager"
        ) as MockCred,
        patch(
            "custom_components.finance_dashboard.categorizer.TransactionCategorizer"
        ) as MockCat,
    ):
        MockCred.return_value = AsyncMock()
        MockCat.return_value = MagicMock()

        mgr = FinanceDashboardManager(hass, entry)
        mgr._transaction_store = AsyncMock()
        mgr._transaction_store.async_load.return_value = valid_cache

        await mgr.async_initialize()

    assert len(mgr._transactions) == 1
    assert mgr._transactions[0]["transactionId"] == "t1"
    assert "acc1" in mgr._tx_by_account
