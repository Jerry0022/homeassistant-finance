# Household model

Read this before touching split logic, month cycles, income or bonus detection.
Note: Phase 4 (see `roadmap.md`) replaces the hard-wired 2026 spreadsheet model with building
blocks; until then this is the implemented model.

## Split model

Four modes for cost distribution:
- **Pooled equal** (default, the household spreadsheet's model): shared costs are paid from the
  POOLED net income, the remainder is split equally, and each person then pays their own
  individual fixed costs out of their share. Two persons' pocket money differs *only* by their
  individual costs, and a person with negative net income is carried by the pool.
- **Equal**: shared costs split evenly, each person keeps their own income.
- **Proportional**: shared costs split by net income ratio.
- **Custom**: user sets percentages per person.

`remainder_mode` is ignored in pooled mode: the remainder is already split equally there, and
applying it again would flatten exactly the individual-cost differences the model preserves.

Additional: remainder split ("no split" or "equal distribution"); optional category-level override
of the split (not implemented yet).

## Month cycle (planned, not wired)

Configurable per person: calendar month or salary-based cycle. Recurring transactions belong to
their logical month (bank-day correction: rent on Feb 28 due to a weekend counts as March).
`month_cycle.py` exists but is not wired.

## Income and bonus detection (planned)

- Salary tolerance window of +-5 days for income detection.
- Income >= 15% above the 3-month average triggers an HA notification for confirmation
  (threshold configurable). A confirmed bonus goes to pocket money, not into the monthly
  balance/split calculation.

## Privacy

Default display is aggregates only. Individual transactions are HA-admin only.
