#!/usr/bin/env python3
"""Sync integration + frontend files into the add-on payload directory.

The companion add-on bundles a copy of the integration code.
This script keeps it in sync with the source.

Usage:
    python scripts/sync_addon_payload.py           # Sync files
    python scripts/sync_addon_payload.py --check   # Check if synced
"""

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SYNC_MAP = [
    (
        ROOT / "custom_components" / "finance_dashboard",
        ROOT / "finance_dashboard_companion" / "payload" / "custom_components" / "finance_dashboard",
    ),
    (
        ROOT / "www" / "community" / "finance-dashboard",
        ROOT / "finance_dashboard_companion" / "payload" / "www" / "community" / "finance-dashboard",
    ),
]

EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".bak",
    "preview.html",
    ".DS_Store",
}


def should_exclude(path: Path) -> bool:
    return any(pat in str(path) for pat in EXCLUDE_PATTERNS)


def sync_directory(src: Path, dst: Path) -> list[str]:
    """Sync source directory to destination, returning list of actions."""
    actions = []

    if not src.exists():
        return [f"SKIP: Source not found: {src}"]

    # Remove stale files in destination
    if dst.exists():
        for dst_file in sorted(dst.rglob("*")):
            if dst_file.is_dir():
                continue
            rel = dst_file.relative_to(dst)
            src_file = src / rel
            if not src_file.exists() or should_exclude(dst_file):
                dst_file.unlink()
                actions.append(f"REMOVED: {rel}")

    # Copy new/changed files
    for src_file in sorted(src.rglob("*")):
        if src_file.is_dir() or should_exclude(src_file):
            continue

        rel = src_file.relative_to(src)
        dst_file = dst / rel

        if dst_file.exists() and filecmp.cmp(src_file, dst_file, shallow=False):
            continue

        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        actions.append(f"COPIED: {rel}")

    return actions


def check_sync() -> bool:
    """Check if payload is in sync with source."""
    all_synced = True

    for src, dst in SYNC_MAP:
        if not src.exists():
            continue

        for src_file in sorted(src.rglob("*")):
            if src_file.is_dir() or should_exclude(src_file):
                continue

            rel = src_file.relative_to(src)
            dst_file = dst / rel

            if not dst_file.exists():
                print(f"MISSING: {dst_file}")
                all_synced = False
            elif not filecmp.cmp(src_file, dst_file, shallow=False):
                print(f"DIFFERS: {rel}")
                all_synced = False

    if all_synced:
        print("Payload is in sync.")
    else:
        print("\nERROR: Payload out of sync!")

    return all_synced


def main():
    parser = argparse.ArgumentParser(description="Sync addon payload")
    parser.add_argument("--check", action="store_true", help="Check sync status")
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_sync() else 1)

    print("Syncing addon payload...\n")
    total_actions = []
    for src, dst in SYNC_MAP:
        actions = sync_directory(src, dst)
        total_actions.extend(actions)
        for action in actions:
            print(f"  {action}")

    if not total_actions:
        print("  Already in sync — no changes needed.")
    else:
        print(f"\n{len(total_actions)} file(s) synced.")


if __name__ == "__main__":
    main()
