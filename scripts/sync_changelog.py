#!/usr/bin/env python3
"""Sync CHANGELOG.md from BUILDLOG.md entries.

Parses the latest BUILDLOG entry and prepends a formatted CHANGELOG section.
Also updates the companion add-on CHANGELOG.

Usage:
    python scripts/sync_changelog.py                    # Sync latest version
    python scripts/sync_changelog.py --check            # Check if CHANGELOG is up-to-date
    python scripts/sync_changelog.py --version 0.7.3    # Sync specific version
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BUILDLOG_PATH = ROOT / "BUILDLOG.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
ADDON_CHANGELOG_PATH = ROOT / "finance_dashboard_companion" / "CHANGELOG.md"
CONST_PATH = ROOT / "custom_components" / "finance_dashboard" / "const.py"


def get_current_version() -> str:
    text = CONST_PATH.read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def get_changelog_latest_version() -> str:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    match = re.search(r'##\s*\[?(\d+\.\d+\.\d+)\]?', text)
    return match.group(1) if match else "0.0.0"


def parse_buildlog_entry(version: str) -> dict | None:
    """Extract a single BUILDLOG entry by version."""
    text = BUILDLOG_PATH.read_text(encoding="utf-8")

    # Match entry header with version
    pattern = rf'##\s*(?:\[?v?{re.escape(version)}\]?)\s*(?:—\s*(\d{{4}}-\d{{2}}-\d{{2}}))?'
    match = re.search(pattern, text)
    if not match:
        return None

    date = match.group(1) or "unknown"
    start = match.end()

    # Find next entry
    next_entry = re.search(r'\n##\s', text[start:])
    end = start + next_entry.start() if next_entry else len(text)

    body = text[start:end].strip()

    # Extract change lines (lines starting with -)
    changes = []
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("- ") and not line.startswith("- **Build"):
            # Clean up prefixes like "fix(x):" or "feat(x):"
            changes.append(line)

    return {"version": version, "date": date, "changes": changes}


def classify_changes(changes: list[str]) -> dict[str, list[str]]:
    """Group changes by type (Added, Changed, Fixed, Improved)."""
    groups: dict[str, list[str]] = {}

    for line in changes:
        text = line.lstrip("- ").strip()

        # Detect type from conventional commit prefix
        if re.match(r'feat\(', text, re.IGNORECASE):
            category = "Added"
            text = re.sub(r'^feat\([^)]*\):\s*', '', text)
        elif re.match(r'fix\(', text, re.IGNORECASE):
            category = "Fixed"
            text = re.sub(r'^fix\([^)]*\):\s*', '', text)
        elif re.match(r'refactor\(', text, re.IGNORECASE):
            category = "Changed"
            text = re.sub(r'^refactor\([^)]*\):\s*', '', text)
        elif "fix" in text[:20].lower():
            category = "Fixed"
        elif any(kw in text[:20].lower() for kw in ["add", "new", "feat"]):
            category = "Added"
        else:
            # Default: infer from content
            category = "Changed"

        text = text[0].upper() + text[1:] if text else text
        groups.setdefault(category, []).append(f"- {text}")

    return groups


def format_changelog_entry(entry: dict) -> str:
    """Format a BUILDLOG entry as a CHANGELOG section."""
    groups = classify_changes(entry["changes"])

    lines = [f'## [{entry["version"]}] — {entry["date"]}', ""]

    # Preferred order
    for category in ["Added", "Changed", "Fixed", "Improved"]:
        if category in groups:
            lines.append(f"### {category}")
            lines.extend(groups[category])
            lines.append("")

    return "\n".join(lines)


def prepend_to_changelog(new_entry: str) -> None:
    """Insert new entry after the file header."""
    text = CHANGELOG_PATH.read_text(encoding="utf-8")

    # Find insertion point (after header lines)
    header_end = 0
    for match in re.finditer(r'^(?:#[^#].*|All notable.*|$)\n', text, re.MULTILINE):
        header_end = match.end()

    before = text[:header_end].rstrip() + "\n\n"
    after = text[header_end:].lstrip("\n")

    CHANGELOG_PATH.write_text(before + new_entry + "\n" + after, encoding="utf-8")


def update_addon_changelog(entry: dict) -> None:
    """Update the companion add-on CHANGELOG (simplified format)."""
    text = ADDON_CHANGELOG_PATH.read_text(encoding="utf-8")

    # Build simplified entry
    simplified = [f"## {entry['version']}"]
    for change in entry["changes"]:
        # Strip conventional commit prefix for addon changelog
        line = change.lstrip("- ").strip()
        line = re.sub(r'^(?:feat|fix|refactor)\([^)]*\):\s*', '', line)
        line = line[0].upper() + line[1:] if line else line
        simplified.append(f"- {line}")

    new_section = "\n".join(simplified) + "\n"

    # Insert after header
    header_match = re.search(r'^# Changelog\s*\n', text)
    if header_match:
        insert_pos = header_match.end()
        text = text[:insert_pos] + "\n" + new_section + "\n" + text[insert_pos:]
    else:
        text = "# Changelog\n\n" + new_section + "\n" + text

    ADDON_CHANGELOG_PATH.write_text(text, encoding="utf-8")


def check_sync() -> bool:
    current = get_current_version()
    changelog_latest = get_changelog_latest_version()

    print(f"Current version:   {current}")
    print(f"CHANGELOG latest:  {changelog_latest}")

    if current == changelog_latest:
        print("\nCHANGELOG is up-to-date.")
        return True
    else:
        print(f"\nCHANGELOG is behind! Missing: {current}")
        return False


def sync_version(version: str) -> bool:
    """Sync a single version from BUILDLOG to CHANGELOG."""
    # Check if already in CHANGELOG
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    if re.search(rf'##\s*\[?{re.escape(version)}\]?', text):
        print(f"v{version} already in CHANGELOG, skipping.")
        return False

    entry = parse_buildlog_entry(version)
    if not entry:
        print(f"v{version} not found in BUILDLOG.")
        return False

    if not entry["changes"]:
        print(f"v{version} has no change lines in BUILDLOG, skipping.")
        return False

    formatted = format_changelog_entry(entry)
    prepend_to_changelog(formatted)
    update_addon_changelog(entry)
    print(f"Synced v{version} to CHANGELOG.md and addon CHANGELOG.md")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sync CHANGELOG from BUILDLOG")
    parser.add_argument("--check", action="store_true", help="Check if CHANGELOG is up-to-date")
    parser.add_argument("--version", help="Sync a specific version")
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_sync() else 1)

    if args.version:
        sync_version(args.version)
    else:
        version = get_current_version()
        sync_version(version)


if __name__ == "__main__":
    main()
