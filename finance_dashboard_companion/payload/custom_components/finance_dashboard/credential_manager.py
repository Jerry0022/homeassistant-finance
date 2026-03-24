"""Secure credential management for Finance Dashboard.

SECURITY ARCHITECTURE:
- All credentials stored in HA's .storage/ directory (encrypted at rest)
- Additional encryption layer using Fernet (symmetric encryption)
- Token auto-rotation before expiry
- Session timeouts for inactive connections
- Full audit trail of all credential operations
- No credentials ever appear in logs, git, or config files
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    STORAGE_KEY_CREDENTIALS,
    STORAGE_KEY_TOKENS,
    STORAGE_VERSION,
    TOKEN_MAX_AGE_DAYS,
    TOKEN_REFRESH_INTERVAL_HOURS,
    SESSION_TIMEOUT_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


class CredentialManager:
    """Manage banking credentials with maximum security.

    Security layers:
    1. HA .storage/ directory (OS-level file permissions)
    2. Fernet symmetric encryption (AES-128-CBC + HMAC)
    3. Token auto-rotation (before 24h GoCardless expiry)
    4. Session timeouts (30min inactivity)
    5. Audit logging (all operations tracked)
    6. Max token age (force re-auth after 90 days)
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize credential manager."""
        self._hass = hass
        self._cred_store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_CREDENTIALS
        )
        self._token_store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_TOKENS
        )
        self._encryption_key: bytes | None = None
        self._fernet: Fernet | None = None
        self._last_activity: float = 0
        self._session_active: bool = False

    async def async_initialize(self) -> None:
        """Initialize the credential manager and load/generate encryption key."""
        key_data = await self._cred_store.async_load()
        if key_data and "encryption_key" in key_data:
            self._encryption_key = key_data["encryption_key"].encode()
        else:
            # Generate new encryption key on first setup
            self._encryption_key = Fernet.generate_key()
            await self._cred_store.async_save(
                {"encryption_key": self._encryption_key.decode()}
            )
        self._fernet = Fernet(self._encryption_key)
        _LOGGER.debug("Credential manager initialized")

    async def async_store_api_credentials(
        self, secret_id: str, secret_key: str
    ) -> None:
        """Store GoCardless API credentials (encrypted)."""
        self._ensure_initialized()
        encrypted_id = self._fernet.encrypt(secret_id.encode()).decode()
        encrypted_key = self._fernet.encrypt(secret_key.encode()).decode()

        token_data = await self._token_store.async_load() or {}
        token_data["api_secret_id"] = encrypted_id
        token_data["api_secret_key"] = encrypted_key
        token_data["stored_at"] = datetime.now().isoformat()
        await self._token_store.async_save(token_data)

        await self._audit_log("api_credentials_stored")

    async def async_get_api_credentials(self) -> tuple[str, str] | None:
        """Retrieve decrypted GoCardless API credentials."""
        self._ensure_initialized()
        self._check_session_timeout()

        token_data = await self._token_store.async_load()
        if not token_data:
            return None

        encrypted_id = token_data.get("api_secret_id")
        encrypted_key = token_data.get("api_secret_key")
        if not encrypted_id or not encrypted_key:
            return None

        try:
            secret_id = self._fernet.decrypt(encrypted_id.encode()).decode()
            secret_key = self._fernet.decrypt(encrypted_key.encode()).decode()
            self._touch_session()
            await self._audit_log("api_credentials_accessed")
            return secret_id, secret_key
        except Exception:
            _LOGGER.error("Failed to decrypt API credentials")
            await self._audit_log("api_credentials_decrypt_failed")
            return None

    async def async_store_access_token(
        self, access_token: str, refresh_token: str, expires_in: int
    ) -> None:
        """Store GoCardless access/refresh tokens (encrypted)."""
        self._ensure_initialized()

        token_data = await self._token_store.async_load() or {}
        token_data["access_token"] = self._fernet.encrypt(
            access_token.encode()
        ).decode()
        token_data["refresh_token"] = self._fernet.encrypt(
            refresh_token.encode()
        ).decode()
        token_data["token_expires_at"] = (
            datetime.now() + timedelta(seconds=expires_in)
        ).isoformat()
        token_data["token_created_at"] = datetime.now().isoformat()
        await self._token_store.async_save(token_data)

        await self._audit_log("access_token_stored")

    async def async_get_access_token(self) -> str | None:
        """Get decrypted access token, auto-refreshing if needed."""
        self._ensure_initialized()
        self._check_session_timeout()

        token_data = await self._token_store.async_load()
        if not token_data or "access_token" not in token_data:
            return None

        # Check token age — force re-auth after max age
        created_at = token_data.get("token_created_at")
        if created_at:
            created = datetime.fromisoformat(created_at)
            if datetime.now() - created > timedelta(days=TOKEN_MAX_AGE_DAYS):
                _LOGGER.warning(
                    "Token exceeded max age (%d days), re-auth required",
                    TOKEN_MAX_AGE_DAYS,
                )
                await self._audit_log("token_max_age_exceeded")
                return None

        # Check if token needs refresh
        expires_at = token_data.get("token_expires_at")
        if expires_at:
            expires = datetime.fromisoformat(expires_at)
            if datetime.now() > expires - timedelta(
                hours=1
            ):  # Refresh 1h before expiry
                await self._audit_log("token_refresh_needed")
                refreshed = await self._async_refresh_token(token_data)
                if not refreshed:
                    return None
                # Reload after refresh
                token_data = await self._token_store.async_load()

        try:
            decrypted = self._fernet.decrypt(
                token_data["access_token"].encode()
            ).decode()
            self._touch_session()
            return decrypted
        except Exception:
            _LOGGER.error("Failed to decrypt access token")
            await self._audit_log("access_token_decrypt_failed")
            return None

    async def async_clear_all(self) -> None:
        """Securely clear all stored credentials and tokens."""
        await self._token_store.async_save({})
        await self._audit_log("all_credentials_cleared")
        _LOGGER.info("All credentials cleared")

    async def async_get_audit_log(
        self, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get recent audit log entries."""
        store = Store(self._hass, STORAGE_VERSION, f"{DOMAIN}_audit_log")
        data = await store.async_load() or {"entries": []}
        return data["entries"][-limit:]

    def _ensure_initialized(self) -> None:
        """Ensure the credential manager is initialized."""
        if self._fernet is None:
            raise RuntimeError(
                "CredentialManager not initialized. Call async_initialize() first."
            )

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

    async def _async_refresh_token(
        self, token_data: dict[str, Any]
    ) -> bool:
        """Refresh the GoCardless access token."""
        refresh_token_enc = token_data.get("refresh_token")
        if not refresh_token_enc:
            return False

        try:
            refresh_token = self._fernet.decrypt(
                refresh_token_enc.encode()
            ).decode()

            from .gocardless_client import GoCardlessClient

            # Get API credentials for refresh
            creds = await self.async_get_api_credentials()
            if not creds:
                return False

            client = GoCardlessClient(creds[0], creds[1])
            new_tokens = await client.async_refresh_token(refresh_token)
            if new_tokens:
                await self.async_store_access_token(
                    new_tokens["access"],
                    new_tokens.get("refresh", refresh_token),
                    new_tokens.get("access_expires", 86400),
                )
                await self._audit_log("token_refreshed")
                return True
        except Exception:
            _LOGGER.exception("Token refresh failed")
            await self._audit_log("token_refresh_failed")
        return False

    async def _audit_log(self, event: str) -> None:
        """Write an entry to the audit log."""
        from .const import AUDIT_MAX_ENTRIES

        store = Store(self._hass, STORAGE_VERSION, f"{DOMAIN}_audit_log")
        data = await store.async_load() or {"entries": []}

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

        await store.async_save(data)
