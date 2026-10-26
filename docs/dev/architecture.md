# Architecture

Read this before touching the manager, storage, config flow, API or frontend.

## Layout

```
custom_components/finance_dashboard/
├── __init__.py            # Setup, services, restart handling, daily scheduled refresh
├── config_flow.py         # `user` (application id + key), BankSubentryFlow, reconfigure, options
├── connect.py             # Bank connect: PSU redirect via my.home-assistant.io, code exchange
├── const.py               # All constants, categories, service names
├── runtime.py             # Per-entry runtime data
├── manager/               # Orchestrator: __init__ (cache reads), _refresh, _persistence, _banks
├── fetch_budget.py        # Per-bank fetch budget (pure logic, injectable time)
├── data_store.py          # Encrypted two-layer storage (raw archive + ledger)
├── balances.py / balance_statistics.py   # Balance series, long-term statistics import
├── account_identity.py    # IBAN-based account key (see CLAUDE.md hard rule)
├── enablebanking_client.py, credential_manager.py   # API client (JWT RS256), Fernet + audit
├── coordinator.py         # DataUpdateCoordinator, cache-only reads
├── entity.py, sensor.py, button.py, number.py, select.py   # Entities and devices
├── diagnostics.py, repairs.py, events.py, panel.py
├── categorizer.py, recurring.py, transfer_detector.py
├── budget_plan.py, spreadsheet_import.py, transfer_plan.py, household.py, benchmark.py
├── api/                   # HTTP views: data, plan, refresh, demo, _helpers
└── frontend/              # One web-component kit, panel + cards
```

## Config flow

1. `user`: Enable Banking application id + RSA private key, validated live.
2. Banks are added as **config subentries** (`BankSubentryFlow`, `connect.py`): ASPSP choice, PSU
   redirect through `my.home-assistant.io`, code exchange, test call, account assignment
   (personal vs. shared).
3. Reconfigure flow (credentials) and options flow (daily refresh, `show_household`, retention, ...).

## Refresh and rate limit (per bank)

`fetch_budget.py` holds the budget per bank (ASPSP), never global:
- Background calls (no PSU headers) are counted per account per UTC day; the scheduled daily
  refresh may use at most `SCHEDULED_BACKGROUND_SHARE` of the limit.
- Attended calls (PSU headers from a real request) are uncapped, never gated on a block, only
  debounced (`ATTENDED_DEBOUNCE_SECONDS`).
- A 429 blocks that bank's background access for `RATE_LIMIT_BACKOFF_HOURS` (6h); other banks are
  unaffected. State is persisted across restarts.

Flow: refresh button / panel open / service -> `POST /api/finance_dashboard/refresh` ->
`manager.async_refresh_transactions()` (lock-guarded) -> balances + transactions per bank in one
round -> stats written to cache -> coordinator pushes to entities -> endpoint returns
`{ok, status}`. Cache-read endpoints (`/balances`, `/transactions`, `/summary`, `/refresh_status`)
never hit the bank.

## Storage

`data_store.py`: every store is HA `Store` with a Fernet-encrypted payload (key from the credential
manager), versioned with a migrate hook.
- **Raw layer**: every bank response unaltered, immutable snapshots, one store per month, pruned by
  retention. Audit trail and source for re-deriving.
- **Ledger layer**: processed, deduplicated per-account transactions and balance time series.
  Categories, summaries and splits are derived, never stored here.

## Entities and devices

One device per bank and per account (`entity.py`). Per account: balance, available balance,
last-update sensors (`sensor.py`). Per bank: consent valid-until, consent state, budget used,
blocked-until, last error, plus a refresh button (`button.py`). Aggregates: total balance, monthly
summary. Balance history is imported as long-term statistics (`balance_statistics.py`).
`diagnostics.py` redacts financial data. See `entities-and-services.md`.

## Frontend

One kit (`finance-dashboard-kit.js`, `fd-*` components), see `docs/ARCHITECTURE-FRONTEND.md`.
- Sidebar panel via `panel_custom`, admin-only (`panel.py`).
- Cards auto-loaded through `frontend.add_extra_js_url`, no manual resource entry.
- Panel tabs: facts **Overview**, and **Household** (only when option `show_household` is on).

## Distribution

HACS only (`hacs.json`). There is no companion add-on and no payload sync.
