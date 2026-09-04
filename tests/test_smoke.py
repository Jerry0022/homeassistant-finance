"""Smoke tests: verify the integration imports cleanly and constants are intact."""

from __future__ import annotations

import importlib


def test_integration_imports_without_error() -> None:
    """The top-level integration package must be importable without errors.

    Any missing dependency or syntax error in the package would surface here
    before any other test attempts to use the integration.
    """
    mod = importlib.import_module("custom_components.finance_dashboard")
    assert mod is not None


def test_const_domain() -> None:
    """DOMAIN must be the canonical string used across HA entity IDs."""
    from custom_components.finance_dashboard.const import DOMAIN

    assert DOMAIN == "finance_dashboard"


def test_const_version_present() -> None:
    """VERSION must be a non-empty string matching semver-ish format."""
    from custom_components.finance_dashboard.const import VERSION

    assert isinstance(VERSION, str)
    assert len(VERSION) > 0
    parts = VERSION.split(".")
    assert len(parts) == 3, f"VERSION '{VERSION}' is not semver (X.Y.Z)"
    assert all(p.isdigit() for p in parts), f"Non-numeric semver part in '{VERSION}'"


def test_const_service_names() -> None:
    """All SERVICE_* constants must be present and non-empty strings."""
    from custom_components.finance_dashboard import const

    service_attrs = [
        "SERVICE_REFRESH_ACCOUNTS",
        "SERVICE_REFRESH_TRANSACTIONS",
        "SERVICE_CATEGORIZE",
        "SERVICE_GET_BALANCE",
        "SERVICE_GET_SUMMARY",
        "SERVICE_SET_BUDGET_LIMIT",
        "SERVICE_EXPORT_CSV",
    ]
    for attr in service_attrs:
        value = getattr(const, attr, None)
        assert value is not None, f"const.{attr} is missing"
        assert isinstance(value, str), f"const.{attr} must be a str"
        assert len(value) > 0, f"const.{attr} must not be empty"
