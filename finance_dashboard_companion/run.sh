#!/usr/bin/with-contenv bashio
set -euo pipefail

INTEGRATION_SOURCE="/payload/custom_components/finance_dashboard"
LOVELACE_SOURCE="/payload/www/community/finance-dashboard"
INTEGRATION_TARGET="/config/custom_components/finance_dashboard"
LOVELACE_TARGET_DIR="/config/www/community/finance-dashboard"
SOURCE_MANIFEST="$INTEGRATION_SOURCE/manifest.json"
TARGET_MANIFEST="$INTEGRATION_TARGET/manifest.json"
INSTALL_STATE_PATH="/config/.storage/finance_dashboard_installer.json"

copy_tree() {
    local source="$1"
    local target="$2"

    rm -rf "$target"

    mkdir -p "$(dirname "$target")"
    cp -R "$source" "$target"
}

copy_dir() {
    local source="$1"
    local target="$2"

    rm -rf "$target"

    mkdir -p "$target"
    cp -R "$source/." "$target/"
}

read_version() {
    local manifest="$1"
    if [ ! -f "$manifest" ]; then
        echo "missing"
        return
    fi
    sed -n 's/.*"version":[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -n 1
}

has_security_marker() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo "missing"
        return
    fi
    if grep -q "SECURITY" "$file"; then
        echo "yes"
    else
        echo "no"
    fi
}

write_install_state() {
    local source_version="$1"
    local target_version="$2"
    local security_marker="$3"
    local lovelace_exists="$4"

    mkdir -p "$(dirname "$INSTALL_STATE_PATH")"
    cat > "$INSTALL_STATE_PATH" <<EOF
{
  "installer": "finance_dashboard_companion",
  "timestamp_utc": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "source_version": "$source_version",
  "target_version": "$target_version",
  "security_marker": "$security_marker",
  "lovelace_asset_present": $lovelace_exists
}
EOF
}

verify_install() {
    local source_version="$1"
    local target_version="$2"
    local security_marker="$3"

    if [ "$target_version" != "$source_version" ]; then
        bashio::log.fatal "Integration copy verification failed: source version $source_version, target version $target_version"
    fi

    if [ "$security_marker" != "yes" ]; then
        bashio::log.fatal "Integration copy verification failed: security marker missing in target __init__.py"
    fi

    if [ ! -f "$INTEGRATION_TARGET/__init__.py" ] || [ ! -f "$INTEGRATION_TARGET/config_flow.py" ]; then
        bashio::log.fatal "Integration copy verification failed: critical integration files are missing in target"
    fi
}

send_restart_notification() {
    local version="$1"
    local notification_id="finance_dashboard_restart_required"
    local title="Finance updated to v${version}"
    local message="The Finance integration has been updated. **Please restart Home Assistant** to activate the new version."

    # Write marker file — the running integration polls for this every 60s
    # and creates a Repairs issue (Settings > System > Repairs) with a restart button.
    bashio::log.info "Writing restart marker file..."
    cat > "/config/.storage/finance_dashboard_restart_needed.json" <<NOTIF
{
  "version": "${version}",
  "timestamp_utc": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "title": "${title}",
  "message": "${message}",
  "notification_id": "${notification_id}"
}
NOTIF
    bashio::log.info "Restart marker written — repair issue will appear in Settings within 60s"

    # Also try a single persistent notification as fallback
    if [ -n "${SUPERVISOR_TOKEN:-}" ]; then
        local payload="{\"notification_id\": \"${notification_id}\", \"title\": \"${title}\", \"message\": \"${message}\"}"
        local response=""
        local status=""
        response="$(curl -sSL -w "\n%{http_code}" -X POST \
            -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
            -H "Content-Type: application/json" \
            "http://supervisor/core/api/services/persistent_notification/create" \
            -d "$payload" 2>&1)" || true
        status="$(echo "$response" | tail -n1)"
        if [ "$status" = "200" ] || [ "$status" = "201" ]; then
            bashio::log.info "Persistent notification created as fallback (HTTP ${status})"
        else
            bashio::log.info "Persistent notification fallback skipped (HTTP ${status})"
        fi
    fi
}

# ── Main ──

if [ ! -d "$INTEGRATION_SOURCE" ]; then
    bashio::log.fatal "Bundled integration payload not found: $INTEGRATION_SOURCE"
fi

SOURCE_VERSION="$(read_version "$SOURCE_MANIFEST")"
INSTALLED_VERSION="$(read_version "$TARGET_MANIFEST")"

bashio::log.info "Bundled integration version: $SOURCE_VERSION"
bashio::log.info "Installed integration version: $INSTALLED_VERSION"
bashio::log.info "Security marker (source): $(has_security_marker "$INTEGRATION_SOURCE/__init__.py")"
bashio::log.info "Security marker (installed): $(has_security_marker "$INTEGRATION_TARGET/__init__.py")"

# Only copy if versions differ or target is missing
if [ "$INSTALLED_VERSION" != "$SOURCE_VERSION" ]; then
    bashio::log.info "Installing bundled custom integration into /config/custom_components"
    copy_tree "$INTEGRATION_SOURCE" "$INTEGRATION_TARGET"

    # Copy Lovelace assets (if bundled)
    if [ -d "$LOVELACE_SOURCE" ]; then
        bashio::log.info "Installing bundled Lovelace assets into /config/www/community"
        copy_dir "$LOVELACE_SOURCE" "$LOVELACE_TARGET_DIR"
    fi

    TARGET_VERSION="$(read_version "$TARGET_MANIFEST")"
    TARGET_SECURITY_MARKER="$(has_security_marker "$INTEGRATION_TARGET/__init__.py")"
    LOVELACE_EXISTS="$([ -d "$LOVELACE_TARGET_DIR" ] && echo "true" || echo "false")"

    bashio::log.info "Installed integration version after copy: $TARGET_VERSION"
    bashio::log.info "Security marker after copy: $TARGET_SECURITY_MARKER"

    verify_install "$SOURCE_VERSION" "$TARGET_VERSION" "$TARGET_SECURITY_MARKER"
    write_install_state "$SOURCE_VERSION" "$TARGET_VERSION" "$TARGET_SECURITY_MARKER" "$LOVELACE_EXISTS"
    bashio::log.info "Wrote installer state to $INSTALL_STATE_PATH"

    bashio::log.warning "Integration updated to v${TARGET_VERSION}. Home Assistant restart required."
    send_restart_notification "$TARGET_VERSION"
else
    bashio::log.info "Integration is already at v${INSTALLED_VERSION}, no update needed."
fi

# Stay running so the Supervisor keeps this add-on in "started" state.
# This ensures the add-on auto-restarts after updates (boot: auto),
# which triggers the install/update logic above with the new payload.
bashio::log.info "Add-on is running. It will re-deploy automatically after updates."
exec sleep infinity
