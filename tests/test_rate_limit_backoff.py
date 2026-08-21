"""Tests for rate-limit backoff and the attended/background split.

PSD2 RTS Art. 36(5)(b) caps AISP access at four times per 24h *only when
the user is not in session*.  With PSU headers present the call is attended
and the cap does not apply — so an attended refresh must neither be blocked
by the gate nor punished with a day-long backoff.

Enable Banking documents a 6h retry for background fetches; the previous
implementation blocked until midnight, turning a 07:00 rate limit into a
lost day.
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import pytest
from homeassistant.util import dt as dt_util


def _make_manager():
    """Return a manager with only the rate-limit fields initialised."""
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    mgr = FinanceDashboardManager.__new__(FinanceDashboardManager)
    mgr._rate_limited_until = None

    class _Hass:
        data: ClassVar[dict] = {}

    mgr._hass = _Hass()
    return mgr


# ---------------------------------------------------------------------------
# Backoff duration
# ---------------------------------------------------------------------------


def test_background_backoff_is_six_hours_not_midnight():
    """A background 429 must pause ~6h, not until the next calendar day."""
    from custom_components.finance_dashboard.const import RATE_LIMIT_BACKOFF_HOURS

    mgr = _make_manager()
    now = dt_util.now()
    mgr._set_rate_limited()

    waited = mgr._rate_limited_until - now
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Either the 6h backoff, or midnight when that comes sooner
    expected = min(midnight, now + timedelta(hours=RATE_LIMIT_BACKOFF_HOURS))
    assert abs((mgr._rate_limited_until - expected).total_seconds()) < 5
    assert waited <= timedelta(hours=RATE_LIMIT_BACKOFF_HOURS) + timedelta(seconds=5)


def test_attended_backoff_is_minutes():
    """An attended 429 is transient upstream noise, not the 4/day rule."""
    from custom_components.finance_dashboard.const import (
        RATE_LIMIT_ATTENDED_BACKOFF_MINUTES,
    )

    mgr = _make_manager()
    now = dt_util.now()
    mgr._set_rate_limited(attended=True)

    waited = mgr._rate_limited_until - now
    assert waited <= timedelta(minutes=RATE_LIMIT_ATTENDED_BACKOFF_MINUTES) + timedelta(seconds=5)
    assert waited > timedelta(0)


def test_backoff_never_exceeds_midnight():
    """Waiting past midnight is pointless — the ASPSP day counter resets."""
    mgr = _make_manager()
    now = dt_util.now()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # A bank asking for a 3-day pause must still not outlive the reset
    mgr._set_rate_limited(now + timedelta(days=3))
    assert mgr._rate_limited_until == midnight


def test_retry_after_header_wins_over_default():
    """The bank's own Retry-After is authoritative below the midnight cap."""
    mgr = _make_manager()
    now = dt_util.now()
    retry_at = now + timedelta(minutes=90)

    mgr._set_rate_limited(retry_at)

    assert abs((mgr._rate_limited_until - retry_at).total_seconds()) < 5


def test_rate_limit_is_persisted_for_the_setup_gate():
    """The fresh-setup client factory reads this key — it must be written."""
    from custom_components.finance_dashboard.api._helpers import _GLOBAL_RATE_LIMIT_KEY
    from custom_components.finance_dashboard.const import DOMAIN

    mgr = _make_manager()
    mgr._set_rate_limited()

    stored = mgr._hass.data[DOMAIN][_GLOBAL_RATE_LIMIT_KEY]
    assert stored == mgr._rate_limited_until.isoformat()


# ---------------------------------------------------------------------------
# The endpoint gate
# ---------------------------------------------------------------------------


class _FakeUser:
    is_admin = True


class _FakeRequest:
    def __init__(self, hass, remote=None):
        self.app = {"hass": hass}
        self.remote = remote
        self._data = {"hass_user": _FakeUser()}

    def get(self, key, default=None):
        return self._data.get(key, default)


class _FakeManager:
    def __init__(self, rate_limited_until):
        self.rate_limited_until = rate_limited_until
        self.calls: list = []

    def get_refresh_status(self):
        return {"rate_limited_until": self.rate_limited_until}

    async def async_refresh_transactions(self, psu_ip=None):
        self.calls.append(psu_ip)
        return []


@pytest.fixture
def refresh_view(monkeypatch):
    """Return (view, install_manager) with the manager lookup patched."""
    from custom_components.finance_dashboard.api import refresh as refresh_mod

    holder: dict = {}

    def _install(manager):
        holder["manager"] = manager
        monkeypatch.setattr(refresh_mod, "_get_manager", lambda hass: manager)
        return manager

    return refresh_mod.FinanceDashboardRefreshTriggerView(), _install


@pytest.mark.asyncio
async def test_attended_refresh_is_not_gated(refresh_view):
    """The refresh button must work even while the background gate is set.

    Regression: a rate limit locked the manual refresh out entirely, so the
    user could not fetch data the bank would have served.
    """
    view, install = refresh_view
    manager = install(_FakeManager(dt_util.now() + timedelta(hours=5)))

    class _Hass:
        data: ClassVar[dict] = {}

    await view.post(_FakeRequest(_Hass(), remote="192.168.1.50"))

    assert manager.calls == ["192.168.1.50"]


@pytest.mark.asyncio
async def test_background_refresh_is_gated(refresh_view):
    """Without a PSU IP the call is unattended and the cap does apply."""
    import json

    view, install = refresh_view
    manager = install(_FakeManager(dt_util.now() + timedelta(hours=5)))

    class _Hass:
        data: ClassVar[dict] = {}

    response = await view.post(_FakeRequest(_Hass(), remote=None))

    assert manager.calls == []
    assert json.loads(response.body)["reason"] == "rate_limited"


# ---------------------------------------------------------------------------
# Attended refresh-on-open policy
# ---------------------------------------------------------------------------


class _Entry:
    def __init__(self, options=None):
        self.options = options or {}
        self.data = {}


def _status_manager(options=None):
    """Manager with just enough state for get_refresh_status()."""
    from custom_components.finance_dashboard.manager import FinanceDashboardManager

    mgr = FinanceDashboardManager.__new__(FinanceDashboardManager)
    mgr._entry = _Entry(options)
    mgr._refresh_in_flight = False
    mgr._last_refresh = None
    mgr._rate_limited_until = None
    mgr._last_refresh_stats = {}
    mgr._accounts = []
    mgr._transactions = []
    mgr._balances = {}
    mgr._demo_mode = False
    return mgr


def test_auto_refresh_defaults_are_exposed():
    """The panel reads policy from status — it must not hardcode defaults."""
    from custom_components.finance_dashboard.const import (
        DEFAULT_AUTO_REFRESH_MAX_AGE_MINUTES,
        DEFAULT_AUTO_REFRESH_ON_OPEN,
    )

    status = _status_manager().get_refresh_status()

    assert status["auto_refresh_on_open"] is DEFAULT_AUTO_REFRESH_ON_OPEN
    assert status["auto_refresh_max_age_seconds"] == (
        DEFAULT_AUTO_REFRESH_MAX_AGE_MINUTES * 60
    )


def test_auto_refresh_can_be_disabled():
    """Opting out must actually reach the panel."""
    from custom_components.finance_dashboard.const import OPT_AUTO_REFRESH_ON_OPEN

    status = _status_manager({OPT_AUTO_REFRESH_ON_OPEN: False}).get_refresh_status()
    assert status["auto_refresh_on_open"] is False


def test_auto_refresh_threshold_is_configurable():
    from custom_components.finance_dashboard.const import (
        OPT_AUTO_REFRESH_MAX_AGE_MINUTES,
    )

    status = _status_manager({OPT_AUTO_REFRESH_MAX_AGE_MINUTES: 30}).get_refresh_status()
    assert status["auto_refresh_max_age_seconds"] == 1800


@pytest.mark.parametrize("bad", [0, -5, "", None, "abc"])
def test_auto_refresh_threshold_never_collapses_to_zero(bad):
    """A zero threshold would refresh on every open — that IS polling."""
    from custom_components.finance_dashboard.const import (
        OPT_AUTO_REFRESH_MAX_AGE_MINUTES,
    )

    status = _status_manager({OPT_AUTO_REFRESH_MAX_AGE_MINUTES: bad}).get_refresh_status()
    assert status["auto_refresh_max_age_seconds"] >= 60
