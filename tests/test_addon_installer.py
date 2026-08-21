"""Companion add-on installer tests.

These pin the delivery path itself, which is untested code that silently stopped
working: between 0.13.0 and 0.15.1 the add-on package auto-updated four times
while ``/config`` kept the integration from the last host reboot. Two causes:

1. ``startup: once`` — such an add-on has already exited when Supervisor
   auto-updates it, and Supervisor only restarts add-ons that were *running*.
2. ``cp -r`` over the existing tree — files a later version dropped survive.

The script is executed for real against a temporary root (``FD_CONFIG_ROOT`` /
``FD_PAYLOAD_ROOT``), so these assert behaviour rather than source text.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = REPO_ROOT / "finance_dashboard_companion"
RUN_SH = ADDON_ROOT / "run.sh"
CONFIG_YAML = ADDON_ROOT / "config.yaml"

def _resolve_bash() -> str | None:
    """Find a bash that actually runs.

    On Windows ``which("bash")`` usually resolves to the WindowsApps WSL stub,
    which is not a shell unless WSL is installed — so every candidate is probed
    before it is trusted. Git for Windows ships a real bash and is preferred.
    """
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        shutil.which("bash"),
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "echo ok"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            # The WSL stub blocks instead of failing when WSL is not installed.
            continue
        if probe.returncode == 0 and probe.stdout.strip() == "ok":
            return candidate
    return None


BASH = _resolve_bash()
requires_bash = pytest.mark.skipif(BASH is None, reason="no working bash available")


def _write_manifest(directory: Path, version: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(
        json.dumps({"domain": "finance_dashboard", "version": version}, indent=2),
        encoding="utf-8",
    )


def _make_payload(root: Path, version: str, *, modules: list[str]) -> Path:
    """Build a fake /payload tree holding the given integration version."""
    integration = root / "custom_components" / "finance_dashboard"
    _write_manifest(integration, version)
    # run.sh verifies the copy by grepping __init__.py for this marker.
    (integration / "__init__.py").write_text(
        '"""SECURITY: no financial data in git."""\n', encoding="utf-8"
    )
    for module in modules:
        target = integration / module
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {module}\n", encoding="utf-8")

    lovelace = root / "www" / "community" / "finance-dashboard"
    lovelace.mkdir(parents=True, exist_ok=True)
    (lovelace / "finance-dashboard.js").write_text(
        f"// card {version}\n", encoding="utf-8"
    )
    return integration


def _run_installer(config_root: Path, payload_root: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        # POSIX separators: a Windows bash reads backslashes as escapes.
        "FD_CONFIG_ROOT": config_root.as_posix(),
        "FD_PAYLOAD_ROOT": payload_root.as_posix(),
        "FD_RUN_ONCE": "1",
        # Never let a test reach the Supervisor notification endpoint.
        "SUPERVISOR_TOKEN": "",
    }
    return subprocess.run(
        [BASH, str(RUN_SH)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _install_state(config_root: Path) -> dict:
    path = config_root / ".storage" / "finance_dashboard_installer.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- config.yaml contract -------------------------------------------------


def test_addon_is_a_long_running_service() -> None:
    """``startup: once`` is what let four releases never reach /config.

    A once-add-on is stopped by the time Supervisor auto-updates it, and a
    stopped add-on is not restarted by the update, so the installer never ran.
    """
    config = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))

    assert config["startup"] == "services"
    assert config["boot"] == "auto"


def test_addon_maps_ha_config_writable() -> None:
    """Without a writable /config mapping the installer cannot deliver anything."""
    config = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))

    mapping = next(m for m in config["map"] if m["type"] == "homeassistant_config")
    assert mapping["read_only"] is False
    assert mapping["path"] == "/config"


# --- installer behaviour --------------------------------------------------


@requires_bash
def test_installs_when_versions_differ(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    payload_root = tmp_path / "payload"
    _make_payload(payload_root, "0.15.2", modules=["manager/__init__.py"])
    _write_manifest(config_root / "custom_components" / "finance_dashboard", "0.13.0")

    result = _run_installer(config_root, payload_root)

    assert result.returncode == 0, result.stderr
    installed = config_root / "custom_components" / "finance_dashboard"
    assert json.loads((installed / "manifest.json").read_text())["version"] == "0.15.2"
    assert _install_state(config_root)["last_action"] == "updated"


@requires_bash
def test_removes_modules_the_new_version_dropped(tmp_path: Path) -> None:
    """The 0.13.0 -> 0.14.0 shape change: manager.py became the manager package.

    ``cp -r`` left the stale module sitting next to the new package. A delete
    sync is the only thing that clears it.
    """
    config_root = tmp_path / "config"
    payload_root = tmp_path / "payload"
    _make_payload(payload_root, "0.15.2", modules=["manager/__init__.py"])

    installed = config_root / "custom_components" / "finance_dashboard"
    _write_manifest(installed, "0.13.0")
    (installed / "manager.py").write_text("# stale module\n", encoding="utf-8")
    (installed / "api.py").write_text("# stale module\n", encoding="utf-8")
    (installed / "__pycache__").mkdir()
    (installed / "__pycache__" / "manager.cpython-312.pyc").write_bytes(b"stale")

    result = _run_installer(config_root, payload_root)

    assert result.returncode == 0, result.stderr
    assert not (installed / "manager.py").exists()
    assert not (installed / "api.py").exists()
    assert not (installed / "__pycache__").exists()
    assert (installed / "manager" / "__init__.py").exists()


@requires_bash
def test_writes_restart_marker_on_update(tmp_path: Path) -> None:
    """The integration polls for this marker to prompt the HA restart."""
    config_root = tmp_path / "config"
    payload_root = tmp_path / "payload"
    _make_payload(payload_root, "0.15.2", modules=[])
    _write_manifest(config_root / "custom_components" / "finance_dashboard", "0.13.0")

    _run_installer(config_root, payload_root)

    marker = config_root / ".storage" / "finance_dashboard_restart_needed.json"
    assert json.loads(marker.read_text(encoding="utf-8"))["version"] == "0.15.2"


@requires_bash
def test_installs_lovelace_assets(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    payload_root = tmp_path / "payload"
    _make_payload(payload_root, "0.15.2", modules=[])
    _write_manifest(config_root / "custom_components" / "finance_dashboard", "0.13.0")

    _run_installer(config_root, payload_root)

    card = config_root / "www" / "community" / "finance-dashboard" / "finance-dashboard.js"
    assert card.read_text(encoding="utf-8").strip() == "// card 0.15.2"
    assert _install_state(config_root)["has_lovelace"] is True


@requires_bash
def test_installs_onto_a_bare_config(tmp_path: Path) -> None:
    """First install: no integration directory exists yet."""
    config_root = tmp_path / "config"
    payload_root = tmp_path / "payload"
    _make_payload(payload_root, "0.15.2", modules=[])

    result = _run_installer(config_root, payload_root)

    assert result.returncode == 0, result.stderr
    installed = config_root / "custom_components" / "finance_dashboard"
    assert json.loads((installed / "manifest.json").read_text())["version"] == "0.15.2"


@requires_bash
def test_skips_when_versions_match_but_still_records_a_heartbeat(
    tmp_path: Path,
) -> None:
    """The state file's timestamp is the only outside proof the installer runs.

    It is what revealed that run.sh had not executed since 2026-04-25.
    """
    config_root = tmp_path / "config"
    payload_root = tmp_path / "payload"
    _make_payload(payload_root, "0.15.2", modules=[])

    installed = config_root / "custom_components" / "finance_dashboard"
    _write_manifest(installed, "0.15.2")
    keepsake = installed / "untouched.py"
    keepsake.write_text("# must survive a no-op run\n", encoding="utf-8")

    result = _run_installer(config_root, payload_root)

    assert result.returncode == 0, result.stderr
    state = _install_state(config_root)
    assert state["last_action"] == "skipped_same_version"
    assert state["timestamp"]
    # A matching version must not trigger the delete sync.
    assert keepsake.exists()
    assert not (
        config_root / ".storage" / "finance_dashboard_restart_needed.json"
    ).exists()
