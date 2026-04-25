"""Pytest configuration for Finance unit tests.

These are pure-Python unit tests that do not need a running Home Assistant
instance.

Problem: the homeassistant-custom-component pytest plugin calls
``disable_socket()`` in ``pytest_runtest_setup()`` (which runs before fixture
setup).  On Windows, even SelectorEventLoop.__init__ opens a loopback socket,
which then hits the blocker.

Solution: override ``event_loop`` so it temporarily re-enables sockets just
long enough to construct the loop, then re-disables them.

The ``pytest_socket.enable_socket()`` function restores the original
``socket.socket`` class so any subsequent socket creation works normally until
``disable_socket()`` is called again.
"""
import asyncio
import sys
import socket as _socket_module

import pytest
import pytest_socket


def _make_loop():
    """Build an event loop with sockets temporarily enabled."""
    # Save original socket constructor (may already be patched by pytest-socket)
    original = _socket_module.socket

    # Force-restore the real socket so the loop can init
    pytest_socket.enable_socket()
    try:
        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop()
        else:
            loop = asyncio.new_event_loop()
    finally:
        # Re-lock sockets (only localhost, allow unix) – mirrors HA plugin policy
        pytest_socket.socket_allow_hosts(["127.0.0.1"])
        pytest_socket.disable_socket(allow_unix_socket=True)

    return loop


@pytest.fixture(scope="function")
def event_loop():
    """Provide a socket-safe event loop for pure unit tests."""
    loop = _make_loop()
    yield loop
    loop.close()
