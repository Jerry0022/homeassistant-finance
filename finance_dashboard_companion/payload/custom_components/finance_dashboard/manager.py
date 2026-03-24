"""Finance Dashboard Manager — core business logic orchestrator.

Coordinates between:
- GoCardless API client (banking data)
- Credential Manager (secure storage)
- Transaction Categorizer (auto-classification)
- Household Model (multi-person budget split)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardManager:
    """Central orchestrator for the Finance Dashboard integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self._hass = hass
        self._entry = entry
        self._credential_manager = None
        self._gocardless_client = None
        self._categorizer = None
        self._accounts: list[dict[str, Any]] = []
        self._transactions: list[dict[str, Any]] = []
        self._balances: dict[str, Any] = {}

    async def async_initialize(self) -> None:
        """Initialize all sub-components."""
        from .credential_manager import CredentialManager
        from .categorizer import TransactionCategorizer

        self._credential_manager = CredentialManager(self._hass)
        await self._credential_manager.async_initialize()

        self._categorizer = TransactionCategorizer()

        _LOGGER.info("Finance Dashboard Manager initialized")

    async def async_shutdown(self) -> None:
        """Clean shutdown — clear sensitive data from memory."""
        self._gocardless_client = None
        self._accounts.clear()
        self._transactions.clear()
        self._balances.clear()
        _LOGGER.info("Finance Dashboard Manager shut down")

    async def async_refresh_accounts(self) -> list[dict[str, Any]]:
        """Refresh account list from GoCardless."""
        client = await self._async_get_client()
        if not client:
            return []

        # TODO: Implement account refresh from stored requisitions
        # This will iterate over linked bank requisitions and fetch
        # account details for each
        await self._credential_manager._audit_log("accounts_refreshed")
        return self._accounts

    async def async_refresh_transactions(
        self, days: int = 30
    ) -> list[dict[str, Any]]:
        """Refresh transactions for all linked accounts."""
        client = await self._async_get_client()
        if not client:
            return []

        date_from = (datetime.now() - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )
        date_to = datetime.now().strftime("%Y-%m-%d")

        all_transactions = []
        for account in self._accounts:
            account_id = account.get("id")
            if not account_id:
                continue

            try:
                txns = await client.async_get_transactions(
                    account_id, date_from, date_to
                )
                booked = txns.get("booked", [])
                # Auto-categorize transactions
                for txn in booked:
                    txn["category"] = self._categorizer.categorize(txn)
                    txn["account_id"] = account_id
                all_transactions.extend(booked)
            except Exception:
                _LOGGER.exception(
                    "Failed to fetch transactions for account %s",
                    account_id,
                )

        self._transactions = all_transactions
        await self._credential_manager._audit_log(
            "transactions_refreshed"
        )
        return all_transactions

    async def async_get_balance(self) -> dict[str, Any]:
        """Get current balances for all accounts."""
        client = await self._async_get_client()
        if not client:
            return {}

        balances = {}
        for account in self._accounts:
            account_id = account.get("id")
            if not account_id:
                continue

            try:
                account_balances = await client.async_get_balances(
                    account_id
                )
                balances[account_id] = {
                    "account_name": account.get("name", "Unknown"),
                    "iban": account.get("iban", ""),
                    "balances": account_balances,
                }
            except Exception:
                _LOGGER.exception(
                    "Failed to fetch balance for account %s",
                    account_id,
                )

        self._balances = balances
        return balances

    async def async_get_monthly_summary(
        self, month: int | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """Get monthly spending summary with category breakdown."""
        now = datetime.now()
        target_month = month or now.month
        target_year = year or now.year

        # Filter transactions for the target month
        monthly_txns = [
            txn
            for txn in self._transactions
            if self._is_in_month(txn, target_month, target_year)
        ]

        # Group by category
        category_totals: dict[str, float] = {}
        total_income = 0.0
        total_expenses = 0.0

        for txn in monthly_txns:
            amount = float(
                txn.get("transactionAmount", {}).get("amount", 0)
            )
            category = txn.get("category", "other")

            if amount > 0:
                total_income += amount
            else:
                total_expenses += abs(amount)

            category_totals[category] = (
                category_totals.get(category, 0) + amount
            )

        return {
            "month": target_month,
            "year": target_year,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "balance": total_income - total_expenses,
            "categories": category_totals,
            "transaction_count": len(monthly_txns),
        }

    async def _async_get_client(self):
        """Get or create GoCardless client with current credentials."""
        if self._gocardless_client:
            return self._gocardless_client

        creds = await self._credential_manager.async_get_api_credentials()
        if not creds:
            _LOGGER.error("No GoCardless credentials available")
            return None

        from .gocardless_client import GoCardlessClient

        self._gocardless_client = GoCardlessClient(creds[0], creds[1])
        return self._gocardless_client

    @staticmethod
    def _is_in_month(
        txn: dict[str, Any], month: int, year: int
    ) -> bool:
        """Check if a transaction belongs to the given month."""
        booking_date = txn.get("bookingDate", "")
        if not booking_date:
            return False
        try:
            dt = datetime.strptime(booking_date, "%Y-%m-%d")
            return dt.month == month and dt.year == year
        except ValueError:
            return False
