"""Savings goals (product-concept § Goals and reserves) - data and validation only.

Four kinds, each with the fields it needs:

* ``target_by_date``  ``target_amount`` by ``target_date`` (``YYYY-MM-DD``)
* ``category_cap``    monthly ``cap_amount`` for a ``category``
* ``savings_rate``    ``rate_percent`` (0-100) of net income
* ``reserve_topup``   ``monthly_amount`` set aside for the reserve ``reserve_id``

All amounts are positive plan-side numbers (EUR). ``owner`` is ``shared`` or a
person key. Goals live in their own HA Store (``.storage`` only, never git).
Readers (home/household) use :func:`async_get_goals`.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_KEY = f"{DOMAIN}.savings_goals"
STORAGE_VERSION = 1
MAX_GOALS = 50
KINDS = ("target_by_date", "category_cap", "savings_rate", "reserve_topup")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_MAX_AMOUNT = 100_000_000


class GoalError(ValueError):
    """Invalid goal; ``code`` is the API error code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


def _amount(raw: Any, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise GoalError("invalid_goal", f"{field} must be a number")
    if not 0 < float(raw) <= _MAX_AMOUNT:
        raise GoalError("invalid_goal", f"{field} out of range")
    return round(float(raw), 2)


def validate_goal(raw: Any, valid_owners: set[str]) -> dict[str, Any]:
    """Body of the add call -> stored goal (without id). Raises :class:`GoalError`."""
    if not isinstance(raw, dict):
        raise GoalError("invalid_body", "Body must be a JSON object")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise GoalError("invalid_kind", "Unknown goal kind")
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 60:  # noqa: PLR2004
        raise GoalError("invalid_goal", "name must be 1-60 characters")
    owner = str(raw.get("owner") or "shared")
    if owner != "shared" and owner not in valid_owners:
        raise GoalError("unknown_owner", "Owner must be shared or a person")
    goal: dict[str, Any] = {"kind": kind, "name": name, "owner": owner}
    if kind == "target_by_date":
        goal["target_amount"] = _amount(raw.get("target_amount"), "target_amount")
        try:
            goal["target_date"] = date.fromisoformat(str(raw.get("target_date")))
            goal["target_date"] = goal["target_date"].isoformat()
        except ValueError as err:
            raise GoalError("invalid_goal", "target_date must be YYYY-MM-DD") from err
    elif kind == "category_cap":
        category = str(raw.get("category") or "")
        if not _SLUG.match(category):
            raise GoalError("invalid_goal", "category must be a slug")
        goal["category"] = category
        goal["cap_amount"] = _amount(raw.get("cap_amount"), "cap_amount")
    elif kind == "savings_rate":
        rate = _amount(raw.get("rate_percent"), "rate_percent")
        if rate > 100:  # noqa: PLR2004
            raise GoalError("invalid_goal", "rate_percent must be <= 100")
        goal["rate_percent"] = rate
    else:  # reserve_topup
        reserve = str(raw.get("reserve_id") or "").strip()
        if not reserve or len(reserve) > 120:  # noqa: PLR2004
            raise GoalError("invalid_goal", "reserve_id required")
        goal["reserve_id"] = reserve
        goal["monthly_amount"] = _amount(raw.get("monthly_amount"), "monthly_amount")
    return goal


def _store(hass: HomeAssistant) -> Store:
    data = hass.data.setdefault(DOMAIN, {})
    store = data.get("_savings_goals_store")
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        data["_savings_goals_store"] = store
    return store


async def async_get_goals(hass: HomeAssistant) -> list[dict[str, Any]]:
    """All goals (cache read)."""
    try:
        raw = await _store(hass).async_load()
    except Exception:  # noqa: BLE001 - a broken file must not break readers
        raw = None
    goals = raw.get("goals") if isinstance(raw, dict) else None
    return [g for g in goals if isinstance(g, dict)] if isinstance(goals, list) else []


async def async_add_goal(
    hass: HomeAssistant, raw: Any, valid_owners: set[str]
) -> dict[str, Any]:
    goals = await async_get_goals(hass)
    if len(goals) >= MAX_GOALS:
        raise GoalError("too_many_goals", "Goal limit reached")
    goal = {"id": uuid.uuid4().hex[:12], **validate_goal(raw, valid_owners)}
    goals.append(goal)
    await _store(hass).async_save({"goals": goals})
    return goal


async def async_remove_goal(hass: HomeAssistant, goal_id: str) -> bool:
    goals = await async_get_goals(hass)
    kept = [g for g in goals if g.get("id") != goal_id]
    if len(kept) == len(goals):
        return False
    await _store(hass).async_save({"goals": kept})
    return True
