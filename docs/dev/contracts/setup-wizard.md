# Contract: setup wizard, payday, pot suggestions, exceptions, member access

Modules: `setup_wizard.py` (state + pure logic), `api/setup.py` (endpoints), `notify.py`
(exceptions + digest), `api/_helpers.py` (`is_admin`, `admin_denied`, `visible_account_ids`),
`panel.py`. Everything is a cache/config read; no bank call.

## Wizard state

Own HA Store `finance_dashboard.setup_wizard` (no config-entry update, no reload). Steps:
`persons, accounts, payday, pots, plan, notifications, ai, done`. Status per step:
`pending|done|skipped`. Skippable: payday, pots, plan, notifications, ai. A `pending` step is
reported `done` when the data already proves it (persons exist; all accounts assigned; every
person has a confirmed payday; at least one pot) - that is the resume rule. `current_step`
is the first unresolved step, `done` once `complete: true` was stored.

`GET /api/finance_dashboard/setup` (admin) ->
`{current_step, steps{}, completed, ai_opt_in, notifications{}, persons[{name, payday}]}`

`PUT /api/finance_dashboard/setup` (admin), all keys optional:
`{step, status, complete, ai_opt_in, notifications{...}, paydays[{person, day 1-31}]}` ->
same payload as GET. Errors 400 `{error, detail}`: `unknown_step, invalid_status,
not_skippable, invalid_ai_opt_in, unknown_notification_setting, invalid_notifications,
invalid_complete, invalid_paydays, unknown_person, invalid_payday`.
`ai_opt_in` is stored only; the AI categoriser is not wired to it here.

Notification settings (defaults): `enabled true, large_debit true, large_debit_factor 3.0,
large_debit_threshold 500.0 (0 = absolute rule off), double_charge true, missing_salary true,
consent_expiring true, digest_enabled true`.

## Payday

Stored on the person record: `entry.data["persons"][i]["payday"] = {"day": int, "confirmed": true}`.
`manager.async_set_assignments` now carries an existing payday over (one small edit) so saving
assignments never drops it.

`GET /setup/payday_suggestions` (admin) -> `{suggestions: [{person, confirmed_day,
suggested_day, source, amount}]}`: largest recurring credit (via `detect_recurring`) on the
person's own accounts. The user confirms via `PUT /setup {paydays: [...]}`.

Cycle rule (not changed, `home.py` is not mine): `setup_wizard.person_payday(person)` returns the
confirmed day or None; `setup_wizard.payday_cycle(day, today)` returns the window containing
today (day clamped to month length). Intended use in `home.build_home` person view: if the
person has a confirmed payday use `payday_cycle`, else keep `person_cycle(incomes)` and the
calendar fallback. Persons without payday behave exactly as before. `notify.detect_missing_salary`
already prefers the confirmed payday.

## Pots from history

`GET /setup/pot_suggestions` (admin) -> `{suggestions: [{owner, category, name, cycle_budget,
samples}]}`. Per owner x category: median of the last 3 completed cycles (salary-start windows,
falling back to the 3 previous calendar months), only cycles with spend count, >= 2 samples,
rounded to 10 EUR (min 10). Excluded: income, transfers, other, and fixed-cost categories
(housing, insurance, loans, subscriptions - those belong in the plan), and owner+category pairs
already covered by an existing pot.

`POST /setup/pot_suggestions` (admin) body `{accept: [{category, owner, cycle_budget, name?}]}`
-> 201 `{ok, pots}`; creates pots via `manager.async_save_pot` (all validated first).

## Exceptions and digest

Run from the daily refresh (`__init__._register_daily_refresh`, after the consent-issue update)
through `notify.async_after_refresh`; never raises; skipped in demo mode and when
`notifications.enabled` is false. Each exception is delivered once (hashed id kept 60 days).

Event `finance_dashboard_exception`: `{kind, person, merchant, amount, date}`.
`kind`: `large_debit | double_charge | missing_salary | consent_expiring | consent_expired`.
`person` = account owner or `"shared"` (automations route on it). `amount` is rounded absolute
(null for consent) - allowed because `events.py` events carry amounts. No IBAN/account number.
The `persistent_notification` is visible to all HA users, so it is generic: kind + person, and
the merchant only for shared items; never amounts.

Event `finance_dashboard_weekly_digest`: `{week, status, top_changes[{category, delta}],
questions_open, text}` once per ISO week + persistent notification `finance_dashboard_digest_<week>`.
Household level only. Text is English.

## Endpoint visibility (panel is now `require_admin=False`)

| Endpoint | Admin | Non-admin member |
|---|---|---|
| `GET /home` | yes | 200, own person view (person from the login) / household with other persons as totals |
| `/pots` POST/PUT/DELETE | any | own personal pots only (existing) |
| `GET /transactions` | full | 200 aggregates only (existing) |
| `GET /summary` | yes | yes (monthly category aggregates, no merchants) |
| `GET /balances` | all accounts | own + shared accounts only (NEW: `visible_account_ids`); unmapped member: shared only; unassigned accounts hidden |
| `GET /bank_status`, `/refresh_status`, `/settings` | yes | yes (no IBAN, no values) |
| `GET /budget_plan` | full | shared positions only (existing, `restricted: true`) |
| `GET /plan_vs_actual` | full | 200 `restricted` stub (existing) |
| `/budget_plan/position`, `/income`, `/import` | yes | 403 (existing) |
| `GET /transfer_plan`, `GET /benchmark` | yes | 403 (NEW gate, per-person plan data) |
| `/transfer_chains` GET/POST | yes | 403 (existing) |
| `/assignments` GET/PUT | yes | 403 (existing) |
| `/refresh` POST, `/demo/toggle` | yes | 403 (existing) |
| `/demo/data` | yes | yes (synthetic data) |
| `/setup`, `/setup/payday_suggestions`, `/setup/pot_suggestions` | yes | 403 |

## Open points

- `GET /budget_plan` for members still returns whatever else is in the view besides `positions`
  (e.g. per-person income totals); not audited in depth - another agent owns the plan model.
- `home.py` does not yet consume `payday_cycle` (not my file).
- The frontend must tolerate 403 on `/transfer_plan` and `/benchmark` for members (check `/settings.is_admin`).

## Region (benchmark comparison)

`GET /setup` also returns `region: {state, postcode}` (from the entry options
`benchmark_state` / `benchmark_postcode`). `PUT /setup` accepts
`{"region": {"state": "DE-RP" | "RP", "postcode": "56179"}}` — state is a
two-letter code with optional `DE-` prefix, postcode optional and 5 digits;
anything else returns `400 invalid_region`. The frontend shows Region as its own
screen between Zahltag and Töpfe; it has no backend step status.

## Backend additions (plan prefill, goals, points, AI, nicknames)

All admin only, cache/config only. Errors are 400 `{error, detail}` unless noted.

- `GET /setup` and `PUT /setup` now also carry `points_target` and `persons[].display_name`
  (falls back to `name`). `PUT /setup {nicknames: [{person, display_name}]}`; empty clears.
  `name` stays the stable key (accounts, pots, plan, rules); only the display text changes.
  `/assignments` GET returns `persons[].display_name`; PUT accepts `display_name` per person and keeps
  the stored one when omitted. Errors: `unknown_person`, `invalid_display_name`, `invalid_nicknames`.
- `GET /setup/plan_prefill` -> `{proposals: [{series_id, name, owner, category, interval, amount,
  plan_mode, already_in_plan}]}` (amount = monthly equivalent, plan sign, owner `shared` or a person).
  `POST` `{accept: [{series_id, name?, owner?, amount?, category?}]}` -> 201 `{ok, created, skipped}`;
  existing plan positions are never overwritten (`skipped` ids). Errors: `invalid_body, unknown_series,
  unknown_owner, invalid_amount, invalid_name, duplicate, too_many`, `demo_mode`.
- `GET /setup/goals` -> `{goals}`; `POST` goal -> 201 `{ok, goal}`; `DELETE /setup/goals/{id}` -> `{ok}` / 404.
  Goal kinds: `target_by_date {target_amount, target_date}`, `category_cap {category, cap_amount}`,
  `savings_rate {rate_percent}`, `reserve_topup {reserve_id, monthly_amount}`; all take `name`, `owner`.
  Readers: `savings_goals.async_get_goals(hass)`.
- `GET/PUT /setup/points` `{entity_id}` (`counter.*` / `input_number.*`, "" clears) -> `{entity_id, event,
  every, answered_total}`. Errors `invalid_entity, unknown_entity`. Finance keeps no points ledger.
- `GET/PUT /setup/ai`: PUT any of `provider (ha|xai|anthropic|openai), model, ha_agent, budget_cap (0-100),
  api_key (write-only, "" removes), ai_opt_in`. Response: `{opt_in, provider, model, effective_model, ha_agent,
  has_key, budget {month, calls, cap, hard_cap, remaining}, cached_merchants, providers[]}`. The key is
  Fernet-encrypted (credential manager) in the `finance_dashboard.ai_provider` store and never returned.
  `ai_provider.async_categorize(...)` is the entry point for the categoriser (not wired into the pipeline yet).
