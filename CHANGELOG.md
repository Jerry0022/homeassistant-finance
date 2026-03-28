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

### Fixed
- Add DataUpdateCoordinator — entities no longer call banking API directly
- Sensor update interval 10 min via coordinator (was ~30 s per entity → rate-limit exhaustion)
- Panel refresh on connectedCallback + 10-min auto-timer instead of every hass setter
- Lovelace card throttles API calls to max once per 10 min (was every hass setter)
- Manual refresh_transactions service triggers coordinator push to entities
