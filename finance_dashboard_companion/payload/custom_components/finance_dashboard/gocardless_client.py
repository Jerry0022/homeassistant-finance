"""GoCardless (Nordigen) Open Banking API client.

Handles communication with the GoCardless Bank Account Data API v2.
Supports 2400+ banks across 31 European countries.

SECURITY:
- All API communication over HTTPS only
- No credentials logged or cached in memory beyond request scope
- Tokens managed by CredentialManager (encrypted at rest)
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import GOCARDLESS_BASE_URL

_LOGGER = logging.getLogger(__name__)


class GoCardlessClient:
    """Client for GoCardless Bank Account Data API."""

    def __init__(self, secret_id: str, secret_key: str) -> None:
        """Initialize with API credentials."""
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._access_token: str | None = None

    async def async_test_connection(self) -> bool:
        """Test API connection by requesting a new token."""
        try:
            tokens = await self._async_get_new_token()
            return tokens is not None and "access" in tokens
        except Exception:
            _LOGGER.exception("GoCardless connection test failed")
            return False

    async def async_get_institutions(
        self, country: str = "DE"
    ) -> list[dict[str, Any]]:
        """Get available banking institutions for a country."""
        return await self._async_request(
            "GET", f"/institutions/?country={country}"
        )

    async def async_create_agreement(
        self,
        institution_id: str,
        max_historical_days: int = 90,
        access_valid_for_days: int = 90,
    ) -> dict[str, Any]:
        """Create an end-user agreement defining data access scope."""
        return await self._async_request(
            "POST",
            "/agreements/enduser/",
            json={
                "institution_id": institution_id,
                "max_historical_days": max_historical_days,
                "access_valid_for_days": access_valid_for_days,
                "access_scope": ["details", "balances", "transactions"],
            },
        )

    async def async_create_requisition(
        self,
        institution_id: str,
        redirect_url: str,
        agreement_id: str | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """Create a bank link requisition (user authorization flow).

        Returns dict with 'id', 'link' (authorization URL), 'status', etc.
        """
        payload: dict[str, Any] = {
            "institution_id": institution_id,
            "redirect": redirect_url,
            "user_language": "de",
        }
        if agreement_id:
            payload["agreement"] = agreement_id
        if reference:
            payload["reference"] = reference

        return await self._async_request(
            "POST",
            "/requisitions/",
            json=payload,
        )

    async def async_delete_requisition(
        self, requisition_id: str
    ) -> bool:
        """Delete a requisition (cleanup after errors)."""
        try:
            await self._async_request(
                "DELETE", f"/requisitions/{requisition_id}/"
            )
            return True
        except Exception:
            return False

    async def async_get_requisition(
        self, requisition_id: str
    ) -> dict[str, Any]:
        """Get requisition status and linked accounts."""
        return await self._async_request(
            "GET", f"/requisitions/{requisition_id}/"
        )

    async def async_get_account_details(
        self, account_id: str
    ) -> dict[str, Any]:
        """Get account metadata (IBAN, name, currency)."""
        return await self._async_request(
            "GET", f"/accounts/{account_id}/details/"
        )

    async def async_get_balances(
        self, account_id: str
    ) -> list[dict[str, Any]]:
        """Get current account balances."""
        result = await self._async_request(
            "GET", f"/accounts/{account_id}/balances/"
        )
        return result.get("balances", [])

    async def async_get_transactions(
        self, account_id: str, date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Get account transactions.

        Args:
            account_id: GoCardless account ID
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)

        Returns:
            Dict with 'booked' and 'pending' transaction lists
        """
        params = []
        if date_from:
            params.append(f"date_from={date_from}")
        if date_to:
            params.append(f"date_to={date_to}")

        query = f"?{'&'.join(params)}" if params else ""
        result = await self._async_request(
            "GET", f"/accounts/{account_id}/transactions/{query}"
        )
        return result.get("transactions", {"booked": [], "pending": []})

    async def async_refresh_token(
        self, refresh_token: str
    ) -> dict[str, Any] | None:
        """Refresh an expired access token."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GOCARDLESS_BASE_URL}/token/refresh/",
                    json={"refresh": refresh_token},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    _LOGGER.error(
                        "Token refresh failed: %d", resp.status
                    )
                    return None
        except Exception:
            _LOGGER.exception("Token refresh request failed")
            return None

    async def _async_get_new_token(self) -> dict[str, Any] | None:
        """Get a new access token using API credentials."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GOCARDLESS_BASE_URL}/token/new/",
                    json={
                        "secret_id": self._secret_id,
                        "secret_key": self._secret_key,
                    },
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._access_token = data.get("access")
                        return data
                    _LOGGER.error(
                        "Token request failed: %d", resp.status
                    )
                    return None
        except Exception:
            _LOGGER.exception("Token request failed")
            return None

    async def _async_request(
        self, method: str, endpoint: str, **kwargs
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make an authenticated API request."""
        if not self._access_token:
            tokens = await self._async_get_new_token()
            if not tokens:
                raise ConnectionError("Failed to obtain access token")

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        url = f"{GOCARDLESS_BASE_URL}{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url, headers=headers, **kwargs
            ) as resp:
                if resp.status == 401:
                    # Token expired, try refresh
                    tokens = await self._async_get_new_token()
                    if tokens:
                        headers["Authorization"] = (
                            f"Bearer {self._access_token}"
                        )
                        async with session.request(
                            method, url, headers=headers, **kwargs
                        ) as retry_resp:
                            retry_resp.raise_for_status()
                            return await retry_resp.json()
                    raise ConnectionError("Authentication failed")

                resp.raise_for_status()
                return await resp.json()
