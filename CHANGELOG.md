# Changelog

All notable changes to the Finance Dashboard will be documented in this file.

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

### Added
- Initial project scaffold
- GoCardless (Nordigen) Open Banking API client
- Secure credential management with Fernet encryption
- Auto-transaction categorization (rule-based)
- Companion add-on with smart payload installer
- Sidebar panel (web component)
- Lovelace card for dashboard integration
- Config flow with GoCardless API setup
- German and English translations
- Version management scripts (bump + sync)
- GitHub Actions CI/CD pipeline
- Maximum security: token rotation, session timeouts, audit log
