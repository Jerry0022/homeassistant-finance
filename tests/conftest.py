"""Pytest configuration and shared fixtures for Finance Dashboard tests.

Design notes
------------
pytest-homeassistant-custom-component (phcc) installs a custom event loop
policy (HassEventLoopPolicy) at module-load time via top-level code, and
then monkey-patches asyncio.set_event_loop_policy to a no-op so nothing
can override it afterwards.

On Windows the HassEventLoopPolicy creates a ProactorEventLoop, which
needs socket.socketpair() for its internal self-pipe.  pytest-socket
(bundled with phcc) blocks socket creation, causing all tests to ERROR
during the event_loop fixture setup.  This is a pure local-dev problem —
Linux CI uses SelectorEventLoop and is unaffected.

Fix: restore the real asyncio.set_event_loop_policy using the original
from the asyncio module and reset the policy to DefaultEventLoopPolicy
before any tests run.  This is done in pytest_configure so it fires
before pytest-asyncio tries to create the event loop fixture.
"""

from __future__ import annotations

import asyncio
import sys

import pytest


# ---------------------------------------------------------------------------
# Windows / pytest-socket compatibility fix
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Undo the HA event loop policy monkey-patch before any tests run.

    pytest-homeassistant-custom-component (phcc) executes at module-load time:
        asyncio.set_event_loop_policy(HassEventLoopPolicy(False))
        asyncio.set_event_loop_policy = lambda policy: None   # blocks overrides

    On Windows both ProactorEventLoop and WindowsSelectorEventLoop need
    socket.socketpair() for the internal self-pipe — which pytest-socket
    (also bundled with phcc) blocks.

    Fix:
    1. Restore the real set_event_loop_policy from asyncio.events.
    2. Install WindowsSelectorEventLoopPolicy on Windows (lighter than Proactor).
    3. In pytest_runtest_setup (below) re-enable sockets after phcc disables them,
       because the event loop needs to create its self-pipe socket.
    """
    import asyncio.events as _ev

    # Step 1: restore the real setter
    asyncio.set_event_loop_policy = _ev.set_event_loop_policy  # type: ignore[assignment]

    # Step 2: switch to a non-Proactor policy on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    else:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


@pytest.fixture
def event_loop_policy():  # type: ignore[no-untyped-def]
    """Return an event loop policy that works on Windows with pytest-socket.

    pytest-homeassistant-custom-component disables all sockets (including
    AF_INET socketpair used by Windows event loop self-pipes).  By providing
    a custom event_loop_policy fixture we can temporarily enable sockets
    around loop creation and teardown.

    pytest-asyncio calls new_event_loop() on this policy to create and
    clean up loops — so we wrap new_event_loop to enable sockets first.
    """
    try:
        import pytest_socket as _ps
        _socket_guard_active = True
    except ImportError:
        _ps = None  # type: ignore[assignment]
        _socket_guard_active = False

    if sys.platform == "win32":
        base_policy = asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
    else:
        base_policy = asyncio.DefaultEventLoopPolicy()

    if not _socket_guard_active:
        return base_policy

    class _SocketPermissivePolicy(type(base_policy)):  # type: ignore[misc]
        """Wraps new_event_loop to temporarily enable sockets on Windows."""

        def new_event_loop(self) -> asyncio.AbstractEventLoop:
            _ps.enable_socket()
            try:
                loop = super().new_event_loop()
            finally:
                _ps.disable_socket(allow_unix_socket=True)
            return loop

    return _SocketPermissivePolicy()


# ---------------------------------------------------------------------------
# pytest-homeassistant-custom-component: allow loading custom integrations
# ---------------------------------------------------------------------------

@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):  # type: ignore[no-untyped-def]
    """Enable loading of custom integrations.

    NOT autouse — only integration tests that spin up a real HA instance
    should request this fixture.  Unit/contract tests must not, to avoid
    pulling in the HA event loop setup.
    """
    yield


# ---------------------------------------------------------------------------
# Minimal hass stub — for integration tests that need a full HA instance
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_hass(hass):  # type: ignore[no-untyped-def]
    """Return a real (but minimal) HomeAssistant test instance.

    Provided by pytest-homeassistant-custom-component.
    Tests that need a fully-configured entry should use `hass` directly;
    this alias exists so test modules have a descriptive fixture name.
    """
    return hass
