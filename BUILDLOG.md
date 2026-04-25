# Build Log

## 0.13.0 — 2026-04-25
Version: 0.13.0
Branch: claude/eager-nobel-e572f9
Changes:
- feat(security): MultiFernet credential storage with key rotation + v1→v2 migration (S2)
- feat(security): timing-safe OAuth state validation with one-time-use, 10min TTL, 32-entry cap, cross-store fallback (S4, F1, F3, F5)
- feat(security): unified setup-wizard rate-limit gate via async_make_setup_call + persistent fresh-setup gate (S3, F2, F4)
- feat(security): IBAN/account-id/EUR-amount log sanitizer; raw API bodies no longer hit ERROR-level logs (S1)
- feat(security): pre-commit secret-scan hook (.pre-commit-config.yaml + scripts/check_no_banking_data.py) (R11)
- feat(banking): PyJWT[crypto] migration with iss=application_id, aud=api.tilisy.com, per-request jti (A4)
- feat(banking): shared aiohttp ClientSession via async_get_clientsession (A5)
- feat(banking): Retry-After header honored on 429 + PSU headers for online-mode (D5, D6)
- feat(api): /refresh_status exposes rate_limit_per_day + cache_is_stale + cache_age_seconds (D7, D9)
- fix(security): /refresh and toggle_demo now require admin (R9, R14)
- fix(security): partial-refresh per-account cache prevents data loss on partial bank failure (R5, F10)
- fix(security): corrupt .storage recovery via try/except + repair-issue (R8)
- fix(security): static file serving non-blocking via async_add_executor_job + LRU cache (R12)
- fix(security): repair-issue payloads scrubbed of exception strings (R10)
- fix(security): _reconstruct_pem PKCS1/PKCS8 detection corrected (C9)
- refactor(api): split api.py (1258 LOC) into api/ package (setup, refresh, data, static, demo, _helpers) (A1)
- refactor(manager): split manager.py (1151 LOC) into mixin modules (RefreshMixin, PersistenceMixin) (A2)
- refactor(frontend): persistent component tree replaces full-rebuild on every data update (A3)
- refactor(frontend): SHARED_CSS adoption + CAT_COLORS/LABELS consolidation in fd-shared-styles (F2, F3)
- refactor(frontend): all hardcoded color literals replaced with CSS tokens (F4)
- refactor(frontend): unified disconnectedCallback for memory cleanup (F5)
- refactor(frontend): shared escHtml helper (F8)
- feat(a11y): setup-wizard modal with role/aria-modal/focus-trap/ESC (U1)
- feat(a11y): institution list with full keyboard navigation (role/listbox/option) (U2)
- feat(a11y): donut chart aria-label + visually-hidden table fallback (U3)
- feat(a11y): toast aria-live based on severity (assertive for warn/error) (U4)
- feat(a11y): cost-distribution role/group + per-segment aria-label (U5)
- feat(frontend): i18n with locale JSON files + hass.language detection + tSync helper (U6, G1-G4)
- feat(frontend): skeleton/loading states across all card components (U8)
- feat(frontend): + Bank entry-point opens wizard from header (U10)
- feat(frontend): countdown for setup-wizard auth-polling step (D8)
- feat(setup): persistent notification after config_flow completion (U11)
- fix(frontend): responsive breakpoint at 980px for category section (U9)
- refactor(frontend): month label as static span (U7)
- chore: remove deprecated GoCardless client (F1)
- refactor(api): manager.async_set_accounts encapsulation (F6)
- perf(security): reuse audit-log Store instance (F7)
- chore(manifest): iot_class cloud_polling → cloud_push (D2)
- docs: align repairs.py role + sync services.yaml (D3, D4)
- docs: precise update_interval docstring on coordinator (D10)
- fix(repairs): mark auth+storage repairs as is_persistent (D11)
- fix: dt_util.now() instead of datetime.now() throughout (D12)
- test: scaffold tests/ + pyproject.toml + requirements_test.txt (T1, T6)
- test: cache-vs-live-boundary contract test as guardian (T2)
- test: JWT/Fernet edge-case coverage (T3, 21 tests)
- test: parametrized categorizer rule coverage (T4, 79 tests)
- test: transfer-detector cascade + override + confidence (T5, 27 tests)
- chore(ci): pytest with coverage in validate workflow (T7)
- docs: sync CLAUDE.md phases with actual code state (D1)
- docs: audit-synthesis concept page (Phase 2 artifact)
- Result: 165/165 tests pass; ruff 0 errors; coverage 31% (categorizer 96%, transfer_detector 91%, const 100%); payload synced

## [unreleased] Wave G2 — Phase-4 RedTeam Security Fixes (F1–F5, F10)
Version: 0.12.1 (no bump)
Branch: claude/eager-nobel-e572f9
Changes:
- fix(security): F1 — OAuth state cross-scope race eliminated; _register_oauth_state() writes to BOTH manager._oauth_states AND hass.data[DOMAIN]["_oauth_states"]; _validate_oauth_state() checks both stores and removes on match from both; setup.py uses _register_oauth_state() exclusively
- fix(security): F2 — fresh-setup rate-limit gate added; _set_rate_limited() mirrors reset timestamp to hass.data["_global_rate_limit_until"]; async_initialize() mirrors on storage load; _get_setup_client() checks hass.data global key before creating client
- fix(security): F3 — UTC-aware OAuth state timestamps throughout; assume-UTC logic for naive timestamps in async_validate_oauth_state() and _parse_utc_dt() helper in api/_helpers.py; TypeError on naive/aware subtraction impossible
- fix(security): F4 — async_make_setup_call() wired into setup wizard; gains optional client= param for setup-credential bypass; institutions and authorize endpoints route through manager gate when available
- chore(security): F5 — _oauth_states dict bounded at 32 entries; oldest 16 evicted on cap; hass.data fallback also enforces 32-entry cap in _register_oauth_state()
- fix(banking): F10 — __unknown__ tx bucket dropped after first successful live refresh (accounts_hit > 0); migration-era legacy data no longer pollutes flat transaction list
- test: 2 new tests in test_oauth_state.py: test_timezone_mismatch_safe (F3 guard), test_oauth_states_dict_bounded (F5 eviction)
- Result: 165/165 tests pass; all changed files pass py_compile

## [unreleased] Wave F — Backend Test-Detail (T3, T4, T5, T6, T7)
Version: 0.12.1 (no bump)
Branch: claude/eager-nobel-e572f9
Changes:
- test(security): T3 — expand JWT/Fernet edge-cases; test_jwt.py gains 4 tests (wrong-algo rejection, expired-token rejection, clock-skew iat guard, cross-key signature mismatch); test_credential_manager.py gains 4 tests (middle-key decrypt across 3-key rotation, corrupt-key migration error, session-timeout flag reset, uninitialized-manager RuntimeError); total 21 tests
- test(categorizer): T4 — 79 parametrized tests covering all 9 rule categories (housing, food, transport, insurance, subscriptions, loans, utilities, income, transfers), positive-amount income fallback, custom-rule injection, case-insensitivity, multi-field (remittance array, creditorName) matching; also fixes shallow-copy bug in get_rules() — inner lists were shared, mutations polluted instance
- test(transfer-detector): T5 — 27 tests: simple 2-account transfer (source/destination assignment, confidence >= 0.60), 3-stage cascade chain (DKB -> PayPal -> HelloFresh, intermediate leg detection), manual override confirm/reject, false-positive guard (same amount != transfer, tolerance boundary, date window, pending status), confidence tiers, refund detection (storno keyword, timing direction), enrich_transactions field population
- chore(lint): T6 — ruff check passes with 0 errors; ruff format applied to 28 files; fixes: F401 unused imports, F841 unused variables, RUF005 list spread, RUF046 int(round()) -> round(), PLR1714 membership test, RUF002/003 ambiguous Unicode, RUF022 __all__ with noqa, E402 import order, RUF012 mutable attrs; per-file-ignores in pyproject.toml for structural PLR violations (too-many-branches/statements in complex handlers)
- chore(ci): T7 — pytest step adds --cov + --cov-report=xml/term-missing; coverage.xml uploaded as artifact; requirements_test.txt gains PyJWT>=2.8, cryptography>=42.0, aiohttp>=3.9
- Result: 163/163 tests pass; coverage 31% total (const 100%, categorizer 96%, transfer_detector 91%); ruff 0 errors

## [unreleased] Wave F — Frontend Refactors (A3, F2, F3, F4, F5, F8)
Branch: claude/eager-nobel-e572f9
Changes:
- refactor(frontend): F8 — escHtml() (regex-based, no DOM round-trip) exported from fd-shared-styles.js; window._fd object exposes all shared constants (CAT_COLORS, CAT_LABELS, MEMBER_COLORS, MONTH_NAMES, SHARED_CSS, escHtml, esc, eur, pct) for classic-script consumers
- refactor(frontend): F2 — local TX_CAT_LABELS, REC_CAT_LABELS, DIST_CAT_COLORS/LABELS, CAT_COLORS/LABELS, MONTH_NAMES duplicates removed from fd-transactions-log, fd-recurring-list, fd-cost-distribution, fd-category-section, fd-categorize, fd-header; all read from window._fd
- refactor(frontend): F3 — SHARED_CSS adopted via <style>${SHARED_CSS}${LOCAL_CSS}</style> in fd-stats-row, fd-stat-card, fd-household-section, fd-person-card, fd-donut-chart, fd-category-section, fd-cost-distribution, fd-recurring-list, fd-transactions-log, fd-header; removes ~120 lines of duplicated :host token definitions
- refactor(frontend): F4 — hard-coded #e74c3c, #0a0a0f, #f39c12, #12121a literals replaced with var(--dg/--error-color), var(--bg/--primary-background-color), var(--warning-color) tokens in fd-budget-config, fd-setup-wizard, finance-dashboard-panel, fd-header; fd-categorize catColors now reads window._fd.CAT_COLORS
- refactor(frontend): F5 — disconnectedCallback added to finance-status-chip (clears _successTimer); stub disconnectedCallbacks in fd-stat-card, fd-household-section, fd-person-card, fd-donut-chart (no active cleanup, guards future additions)
- refactor(frontend): A3 — FinanceDashboardPanel._onData() no longer rebuilds DOM on every fd-data-updated event; _ensureComponents() creates 6 child components once; _onData() pushes .data to persistent refs; loading/error/onboarding states use #overlay div toggled via .hidden class; onboarding listener rebind guarded by overlayState check
- Result: 49/49 tests pass; all 17 frontend JS files pass node --check

## [unreleased] Wave E — Backend Refactor + Polish (F1, F6, F7, D1-D12)
Branch: claude/eager-nobel-e572f9
Changes:
- chore: F1 — remove `_gocardless_client_deprecated.py`; no callers remained (GOCARDLESS_BASE_URL was only referenced internally in the deleted file); no companion-payload copy existed
- refactor(api): F6 — add `manager.async_set_accounts(accounts: list)` with isinstance validation + config-entry persistence; replace direct `manager._accounts = existing` in `api/setup.py` with the new method
- perf(security): F7 — CredentialManager stores single `_audit_store` instance in `__init__`; `_audit_log()` and `async_get_audit_log()` reuse it instead of creating `Store()` on every call; imports `AUDIT_MAX_ENTRIES` and `STORAGE_KEY_AUDIT` at module top; test helper updated to include `_audit_store = FakeStore()` and `test_audit_log_on_rotate` patching strategy updated for the new design
- chore(manifest): D2 — `iot_class` `cloud_polling` → `cloud_push` (data only enters on user-triggered push, not background poll)
- docs: D3 — `repairs.py` docstring explains intentional thin re-export design; issue creation lives in manager mixins which have execution context
- docs: D4 — CLAUDE.md service count corrected from 7 to 8 (`toggle_demo` was missing); all 8 services verified present in `services.yaml` and `const.py`
- feat(banking): D5 — `RateLimitExceeded` carries optional `retry_after_seconds: int | None`; `_async_request` parses `Retry-After` header on 429; `_set_rate_limited(retry_after_dt=None)` uses `min(midnight, retry_after_dt)` reset; both 429 catch-sites in `_do_refresh` and `_async_refresh_balances_live` forward the parsed value
- feat(banking): D6 — `_async_request` accepts optional `psu_ip`/`psu_ua` params; `async_get_transactions` and `async_get_balances` pass `psu_ua=self._PSU_UA` (canonical `HomeAssistant-Finance-Dashboard/<version>` string, class-level constant); `async_refresh_transactions(psu_ip=None)` accepts and forwards PSU IP all the way to client calls; `api/refresh.py` passes `request.remote` as `psu_ip`
- fix(repairs): D11 — `_raise_credentials_issue` sets `is_persistent=True` (auth issues survive restart); `_raise_storage_corrupt_issue` sets `is_persistent=True` (corrupt file requires manual intervention)
- fix: D12 — replace all `datetime.now()` in `manager/_refresh.py` and rate-limit comparison in `manager/__init__.py` with `dt_util.now()` (tz-aware, consistent with HA conventions); `from homeassistant.util import dt as dt_util` added to both files
- feat(api): D7 — `get_refresh_status()` includes `rate_limit_per_day: ENABLEBANKING_RATE_LIMIT_DAILY` (currently 4); frontend can render the cap label dynamically without hardcoding
- feat(api): D9 — `get_refresh_status()` includes `cache_is_stale: bool` (True when `cache_age_seconds > 6h`); `_CACHE_STALE_THRESHOLD_SECONDS = 6 * 3600` class constant
- docs: D10 — `FinanceDashboardCoordinator.__init__` docstring rewritten to precisely explain cache-only contract, `update_interval=None` rationale, and 4/day rate-limit constraint
- docs: D1 — CLAUDE.md architecture block updated to show `manager/` and `api/` as packages with sub-files; Phase 1 all checkboxed; Phase 2 items marked [x]/[ ] per actual code state; Phase 3 marked frozen; service count 8; next version hint 0.13.0
- Result: 49/49 tests pass

## [unreleased] Wave D — Architecture Refactors (A1, A2, A4, A5)
Branch: claude/eager-nobel-e572f9
Changes:
- feat(security): A4 — replace manual base64/cryptography JWT with PyJWT[crypto]>=2.8.0; iss=application_id, aud=api.tilisy.com per current Enable Banking docs; adds unique jti per request (replay protection); adds tests/test_jwt.py (8 cases: decode, iss, aud, TTL, jti presence, jti uniqueness, kid header, RS256 algorithm)
- refactor(banking): A5 — EnableBankingClient accepts optional session parameter; HA-managed session injected via async_get_clientsession in both manager.py and api/_helpers.py; private session lazily created only when none injected; async_close() cleans up private session only (owner=True); eliminates per-request TCP handshake overhead
- refactor(api): A1 — split 1373-line api.py into api/ package: _helpers.py (shared utils), setup.py (7 setup-wizard views + OAuth callback), refresh.py (RefreshTriggerView + RefreshStatusView), data.py (BalancesView, TransactionsView, SummaryView, TransferChainsView), static.py (LRU file serving), demo.py (DemoToggleView + DemoDataView), __init__.py (async_register_api + full re-exports); from .api import async_register_api still works; test patch target updated to api.refresh._get_manager
- refactor(manager): A2 — split 1321-line manager.py into manager/ package with two mixins: RefreshMixin (_refresh.py: async_refresh_transactions, _do_refresh, _async_refresh_balances_live, _set_rate_limited, OAuth state, setup proxy, client factory, credential issue helpers), PersistenceMixin (_persistence.py: _persist_transactions, _async_load_transfer_overrides, storage corrupt issue); FinanceDashboardManager inherits both (MRO: Manager → RefreshMixin → PersistenceMixin); from .manager import FinanceDashboardManager unchanged

## Wave A — Test Infrastructure — 2026-04-25
Version: 0.12.1 (no bump)
Branch: claude/eager-nobel-e572f9
Changes:
- test(infra): scaffold tests/ directory — __init__.py, conftest.py with Windows-compatible event loop policy fix (pytest-homeassistant-custom-component uses HassEventLoopPolicy + socket guard that conflicts with Windows ProactorEventLoop socketpair; fixed via event_loop_policy fixture wrapping new_event_loop with socket enable/disable)
- test(infra): pyproject.toml with pytest asyncio_mode=auto, ruff lint config (E/F/W/I/B/UP/PLR/RUF, line-length=100, py312), mypy strict for custom_components/
- test(infra): requirements_test.txt (pytest>=8.0, pytest-asyncio, pytest-cov, pytest-homeassistant-custom-component, ruff, mypy, ha-customapps>=0.3.0)
- test(smoke): test_smoke.py — import smoke test, DOMAIN/VERSION/SERVICE_* constants validation
- test(coordinator): test_coordinator_contract.py — GUARDIAN tests asserting coordinator._async_update_data() and async_load_cached() never call any EnableBankingClient live method (async_get_transactions, async_get_balances, async_get_account_details, async_get_institutions, async_create_auth, async_create_session, async_test_connection); update_interval=None assertion
- ci: add pytest job to validate.yml (parallel to validate, Python 3.12, pip install requirements_test.txt, pytest tests/ -v)
- Result: 7/7 tests pass locally

## [unreleased] Wave C — Security Audit (R5, R8, R9, R10, R11, R12, R14, C9)
Branch: claude/eager-nobel-e572f9
Changes:
- fix(core): R5 — per-account transaction cache (`_tx_by_account: dict[str, list]`); partial refresh failure leaves intact account untouched, stale data preserved; storage migrates old flat-list format on load; flat `_transactions` rebuilt deterministically from dict
- fix(core): R8 — wrap `async_load()` in `async_initialize` with try/except (JSONDecodeError, ValueError, OSError); on decode error log sanitized ERROR + full stack at DEBUG only; raise `storage_corrupt` Repair issue with error_class only (no str(exc) leakage)
- fix(api): R9 — `FinanceDashboardRefreshTriggerView.post` gated by `user.is_admin`; non-admin returns 403 admin_required before any API call
- fix(services): R14 — `handle_toggle_demo` service checks `call.context.user_id`, fetches user via `hass.auth.async_get_user`, raises `HomeAssistantError("admin_required")` for non-admin; backup/restore real transaction data around demo enable/disable
- fix(enablebanking): C9 — `_reconstruct_pem` detects PKCS1/PKCS8 marker BEFORE stripping headers; is_pkcs1 flag set on raw string, not residue
- fix(api): R12 — `FinanceDashboardStaticView` uses `hass.async_add_executor_job(file_path.read_bytes)` instead of synchronous read; mtime-aware LRU cache (16 entries) for hot files
- fix(core): R10 — Repair issues never include `str(exc)` or tracebacks in `translation_placeholders`; only `error_class = type(exc).__name__`; PEM-load failure logs class-only at ERROR, full stack at DEBUG; `storage_corrupt` and `credentials_invalid_pem` issues use translation-key-only pattern; new `storage_corrupt` translation key added to en.json + de.json
- feat(precommit): R11 — `.pre-commit-config.yaml` with standard hooks + local `no-banking-data` hook; `scripts/check_no_banking_data.py` blocks real DE IBANs / long account numbers / EUR amounts; allowlists tests/ path and DE89370400440532013000 (public test IBAN); exits 0 for clean files, 1 for violations
- test: R5 — `tests/test_partial_refresh.py` (3 cases: partial success, full success, migration)
- test: R8 — `tests/test_storage_recovery.py` (2 cases: corrupt → starts empty + repair, valid → loads normally)
- test: R9 — `tests/test_admin_gating.py` (3 cases: non-admin 403, no-user 403, admin passes gate)
- test: C9 — `tests/test_pem_reconstruct.py` (5 cases: PKCS8 detection, PKCS1 detection, escaped newlines both formats, 64-char chunking)
- test: R11 — `tests/test_banking_data_hook.py` (6 cases: clean, real IBAN blocked, test IBAN allowed, path allowlist, main exit codes)

## [unreleased] Wave B — Security-Critical (S1-S4)
Branch: security/wave-b-s1-s4
Changes:
- fix(security): sanitize banking responses in error logs (S1) — _LOGGER.error no longer emits raw response body; IBANs, 16-19 digit account IDs, and EUR amounts are masked via _sanitize_log() before reaching DEBUG-level log; exception messages also sanitized
- feat(security): MultiFernet with key rotation + migration (S2) — credential_manager.py now stores keys as a versioned list (schema v2); async_rotate_key() prepends a new primary key, retains max 3; legacy v1 "encryption_key" string auto-migrated on init; audit entry "key_rotated" on every rotation
- fix(security): route setup-wizard live calls through rate-limit gate (S3) — all 4 direct EnableBankingClient() instantiations in setup-wizard endpoints replaced with _get_setup_client(hass); checks manager.rate_limited_until before issuing any live call; async_make_setup_call() added to FinanceDashboardManager as the canonical gate
- fix(security): validate OAuth state with timing-safe compare (S4) — async_register_oauth_state() / async_validate_oauth_state() added to FinanceDashboardManager using secrets.compare_digest() with 10min TTL and one-time-use; OAuth callback validates state before processing authorization code

## 0.12.1 — 2026-04-24
Version: 0.12.1
Branch: claude/charming-cohen-05563c
PR: (pending)
Changes:
- fix(core): preserve partial balances when Enable Banking rate-limit hits mid-fetch — accounts that succeeded before the 429 no longer lose their fresh value, merged into the existing cache instead of being discarded
- fix(core): reconstruct `_previous_balances` baseline from cached balances on `async_initialize` so the first refresh after every HA restart no longer fires spurious `fd_balance_changed` events for every account
- fix(core): balance-refresh end path now merges into existing cache instead of replacing — accounts that errored this round keep their last known value
- fix(setup): deferred reload after setup-wizard completion now triggers a real live refresh via `manager.async_refresh_transactions()` instead of a cache-only `coordinator.async_refresh()` — entities populate with actual bank data immediately, no more "unavailable" state until the user clicks "Aktualisieren"
- fix(coordinator): `async_load_cached` failure path publishes an empty snapshot so entities stay `unknown` (recoverable) instead of `unavailable` (stuck) when cache read errors
- fix(core): `refresh_accounts` service call now pushes the updated state through the coordinator so dashboards reflect the new account metadata immediately, matching `refresh_transactions` behavior
- fix(core): always load the cached snapshot into the coordinator regardless of `configured`/`demo_mode` state so half-configured entries don't leave entities permanently unavailable
- fix(number): `BudgetLimitNumber` now inherits from `RestoreEntity` — user-set budget limits survive HA restarts instead of silently resetting to 0
- fix(select): `SplitModelSelect` and `RemainderModeSelect` listen for config-entry updates and re-sync their current option when the options flow changes the stored key — no more stale display after external option changes
- fix(api): `/demo/toggle` returns HTTP 503 when no manager is configured instead of toggling a dead `hass.data` flag that nothing reads
- refactor(enablebanking_client): drop unused `ENABLEBANKING_RATE_LIMIT_DAILY` import, move `RateLimitExceeded` below all imports for a clean module layout
- docs(__init__): replace stale "GoCardless/Nordigen" docstring with Enable Banking PSD2 reference, document the 4/day/ASPSP rate-limit gate
- docs(addon): replace stale "GoCardless Open Banking API" description in `finance_dashboard_companion/config.yaml` with Enable Banking PSD2

## 0.12.0 — 2026-04-23
Version: 0.12.0
Branch: claude/gallant-mestorf-fcf6f0
PR: (pending)
Changes:
- feat(frontend): new `fd-transactions-log` card shows imported (cached) transactions after at least one bank is linked and a refresh ran — date, counterparty, description, category badge, account, coloured amount, "vorgemerkt" flag for pending items; collapses to 25 rows with "Alle N anzeigen" toggle (cap 100 from the API)
- feat(frontend): `fd-data-provider` caches `/api/finance_dashboard/transactions` in-memory, refetches on user-triggered refresh and on first rebuild with linked accounts — entity-only state changes no longer trigger redundant fetches, and the endpoint is cache-read only (unbounded-safe, no Enable Banking call)
- refactor(panel): register `fd-transactions-log.js` in `LOVELACE_COMPONENTS`, append component after `fd-recurring-list` in the shell's component tree

## 0.11.1 — 2026-04-20
Version: 0.11.1
Branch: claude/fix-refresh-demo-race-0-11-1
PR: (pending)
Changes:
- fix(frontend): btn-demo now renders neutral/ghost by default — orange fill only when demo mode is active (btn-demo-active), preventing false "already in demo" appearance
- fix(frontend): refresh race eliminated — after POST /refresh, poll for entity state change (≤5s, 500ms ticks) before calling _rebuild(), avoiding stale hass.states read that returned accountCount=0 and flashed onboarding screen
- fix(frontend): _onHassChanged no longer advances _prevStateHash when _loading=true; instead sets _pendingRebuild=true so _rebuild retries immediately after the in-flight rebuild finishes, closing the concurrent-rebuild deadlock

## 0.11.0 — 2026-04-20
Version: 0.11.0
Branch: claude/bold-swirles-d0afe6
PR: (pending)
Changes:
- fix(core): separate cache-reads from live API fetches — `manager.async_get_balance()` now returns cached balances only (was hitting Enable Banking on every HTTP `/balances` call, burning the 4/day/ASPSP rate limit)
- feat(core): serialise user-triggered refreshes with `asyncio.Lock` to prevent double-click concurrent fetches
- feat(core): persist `rate_limited_until` and `last_refresh_stats` across HA restart so the 4/day counter is not lost on reboot
- feat(core): track structured refresh stats (outcome, accounts, transactions, new, duration_ms, errors) exposed via `manager.get_refresh_status()`
- feat(api): new `POST /api/finance_dashboard/refresh` endpoint — the single user-triggered live-fetch entry point, returns stats synchronously
- feat(api): new `GET /api/finance_dashboard/refresh_status` — cache-only polling endpoint, unbounded reads allowed
- feat(core): `refresh_transactions` service now uses `SupportsResponse.OPTIONAL` and returns stats so automations can react to the outcome
- feat(core): refresh_transactions refreshes balances in the same user-triggered round — one click, one cache update
- feat(frontend): refresh button now shows a result toast ("5 Konten, 243 Transaktionen, 2 neu in 3.1s" / rate-limit / partial / error)
- feat(frontend): header timestamp shows live cache age ("Zuletzt 14:23 · vor 2 Std") and updates every minute
- feat(frontend): rate-limit and loading states surfaced clearly next to the refresh button instead of silent "Aktualisieren" reverts
- fix(frontend): "Noch keine Daten" state now has explicit styling + hint to click Aktualisieren
- refactor(coordinator): remove staleness-based auto-refresh — coordinator is now a pure cache projection, live fetches only via dedicated endpoint
- docs(claude-md): replace stale GoCardless references with Enable Banking, document cache vs. live-fetch contract

## 0.10.1 — 2026-04-19
Version: 0.10.1
Branch: claude/pensive-rosalind-793ad9
PR: (pending)
Changes:
- fix(setup): propagate OAuth callback errors through /setup/status so the wizard surfaces them within 2s instead of timing out after 5min
- fix(setup): hard-fail /setup/authorize when callback URL is HTTP (Enable Banking requires pre-registered HTTPS redirect)
- fix(setup): trigger one coordinator refresh after deferred entry reload so entities populate immediately after bank link
- fix(core): raise Repairs issue on missing or invalid Enable Banking credentials, auto-clear on recovery
- fix(frontend): wizard polling stops on setup_error and shows the message instead of waiting for timeout
- fix(frontend): data provider subscribes to entity_registry_updated events so newly created sensors appear without race-prone 4s timer

## 0.10.0 — 2026-04-12
Version: 0.10.0
Branch: claude/sweet-nightingale
PR: (pending)
Changes:
- feat(frontend): add inline bank connection wizard as modal overlay (4-step flow: institution search, bank authorization with polling, account assignment, success)
- fix(frontend): replace fragile entity_id prefix matching with HA Entity Registry lookup — entities are now found by platform + unique_id regardless of HA-generated entity_ids
- feat(frontend): add "+ Konto" button in header to open wizard from anywhere
- refactor(frontend): replace onboarding "Einstellungen" link with inline "Bankkonto verbinden" button
- fix(frontend): add 4s delay before refreshRegistry() after setup complete to wait for HA config entry reload
- fix(frontend): add https scheme validation on auth URLs to prevent XSS via javascript: scheme
- fix(frontend): update institution filter to only re-render list container (prevents cursor jump)

## 0.9.2 — 2026-04-11
Version: 0.9.2
Branch: claude/sharp-shockley
PR: (pending)
Changes:
- refactor(core): remove automatic banking API calls on HA startup — coordinator now loads from cache only, no external calls until user clicks "Aktualisieren"
- refactor(core): remove _first_update force-refresh flag from coordinator — staleness check is sufficient
- refactor(frontend): remove automatic API fallback in _rebuild() — /summary endpoint only called on explicit user refresh, not on every entity change
- feat(frontend): add onboarding welcome screen with "Demo starten" CTA when no bank accounts connected
- feat(frontend): show "Noch keine Daten" timestamp fallback when no refresh has occurred
- feat(frontend): make Demo button more prominent with visible background fill
- fix(frontend): handle loading state in _onData to prevent clearing content during demo toggle

## 0.9.1 — 2026-04-07
Version: 0.9.1
Branch: claude/optimistic-merkle
PR: (pending)
Changes:
- fix(restart): add missing issue-level description to strings.json — Repairs card had no body text, rendering it invisible in some HA versions
- fix(restart): add is_persistent=True to ir.async_create_issue — prevents HA from discarding the issue during internal operations
- fix(restart): wrap synchronous file I/O (exists/read_text/unlink) in async_add_executor_job — HA 2024+ blocks or warns on sync I/O in event loop
- fix(repairs): return None for unknown issue_ids instead of generic RepairsFlow()
- chore: sync translations (en.json, de.json) with new issue description
- chore: sync addon payload

## 0.9.0 — 2026-04-05
Version: 0.9.0
Branch: claude/practical-fermi
PR: (pending)
Changes:
- feat(demo): full demo mode with realistic German banking data (3 accounts, ~35 transactions, household split, recurring patterns)
- feat(demo): toggle via UI button (admin-only), service call, or options flow — persists across HA restarts
- feat(core): manual-only API refresh — coordinator update_interval=None, data only updates on explicit user action
- fix(core): initial coordinator refresh now works on config entry reloads (not just first HA start)
- fix(core): shutdown no longer overwrites real transaction cache when demo mode is active
- fix(api): AttributeError in DemoToggleView coordinator lookup — null-safe access pattern
- fix(api): GoCardless reference replaced with Enable Banking in services.yaml
- fix(coordinator): removed dead COORDINATOR_UPDATE_INTERVAL constant and corrected all docstrings
- feat(frontend): demo toggle button with DEMO badge, aria-pressed accessibility, mobile breakpoint
- fix(frontend): rapid-click guard and loading state for demo API calls
- fix(frontend): demoMode flag propagated in all data events for consistent UI state

## 0.8.1 — 2026-04-02
Version: 0.8.1
Branch: claude/frosty-hoover, claude/competent-payne
PR: #59
Changes:
- fix(frontend): fd-data-provider never called _rebuild when no fd_ entities exist — dashboard stuck on "Lade Finanzdaten..." forever. Added _initialRebuildDone flag to ensure first rebuild always runs.
- fix(core): restart notification deleted by race condition — async_setup_entry unconditionally cleared restart_required issue before polling timer could detect marker. Now preserves issue when marker file exists and polls immediately on setup.
- fix(frontend): prevent infinite loading spinner when no fd_ entities exist — data provider now always triggers initial rebuild
- chore: add .playwright-mcp/ to .gitignore

## 0.8.0 — 2026-03-28
Version: 0.8.0
Branch: claude/compassionate-kowalevski
PR: #56
Changes:
- refactor(frontend): decompose monolithic panel into 10 web components (fd-data-provider, fd-header, fd-stats-row, fd-stat-card, fd-household-section, fd-person-card, fd-category-section, fd-donut-chart, fd-cost-distribution, fd-recurring-list)
- refactor(frontend): entity-first data strategy — fd-data-provider reads HA sensor/number/select entities, falls back to API for household+recurring
- refactor(frontend): panel shell reduced from 507 lines to ~120 lines
- fix(core): coordinator force-refreshes transactions on first cycle — prevents stale cache showing 0,00 EUR
- fix(core): account settings API now persists `person` field for household assignment
- fix(core): monthly summary sensor exposes fixed_costs, variable_costs, household, recurring attributes
- docs: ARCHITECTURE-FRONTEND.md added with component hierarchy, data flow, entity table, event system

## 0.7.8 — 2026-03-28
Version: 0.7.8
Branch: main (hotfix)
Changes:
- fix(core): graceful degradation for household model — exception no longer crashes coordinator
- fix(core): graceful degradation for recurring detection — failure yields empty list
- fix(core): graceful degradation for budget limit checks — log and skip on error
- fix(core): graceful degradation for event firing (balance + transaction) — never blocks data flow

## 0.7.7 — 2026-03-28
Version: 0.7.7
Branch: claude/zen-satoshi
PR: #55
Changes:
- feat(core): integrate HouseholdModel into manager — auto-builds members from account assignments, computes per-person Spielgeld splits
- feat(core): activate recurring payment detection on each transaction refresh
- feat(core): fire fd_transaction_new, fd_balance_changed, fd_budget_exceeded events
- feat(core): budget limit checking against Number entities per category
- feat(core): fixed vs variable cost computation in summary API
- feat(frontend): dashboard shows real bank balance from API (not income minus expenses)
- feat(frontend): person cards with Spielgeld, income ratio, shared costs share
- feat(frontend): shared Fixkosten bar with per-person distribution
- feat(frontend): recurring payments section with detected patterns
- feat(frontend): German category labels (Wohnen, Mobilität, etc.)
- feat(frontend): responsive layout for mobile viewports
- fix(frontend): XSS protection for user-provided names

## 0.7.6 — 2026-03-28
Version: 0.7.6
Branch: claude/stoic-wing
Changes:
- fix(core): add DataUpdateCoordinator — entities no longer call banking API directly
- fix(core): sensor update interval 10 min via coordinator (was ~30 s per entity → rate-limit exhaustion)
- fix(frontend): panel refresh on connectedCallback + 10-min auto-timer instead of every hass setter
- fix(frontend): Lovelace card throttles API calls to max once per 10 min (was every hass setter)
- feat(core): coordinator refreshes transactions only when cache is stale (>6 h), balances every 10 min
- fix(core): manual refresh_transactions service triggers coordinator push to entities


## 0.7.5 — 2026-03-27
Version: 0.7.5
Branch: claude/keen-meninsky
Changes:
- fix(core): expose config entry to API views (entry key was never set)
- fix(core): auto-refresh transactions on HA startup (summary panel showed zeros)

## 0.4.0 — 2026-03-24
Version: 0.4.0
Branch: main
PR: #17
Commit: 513ff1b
Changes:
- Benchmark auto-crawl with 7 German national averages (Destatis, Bundesbank, GDV)
- Drag & drop transaction categorizer (admin-only Lovelace card)
- CSV export service with auto-cleanup (1h TTL)
- GitHub Actions release workflow (creates releases on v* tags)

## 0.3.0 — 2026-03-24
Version: 0.3.0
Branch: main
PR: #16
Commit: 37aa2b8
Changes:
- N-person household budget model (equal, proportional, custom split)
- Recurring transaction detection (monthly pattern analysis)
- Income recognition with salary tolerance ±5 days
- Bonus detection (≥15% above 3-month average → Spielgeld)
- Month cycle logic (calendar vs. salary-based per person)
- Budget limit Number entities per category
- Split model + remainder mode Select entities
- 4 automation events (transaction_new, balance_changed, budget_exceeded, recurring_detected)
- Budget Config Lovelace card (split dropdown, remainder toggle, Spielgeld preview)
- Complete sidebar panel rewrite (donut chart, top-3 costs, fix vs. variable, shared costs bar)

## 0.2.0 — 2026-03-24
Version: 0.2.0
Branch: main
PR: #15
Commit: caedb35
Changes:
- GoCardless OAuth flow end-to-end (4-step config flow)
- Account balance sensors with bank logos (1 per account + optional aggregate)
- Monthly summary sensor with category breakdown
- Transaction fetching + caching in encrypted .storage/ (90-day lookback)
- Privacy-first API (admin-only transaction details, IBAN masking)
- OAuth callback endpoint with user-friendly HTML response
- Full EN/DE translations for all config flow steps

## initial — 2026-03-24
Version: 0.1.0
Branch: main
PR: —
Commit: initial
Changes:
- Initial project scaffold with complete architecture
- GoCardless Open Banking API client skeleton
- Secure credential manager with Fernet encryption + audit log
- Rule-based transaction auto-categorizer
- Companion add-on (Dockerfile, run.sh, payload sync)
- Sidebar panel + Lovelace card (web components)
- Config flow (GoCardless setup + options)
- Version management scripts + CI/CD pipeline
- EN/DE translations
