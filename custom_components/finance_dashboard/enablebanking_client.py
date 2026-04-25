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

import logging
import re
import secrets
import time
import uuid
from typing import Any

import aiohttp
import jwt
from cryptography.hazmat.primitives import serialization

from .const import ENABLEBANKING_BASE_URL, VERSION

# Type alias for optional injected session
_SessionType = aiohttp.ClientSession | None

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Log sanitizer — strips PII from error response bodies before any logging.
# ---------------------------------------------------------------------------

_RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,25}\b")
_RE_ACCOUNT_ID = re.compile(r"\b\d{16,19}\b")
_RE_AMOUNT = re.compile(r"\b\d+[.,]\d{2}\s*(?:EUR|€)\b", re.IGNORECASE)


def _sanitize_log(text: str) -> str:
    """Return *text* with IBANs, long numeric account IDs and amounts masked.

    Applied to all banking response bodies before they reach the log sink so
    that a misconfigured log shipper cannot exfiltrate financial PII.

    Examples:
        "DE89370400440532013000" → "***IBAN***"
        "1234567890123456"       → "***ACCOUNT***"
        "1234.56 EUR"            → "***AMOUNT***"
    """
    text = _RE_IBAN.sub("***IBAN***", text)
    text = _RE_ACCOUNT_ID.sub("***ACCOUNT***", text)
    text = _RE_AMOUNT.sub("***AMOUNT***", text)
    return text


class RateLimitExceeded(Exception):
    """Raised when the banking API returns HTTP 429 (daily quota exhausted).

    Attributes:
        retry_after_seconds: Value from the ``Retry-After`` response header
            (seconds), or ``None`` when the header was absent/unparseable.
            Callers should use ``min(midnight, now + retry_after_seconds)``
            as the rate-limit reset time when this value is set.
    """

    def __init__(self, message: str = "", retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds: int | None = retry_after_seconds


class EnableBankingClient:
    """Client for Enable Banking Open Banking API.

    SECURITY:
    - All API communication over HTTPS only
    - JWT signed per-request (no long-lived tokens in memory)
    - No credentials logged or cached beyond request scope
    """

    def __init__(
        self,
        application_id: str,
        private_key_pem: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize with Enable Banking credentials.

        Args:
            application_id: Enable Banking application ID (used as JWT kid).
            private_key_pem: RSA private key in PEM format for JWT signing.
            session: Optional shared aiohttp ClientSession.  When provided the
                caller is responsible for lifecycle management (HA-owned sessions
                must not be closed by this client).  When omitted a private
                session is created lazily on first request and closed on
                ``async_close()``.
        """
        self._application_id = application_id
        pem_bytes = (
            private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem
        )
        try:
            self._private_key = serialization.load_pem_private_key(pem_bytes, password=None)
        except (ValueError, TypeError):
            # PEM may have lost newlines — try to reconstruct
            _LOGGER.debug("PEM load failed, attempting newline reconstruction")
            pem_str = pem_bytes.decode() if isinstance(pem_bytes, bytes) else pem_bytes
            pem_str = self._reconstruct_pem(pem_str)
            self._private_key = serialization.load_pem_private_key(pem_str.encode(), password=None)
        # Session management: injected → caller-owned; None → we own it.
        self._session: aiohttp.ClientSession | None = session
        self._session_owner: bool = session is None  # True → we must close

    async def async_close(self) -> None:
        """Close the private session if we own it.

        No-op when an external session was injected at construction time.
        """
        if self._session_owner and self._session is not None:
            await self._session.close()
            self._session = None

    @staticmethod
    def _reconstruct_pem(raw: str) -> str:
        """Reconstruct PEM with proper line breaks.

        C9: Marker-type detection (PKCS1 vs PKCS8) is performed BEFORE
        stripping the markers so the check is not confused by partial or
        escaped header text.
        """
        # Normalize escaped newlines first so marker strings are intact.
        raw = raw.replace("\\n", "\n")
        # C9: detect key type BEFORE stripping markers — once the header
        # lines are removed the type information is gone.
        is_pkcs1 = "RSA PRIVATE KEY" in raw or "BEGIN RSA PRIVATE KEY" in raw
        # Strip all known PEM header/footer lines.
        for marker in (
            "-----BEGIN PRIVATE KEY-----",
            "-----END PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----END RSA PRIVATE KEY-----",
        ):
            raw = raw.replace(marker, "")
        body = raw.replace("\n", "").replace("\r", "").replace(" ", "")
        if is_pkcs1:
            h = "-----BEGIN RSA PRIVATE KEY-----"
            f = "-----END RSA PRIVATE KEY-----"
        else:
            h = "-----BEGIN PRIVATE KEY-----"
            f = "-----END PRIVATE KEY-----"
        lines = [body[i : i + 64] for i in range(0, len(body), 64)]
        return f"{h}\n" + "\n".join(lines) + f"\n{f}"

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

    async def async_get_institutions(self, country: str = "DE") -> list[dict[str, Any]]:
        """Get available banks (ASPSPs) for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code (default: DE).

        Returns:
            List of institution dicts with keys: id, name, bic, logo, countries
            (normalized from Enable Banking ASPSP format).
        """
        result = await self._async_request("GET", f"/aspsps?country={country}")
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
            "state": state or str(uuid.uuid4()),
        }
        if valid_until:
            payload["access"] = {"valid_until": valid_until}

        result = await self._async_request("POST", "/auth", json=payload)
        return {
            "url": result.get("url", ""),
            "auth_id": result.get("authorization_id", result.get("auth_id", "")),
        }

    async def async_create_session(self, auth_code: str) -> dict[str, Any]:
        """Exchange authorization code for a session.

        Args:
            auth_code: Authorization code received from the redirect callback.

        Returns:
            Dict with keys:
            - session_id: Enable Banking session identifier
            - accounts: list of {id, iban, name, currency}
        """
        result = await self._async_request("POST", "/sessions", json={"code": auth_code})

        session_id = result.get("session_id", result.get("id", ""))
        raw_accounts = result.get("accounts", [])

        accounts = []
        for acct in raw_accounts:
            # IBAN can be nested in account_id object or flat
            account_id_obj = acct.get("account_id", {})
            iban = (
                account_id_obj.get("iban", "")
                if isinstance(account_id_obj, dict)
                else acct.get("iban", "")
            )
            accounts.append(
                {
                    "id": acct.get("uid", acct.get("id", "")),
                    "iban": iban,
                    "name": acct.get("account_name", acct.get("name", "")),
                    "currency": acct.get("currency", "EUR"),
                }
            )

        return {"session_id": session_id, "accounts": accounts}

    async def async_get_account_details(self, account_id: str) -> dict[str, Any]:
        """Get account metadata.

        Args:
            account_id: Enable Banking account ID.

        Returns:
            Dict normalized to GoCardless format:
            {account: {iban, name, currency, ...}}
        """
        result = await self._async_request("GET", f"/accounts/{account_id}")
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

    # Canonical PSU user-agent for user-triggered live calls.
    # Set once at class level so all instances share the same string.
    _PSU_UA: str = f"HomeAssistant-Finance-Dashboard/{VERSION}"

    async def async_get_balances(
        self,
        account_id: str,
        psu_ip: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get account balances.

        Args:
            account_id: Enable Banking account ID.
            psu_ip: Optional PSU IP address from the originating user request.

        Returns:
            List normalized to GoCardless format:
            [{balanceAmount: {amount, currency}, balanceType, referenceDate}]
        """
        result = await self._async_request(
            "GET",
            f"/accounts/{account_id}/balances",
            psu_ip=psu_ip,
            psu_ua=self._PSU_UA,
        )
        balances = result if isinstance(result, list) else result.get("balances", [])
        return [self._normalize_balance(b) for b in balances]

    async def async_get_transactions(
        self,
        account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        psu_ip: str | None = None,
    ) -> dict[str, Any]:
        """Get account transactions.

        Args:
            account_id: Enable Banking account ID.
            date_from: Start date (YYYY-MM-DD, optional).
            date_to: End date (YYYY-MM-DD, optional).
            psu_ip: Optional PSU IP address from the originating user request.

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
            "GET",
            f"/accounts/{account_id}/transactions{query}",
            psu_ip=psu_ip,
            psu_ua=self._PSU_UA,
        )

        transactions = (
            result
            if isinstance(result, dict) and ("booked" in result or "pending" in result)
            else result.get("transactions", {})
        )

        booked = [self._normalize_transaction(t) for t in transactions.get("booked", [])]
        pending = [self._normalize_transaction(t) for t in transactions.get("pending", [])]
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
            "transactionId": txn.get("entry_reference", txn.get("transaction_id", "")),
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
                debtor.get("name", "") if isinstance(debtor, dict) else txn.get("debtor_name", "")
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

        Creates an RS256-signed JWT with 60-second validity using PyJWT.
        Each token includes a unique ``jti`` claim to prevent replay attacks.
        """
        now = int(time.time())
        payload = {
            "iss": self._application_id,
            "aud": "api.tilisy.com",
            "iat": now,
            "exp": now + 60,
            "jti": secrets.token_hex(16),
        }
        # Export the RSA private key in PEM format so PyJWT can use it.
        # The cryptography key object is already loaded in __init__.
        pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return jwt.encode(
            payload,
            pem,
            algorithm="RS256",
            headers={"kid": self._application_id},
        )

    async def _async_request(
        self,
        method: str,
        endpoint: str,
        psu_ip: str | None = None,
        psu_ua: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make an authenticated API request.

        Generates a fresh JWT for every request (60s validity).
        Raises aiohttp.ClientResponseError on HTTP errors.

        Args:
            psu_ip: Optional PSU IP address (from request context).  Sent as
                ``Psu-Ip-Address`` header when provided.  Omitted otherwise —
                never invent a value.
            psu_ua: Optional PSU user-agent string.  Defaults to the
                integration's canonical UA when not explicitly overridden.
                Sent as ``Psu-User-Agent`` for user-triggered live calls only.
        """
        jwt_token = self._generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }
        if psu_ip:
            headers["Psu-Ip-Address"] = psu_ip
        if psu_ua:
            headers["Psu-User-Agent"] = psu_ua

        url = f"{ENABLEBANKING_BASE_URL}{endpoint}"
        _LOGGER.debug("Enable Banking request: %s %s", method, url)

        timeout = aiohttp.ClientTimeout(total=30)
        # Lazily create a private session if none was injected.
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=timeout)

        async with self._session.request(
            method, url, headers=headers, timeout=timeout, **kwargs
        ) as resp:
            _LOGGER.debug(
                "Enable Banking response: HTTP %s for %s %s",
                resp.status,
                method,
                url,
            )
            if not resp.ok:
                body = await resp.text()
                # Log only sanitized form at ERROR level to prevent PII
                # (IBANs, account IDs, amounts) reaching the HA log file.
                _LOGGER.error(
                    "Enable Banking API error: HTTP %s %s %s",
                    resp.status,
                    method,
                    endpoint,
                )
                _LOGGER.debug(
                    "Enable Banking error body (sanitized): %s",
                    _sanitize_log(body[:500]),
                )
                # Daily consent quota exhausted — signal callers to
                # stop retrying and serve cached data until tomorrow.
                # Honor the Retry-After header when present so the
                # reset time can be earlier than midnight.
                if resp.status == 429:
                    retry_after_seconds: int | None = None
                    raw_retry = resp.headers.get("Retry-After")
                    if raw_retry:
                        try:
                            retry_after_seconds = int(raw_retry)
                        except (ValueError, TypeError):
                            _LOGGER.debug(
                                "Could not parse Retry-After header: %s",
                                raw_retry,
                            )
                    raise RateLimitExceeded(
                        "Daily API quota exhausted (HTTP 429)",
                        retry_after_seconds,
                    )
                # Include a sanitized excerpt in the exception message
                # so callers can surface a safe error to the user.
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=_sanitize_log(body[:500]),
                )
            return await resp.json()
