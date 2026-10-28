# Contract: household summary per cycle

`GET /api/finance_dashboard/household_summary?cycle=current|previous[&view=person]`

Cache read, any authenticated user, never a bank call. 400 on an unknown `cycle`, 404 when not configured.
Code: `household_summary.py` (pure), `api/household.py` (view), `manager.get_household_summary`.
`/summary` stays for backwards compatibility; the panel's Household KPI numbers should come from here.

## Semantics

All amounts are positive magnitudes in EUR: `surplus = income - expenses`.

Not counted: own-account transfers (chains with only source+destination legs: both legs; chains with intermediate legs: only the source leg counts, once; user-rejected chains count normally), bookings categorised `transfers`, PayPal funding debits on other accounts when a PayPal account is linked (PayPal's own lines are the truth), pending lines. Refunds (`_refund_role == "refund"`) are netted against expenses, not income.

Ownership of an expense: account owner (person / `shared` / `open` = unassigned) -> matched plan position owner -> user correction (`manager._owner_corrections`: `{transactionId: owner}`; hook only, nothing writes it yet). Fixed = recurring series (negative `detect_recurring` pattern by creditor) or plan position of kind `fixed`; the rest is variable. Income is attributed to the account owner.

## Payload

```
cycle: { label: "Zyklus", selected: "current"|"previous", start, end, day, days,
         rule: "household_7_day"|"calendar_fallback", anchor: person|null,
         previous_start, previous_end }          # the comparison cycle (null = unknown)
income, expenses, surplus, fixed, variable       # selected cycle
savings_rate: number|null                        # (income-expenses)/income; null while income == 0
income_pending: bool                             # known recurring income still due in this cycle (current only)
expected_income_date: "YYYY-MM-DD"|null
lines: { income|expenses|fixed|variable|surplus|savings_rate: { current, previous, delta } }
                                                 # previous/delta null when no comparison cycle
owners: [ { owner, kind: person|shared|open, restricted, income, expenses, surplus, previous_expenses,
            fixed?, variable?, categories?: [{category, amount}] } ]
privacy: "full"|"restricted", as_of
```

UI rule: show `savings_rate: null` as "-" (never -786 %); with `income_pending` show "Gehalt erwartet am <date>".

## Visibility

No endpoint returns booking lists. `privacy: "full"` only for admins (without `view=person`). Otherwise persons other than the viewer's resolved person have `restricted: true` and only `income/expenses/surplus/previous_expenses` (no fixed/variable split, no categories). Household totals and `shared` rows are visible to everyone. A non-admin without person mapping sees all persons restricted.

## Known limits

- The cycle end is projected from the typical salary interval; a recurring salary due after that end is not `income_pending` (it opens the next cycle).
- Plan matching is name-token based (same as plan-vs-actual); the positions' month is the booking's calendar month.
