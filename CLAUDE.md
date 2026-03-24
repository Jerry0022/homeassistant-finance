<!-- Inherits from ~/.claude/CLAUDE.md — do not duplicate global rules here -->
<!-- global-sync: 2026-03-24 -->

# Finance Dashboard — Home Assistant Integration

## Project Overview

A secure Home Assistant add-on and integration for personal finance management. Pulls live banking data via GoCardless (Nordigen) Open Banking API, auto-categorizes transactions, and provides household budget tracking with configurable multi-person split models.

## Architecture

```
homeassistant-finance/
├── custom_components/finance_dashboard/   # HA Integration
│   ├── __init__.py              # Setup, services, HTTP endpoints, restart polling
│   ├── manifest.json            # Integration metadata + dependencies
│   ├── config_flow.py           # Config + Options + Reconfigure flows
│   ├── const.py                 # All constants, categories, service names
│   ├── manager.py               # Core orchestrator (accounts, transactions, summaries)
│   ├── credential_manager.py    # Fernet encryption, token rotation, audit log
│   ├── gocardless_client.py     # GoCardless Bank Account Data API v2 client
│   ├── categorizer.py           # Rule-based transaction auto-categorization
│   ├── api.py                   # HTTP API endpoints (balances, transactions, summary)
│   ├── panel.py                 # Sidebar panel registration
│   ├── repairs.py               # Restart notification repair flow
│   ├── services.yaml            # Service definitions for HA
│   ├── strings.json             # UI strings (EN default)
│   ├── frontend/                # Web components (sidebar panel)
│   └── translations/            # i18n (en.json, de.json)
├── finance_dashboard_companion/           # HA Companion Add-on
│   ├── config.yaml              # Add-on metadata (version, arch)
│   ├── Dockerfile               # Alpine-based container
│   ├── run.sh                   # Smart payload installer (version-aware)
│   └── payload/                 # Bundled integration + Lovelace assets
├── www/community/finance-dashboard/       # Lovelace card (HACS install)
├── scripts/                               # Dev tooling
│   ├── bump_versions.py         # Sync versions across manifest/addon/const
│   └── sync_addon_payload.py    # Copy integration → add-on payload
└── .github/workflows/validate.yml         # CI: syntax + version + payload validation
```

## Security Model

**CRITICAL — Banking-Grade Security Requirements:**

1. **No financial data in git**: Zero runtime data (balances, transactions, account numbers, tokens) may ever be committed. The `.gitignore` enforces this.
2. **Encrypted storage**: All credentials use Fernet symmetric encryption (AES-128-CBC + HMAC) on top of HA's `.storage/` directory.
3. **Token rotation**: GoCardless tokens are refreshed 1 hour before expiry. Forced re-auth after 90 days.
4. **Session timeouts**: Credential access times out after 30 minutes of inactivity.
5. **Audit trail**: Every credential operation is logged (timestamp + event type only, never values).
6. **IBAN masking**: API responses truncate IBANs to last 4 digits for frontend display.
7. **Header security**: API endpoints require HA Bearer token authentication.
8. **No external calls**: Only GoCardless API is contacted. No telemetry, no analytics.

**Before every commit, verify:**
- `git diff --cached` contains zero financial data (account numbers, balances, tokens)
- No `.storage/` files are staged
- No `credentials.json` or `tokens.json` files are staged

## Tech Stack

- **Language**: Python 3.12+ (integration), JavaScript (frontend)
- **Banking API**: GoCardless (Nordigen) Open Banking API v2
- **Encryption**: `cryptography` library (Fernet)
- **Frontend**: Vanilla Web Components (Custom Elements API)
- **HA APIs**: Config Entries, Services, HTTP Views, Repairs, Frontend Panel
- **CI**: GitHub Actions (Python/JS syntax, version alignment, payload sync)

## Version Management

Three files must always have aligned versions:
1. `custom_components/finance_dashboard/manifest.json` → `version` field
2. `finance_dashboard_companion/config.yaml` → `version` field
3. `custom_components/finance_dashboard/const.py` → `VERSION` constant

Use `python scripts/bump_versions.py --part [patch|minor|major]` to bump all three atomically. The script also auto-syncs the add-on payload.

## Key Patterns (from Golden Sample)

### Companion Add-on
The add-on is a thin installer — it copies the integration code into HA's `custom_components/` directory. The `run.sh` script:
- Compares bundled vs installed version
- Only copies if versions differ
- Writes restart marker for integration to detect
- Falls back to persistent notification via HA Supervisor API

### Config Flow
Three-step flow: `user` (API credentials) → `link_bank` (bank authorization) → `options` (settings). Real-time validation with GoCardless API call during setup.

### Service API
Services exposed: `refresh_accounts`, `refresh_transactions`, `get_balance`, `get_monthly_summary`, `categorize_transactions`. All callable from HA automations.

## Commands

```bash
# Version management
python scripts/bump_versions.py --check        # Verify alignment
python scripts/bump_versions.py --part patch    # Bump version

# Payload sync
python scripts/sync_addon_payload.py            # Sync files
python scripts/sync_addon_payload.py --check    # Verify sync

# Validation (same as CI)
python -m py_compile custom_components/finance_dashboard/__init__.py
node --check custom_components/finance_dashboard/frontend/finance-dashboard-panel.js
```

## Development Phases

### Phase 1 (Current) — Scaffold + MVP
- [x] Repository structure mirroring YouTube Music Connector golden sample
- [x] GoCardless API client skeleton
- [x] Credential manager with encryption + audit
- [x] Transaction categorizer (rule-based)
- [x] Companion add-on with smart installer
- [x] Sidebar panel + Lovelace card
- [x] CI/CD pipeline
- [ ] End-to-end GoCardless OAuth flow
- [ ] Live data integration testing

### Phase 2 — Household Budget
- [ ] Multi-person model (N persons, configurable split)
- [ ] Auto-detection of recurring transactions (Fixkosten)
- [ ] Income recognition and split ratio calculation
- [ ] Budget split UI (Lovelace component)
- [ ] Historical comparison (month-over-month)

### Phase 3 — Analytics
- [ ] Spending trend analysis
- [ ] Category benchmarking (vs. German national averages)
- [ ] Savings goal tracking
- [ ] Recurring payment detection and alerts
- [ ] Export (CSV/PDF) — no financial data in git, only user-triggered downloads

## Labels

| Type | Prefix |
|------|--------|
| `type:feature` | `[FEATURE]` |
| `type:bug` | `[BUG]` |
| `type:security` | `[SECURITY]` |
| `type:refactor` | `[REFACTOR]` |

| Role | Scope |
|------|-------|
| `role:core` | Manager, API client, credential manager |
| `role:frontend` | Panel, Lovelace cards, web components |
| `role:security` | Encryption, audit, token management |
| `role:addon` | Companion add-on, Dockerfile, run.sh |

| Module | Scope |
|--------|-------|
| `module:gocardless` | Banking API integration |
| `module:categorizer` | Transaction categorization |
| `module:household` | Multi-person budget model |
| `module:frontend` | UI components |
| `module:addon` | Companion add-on |
