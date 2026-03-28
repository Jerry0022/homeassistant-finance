# Frontend Component Architecture

## Overview

The Finance Dashboard uses a **component-based architecture** built with vanilla Web Components (Custom Elements API). Data flows from the Home Assistant coordinator through entity states into an invisible data provider, which distributes a unified data object to visual components.

## Component Hierarchy

```
finance-dashboard-panel (Shell — sidebar entry point, ~80 lines)
 |-- fd-data-provider (Invisible — entity subscription + API bridge)
 |-- fd-header (Title bar, month selector, refresh button, status chip)
 |    '-- finance-status-chip (Sync state indicator)
 |-- fd-stats-row (4 KPI cards grid)
 |    '-- fd-stat-card x4 (Single KPI: balance, expenses, income, savings)
 |-- fd-household-section (Conditional — only when household data present)
 |    '-- fd-person-card xN (Per-person Spielgeld breakdown)
 |-- fd-category-section (Grid: donut + top-3 + fix/var)
 |    |-- fd-donut-chart (SVG donut with category list)
 |    '-- (top-3 costs + fix/var inline)
 |-- fd-cost-distribution (Stacked horizontal bar — shared costs or category)
 '-- fd-recurring-list (Recurring payments, max 8)
```

Standalone Lovelace cards (registered separately):
- `finance-dashboard-card` (compact balance widget in `www/community/`)
- `fd-budget-config` (split model configuration)
- `fd-categorize` (transaction categorization, admin-only)
- `finance-status-chip` (sync state indicator)

## Data Flow

```
Enable Banking API
      |
      v
  Manager (business logic — manager.py)
      |
      v
  Coordinator (10-min cycle — coordinator.py)
      |
      v
  coordinator.data = { balances: {...}, summary: {...} }
      |                                    |
      v                                    v
  Entity States updated              API endpoints read
  (sensor.fd_*, number.fd_*,         from coordinator.data
   select.fd_*)                            |
      |                                    |
      v                                    v
  fd-data-provider <-------- merges -------+
      |                    (reads entities for balances/summary,
      |                     ONE API call for household/recurring)
      v
  CustomEvent("fd-data-updated")
      |
      v
  All child components re-render via property setters
```

## Data Strategy: Entities First, API for Complex Data

| Data Point | Source | Entity / Endpoint | Reason |
|---|---|---|---|
| Per-account balance | **Entity state** | `sensor.fd_{bank}_{account}` | Reactive, coordinator-driven |
| Total balance | **Entity state** | `sensor.fd_total_balance` | Aggregation done server-side |
| Monthly income | **Entity attr** | `sensor.fd_monthly_summary` → `total_income` | Already in extra_state_attributes |
| Monthly expenses | **Entity attr** | `sensor.fd_monthly_summary` → `total_expenses` | Already in extra_state_attributes |
| Categories | **Entity attr** | `sensor.fd_monthly_summary` → `categories` | Dict of category → amount |
| Transaction count | **Entity attr** | `sensor.fd_monthly_summary` → `transaction_count` | Simple integer |
| Fixed/variable costs | **Entity attr** | `sensor.fd_monthly_summary` → `fixed_costs`, `variable_costs` | Simple floats |
| Budget limits | **Entity state** | `number.fd_budget_{category}` | One entity per category |
| Split model | **Entity state** | `select.fd_split_model` | User-configurable select |
| Household data | **API call** | `GET /summary` → `household` | Nested member arrays, too complex for attrs |
| Recurring payments | **API call** | `GET /summary` → `recurring` | Array of objects |
| Transaction list | **API call** | `GET /transactions` (admin-only) | Privacy: admin-only detail data |

## Unified Data Object

The `fd-data-provider` merges entity states + API data into one object:

```javascript
{
  accounts: [
    { entityId, name, institution, balance, ibanMasked, currency, person }
  ],
  totalBalance: 12345.67,
  accountCount: 2,
  summary: {
    totalIncome: 4500.00,
    totalExpenses: 3200.00,
    balance: 1300.00,
    categories: { housing: -1200, food: -450, ... },
    transactionCount: 87,
    fixedCosts: 2100.00,
    variableCosts: 1100.00,
    month: 3,
    year: 2026,
  },
  budgets: { housing: 1300, food: 500, ... },
  splitModel: "proportional",
  household: { members: [...], split_model, total_shared_costs },
  recurring: [ { creditor, average_amount, frequency, category, expected_day } ],
  loading: false,
  error: null,
  lastRefresh: "2026-03-28T14:30:00",
}
```

## Event System

### Parent → Child: Property Setters

```javascript
// Panel shell pushes data to children
this._statsRow.data = this._dataProvider.data;
this._categorySection.data = this._dataProvider.data;
```

### Child → Parent: CustomEvents

All events use `fd-` prefix, `bubbles: true, composed: true` for Shadow DOM traversal.

| Event | Dispatched By | Handled By | Purpose |
|---|---|---|---|
| `fd-data-updated` | fd-data-provider | panel shell | New data available |
| `fd-refresh-requested` | fd-header | panel shell → data provider | Manual refresh |
| `fd-month-changed` | fd-header | fd-data-provider | Month navigation (Phase 2) |
| `fd-category-selected` | fd-donut-chart | fd-transaction-list (Phase 3) | Category drill-down |
| `retry` | finance-status-chip | fd-header | Error recovery |

### Sibling Communication

Siblings never communicate directly. The panel shell mediates all cross-component data flow.

## Extension Points

### Phase 2: Household Budget
- `fd-household-section` renders conditionally when `data.household` exists
- Custom split slider dispatches `fd-split-changed` → `hass.callService("select", "select_option")`
- `fd-person-card` supports month-over-month sparkline via optional `trend` property

### Phase 3: Analytics
- `fd-transaction-list`: activated by `fd-category-selected` from donut click
- `fd-benchmark-card`: standalone, fetches from `GET /benchmark`
- `fd-trend-chart`: reads from HA long-term statistics or new `GET /summary/history?months=6`

### Adding New Components
1. Create `frontend/fd-{name}.js` with `customElements.define()`
2. Register for Lovelace use: `window.customCards.push(...)` + add to `LOVELACE_COMPONENTS` in `panel.py`
3. For panel use: import in shell, create instance, set `data` property

## File Layout

```
frontend/
  finance-dashboard-panel.js    — Thin shell (~120 lines)
  fd-data-provider.js           — Entity subscription + API bridge
  fd-shared-styles.js           — CSS template + formatters + XSS helper
  fd-header.js                  — Title bar, month, refresh, status chip
  fd-stats-row.js               — 4-KPI grid container
  fd-stat-card.js               — Single KPI card (reusable)
  fd-household-section.js       — Person cards + shared costs bar
  fd-person-card.js             — Single person Spielgeld card
  fd-category-section.js        — Donut + top-3 + fix/var grid
  fd-donut-chart.js             — SVG donut chart
  fd-cost-distribution.js       — Stacked horizontal bar
  fd-recurring-list.js          — Recurring payments card
  finance-status-chip.js        — Sync state indicator (existing)
  fd-budget-config.js           — Budget configuration (existing)
  fd-categorize.js              — Transaction categorization (existing)
```

## Security

- **IBAN masking**: Data provider reads `iban_masked` from entity attributes — never full IBAN
- **Admin gate**: Components that show individual transactions check `this._hass.user.is_admin`
- **Shadow DOM**: Each component uses `attachShadow({ mode: "open" })` for style isolation
- **XSS prevention**: All user-provided text passed through `_esc()` helper
- **No sensitive data in DOM**: Amounts in text content only, never in `data-*` attributes
