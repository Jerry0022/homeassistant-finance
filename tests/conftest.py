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

def _legacy_asyncio_stack() -> bool:
    """True for pytest-asyncio < 1.0 (the stack paired with HA <= 2025.x).

    Newer pytest-homeassistant-custom-component releases ship with
    pytest-asyncio >= 1.0 and manage the loop policy themselves; overriding
    ``event_loop_policy`` there raises ``ScopeMismatch``.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return int(version("pytest-asyncio").split(".")[0]) < 1
    except (PackageNotFoundError, ValueError):
        return False


_LEGACY = _legacy_asyncio_stack()


def _allow_loop_socketpair_on_windows() -> None:
    """Let event-loop self-pipes through pytest-socket on Windows.

    Windows event loops build their self-pipe with ``socket.socketpair()``
    (two AF_INET sockets), which pytest-socket blocks.  Wrap just that call
    so the guard is lifted for its duration only; Linux/macOS use Unix
    sockets and are unaffected.
    """
    if sys.platform != "win32":
        return
    import socket

    real = socket.socketpair

    def _socketpair(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            import pytest_socket as _ps
        except ImportError:
            return real(*args, **kwargs)
        _ps.enable_socket()
        try:
            return real(*args, **kwargs)
        finally:
            _ps.disable_socket(allow_unix_socket=True)

    socket.socketpair = _socketpair  # type: ignore[assignment]


def pytest_configure(config: pytest.Config) -> None:
    """Undo the HA event loop policy monkey-patch (legacy stack only).

    Legacy phcc replaces asyncio.set_event_loop_policy with a no-op and
    installs a Proactor-based policy on Windows, which pytest-socket blocks.
    """
    if not _LEGACY:
        _allow_loop_socketpair_on_windows()
        return
    import asyncio.events as _ev

    asyncio.set_event_loop_policy = _ev.set_event_loop_policy  # type: ignore[assignment]
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    else:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


if _LEGACY:

    @pytest.fixture
    def event_loop_policy():  # type: ignore[no-untyped-def]
        """Event loop policy that tolerates pytest-socket (legacy stack only)."""
        try:
            import pytest_socket as _ps
        except ImportError:
            _ps = None  # type: ignore[assignment]

        if sys.platform == "win32":
            base_policy = asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
        else:
            base_policy = asyncio.DefaultEventLoopPolicy()

        if _ps is None:
            return base_policy

        class _SocketPermissivePolicy(type(base_policy)):  # type: ignore[misc]
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
