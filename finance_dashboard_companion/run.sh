#!/usr/bin/env bash
# Finance Dashboard Companion Add-on — Smart Payload Installer
#
# This script runs once after the add-on starts.
# It copies the bundled integration + frontend assets to HA config,
# but only if the versions differ (avoids unnecessary restarts).
#
# SECURITY: This script never touches credentials or financial data.
# It only manages integration code files.

set -e

INTEGRATION_SOURCE="/payload/custom_components/finance_dashboard"
INTEGRATION_TARGET="/config/custom_components/finance_dashboard"
LOVELACE_SOURCE="/payload/www/community/finance-dashboard"
LOVELACE_TARGET="/config/www/community/finance-dashboard"
INSTALL_STATE_PATH="/config/.storage/finance_dashboard_installer.json"
RESTART_MARKER_PATH="/config/.storage/finance_dashboard_restart_needed.json"

# --- Helper functions ---

get_version_from_manifest() {
    local manifest_path="$1/manifest.json"
    if [ -f "$manifest_path" ]; then
        grep -o '"version": *"[^"]*"' "$manifest_path" | head -1 | sed 's/.*"\([^"]*\)"/\1/'
    else
        echo "0.0.0"
    fi
}

has_diagnostics_marker() {
    local file="$1"
    grep -q "SECURITY" "$file" 2>/dev/null
}

write_install_state() {
    local bundled_version="$1"
    local installed_version="$2"
    local action="$3"

    cat > "$INSTALL_STATE_PATH" << EOF
{
    "bundled_version": "$bundled_version",
    "installed_version": "$installed_version",
    "last_action": "$action",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "has_lovelace": $([ -d "$LOVELACE_TARGET" ] && echo "true" || echo "false")
}
EOF
    echo "[Finance Dashboard] Install state written: $action"
}

write_restart_marker() {
    local version="$1"
    cat > "$RESTART_MARKER_PATH" << EOF
{
    "version": "$version",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    echo "[Finance Dashboard] Restart marker written for version $version"
}

# --- Main logic ---

echo "========================================"
echo "  Finance Dashboard Companion Add-on"
echo "========================================"

BUNDLED_VERSION=$(get_version_from_manifest "$INTEGRATION_SOURCE")
INSTALLED_VERSION=$(get_version_from_manifest "$INTEGRATION_TARGET")

echo "[Finance Dashboard] Bundled version:   $BUNDLED_VERSION"
echo "[Finance Dashboard] Installed version:  $INSTALLED_VERSION"

if [ "$BUNDLED_VERSION" = "$INSTALLED_VERSION" ]; then
    echo "[Finance Dashboard] Versions match — no update needed."
    write_install_state "$BUNDLED_VERSION" "$INSTALLED_VERSION" "skipped_same_version"
    exit 0
fi

echo "[Finance Dashboard] Version mismatch — updating integration..."

# Create target directories
mkdir -p "$INTEGRATION_TARGET"
mkdir -p "$(dirname "$LOVELACE_TARGET")"

# Copy integration files
echo "[Finance Dashboard] Copying integration files..."
cp -r "$INTEGRATION_SOURCE/"* "$INTEGRATION_TARGET/"

# Verify copy
if has_diagnostics_marker "$INTEGRATION_TARGET/__init__.py"; then
    echo "[Finance Dashboard] Integration files verified."
else
    echo "[Finance Dashboard] WARNING: Verification failed — files may be incomplete."
fi

# Copy Lovelace assets (if bundled)
if [ -d "$LOVELACE_SOURCE" ]; then
    echo "[Finance Dashboard] Copying Lovelace assets..."
    mkdir -p "$LOVELACE_TARGET"
    cp -r "$LOVELACE_SOURCE/"* "$LOVELACE_TARGET/"
    echo "[Finance Dashboard] Lovelace assets copied."
fi

# Write install state
write_install_state "$BUNDLED_VERSION" "$BUNDLED_VERSION" "updated"

# Signal restart needed
write_restart_marker "$BUNDLED_VERSION"

# Also try to create a persistent notification via HA API (fallback)
if [ -n "$SUPERVISOR_TOKEN" ]; then
    curl -s -X POST \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"Finance Dashboard Updated\", \"message\": \"Version ${BUNDLED_VERSION} installed. Please restart Home Assistant.\", \"notification_id\": \"finance_dashboard_update\"}" \
        "http://supervisor/core/api/services/persistent_notification/create" \
        > /dev/null 2>&1 || true
    echo "[Finance Dashboard] Persistent notification sent."
fi

echo "[Finance Dashboard] Update complete. Restart Home Assistant to apply."
echo "========================================"
