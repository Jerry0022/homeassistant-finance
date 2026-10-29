"""Points hand-off: Finance keeps no points ledger.

Every ``POINT_EVERY`` answered questions fire ``finance_dashboard_points_awarded``
and, when the user configured a helper, increment it (``counter.*`` via
``counter.increment`` or ``input_number.*`` via ``input_number.increment``).
The points system itself lives outside this repository.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

EVENT_POINTS_AWARDED = f"{DOMAIN}_points_awarded"
TARGET_DOMAINS = ("counter", "input_number")


class PointsTargetError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


def validate_target(hass: HomeAssistant, raw: Any) -> str:
    """``""`` clears the target; otherwise an existing counter/input_number entity id."""
    if raw is None or raw == "":
        return ""
    if not isinstance(raw, str):
        raise PointsTargetError("invalid_entity", "entity_id must be a string")
    entity_id = raw.strip().lower()
    if entity_id.split(".", 1)[0] not in TARGET_DOMAINS or "." not in entity_id:
        raise PointsTargetError("invalid_entity", "Use a counter or input_number entity")
    if hass.states.get(entity_id) is None:
        raise PointsTargetError("unknown_entity", "Entity does not exist")
    return entity_id


def person_of_user(persons: list[dict[str, Any]], user_id: str | None) -> str | None:
    if not user_id:
        return None
    for p in persons:
        if user_id in [str(i) for i in p.get("ha_users") or []]:
            return str(p.get("name") or "") or None
    return None


async def async_award(
    hass: HomeAssistant,
    *,
    target: str,
    user_id: str | None,
    person: str | None,
    answered: int,
) -> None:
    """Fire the event and bump the configured helper (best effort)."""
    hass.bus.async_fire(
        EVENT_POINTS_AWARDED,
        {"user_id": user_id, "person": person, "points": 1, "answered_total": answered},
    )
    if not target:
        return
    domain = target.split(".", 1)[0]
    if domain not in TARGET_DOMAINS or hass.states.get(target) is None:
        _LOGGER.warning("Points target %s is missing; skipping increment", target)
        return
    try:
        await hass.services.async_call(domain, "increment", {"entity_id": target}, blocking=False)
    except Exception:  # noqa: BLE001 - a helper problem must never fail an answer
        _LOGGER.warning("Could not increment points target %s", target)
