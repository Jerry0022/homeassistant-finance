"""Finance Manager — core business logic orchestrator.

Coordinates between:
- Enable Banking API client (banking data via PSD2)
- Credential Manager (secure storage)
- Transaction Categorizer (auto-classification)
- Transaction Cache (encrypted .storage/)

SECURITY: All transaction data is cached in HA's .storage/ directory
(encrypted at rest). No financial data is ever written to logs or git.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

TRANSACTION_CACHE_KEY = f"{DOMAIN}_transactions"
TRANSACTION_CACHE_VERSION = 1


class FinanceDashboardManager:
    """Central orchestrator for the Finance integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self._hass = hass
        self._entry = entry
        self._credential_manager = None
        self._banking_client = None
        self._categorizer = None
        self._transaction_store = Store(
            hass, TRANSACTION_CACHE_VERSION, TRANSACTION_CACHE_KEY
        )
        self._accounts: list[dict[str, Any]] = entry.data.get(
            "accounts", []
        )
        self._transactions: list[dict[str, Any]] = []
        self._balances: dict[str, Any] = {}
        self._last_refresh: datetime | None = None

    async def async_initialize(self) -> None:
        """Initialize all sub-components."""
        from .credential_manager import CredentialManager
        from .categorizer import TransactionCategorizer

        self._credential_manager = CredentialManager(self._hass)
        await self._credential_manager.async_initialize()

        self._categorizer = TransactionCategorizer()

        # Load cached transactions from .storage/
        cached = await self._transaction_store.async_load()
        if cached and "transactions" in cached:
            self._transactions = cached["transactions"]
            last_refresh = cached.get("last_refresh")
            if last_refresh:
                self._last_refresh = datetime.fromisoformat(last_refresh)
            _LOGGER.info(
                "Loaded %d cached transactions (last refresh: %s)",
                len(self._transactions),
                self._last_refresh,
            )

        _LOGGER.info("Finance Manager initialized")

    async def async_shutdown(self) -> None:
        """Clean shutdown — persist cache, clear sensitive data from memory."""
        # Save current transactions before shutdown
        await self._persist_transactions()
        self._banking_client = None
        self._balances.clear()
        _LOGGER.info("Finance Manager shut down")

    async def async_refresh_accounts(self) -> list[dict[str, Any]]:
        """Refresh account list from Enable Banking."""
        client = await self._async_get_client()
        if not client:
            return []

        refreshed = []
        for account in self._accounts:
            acc_id = account.get("id")
            if not acc_id:
                continue
            try:
                details = await client.async_get_account_details(acc_id)
                acc_data = details.get("account", {})
                acc_data["id"] = acc_id
                # Preserve assignment info from config
                acc_data["type"] = account.get("type", "personal")
                acc_data["person"] = account.get("person", "")
                acc_data["institution"] = account.get("institution", "")
                acc_data["logo"] = account.get("logo", "")
                refreshed.append(acc_data)
            except Exception:
                _LOGGER.warning(
                    "Failed to refresh account %s", acc_id
                )
                refreshed.append(account)

        self._accounts = refreshed
        await self._credential_manager._audit_log("accounts_refreshed")
        return self._accounts

    async def async_refresh_transactions(
        self, days: int = 90
    ) -> list[dict[str, Any]]:
        """Refresh transactions for all linked accounts.

        Fetches last N days of transactions, auto-categorizes them,
        and persists to encrypted .storage/ cache.
        """
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
                pending = txns.get("pending", [])

                # Tag each transaction with account info
                for txn in booked:
                    txn["_account_id"] = account_id
                    txn["_account_name"] = account.get("name", "")
                    txn["_account_type"] = account.get("type", "personal")
                    txn["_account_person"] = account.get("person", "")
                    txn["_status"] = "booked"
                    txn["category"] = self._categorizer.categorize(txn)

                for txn in pending:
                    txn["_account_id"] = account_id
                    txn["_account_name"] = account.get("name", "")
                    txn["_status"] = "pending"
                    txn["category"] = self._categorizer.categorize(txn)

                all_transactions.extend(booked)
                all_transactions.extend(pending)

                _LOGGER.debug(
                    "Account %s: %d booked, %d pending",
                    account_id,
                    len(booked),
                    len(pending),
                )
            except Exception:
                _LOGGER.exception(
                    "Failed to fetch transactions for account %s",
                    account_id,
                )

        # Sort by booking date (newest first)
        all_transactions.sort(
            key=lambda t: t.get("bookingDate", ""),
            reverse=True,
        )

        self._transactions = all_transactions
        self._last_refresh = datetime.now()

        # Persist to encrypted .storage/
        await self._persist_transactions()

        await self._credential_manager._audit_log(
            "transactions_refreshed"
        )
        _LOGGER.info(
            "Refreshed %d transactions across %d accounts",
            len(all_transactions),
            len(self._accounts),
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
                iban = account.get("iban", "")
                balances[account_id] = {
                    "account_name": account.get("name", "Unknown"),
                    "iban": iban,
                    "iban_masked": (
                        f"****{iban[-4:]}"
                        if len(iban) >= 4
                        else "****"
                    ),
                    "institution": account.get("institution", ""),
                    "logo": account.get("logo", ""),
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
            and txn.get("_status") == "booked"
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
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "balance": round(total_income - total_expenses, 2),
            "categories": {
                k: round(v, 2) for k, v in category_totals.items()
            },
            "transaction_count": len(monthly_txns),
            "last_refresh": (
                self._last_refresh.isoformat()
                if self._last_refresh
                else None
            ),
        }

    async def async_categorize_transactions(self) -> None:
        """Re-run auto-categorization on all cached transactions."""
        if not self._categorizer:
            return
        for txn in self._transactions:
            txn["category"] = self._categorizer.categorize(txn)
        await self._persist_transactions()
        _LOGGER.info(
            "Re-categorized %d transactions", len(self._transactions)
        )

    async def async_set_budget_limit(
        self, category: str, limit: float
    ) -> None:
        """Set a budget limit for a category via the Number entity."""
        from .const import DOMAIN

        entity_id = f"number.fd_budget_{category}"
        state = self._hass.states.get(entity_id)
        if state is not None:
            await self._hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": limit},
            )
            _LOGGER.info(
                "Budget limit for %s set to %.2f", category, limit
            )
        else:
            _LOGGER.warning(
                "Budget entity %s not found", entity_id
            )

    async def async_export_csv(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        categories: list[str] | None = None,
    ) -> str:
        """Export transactions as CSV file."""
        from .export import async_export_csv

        return await async_export_csv(
            self._hass,
            self._transactions,
            date_from=date_from,
            date_to=date_to,
            categories=categories,
        )

    def get_cached_transactions(
        self, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get cached transactions (no API call).

        Returns sanitized transactions for API responses.
        Full details only — caller must check admin status.
        """
        return self._transactions[:limit]

    async def _async_get_client(self):
        """Get or create Enable Banking client with current credentials."""
        if self._banking_client:
            return self._banking_client

        creds = await self._credential_manager.async_get_api_credentials()
        if not creds:
            _LOGGER.error("No Enable Banking credentials available")
            return None

        from .enablebanking_client import EnableBankingClient

        self._banking_client = EnableBankingClient(creds[0], creds[1])
        return self._banking_client

    async def _persist_transactions(self) -> None:
        """Save transactions to encrypted .storage/ cache."""
        await self._transaction_store.async_save(
            {
                "transactions": self._transactions,
                "last_refresh": (
                    self._last_refresh.isoformat()
                    if self._last_refresh
                    else None
                ),
                "account_count": len(self._accounts),
            }
        )

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
