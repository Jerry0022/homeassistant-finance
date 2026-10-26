# Product concept

Read this before planning features, the panel, cards or notifications. It records what Finance is
for and which interactions it supports, as decided with the household in the concept rounds of
2026-10-26 (the interactive decision pages were not kept in the repo). Visual design is out of
scope here; see `visual-round-handoff.md`.

## Purpose

Finance answers one question first: **"Are we on plan — and is there anything we need to do?"**
The plan is the front door; bank data confirms or contradicts it. Categories and bookings are
drill-downs, not the main screen.

Not in scope: payments or transfers, investments / net worth, gamified pressure, pretending to be
real-time, blaming a person for spending.

## Jobs to be done

1. Before spending: a trustworthy *free to spend* figure, without opening banking apps.
2. When money moves unexpectedly (large debit, double charge, price increase, missing salary): be
   told once, briefly.
3. At cycle close: plan vs. actual per position and per person, plus the settle-up.
4. Before a contract renews or an annual bill lands: know it and whether it is covered.
5. For the less finance-minded partner: a one-glance answer in plain words.
6. When planning: compare with similar households.

## Rhythms

| Rhythm | What happens |
|---|---|
| Glance | Status, *free to spend* = remaining variable plan budget of the period, next debits, freshness stamp ("as of 06:30"), pending shown apart |
| Week (calendar week) | Weekly digest + review inbox (max. 10 items per week, highest euro impact first; owner first, then category) |
| Cycle (salary cycle) | Planning unit. A calendar week crossing payday is split pro rata by days. Cycle close: plan vs. actual, settle-up, plan-adjustment prompts |
| Year | Contracts, annual cost, benchmark comparison, plan revision |
| Event | Exceptions only (consent expiring, unusual debit, projected shortfall), routed to the person concerned |

Not chosen for now: voice answers, tax export.

## Household and privacy

- N persons supported; presentation optimised for two.
- Joint accounts and the plan are fully visible to all members; personal accounts show totals only
  to the others. Sensors expose aggregates only (the HA recorder is outside the Fernet boundary).

## Ownership (mine / yours / ours)

1. Every account belongs to person A, B (… N) or *shared* — the default owner of its bookings.
2. A matched plan position overrides the account default.
3. A user decision overrides both, and can be saved as a rule for the recurring bookings it matches.

## Data truth

Pipeline: ingest (raw archive) → normalise (merchant key, remittance tokens) → link → enrich
(category, owner, series) → aggregate (period, plan position) → surface (sensors, inbox, digest).

- Links detected automatically, always visible and undoable: own-account transfers (IBAN),
  PayPal mirror (the PayPal line is the spend, the bank debit is funding), true duplicates,
  refunds/reversals, several bookings that are one purchase (merge as a suggestion), credit-card
  settlement.
- PayPal details are attached to the bank booking **before** any rule or AI step.
- Corrections offer a reach (this booking / merchant / remittance pattern, merchant preselected).
  Default tolerances ±20 % amount and ±5 days date, adjustable per rule and per series.
- Reprocessing on a new processing version: yes. User corrections survive every rebuild; changed
  closed periods appear only as a hint in the report log.

## AI categorisation

Opt-in. Order: rules → learned merchant memory → AI for unknown merchants only. Payload: merchant +
remittance text, never amount, IBAN or date. Results cached per merchant permanently. Hard cap
100 calls per month. Provider: Home Assistant's own AI functions first (AI Task / conversation
agents the user already configured); otherwise an own API key for a fixed set (Grok, Claude,
ChatGPT).

## Points

Finance does not keep points. It fires an HA event / increments a counter helper; the household's
existing points system books it. Rule: 30 answered review-inbox questions = 1 point (≈ 15 fully
classified bookings) for the person who answered, regardless of whose booking it was. Fully
automatic, deletable only by the recipient, never grantable via a button; a merchant-wide rule
counts once. The household's points budget stays separate; Finance only recognises its bookings as
a booking class by remittance text.

## Contracts and subscriptions

- Series of any interval, with expected date and amount, *missing* state, price-change detection,
  link to a plan position, annual cost.
- Plan amount of a series: default **highest value**; per plan position switchable to average,
  last, median or a fixed value — applied the same across intervals, never edited by hand.
- Contract model, all prefilled: start, minimum term, renewal, notice period with unit and
  reference (end of term / end of month), defaults per category, reminder to the contract owner.
- Special termination after a price increase only when the increase is not implicit in the
  contract: a checkbox prefilled from the detected pattern (even payments → checked; differing in
  at least 2 of 3 cases → unchecked).

## Benchmarks

- Germany fixed, federal state selectable, postcode asked in the setup wizard (prefilled from the
  HA location). Each comparison uses the finest available level: postcode → district → state →
  country. Nothing location-specific in this public repo.
- Dimensions: rent per m², electricity (kWh and €), heating (district heating, gas, oil, heat
  pump), food, mobility, insurance, communication/subscriptions, debt ratio, savings rate,
  equivalised income, Bürgergeld Regelbedarf as a floor.
- Median where published, otherwise mean — always labelled with statistic, source and year.
- A bundled, versioned dataset; sources from a fixed allowlist kept in this repo (official
  statistics and recognised bodies only). No runtime fetch.

## Goals and reserves

- Savings hints are evidence-based (price increase, double subscription, above the benchmark
  median, unused contract) and neutral — never addressed at a person.
- Goals: amount by date, category cap, savings rate, reserve top-up, dynamic suggestion.
- Annual and irregular costs become monthly reserves in the plan. Accounts can be marked as
  savings accounts. **Virtual pots** split one account into pots that behave like separate
  accounts (full feature set; the view can switch back to the real account). The pots together should
  always cover the real account position on both sides; a shortfall warns and names the top-up
  amount. Pots may finance ad-hoc spending.

## Setup wizard

Runs until completed once (every step confirmed): persons, accounts → owner, postcode/state,
payday per person, plan prefilled from history (detected series), notifications and digest, AI
(opt-in, provider, budget), savings goals, connect the points system.

## Impact on the codebase (as of 2026-10-26)

- `benchmark.py` crawls at runtime → replace with the bundled dataset.
- `recurring.py` detects monthly series only (±10 %) → any interval, configurable tolerances.
- `categorizer.py` is keyword-only → rules + learned merchant memory + optional AI tail.
- `month_cycle.py` exists but is not wired → salary cycle.
- Panel is admin-only → non-admin household view per the privacy rule.
