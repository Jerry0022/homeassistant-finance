# Release, versions, changelog

Read this before bumping a version, writing a BUILDLOG entry or shipping.

## Versions

`custom_components/finance_dashboard/manifest.json` (`version`) and `const.py` (`VERSION`) must
always match. `hacs.json` carries no version. Bump atomically:

```bash
python scripts/bump_versions.py --check
python scripts/bump_versions.py --part patch|minor|major
```

## Changelog

After every BUILDLOG entry run `python scripts/sync_changelog.py` to propagate it to
`CHANGELOG.md` (keep-a-changelog; conventional prefixes `feat()/fix()/refactor()` group into
Added/Changed/Fixed). `--check` verifies, `--version X.Y.Z` syncs a specific version.
Ship through the `/devops-ship` pipeline, never manually.

## Validation (same as CI)

```bash
python -m py_compile custom_components/finance_dashboard/__init__.py
node --check custom_components/finance_dashboard/frontend/finance-dashboard-panel.js
python scripts/check_no_banking_data.py
pytest tests
```

## Distribution

HACS only. The companion add-on and payload sync were removed.
