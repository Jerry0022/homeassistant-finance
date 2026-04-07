# Build Log

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
