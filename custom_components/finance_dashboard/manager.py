"""Finance Manager — core business logic orchestrator.

Coordinates between:
- Enable Banking API client (banking data via PSD2)
- Credential Manager (secure storage)
- Transaction Categorizer (auto-classification)
- Transaction Cache (encrypted .storage/)

SECURITY: All transaction data is cached in HA's .storage/ directory
(encrypted at rest). No financial data is ever written to logs or git.

CACHE vs LIVE FETCH CONTRACT:
- ``get_cached_*`` / ``async_get_balance`` return in-memory cache only —
  zero API calls, unbounded calls allowed. Use from HTTP read endpoints.
- ``async_refresh_*`` hits the Enable Banking API and updates the cache —
  ONLY called from explicit user-triggered paths (service call, refresh
  button, setup-complete bootstrap). Enable Banking enforces a 4/day
  ASPSP rate limit, so automatic background fetches are forbidden.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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

# OAuth state token TTL in seconds (10 minutes)
_OAUTH_STATE_TTL = 600


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
        # Per-account transaction cache: account_id → list[tx].
        # Partial refresh failures only affect the failed account's slice —
        # other accounts keep their last-known data (R5 fix).
        self._tx_by_account: dict[str, list[dict[str, Any]]] = {}
        # Flat view (legacy + internal use) — kept in sync with _tx_by_account.
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
        self._demo_mode: bool = False
        # Last user-triggered refresh statistics — surfaced to the UI so
        # the user sees exactly what happened on the last "Aktualisieren"
        # click (accounts hit, transactions loaded, duration, outcome).
        # Structure: {"outcome": str, "accounts": int, "transactions": int,
        #   "new": int, "duration_ms": int, "started_at": ISO,
        #   "finished_at": ISO, "errors": list[str]}
        self._last_refresh_stats: dict[str, Any] = {}
        # Serialises concurrent refresh requests (double-click guard,
        # parallel service calls). In-flight state is also surfaced via
        # ``is_refreshing`` so the frontend can poll for completion.
        self._refresh_lock = asyncio.Lock()
        self._refresh_in_flight: bool = False
        # OAuth state tokens: {state_str: created_iso} — one-time-use, 10min TTL
        self._oauth_states: dict[str, str] = {}

    @property
    def rate_limited_until(self) -> datetime | None:
        """Return the datetime until which the API is rate-limited, or None."""
        if self._rate_limited_until and datetime.now() < self._rate_limited_until:
            return self._rate_limited_until
        return None

    @property
    def is_refreshing(self) -> bool:
        """True while a user-triggered refresh is in flight."""
        return self._refresh_in_flight

    @property
    def last_refresh(self) -> datetime | None:
        """Timestamp of the last successful transaction refresh, if any."""
        return self._last_refresh

    @property
    def last_refresh_stats(self) -> dict[str, Any]:
        """Structured stats from the most recent refresh attempt."""
        return dict(self._last_refresh_stats)

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

    @property
    def demo_mode(self) -> bool:
        """Return whether demo mode is active."""
        return self._demo_mode

    def set_demo_mode(self, enabled: bool) -> None:
        """Toggle demo mode on or off.

        When enabled, loads synthetic demo data into the manager's state.
        When disabled, clears demo data and reverts to real cached data.
        """
        self._demo_mode = enabled
        if enabled:
            from .demo import generate_demo_data

            data = generate_demo_data()
            self._accounts = data["_demo_accounts"]
            self._transactions = data["_demo_transactions"]
            self._balances = data["_demo_balances"]
            self._last_refresh = datetime.now()
            self._recurring_patterns = data.get("recurring", [])
            self._last_refresh_stats = self._build_stats(
                outcome="demo",
                started=self._last_refresh,
                duration_ms=0,
                accounts=len(self._accounts),
                transactions=len(self._transactions),
                new=0,
                errors=[],
            )
            _LOGGER.info("Demo mode enabled — loaded synthetic data")
        else:
            # Clear demo data — real data reloads on next manual refresh
            self._accounts = self._entry.data.get("accounts", [])
            self._transactions = []
            self._balances = {}
            self._last_refresh = None
            self._recurring_patterns = []
            _LOGGER.info("Demo mode disabled — cleared synthetic data")

    async def async_initialize(self) -> None:
        """Initialize all sub-components."""
        from .credential_manager import CredentialManager
        from .categorizer import TransactionCategorizer

        self._credential_manager = CredentialManager(self._hass)
        await self._credential_manager.async_initialize()

        self._categorizer = TransactionCategorizer()

        # Load cached transactions from .storage/
        # R8: wrap in try/except — a corrupt .storage/ file must not crash
        # HA startup.  On decode error the file is renamed to .corrupt-<ts>
        # and a Repair issue is raised so the user is notified.
        cached = None
        try:
            cached = await self._transaction_store.async_load()
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            _LOGGER.error(
                "Transaction cache corrupt (%s: %s) — starting with empty state",
                type(exc).__name__,
                exc,
            )
            self._raise_storage_corrupt_issue(
                TRANSACTION_CACHE_KEY, type(exc).__name__
            )
        if cached and ("transactions" in cached or "tx_by_account" in cached):
            # R5: prefer per-account dict; fall back to flat list (migration).
            raw_tx_by_account = cached.get("tx_by_account")
            if isinstance(raw_tx_by_account, dict):
                self._tx_by_account = raw_tx_by_account
                self._transactions = [
                    tx
                    for txs in self._tx_by_account.values()
                    for tx in txs
                ]
                # Deterministic sort after flatten
                self._transactions.sort(
                    key=lambda t: t.get("bookingDate", ""), reverse=True
                )
            else:
                # Migrate: old flat list → per-account dict
                flat: list[dict[str, Any]] = cached.get("transactions", [])
                self._transactions = flat
                for tx in flat:
                    acc_id = tx.get("_account_id", "__unknown__")
                    self._tx_by_account.setdefault(acc_id, []).append(tx)
            last_refresh = cached.get("last_refresh")
            if last_refresh:
                try:
                    self._last_refresh = datetime.fromisoformat(last_refresh)
                except ValueError:
                    self._last_refresh = None
            # Cached balances survive restart so the UI shows something
            # immediately — they're only reset by an explicit live refresh.
            self._balances = cached.get("balances", {}) or {}
            # Rebuild the balance-change baseline from the cache, otherwise
            # the first refresh after every HA restart fires a
            # fd_balance_changed event for every account (stale baseline =
            # 0.00 vs. cached value) and spams user automations.
            for acc_id, data in self._balances.items():
                raw = data.get("balances") if isinstance(data, dict) else None
                if not raw:
                    continue
                try:
                    self._previous_balances[acc_id] = float(
                        raw[0].get("balanceAmount", {}).get("amount", 0)
                    )
                except (TypeError, ValueError, IndexError, AttributeError):
                    continue
            # Rate-limit state must survive restart — otherwise a user
            # who hit HTTP 429 at 23:59 would "reset" by bouncing HA.
            rl = cached.get("rate_limited_until")
            if rl:
                try:
                    rl_dt = datetime.fromisoformat(rl)
                    if rl_dt > datetime.now():
                        self._rate_limited_until = rl_dt
                except ValueError:
                    pass
            stats = cached.get("last_refresh_stats")
            if isinstance(stats, dict):
                self._last_refresh_stats = stats
            _LOGGER.info(
                "Loaded %d cached transactions (last refresh: %s, balances: %d)",
                len(self._transactions),
                self._last_refresh,
                len(self._balances),
            )

        _LOGGER.info("Finance Manager initialized")

    async def async_shutdown(self) -> None:
        """Clean shutdown — persist cache, clear sensitive data from memory."""
        # Only persist real transactions — never overwrite cache with demo data
        if not self._demo_mode:
            await self._persist_transactions()
        self._banking_client = None
        self._balances.clear()
        _LOGGER.info("Finance Manager shut down")

    async def async_refresh_accounts(self) -> list[dict[str, Any]]:
        """Refresh account list from Enable Banking."""
        if self._demo_mode:
            return self._accounts
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
        """Refresh transactions AND balances for all linked accounts.

        Fetches last N days of transactions, auto-categorizes them,
        and persists to encrypted .storage/ cache. Also refreshes
        balances in the same user-triggered round — a single click
        updates the entire cache.

        If the API returns HTTP 429 (daily quota exhausted), cached
        data is served and no further API calls are attempted until
        the next calendar day (midnight local time).

        Concurrent calls are serialised by ``_refresh_lock`` and stats
        are written to ``_last_refresh_stats`` regardless of outcome.
        """
        async with self._refresh_lock:
            self._refresh_in_flight = True
            started = datetime.now()
            t0 = time.monotonic()
            try:
                return await self._do_refresh(days, started, t0)
            finally:
                self._refresh_in_flight = False

    async def _do_refresh(
        self, days: int, started: datetime, t0: float
    ) -> list[dict[str, Any]]:
        # Demo mode — regenerate fresh demo data without API calls
        if self._demo_mode:
            from .demo import generate_demo_data

            data = generate_demo_data()
            self._transactions = data["_demo_transactions"]
            self._balances = data["_demo_balances"]
            self._last_refresh = datetime.now()
            self._recurring_patterns = data.get("recurring", [])
            self._last_refresh_stats = self._build_stats(
                outcome="demo",
                started=started,
                duration_ms=int((time.monotonic() - t0) * 1000),
                accounts=len(self._accounts),
                transactions=len(self._transactions),
                new=0,
                errors=[],
            )
            return self._transactions

        # Skip API calls if we're still rate-limited
        if self.rate_limited_until:
            _LOGGER.info(
                "API rate-limited until %s — serving cached transactions",
                self._rate_limited_until.isoformat(),
            )
            self._last_refresh_stats = self._build_stats(
                outcome="rate_limited",
                started=started,
                duration_ms=int((time.monotonic() - t0) * 1000),
                accounts=0,
                transactions=len(self._transactions),
                new=0,
                errors=["Tageslimit der Bank-API erreicht (4/Tag pro Konto)"],
            )
            return self._transactions

        client = await self._async_get_client()
        if not client:
            self._last_refresh_stats = self._build_stats(
                outcome="error",
                started=started,
                duration_ms=int((time.monotonic() - t0) * 1000),
                accounts=0,
                transactions=len(self._transactions),
                new=0,
                errors=["Keine Enable-Banking-Credentials hinterlegt"],
            )
            return []

        date_from = (datetime.now() - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )
        date_to = datetime.now().strftime("%Y-%m-%d")

        errors: list[str] = []
        accounts_hit = 0
        for account in self._accounts:
            account_id = account.get("id")
            if not account_id:
                continue

            try:
                txns = await client.async_get_transactions(
                    account_id, date_from, date_to
                )
                accounts_hit += 1
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

                # R5: atomic per-account update — only overwrite on success
                self._tx_by_account[account_id] = booked + pending

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
                errors.append(
                    f"Rate-Limit bei {account.get('name', account_id)} — "
                    "Tageslimit (4/Tag) aufgebraucht"
                )
                break
            except Exception as exc:
                _LOGGER.exception(
                    "Failed to fetch transactions for account %s",
                    account_id,
                )
                errors.append(
                    f"{account.get('name', account_id)}: {str(exc)[:120]}"
                )
                # R5: keep stale cache for this account — do NOT clear it

        # Rebuild flat list from per-account dict (deterministic sort)
        all_transactions = [
            tx for txs in self._tx_by_account.values() for tx in txs
        ]

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

        # Same user click → also refresh balances so the whole cache
        # is consistent when the UI re-reads. Failures here are logged
        # but do not fail the transaction refresh.
        balance_errors: list[str] = []
        try:
            await self._async_refresh_balances_live(client, balance_errors)
        except Exception:
            _LOGGER.exception("Balance refresh leg failed")
        errors.extend(balance_errors)

        # Outcome classification: full success, partial (some accounts
        # errored), rate_limited (quota hit during the call), or error.
        if self.rate_limited_until:
            outcome = "rate_limited"
        elif errors:
            outcome = "partial" if accounts_hit > 0 else "error"
        else:
            outcome = "ok"

        self._last_refresh_stats = self._build_stats(
            outcome=outcome,
            started=started,
            duration_ms=int((time.monotonic() - t0) * 1000),
            accounts=accounts_hit,
            transactions=len(all_transactions),
            new=len(new_txns),
            errors=errors,
        )

        return all_transactions

    @staticmethod
    def _build_stats(
        outcome: str,
        started: datetime,
        duration_ms: int,
        accounts: int,
        transactions: int,
        new: int,
        errors: list[str],
    ) -> dict[str, Any]:
        """Assemble a refresh-stats dict for the status endpoint."""
        finished = datetime.now()
        return {
            "outcome": outcome,
            "accounts": accounts,
            "transactions": transactions,
            "new": new,
            "duration_ms": duration_ms,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "errors": list(errors)[:5],  # cap payload size
        }

    async def _async_refresh_balances_live(
        self, client, errors: list[str]
    ) -> dict[str, Any]:
        """Live-fetch balances from the API and update the cache.

        NEVER call this directly from an HTTP read endpoint — only from
        user-triggered refresh paths.  Reads should go through
        ``async_get_balance()`` which is cache-only.
        """
        balances: dict[str, Any] = {}
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
                    "Rate limit hit fetching balance for %s", account_id
                )
                self._set_rate_limited()
                errors.append(
                    f"Rate-Limit beim Saldo für "
                    f"{account.get('name', account_id)}"
                )
                # Preserve the partial batch we already fetched — without
                # this, accounts that succeeded BEFORE the 429 would lose
                # their fresh balance and the UI would show stale numbers
                # until the next day. Merge into existing cache so other
                # accounts (not reached this round) keep their last value.
                if balances:
                    merged = dict(self._balances)
                    merged.update(balances)
                    self._balances = merged
                return self._balances
            except Exception as exc:
                _LOGGER.exception(
                    "Failed to fetch balance for account %s",
                    account_id,
                )
                errors.append(
                    f"Saldo {account.get('name', account_id)}: "
                    f"{str(exc)[:120]}"
                )

        # Fire balance-change events — must never crash the refresh
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

        if balances:
            # Merge so accounts that errored this round keep their
            # last known cached value instead of silently disappearing
            # from the dashboard.
            merged = dict(self._balances)
            merged.update(balances)
            self._balances = merged
        return self._balances

    async def async_get_balance(self) -> dict[str, Any]:
        """Return cached balances — NEVER hits the banking API.

        This is the read path used by the HTTP balance endpoint and the
        coordinator's state queries. Safe for unbounded reads. Live
        updates happen inside ``async_refresh_transactions`` which is
        only invoked from user-triggered refresh paths.
        """
        return dict(self._balances)

    def get_cached_balances(self) -> dict[str, Any]:
        """Synchronous alias for ``async_get_balance`` — cache only."""
        return dict(self._balances)

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
            "last_refresh_stats": dict(self._last_refresh_stats),
            "is_refreshing": self._refresh_in_flight,
        }

    async def async_categorize_transactions(self) -> None:
        """Re-run auto-categorization on all cached transactions."""
        if self._demo_mode or not self._categorizer:
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

    def get_refresh_status(self) -> dict[str, Any]:
        """Return a compact status snapshot for the UI status endpoint.

        Pure cache read — NEVER touches the banking API. Safe for
        unbounded polling while a refresh is in flight.
        """
        now = datetime.now()
        cache_age_seconds: int | None = None
        if self._last_refresh:
            cache_age_seconds = int(
                (now - self._last_refresh).total_seconds()
            )
        return {
            "is_refreshing": self._refresh_in_flight,
            "last_refresh": (
                self._last_refresh.isoformat()
                if self._last_refresh
                else None
            ),
            "cache_age_seconds": cache_age_seconds,
            "rate_limited_until": (
                self._rate_limited_until.isoformat()
                if self.rate_limited_until
                else None
            ),
            "stats": dict(self._last_refresh_stats),
            "account_count": len(self._accounts),
            "transaction_count": len(self._transactions),
            "has_cache": bool(self._transactions) or bool(self._balances),
            "demo_mode": self._demo_mode,
        }

    async def async_register_oauth_state(self, state: str) -> None:
        """Register an OAuth state token for later CSRF validation.

        The state is stored in memory only (not persisted) with a creation
        timestamp so it can be expired after ``_OAUTH_STATE_TTL`` seconds.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._oauth_states[state] = now
        _LOGGER.debug("OAuth state registered (total: %d)", len(self._oauth_states))

    async def async_validate_oauth_state(self, state: str) -> bool:
        """Validate and consume an OAuth state token (CSRF protection).

        Uses ``secrets.compare_digest`` for timing-safe comparison to prevent
        timing-based enumeration of valid state tokens.

        Returns:
            True if the state was registered, not yet consumed, and not expired.
            False otherwise (unknown state, already consumed, or TTL exceeded).
        """
        # Purge all expired states first
        now = datetime.now(timezone.utc)
        expired = [
            s for s, created in self._oauth_states.items()
            if (now - datetime.fromisoformat(created)).total_seconds() > _OAUTH_STATE_TTL
        ]
        for s in expired:
            del self._oauth_states[s]

        if not self._oauth_states:
            return False

        # Timing-safe search: compare against every registered state so the
        # response time does not leak whether the prefix matched.
        matched_key: str | None = None
        for registered in list(self._oauth_states.keys()):
            if secrets.compare_digest(registered, state):
                matched_key = registered
                # One-time-use: delete immediately on match
                del self._oauth_states[registered]
                break

        if matched_key is None:
            _LOGGER.warning("OAuth callback received with unknown/invalid state")
            return False

        _LOGGER.debug("OAuth state validated and consumed")
        return True

    async def async_make_setup_call(self, method_name: str, *args, **kwargs):
        """Invoke an EnableBankingClient method through the rate-limit gate.

        Setup-wizard endpoints (institutions, authorize, OAuth callback) must
        go through here instead of instantiating EnableBankingClient directly.
        This ensures that the 4/day ASPSP quota is respected even during the
        onboarding flow — a user who hit the limit cannot bypass it by
        re-running the wizard.

        Raises:
            RateLimitExceeded: when the API is still rate-limited.
            RuntimeError: when no credentials are available.
        """
        if self.rate_limited_until:
            raise RateLimitExceeded(
                f"API rate-limited until {self._rate_limited_until.isoformat()} "
                "— bitte morgen erneut versuchen."
            )

        client = await self._async_get_client()
        if not client:
            raise RuntimeError(
                "Enable Banking client not available — credentials missing or invalid."
            )

        method = getattr(client, method_name)
        return await method(*args, **kwargs)

    async def _async_get_client(self):
        """Get or create Enable Banking client with current credentials."""
        if self._banking_client:
            return self._banking_client

        creds = await self._credential_manager.async_get_api_credentials()
        if not creds:
            _LOGGER.error("No Enable Banking credentials available")
            self._raise_credentials_issue("missing")
            return None

        from .enablebanking_client import EnableBankingClient

        try:
            self._banking_client = EnableBankingClient(
                creds["application_id"],
                creds["private_key_pem"],
                session=async_get_clientsession(self._hass),
            )
        except (ValueError, TypeError) as exc:
            # R10: log class-only at ERROR, full stack trace at DEBUG only.
            _LOGGER.error(
                "Enable Banking client init failed — PEM key invalid (%s)",
                type(exc).__name__,
            )
            _LOGGER.debug(
                "Enable Banking client init exception detail",
                exc_info=True,
            )
            self._raise_credentials_issue("invalid_pem")
            return None

        # Successful client creation — clear any stale repair issue
        self._clear_credentials_issue()
        return self._banking_client

    def _raise_credentials_issue(self, kind: str) -> None:
        """Surface credential problems via the Repairs flow."""
        try:
            from homeassistant.helpers import issue_registry as ir

            translation_key = (
                "credentials_missing"
                if kind == "missing"
                else "credentials_invalid_pem"
            )
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                f"credentials_{kind}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=translation_key,
                learn_more_url=(
                    "https://enablebanking.com/docs/api/reference/"
                ),
            )
        except Exception:
            _LOGGER.debug("Could not create credentials repair issue",
                          exc_info=True)

    def _clear_credentials_issue(self) -> None:
        """Remove credential-related repair issues after recovery."""
        try:
            from homeassistant.helpers import issue_registry as ir

            for kind in ("missing", "invalid_pem"):
                ir.async_delete_issue(
                    self._hass, DOMAIN, f"credentials_{kind}"
                )
        except Exception:
            pass

    def _raise_storage_corrupt_issue(
        self, storage_key: str, error_class: str
    ) -> None:
        """Raise a Repair issue for a corrupt .storage/ file (R8).

        Only the storage key name and Python exception class are included
        in the repair issue — never raw exception text or stack traces.
        """
        try:
            from homeassistant.helpers import issue_registry as ir

            ir.async_create_issue(
                self._hass,
                DOMAIN,
                f"storage_corrupt_{storage_key}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="storage_corrupt",
                translation_placeholders={
                    "storage_key": storage_key,
                    "error_class": error_class,
                },
            )
        except Exception:
            _LOGGER.debug(
                "Could not create storage_corrupt repair issue", exc_info=True
            )

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
        """Save transactions, balances, rate-limit and stats to cache.

        R5: saves the per-account dict (tx_by_account) as the canonical
        format.  The flat ``transactions`` key is kept for one-version
        backward-compatibility but is no longer the authoritative source.
        """
        await self._transaction_store.async_save(
            {
                # R5: per-account dict is the canonical storage format.
                "tx_by_account": self._tx_by_account,
                # Legacy flat list — kept so older versions can still read
                # something useful if rolled back.
                "transactions": self._transactions,
                "balances": self._balances,
                "last_refresh": (
                    self._last_refresh.isoformat()
                    if self._last_refresh
                    else None
                ),
                "rate_limited_until": (
                    self._rate_limited_until.isoformat()
                    if self._rate_limited_until
                    else None
                ),
                "last_refresh_stats": self._last_refresh_stats,
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
