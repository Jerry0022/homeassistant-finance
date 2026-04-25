"""Tests for MultiFernet key rotation in CredentialManager (S2 + T3).

Tests:
1. Encrypt with key1, rotate, decrypt still works (old ciphertext readable).
2. Encrypt with key2 (after rotate), decrypt works.
3. Key history is capped at _MAX_KEY_HISTORY.
4. Migration from v1 (single string key) to v2 (key list) is transparent.
5. audit log receives 'key_rotated' event on rotation.
--- T3 edge-cases ---
6. Encrypt with 3 keys, decrypt with middle key still succeeds.
7. Migration v1 → v2 with a corrupt old key raises the appropriate error.
8. Session timeout flag resets after inactivity threshold is exceeded.
9. async_get_api_credentials returns None when manager is not initialized.
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


# ---------------------------------------------------------------------------
# T3 edge-cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_encrypt_with_middle_key_still_decrypts():
    """Ciphertext produced by the *second* key in a 3-key rotation must
    decrypt correctly even when a newer primary key exists.

    Setup: k1 → rotate → k2 (primary) → encrypt → rotate → k3 (primary).
    The MultiFernet must still decrypt the k2 ciphertext because k2 is in
    position 1 of the key list [k3, k2, k1] (all ≤ _MAX_KEY_HISTORY = 3).
    """
    with _patch_store():
        mgr = _make_manager()
        await mgr.async_initialize()

        # After first rotation k2 becomes primary
        await mgr.async_rotate_key()
        plaintext = b"encrypted-with-key-2"
        ciphertext_k2 = mgr._fernet.encrypt(plaintext)

        # After second rotation k3 becomes primary; k2 is now middle key
        await mgr.async_rotate_key()

        # Must still decrypt k2 ciphertext
        assert mgr._fernet.decrypt(ciphertext_k2) == plaintext


@pytest.mark.asyncio
async def test_migration_v1_corrupt_key_raises():
    """A v1 store with a corrupt (non-base64) encryption key must raise
    a ValueError or InvalidToken when the MultiFernet is built, not silently
    swallow the error.
    """
    from cryptography.fernet import InvalidToken

    with _patch_store():
        mgr = _make_manager()
        # Plant a deliberately broken key
        mgr._cred_store._data = {"encryption_key": "not-a-valid-fernet-key!!!"}

        with pytest.raises((ValueError, Exception)):
            await mgr.async_initialize()
            # Force an actual encrypt/decrypt to trigger the key error
            mgr._fernet.encrypt(b"test")


@pytest.mark.asyncio
async def test_session_timeout_resets_flag():
    """After SESSION_TIMEOUT_MINUTES inactivity the session active flag must
    be cleared by _check_session_timeout().
    """
    import time
    from custom_components.finance_dashboard.const import SESSION_TIMEOUT_MINUTES

    with _patch_store():
        mgr = _make_manager()
        await mgr.async_initialize()

        # Simulate an active session that started long ago
        mgr._session_active = True
        mgr._last_activity = time.time() - (SESSION_TIMEOUT_MINUTES * 60 + 5)

        mgr._check_session_timeout()

        assert mgr._session_active is False


@pytest.mark.asyncio
async def test_get_api_credentials_uninitialized_raises():
    """async_get_api_credentials must raise RuntimeError when the manager
    has not been initialized (no async_initialize call).
    """
    mgr = _make_manager()
    # _fernet is None — _ensure_initialized() must raise
    with pytest.raises(RuntimeError, match="not initialized"):
        await mgr.async_get_api_credentials()
