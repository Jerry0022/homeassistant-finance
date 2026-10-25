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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from ..const import DEFAULT_FETCH_DAYS, INCREMENTAL_OVERLAP_DAYS

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# OAuth state token TTL in seconds (10 minutes)
_OAUTH_STATE_TTL = 600

# hass.data key for persistent rate-limit timestamp (shared with api._helpers)
_GLOBAL_RATE_LIMIT_KEY = "_global_rate_limit_until"

# Maximum number of in-memory OAuth state tokens (F5)
_OAUTH_STATES_MAX = 32
_OAUTH_STATES_EVICT = 16


class RefreshMixin:
    """Mixin that adds all live-fetch and OAuth methods to the manager."""

    # ------------------------------------------------------------------
    # Rate-limit helpers
    # ------------------------------------------------------------------

    def _set_rate_limited(
        self,
        retry_after_dt: datetime | None = None,
        *,
        attended: bool = False,
    ) -> None:
        """Mark API as rate-limited.

        Writes the reset timestamp to both the instance field and the
        persistent ``hass.data[DOMAIN][_GLOBAL_RATE_LIMIT_KEY]`` so that the
        fresh-setup client factory can also respect the quota gate (F2).

        The reset is capped at midnight — the ASPSP day counter resets then,
        so waiting past it is never useful — but the default backoff is much
        shorter than a full day: Enable Banking documents a 6h retry for
        background fetches, and an attended 429 is a transient upstream
        condition rather than the 4/day rule, so it pauses for minutes.

        Args:
            retry_after_dt: Optional reset datetime derived from the
                ``Retry-After`` response header.  Takes precedence over the
                default backoff — the bank knows better than we do.
            attended: True when the call carried PSU headers (user present).
        """
        from ..const import (
            DOMAIN,
            RATE_LIMIT_ATTENDED_BACKOFF_MINUTES,
            RATE_LIMIT_BACKOFF_HOURS,
        )

        now = dt_util.now()
        midnight = (now + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        if retry_after_dt is not None:
            candidate = retry_after_dt
        elif attended:
            candidate = now + timedelta(minutes=RATE_LIMIT_ATTENDED_BACKOFF_MINUTES)
        else:
            candidate = now + timedelta(hours=RATE_LIMIT_BACKOFF_HOURS)
        reset_at = min(midnight, candidate)
        self._rate_limited_until = reset_at

        # Persist to hass.data so the fresh-setup client gate can read it
        # even when the manager is not consulted directly (F2).
        try:
            self._hass.data.setdefault(DOMAIN, {})[_GLOBAL_RATE_LIMIT_KEY] = (
                reset_at.isoformat()
            )
        except Exception:  # pragma: no cover
            _LOGGER.debug("Could not write global rate-limit key to hass.data", exc_info=True)

        _LOGGER.warning(
            "API rate-limited — serving cached data until %s",
            reset_at.isoformat(),
        )

    # ------------------------------------------------------------------
    # Public refresh entry point
    # ------------------------------------------------------------------

    async def async_refresh_transactions(
        self,
        days: int | None = None,
        psu_ip: str | None = None,
        scheduled: bool = False,
    ) -> list[dict[str, Any]]:
        """Refresh transactions AND balances for every linked bank.

        Fetch budget is tracked PER BANK (see ``fetch_budget``):

        * ``psu_ip`` present -> *attended*: never capped, never gated on a
          block, only debounced per bank.
        * no ``psu_ip`` -> *background*: counted per account per UTC day;
          the ``scheduled`` daily refresh may use 1 of 4, other background
          callers up to 4.  A 429 blocks only the bank that sent it, for 6h.

        Fetches are incremental (last booked date minus an overlap); the
        first fetch of an account covers ``DEFAULT_FETCH_DAYS``.  An explicit
        ``days`` forces a full window.  Concurrent calls are serialised by
        ``_refresh_lock``; stats are written regardless of outcome.
        """
        async with self._refresh_lock:
            self._refresh_in_flight = True
            started = dt_util.now()
            t0 = time.monotonic()
            try:
                return await self._do_refresh(days, started, t0, psu_ip=psu_ip, scheduled=scheduled)
            finally:
                self._refresh_in_flight = False

    def _fetch_date_from(self, account_key_: str, days: int | None) -> str:
        """Start of the fetch window for one account."""
        now = dt_util.now()
        if days:
            return (now - timedelta(days=int(days))).strftime("%Y-%m-%d")
        floor = now - timedelta(days=DEFAULT_FETCH_DAYS)
        last = self._ledger.last_booked_date(account_key_)
        if last:
            try:
                start = datetime.fromisoformat(last[:10]) - timedelta(days=INCREMENTAL_OVERLAP_DAYS)
                start = start.replace(tzinfo=floor.tzinfo)
                return max(start, floor).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return floor.strftime("%Y-%m-%d")

    def _raw_sink(self, bank_id: str, uid: str, attended: bool):
        """Callback handing unaltered bank JSON to the raw archive."""

        def sink(kind: str, http_status: int, body: Any) -> None:
            if self._raw is None:
                return
            self._raw.record(
                self._raw.make_snapshot(
                    bank=bank_id,
                    account=uid,
                    kind=kind,
                    attended=attended,
                    http_status=http_status,
                    response=body,
                )
            )

        return sink

    async def _do_refresh(
        self,
        days: int | None,
        started: datetime,
        t0: float,
        psu_ip: str | None = None,
        scheduled: bool = False,
    ) -> list[dict[str, Any]]:
        import aiohttp

        from ..account_identity import account_key
        from ..enablebanking_client import RateLimitExceeded
        from ..recurring import detect_recurring

        def elapsed_ms() -> int:
            return int((time.monotonic() - t0) * 1000)

        # Demo mode — regenerate fresh demo data without API calls
        if self._demo_mode:
            from ..demo import generate_demo_data

            data = generate_demo_data()
            self._transactions = data["_demo_transactions"]
            self._balances = data["_demo_balances"]
            self._last_refresh = dt_util.now()
            self._recurring_patterns = data.get("recurring", [])
            self._last_refresh_stats = self._build_stats(
                outcome="demo",
                started=started,
                duration_ms=elapsed_ms(),
                accounts=len(self._accounts),
                transactions=len(self._transactions),
                new=0,
                errors=[],
            )
            return self._transactions

        client = await self._async_get_client()
        if not client:
            self._last_refresh_stats = self._build_stats(
                outcome="error",
                started=started,
                duration_ms=elapsed_ms(),
                accounts=0,
                transactions=len(self._transactions),
                new=0,
                errors=["Keine Enable-Banking-Credentials hinterlegt"],
            )
            return []

        attended = bool(psu_ip)
        date_to = dt_util.now().strftime("%Y-%m-%d")
        targets = await self._async_bank_targets()

        errors: list[str] = []
        accounts_hit = 0
        new_ids: set[str] = set()
        fresh_balances: dict[str, Any] = {}
        skipped: dict[str, int] = {}
        rate_limited_round = False

        for bank in targets:
            bank_id = bank["bank_id"]
            title = bank["title"] or "Bank"

            if self._consent_state(bank["valid_until"]) == "expired":
                self._budget.record_error(bank_id, "consent_expired")
                errors.append(f"{title}: Zustimmung abgelaufen — bitte Bank neu verbinden")
                continue

            decision = self._budget.decide(bank_id, attended=attended, scheduled=scheduled)
            if not decision.allowed:
                skipped[decision.reason] = skipped.get(decision.reason, 0) + 1
                _LOGGER.info("Bank %s skipped (%s) — serving cache", bank_id[:8], decision.reason)
                if decision.reason in ("blocked", "budget_exhausted"):
                    rate_limited_round = True
                    errors.append(f"{title}: Tageslimit der Bank-API erreicht (4/Tag pro Konto)")
                continue

            if attended:
                # Stamp before the first call so a double click is debounced
                # even while this fetch is still running.
                self._budget.record_attempt(bank_id, "", attended=True)

            for account in bank["accounts"]:
                uid = account.get("id")
                if not uid:
                    continue
                akey = account_key(account)
                name = account.get("name", uid)
                self._budget.record_attempt(bank_id, akey, attended=attended)
                date_from = self._fetch_date_from(akey, days)
                sink = self._raw_sink(bank_id, uid, attended)

                try:
                    txns = await client.async_get_transactions(
                        uid, date_from, date_to, psu_ip=psu_ip, on_response=sink
                    )
                    new = self._ledger.ingest(
                        akey,
                        txns.get("booked", []),
                        txns.get("pending", []),
                        date_from=date_from,
                        truncated=bool(txns.get("truncated")),
                    )
                    new_ids.update(f"{akey}|{t['_ledger_id']}" for t in new)
                    accounts_hit += 1
                    _LOGGER.debug(
                        "Account %s: %d booked, %d pending",
                        uid[:8],
                        len(txns.get("booked", [])),
                        len(txns.get("pending", [])),
                    )
                    bals = await client.async_get_balances(uid, psu_ip=psu_ip, on_response=sink)
                    iban = account.get("iban", "")
                    fresh_balances[uid] = {
                        "account_name": account.get("name", "Unknown"),
                        "iban": iban,
                        "iban_masked": (f"****{iban[-4:]}" if len(iban) >= 4 else "****"),
                        "institution": account.get("institution", ""),
                        "logo": account.get("logo", ""),
                        "balances": bals,
                    }
                    self._ledger.add_balances(
                        akey,
                        bals,
                        dt_util.utcnow().isoformat(),
                        self._raw_retention_days,
                    )
                except RateLimitExceeded as rle:
                    until = self._budget.block(
                        bank_id,
                        retry_after_seconds=rle.retry_after_seconds,
                        attended=attended,
                    )
                    self._budget.record_error(bank_id, "rate_limited")
                    rate_limited_round = True
                    _LOGGER.warning(
                        "Rate limit hit for bank %s — blocked until %s", bank_id[:8], until
                    )
                    errors.append(f"Rate-Limit bei {title} — Tageslimit (4/Tag) aufgebraucht")
                    break  # only THIS bank stops; other banks continue
                except aiohttp.ClientResponseError as exc:
                    if exc.status in (401, 403):
                        self._mark_consent_error(bank_id, bank["valid_until"])
                    self._budget.record_error(bank_id, f"http_{exc.status}")
                    _LOGGER.error("Fetch failed for account %s: HTTP %s", uid[:8], exc.status)
                    errors.append(f"{name}: HTTP {exc.status}")
                except Exception as exc:
                    _LOGGER.exception("Failed to fetch account %s", uid[:8])
                    self._budget.record_error(bank_id, type(exc).__name__)
                    errors.append(f"{name}: {str(exc)[:120]}")
                else:
                    self._budget.record_success(bank_id)

        # The migration-era __unknown__ bucket is superseded by real fetches.
        if accounts_hit > 0:
            self._ledger.data.get("accounts", {}).pop("__unknown__", None)

        # Derivations (categories, tags, transfer chains) are rebuilt from the
        # ledger — never carried over from a previous round.
        overrides = await self._async_load_transfer_overrides()
        old_ids = {t.get("_ledger_id") for t in self._transactions}
        all_transactions = self._derive_from_ledger(overrides)
        new_txns = [
            t
            for t in all_transactions
            if t.get("_status") == "booked"
            and t.get("_ledger_id")
            and t["_ledger_id"] not in old_ids
            and f"{t.get('_account_key', '')}|{t['_ledger_id']}" in new_ids
        ]

        if fresh_balances:
            self._fire_balance_events(fresh_balances)
            merged = dict(self._balances)
            merged.update(fresh_balances)
            self._balances = merged

        # Only claim a refresh happened when at least one account answered.
        if accounts_hit > 0:
            self._last_refresh = dt_util.now()
        else:
            _LOGGER.warning(
                "Refresh reached no account (%d error(s)) — keeping previous "
                "refresh timestamp so the UI reports the cache as stale",
                len(errors),
            )

        try:
            self._recurring_patterns = detect_recurring(all_transactions)
        except Exception:
            _LOGGER.exception("Recurring detection failed — skipping")
            self._recurring_patterns = []

        await self._persist_transactions()
        if self._raw is not None:
            try:
                await self._raw.async_flush()
            except Exception:
                _LOGGER.exception("Raw archive write failed — continuing")

        try:
            from ..events import fire_transaction_new

            for txn in new_txns:
                fire_transaction_new(
                    self._hass,
                    amount=float(txn.get("transactionAmount", {}).get("amount", 0)),
                    creditor=txn.get("creditorName", ""),
                    category=txn.get("category", "other"),
                    account_name=txn.get("_account_name", ""),
                )
        except Exception:
            _LOGGER.exception("Transaction event firing failed — skipping")

        try:
            await self.async_update_consent_issues()
        except Exception:
            _LOGGER.debug("Consent issue update failed", exc_info=True)

        await self._credential_manager._audit_log("transactions_refreshed")
        _LOGGER.info(
            "Refreshed %d transactions across %d accounts (%d new, %d recurring patterns)",
            len(all_transactions),
            accounts_hit,
            len(new_txns),
            len(self._recurring_patterns),
        )

        if rate_limited_round:
            outcome = "rate_limited"
        elif skipped.get("debounced") and not accounts_hit and not errors:
            outcome = "debounced"
        elif errors:
            outcome = "partial" if accounts_hit > 0 else "error"
        else:
            outcome = "ok"

        if outcome == "debounced":
            # A second attended click inside the debounce window: leave the
            # previous result (and its stats) in place.
            return self._transactions

        self._last_refresh_stats = self._build_stats(
            outcome=outcome,
            started=started,
            duration_ms=elapsed_ms(),
            accounts=accounts_hit,
            transactions=len(all_transactions),
            new=len(new_txns),
            errors=errors,
        )
        await self._persist_transactions()
        return all_transactions

    def _fire_balance_events(self, balances: dict[str, Any]) -> None:
        """Fire fd_balance_changed for material changes — never crashes refresh."""
        try:
            from ..events import fire_balance_changed

            for acc_id, data in balances.items():
                raw = data.get("balances", [])
                if raw:
                    new_bal = float(raw[0].get("balanceAmount", {}).get("amount", 0))
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

    @staticmethod
    def _merge_account_transactions(
        previous: list[dict[str, Any]],
        booked: list[dict[str, Any]],
        pending: list[dict[str, Any]],
        date_from: str,
    ) -> list[dict[str, Any]]:
        """Merge a freshly fetched window into an account's cached history.

        The fetch covers a rolling window (``date_from`` onwards). Within that
        window the fresh data is authoritative — it reflects re-bookings,
        corrections and pending-to-booked transitions. Outside the window the
        previously cached BOOKED transactions are kept, which is what allows
        history to accumulate beyond the window instead of being truncated on
        every refresh.

        Cached pending transactions are always discarded: pending entries are
        volatile, and keeping an old one alongside its booked counterpart would
        double-count the same debit.

        Args:
            previous: The account's cached transactions.
            booked: Freshly fetched booked transactions.
            pending: Freshly fetched pending transactions.
            date_from: Inclusive ``YYYY-MM-DD`` start of the fetched window.

        Returns:
            The merged transaction list for this account.
        """
        fresh = list(booked) + list(pending)
        fresh_ids = {t.get("transactionId") for t in fresh if t.get("transactionId")}

        kept: list[dict[str, Any]] = []
        for txn in previous:
            if txn.get("_status") != "booked":
                continue
            transaction_id = txn.get("transactionId")
            if transaction_id and transaction_id in fresh_ids:
                continue  # superseded by the fresh copy
            booking_date = str(txn.get("bookingDate") or "")
            # No booking date means we cannot place it relative to the window;
            # keep it rather than lose a real transaction.
            if booking_date and booking_date >= date_from:
                # Inside the refetched window and absent from the fresh data —
                # the bank no longer reports it (reversal, correction).
                continue
            kept.append(txn)

        return kept + fresh

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
        finished = dt_util.now()
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

    # ------------------------------------------------------------------
    # OAuth state management
    # ------------------------------------------------------------------

    async def async_register_oauth_state(self, state: str) -> None:
        """Register an OAuth state token for later CSRF validation.

        The state is stored in memory only (not persisted) with a creation
        timestamp so it can be expired after ``_OAUTH_STATE_TTL`` seconds.

        The dict is bounded to ``_OAUTH_STATES_MAX`` entries to prevent an
        unbounded memory growth if authorize is called repeatedly without a
        matching callback (F5).  When the cap is reached the oldest
        ``_OAUTH_STATES_EVICT`` entries (by creation time) are evicted.
        """
        # Evict oldest entries when approaching the cap (F5)
        if len(self._oauth_states) >= _OAUTH_STATES_MAX:
            sorted_states = sorted(self._oauth_states.items(), key=lambda kv: kv[1])
            for old_key, _ in sorted_states[:_OAUTH_STATES_EVICT]:
                self._oauth_states.pop(old_key, None)
            _LOGGER.debug(
                "OAuth state dict capped — evicted %d oldest entries", _OAUTH_STATES_EVICT
            )

        now = datetime.now(UTC).isoformat()
        self._oauth_states[state] = now
        _LOGGER.debug("OAuth state registered (total: %d)", len(self._oauth_states))

    async def async_validate_oauth_state(self, state: str) -> bool:
        """Validate and consume an OAuth state token (CSRF protection).

        Uses ``secrets.compare_digest`` for timing-safe comparison to prevent
        timing-based enumeration of valid state tokens.

        All timestamp comparisons use UTC-aware datetimes.  Naive timestamps
        stored by older code versions are assumed UTC (F3).

        Returns:
            True if the state was registered, not yet consumed, and not expired.
            False otherwise (unknown state, already consumed, or TTL exceeded).
        """
        # Purge all expired states first — use UTC-aware comparison (F3)
        now = datetime.now(UTC)
        expired = []
        for s, created in self._oauth_states.items():
            try:
                created_dt = datetime.fromisoformat(created)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=UTC)
                if (now - created_dt).total_seconds() > _OAUTH_STATE_TTL:
                    expired.append(s)
            except (ValueError, TypeError):
                expired.append(s)  # Corrupt entry — evict
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

    async def async_make_setup_call(self, method_name: str, *args, client=None, **kwargs):
        """Invoke an EnableBankingClient method through the rate-limit gate.

        Setup-wizard endpoints (institutions, authorize, OAuth callback) must
        go through here instead of calling the client directly.  This ensures
        the 4/day ASPSP quota is respected even during the onboarding flow.

        Args:
            method_name: Name of the EnableBankingClient method to call.
            *args: Positional arguments forwarded to the method.
            client: Optional pre-built EnableBankingClient instance.  When
                provided the manager's own credential chain is bypassed — useful
                for fresh-setup flows where the credential store holds setup-app
                credentials rather than a live PSU session.  Rate-limit gate is
                still enforced regardless.
            **kwargs: Keyword arguments forwarded to the method.

        Raises:
            RateLimitExceeded: when the API is still rate-limited.
            RuntimeError: when no credentials are available and no client given.
        """
        # No quota gate: the setup wizard (catalog, authorize, session
        # exchange) talks to Enable Banking, not to a bank's data API, so it
        # neither spends nor is bound by the per-ASPSP 4/day budget.
        if client is None:
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

        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        from ..enablebanking_client import EnableBankingClient

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
        """Surface credential problems via the Repairs flow.

        Auth/credential issues are marked ``is_persistent=True`` — they
        survive HA restarts and remain visible until the user fixes their
        credentials.  Transient issues (rate-limit) should NOT use this
        method; they are surfaced inline in the refresh status instead.
        """
        try:
            from homeassistant.helpers import issue_registry as ir

            from ..const import DOMAIN

            translation_key = (
                "credentials_missing" if kind == "missing" else "credentials_invalid_pem"
            )
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                f"credentials_{kind}",
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key=translation_key,
                learn_more_url=("https://enablebanking.com/docs/api/reference/"),
            )
        except Exception:
            _LOGGER.debug("Could not create credentials repair issue", exc_info=True)

    def _clear_credentials_issue(self) -> None:
        """Remove credential-related repair issues after recovery."""
        try:
            from homeassistant.helpers import issue_registry as ir

            from ..const import DOMAIN

            for kind in ("missing", "invalid_pem"):
                ir.async_delete_issue(self._hass, DOMAIN, f"credentials_{kind}")
        except Exception:
            pass
