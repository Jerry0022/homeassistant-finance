"""Tests for OAuth state validation in FinanceDashboardManager (S4).

Covers:
1. register → validate (success, one-time-use)
2. register → validate twice (second call fails — one-time-use)
3. register → wait TTL → validate (fails — expired)
4. validate without prior register (fails)
5. Multiple states: validate correct one, others unaffected
6. Timezone mismatch: UTC-stored state validated with naive timestamp (F3)
7. Unbounded dict eviction: capped at _OAUTH_STATES_MAX (F5)
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager():
    """Return a FinanceDashboardManager with only oauth state fields init'd."""
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    mgr = FinanceDashboardManager.__new__(FinanceDashboardManager)
    mgr._oauth_states = {}
    return mgr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_then_validate_success():
    """A registered state must validate successfully on first use."""
    mgr = _make_manager()
    state = "test-state-abc123"
    await mgr.async_register_oauth_state(state)
    result = await mgr.async_validate_oauth_state(state)
    assert result is True


@pytest.mark.asyncio
async def test_one_time_use():
    """A validated state must be consumed — second validation must fail."""
    mgr = _make_manager()
    state = "one-time-state"
    await mgr.async_register_oauth_state(state)
    assert await mgr.async_validate_oauth_state(state) is True
    # Second validation — state was consumed
    assert await mgr.async_validate_oauth_state(state) is False


@pytest.mark.asyncio
async def test_expired_state_rejected():
    """A state older than _OAUTH_STATE_TTL must be rejected."""
    from custom_components.finance_dashboard import manager as mgr_module

    mgr = _make_manager()
    state = "old-state"

    # Backdate the created timestamp beyond the TTL
    past = (
        datetime.now(timezone.utc) - timedelta(seconds=mgr_module._OAUTH_STATE_TTL + 1)
    ).isoformat()
    mgr._oauth_states[state] = past

    result = await mgr.async_validate_oauth_state(state)
    assert result is False


@pytest.mark.asyncio
async def test_validate_without_register_fails():
    """Validating an unknown state must return False."""
    mgr = _make_manager()
    result = await mgr.async_validate_oauth_state("never-registered")
    assert result is False


@pytest.mark.asyncio
async def test_multiple_states_only_correct_consumed():
    """Only the matching state is consumed; unrelated states remain valid."""
    mgr = _make_manager()
    state_a = "state-aaa"
    state_b = "state-bbb"
    await mgr.async_register_oauth_state(state_a)
    await mgr.async_register_oauth_state(state_b)

    assert await mgr.async_validate_oauth_state(state_a) is True
    # state_b must still be valid
    assert await mgr.async_validate_oauth_state(state_b) is True
    # Both now consumed
    assert await mgr.async_validate_oauth_state(state_a) is False
    assert await mgr.async_validate_oauth_state(state_b) is False


@pytest.mark.asyncio
async def test_timezone_mismatch_safe():
    """Naive timestamp in _oauth_states must not raise TypeError (F3).

    Simulates a state stored by older code (naive datetime, no tzinfo) and
    verifies that async_validate_oauth_state still succeeds without a
    TypeError from naive vs. aware subtraction.
    """
    mgr = _make_manager()
    state = "tz-safe-state"

    # Inject a NAIVE timestamp — as if stored before the F3 fix
    naive_ts = datetime.utcnow().isoformat()  # noqa: DTZ003 — intentionally naive to test F3 guard
    mgr._oauth_states[state] = naive_ts

    # Must not raise, must return True (state is fresh)
    result = await mgr.async_validate_oauth_state(state)
    assert result is True


@pytest.mark.asyncio
async def test_oauth_states_dict_bounded():
    """_oauth_states must evict oldest entries when cap is reached (F5)."""
    from custom_components.finance_dashboard.manager._refresh import (
        _OAUTH_STATES_EVICT,
        _OAUTH_STATES_MAX,
    )

    mgr = _make_manager()

    # Fill to exactly the cap
    for i in range(_OAUTH_STATES_MAX):
        await mgr.async_register_oauth_state(f"state-{i:04d}")

    assert len(mgr._oauth_states) == _OAUTH_STATES_MAX

    # One more insertion must trigger eviction
    await mgr.async_register_oauth_state("state-overflow")

    # After eviction, size must be <= MAX - EVICT + 1
    expected_max = _OAUTH_STATES_MAX - _OAUTH_STATES_EVICT + 1
    assert len(mgr._oauth_states) <= expected_max

    # The newly inserted state must still be present
    assert "state-overflow" in mgr._oauth_states
