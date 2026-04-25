"""Tests for MultiFernet key rotation in CredentialManager (S2).

Tests:
1. Encrypt with key1, rotate, decrypt still works (old ciphertext readable).
2. Encrypt with key2 (after rotate), decrypt works.
3. Key history is capped at _MAX_KEY_HISTORY.
4. Migration from v1 (single string key) to v2 (key list) is transparent.
5. audit log receives 'key_rotated' event on rotation.
"""
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Minimal stubs for HA dependencies
# ---------------------------------------------------------------------------

class FakeStore:
    """In-memory substitute for homeassistant.helpers.storage.Store."""

    def __init__(self, *args, **kwargs):
        self._data = None

    async def async_load(self):
        return self._data

    async def async_save(self, data):
        import copy
        self._data = copy.deepcopy(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager():
    """Return a CredentialManager with all HA deps fully stubbed out."""
    from custom_components.finance_dashboard.credential_manager import CredentialManager

    mgr = CredentialManager.__new__(CredentialManager)
    mgr._hass = MagicMock()
    mgr._cred_store = FakeStore()
    mgr._token_store = FakeStore()
    mgr._audit_store = FakeStore()
    mgr._fernet = None
    mgr._last_activity = 0.0
    mgr._session_active = False
    return mgr


def _patch_store():
    """Context manager that replaces all Store() calls with FakeStore()."""
    return patch(
        "custom_components.finance_dashboard.credential_manager.Store",
        side_effect=lambda *a, **kw: FakeStore(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_encrypt_rotate_decrypt_old_ciphertext():
    """Ciphertext produced by key1 must still decrypt after rotation to key2."""
    with _patch_store():
        mgr = _make_manager()
        await mgr.async_initialize()

        # Encrypt some data with the initial key
        plaintext = b"secret-account-data"
        ciphertext = mgr._fernet.encrypt(plaintext)

        # Rotate — new key becomes primary
        await mgr.async_rotate_key()

        # Old ciphertext must still decrypt correctly
        assert mgr._fernet.decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_encrypt_with_new_key_after_rotation():
    """Ciphertext produced after rotation decrypts with the post-rotate key."""
    with _patch_store():
        mgr = _make_manager()
        await mgr.async_initialize()
        await mgr.async_rotate_key()

        plaintext = b"new-secret-data"
        ciphertext = mgr._fernet.encrypt(plaintext)
        assert mgr._fernet.decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_key_history_capped():
    """After _MAX_KEY_HISTORY + 1 rotations the key list must not exceed the cap."""
    with _patch_store():
        mgr = _make_manager()
        await mgr.async_initialize()

        cap = mgr._MAX_KEY_HISTORY
        for _ in range(cap + 2):
            await mgr.async_rotate_key()

        key_data = await mgr._cred_store.async_load()
        assert len(key_data["keys"]) <= cap


@pytest.mark.asyncio
async def test_migration_v1_to_v2():
    """A legacy v1 store (single encryption_key string) must be migrated transparently."""
    old_key = Fernet.generate_key().decode()
    old_fernet = Fernet(old_key.encode())
    old_ciphertext = old_fernet.encrypt(b"legacy-secret")

    with _patch_store():
        mgr = _make_manager()
        # Plant a v1-style store payload
        mgr._cred_store._data = {"encryption_key": old_key}

        await mgr.async_initialize()

        # Store must be upgraded to v2
        key_data = await mgr._cred_store.async_load()
        assert key_data["schema_version"] == 2
        assert isinstance(key_data["keys"], list)
        assert len(key_data["keys"]) == 1

        # The migrated manager must decrypt v1 ciphertexts
        assert mgr._fernet.decrypt(old_ciphertext) == b"legacy-secret"


@pytest.mark.asyncio
async def test_audit_log_on_rotate():
    """async_rotate_key must write a 'key_rotated' audit entry.

    Since F7 the CredentialManager reuses a single ``_audit_store`` instance
    created in ``__init__`` (rather than calling ``Store()`` inside
    ``_audit_log``).  We therefore wire the spy store directly on the manager
    instance instead of patching the ``Store`` constructor.
    """
    audit_data = {}

    class SpyStore(FakeStore):
        async def async_save(self, data):
            await super().async_save(data)
            if "entries" in data:
                audit_data.update(data)

    mgr = _make_manager()
    # Replace the pre-created audit store with the spy variant so writes
    # are captured without patching the Store constructor.
    mgr._audit_store = SpyStore()
    await mgr.async_initialize()
    await mgr.async_rotate_key()

    events = [e["event"] for e in audit_data.get("entries", [])]
    assert "key_rotated" in events
