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

Home screen (`api/home.py`, `home.py`, `pots.py`, `cycle.py`):

- `GET /home?horizon=today|week|cycle|year&view=person|household[&demo=1]` - cache read only, never a
  bank call. The person comes from the logged-in HA user (account `ha_users`), never from a
  parameter; without a mapping `view=person` degrades to `household`. Household view shows shared
  pots in full and every person only as totals (`persons[]`). Contract: see
  `docs/concepts/20261027-2210-finance-visual-round/briefs/home-api-contract.md`.
- `POST|PUT|DELETE /pots` - pot CRUD. Admins manage every pot; other users only their own
  personal pots (also checked against the existing owner on update/delete, so a pot cannot be
  taken over). Ids are server-generated on create. Pots are stored in `.storage/finance_dashboard_pots`.
- `GET|PUT /assignments` (`api/assignments.py`, admin only, 403 `admin_required`) - the "Personen & Konten"
  settings. GET returns `persons` (name + `ha_users`), `ha_users` (id, name, is_admin, `suggested`,
  `reason` person|active_user|system|inactive), `accounts` (`key`, name, institution, `iban_last4`,
  `owner` person|shared|"") and `plan_persons`. PUT takes `{persons, accounts:[{key, owner}]}`,
  validates (unique names <= 40 chars, existing HA users, one person per user, owner shared or a
  person, known account keys; else 400 `{error, detail}`), stores `persons` in the config entry and
  writes `type`/`person`/`ha_users` onto the accounts (user-owned fields, kept on bank re-link).
  `/home` carries `setup {persons, user_mapped, accounts_total, accounts_assigned, pots}`.
- Demo mode (`manager.demo_mode`, or `demo=1`) serves the same payload from invented data
  (`demo.generate_demo_home`).
