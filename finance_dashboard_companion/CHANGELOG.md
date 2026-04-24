# Changelog

## 0.12.1
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
- Drop unused `ENABLEBANKING_RATE_LIMIT_DAILY` import, move `RateLimitExceeded` below all imports for a clean module layout
- Docs(__init__): replace stale "GoCardless/Nordigen" docstring with Enable Banking PSD2 reference, document the 4/day/ASPSP rate-limit gate
- Docs(addon): replace stale "GoCardless Open Banking API" description in `finance_dashboard_companion/config.yaml` with Enable Banking PSD2

## 0.12.0
- New `fd-transactions-log` card shows imported (cached) transactions after at least one bank is linked and a refresh ran — date, counterparty, description, category badge, account, coloured amount, "vorgemerkt" flag for pending items; collapses to 25 rows with "Alle N anzeigen" toggle (cap 100 from the API)
- `fd-data-provider` caches `/api/finance_dashboard/transactions` in-memory, refetches on user-triggered refresh and on first rebuild with linked accounts — entity-only state changes no longer trigger redundant fetches, and the endpoint is cache-read only (unbounded-safe, no Enable Banking call)
- Register `fd-transactions-log.js` in `LOVELACE_COMPONENTS`, append component after `fd-recurring-list` in the shell's component tree

## 0.11.1
- Btn-demo now renders neutral/ghost by default — orange fill only when demo mode is active (btn-demo-active), preventing false "already in demo" appearance
- Refresh race eliminated — after POST /refresh, poll for entity state change (≤5s, 500ms ticks) before calling _rebuild(), avoiding stale hass.states read that returned accountCount=0 and flashed onboarding screen
- _onHassChanged no longer advances _prevStateHash when _loading=true; instead sets _pendingRebuild=true so _rebuild retries immediately after the in-flight rebuild finishes, closing the concurrent-rebuild deadlock

## 0.11.0
- Separate cache-reads from live API fetches — `manager.async_get_balance()` now returns cached balances only (was hitting Enable Banking on every HTTP `/balances` call, burning the 4/day/ASPSP rate limit)
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
- "Noch keine Daten" state now has explicit styling + hint to click Aktualisieren
- Remove staleness-based auto-refresh — coordinator is now a pure cache projection, live fetches only via dedicated endpoint
- Docs(claude-md): replace stale GoCardless references with Enable Banking, document cache vs. live-fetch contract

## 0.10.1
- Propagate OAuth callback errors through /setup/status so the wizard surfaces them within 2s instead of timing out after 5min
- Hard-fail /setup/authorize when callback URL is HTTP (Enable Banking requires pre-registered HTTPS redirect)
- Trigger one coordinator refresh after deferred entry reload so entities populate immediately after bank link
- Raise Repairs issue on missing or invalid Enable Banking credentials, auto-clear on recovery
- Wizard polling stops on setup_error and shows the message instead of waiting for timeout
- Data provider subscribes to entity_registry_updated events so newly created sensors appear without race-prone 4s timer

## 0.10.0
- Add inline bank connection wizard as modal overlay (4-step flow: institution search, bank authorization with polling, account assignment, success)
- Replace fragile entity_id prefix matching with HA Entity Registry lookup — entities are now found by platform + unique_id regardless of HA-generated entity_ids
- Add "+ Konto" button in header to open wizard from anywhere
- Replace onboarding "Einstellungen" link with inline "Bankkonto verbinden" button
- Add 4s delay before refreshRegistry() after setup complete to wait for HA config entry reload
- Add https scheme validation on auth URLs to prevent XSS via javascript: scheme
- Update institution filter to only re-render list container (prevents cursor jump)

## 0.9.2
- Remove automatic banking API calls on HA startup — coordinator now loads from cache only, no external calls until user clicks "Aktualisieren"
- Remove _first_update force-refresh flag from coordinator — staleness check is sufficient
- Remove automatic API fallback in _rebuild() — /summary endpoint only called on explicit user refresh, not on every entity change
- Add onboarding welcome screen with "Demo starten" CTA when no bank accounts connected
- Show "Noch keine Daten" timestamp fallback when no refresh has occurred
- Make Demo button more prominent with visible background fill
- Handle loading state in _onData to prevent clearing content during demo toggle

## 0.9.1
- Add missing issue-level description to strings.json — Repairs card had no body text, rendering it invisible in some HA versions
- Add is_persistent=True to ir.async_create_issue — prevents HA from discarding the issue during internal operations
- Wrap synchronous file I/O (exists/read_text/unlink) in async_add_executor_job — HA 2024+ blocks or warns on sync I/O in event loop
- Return None for unknown issue_ids instead of generic RepairsFlow()
- Chore: sync translations (en.json, de.json) with new issue description
- Chore: sync addon payload

## 0.9.0
- Full demo mode with realistic German banking data (3 accounts, ~35 transactions, household split, recurring patterns)
- Toggle via UI button (admin-only), service call, or options flow — persists across HA restarts
- Manual-only API refresh — coordinator update_interval=None, data only updates on explicit user action
- Initial coordinator refresh now works on config entry reloads (not just first HA start)
- Shutdown no longer overwrites real transaction cache when demo mode is active
- AttributeError in DemoToggleView coordinator lookup — null-safe access pattern
- GoCardless reference replaced with Enable Banking in services.yaml
- Removed dead COORDINATOR_UPDATE_INTERVAL constant and corrected all docstrings
- Demo toggle button with DEMO badge, aria-pressed accessibility, mobile breakpoint
- Rapid-click guard and loading state for demo API calls
- DemoMode flag propagated in all data events for consistent UI state

## 0.8.1
- Dashboard no longer stuck on "Lade Finanzdaten..." when no finance entities exist
- Restart notification no longer lost due to race condition in entry setup
- Prevent infinite loading spinner when no fd_ entities exist — data provider now always triggers initial rebuild
- Chore: add .playwright-mcp/ to .gitignore

## 0.8.0
- Decompose monolithic panel into 10 web components (fd-data-provider, fd-header, fd-stats-row, fd-stat-card, fd-household-section, fd-person-card, fd-category-section, fd-donut-chart, fd-cost-distribution, fd-recurring-list)
- Entity-first data strategy — fd-data-provider reads HA sensor/number/select entities, falls back to API for household+recurring
- Panel shell reduced from 507 lines to ~120 lines
- Coordinator force-refreshes transactions on first cycle — prevents stale cache showing 0,00 EUR
- Account settings API now persists `person` field for household assignment
- Monthly summary sensor exposes fixed_costs, variable_costs, household, recurring attributes
- Docs: ARCHITECTURE-FRONTEND.md added with component hierarchy, data flow, entity table, event system

## 0.7.8
- Graceful degradation for household model — exception no longer crashes coordinator
- Graceful degradation for recurring detection — failure yields empty list
- Graceful degradation for budget limit checks — log and skip on error
- Graceful degradation for event firing (balance + transaction) — never blocks data flow

## 0.7.7
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
- XSS protection for user-provided names

## 0.7.6
- Add DataUpdateCoordinator — entities no longer call banking API directly
- Sensor update interval 10 min via coordinator (was ~30 s per entity → rate-limit exhaustion)
- Panel refresh on connectedCallback + 10-min auto-timer instead of every hass setter
- Lovelace card throttles API calls to max once per 10 min (was every hass setter)
- Coordinator refreshes transactions only when cache is stale (>6 h), balances every 10 min
- Manual refresh_transactions service triggers coordinator push to entities


## 0.7.5
- Expose config entry to API views (entry key was never set)
- Auto-refresh transactions on HA startup (summary panel showed zeros)

## 0.7.4
- **Branch:** claude/upbeat-davinci
- **Changes:** feat(frontend): status chip replaces refresh button
- New `<finance-status-chip>` Lovelace component with 4 visual states (idle/loading/success/error)
- Panel header uses status chip instead of refresh button + dot indicator
- Register status chip JS as Lovelace extra module

## 0.7.3
- Fix setup wizard race condition — guard flag prevents wizard re-trigger during entry reload
- Fix account defaults in step 3 — merge existing settings into pending accounts

## 0.7.2
- Fix setup/complete merges new accounts with existing ones instead of replacing entry.data
- Fix dashboard refresh uses independent error handling per endpoint
- Fix manage accounts dialog retries 3x with 2s delay before showing error

## 0.7.1
- Fix settings overlay flash on load
- Fix balance data display in account cards

## 0.7.0
- Cascading transfer chain detection

## 0.6.15
- Gesamtsaldo uses actual bank balances from /balances API
- Settings gear icon in dashboard header for account management
- Manage-accounts overlay with rename, type change, person assignment
- New update_accounts endpoint and account details in setup/status

## 0.6.14
- Shimmer skeleton loaders replacing plain loading text
- Async refresh indicator (pulsing dot + timestamp)
- Responsive breakpoints for tablet and mobile
- Improved empty state with SVG icon and descriptive text

## 0.6.12
- HA user multi-select chips in step 3 instead of free-text person field
- Custom display name field per account
- New setup/users endpoint for HA user list

## 0.6.9
- Fix RepairsFlow calls homeassistant.restart service when user confirms
- Fix repair notification title says "Restart Required"
- Updated EN and DE translations for restart repair flow

## 0.6.5
- Fix retry logic and error handling for bank list API calls
- Fix graceful error handling when fetching supported banks fails
- Fix frontend error state with actionable feedback

## 0.6.4
- Fix credential return type breaking bank list loading (dict instead of tuple)

## 0.6.3
- Fix backend returns typed errors for differentiated frontend handling
- Fix frontend shows specific German error messages per error type
- Fix credential errors link to integration settings
- Fix 5-minute polling timeout in Step 2

## 0.6.2
- Fix restart marker poll outside is_configured, check on startup

## 0.6.1
- Fix 30s timeout for Enable Banking API, error state with retry button
- Rename "Finance Dashboard" to "Finance" everywhere

## 0.6.0
- Move bank setup from config flow to dashboard panel setup wizard
- Config flow reduced to credentials-only (1 step, config VERSION 3)
- 4-step setup wizard overlay in Finance sidebar panel
- 4 new setup API endpoints
- Config entry migration v2 to v3

## 0.5.5
- Fix granular Enable Banking API debug logging

## 0.5.2
- Fix config flow error handling for PEM key format errors vs API auth failures

## 0.5.1
- Fix PEM private key field renders as multiline textarea
- Remove deprecated arch values from companion add-on config
- Step-by-step Enable Banking setup instructions

## 0.5.0
- Migrate from GoCardless to Enable Banking API
- New EnableBankingClient with JWT RS256 signing
- Config flow v2 with migration handler

## 0.4.3
- Remove unused nordigen-python dependency (fixes 500 error on config flow)

## 0.4.2
- Fix sidebar panel not appearing (use correct panel_custom API)
- Fix repository.yaml format (remove non-standard channel field)

## 0.4.1
- Fix add-on not showing updates (add exec sleep infinity)
- Fix config.yaml missing fields (stage, options, schema, homeassistant_api)
- Add dark mode icon variants
- Switch to bashio structured logging
- Replace SVG brand assets with PNGs

## 0.4.0
- Benchmark auto-crawl with German national averages
- Drag & drop transaction categorizer
- CSV export service

## 0.3.0
- N-person household budget model
- Recurring transaction detection
- Income recognition with salary tolerance
- Bonus detection
- Budget Config Lovelace card

## 0.2.0
- GoCardless OAuth flow
- Account balance sensors
- Monthly summary sensor
- Privacy-first API

## 0.1.0
- Initial release
