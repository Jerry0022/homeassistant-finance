"""RefreshMixin — live-fetch logic for FinanceDashboardManager.

Covers the ONLY allowed live-fetch path: user-triggered refresh of
transactions and balances.  All methods here may call the Enable Banking
API.

Also includes OAuth state management (register/validate state tokens),
the setup-call proxy, and credential/issue helpers.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# OAuth state token TTL in seconds (10 minutes)
_OAUTH_STATE_TTL = 600


class RefreshMixin:
    """Mixin that adds all live-fetch and OAuth methods to the manager."""

    # ------------------------------------------------------------------
    # Rate-limit helpers
    # ------------------------------------------------------------------

    def _set_rate_limited(
        self, retry_after_dt: Optional[datetime] = None
    ) -> None:
        """Mark API as rate-limited.

        Args:
            retry_after_dt: Optional earlier reset datetime derived from the
                ``Retry-After`` response header.  When provided the reset is
                ``min(midnight, retry_after_dt)`` so we never wait *longer*
                than midnight but may wait less when the API signals a shorter
                window.  Falls back to midnight when ``None``.
        """
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        if retry_after_dt is not None:
            reset_at = min(midnight, retry_after_dt)
        else:
            reset_at = midnight
        self._rate_limited_until = reset_at
        _LOGGER.warning(
            "API rate-limited — serving cached data until %s",
            reset_at.isoformat(),
        )

    # ------------------------------------------------------------------
    # Public refresh entry point
    # ------------------------------------------------------------------

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
        from ..enablebanking_client import RateLimitExceeded
        from ..recurring import detect_recurring
        from ..transfer_detector import (
            apply_overrides,
            detect_transfer_chains,
            enrich_transactions,
        )

        # Demo mode — regenerate fresh demo data without API calls
        if self._demo_mode:
            from ..demo import generate_demo_data

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
            except RateLimitExceeded as _rle:
                _LOGGER.warning(
                    "Rate limit hit for account %s — stopping all fetches",
                    account_id,
                )
                retry_after_dt = None
                if _rle.retry_after_seconds is not None:
                    retry_after_dt = datetime.now() + timedelta(
                        seconds=_rle.retry_after_seconds
                    )
                self._set_rate_limited(retry_after_dt)
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
            from ..events import fire_transaction_new

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
        self, client: Any, errors: list[str]
    ) -> dict[str, Any]:
        """Live-fetch balances from the API and update the cache.

        NEVER call this directly from an HTTP read endpoint — only from
        user-triggered refresh paths.  Reads should go through
        ``async_get_balance()`` which is cache-only.
        """
        from ..enablebanking_client import RateLimitExceeded

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
            except RateLimitExceeded as _rle:
                _LOGGER.warning(
                    "Rate limit hit fetching balance for %s", account_id
                )
                retry_after_dt = None
                if _rle.retry_after_seconds is not None:
                    retry_after_dt = datetime.now() + timedelta(
                        seconds=_rle.retry_after_seconds
                    )
                self._set_rate_limited(retry_after_dt)
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
            from ..events import fire_balance_changed

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

    # ------------------------------------------------------------------
    # OAuth state management
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Setup call proxy
    # ------------------------------------------------------------------

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
        from ..enablebanking_client import RateLimitExceeded

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

    # ------------------------------------------------------------------
    # Client factory + credential issue helpers
    # ------------------------------------------------------------------

    async def _async_get_client(self):
        """Get or create Enable Banking client with current credentials."""
        if self._banking_client:
            return self._banking_client

        creds = await self._credential_manager.async_get_api_credentials()
        if not creds:
            _LOGGER.error("No Enable Banking credentials available")
            self._raise_credentials_issue("missing")
            return None

        from ..enablebanking_client import EnableBankingClient
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
            from ..const import DOMAIN

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
            from ..const import DOMAIN

            for kind in ("missing", "invalid_pem"):
                ir.async_delete_issue(
                    self._hass, DOMAIN, f"credentials_{kind}"
                )
        except Exception:
            pass
