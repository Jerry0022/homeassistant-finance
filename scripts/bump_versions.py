#!/usr/bin/env python3
"""Bump versions across all project files to keep them aligned.

Ensures manifest.json, addon config.yaml, and const.py all have the same version.

Usage:
    python scripts/bump_versions.py --check          # Verify alignment
    python scripts/bump_versions.py --part patch      # Bump patch version
    python scripts/bump_versions.py --part minor      # Bump minor version
    python scripts/bump_versions.py --part major      # Bump major version
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MANIFEST_PATH = ROOT / "custom_components" / "finance_dashboard" / "manifest.json"
ADDON_CONFIG_PATH = ROOT / "finance_dashboard_companion" / "config.yaml"
CONST_PATH = ROOT / "custom_components" / "finance_dashboard" / "const.py"


def get_manifest_version() -> str:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data["version"]


def get_addon_version() -> str:
    text = ADDON_CONFIG_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?(\d+\.\d+\.\d+)"?', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def get_const_version() -> str:
    text = CONST_PATH.read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def check_versions() -> bool:
    manifest = get_manifest_version()
    addon = get_addon_version()
    const = get_const_version()

    print(f"manifest.json:  {manifest}")
    print(f"config.yaml:    {addon}")
    print(f"const.py:       {const}")

    if manifest == addon == const:
        print("\nAll versions aligned.")
        return True
    else:
        print("\nERROR: Version mismatch detected!")
        return False


def bump_version(current: str, part: str) -> str:
    major, minor, patch = map(int, current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def set_version(new_version: str) -> None:
    # Update manifest.json
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["version"] = new_version
    MANIFEST_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Updated manifest.json -> {new_version}")

    # Update addon config.yaml
    text = ADDON_CONFIG_PATH.read_text(encoding="utf-8")
    text = re.sub(
        r'^(version:\s*)"?\d+\.\d+\.\d+"?',
        f'\\1"{new_version}"',
        text,
        flags=re.MULTILINE,
    )
    ADDON_CONFIG_PATH.write_text(text, encoding="utf-8")
    print(f"Updated config.yaml -> {new_version}")

    # Update const.py VERSION
    text = CONST_PATH.read_text(encoding="utf-8")
    text = re.sub(
        r'^(VERSION\s*=\s*)"[^"]*"',
        f'\\1"{new_version}"',
        text,
        flags=re.MULTILINE,
    )
    CONST_PATH.write_text(text, encoding="utf-8")
    print(f"Updated const.py -> {new_version}")

    # Auto-sync payload
    sync_script = ROOT / "scripts" / "sync_addon_payload.py"
    if sync_script.exists():
        print("\nSyncing addon payload...")
        subprocess.run([sys.executable, str(sync_script)], check=True)


def main():
    parser = argparse.ArgumentParser(description="Version management")
    parser.add_argument("--check", action="store_true", help="Check version alignment")
    parser.add_argument("--part", choices=["patch", "minor", "major"], help="Version part to bump")
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_versions() else 1)

    if args.part:
        current = get_manifest_version()
        new_version = bump_version(current, args.part)
        print(f"Bumping: {current} -> {new_version}\n")
        set_version(new_version)
        print(f"\nVersion bumped to {new_version}")
        check_versions()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
