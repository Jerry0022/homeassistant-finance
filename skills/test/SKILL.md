---
description: "Test the HA Finance integration — SSH log inspection + Edge UI tests. Use proactively after ANY change to verify functionality, even for non-UI features. Also triggers on: 'test this', 'zeig mal', 'check the output', 'funktioniert das'. Validates both backend (HA logs via SSH) and frontend (Edge browser UI)."
user_invocable: true
---

# /test — HA Finance Verification

**Extends (global /test):** Project-specific testing via SSH logs + Edge browser UI.

## Core Rule

After every change, verify it works. Pick the method that fits the change:

| Change type | Verification method |
|---|---|
| **Python backend** (API, manager, sensors) | SSH logs + API call via curl |
| **Frontend** (panel JS, Lovelace card) | Edge browser UI test |
| **Config flow** | Edge browser → Settings → Integrations |
| **Services** | SSH: `ha service call finance_dashboard.<service>` |
| **Events** | SSH logs: watch for `fd_*` events |
| **Mixed** | Both SSH logs + Edge UI |

## SSH Log Inspection

```bash
# Live logs (last 100 lines, filtered to finance_dashboard)
ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'ha core logs | grep -i finance_dashboard | tail -100'

# Full HA logs (for startup errors)
ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'ha core logs | tail -200'

# Check integration loaded successfully
ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'ha core logs | grep -E "(finance_dashboard|Setup of|Error setting up)"'
```

## Edge Browser UI Testing

Use Claude in Chrome MCP tools to interact with the HA dashboard:

1. **Get tab context**: `tabs_context_mcp` → find or create Edge tab
2. **Navigate**: `navigate` to `http://192.168.178.32:8123/finance-dashboard`
3. **Verify page loaded**: `read_page` or `find` to check for expected elements
4. **Interact**: `computer` (click, type) to test interactive features
5. **Check results**: `read_page` or `computer` (screenshot) to verify outcomes
6. **Console errors**: `read_console_messages` for JavaScript errors

### Login handling
If HA login page appears, inform the user — do not enter credentials.

## API Verification (for non-UI features)

```bash
# Check API endpoint responds
ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 \
  'curl -s -H "Authorization: Bearer $(cat /config/.storage/core.auth | python3 -c \"import json,sys; print(json.load(sys.stdin)[\\\"data\\\"][\\\"refresh_tokens\\\"][0][\\\"token\\\"])\")" \
  http://localhost:8123/api/finance_dashboard/balances'

# Check entity exists
ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 \
  'ha state list | grep finance_dashboard'
```

## Test Plan Format

After running tests, show results in the global test plan format (see global `/test` deep-knowledge `test-strategy.md`, §User-facing test plan).

## Verification Checklist (run through as applicable)

1. **Integration loaded**: No errors in `ha core logs` mentioning finance_dashboard
2. **Entities created**: Expected sensors/numbers/selects exist in HA state
3. **API responds**: HTTP endpoints return valid JSON (not 404/500)
4. **Panel renders**: Sidebar panel loads without JS errors
5. **Services callable**: `ha service call` returns success
6. **Events fire**: Trigger action → check logs for `fd_*` event

## When NOT to Test

- Pure `.gitignore`, `README.md`, `CHANGELOG.md`, `BUILDLOG.md` changes
- Script changes (`scripts/`) that don't affect the running integration
- CI/CD workflow changes (`.github/workflows/`)

## Rules

- Always check SSH connectivity before running commands.
- Never enter HA credentials or tokens — if login is required, inform the user.
- Report both successes and failures clearly.
- For frontend tests, always check browser console for JS errors.
- If Edge is not available in foreground, open it: `start msedge "http://192.168.178.32:8123/finance-dashboard"`
