# Changelog

All notable changes to the Finance will be documented in this file.

## [0.15.2] — 2026-08-20

### Changed
- Test: the delivery path had zero coverage. `tests/test_addon_installer.py` executes `run.sh` for real against a temporary root (`FD_CONFIG_ROOT` / `FD_PAYLOAD_ROOT`, `FD_RUN_ONCE`) and pins the stale-module removal, the restart marker, the Lovelace copy, a bare first install, the no-op path, and the `startup: services` contract itself — total 315 → 323
- Ci: `bash -n` on run.sh, and `.gitattributes` pins `*.sh` to LF — a CRLF checkout breaks the shebang inside the Alpine container, failing as a stopped add-on rather than an error

### Fixed
- The companion add-on ran with `startup: once`, so it had already exited by the time Supervisor auto-updated it — and Supervisor only restarts add-ons that were *running*. The installer therefore only ever executed on a host reboot. On the reporting instance the add-on package sat at 0.14.0 while `/config` still held 0.13.0 with a file timestamp of 2026-04-25; 0.13.1, 0.14.0, 0.15.0 and 0.15.1 never reached disk. The add-on is now a resident service (`startup: services`) that installs on start and re-checks hourly, so every auto-update delivers its payload the minute it lands
- The installer replaces the integration tree instead of copying over it. `cp -r` removes nothing, so `api.py` and `manager.py` from 0.13.0 survived next to the packages of the same name that replaced them, together with their stale `__pycache__`. The delete sync is guarded by an allowlist — it deletes recursively, and only the two paths it owns
- A failed install no longer kills the container. Exiting left the add-on stopped, which is precisely the silent-failure mode that hid this outage for four months; the run is retried on the next interval instead. A TERM/INT trap plus backgrounded `sleep` lets a Supervisor stop take effect immediately rather than after the SIGKILL timeout
- The install-state file is rewritten on every check, not just on an update. Its timestamp is the only evidence visible from outside the container that the installer is alive — a stale one is what identified this bug

## [0.15.1] — 2026-08-20

### Changed
- Test: pin the empty-account-list case — total 314 -> 315

### Fixed
- The entity-registry reconciler removed every balance entity when the config entry listed no accounts. An empty list means "we do not know what is linked" — a half-configured setup, a storage-recovery round, a re-auth that cleared the list before failing — not "all orphaned". Reconciliation now returns early in that state, so it can no longer destroy history HA cannot restore. Found by re-reading the 0.15.0 diff before promoting it to stable

## [0.15.0] — 2026-08-20

### Added
- Institution catalog is cached (24h TTL). A fresh cache skips the API entirely; an outage degrades the wizard to the stale list, flagged with its date, instead of an empty one. An empty API result counts as a failure — DE always has banks
- Opening the panel triggers one attended live refresh when the cache is older than the configured threshold (default 60 min, `auto_refresh_on_open` / `auto_refresh_max_age_minutes`). Once per panel mount, never on an interval — this is what makes DKB balances current without spending the background budget

### Changed
- Test: +48 tests covering catalog rate-limit exemption and cache fallback, account identity and re-link dedup, registry migration/orphan cleanup, and the attended/background split — total 266 → 314, all green

### Fixed
- The setup wizard reported every failure as "Banken werden geladen…" — all three catch blocks assigned the LOADING string as the error message, so the real exception was discarded before anyone could read it. The wizard now surfaces the backend's `error_type` as a readable cause, appends the raw detail, distinguishes an HTTP status from a transport failure, and offers a retry button
- The bank list was gated on the 4/day ASPSP quota. `/aspsps` is Enable Banking's own catalog, not a call to any bank — it neither spends nor is bound by that quota — so a user who had refreshed four times could not connect a new bank until midnight. `_get_setup_client` now takes `enforce_rate_limit`, and the catalog opts out
- Account identity is now the IBAN, not the Enable Banking session uid. The uid is reissued on every re-link, so re-connecting a bank created a second set of entities for the same real account and orphaned the first. `account_identity.py` derives a stable key (truncated SHA-256 — the key lands in the entity registry, so it must not carry the account number), merges re-links onto it, and preserves user-owned fields (custom name, type, person, HA users) across the merge
- Entity registry is reconciled on setup — entities still on the uid-derived `unique_id` are migrated in place (entity_id and history preserved), and balance entities owned by no linked account are removed. This clears duplicates left by earlier re-links
- Attended calls are no longer gated on the rate limit. PSD2 RTS Art. 36(5)(b) caps AISP access only when the user is not in session; with PSU headers present the cap does not apply, so refusing the refresh button while rate-limited denied a call the bank permits. The refresh endpoint, the manager pre-flight check, the header button and the panel's client-side guard all now distinguish attended from background
- A 429 backs off 6h (Enable Banking's documented retry) instead of until midnight — a rate limit at 07:00 used to cost the entire day. An attended 429 is transient upstream noise and pauses 15 minutes. `Retry-After` still wins, capped at midnight where the ASPSP day counter resets

## [0.14.0] — 2026-08-17

### Added
- Budget_plan.py — cost-position ledger, the model the household spreadsheet is built on. Positions carry an explicit owner (person or shared), a signed amount (negative = reimbursement billed onward), a kind (fixed or buffer with units x unit price), an inclusive YYYY-MM validity window, and an optional debit account independent of the owner
- Spreadsheet_import.py — migrates a `Kalkulation Haushalt.xlsx` workbook into the plan. Recovers buffer factors from formulas (`=80*4.5`), validity windows from prose comments ("bis inkl. April 2027"), and cross-checks recomputed net income against the sheet's own stated net, reporting any mismatch
- Transfer_plan.py — reproduces the workbook's monthly transfer choreography (accounts x ordered steps) and enforces its central invariant in code: a pass-through account must net to zero. Contributions are liquidity-aware, so a person whose income cannot cover their share contributes what they have and the rest is carried by those with a surplus
- `settlement_delta` per person — how much one person is fronting for another. The spreadsheet contained this implicitly as the gap between account balance and entitled pocket money; it is now explicit
- `pooled_equal` split model — shared costs paid from POOLED net income, remainder split equally, each person then paying their own individual costs. Now the default. The previous models computed a materially different result and could not carry a person with negative net income
- Plan-vs-actual comparison per category and per position, with unmatched positions reported as unmatched rather than shown as zero
- BenchmarkProvider wired up — it was dead code with zero imports repo-wide. The "ours" side is now computed from the plan, plus a manual water-consumption metric (not derivable from banking data)
- /budget_plan, /transfer_plan, /plan_vs_actual, /benchmark, plus admin-gated position/income/import endpoints. Import paths are validated against `allowlist_external_dirs`
- Fd-budget-plan card — income breakdown, cost ledger grouped by owner, pocket money, transfer table with the zero-sum badge, benchmark comparison
- Once-daily scheduled refresh at a configurable time (default 06:30). One call of the 4/day/ASPSP budget, leaving three for manual refreshes
- `import_spreadsheet` (admin-only, allowlist-checked) and `get_transfer_plan`

### Changed
- Test: +81 tests covering the plan model, the split invariants, transfer-plan balancing, and the Enable Banking normalization layer that had no coverage at all — total 185 → 266, all green
- Chore(deps): openpyxl>=3.1.0 for spreadsheet import

### Fixed
- Transaction fetch could never parse a real Enable Banking response. The API returns `{"transactions": [...], "continuation_key": ...}` — a LIST — while the client called `.get("booked")` on it, raising AttributeError for every account. Swallowed by a broad handler, so refreshes reported success over an empty cache
- Derive the amount sign from `credit_debit_indicator` (CRDT/DBDT). It appeared nowhere in the codebase, so every transaction would have read as income with total expenses stuck at 0
- Honour per-transaction `status` (BOOK/PDNG) instead of hardcoding buckets; join `remittance_information`, which is an array, not a string
- Follow `continuation_key` pagination, capped at 10 pages with the truncation logged rather than silent
- Pass ISO 20022 balance codes through (CLBD/ITAV/...) and match them in the sensor's priority list, which previously listed only camelCase names and could never match — so each account showed whichever balance the bank happened to list first
- HA start crashed on every restart — a sync lambda calling `hass.async_create_task` from a worker thread tripped HA's thread-safety guard, the coroutine was never awaited, and the transaction cache was therefore never loaded. Entities stayed empty until a manual refresh
- Merge each fetch window into the cached history instead of replacing it. Every refresh previously truncated history to the rolling window, making multi-month views impossible to populate
- Only stamp `_last_refresh` when at least one account answered. A total failure used to look identical to a success, and the false timestamp survived restarts via persistence
- Tag pending transactions with account/person like booked ones
- Expose `last_refresh_stats`, `is_refreshing`, `cache_age_seconds`, `cache_is_stale` — the frontend already read these keys, which never existed, so a stale cache was visually indistinguishable from fresh data
- Honour the documented `days` field on `refresh_transactions` and month/year on `get_monthly_summary`; both were advertised and ignored
- A "Kommentar" column header was read as a person column, so every validity window in the sheet was lost
- The transfer plan reports amounts it cannot place on any account (`unplaced`) instead of dropping them. Without a joint account every shared position was skipped, no account ended up out of balance, and the plan declared itself balanced while omitting the largest cost block
- sync_changelog.py appended every entry to the BOTTOM of CHANGELOG.md — its header-detection regex alternation included `$`, which matches every blank line, so the insertion point became the last blank line of the file. `--check` read the first heading and therefore reported the CHANGELOG as permanently behind while claiming each sync succeeded. Added `--repair` and re-sorted all 44 accumulated sections newest-first

## [0.13.1] — 2026-05-16

### Added
- Global :focus-visible outline rings + prefers-reduced-motion override in SHARED_CSS
- Aria-expanded on transactions-log show-more toggle
- New design tokens in SHARED_CSS (--r-sm/md, --sh-sm/md/lg, --fs-sm/md/lg/xl, --lh-tight/normal, --sp-xs/sm/md/lg/xl) for upcoming token-migration polish

### Changed
- Remove unused TRANSACTION_REFRESH_STALENESS constant + timedelta import
- Test: +20 unit tests for events.py (11) + export.py (9 incl. OSError/OverflowError monkeypatch paths) — total 165 → 185, all green
- Chore(lint): ruff sweep across tests/ — 44 fixes (import order, unused imports, datetime.UTC migration)
- Chore(payload): re-sync addon mirror (incl. pre-existing UTC drift from v0.13.0)

### Fixed
- RateLimitExceeded on /setup/complete surfaces as error_type=rate_limited in HTTP 200 body (matches setup-wizard contract; was previously masked as generic failure)
- Categorizer None-guard with WARNING log — refresh races ahead of init fall back to category="other" instead of crashing
- Cleanup of old CSV exports swallows OSError/ValueError/OverflowError and logs cause (no more silent bare-except)

## [0.13.0] — 2026-04-25

### Added
- MultiFernet credential storage with key rotation + v1→v2 migration (S2)
- Timing-safe OAuth state validation with one-time-use, 10min TTL, 32-entry cap, cross-store fallback (S4, F1, F3, F5)
- Unified setup-wizard rate-limit gate via async_make_setup_call + persistent fresh-setup gate (S3, F2, F4)
- IBAN/account-id/EUR-amount log sanitizer; raw API bodies no longer hit ERROR-level logs (S1)
- Pre-commit secret-scan hook (.pre-commit-config.yaml + scripts/check_no_banking_data.py) (R11)
- PyJWT[crypto] migration with iss=application_id, aud=api.tilisy.com, per-request jti (A4)
- Shared aiohttp ClientSession via async_get_clientsession (A5)
- Retry-After header honored on 429 + PSU headers for online-mode (D5, D6)
- /refresh_status exposes rate_limit_per_day + cache_is_stale + cache_age_seconds (D7, D9)
- Setup-wizard modal with role/aria-modal/focus-trap/ESC (U1)
- Institution list with full keyboard navigation (role/listbox/option) (U2)
- Donut chart aria-label + visually-hidden table fallback (U3)
- Toast aria-live based on severity (assertive for warn/error) (U4)
- Cost-distribution role/group + per-segment aria-label (U5)
- I18n with locale JSON files + hass.language detection + tSync helper (U6, G1-G4)
- Skeleton/loading states across all card components (U8)
- + Bank entry-point opens wizard from header (U10)
- Countdown for setup-wizard auth-polling step (D8)
- Persistent notification after config_flow completion (U11)

### Changed
- Split api.py (1258 LOC) into api/ package (setup, refresh, data, static, demo, _helpers) (A1)
- Split manager.py (1151 LOC) into mixin modules (RefreshMixin, PersistenceMixin) (A2)
- Persistent component tree replaces full-rebuild on every data update (A3)
- SHARED_CSS adoption + CAT_COLORS/LABELS consolidation in fd-shared-styles (F2, F3)
- All hardcoded color literals replaced with CSS tokens (F4)
- Unified disconnectedCallback for memory cleanup (F5)
- Shared escHtml helper (F8)
- Month label as static span (U7)
- Chore: remove deprecated GoCardless client (F1)
- Manager.async_set_accounts encapsulation (F6)
- Perf(security): reuse audit-log Store instance (F7)
- Chore(manifest): iot_class cloud_polling → cloud_push (D2)
- Docs: align repairs.py role + sync services.yaml (D3, D4)
- Docs: precise update_interval docstring on coordinator (D10)
- Test: scaffold tests/ + pyproject.toml + requirements_test.txt (T1, T6)
- Test: cache-vs-live-boundary contract test as guardian (T2)
- Test: JWT/Fernet edge-case coverage (T3, 21 tests)
- Test: parametrized categorizer rule coverage (T4, 79 tests)
- Test: transfer-detector cascade + override + confidence (T5, 27 tests)
- Chore(ci): pytest with coverage in validate workflow (T7)
- Docs: sync CLAUDE.md phases with actual code state (D1)
- Docs: audit-synthesis concept page (Phase 2 artifact)
- Result: 165/165 tests pass; ruff 0 errors; coverage 31% (categorizer 96%, transfer_detector 91%, const 100%); payload synced

### Fixed
- /refresh and toggle_demo now require admin (R9, R14)
- Partial-refresh per-account cache prevents data loss on partial bank failure (R5, F10)
- Corrupt .storage recovery via try/except + repair-issue (R8)
- Static file serving non-blocking via async_add_executor_job + LRU cache (R12)
- Repair-issue payloads scrubbed of exception strings (R10)
- _reconstruct_pem PKCS1/PKCS8 detection corrected (C9)
- Responsive breakpoint at 980px for category section (U9)
- Mark auth+storage repairs as is_persistent (D11)
- Fix: dt_util.now() instead of datetime.now() throughout (D12)

### Changed
- Register `fd-transactions-log.js` in `LOVELACE_COMPONENTS`, append component after `fd-recurring-list` in the shell's component tree

## [0.12.1] — 2026-04-24

### Changed
- Drop unused `ENABLEBANKING_RATE_LIMIT_DAILY` import, move `RateLimitExceeded` below all imports for a clean module layout
- Replace stale "GoCardless/Nordigen" docstring in `__init__.py` with Enable Banking PSD2 reference and document the 4/day/ASPSP rate-limit gate
- Replace stale "GoCardless Open Banking API" description in `finance_dashboard_companion/config.yaml` with Enable Banking PSD2

### Fixed
- Preserve partial balances when Enable Banking rate-limit hits mid-fetch — accounts that succeeded before the 429 no longer lose their fresh value, merged into the existing cache instead of being discarded
- Reconstruct `_previous_balances` baseline from cached balances on `async_initialize` so the first refresh after every HA restart no longer fires spurious `fd_balance_changed` events for every account
- Balance-refresh end path now merges into existing cache instead of replacing — accounts that errored this round keep their last known value
- Deferred reload after setup-wizard completion now triggers a real live refresh via `manager.async_refresh_transactions()` instead of a cache-only `coordinator.async_refresh()` — entities populate with actual bank data immediately, no more "unavailable" state until the user clicks "Aktualisieren"
- `async_load_cached` failure path publishes an empty snapshot so entities stay `unknown` (recoverable) instead of `unavailable` (stuck) when cache read errors
- `refresh_accounts` service call now pushes the updated state through the coordinator so dashboards reflect the new account metadata immediately, matching `refresh_transactions` behavior
- Always load the cached snapshot into the coordinator regardless of `configured`/`demo_mode` state so half-configured entries don't leave entities permanently unavailable
- `BudgetLimitNumber` now inherits from `RestoreEntity` — user-set budget limits survive HA restarts instead of silently resetting to 0
- `SplitModelSelect` and `RemainderModeSelect` listen for config-entry updates and re-sync their current option when the options flow changes the stored key — no more stale display after external option changes
- `/demo/toggle` returns HTTP 503 when no manager is configured instead of toggling a dead `hass.data` flag that nothing reads

## [0.12.0] — 2026-04-23

### Added
- New `fd-transactions-log` card shows imported (cached) transactions after at least one bank is linked and a refresh ran — date, counterparty, description, category badge, account, coloured amount, "vorgemerkt" flag for pending items; collapses to 25 rows with "Alle N anzeigen" toggle (cap 100 from the API)
- `fd-data-provider` caches `/api/finance_dashboard/transactions` in-memory, refetches on user-triggered refresh and on first rebuild with linked accounts — entity-only state changes no longer trigger redundant fetches, and the endpoint is cache-read only (unbounded-safe, no Enable Banking call)

## [0.11.1] — 2026-04-20

### Fixed
- Btn-demo now renders neutral/ghost by default — orange fill only when demo mode is active (btn-demo-active), preventing false "already in demo" appearance
- Refresh race eliminated — after POST /refresh, poll for entity state change (≤5s, 500ms ticks) before calling _rebuild(), avoiding stale hass.states read that returned accountCount=0 and flashed onboarding screen
- _onHassChanged no longer advances _prevStateHash when _loading=true; instead sets _pendingRebuild=true so _rebuild retries immediately after the in-flight rebuild finishes, closing the concurrent-rebuild deadlock

## [0.11.0] — 2026-04-20

### Added
- Serialise user-triggered refreshes with `asyncio.Lock` to prevent double-click concurrent fetches
- Persist `rate_limited_until` and `last_refresh_stats` across HA restart so the 4/day counter is not lost on reboot
- Track structured refresh stats (outcome, accounts, transactions, new, duration_ms, errors) exposed via `manager.get_refresh_status()`
- New `POST /api/finance_dashboard/refresh` endpoint — the single user-triggered live-fetch entry point, returns stats synchronously
- New `GET /api/finance_dashboard/refresh_status` — cache-only polling endpoint, unbounded reads allowed
- `refresh_transactions` service now uses `SupportsResponse.OPTIONAL` and returns stats so automations can react to the outcome
- Refresh_transactions refreshes balances in the same user-triggered round — one click, one cache update
- Refresh button now shows a result toast ("5 Konten, 243 Transaktionen, 2 neu in 3.1s" / rate-limit / partial / error)
- Header timestamp shows live cache age ("Zuletzt 14:23 · vor 2 Std") and updates every minute
- Rate-limit and loading states surfaced clearly next to the refresh button instead of silent "Aktualisieren" reverts

### Changed
- Remove staleness-based auto-refresh — coordinator is now a pure cache projection, live fetches only via dedicated endpoint
- Docs(claude-md): replace stale GoCardless references with Enable Banking, document cache vs. live-fetch contract

### Fixed
- Separate cache-reads from live API fetches — `manager.async_get_balance()` now returns cached balances only (was hitting Enable Banking on every HTTP `/balances` call, burning the 4/day/ASPSP rate limit)
- "Noch keine Daten" state now has explicit styling + hint to click Aktualisieren

## [0.10.1] — 2026-04-19

### Fixed
- Propagate OAuth callback errors through /setup/status so the wizard surfaces them within 2s instead of timing out after 5min
- Hard-fail /setup/authorize when callback URL is HTTP (Enable Banking requires pre-registered HTTPS redirect)
- Trigger one coordinator refresh after deferred entry reload so entities populate immediately after bank link
- Raise Repairs issue on missing or invalid Enable Banking credentials, auto-clear on recovery
- Wizard polling stops on setup_error and shows the message instead of waiting for timeout
- Data provider subscribes to entity_registry_updated events so newly created sensors appear without race-prone 4s timer

## [0.10.0] — 2026-04-12

### Added
- Add inline bank connection wizard as modal overlay (4-step flow: institution search, bank authorization with polling, account assignment, success)
- Add "+ Konto" button in header to open wizard from anywhere

### Changed
- Replace onboarding "Einstellungen" link with inline "Bankkonto verbinden" button

### Fixed
- Replace fragile entity_id prefix matching with HA Entity Registry lookup — entities are now found by platform + unique_id regardless of HA-generated entity_ids
- Add 4s delay before refreshRegistry() after setup complete to wait for HA config entry reload
- Add https scheme validation on auth URLs to prevent XSS via javascript: scheme
- Update institution filter to only re-render list container (prevents cursor jump)

## [0.9.2] — 2026-04-11

### Added
- Add onboarding welcome screen with "Demo starten" CTA when no bank accounts connected
- Show "Noch keine Daten" timestamp fallback when no refresh has occurred
- Make Demo button more prominent with visible background fill

### Changed
- Remove automatic banking API calls on HA startup — coordinator now loads from cache only, no external calls until user clicks "Aktualisieren"
- Remove _first_update force-refresh flag from coordinator — staleness check is sufficient
- Remove automatic API fallback in _rebuild() — /summary endpoint only called on explicit user refresh, not on every entity change

### Fixed
- Handle loading state in _onData to prevent clearing content during demo toggle

## [0.9.1] — 2026-04-07

### Added
- Chore: sync addon payload

### Changed
- Chore: sync translations (en.json, de.json) with new issue description

### Fixed
- Add missing issue-level description to strings.json — Repairs card had no body text, rendering it invisible in some HA versions
- Add is_persistent=True to ir.async_create_issue — prevents HA from discarding the issue during internal operations
- Wrap synchronous file I/O (exists/read_text/unlink) in async_add_executor_job — HA 2024+ blocks or warns on sync I/O in event loop
- Return None for unknown issue_ids instead of generic RepairsFlow()

## [0.9.0] — 2026-04-05

### Added
- Full demo mode with realistic German banking data (3 accounts, ~35 transactions, household split, recurring patterns)
- Toggle via UI button (admin-only), service call, or options flow — persists across HA restarts
- Manual-only API refresh — coordinator update_interval=None, data only updates on explicit user action
- Demo toggle button with DEMO badge, aria-pressed accessibility, mobile breakpoint

### Fixed
- Initial coordinator refresh now works on config entry reloads (not just first HA start)
- Shutdown no longer overwrites real transaction cache when demo mode is active
- AttributeError in DemoToggleView coordinator lookup — null-safe access pattern
- GoCardless reference replaced with Enable Banking in services.yaml
- Removed dead COORDINATOR_UPDATE_INTERVAL constant and corrected all docstrings
- Rapid-click guard and loading state for demo API calls
- DemoMode flag propagated in all data events for consistent UI state

## [0.8.1] — 2026-04-02

### Added
- Chore: add .playwright-mcp/ to .gitignore

## [0.8.0] — 2026-03-28

### Changed
- Decompose monolithic panel into 10 web components (fd-data-provider, fd-header, fd-stats-row, fd-stat-card, fd-household-section, fd-person-card, fd-category-section, fd-donut-chart, fd-cost-distribution, fd-recurring-list)
- Entity-first data strategy — fd-data-provider reads HA sensor/number/select entities, falls back to API for household+recurring
- Panel shell reduced from 507 lines to ~120 lines
- Docs: ARCHITECTURE-FRONTEND.md added with component hierarchy, data flow, entity table, event system

### Fixed
- Coordinator force-refreshes transactions on first cycle — prevents stale cache showing 0,00 EUR
- Account settings API now persists `person` field for household assignment
- Monthly summary sensor exposes fixed_costs, variable_costs, household, recurring attributes

## [0.7.8] — 2026-03-28

### Fixed
- Graceful degradation for household model — exception no longer crashes coordinator
- Graceful degradation for recurring detection — failure yields empty list
- Graceful degradation for budget limit checks — log and skip on error
- Graceful degradation for event firing (balance + transaction) — never blocks data flow

## [0.7.7] — 2026-03-28

### Added
- Integrate HouseholdModel into manager — auto-builds members from account assignments, computes per-person Spielgeld splits
- Activate recurring payment detection on each transaction refresh
- Fire fd_transaction_new, fd_balance_changed, fd_budget_exceeded events
- Budget limit checking against Number entities per category
- Fixed vs variable cost computation in summary API
- Dashboard shows real bank balance from API (not income minus expenses)
- Person cards with Spielgeld, income ratio, shared costs share
- Shared Fixkosten bar with per-person distribution
- Recurring payments section with detected patterns
- German category labels (Wohnen, Mobilität, etc.)
- Responsive layout for mobile viewports

### Fixed
- XSS protection for user-provided names

## [0.7.6] — 2026-03-28


### Added
- Coordinator refreshes transactions only when cache is stale (>6 h), balances every 10 min

## [0.7.5] — 2026-03-27

### Fixed
- Expose config entry to API views (entry key was never set)
- Auto-refresh transactions on HA startup (summary panel showed zeros)

## [0.7.4] — 2026-03-26

### Added
- **Changes:** feat(frontend): status chip replaces refresh button
- New `<finance-status-chip>` Lovelace component with 4 visual states (idle/loading/success/error)
- Register status chip JS as Lovelace extra module

### Changed
- **Branch:** claude/upbeat-davinci
- Panel header uses status chip instead of refresh button + dot indicator

## [0.7.3] — 2026-03-26

### Fixed
- Setup wizard race condition — guard flag prevents wizard re-trigger during entry reload
- Account defaults in step 3 — merge existing settings into pending accounts

## [0.7.2] — 2026-03-26

### Fixed
- `setup/complete` merges new accounts with existing ones instead of replacing entry.data
- Dashboard `_refresh()` uses independent `.catch()` per endpoint instead of `Promise.all`
- Manage accounts dialog retries 3x with 2s delay before showing error

## [0.7.1] — 2026-03-26

### Fixed
- Defer settings overlay render to prevent flash on load
- Correct balance data display in account cards

## [0.7.0] — 2026-03-26

### Added
- Cascading transfer chain detection

## [0.6.15] — 2026-03-26

### Added
- Gesamtsaldo uses actual bank balances from `/balances` API instead of transaction sums
- Settings gear icon in dashboard header for account management
- Manage-accounts overlay with rename, type change, person assignment, connect new bank
- New `update_accounts` endpoint and account details in `setup/status`

## [0.6.14] — 2026-03-26

### Added
- Shimmer skeleton loaders replacing plain loading text
- Async refresh indicator (pulsing dot + timestamp) — old data stays visible
- Responsive breakpoints for tablet (≤900px) and mobile (≤480px)
- Improved empty state with SVG icon and descriptive text

## [0.6.12] — 2026-03-26

### Added
- Step 3 offers HA user multi-select chips (n:m) instead of free-text person field
- Custom display name field per account
- New `GET /api/finance_dashboard/setup/users` endpoint for HA user list
- New fields propagated through manager, sensor attributes, and transaction tagging

## [0.6.9] — 2026-03-26

### Fixed
- RepairsFlow calls `homeassistant.restart` service when user confirms
- Repair notification title says "Restart Required" instead of "Update Available"
- Updated EN and DE translations for restart repair flow

## [0.6.5] — 2026-03-25

### Fixed
- Retry logic and error handling in EnableBanking client for bank list API calls
- Graceful error handling when fetching supported banks fails
- Frontend error state with actionable feedback for bank list loading failures
- Improved error response handling for bank list endpoint

## [0.6.4] — 2026-03-25

### Fixed
- Return dict from `async_get_api_credentials` instead of tuple (callers expected dict-style access; tuple caused TypeError)

## [0.6.3] — 2026-03-25

### Fixed
- Backend returns typed errors (`error_type`) for differentiated frontend handling
- Frontend shows specific German error messages per error type
- Credential errors link to integration settings instead of retry
- 5-minute polling timeout in Step 2, cancel button to return to Step 1

## [0.6.2] — 2026-03-25

### Fixed
- Move restart marker poll outside `is_configured`, check on startup, remove persistent notification fallback

## [0.6.1] — 2026-03-25

### Fixed
- 30s timeout added to Enable Banking API, error state with retry button
- Rename "Finance Dashboard" to "Finance" everywhere

## [0.6.0] — 2026-03-25

### Changed
- **Breaking**: Bank setup moved from config flow to dashboard panel setup wizard
- Config flow reduced to credentials-only (1 step, config VERSION 3)
- Config entry migration v2→v3 preserves existing setups

### Added
- 4-step setup wizard overlay in Finance sidebar panel
- 4 new setup API endpoints (status, institutions, authorize, complete)

### Fixed
- Enable Banking API: `authorization_id` field, nested IBAN, UUID state
- Panel registration: `StaticPathConfig` with cache, correct unregister

## [0.5.5] — 2026-03-25

### Fixed
- Added granular debug logging for Enable Banking HTTP requests and responses (status code, URL, error body on non-OK responses)
- Added debug logging in bank authorization step: callback URL, institution name, full API response, and explicit error when auth URL is missing

## [0.5.2] — 2026-03-25

### Fixed
- Config flow error handling now distinguishes PEM key format errors from API auth failures
- Specific error messages for: invalid key format (PEM parsing), auth rejected (401/403), network errors

### Changed
- README fully updated: all GoCardless references replaced with Enable Banking, version synced, setup instructions rewritten
- CHANGELOG updated with v0.5.0 and v0.5.1 entries

## [0.5.1] — 2026-03-25

### Fixed
- PEM private key field now renders as multiline textarea (was single-line, truncating key)
- Removed deprecated `armhf`, `armv7`, `i386` arch values from companion add-on config
- Updated add-on description from GoCardless to Enable Banking

### Improved
- Step-by-step instructions in Enable Banking setup dialog (EN + DE)
- Config flow shows redirect URL dynamically for easy copy-paste

## [0.5.0] — 2026-03-25

### Changed
- **Breaking**: Migrated from GoCardless to Enable Banking API
  - New credentials format: Application ID + RSA Private Key (PEM) instead of Secret ID/Key
  - JWT-based per-request authentication (RS256) instead of OAuth tokens
  - Config flow version bumped to 2 (automatic reconfigure prompt for existing users)
- API client rewritten for Enable Banking endpoints with GoCardless-compatible normalization

## [0.4.3] — 2026-03-25

### Fixed
- Removed unused `nordigen-python==2.1.0` dependency from `manifest.json` that caused 500 Internal Server Error during config flow (package not installable)

## [0.4.2] — 2026-03-25

### Fixed
- Sidebar panel not appearing in HA (used wrong API: `async_register_built_in_panel` → `panel_custom.async_register_panel`)
- Non-standard `channel` field in `repository.yaml` removed
- Add-on CHANGELOG.md added (required by Supervisor for update display)

## [0.4.1] — 2026-03-24

### Fixed
- Companion add-on not showing updates in HA (missing `exec sleep infinity` — container exited immediately)
- Add-on config missing `stage`, `options`, `schema` fields required by HA Supervisor
- Wrong API permission field (`auth_api` → `homeassistant_api`)
- Brand assets using SVGs instead of PNGs (HA ignores SVGs)
- Missing dark mode icon variants (`dark_icon.png`, `dark_logo.png`)

### Added
- Procedural branding asset generator (`scripts/generate_branding_assets.py`)
- bashio logging integration for structured HA log output

## [0.4.0] — 2026-03-24

### Added
- Benchmark auto-crawl with 7 German national averages (Destatis, Bundesbank, GDV)
- Drag & drop transaction categorizer (admin-only Lovelace card)
- CSV export service with auto-cleanup (1h TTL)
- GitHub Actions release workflow (creates releases on v* tags)

## [0.3.0] — 2026-03-24

### Added
- N-person household budget model (equal, proportional, custom split)
- Recurring transaction detection (monthly pattern analysis)
- Income recognition with salary tolerance ±5 days
- Bonus detection (≥15% above 3-month average → Spielgeld)
- Month cycle logic (calendar vs. salary-based per person)
- Logical month assignment for recurring costs (bank day correction)
- Budget limit Number entities per category
- Split model + remainder mode Select entities
- 4 automation events (transaction_new, balance_changed, budget_exceeded, recurring_detected)
- Budget Config Lovelace card (split dropdown, remainder toggle, Spielgeld preview)
- Complete sidebar panel rewrite (donut chart, top-3 costs, fix vs. variable, shared costs bar)

## [0.2.0] — 2026-03-24

### Added
- GoCardless OAuth flow end-to-end (4-step config: credentials → bank → authorize → assign)
- Account balance sensors with bank logos (1 per account + optional aggregate)
- Monthly summary sensor with category breakdown
- Transaction fetching + caching in encrypted .storage/ (90-day lookback)
- Privacy-first API (admin-only transaction details, IBAN masking)
- OAuth callback endpoint with user-friendly HTML response
- Full EN/DE translations for all config flow steps

## [0.1.0] — 2026-03-24
