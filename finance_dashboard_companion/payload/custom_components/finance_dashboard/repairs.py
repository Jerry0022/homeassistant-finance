"""Repair flows for Finance.

This module is intentionally thin.  Repair *issues* are raised directly via
``homeassistant.helpers.issue_registry`` inside the manager mixins
(``manager/_refresh.py`` and ``manager/__init__.py``) because they have the
full execution context (hass, entry, error details) at the point of failure.

Re-exports ``async_create_fix_flow`` from ``ha-customapps`` so HA's repair
machinery can locate the fix-flow handler via the standard import path
``custom_components.finance_dashboard.repairs``.
"""

from ha_customapps.repairs import async_create_fix_flow  # noqa: F401
