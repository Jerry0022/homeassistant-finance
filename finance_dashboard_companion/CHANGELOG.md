# Changelog


## 0.7.4
- **Branch:** claude/upbeat-davinci
- **Changes:** feat(frontend): status chip replaces refresh button
- New `<finance-status-chip>` Lovelace component with 4 visual states (idle/loading/success/error)
- Panel header uses status chip instead of refresh button + dot indicator
- Register status chip JS as Lovelace extra module

## 0.7.3
- Fix setup wizard race condition — guard flag prevents wizard re-trigger during entry reload
- Fix account defaults in step 3 — merge existing settings into pending accounts

## 0.7.2
- Fix setup/complete merges new accounts with existing ones instead of replacing entry.data
- Fix dashboard refresh uses independent error handling per endpoint
- Fix manage accounts dialog retries 3x with 2s delay before showing error

## 0.7.1
- Fix settings overlay flash on load
- Fix balance data display in account cards

## 0.7.0
- Cascading transfer chain detection

## 0.6.15
- Gesamtsaldo uses actual bank balances from /balances API
- Settings gear icon in dashboard header for account management
- Manage-accounts overlay with rename, type change, person assignment
- New update_accounts endpoint and account details in setup/status

## 0.6.14
- Shimmer skeleton loaders replacing plain loading text
- Async refresh indicator (pulsing dot + timestamp)
- Responsive breakpoints for tablet and mobile
- Improved empty state with SVG icon and descriptive text

## 0.6.12
- HA user multi-select chips in step 3 instead of free-text person field
- Custom display name field per account
- New setup/users endpoint for HA user list

## 0.6.9
- Fix RepairsFlow calls homeassistant.restart service when user confirms
- Fix repair notification title says "Restart Required"
- Updated EN and DE translations for restart repair flow

## 0.6.5
- Fix retry logic and error handling for bank list API calls
- Fix graceful error handling when fetching supported banks fails
- Fix frontend error state with actionable feedback

## 0.6.4
- Fix credential return type breaking bank list loading (dict instead of tuple)

## 0.6.3
- Fix backend returns typed errors for differentiated frontend handling
- Fix frontend shows specific German error messages per error type
- Fix credential errors link to integration settings
- Fix 5-minute polling timeout in Step 2

## 0.6.2
- Fix restart marker poll outside is_configured, check on startup

## 0.6.1
- Fix 30s timeout for Enable Banking API, error state with retry button
- Rename "Finance Dashboard" to "Finance" everywhere

## 0.6.0
- Move bank setup from config flow to dashboard panel setup wizard
- Config flow reduced to credentials-only (1 step, config VERSION 3)
- 4-step setup wizard overlay in Finance sidebar panel
- 4 new setup API endpoints
- Config entry migration v2 to v3

## 0.5.5
- Fix granular Enable Banking API debug logging

## 0.5.2
- Fix config flow error handling for PEM key format errors vs API auth failures

## 0.5.1
- Fix PEM private key field renders as multiline textarea
- Remove deprecated arch values from companion add-on config
- Step-by-step Enable Banking setup instructions

## 0.5.0
- Migrate from GoCardless to Enable Banking API
- New EnableBankingClient with JWT RS256 signing
- Config flow v2 with migration handler

## 0.4.3
- Remove unused nordigen-python dependency (fixes 500 error on config flow)

## 0.4.2
- Fix sidebar panel not appearing (use correct panel_custom API)
- Fix repository.yaml format (remove non-standard channel field)

## 0.4.1
- Fix add-on not showing updates (add exec sleep infinity)
- Fix config.yaml missing fields (stage, options, schema, homeassistant_api)
- Add dark mode icon variants
- Switch to bashio structured logging
- Replace SVG brand assets with PNGs

## 0.4.0
- Benchmark auto-crawl with German national averages
- Drag & drop transaction categorizer
- CSV export service

## 0.3.0
- N-person household budget model
- Recurring transaction detection
- Income recognition with salary tolerance
- Bonus detection
- Budget Config Lovelace card

## 0.2.0
- GoCardless OAuth flow
- Account balance sensors
- Monthly summary sensor
- Privacy-first API

## 0.1.0
- Initial release
