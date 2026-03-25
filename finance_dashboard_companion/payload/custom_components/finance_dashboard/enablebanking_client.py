"""Enable Banking Open Banking API client.

Handles communication with the Enable Banking API for PSD2-compliant
bank account data access. Replaces the GoCardless client while normalizing
all response data to GoCardless-compatible field names so downstream
consumers (manager.py, categorizer.py, api.py) remain unchanged.

SECURITY:
- All API communication over HTTPS only
- JWT signed per-request with RSA private key (no long-lived tokens in memory)
- No credentials logged or cached beyond request scope
- Private key held only in memory, never written to disk by this module
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import ENABLEBANKING_BASE_URL

_LOGGER = logging.getLogger(__name__)


class EnableBankingClient:
    """Client for Enable Banking Open Banking API.

    SECURITY:
    - All API communication over HTTPS only
    - JWT signed per-request (no long-lived tokens in memory)
    - No credentials logged or cached beyond request scope
    """

    def __init__(
        self, application_id: str, private_key_pem: str
    ) -> None:
        """Initialize with Enable Banking credentials.

        Args:
            application_id: Enable Banking application ID (used as JWT kid).
            private_key_pem: RSA private key in PEM format for JWT signing.
        """
        self._application_id = application_id
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode()
            if isinstance(private_key_pem, str)
            else private_key_pem,
            password=None,
        )

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def async_test_connection(self) -> bool:
        """Test API connection by listing institutions.

        Returns True if the API responds successfully, False otherwise.
        """
        try:
            institutions = await self.async_get_institutions("DE")
            return isinstance(institutions, list)
        except Exception:
            _LOGGER.exception("Enable Banking connection test failed")
            return False

    async def async_get_institutions(
        self, country: str = "DE"
    ) -> list[dict[str, Any]]:
        """Get available banks (ASPSPs) for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code (default: DE).

        Returns:
            List of institution dicts with keys: id, name, bic, logo, countries
            (normalized from Enable Banking ASPSP format).
        """
        result = await self._async_request(
            "GET", f"/aspsps?country={country}"
        )
        aspsps = result if isinstance(result, list) else result.get("aspsps", [])
        return [self._normalize_institution(a) for a in aspsps]

    async def async_create_auth(
        self,
        aspsp_name: str,
        aspsp_country: str,
        redirect_url: str,
        valid_until: str | None = None,
        psu_type: str = "personal",
        state: str = "",
    ) -> dict[str, Any]:
        """Initiate bank authorization (PSU redirect flow).

        Args:
            aspsp_name: Bank name as returned by async_get_institutions.
            aspsp_country: ISO 3166-1 alpha-2 country code.
            redirect_url: URL to redirect the user back to after auth.
            valid_until: RFC3339 datetime with timezone for access validity.
            psu_type: Payment service user type (default: personal).
            state: Arbitrary string for request tracking (required by API).

        Returns:
            Dict with keys: url (authorization URL), auth_id.
        """
        payload: dict[str, Any] = {
            "aspsp": {
                "name": aspsp_name,
                "country": aspsp_country,
            },
            "redirect_url": redirect_url,
            "psu_type": psu_type,
            "state": state or "ha-finance",
        }
        if valid_until:
            payload["access"] = {"valid_until": valid_until}

        result = await self._async_request(
            "POST", "/auth", json=payload
        )
        return {
            "url": result.get("url", ""),
            "auth_id": result.get("auth_id", result.get("id", "")),
        }

    async def async_create_session(
        self, auth_code: str
    ) -> dict[str, Any]:
        """Exchange authorization code for a session.

        Args:
            auth_code: Authorization code received from the redirect callback.

        Returns:
            Dict with keys:
            - session_id: Enable Banking session identifier
            - accounts: list of {id, iban, name, currency}
        """
        result = await self._async_request(
            "POST", "/sessions", json={"code": auth_code}
        )

        session_id = result.get("session_id", result.get("id", ""))
        raw_accounts = result.get("accounts", [])

        accounts = []
        for acct in raw_accounts:
            accounts.append({
                "id": acct.get("uid", acct.get("id", "")),
                "iban": acct.get("iban", ""),
                "name": acct.get("account_name", acct.get("name", "")),
                "currency": acct.get("currency", "EUR"),
            })

        return {"session_id": session_id, "accounts": accounts}

    async def async_get_account_details(
        self, account_id: str
    ) -> dict[str, Any]:
        """Get account metadata.

        Args:
            account_id: Enable Banking account ID.

        Returns:
            Dict normalized to GoCardless format:
            {account: {iban, name, currency, ...}}
        """
        result = await self._async_request(
            "GET", f"/accounts/{account_id}"
        )
        acct = result if "iban" in result else result.get("account", result)
        return {
            "account": {
                "iban": acct.get("iban", ""),
                "name": acct.get("account_name", acct.get("name", "")),
                "currency": acct.get("currency", "EUR"),
                "product": acct.get("product", ""),
                "ownerName": acct.get("owner_name", ""),
            }
        }

    async def async_get_balances(
        self, account_id: str
    ) -> list[dict[str, Any]]:
        """Get account balances.

        Args:
            account_id: Enable Banking account ID.

        Returns:
            List normalized to GoCardless format:
            [{balanceAmount: {amount, currency}, balanceType, referenceDate}]
        """
        result = await self._async_request(
            "GET", f"/accounts/{account_id}/balances"
        )
        balances = result if isinstance(result, list) else result.get("balances", [])
        return [self._normalize_balance(b) for b in balances]

    async def async_get_transactions(
        self,
        account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Get account transactions.

        Args:
            account_id: Enable Banking account ID.
            date_from: Start date (YYYY-MM-DD, optional).
            date_to: End date (YYYY-MM-DD, optional).

        Returns:
            Dict normalized to GoCardless format:
            {booked: [...], pending: [...]}
            Each transaction has: transactionId, bookingDate,
            transactionAmount: {amount, currency},
            remittanceInformationUnstructured, creditorName.
        """
        params = []
        if date_from:
            params.append(f"date_from={date_from}")
        if date_to:
            params.append(f"date_to={date_to}")

        query = f"?{'&'.join(params)}" if params else ""
        result = await self._async_request(
            "GET", f"/accounts/{account_id}/transactions{query}"
        )

        transactions = (
            result if isinstance(result, dict) and ("booked" in result or "pending" in result)
            else result.get("transactions", {})
        )

        booked = [
            self._normalize_transaction(t)
            for t in transactions.get("booked", [])
        ]
        pending = [
            self._normalize_transaction(t)
            for t in transactions.get("pending", [])
        ]
        return {"booked": booked, "pending": pending}

    # ------------------------------------------------------------------
    # Data normalization (Enable Banking → GoCardless field names)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_transaction(txn: dict[str, Any]) -> dict[str, Any]:
        """Normalize Enable Banking transaction to GoCardless format.

        Enable Banking uses snake_case; downstream consumers expect
        camelCase GoCardless fields.
        """
        amount_data = txn.get("transaction_amount", {})
        creditor = txn.get("creditor")
        debtor = txn.get("debtor")

        return {
            "transactionId": txn.get(
                "entry_reference", txn.get("transaction_id", "")
            ),
            "bookingDate": txn.get("booking_date", ""),
            "bookingDateTime": txn.get("booking_date_time", ""),
            "valueDate": txn.get("value_date", ""),
            "transactionAmount": {
                "amount": amount_data.get("amount", "0"),
                "currency": amount_data.get("currency", "EUR"),
            },
            "creditorName": (
                creditor.get("name", "")
                if isinstance(creditor, dict)
                else txn.get("creditor_name", "")
            ),
            "debtorName": (
                debtor.get("name", "")
                if isinstance(debtor, dict)
                else txn.get("debtor_name", "")
            ),
            "remittanceInformationUnstructured": (
                txn.get("remittance_information", "")
                or txn.get("remittance_information_unstructured", "")
            ),
        }

    @staticmethod
    def _normalize_balance(bal: dict[str, Any]) -> dict[str, Any]:
        """Normalize Enable Banking balance to GoCardless format."""
        amount_data = bal.get("balance_amount", {})
        return {
            "balanceAmount": {
                "amount": amount_data.get("amount", "0"),
                "currency": amount_data.get("currency", "EUR"),
            },
            "balanceType": bal.get("balance_type", "closingBooked"),
            "referenceDate": bal.get("reference_date", ""),
        }

    @staticmethod
    def _normalize_institution(aspsp: dict[str, Any]) -> dict[str, Any]:
        """Normalize Enable Banking ASPSP to GoCardless institution format."""
        return {
            "id": aspsp.get("name", ""),
            "name": aspsp.get("name", ""),
            "bic": aspsp.get("bic", ""),
            "logo": aspsp.get("logo", ""),
            "countries": aspsp.get("countries", []),
        }

    # ------------------------------------------------------------------
    # JWT generation & HTTP transport
    # ------------------------------------------------------------------

    def _generate_jwt(self) -> str:
        """Generate a short-lived JWT for API authentication.

        Creates an RS256-signed JWT with 60-second validity.
        No external JWT library required — uses cryptography directly.
        """
        header = {
            "alg": "RS256",
            "typ": "JWT",
            "kid": self._application_id,
        }
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header_b64 = b64url(
            json.dumps(header, separators=(",", ":")).encode()
        )
        payload_b64 = b64url(
            json.dumps(payload, separators=(",", ":")).encode()
        )
        signing_input = f"{header_b64}.{payload_b64}"

        signature = self._private_key.sign(
            signing_input.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        return f"{signing_input}.{b64url(signature)}"

    async def _async_request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make an authenticated API request.

        Generates a fresh JWT for every request (60s validity).
        Raises aiohttp.ClientResponseError on HTTP errors.
        """
        jwt_token = self._generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }

        url = f"{ENABLEBANKING_BASE_URL}{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url, headers=headers, **kwargs
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
