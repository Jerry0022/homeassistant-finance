"""Balance selection shared by the sensors and the statistics import."""

from __future__ import annotations

from typing import Any

from .const import AVAILABLE_BALANCE_TYPES, BALANCE_TYPE_PRIORITY


def pick_balance(balances: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the most useful balance (booked first, see BALANCE_TYPE_PRIORITY).

    Matches ISO 20022 codes and camelCase names case-insensitively.  Falling
    through to ``balances[0]`` is the last resort.
    """
    if not balances:
        return None
    by_type = {str(b.get("balanceType", "")).upper(): b for b in balances}
    for balance_type in BALANCE_TYPE_PRIORITY:
        match = by_type.get(balance_type.upper())
        if match is not None:
            return match
    return balances[0]


def pick_available(balances: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the bank-reported available balance, or None if it gave none."""
    by_type = {str(b.get("balanceType", "")).upper(): b for b in balances or []}
    for balance_type in AVAILABLE_BALANCE_TYPES:
        match = by_type.get(balance_type.upper())
        if match is not None:
            return match
    return None


def amount_of(balance: dict[str, Any] | None) -> float | None:
    """Parse ``balanceAmount.amount`` into a float, None when unusable."""
    if not balance:
        return None
    try:
        return float((balance.get("balanceAmount") or {}).get("amount"))
    except (TypeError, ValueError):
        return None
