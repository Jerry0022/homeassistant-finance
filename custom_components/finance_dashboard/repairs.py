"""Repair flows for Finance.

Repair *issues* are raised directly via ``homeassistant.helpers.issue_registry``
inside the manager mixins (``manager/_refresh.py`` and ``manager/__init__.py``)
because they have the full execution context (hass, entry, error details) at
the point of failure.  All of them are ``is_fixable=False`` (informational), so
no fix flow is needed and none is exported.
"""
