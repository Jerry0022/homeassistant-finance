"""Repair flows for Finance.

Most repair *issues* are informational and raised directly via
``homeassistant.helpers.issue_registry`` inside the manager mixins.

The exception is bank consent renewal: the manager raises
``consent_expiring_<subentry_id>`` (14 days before ``valid_until``) and
``consent_expired_<subentry_id>`` (on expiry / HTTP 401) as *fixable* issues.
The fix flow here guides the user to the bank subentry's "Reconfigure" action,
which re-runs the bank authorization (``config_flow.BankSubentryFlow``) and
replaces the session + ``valid_until``.  The issue is intentionally NOT
dismissed by this flow: the manager clears it once a fresh session is stored.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ASPSP_NAME,
    DOMAIN,
    ISSUE_CONSENT_EXPIRED_PREFIX,
    ISSUE_CONSENT_EXPIRING_PREFIX,
)

_PREFIXES = (ISSUE_CONSENT_EXPIRING_PREFIX, ISSUE_CONSENT_EXPIRED_PREFIX)


def subentry_id_from_issue(issue_id: str) -> str | None:
    """Extract the subentry id from a consent issue id, or None."""
    for prefix in _PREFIXES:
        if issue_id.startswith(prefix):
            return issue_id[len(prefix) :] or None
    return None


def _find_bank(hass: HomeAssistant, subentry_id: str) -> tuple[str, str] | None:
    """Return (entry_id, bank name) for a bank subentry id."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        sub = entry.subentries.get(subentry_id)
        if sub is not None:
            return entry.entry_id, str(sub.data.get(CONF_ASPSP_NAME) or sub.title)
    return None


class ConsentRenewalRepairFlow(RepairsFlow):
    """Guide the user to re-authorize a bank whose consent is ending/ended."""

    def __init__(self, subentry_id: str) -> None:
        self._subentry_id = subentry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Explain how to renew; on submit leave the issue open."""
        if user_input is not None:
            return self.async_abort(reason="continue_in_integrations")
        found = _find_bank(self.hass, self._subentry_id)
        if found is None:
            return self.async_abort(reason="bank_not_found")
        entry_id, bank = found
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={
                "bank": bank,
                "link": f"/config/integrations/integration/{DOMAIN}#config_entry={entry_id}",
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    """Create the fix flow for a fixable Finance issue."""
    subentry_id = subentry_id_from_issue(issue_id)
    if subentry_id is None and data:
        subentry_id = str(data.get("subentry_id") or "") or None
    if subentry_id is None:
        raise ValueError(f"No fix flow for issue {issue_id}")
    return ConsentRenewalRepairFlow(subentry_id)
