#!/usr/bin/env bash
# Finance Dashboard Companion Add-on — Smart Payload Installer
#
# This script installs the bundled integration + frontend assets into HA config
# whenever the bundled version differs from the installed one, then stays alive
# and re-checks on an interval.
#
# Why it stays alive instead of running once and exiting:
# a `startup: once` add-on has already exited by the time Supervisor auto-updates
# it, and Supervisor only restarts add-ons that were *running*. The installer
# therefore never ran again after an update — the payload sat unpacked in the
# image while /config kept the version from the last host reboot. Staying
# resident keeps the add-on "running", so every auto-update restarts it and the
# payload lands the same minute it arrives.
#
# SECURITY: This script never touches credentials or financial data.
# It only manages integration code files.

set -e

# Roots are overridable so the installer can be exercised against a temporary
# directory in tests. Production always uses the container's real mounts.
CONFIG_ROOT="${FD_CONFIG_ROOT:-/config}"
PAYLOAD_ROOT="${FD_PAYLOAD_ROOT:-/payload}"

INTEGRATION_SOURCE="$PAYLOAD_ROOT/custom_components/finance_dashboard"
INTEGRATION_TARGET="$CONFIG_ROOT/custom_components/finance_dashboard"
LOVELACE_SOURCE="$PAYLOAD_ROOT/www/community/finance-dashboard"
LOVELACE_TARGET="$CONFIG_ROOT/www/community/finance-dashboard"
INSTALL_STATE_PATH="$CONFIG_ROOT/.storage/finance_dashboard_installer.json"
RESTART_MARKER_PATH="$CONFIG_ROOT/.storage/finance_dashboard_restart_needed.json"

# Seconds between drift checks. The install itself is triggered by the add-on
# start; this interval only catches a /config that changed underneath us.
DRIFT_CHECK_INTERVAL="${DRIFT_CHECK_INTERVAL:-3600}"

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

    mkdir -p "$(dirname "$INSTALL_STATE_PATH")"
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

    mkdir -p "$(dirname "$RESTART_MARKER_PATH")"
    cat > "$RESTART_MARKER_PATH" << EOF
{
    "version": "$version",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    echo "[Finance Dashboard] Restart marker written for version $version"
}

# Replace a target tree wholesale instead of copying over the top of it.
# `cp -r` never removes files a later version dropped: 0.13.0 shipped api.py and
# manager.py, later versions replaced both with packages of the same name, and
# copying left the stale modules plus their __pycache__ sitting next to the new
# packages. The allowlist is a guard — this function deletes recursively.
replace_tree() {
    local source="$1"
    local target="$2"

    case "$target" in
        "$INTEGRATION_TARGET") ;;
        "$LOVELACE_TARGET") ;;
        *)
            echo "[Finance Dashboard] REFUSING to replace unexpected path: $target"
            return 1
            ;;
    esac

    rm -rf "$target"
    mkdir -p "$target"
    cp -r "$source/." "$target/"
}

install_if_needed() {
    local bundled_version
    local installed_version

    bundled_version=$(get_version_from_manifest "$INTEGRATION_SOURCE")
    installed_version=$(get_version_from_manifest "$INTEGRATION_TARGET")

    echo "[Finance Dashboard] Bundled version:   $bundled_version"
    echo "[Finance Dashboard] Installed version:  $installed_version"

    if [ "$bundled_version" = "$installed_version" ]; then
        echo "[Finance Dashboard] Versions match — no update needed."
        # Still rewrite the state file: its timestamp is the only proof from
        # outside the container that the installer is actually running.
        write_install_state "$bundled_version" "$installed_version" "skipped_same_version"
        return 0
    fi

    echo "[Finance Dashboard] Version mismatch — updating integration..."

    mkdir -p "$(dirname "$INTEGRATION_TARGET")"
    mkdir -p "$(dirname "$LOVELACE_TARGET")"

    echo "[Finance Dashboard] Copying integration files..."
    replace_tree "$INTEGRATION_SOURCE" "$INTEGRATION_TARGET"

    # Verify copy
    if has_diagnostics_marker "$INTEGRATION_TARGET/__init__.py"; then
        echo "[Finance Dashboard] Integration files verified."
    else
        echo "[Finance Dashboard] WARNING: Verification failed — files may be incomplete."
    fi

    # Copy Lovelace assets (if bundled)
    if [ -d "$LOVELACE_SOURCE" ]; then
        echo "[Finance Dashboard] Copying Lovelace assets..."
        replace_tree "$LOVELACE_SOURCE" "$LOVELACE_TARGET"
        echo "[Finance Dashboard] Lovelace assets copied."
    fi

    write_install_state "$bundled_version" "$bundled_version" "updated"
    write_restart_marker "$bundled_version"

    # Also try to create a persistent notification via HA API (fallback)
    if [ -n "$SUPERVISOR_TOKEN" ]; then
        curl -s -X POST \
            -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"title\": \"Finance Dashboard Updated\", \"message\": \"Version ${bundled_version} installed. Please restart Home Assistant.\", \"notification_id\": \"finance_dashboard_update\"}" \
            "http://supervisor/core/api/services/persistent_notification/create" \
            > /dev/null 2>&1 || true
        echo "[Finance Dashboard] Persistent notification sent."
    fi

    echo "[Finance Dashboard] Update complete. Restart Home Assistant to apply."
    return 0
}

# --- Main logic ---

echo "========================================"
echo "  Finance Dashboard Companion Add-on"
echo "========================================"

# Exit cleanly on a Supervisor stop instead of waiting out the SIGKILL timeout.
trap 'echo "[Finance Dashboard] Stopping."; exit 0' TERM INT

# A failed install must not kill the container: exiting would leave the add-on
# stopped, which is exactly the silent-failure mode this add-on exists to avoid.
# `if !` also suppresses errexit inside the call, so one bad copy is retryable.
if ! install_if_needed; then
    echo "[Finance Dashboard] ERROR: install failed — retrying in ${DRIFT_CHECK_INTERVAL}s."
fi

if [ -n "$FD_RUN_ONCE" ]; then
    echo "[Finance Dashboard] FD_RUN_ONCE set — exiting after a single check."
    exit 0
fi

echo "[Finance Dashboard] Watching for version drift every ${DRIFT_CHECK_INTERVAL}s."
echo "========================================"

while true; do
    # Backgrounded sleep + wait, so the TERM trap fires immediately instead of
    # after the current interval elapses.
    sleep "$DRIFT_CHECK_INTERVAL" &
    wait $!

    if ! install_if_needed; then
        echo "[Finance Dashboard] ERROR: drift check failed — retrying in ${DRIFT_CHECK_INTERVAL}s."
    fi
done
