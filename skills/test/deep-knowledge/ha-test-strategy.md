# HA Finance Test Strategy

## SSH Connection Details

```
Host: 192.168.178.32
Port: 22222
User: root
Key: ~/.ssh/ha_key
```

## Log Patterns to Watch

### Success indicators
```
Setting up finance_dashboard
Setup of finance_dashboard completed
Loaded finance_dashboard
```

### Error indicators
```
Error setting up finance_dashboard
Unable to set up
ImportError
SyntaxError
TypeError
AttributeError
```

### Event patterns
```
fd_transaction_new
fd_balance_changed
fd_budget_exceeded
fd_recurring_detected
```

## Entity Naming Convention

- Balance sensors: `sensor.fd_{bank}_{account}`
- Total balance: `sensor.fd_total_balance`
- Monthly summary: `sensor.fd_monthly_summary`
- Budget per person: `sensor.fd_budget_{person}`
- Budget limit: `number.fd_budget_{category}`
- Split model: `select.fd_split_model`

## API Endpoints

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/api/finance_dashboard/balances` | GET | Bearer | Account balances |
| `/api/finance_dashboard/transactions` | GET | Bearer | Transaction list |
| `/api/finance_dashboard/summary` | GET | Bearer | Monthly summary |

## Frontend Panel

- URL: `http://192.168.178.32:8123/finance-dashboard`
- Entry point: `finance-dashboard-panel.js`
- Expected elements: sidebar panel with finance dashboard content
- Budget config: `fd-budget-config.js` sub-component
- Categorization: `fd-categorize.js` sub-component

## Restart Recovery Times

| Action | Expected recovery |
|---|---|
| YAML reload | ~2s |
| Integration reload | ~5s |
| Full HA restart | ~30-60s |
| Frontend hard reload (Ctrl+F5) | Instant |
