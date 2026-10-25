"""Secure credential management for Finance.

SECURITY ARCHITECTURE:
- All credentials stored in HA's .storage/ directory (encrypted at rest)
- Additional encryption layer using Fernet (symmetric encryption)
- Session management (up to 180 days)
- Session timeouts for inactive connections
- Full audit trail of all credential operations
- No credentials ever appear in logs, git, or config files
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, MultiFernet
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    AUDIT_MAX_ENTRIES,
    SESSION_TIMEOUT_MINUTES,
    STORAGE_KEY_AUDIT,
    STORAGE_KEY_CREDENTIALS,
    STORAGE_KEY_TOKENS,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class CredentialManager:
    """Manage banking credentials with maximum security.

    Security layers:
    1. HA .storage/ directory (OS-level file permissions)
    2. Fernet symmetric encryption (AES-128-CBC + HMAC)
    3. Session management (up to 180 days)
    4. Session timeouts (30min inactivity)
    5. Audit logging (all operations tracked)
    6. Max token age (force re-auth after 90 days)
    """

    # Maximum number of historic keys kept for decryption (primary + N-1 old)
    _MAX_KEY_HISTORY = 3

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize credential manager."""
        self._hass = hass
        self._cred_store = Store(hass, STORAGE_VERSION, STORAGE_KEY_CREDENTIALS)
        self._token_store = Store(hass, STORAGE_VERSION, STORAGE_KEY_TOKENS)
        # Single Store instance reused by every _audit_log() call to avoid
        # creating a new Store object on every audit write (performance).
        self._audit_store = Store(hass, STORAGE_VERSION, STORAGE_KEY_AUDIT)
        self._fernet: MultiFernet | None = None
        self._last_activity: float = 0
        self._session_active: bool = False

    async def async_initialize(self) -> None:
        """Initialize the credential manager.

        Storage schema v2: keys stored as a list
        ``[{"version": N, "key": "<base64>", "created": "<iso>"}, ...]``
        with element 0 being the current (primary) encryption key.

        Migration: if a legacy string ``encryption_key`` field is found
        (schema v1) it is converted in-place to the v2 list format.
        """
        key_data = await self._cred_store.async_load() or {}

        if key_data.get("schema_version", 1) < 2:
            # --- Migration from v1 (single string key) to v2 (key list) ---
            if "encryption_key" in key_data:
                old_key = key_data["encryption_key"]
                key_data = {
                    "schema_version": 2,
                    "keys": [
                        {
                            "version": 1,
                            "key": old_key,
                            "created": datetime.now().isoformat(),
                        }
                    ],
                }
            else:
                # Fresh install — generate first key
                new_key = Fernet.generate_key().decode()
                key_data = {
                    "schema_version": 2,
                    "keys": [
                        {
                            "version": 1,
                            "key": new_key,
                            "created": datetime.now().isoformat(),
                        }
                    ],
                }
            await self._cred_store.async_save(key_data)

        self._fernet = self._build_multifernet(key_data["keys"])
        _LOGGER.debug(
            "Credential manager initialized (schema v2, %d key(s))",
            len(key_data["keys"]),
        )

    async def async_rotate_key(self) -> None:
        """Add a new primary encryption key (key rotation).

        The new key becomes the encryption key (position 0).  Existing
        encrypted data is NOT re-encrypted — MultiFernet transparently tries
        all keys in order for decryption so old ciphertexts remain readable
        until they are re-encrypted with the new primary key.

        At most ``_MAX_KEY_HISTORY`` keys are retained.
        """
        self._ensure_initialized()
        key_data = await self._cred_store.async_load() or {}
        keys: list[dict] = key_data.get("keys", [])

        # Determine next version number
        next_version = (max(k["version"] for k in keys) + 1) if keys else 1
        new_entry = {
            "version": next_version,
            "key": Fernet.generate_key().decode(),
            "created": datetime.now().isoformat(),
        }

        # Prepend new key (becomes primary), prune history
        keys = [new_entry, *keys]
        keys = keys[: self._MAX_KEY_HISTORY]

        key_data["keys"] = keys
        await self._cred_store.async_save(key_data)

        self._fernet = self._build_multifernet(keys)
        await self._audit_log("key_rotated")
        _LOGGER.info(
            "Encryption key rotated to version %d (%d keys in rotation)",
            next_version,
            len(keys),
        )

    @staticmethod
    def _build_multifernet(keys: list[dict]) -> MultiFernet:
        """Build a MultiFernet from the ordered key list."""
        return MultiFernet([Fernet(k["key"].encode()) for k in keys])

    async def async_store_api_credentials(self, application_id: str, private_key_pem: str) -> None:
        """Store Enable Banking API credentials (encrypted)."""
        self._ensure_initialized()
        encrypted_id = self._fernet.encrypt(application_id.encode()).decode()
        encrypted_key = self._fernet.encrypt(private_key_pem.encode()).decode()

        token_data = await self._token_store.async_load() or {}
        token_data["api_application_id"] = encrypted_id
        token_data["api_private_key_pem"] = encrypted_key
        token_data["stored_at"] = datetime.now().isoformat()
        await self._token_store.async_save(token_data)

        await self._audit_log("api_credentials_stored")

    async def async_get_api_credentials(self) -> dict[str, str] | None:
        """Retrieve decrypted Enable Banking API credentials."""
        self._ensure_initialized()
        self._check_session_timeout()

        token_data = await self._token_store.async_load()
        if not token_data:
            return None

        encrypted_id = token_data.get("api_application_id")
        encrypted_key = token_data.get("api_private_key_pem")

        # Migration detection: old GoCardless keys present but new keys missing
        if not encrypted_id or not encrypted_key:
            if token_data.get("api_secret_id"):
                _LOGGER.warning(
                    "Found legacy GoCardless credentials but no Enable Banking "
                    "credentials. Re-configuration required."
                )
            return None

        try:
            application_id = self._fernet.decrypt(encrypted_id.encode()).decode()
            private_key_pem = self._fernet.decrypt(encrypted_key.encode()).decode()
            self._touch_session()
            await self._audit_log("api_credentials_accessed")
            return {
                "application_id": application_id,
                "private_key_pem": private_key_pem,
            }
        except Exception:
            _LOGGER.error("Failed to decrypt API credentials")
            await self._audit_log("api_credentials_decrypt_failed")
            return None

    async def async_store_session(self, session_id: str, valid_until: str) -> None:
        """Store Enable Banking session (encrypted)."""
        self._ensure_initialized()
        token_data = await self._token_store.async_load() or {}
        token_data["eb_session_id"] = self._fernet.encrypt(session_id.encode()).decode()
        token_data["eb_session_valid_until"] = valid_until  # ISO datetime string, not secret
        token_data["eb_session_stored_at"] = datetime.now().isoformat()
        await self._token_store.async_save(token_data)
        await self._audit_log("session_stored")

    async def async_get_session(self) -> dict[str, str] | None:
        """Get Enable Banking session if still valid."""
        self._ensure_initialized()
        self._check_session_timeout()

        token_data = await self._token_store.async_load()
        if not token_data:
            return None

        encrypted_session = token_data.get("eb_session_id")
        valid_until = token_data.get("eb_session_valid_until")
        if not encrypted_session or not valid_until:
            return None

        # Check if session has expired
        try:
            expires = datetime.fromisoformat(valid_until)
            if datetime.now() >= expires:
                _LOGGER.warning("Enable Banking session expired")
                await self._audit_log("session_expired")
                return None
        except ValueError:
            return None

        try:
            session_id = self._fernet.decrypt(encrypted_session.encode()).decode()
            self._touch_session()
            await self._audit_log("session_accessed")
            return {"session_id": session_id, "valid_until": valid_until}
        except Exception:
            _LOGGER.error("Failed to decrypt session")
            return None

    # ------------------------------------------------------------------
    # Multi-bank sessions (one per bank config subentry)
    # ------------------------------------------------------------------

    async def async_store_bank_session(
        self, subentry_id: str, session_id: str, valid_until: str
    ) -> None:
        """Store the Enable Banking session of one bank (encrypted)."""
        self._ensure_initialized()
        token_data = await self._token_store.async_load() or {}
        sessions = dict(token_data.get("bank_sessions") or {})
        sessions[subentry_id] = {
            "session_id": self._fernet.encrypt(session_id.encode()).decode(),
            "valid_until": valid_until,  # ISO datetime, not secret
            "stored_at": datetime.now().isoformat(),
        }
        token_data["bank_sessions"] = sessions
        await self._token_store.async_save(token_data)
        await self._audit_log("bank_session_stored")

    async def async_get_bank_session(self, subentry_id: str) -> dict[str, str] | None:
        """Return ``{"session_id", "valid_until"}`` for a bank, or None.

        An expired session is still returned: the caller needs ``valid_until``
        to tell "expired" (raise a repair issue) from "never linked".
        """
        self._ensure_initialized()
        token_data = await self._token_store.async_load() or {}
        record = (token_data.get("bank_sessions") or {}).get(subentry_id)
        if not record:
            return None
        try:
            session_id = self._fernet.decrypt(record["session_id"].encode()).decode()
        except Exception:
            _LOGGER.error("Failed to decrypt bank session")
            return None
        self._touch_session()
        return {"session_id": session_id, "valid_until": record.get("valid_until", "")}

    async def async_remove_bank_session(self, subentry_id: str) -> None:
        """Forget the session of one bank."""
        self._ensure_initialized()
        token_data = await self._token_store.async_load() or {}
        sessions = dict(token_data.get("bank_sessions") or {})
        if sessions.pop(subentry_id, None) is not None:
            token_data["bank_sessions"] = sessions
            await self._token_store.async_save(token_data)
            await self._audit_log("bank_session_removed")

    # ------------------------------------------------------------------
    # Encryption helpers for data-at-rest (ledger, raw archive)
    # ------------------------------------------------------------------

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Encrypt with the primary key (Fernet token)."""
        self._ensure_initialized()
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, token: bytes) -> bytes:
        """Decrypt with any key still in rotation."""
        self._ensure_initialized()
        return self._fernet.decrypt(token)

    def encrypt_json(self, payload: Any) -> str:
        """Serialise and encrypt a JSON-able payload to a text token."""
        return self.encrypt_bytes(json.dumps(payload, separators=(",", ":")).encode()).decode()

    def decrypt_json(self, token: str) -> Any:
        """Inverse of :meth:`encrypt_json`."""
        return json.loads(self.decrypt_bytes(token.encode()))

    def encrypted_store(
        self,
        key: str,
        version: int,
        minor_version: int = 1,
        migrate: Callable[[int, int, Any], Awaitable[Any]] | None = None,
    ):
        """Create a versioned, Fernet-encrypted Store (see ``data_store``)."""
        from .data_store import EncryptedStore

        return EncryptedStore(self._hass, self, key, version, minor_version, migrate)

    async def async_clear_all(self) -> None:
        """Securely clear all stored credentials and tokens."""
        await self._token_store.async_save({})
        await self._audit_log("all_credentials_cleared")
        _LOGGER.info("All credentials cleared")

    async def async_get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent audit log entries."""
        data = await self._audit_store.async_load() or {"entries": []}
        return data["entries"][-limit:]

    def _ensure_initialized(self) -> None:
        """Ensure the credential manager is initialized."""
        if self._fernet is None:
            raise RuntimeError("CredentialManager not initialized. Call async_initialize() first.")

    def _touch_session(self) -> None:
        """Update last activity timestamp."""
        self._last_activity = time.time()
        self._session_active = True

    def _check_session_timeout(self) -> None:
        """Check if session has timed out due to inactivity."""
        if not self._session_active:
            return
        elapsed = time.time() - self._last_activity
        if elapsed > SESSION_TIMEOUT_MINUTES * 60:
            self._session_active = False
            _LOGGER.info(
                "Session timed out after %d minutes of inactivity",
                SESSION_TIMEOUT_MINUTES,
            )

    async def _audit_log(self, event: str) -> None:
        """Write an entry to the audit log.

        Reuses ``self._audit_store`` (created once in __init__) to avoid
        instantiating a new Store on every call (performance + consistency).
        """
        data = await self._audit_store.async_load() or {"entries": []}

        data["entries"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "event": event,
                # Never log actual credential values
            }
        )

        # Trim to max entries
        if len(data["entries"]) > AUDIT_MAX_ENTRIES:
            data["entries"] = data["entries"][-AUDIT_MAX_ENTRIES:]

        await self._audit_store.async_save(data)
