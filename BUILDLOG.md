# Build Log

## v0.7.0 — 2026-03-26
- **Build hash:** `7305434`
- **Branch:** claude/awesome-knuth
- **Changes:** feat(transfers): cascading transfer chain detection

## v0.6.15 — 2026-03-26
- **Build:** `b72a132`
- **Scope:** Real bank balances and settings overlay
- feat(frontend): Gesamtsaldo uses actual bank balances from /balances API instead of transaction sums
- feat(frontend): settings gear icon in dashboard header for account management
- feat(frontend): manage-accounts overlay with rename, type change, person assignment, connect new bank
- feat(api): new `update_accounts` endpoint and account details in `setup/status`

## v0.6.14 — 2026-03-26
- **Build:** `98bfa58`
- **Scope:** Dashboard loading UX and mobile responsiveness
- feat(frontend): shimmer skeleton loaders replacing plain loading text
- feat(frontend): async refresh indicator (pulsing dot + timestamp) — old data stays visible
- feat(frontend): responsive breakpoints for tablet (≤900px) and mobile (≤480px)
- feat(frontend): improved empty state with SVG icon and descriptive text

## v0.6.12 — 2026-03-26
- **Build:** `86c41b8`
- **Scope:** HA user assignment and custom account names in setup wizard
- feat(setup): Step 3 offers HA user multi-select chips (n:m) instead of free-text person field
- feat(setup): custom display name field per account
- feat(api): new `GET /api/finance_dashboard/setup/users` endpoint for HA user list
- feat(sensor): new fields propagated through manager, sensor attributes, and transaction tagging

## v0.6.9 — 2026-03-26
- **Build:** `94a283c`
- **Scope:** Repair flow now triggers actual HA restart
- fix(addon): RepairsFlow calls `homeassistant.restart` service when user confirms
- fix(addon): repair notification title says "Restart Required" instead of "Update Available"
- fix(addon): updated EN and DE translations for restart repair flow

## v0.6.5 — 2026-03-25
- **Build:** `35a8905`
- **Scope:** Fix bank list loading error in setup wizard
- fix(setup): add retry logic and error handling in EnableBanking client for bank list API calls
- fix(config_flow): graceful error handling when fetching supported banks fails
- fix(panel): frontend error state with actionable feedback for bank list loading failures
- fix(api): improved error response handling for bank list endpoint

## v0.6.4 — 2026-03-25
- **Build:** `38778e0`
- **Scope:** Fix credential return type breaking bank list loading
- fix(credentials): return dict from async_get_api_credentials instead of tuple
- Callers in api.py and manager.py expected dict-style access; tuple caused TypeError swallowed by exception handlers

## v0.6.3 — 2026-03-25
- **Build:** `0c2dbc4`
- **Scope:** Improve setup wizard error handling and UX
- fix(panel): backend returns typed errors (error_type) for differentiated frontend handling
- fix(panel): frontend shows specific German error messages per error type
- fix(panel): credential errors link to integration settings instead of retry
- fix(panel): 5-minute polling timeout in Step 2, cancel button to return to Step 1

## v0.6.2 — 2026-03-25
- **Build:** `77a8500`
- **Scope:** Fix restart repair notification not appearing
- fix(repairs): move restart marker poll outside is_configured, check on startup, remove persistent notification fallback

## v0.6.1 — 2026-03-25
- **Build:** `b48cbc3`
- **Scope:** Fix infinite spinner in bank setup wizard + branding rename
- fix(panel): add 30s timeout to Enable Banking API, error state with retry button (#32)
- fix(branding): rename "Finance Dashboard" to "Finance" everywhere (#31)

## [v0.6.0] 2026-03-25 — 670ccb3
Version: 0.6.0
Branch: claude/zealous-shannon
PR: #30
Commit: 670ccb3
Changes:
- Move bank setup from config flow to dashboard panel setup wizard
- Config flow reduced to credentials-only (1 step, config VERSION 3)
- New 4-step setup wizard overlay in Finance sidebar panel
- 4 new setup API endpoints (status, institutions, authorize, complete)
- Fix Enable Banking API: authorization_id field, nested IBAN, UUID state
- Fix panel registration: StaticPathConfig with cache, correct unregister
- Config entry migration v2→v3 preserves existing setups

## [v0.5.5] 2026-03-25 — 000de4a
- fix(logging): granular Enable Banking API debug logging

## d66a1c2 — 2026-03-25
Branch: fix/config-flow-pem-multiline
PR: #25
Commit: 504e942
Changes:
- Use multiline TextSelector for PEM private key field in config flow
- Synced addon payload with latest config_flow and translation changes

## 456ec0c — 2026-03-25
Branch: fix/addon-deprecated-arch
PR: #24
Commit: ea4dbf0
Changes:
- Remove deprecated arch values (armhf, armv7, i386) from companion add-on config
- Update add-on description from GoCardless to Enable Banking

## 3a525f7 — 2026-03-25
Branch: claude/nostalgic-poitras
PR: #23
Commit: 3c4a832
Changes:
- Add step-by-step Enable Banking setup instructions to config flow
- Show dynamic redirect URL in setup dialog
- Updated EN + DE translations

## eb7ef69 — 2026-03-25
Version: 0.5.0
Branch: claude/wonderful-leakey
PR: #22
Commit: 3bf932d
Changes:
- Migrate from GoCardless to Enable Banking API
- New EnableBankingClient with JWT RS256 signing
- RSA PEM key storage + session management
- Config flow v2 with migration handler
- Updated UI strings (EN + DE)

## c4851d1 — 2026-03-25
Version: 0.4.3
Branch: claude/vibrant-swirles
PR: #21
Commit: 0edd268
Changes:
- Remove unused nordigen-python==2.1.0 dependency from manifest.json
- Fix 500 Internal Server Error when adding integration via config flow

## f83c141 — 2026-03-25
Version: 0.4.2
Branch: claude/determined-goldwasser
PR: #20
Commit: f83c141
Changes:
- Fix sidebar panel not appearing after installation (use panel_custom API)
- Fix repository.yaml format (remove non-standard channel field)
- Add addon CHANGELOG.md

## 255c9f2 — 2026-03-24
Version: 0.4.1
Branch: claude/confident-neumann
PR: #19
Commit: 64e8d3b
Changes:
- Fix companion add-on not showing updates (missing sleep infinity)
- Add missing config.yaml fields (stage, options, schema, homeassistant_api)
- Replace SVG brand assets with PNGs, add dark mode variants
- Switch to bashio logging, add post-copy verification
- Add generate_branding_assets.py script

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
