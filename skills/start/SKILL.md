---
description: "Start the Home Assistant integration for manual testing via SSH. Triggers config reload or HA restart over SSH, then opens HA dashboard in Edge. Use when: 'dev start', 'starte die app', 'app starten', 'start', 'run it'. Executes immediately without confirmation."
user_invocable: true
---

# /start — Launch HA Finance Dashboard

**Extends (global /start):** Project-specific launch via SSH + Edge browser.

## Execution Steps

1. **Sync files to HA via SSH** — Copy changed integration files:
   ```bash
   scp -i ~/.ssh/ha_key -P 22222 -r custom_components/finance_dashboard/ root@192.168.178.32:/config/custom_components/finance_dashboard/
   ```

2. **Determine restart level** based on what changed:
   - **YAML reload** (services.yaml, strings.json, translations): `ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'ha core reload'`
   - **Integration reload** (Python files, config_flow): `ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'ha core reload'` + reload config entry via API
   - **Full restart** (manifest.json, __init__.py setup changes, new dependencies): `ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'ha core restart'`
   - **Frontend injection** (JS panel files, Lovelace card): SCP the files + instruct user to press Ctrl+F5

3. **Open HA dashboard in Edge** (background if possible):
   ```bash
   start msedge "http://192.168.178.32:8123/finance-dashboard"
   ```

4. **Get the build ID**: `git write-tree | cut -c1-7`

5. **Show the test prompt card** (format in global `/start` deep-knowledge `test-prompt-card.md`).

## SSH Connection

```
Host: 192.168.178.32
Port: 22222
User: root
Key: ~/.ssh/ha_key
```

## Restart Decision Matrix

| Changed files | Action | User action needed |
|---|---|---|
| `services.yaml`, `strings.json`, `translations/` | YAML reload | None |
| `*.py` (except `__init__.py` setup) | Integration reload | None |
| `manifest.json`, `__init__.py` (setup/deps) | Full HA restart | Wait ~30s |
| `frontend/*.js`, `www/` | SCP only | Ctrl+F5 hard reload |
| Mixed Python + Frontend | Restart + SCP | Ctrl+F5 after restart |

## Rules

- Execute immediately — no confirmation needed.
- Always SCP first, then trigger the appropriate reload/restart.
- Check SSH connectivity first: `ssh -i ~/.ssh/ha_key -p 22222 root@192.168.178.32 'echo ok'` — if this fails, report and stop.
- The test prompt card is **mandatory** after every start. Never skip it.
- When frontend files changed, explicitly tell the user to press Ctrl+F5.
