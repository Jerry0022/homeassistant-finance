"""Repair flows for Finance Dashboard."""

from __future__ import annotations

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant


class RestartRequiredRepairFlow(RepairsFlow):
    """Handler for restart required repair."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the repair flow."""
        if user_input is not None:
            # User clicked "Restart" — HA handles restart
            return self.async_create_entry(data={}, title="")
        return self.async_show_form(step_id="init")


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict | None
) -> RepairsFlow:
    """Create repair flows."""
    if issue_id == "restart_required":
        return RestartRequiredRepairFlow()
    return RepairsFlow()
