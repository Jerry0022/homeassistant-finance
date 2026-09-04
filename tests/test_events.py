"""Tests for the four automation events (S6 — coverage gap fill).

Covers:
1. fire_transaction_new: emits correct event + payload shape
2. fire_balance_changed: computes change correctly (positive/negative/zero)
3. fire_budget_exceeded: computes overshoot + pct, guards against limit=0
4. fire_recurring_detected: emits with default + custom frequency

These functions are deterministic wrappers around hass.bus.async_fire and
have zero I/O — pure MagicMock-based unit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.finance_dashboard.events import (
    EVENT_BALANCE_CHANGED,
    EVENT_BUDGET_EXCEEDED,
    EVENT_RECURRING_DETECTED,
    EVENT_TRANSACTION_NEW,
    fire_balance_changed,
    fire_budget_exceeded,
    fire_recurring_detected,
    fire_transaction_new,
)


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    return hass


# ---------------------------------------------------------------------------
# fire_transaction_new
# ---------------------------------------------------------------------------

def test_fire_transaction_new_emits_full_payload():
    """Happy path: all fields propagated, event name correct."""
    hass = _make_hass()
    fire_transaction_new(
        hass,
        amount=-49.99,
        creditor="Amazon",
        category="subscriptions",
        account_name="Hauptkonto",
    )
    hass.bus.async_fire.assert_called_once()
    event_name, payload = hass.bus.async_fire.call_args.args
    assert event_name == EVENT_TRANSACTION_NEW
    assert payload == {
        "amount": -49.99,
        "creditor": "Amazon",
        "category": "subscriptions",
        "account_name": "Hauptkonto",
    }


def test_fire_transaction_new_default_account_empty():
    """Edge: account_name defaults to empty string."""
    hass = _make_hass()
    fire_transaction_new(hass, amount=0.0, creditor="", category="other")
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["account_name"] == ""


# ---------------------------------------------------------------------------
# fire_balance_changed
# ---------------------------------------------------------------------------

def test_fire_balance_changed_positive_delta():
    """Happy: salary arrives — new > old → positive change."""
    hass = _make_hass()
    fire_balance_changed(hass, "Lohnkonto", old_balance=100.0, new_balance=2500.0)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload == {
        "account_name": "Lohnkonto",
        "old_balance": 100.0,
        "new_balance": 2500.0,
        "change": 2400.0,
    }


def test_fire_balance_changed_negative_delta():
    """Edge: payment outgoing → negative change."""
    hass = _make_hass()
    fire_balance_changed(hass, "Hauptkonto", old_balance=500.0, new_balance=200.0)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["change"] == -300.0


def test_fire_balance_changed_rounds_to_cents():
    """Edge: float arithmetic noise gets rounded to 2 decimals."""
    hass = _make_hass()
    fire_balance_changed(hass, "X", old_balance=10.123456, new_balance=20.987654)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["old_balance"] == 10.12
    assert payload["new_balance"] == 20.99
    assert payload["change"] == 10.86


# ---------------------------------------------------------------------------
# fire_budget_exceeded
# ---------------------------------------------------------------------------

def test_fire_budget_exceeded_computes_overshoot_and_pct():
    """Happy: 250€ spent against 200€ limit → 25% over."""
    hass = _make_hass()
    fire_budget_exceeded(hass, category="food", limit=200.0, actual=250.0)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["category"] == "food"
    assert payload["limit"] == 200.0
    assert payload["actual"] == 250.0
    assert payload["overshoot"] == 50.0
    assert payload["overshoot_pct"] == 25.0


def test_fire_budget_exceeded_zero_limit_guards_against_div_by_zero():
    """Edge: limit=0 must not raise ZeroDivisionError; pct defaults to 0."""
    hass = _make_hass()
    fire_budget_exceeded(hass, category="other", limit=0.0, actual=15.0)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["overshoot"] == 15.0
    assert payload["overshoot_pct"] == 0


def test_fire_budget_exceeded_marginal_overshoot():
    """Edge: 0.01€ over budget still fires; rounding preserved."""
    hass = _make_hass()
    fire_budget_exceeded(hass, category="loans", limit=1000.0, actual=1000.01)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["overshoot"] == 0.01
    assert payload["overshoot_pct"] == 0.0  # 0.001% rounds to 0.0


# ---------------------------------------------------------------------------
# fire_recurring_detected
# ---------------------------------------------------------------------------

def test_fire_recurring_detected_default_frequency():
    """Happy: monthly is the default."""
    hass = _make_hass()
    fire_recurring_detected(hass, creditor="Netflix", amount=12.99)
    event_name, payload = hass.bus.async_fire.call_args.args
    assert event_name == EVENT_RECURRING_DETECTED
    assert payload == {
        "creditor": "Netflix",
        "amount": 12.99,
        "frequency": "monthly",
    }


def test_fire_recurring_detected_custom_frequency():
    """Edge: weekly/annually frequencies are forwarded as-is."""
    hass = _make_hass()
    fire_recurring_detected(hass, creditor="GEZ", amount=18.36, frequency="quarterly")
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["frequency"] == "quarterly"


# ---------------------------------------------------------------------------
# Cross-cut: event-name constants are domain-prefixed
# ---------------------------------------------------------------------------

def test_event_names_are_domain_prefixed():
    """The fd_ prefix matches the documented automation contract."""
    assert EVENT_TRANSACTION_NEW == "finance_dashboard_transaction_new"
    assert EVENT_BALANCE_CHANGED == "finance_dashboard_balance_changed"
    assert EVENT_BUDGET_EXCEEDED == "finance_dashboard_budget_exceeded"
    assert EVENT_RECURRING_DETECTED == "finance_dashboard_recurring_detected"
