# Entities, services, events

Read this before adding or changing entities, services, events or HTTP endpoints.

## Entities

- Devices: one per bank, one per account (`entity.py`).
- Sensors per account: balance (with bank logo, IBAN masked), available balance, last update.
- Sensors per bank: consent valid-until, consent state, budget used, blocked-until, last error.
- Button per bank: refresh (attended path).
- Aggregates: `total_balance` (optional), `monthly_summary`; per-person budget sensors.
- Number per category: budget limit. Select: split model.
- Unique ids go through `account_identity.py` (IBAN-based), never the raw uid.
- Balance history is imported as long-term statistics (`balance_statistics.py`).

## Services (see `services.yaml`)

`refresh_accounts`, `refresh_transactions` (both return refresh stats via
`SupportsResponse.OPTIONAL`), `get_balance`, `get_monthly_summary`, `categorize_transactions`,
`set_budget_limit`, `export_csv`, `toggle_demo`, `import_spreadsheet` (admin-only, path checked
against `allowlist_external_dirs`), `get_transfer_plan`, `set_cost_position`,
`delete_cost_position`, `reprocess_data` (admin-only; rebuilds the ledger from the raw archive, no
bank call, returns rebuild stats). `refresh_transactions` is the only live-fetch entry point and
updates balances + transactions + recurring in one round.

## Events

`fd_transaction_new`, `fd_balance_changed`, `fd_budget_exceeded`, `fd_recurring_detected`.

## HTTP endpoints (`api/`, all require HA auth)

Cache reads: `/balances`, `/transactions`, `/summary`, `/refresh_status`, bank status, settings.
Live: `/refresh`. Plan: `/budget_plan`, `/transfer_plan`, `/plan_vs_actual`, `/benchmark`, plan
position/income/import. Demo: toggle + data. IBANs are truncated to the last 4 digits.
