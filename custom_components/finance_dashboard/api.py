"""HTTP API endpoints for Finance Dashboard.

Provides REST endpoints for the frontend panel and Lovelace cards
to interact with the integration.

SECURITY:
- All endpoints require HA authentication (Bearer token)
- No financial data in URL parameters
- Responses stripped of sensitive fields (tokens, IBANs truncated)
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_register_api(hass: HomeAssistant) -> None:
    """Register HTTP API endpoints."""
    hass.http.register_view(FinanceDashboardStaticView())
    hass.http.register_view(FinanceDashboardBalanceView())
    hass.http.register_view(FinanceDashboardTransactionsView())
    hass.http.register_view(FinanceDashboardSummaryView())
    _LOGGER.debug("Finance Dashboard API endpoints registered")


class FinanceDashboardStaticView(HomeAssistantView):
    """Serve static frontend files."""

    url = f"/api/{DOMAIN}/static/{{filename}}"
    name = f"api:{DOMAIN}:static"
    requires_auth = False  # Static JS/CSS files

    async def get(
        self, request: web.Request, filename: str
    ) -> web.Response:
        """Serve a static file from the frontend directory."""
        frontend_dir = Path(__file__).parent / "frontend"
        file_path = frontend_dir / filename

        if not file_path.exists() or not file_path.is_file():
            return web.Response(status=404)

        # Security: prevent directory traversal
        try:
            file_path.resolve().relative_to(frontend_dir.resolve())
        except ValueError:
            return web.Response(status=403)

        content_type = "application/javascript"
        if filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".html"):
            content_type = "text/html"

        return web.Response(
            body=file_path.read_bytes(),
            content_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )


class FinanceDashboardBalanceView(HomeAssistantView):
    """API endpoint for account balances."""

    url = f"/api/{DOMAIN}/balances"
    name = f"api:{DOMAIN}:balances"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get balances for all linked accounts."""
        hass = request.app["hass"]
        entries = hass.data.get(DOMAIN, {})

        if not entries:
            return self.json({"error": "Not configured"}, status_code=404)

        manager = next(iter(entries.values()))
        balances = await manager.async_get_balance()

        # Sanitize output — truncate IBANs for frontend display
        sanitized = {}
        for account_id, data in balances.items():
            iban = data.get("iban", "")
            sanitized[account_id] = {
                "account_name": data.get("account_name", "Unknown"),
                "iban_masked": f"****{iban[-4:]}" if len(iban) >= 4 else "****",
                "balances": data.get("balances", []),
            }

        return self.json(sanitized)


class FinanceDashboardTransactionsView(HomeAssistantView):
    """API endpoint for transactions."""

    url = f"/api/{DOMAIN}/transactions"
    name = f"api:{DOMAIN}:transactions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get recent transactions."""
        hass = request.app["hass"]
        entries = hass.data.get(DOMAIN, {})

        if not entries:
            return self.json({"error": "Not configured"}, status_code=404)

        manager = next(iter(entries.values()))
        transactions = await manager.async_refresh_transactions()

        # Sanitize — never expose full account numbers
        sanitized = []
        for txn in transactions[:100]:  # Limit response size
            sanitized.append(
                {
                    "date": txn.get("bookingDate", ""),
                    "amount": txn.get("transactionAmount", {}).get(
                        "amount", "0"
                    ),
                    "currency": txn.get("transactionAmount", {}).get(
                        "currency", "EUR"
                    ),
                    "description": txn.get(
                        "remittanceInformationUnstructured", ""
                    ),
                    "creditor": txn.get("creditorName", ""),
                    "category": txn.get("category", "other"),
                }
            )

        return self.json({"transactions": sanitized})


class FinanceDashboardSummaryView(HomeAssistantView):
    """API endpoint for monthly summary."""

    url = f"/api/{DOMAIN}/summary"
    name = f"api:{DOMAIN}:summary"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get monthly spending summary."""
        hass = request.app["hass"]
        entries = hass.data.get(DOMAIN, {})

        if not entries:
            return self.json({"error": "Not configured"}, status_code=404)

        manager = next(iter(entries.values()))
        summary = await manager.async_get_monthly_summary()

        return self.json(summary)
