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
import re
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..budget_plan import BudgetPlan, BudgetPlanStore, CostPosition
from ..const import (
    BENCHMARK_METRIC_SOURCES,
    DEFAULT_SPLIT_MODEL,
    DEFAULT_WATER_BENCHMARK,
    DOMAIN,
    ENABLEBANKING_RATE_LIMIT_DAILY,
    OPT_WATER_RATIO,
    OWNER_SHARED,
    STORAGE_KEY_TRANSFER_OVERRIDES,
)
from ..household import HouseholdMember, HouseholdModel, model_from_plan
from ..transfer_detector import (
    apply_overrides,
    get_effective_transactions,
)
from ..transfer_plan import build_transfer_plan
from ._persistence import PersistenceMixin
from ._refresh import RefreshMixin

_LOGGER = logging.getLogger(__name__)

TRANSACTION_CACHE_KEY = f"{DOMAIN}_transactions"
TRANSACTION_CACHE_VERSION = 1

# OAuth state token TTL in seconds (10 minutes) — kept here for test imports
_OAUTH_STATE_TTL = 600


class FinanceDashboardManager(RefreshMixin, PersistenceMixin):
    """Central orchestrator for the Finance integration.

    Inherits from:
    - RefreshMixin   (_refresh.py) — all live-fetch + OAuth methods
    - PersistenceMixin (_persistence.py) — storage read/write
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self._hass = hass
        self._entry = entry
        self._credential_manager = None
        self._banking_client = None
        self._categorizer = None
        self._transaction_store = Store(hass, TRANSACTION_CACHE_VERSION, TRANSACTION_CACHE_KEY)
        self._accounts: list[dict[str, Any]] = entry.data.get("accounts", [])
        # Per-account transaction cache: account_id → list[tx].
        # Partial refresh failures only affect the failed account's slice —
        # other accounts keep their last-known data (R5 fix).
        self._tx_by_account: dict[str, list[dict[str, Any]]] = {}
        # Flat view (legacy + internal use) — kept in sync with _tx_by_account.
        self._transactions: list[dict[str, Any]] = []
        self._balances: dict[str, Any] = {}
        self._last_refresh: datetime | None = None
        self._rate_limited_until: datetime | None = None
        self._transfer_override_store = Store(hass, 1, STORAGE_KEY_TRANSFER_OVERRIDES)
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
        # The PLAN side: the migrated household spreadsheet (cost positions +
        # per-person income). Live bank data supplies the ACTUAL side; the two
        # are compared per position in the monthly summary.
        self._plan_store = BudgetPlanStore(hass)
        # Lazily created on first benchmark request — it reads .storage/ and
        # nothing needs it during setup.
        self._benchmark_provider = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def rate_limited_until(self) -> datetime | None:
        """Return the datetime until which the API is rate-limited, or None."""
        if self._rate_limited_until and dt_util.now() < self._rate_limited_until:
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

    @property
    def demo_mode(self) -> bool:
        """Return whether demo mode is active."""
        return self._demo_mode

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------

    def set_demo_mode(self, enabled: bool) -> None:
        """Toggle demo mode on or off.

        When enabled, loads synthetic demo data into the manager's state.
        When disabled, clears demo data and reverts to real cached data.
        """
        self._demo_mode = enabled
        if enabled:
            from ..demo import generate_demo_data

            data = generate_demo_data()
            self._accounts = data["_demo_accounts"]
            self._transactions = data["_demo_transactions"]
            self._balances = data["_demo_balances"]
            self._last_refresh = dt_util.now()
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_initialize(self) -> None:  # noqa: PLR0915
        """Initialize all sub-components."""
        from ..categorizer import TransactionCategorizer
        from ..credential_manager import CredentialManager

        self._credential_manager = CredentialManager(self._hass)
        await self._credential_manager.async_initialize()

        self._categorizer = TransactionCategorizer()

        # Load the budget plan. A read failure must not block startup — the
        # store falls back to an empty plan and the UI prompts for an import.
        await self._plan_store.async_load()

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
            self._raise_storage_corrupt_issue(TRANSACTION_CACHE_KEY, type(exc).__name__)
        if cached and ("transactions" in cached or "tx_by_account" in cached):
            # R5: prefer per-account dict; fall back to flat list (migration).
            raw_tx_by_account = cached.get("tx_by_account")
            if isinstance(raw_tx_by_account, dict):
                self._tx_by_account = raw_tx_by_account
                self._transactions = [tx for txs in self._tx_by_account.values() for tx in txs]
                # Deterministic sort after flatten
                self._transactions.sort(key=lambda t: t.get("bookingDate", ""), reverse=True)
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
                    # Ensure UTC-aware for comparison (F3)
                    if rl_dt.tzinfo is None:
                        rl_dt = rl_dt.replace(tzinfo=UTC)
                    if rl_dt > dt_util.now():
                        self._rate_limited_until = rl_dt
                        # Mirror to hass.data so the fresh-setup client gate
                        # can enforce the quota even before manager is reached (F2).
                        self._hass.data.setdefault(DOMAIN, {})[
                            "_global_rate_limit_until"
                        ] = rl_dt.isoformat()
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

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def async_set_accounts(self, accounts: list[dict[str, Any]]) -> None:
        """Update the in-memory account list (encapsulated write path).

        Validates that *accounts* is a list; persists immediately to the
        config-entry data so the new assignments survive an HA restart.
        """
        if not isinstance(accounts, list):
            raise TypeError(f"async_set_accounts: expected list, got {type(accounts).__name__}")
        self._accounts = accounts
        # Mirror to config-entry data so accounts survive HA restart
        try:
            new_data = {**self._entry.data, "accounts": accounts}
            self._hass.config_entries.async_update_entry(self._entry, data=new_data)
        except Exception:
            _LOGGER.warning(
                "async_set_accounts: failed to persist to config entry",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Account refresh
    # ------------------------------------------------------------------

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
                _LOGGER.warning("Failed to refresh account %s", acc_id)
                refreshed.append(account)

        self._accounts = refreshed
        await self._credential_manager._audit_log("accounts_refreshed")
        return self._accounts

    # ------------------------------------------------------------------
    # Cache read endpoints (no API calls)
    # ------------------------------------------------------------------

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
            if self._is_in_month(txn, target_month, target_year) and txn.get("_status") == "booked"
        ]

        # Count excluded transfers for transparency
        all_monthly = [
            txn
            for txn in self._transactions
            if self._is_in_month(txn, target_month, target_year) and txn.get("_status") == "booked"
        ]
        excluded_chain_txns = [
            txn
            for txn in all_monthly
            if txn.get("_transfer_role") in ("intermediate", "destination")
            and txn.get("_transfer_confirmed") is not False
        ]
        excluded_amount = sum(
            abs(float(t.get("transactionAmount", {}).get("amount", 0))) for t in excluded_chain_txns
        )

        # Group by category
        category_totals: dict[str, float] = {}
        total_income = 0.0
        total_expenses = 0.0

        for txn in monthly_txns:
            amount = float(txn.get("transactionAmount", {}).get("amount", 0))
            category = txn.get("category", "other")

            if amount > 0:
                total_income += amount
            else:
                total_expenses += abs(amount)

            category_totals[category] = category_totals.get(category, 0) + amount

        # Build household split data from per-person accounts
        # Graceful degradation: household features must never crash the coordinator
        household = None
        try:
            household = self._compute_household(
                monthly_txns, total_expenses, target_month, target_year
            )
        except Exception:
            _LOGGER.exception("Household computation failed — skipping")

        # Recurring patterns (already detected during refresh)
        recurring_top = self._recurring_patterns[:10]

        # Fixed vs variable costs
        fixed_cats = {"housing", "loans", "utilities", "insurance"}
        fixed_total = sum(abs(category_totals.get(c, 0)) for c in fixed_cats)
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
            "categories": {k: round(v, 2) for k, v in category_totals.items()},
            "transaction_count": len(monthly_txns),
            "excluded_transfers": {
                "chain_count": len(
                    {
                        t.get("_transfer_chain_id")
                        for t in excluded_chain_txns
                        if t.get("_transfer_chain_id")
                    }
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
            "last_refresh": (self._last_refresh.isoformat() if self._last_refresh else None),
            "rate_limited_until": (
                self._rate_limited_until.isoformat() if self.rate_limited_until else None
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
        _LOGGER.info("Re-categorized %d transactions", len(self._transactions))

    async def async_set_budget_limit(self, category: str, limit: float) -> None:
        """Set a budget limit for a category via the Number entity."""
        entity_id = f"number.fd_budget_{category}"
        state = self._hass.states.get(entity_id)
        if state is not None:
            await self._hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": limit},
            )
            _LOGGER.info("Budget limit for %s set to %.2f", category, limit)
        else:
            _LOGGER.warning("Budget entity %s not found", entity_id)

    async def async_export_csv(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        categories: list[str] | None = None,
    ) -> str:
        """Export transactions as CSV file."""
        from ..export import async_export_csv

        return await async_export_csv(
            self._hass,
            self._transactions,
            date_from=date_from,
            date_to=date_to,
            categories=categories,
        )

    def get_cached_transactions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get cached transactions (no API call).

        Returns sanitized transactions for API responses.
        Full details only — caller must check admin status.
        """
        return self._transactions[:limit]

    # Cache staleness threshold — matches the coordinator constant.
    # Cache is considered stale when older than this value.
    _CACHE_STALE_THRESHOLD_SECONDS: int = 6 * 3600  # 6 hours

    def get_refresh_status(self) -> dict[str, Any]:
        """Return a compact status snapshot for the UI status endpoint.

        Pure cache read — NEVER touches the banking API. Safe for
        unbounded polling while a refresh is in flight.
        """
        now = dt_util.now()
        cache_age_seconds: int | None = None
        cache_is_stale: bool = False
        if self._last_refresh:
            cache_age_seconds = int((now - self._last_refresh).total_seconds())
            cache_is_stale = cache_age_seconds > self._CACHE_STALE_THRESHOLD_SECONDS
        return {
            "is_refreshing": self._refresh_in_flight,
            "last_refresh": (self._last_refresh.isoformat() if self._last_refresh else None),
            "cache_age_seconds": cache_age_seconds,
            "cache_is_stale": cache_is_stale,
            "rate_limited_until": (
                self._rate_limited_until.isoformat() if self.rate_limited_until else None
            ),
            "stats": dict(self._last_refresh_stats),
            "account_count": len(self._accounts),
            "transaction_count": len(self._transactions),
            "has_cache": bool(self._transactions) or bool(self._balances),
            "demo_mode": self._demo_mode,
            # Expose the daily rate-limit cap so the frontend can render
            # the "4/day" label dynamically instead of hardcoding it.
            "rate_limit_per_day": ENABLEBANKING_RATE_LIMIT_DAILY,
            # Attended-refresh-on-open policy, so the panel does not need to
            # know the option keys or defaults.
            "auto_refresh_on_open": self._auto_refresh_on_open,
            "auto_refresh_max_age_seconds": self._auto_refresh_max_age_seconds,
        }

    @property
    def _auto_refresh_on_open(self) -> bool:
        """Whether opening the panel may trigger one attended live fetch."""
        from ..const import DEFAULT_AUTO_REFRESH_ON_OPEN, OPT_AUTO_REFRESH_ON_OPEN

        options = getattr(self._entry, "options", {}) or {}
        return bool(options.get(OPT_AUTO_REFRESH_ON_OPEN, DEFAULT_AUTO_REFRESH_ON_OPEN))

    @property
    def _auto_refresh_max_age_seconds(self) -> int:
        """Cache age above which opening the panel refreshes live data."""
        from ..const import (
            DEFAULT_AUTO_REFRESH_MAX_AGE_MINUTES,
            OPT_AUTO_REFRESH_MAX_AGE_MINUTES,
        )

        options = getattr(self._entry, "options", {}) or {}
        minutes = options.get(
            OPT_AUTO_REFRESH_MAX_AGE_MINUTES, DEFAULT_AUTO_REFRESH_MAX_AGE_MINUTES
        )
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = DEFAULT_AUTO_REFRESH_MAX_AGE_MINUTES
        # A zero/negative threshold would refresh on every single open.
        return max(minutes, 1) * 60

    # ------------------------------------------------------------------
    # Budget plan — the migrated spreadsheet model
    # ------------------------------------------------------------------

    @property
    def budget_plan(self) -> BudgetPlan:
        """The current budget plan (empty until imported or entered)."""
        return self._plan_store.plan

    def _split_options(self) -> tuple[str, str, dict[str, float]]:
        """Split configuration from the config entry options."""
        return (
            self._entry.options.get("split_model", DEFAULT_SPLIT_MODEL),
            self._entry.options.get("remainder_mode", "none"),
            self._entry.options.get("custom_ratios", {}) or {},
        )

    async def async_import_spreadsheet(self, path: str) -> dict[str, Any]:
        """Import a household workbook into the budget plan.

        Runs the blocking openpyxl parse in an executor so the event loop is
        never held. Replaces the plan wholesale — an import is a migration, not
        a merge, so a partially parsed workbook cannot leave a hybrid plan.

        Returns the import report (counts and warnings only, never amounts).
        """
        from ..spreadsheet_import import parse_workbook

        plan, report = await self._hass.async_add_executor_job(parse_workbook, path)
        await self._plan_store.async_save(plan)
        _LOGGER.info(
            "Budget plan replaced by spreadsheet import: %d positions, %d persons",
            len(plan.positions),
            len(plan.persons),
        )
        return report.to_dict()

    async def async_set_cost_position(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update a single cost position."""
        plan = await self._plan_store.async_load()
        position = CostPosition.from_dict(data)
        if not position.name:
            raise ValueError("A cost position needs a name")
        plan.upsert_position(position)
        await self._plan_store.async_save(plan)
        return position.to_dict()

    async def async_delete_cost_position(self, position_id: str) -> bool:
        """Delete a cost position by id."""
        plan = await self._plan_store.async_load()
        removed = plan.remove_position(position_id)
        if removed:
            await self._plan_store.async_save(plan)
        return removed

    async def async_set_income(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update one person's income entry."""
        from ..budget_plan import IncomeEntry

        plan = await self._plan_store.async_load()
        entry = IncomeEntry.from_dict(data)
        if not entry.person:
            raise ValueError("An income entry needs a person")
        plan.set_income(entry)
        await self._plan_store.async_save(plan)
        return entry.to_dict()

    def get_budget_plan_view(
        self, month: int | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """Full plan snapshot for the given month — pure cache read.

        This is the API shape behind the ledger, income and split cards. It
        mirrors the three spreadsheet sheets: income breakdown, cost ledger,
        and the resulting split.
        """
        now = dt_util.now()
        target_month = month or now.month
        target_year = year or now.year
        plan = self.budget_plan

        split_mode, remainder_mode, custom_ratios = self._split_options()
        model, shared_costs = model_from_plan(
            plan,
            target_month,
            target_year,
            split_mode=split_mode,
            remainder_mode=remainder_mode,
            custom_ratios=custom_ratios,
        )
        results = model.calculate_split(shared_costs)

        return {
            "month": target_month,
            "year": target_year,
            "source": plan.source,
            "is_empty": plan.is_empty(),
            "persons": plan.persons,
            "income": [
                {
                    "person": person,
                    "deposit": plan.income[person].deposit if person in plan.income else 0.0,
                    "insurance_mandatory": (
                        plan.income[person].insurance_mandatory if person in plan.income else 0.0
                    ),
                    "tax_adjustment": (
                        plan.income[person].tax_adjustment if person in plan.income else 0.0
                    ),
                    "net": plan.income_net(person),
                    "share": round(plan.income_rel(person) * 100, 2),
                }
                for person in plan.persons
            ],
            "income_net_total": plan.income_net_total(),
            "positions": [
                {
                    **position.to_dict(),
                    "planned_amount": position.planned_amount,
                    "effective_amount": position.effective_amount(target_month, target_year),
                    "is_active": position.is_active(target_month, target_year),
                }
                for position in plan.positions
            ],
            "costs": {
                "shared": plan.cost_shared(target_month, target_year),
                "individual": {
                    person: plan.cost_individual(person, target_month, target_year)
                    for person in plan.persons
                },
                "grand_total": plan.cost_grand_total(target_month, target_year),
                "shared_fixed": plan.fixed_total(target_month, target_year, OWNER_SHARED),
                "shared_buffer": plan.buffer_total(target_month, target_year, OWNER_SHARED),
                "by_category": plan.category_totals(target_month, target_year),
            },
            "split": {
                "model": split_mode,
                "members": [
                    {
                        "person": r.person,
                        "net_income": r.net_income,
                        "income_share": round(r.income_ratio * 100, 2),
                        "shared_costs_share": r.shared_costs_share,
                        "remainder_share": r.remainder_share,
                        "individual_costs": r.individual_costs,
                        "spielgeld": r.spielgeld,
                    }
                    for r in results
                ],
                "spielgeld_total": round(sum(r.spielgeld for r in results), 2),
            },
        }

    def get_transfer_plan(
        self, month: int | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """The monthly transfer choreography — pure cache read.

        Reproduces the spreadsheet's account-by-account transfer ledger and
        reports whether every pass-through account nets to zero.
        """
        now = dt_util.now()
        target_month = month or now.month
        target_year = year or now.year
        plan = self.budget_plan

        split_mode, remainder_mode, custom_ratios = self._split_options()
        model, shared_costs = model_from_plan(
            plan,
            target_month,
            target_year,
            split_mode=split_mode,
            remainder_mode=remainder_mode,
            custom_ratios=custom_ratios,
        )
        results = model.calculate_split(shared_costs)

        return build_transfer_plan(
            plan,
            self._accounts,
            target_month,
            target_year,
            split_results=results,
        ).to_dict()

    def get_plan_vs_actual(
        self, month: int | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """Compare planned positions against what the bank actually booked.

        Matching happens on two levels because neither alone is reliable:

        - **per category**, which always adds up but is coarse
        - **per position**, by matching the distinctive words of a position
          name against the transaction text; unmatched positions are reported
          as such rather than silently showing 0

        Amounts are normalised to the plan's sign convention (expense
        positive), so plan and actual are directly comparable.
        """
        from ..budget_plan import actual_amount_to_plan_sign

        now = dt_util.now()
        target_month = month or now.month
        target_year = year or now.year
        plan = self.budget_plan

        booked = [
            txn
            for txn in get_effective_transactions(self._transactions)
            if self._is_in_month(txn, target_month, target_year)
            and txn.get("_status") == "booked"
        ]

        actual_by_category: dict[str, float] = {}
        for txn in booked:
            amount = actual_amount_to_plan_sign(
                float(txn.get("transactionAmount", {}).get("amount", 0) or 0)
            )
            if amount <= 0:
                continue  # income, not a cost
            category = txn.get("category", "other")
            actual_by_category[category] = round(actual_by_category.get(category, 0.0) + amount, 2)

        planned_by_category = plan.category_totals(target_month, target_year)

        positions: list[dict[str, Any]] = []
        for position in plan.active_positions(target_month, target_year):
            matched = self._match_transactions(position, booked)
            actual = round(
                sum(
                    actual_amount_to_plan_sign(
                        float(t.get("transactionAmount", {}).get("amount", 0) or 0)
                    )
                    for t in matched
                ),
                2,
            )
            planned = position.effective_amount(target_month, target_year)
            positions.append(
                {
                    "id": position.id,
                    "name": position.name,
                    "owner": position.owner,
                    "category": position.category,
                    "planned": planned,
                    "actual": actual if matched else None,
                    "delta": round(actual - planned, 2) if matched else None,
                    "match_count": len(matched),
                }
            )

        categories = sorted(set(planned_by_category) | set(actual_by_category))
        return {
            "month": target_month,
            "year": target_year,
            "has_actuals": bool(booked),
            "categories": [
                {
                    "category": category,
                    "planned": planned_by_category.get(category, 0.0),
                    "actual": actual_by_category.get(category, 0.0),
                    "delta": round(
                        actual_by_category.get(category, 0.0)
                        - planned_by_category.get(category, 0.0),
                        2,
                    ),
                }
                for category in categories
            ],
            "positions": positions,
            "unmatched_positions": sum(1 for p in positions if p["actual"] is None),
        }

    async def async_get_benchmarks(
        self, month: int | None = None, year: int | None = None
    ) -> dict[str, Any]:
        """Compare our own ratios against German national averages.

        The spreadsheet compared four hand-maintained figures against values
        copied out of Destatis/Statista once. Here the "ours" side is computed
        from the plan and the reference side comes from
        :class:`~.benchmark.BenchmarkProvider`, whose baseline is versioned with
        the integration — so the comparison stays current without retyping.

        Percentage metrics are expressed as a share of pooled net income, which
        is the basis the spreadsheet used. Absolute metrics (EUR) are compared
        directly. Metrics whose numerator is zero are omitted rather than shown
        as "0% — better than average".
        """
        from ..benchmark import BenchmarkProvider

        if self._benchmark_provider is None:
            provider = BenchmarkProvider(self._hass)
            await provider.async_initialize()
            self._benchmark_provider = provider
        provider = self._benchmark_provider

        now = dt_util.now()
        target_month = month or now.month
        target_year = year or now.year
        plan = self.budget_plan
        income = plan.income_net_total()
        by_category = plan.category_totals(target_month, target_year)

        comparisons: list[dict[str, Any]] = []
        for metric_category, source_categories in BENCHMARK_METRIC_SOURCES.items():
            numerator = round(sum(by_category.get(c, 0.0) for c in source_categories), 2)
            if numerator <= 0:
                continue
            benchmark = provider.get_benchmark_for_category(metric_category)
            if not benchmark:
                continue
            if benchmark.get("unit") == "%":
                if income <= 0:
                    continue
                our_value = round(numerator / income * 100, 2)
            else:
                our_value = numerator
            result = provider.compare(metric_category, our_value)
            if result:
                result["our_amount"] = numerator
                result["source_categories"] = source_categories
                comparisons.append(result)

        # Consumption metrics cannot be derived from banking data — the utility
        # statement is the only source. Kept as an explicit option so the
        # spreadsheet's water comparison survives the migration instead of
        # being silently dropped.
        water_ratio = self._entry.options.get(OPT_WATER_RATIO)
        if water_ratio:
            try:
                value = float(water_ratio)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                comparisons.append(
                    {
                        "label": "Kaltwasser",
                        "category": "water",
                        "user_value": value,
                        "benchmark_value": DEFAULT_WATER_BENCHMARK,
                        "difference": round(value - DEFAULT_WATER_BENCHMARK, 2),
                        "better": value < DEFAULT_WATER_BENCHMARK,
                        "unit": "x Ø",
                        "source": "Nebenkostenabrechnung (manuell gepflegt)",
                        "survey_year": target_year,
                        "fetch_date": "manual",
                        "text": (
                            f"Kaltwasser: {value:.2f}x "
                            f"(DE Ø {DEFAULT_WATER_BENCHMARK:.2f}x, Nebenkostenabrechnung)"
                        ),
                        "manual": True,
                    }
                )

        return {
            "month": target_month,
            "year": target_year,
            "income_net_total": income,
            "comparisons": comparisons,
            "has_plan": not plan.is_empty(),
        }

    @staticmethod
    def _match_transactions(
        position: Any, transactions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find the transactions that plausibly belong to a cost position.

        Uses the distinctive words of the position name (4+ characters, so
        "DKB Zinsen" matches on "zinsen" rather than on the ubiquitous bank
        name). A position with no distinctive word matches nothing, which is
        reported honestly instead of guessed.
        """
        tokens = [word for word in re.findall(r"[a-zäöüß]{4,}", position.name.lower())]
        if not tokens:
            return []
        matches = []
        for txn in transactions:
            haystack = " ".join(
                str(part).lower()
                for part in (
                    txn.get("remittanceInformationUnstructured", ""),
                    (txn.get("creditorName") or ""),
                    (txn.get("debtorName") or ""),
                )
            )
            if any(token in haystack for token in tokens):
                matches.append(txn)
        return matches

    # ------------------------------------------------------------------
    # Transfer chain management
    # ------------------------------------------------------------------

    async def async_confirm_transfer_chain(self, chain_id: str, confirmed: bool) -> None:
        """Confirm or reject a detected transfer chain.

        Args:
            chain_id: The chain UUID to confirm/reject
            confirmed: True = user agrees it's a chain, False = reject
        """
        self._transfer_overrides[chain_id] = confirmed
        await self._transfer_override_store.async_save(self._transfer_overrides)
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

            amount = float(txn.get("transactionAmount", {}).get("amount", 0))
            chains[chain_id]["transactions"].append(
                {
                    "transactionId": txn.get("transactionId", ""),
                    "role": txn.get("_transfer_role", ""),
                    "account_name": txn.get("_account_name", ""),
                    "amount": amount,
                    "date": txn.get("bookingDate", ""),
                    "creditor": txn.get("creditorName", ""),
                    "description": txn.get("remittanceInformationUnstructured", ""),
                }
            )

        return list(chains.values())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_household(
        self,
        monthly_txns: list[dict[str, Any]],
        total_expenses: float,
        month: int | None = None,
        year: int | None = None,
    ) -> dict[str, Any] | None:
        """Build household split data for the monthly summary.

        Prefers the budget PLAN when one exists: the plan states each person's
        income and each position's owner explicitly, which the transaction
        stream cannot. Deriving ownership from "which account was debited"
        mis-assigns every position whose payment account differs from its owner
        — a shared subscription billed onward, or one person's contract paid
        from the joint account.

        Falls back to the transaction-derived estimate only when no plan has
        been imported yet, so a fresh install still shows something.
        """
        plan = self.budget_plan
        if not plan.is_empty() and plan.persons:
            now = dt_util.now()
            target_month = month or now.month
            target_year = year or now.year
            split_mode, remainder_mode, custom_ratios = self._split_options()
            model, shared_costs = model_from_plan(
                plan,
                target_month,
                target_year,
                split_mode=split_mode,
                remainder_mode=remainder_mode,
                custom_ratios=custom_ratios,
            )
            results = model.calculate_split(shared_costs)
            return {
                "members": [
                    {
                        "person": r.person,
                        "gross_income": round(r.gross_income, 2),
                        "net_income": round(r.net_income, 2),
                        "income_ratio": round(r.income_ratio * 100, 1),
                        "shared_costs_share": round(r.shared_costs_share, 2),
                        "remainder_share": round(r.remainder_share, 2),
                        "individual_costs": round(r.individual_costs, 2),
                        "spielgeld": round(r.spielgeld, 2),
                        "bonus_amount": round(r.bonus_amount, 2),
                    }
                    for r in results
                ],
                "split_model": split_mode,
                "remainder_mode": remainder_mode,
                "total_shared_costs": round(shared_costs, 2),
                "spielgeld_total": round(sum(r.spielgeld for r in results), 2),
                "source": "plan",
            }

        return self._household_from_transactions(monthly_txns)

    def _household_from_transactions(
        self,
        monthly_txns: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Estimate the household split from transactions alone.

        Used only before a budget plan exists. Ownership is inferred from the
        debited account, which is an approximation — the plan replaces it.
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
            amount = float(txn.get("transactionAmount", {}).get("amount", 0))
            acc_type = txn.get("_account_type", "personal")
            person = txn.get("_account_person", "")
            category = txn.get("category", "other")

            if acc_type == "shared":
                # Shared account — costs are split among all members
                if amount < 0:
                    shared_costs += abs(amount)
                    shared_cost_items.append(
                        {
                            "category": category,
                            "amount": amount,
                        }
                    )
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

        split_mode, remainder_mode, custom_ratios = self._split_options()

        model = HouseholdModel(
            members=members,
            split_mode=split_mode,
            remainder_mode=remainder_mode,
            custom_ratios=custom_ratios,
        )

        results = model.calculate_split(shared_costs, shared_cost_items or None)

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
            "spielgeld_total": round(sum(r.spielgeld for r in results), 2),
            "source": "transactions",
        }

    def _check_budget_limits(self, category_totals: dict[str, float]) -> None:
        """Check if any category exceeds its budget limit and fire events."""
        from ..events import fire_budget_exceeded

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
    def _is_in_month(txn: dict[str, Any], month: int, year: int) -> bool:
        """Check if a transaction belongs to the given month."""
        booking_date = txn.get("bookingDate", "")
        if not booking_date:
            return False
        try:
            dt = datetime.strptime(booking_date, "%Y-%m-%d")
            return dt.month == month and dt.year == year
        except ValueError:
            return False
