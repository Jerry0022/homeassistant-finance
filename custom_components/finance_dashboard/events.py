"""Event firing for Finance Dashboard automation triggers.

4 events:
- fd_transaction_new: New transaction detected
- fd_balance_changed: Account balance changed significantly
- fd_budget_exceeded: Category spending exceeds budget limit
- fd_recurring_detected: New recurring payment pattern found
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

EVENT_TRANSACTION_NEW = f"{DOMAIN}_transaction_new"
EVENT_BALANCE_CHANGED = f"{DOMAIN}_balance_changed"
EVENT_BUDGET_EXCEEDED = f"{DOMAIN}_budget_exceeded"
EVENT_RECURRING_DETECTED = f"{DOMAIN}_recurring_detected"


def fire_transaction_new(
    hass: HomeAssistant,
    amount: float,
    creditor: str,
    category: str,
    account_name: str = "",
) -> None:
    """Fire event when a new transaction is detected."""
    hass.bus.async_fire(
        EVENT_TRANSACTION_NEW,
        {
            "amount": amount,
            "creditor": creditor,
            "category": category,
            "account_name": account_name,
        },
    )
    _LOGGER.debug(
        "Event fired: %s (%.2f from %s)",
        EVENT_TRANSACTION_NEW,
        amount,
        creditor,
    )


def fire_balance_changed(
    hass: HomeAssistant,
    account_name: str,
    old_balance: float,
    new_balance: float,
) -> None:
    """Fire event when account balance changes."""
    change = new_balance - old_balance
    hass.bus.async_fire(
        EVENT_BALANCE_CHANGED,
        {
            "account_name": account_name,
            "old_balance": round(old_balance, 2),
            "new_balance": round(new_balance, 2),
            "change": round(change, 2),
        },
    )


def fire_budget_exceeded(
    hass: HomeAssistant,
    category: str,
    limit: float,
    actual: float,
) -> None:
    """Fire event when spending exceeds budget limit for a category."""
    overshoot = actual - limit
    overshoot_pct = (overshoot / limit * 100) if limit > 0 else 0
    hass.bus.async_fire(
        EVENT_BUDGET_EXCEEDED,
        {
            "category": category,
            "limit": round(limit, 2),
            "actual": round(actual, 2),
            "overshoot": round(overshoot, 2),
            "overshoot_pct": round(overshoot_pct, 1),
        },
    )
    _LOGGER.info(
        "Budget exceeded for %s: %.2f / %.2f (%.1f%% over)",
        category,
        actual,
        limit,
        overshoot_pct,
    )


def fire_recurring_detected(
    hass: HomeAssistant,
    creditor: str,
    amount: float,
    frequency: str = "monthly",
) -> None:
    """Fire event when a new recurring payment pattern is detected."""
    hass.bus.async_fire(
        EVENT_RECURRING_DETECTED,
        {
            "creditor": creditor,
            "amount": round(amount, 2),
            "frequency": frequency,
        },
    )
    _LOGGER.info(
        "Recurring detected: %s (%.2f %s)", creditor, amount, frequency
    )
