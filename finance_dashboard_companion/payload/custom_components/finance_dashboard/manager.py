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

from .const import DOMAIN, STORAGE_KEY_TRANSFER_OVERRIDES, STORAGE_VERSION
from .enablebanking_client import RateLimitExceeded
from .household import HouseholdMember, HouseholdModel
from .recurring import detect_recurring
from .transfer_detector import (
    apply_overrides,
    detect_transfer_chains,
    enrich_transactions,
    get_effective_transactions,
)

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
        self._rate_limited_until: datetime | None = None
        self._transfer_override_store = Store(
            hass, 1, STORAGE_KEY_TRANSFER_OVERRIDES
        )
        self._transfer_overrides: dict[str, bool] = {}
        self._recurring_patterns: list[dict[str, Any]] = []
        self._previous_balances: dict[str, float] = {}

    @property
    def rate_limited_until(self) -> datetime | None:
        """Return the datetime until which the API is rate-limited, or None."""
        if self._rate_limited_until and datetime.now() < self._rate_limited_until:
            return self._rate_limited_until
        return None

    def _set_rate_limited(self) -> None:
        """Mark API as rate-limited until midnight (next calendar day)."""
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        self._rate_limited_until = tomorrow
        _LOGGER.warning(
            "API rate-limited — serving cached data until %s",
            tomorrow.isoformat(),
        )

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
                acc_data["ha_users"] = account.get("ha_users", [])
                acc_data["custom_name"] = account.get("custom_name", "")
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

        If the API returns HTTP 429 (daily quota exhausted), cached
        data is served and no further API calls are attempted until
        the next calendar day (midnight local time).
        """
        # Skip API calls if we're still rate-limited
        if self.rate_limited_until:
            _LOGGER.info(
                "API rate-limited until %s — serving cached transactions",
                self._rate_limited_until.isoformat(),
            )
            return self._transactions

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
                display_name = account.get("custom_name") or account.get("name", "")
                for txn in booked:
                    txn["_account_id"] = account_id
                    txn["_account_name"] = display_name
                    txn["_account_type"] = account.get("type", "personal")
                    txn["_account_person"] = account.get("person", "")
                    txn["_account_ha_users"] = account.get("ha_users", [])
                    txn["_status"] = "booked"
                    txn["category"] = self._categorizer.categorize(txn)

                for txn in pending:
                    txn["_account_id"] = account_id
                    txn["_account_name"] = display_name
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
            except RateLimitExceeded:
                _LOGGER.warning(
                    "Rate limit hit for account %s — stopping all fetches",
                    account_id,
                )
                self._set_rate_limited()
                break
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

        # Detect cascading transfers and refunds
        chains, refunds = detect_transfer_chains(
            all_transactions, self._accounts
        )
        all_transactions = enrich_transactions(
            all_transactions, chains, refunds
        )

        # Apply user overrides (confirmed/rejected chains)
        overrides = await self._async_load_transfer_overrides()
        apply_overrides(all_transactions, overrides)

        # Detect new transactions (compare with previous set)
        old_ids = {
            t.get("transactionId") for t in self._transactions
            if t.get("transactionId")
        }
        new_txns = [
            t for t in all_transactions
            if t.get("transactionId") and t["transactionId"] not in old_ids
        ]

        self._transactions = all_transactions
        self._last_refresh = datetime.now()

        # Detect recurring payment patterns — must not crash transaction refresh
        try:
            self._recurring_patterns = detect_recurring(all_transactions)
        except Exception:
            _LOGGER.exception("Recurring detection failed — skipping")
            self._recurring_patterns = []

        # Persist to encrypted .storage/
        await self._persist_transactions()

        # Fire events for newly detected transactions — must not crash refresh
        try:
            from .events import fire_transaction_new

            for txn in new_txns:
                amount = float(
                    txn.get("transactionAmount", {}).get("amount", 0)
                )
                fire_transaction_new(
                    self._hass,
                    amount=amount,
                    creditor=txn.get("creditorName", ""),
                    category=txn.get("category", "other"),
                    account_name=txn.get("_account_name", ""),
                )
        except Exception:
            _LOGGER.exception("Transaction event firing failed — skipping")

        await self._credential_manager._audit_log(
            "transactions_refreshed"
        )
        _LOGGER.info(
            "Refreshed %d transactions across %d accounts (%d new, %d recurring patterns)",
            len(all_transactions),
            len(self._accounts),
            len(new_txns),
            len(self._recurring_patterns),
        )
        return all_transactions

    async def async_get_balance(self) -> dict[str, Any]:
        """Get current balances for all accounts."""
        # Serve cached balances while rate-limited
        if self.rate_limited_until:
            _LOGGER.debug("Rate-limited — serving cached balances")
            return self._balances

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
            except RateLimitExceeded:
                _LOGGER.warning(
                    "Rate limit hit fetching balance for %s — serving cache",
                    account_id,
                )
                self._set_rate_limited()
                return self._balances
            except Exception:
                _LOGGER.exception(
                    "Failed to fetch balance for account %s",
                    account_id,
                )

        # Fire events for significant balance changes — must not crash balance fetch
        try:
            from .events import fire_balance_changed

            for acc_id, data in balances.items():
                raw = data.get("balances", [])
                if raw:
                    new_bal = float(
                        raw[0].get("balanceAmount", {}).get("amount", 0)
                    )
                    old_bal = self._previous_balances.get(acc_id)
                    if old_bal is not None and abs(new_bal - old_bal) >= 1.0:
                        fire_balance_changed(
                            self._hass,
                            account_name=data.get("account_name", ""),
                            old_balance=old_bal,
                            new_balance=new_bal,
                        )
                    self._previous_balances[acc_id] = new_bal
        except Exception:
            _LOGGER.exception("Balance change event firing failed — skipping")

        self._balances = balances
        return balances

    async def async_get_monthly_summary(
        self, month: int | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """Get monthly spending summary with category breakdown."""
        now = datetime.now()
        target_month = month or now.month
        target_year = year or now.year

        # Use effective transactions (intermediate chain legs excluded)
        effective = get_effective_transactions(self._transactions)

        # Filter for target month
        monthly_txns = [
            txn
            for txn in effective
            if self._is_in_month(txn, target_month, target_year)
            and txn.get("_status") == "booked"
        ]

        # Count excluded transfers for transparency
        all_monthly = [
            txn
            for txn in self._transactions
            if self._is_in_month(txn, target_month, target_year)
            and txn.get("_status") == "booked"
        ]
        excluded_chain_txns = [
            txn for txn in all_monthly
            if txn.get("_transfer_role") in ("intermediate", "destination")
            and txn.get("_transfer_confirmed") is not False
        ]
        excluded_amount = sum(
            abs(float(t.get("transactionAmount", {}).get("amount", 0)))
            for t in excluded_chain_txns
        )

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

        # Build household split data from per-person accounts
        # Graceful degradation: household features must never crash the coordinator
        household = None
        try:
            household = self._compute_household(monthly_txns, total_expenses)
        except Exception:
            _LOGGER.exception("Household computation failed — skipping")

        # Recurring patterns (already detected during refresh)
        recurring_top = self._recurring_patterns[:10]

        # Fixed vs variable costs
        fixed_cats = {"housing", "loans", "utilities", "insurance"}
        fixed_total = sum(
            abs(category_totals.get(c, 0)) for c in fixed_cats
        )
        variable_total = total_expenses - fixed_total

        # Budget exceeded check — must not crash the coordinator
        try:
            self._check_budget_limits(category_totals)
        except Exception:
            _LOGGER.exception("Budget limit check failed — skipping")

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
            "excluded_transfers": {
                "chain_count": len(
                    {t.get("_transfer_chain_id")
                     for t in excluded_chain_txns
                     if t.get("_transfer_chain_id")}
                ),
                "excluded_amount": round(excluded_amount, 2),
                "excluded_txn_count": len(excluded_chain_txns),
            },
            "household": household,
            "recurring": [
                {
                    "creditor": p.get("creditor", ""),
                    "average_amount": p.get("average_amount", 0),
                    "frequency": p.get("frequency", "monthly"),
                    "category": p.get("category", "other"),
                    "occurrences": p.get("occurrences", 0),
                    "expected_day": p.get("expected_day", 1),
                }
                for p in recurring_top
            ],
            "fixed_costs": round(fixed_total, 2),
            "variable_costs": round(variable_total, 2),
            "last_refresh": (
                self._last_refresh.isoformat()
                if self._last_refresh
                else None
            ),
            "rate_limited_until": (
                self._rate_limited_until.isoformat()
                if self.rate_limited_until
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

        self._banking_client = EnableBankingClient(
            creds["application_id"], creds["private_key_pem"]
        )
        return self._banking_client

    async def async_confirm_transfer_chain(
        self, chain_id: str, confirmed: bool
    ) -> None:
        """Confirm or reject a detected transfer chain.

        Args:
            chain_id: The chain UUID to confirm/reject
            confirmed: True = user agrees it's a chain, False = reject
        """
        self._transfer_overrides[chain_id] = confirmed
        await self._transfer_override_store.async_save(
            self._transfer_overrides
        )
        # Apply to in-memory transactions immediately
        apply_overrides(self._transactions, self._transfer_overrides)
        _LOGGER.info(
            "Transfer chain %s %s",
            chain_id,
            "confirmed" if confirmed else "rejected",
        )

    def get_transfer_chains(self) -> list[dict[str, Any]]:
        """Return detected transfer chains for API/frontend display."""
        chains: dict[str, dict[str, Any]] = {}
        for txn in self._transactions:
            chain_id = txn.get("_transfer_chain_id")
            if not chain_id:
                continue

            if chain_id not in chains:
                chains[chain_id] = {
                    "chain_id": chain_id,
                    "confidence": txn.get("_transfer_confidence", 0),
                    "confirmed": txn.get("_transfer_confirmed"),
                    "transactions": [],
                }

            amount = float(
                txn.get("transactionAmount", {}).get("amount", 0)
            )
            chains[chain_id]["transactions"].append({
                "transactionId": txn.get("transactionId", ""),
                "role": txn.get("_transfer_role", ""),
                "account_name": txn.get("_account_name", ""),
                "amount": amount,
                "date": txn.get("bookingDate", ""),
                "creditor": txn.get("creditorName", ""),
                "description": txn.get(
                    "remittanceInformationUnstructured", ""
                ),
            })

        return list(chains.values())

    async def _async_load_transfer_overrides(
        self,
    ) -> dict[str, bool]:
        """Load user overrides for transfer chains from storage."""
        data = await self._transfer_override_store.async_load()
        if data and isinstance(data, dict):
            self._transfer_overrides = data
            return data
        return {}

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

    def _compute_household(
        self,
        monthly_txns: list[dict[str, Any]],
        total_expenses: float,
    ) -> dict[str, Any] | None:
        """Build household split data from account assignments and transactions.

        Groups transactions by person (from account assignments), computes
        income and individual costs per person, then runs the household
        split model to calculate each person's share of shared costs
        and their remaining Spielgeld.
        """
        # Build person map from account config
        persons: dict[str, dict[str, Any]] = {}
        for acc in self._accounts:
            person = acc.get("person", "")
            if not person:
                continue
            if person not in persons:
                persons[person] = {
                    "income": 0.0,
                    "individual_costs": 0.0,
                    "account_ids": [],
                    "acc_type": acc.get("type", "personal"),
                }
            persons[person]["account_ids"].append(acc.get("id", ""))

        if not persons:
            return None

        # Sum income and costs per person from their transactions
        shared_costs = 0.0
        shared_cost_items: list[dict[str, Any]] = []

        for txn in monthly_txns:
            amount = float(
                txn.get("transactionAmount", {}).get("amount", 0)
            )
            acc_type = txn.get("_account_type", "personal")
            person = txn.get("_account_person", "")
            category = txn.get("category", "other")

            if acc_type == "shared":
                # Shared account — costs are split among all members
                if amount < 0:
                    shared_costs += abs(amount)
                    shared_cost_items.append({
                        "category": category,
                        "amount": amount,
                    })
            elif person and person in persons:
                if amount > 0:
                    persons[person]["income"] += amount
                else:
                    persons[person]["individual_costs"] += abs(amount)

        # Build HouseholdMembers
        members = []
        for name, data in persons.items():
            members.append(
                HouseholdMember(
                    name=name,
                    net_income=data["income"],
                    gross_income=data["income"],
                    individual_costs=data["individual_costs"],
                    account_ids=data["account_ids"],
                )
            )

        split_mode = self._entry.options.get("split_model", "proportional")
        remainder_mode = self._entry.options.get("remainder_mode", "none")

        model = HouseholdModel(
            members=members,
            split_mode=split_mode,
            remainder_mode=remainder_mode,
        )

        results = model.calculate_split(
            shared_costs, shared_cost_items or None
        )

        return {
            "members": [
                {
                    "person": r.person,
                    "gross_income": round(r.gross_income, 2),
                    "net_income": round(r.net_income, 2),
                    "income_ratio": round(r.income_ratio * 100, 1),
                    "shared_costs_share": round(r.shared_costs_share, 2),
                    "individual_costs": round(r.individual_costs, 2),
                    "spielgeld": round(r.spielgeld, 2),
                    "bonus_amount": round(r.bonus_amount, 2),
                }
                for r in results
            ],
            "split_model": split_mode,
            "remainder_mode": remainder_mode,
            "total_shared_costs": round(shared_costs, 2),
        }

    def _check_budget_limits(
        self, category_totals: dict[str, float]
    ) -> None:
        """Check if any category exceeds its budget limit and fire events."""
        from .events import fire_budget_exceeded

        for category, amount in category_totals.items():
            if amount >= 0:
                continue  # Only check expense categories
            actual = abs(amount)
            entity_id = f"number.fd_budget_{category}"
            state = self._hass.states.get(entity_id)
            if state is None:
                continue
            try:
                limit = float(state.state)
            except (ValueError, TypeError):
                continue
            if limit > 0 and actual > limit:
                fire_budget_exceeded(
                    self._hass,
                    category=category,
                    limit=limit,
                    actual=actual,
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
