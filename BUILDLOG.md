# Build Log

## v0.6.1 — 2026-03-25
- **Build:** `918fb98`
- **Scope:** Branding rename — "Finance Dashboard" → "Finance" across all user-visible strings

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
