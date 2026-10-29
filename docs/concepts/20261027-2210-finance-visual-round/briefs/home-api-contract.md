# Home API contract (final, W1 -> W2)

`GET /api/finance_dashboard/home?horizon=today|week|cycle|year&view=person|household[&demo=1]`

Follows `impl.md` § Backend contract; this file lists the **final** fields including additions.
Cache read only. Plan sign (expense positive). The person is derived from the logged-in HA user;
if no person maps to the user, `view=person` is answered as `view="household"` with `person: null`
(check `view` in the response, not the request). `demo=1` (or manager demo mode) serves invented data;
without a configured manager only `demo=1` works (otherwise 404).

Always present: `view`, `person` (`{id,name}`|null), `horizon`, `freshness` (`{as_of, status: fresh|stale|error}`),
`alerts` (`[{id, severity: info|warn, kind, title, actions:[{id, bank_id}]}]`; `kind`: `consent_expiring`,
`consent_expired`, `bank_error`, `bank_limit`; `title` = bank name, the frontend words the alert), `questions_open`,
`cycle` (`{start, end, days, day, anchor, rule}`; `rule`: `person_highest_income` | `household_7_day` |
`calendar_fallback`; show anchor/rule only behind the info button), `status` (`good|knapp|over`),
`remaining` (sum of spend-pot balances in scope, can be negative), `pots`.

`pots[]` (spend pots visible in this view; person view: own personal pots, household view: shared pots):
`{id, name, owner ("shared" | person name), balance, per_day, status, kind, cycle_budget, spent, carry_in_week, category_keys}`.
Reserve pots are returned in `reserves[]` instead (`{id,name,owner,balance,per_day,cycle_budget,kind}`).

Household view only: `persons[]` = `{id, name, budget, spent, balance, status}` per person - totals only,
never pot names, merchants or bookings of a person.

Per horizon:

- `today`: `today: {spent, daily_budget, can_spend}` (`can_spend = max(0, remaining)` - the "what can I still spend" number).
- `week`: `week` = `{start, end, daily_budget, carry_over, week_budget, spent, remaining, days[], linear_line[7], zero_carry_line[7], upcoming}`.
  `days[]` = `{date, budget, actual, future, today, in_cycle}` (Mon-Sun; days outside the cycle have budget 0).
  `carry_over` only counts earlier days of the current cycle. `week_budget = max(0, carry_over + daily_budget * days_in_cycle)`.
  `linear_line`: cumulative allowance per day incl. carry-over (solid Soll line). `zero_carry_line`: the same
  without carry-over (thin dashed line); flat `0` when the carry-over leaves nothing for the week.
  `upcoming` = `{sum, count, items[top 3]}` with items `{date, label, amount, pending, category}` (pending = "vorgemerkt").
- `cycle` and `year`: `next` (top 3 of `{date,label,amount,pending}`) + `next_total` (for "mehr anzeigen"),
  `did_you_know` (`null` | `{key, params, text}`; rule-based, `text` is English fallback), `reserves`,
  `fixed_costs_covered` (`bool|null`; null without a budget plan).
- `year` adds `year: {cycles[{start,end,status,current}], vs_last_year{available, spent, spent_last_year, delta}, benchmark{available:false, reason}}`
  (`benchmark` is the marked placeholder for inflation/purchasing power comparison, no runtime fetch).

Pot CRUD: `POST /pots` (create, body `{name, owner, cycle_budget, category_keys[], kind}` -> 201 `{ok, pot}`),
`PUT /pots` (body incl. `id`), `DELETE /pots?id=`. 403 when a non-admin touches shared or foreign pots; 400 on invalid input.
