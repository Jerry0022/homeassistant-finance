# Changelog

All notable changes to the Finance will be documented in this file.

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

## [0.7.4] — 2026-03-26

### Added
- **Changes:** feat(frontend): status chip replaces refresh button
- New `<finance-status-chip>` Lovelace component with 4 visual states (idle/loading/success/error)
- Register status chip JS as Lovelace extra module

### Changed
- **Branch:** claude/upbeat-davinci
- Panel header uses status chip instead of refresh button + dot indicator

## [0.7.5] — 2026-03-27

### Fixed
- Expose config entry to API views (entry key was never set)
- Auto-refresh transactions on HA startup (summary panel showed zeros)

## [0.7.6] — 2026-03-28


### Added
- Coordinator refreshes transactions only when cache is stale (>6 h), balances every 10 min

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

## [0.8.1] — 2026-04-02

### Added
- Chore: add .playwright-mcp/ to .gitignore

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

## [0.10.1] — 2026-04-19

### Fixed
- Propagate OAuth callback errors through /setup/status so the wizard surfaces them within 2s instead of timing out after 5min
- Hard-fail /setup/authorize when callback URL is HTTP (Enable Banking requires pre-registered HTTPS redirect)
- Trigger one coordinator refresh after deferred entry reload so entities populate immediately after bank link
- Raise Repairs issue on missing or invalid Enable Banking credentials, auto-clear on recovery
- Wizard polling stops on setup_error and shows the message instead of waiting for timeout
- Data provider subscribes to entity_registry_updated events so newly created sensors appear without race-prone 4s timer

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

## [0.11.1] — 2026-04-20

### Fixed
- Btn-demo now renders neutral/ghost by default — orange fill only when demo mode is active (btn-demo-active), preventing false "already in demo" appearance
- Refresh race eliminated — after POST /refresh, poll for entity state change (≤5s, 500ms ticks) before calling _rebuild(), avoiding stale hass.states read that returned accountCount=0 and flashed onboarding screen
- _onHassChanged no longer advances _prevStateHash when _loading=true; instead sets _pendingRebuild=true so _rebuild retries immediately after the in-flight rebuild finishes, closing the concurrent-rebuild deadlock

## [0.12.0] — 2026-04-23

### Added
- New `fd-transactions-log` card shows imported (cached) transactions after at least one bank is linked and a refresh ran — date, counterparty, description, category badge, account, coloured amount, "vorgemerkt" flag for pending items; collapses to 25 rows with "Alle N anzeigen" toggle (cap 100 from the API)
- `fd-data-provider` caches `/api/finance_dashboard/transactions` in-memory, refetches on user-triggered refresh and on first rebuild with linked accounts — entity-only state changes no longer trigger redundant fetches, and the endpoint is cache-read only (unbounded-safe, no Enable Banking call)

### Changed
- Register `fd-transactions-log.js` in `LOVELACE_COMPONENTS`, append component after `fd-recurring-list` in the shell's component tree

### Fixed
- Prevent infinite loading spinner when no fd_ entities exist — data provider now always triggers initial rebuild
- Dashboard no longer stuck on "Lade Finanzdaten..." when no finance entities exist — data provider always triggers initial rebuild
- Restart notification no longer lost due to race condition in entry setup — preserves issue when marker file exists and polls immediately
- Add DataUpdateCoordinator — entities no longer call banking API directly
- Sensor update interval 10 min via coordinator (was ~30 s per entity → rate-limit exhaustion)
- Panel refresh on connectedCallback + 10-min auto-timer instead of every hass setter
- Lovelace card throttles API calls to max once per 10 min (was every hass setter)
- Manual refresh_transactions service triggers coordinator push to entities
