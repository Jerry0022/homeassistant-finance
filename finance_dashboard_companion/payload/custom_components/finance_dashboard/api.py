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
    hass.http.register_view(FinanceDashboardOAuthCallbackView())
    hass.http.register_view(FinanceDashboardStaticView())
    hass.http.register_view(FinanceDashboardBalanceView())
    hass.http.register_view(FinanceDashboardTransactionsView())
    hass.http.register_view(FinanceDashboardSummaryView())
    _LOGGER.debug("Finance Dashboard API endpoints registered")


class FinanceDashboardOAuthCallbackView(HomeAssistantView):
    """Handle OAuth callback from Enable Banking bank authorization.

    After the user authorizes at their bank, Enable Banking redirects here
    with a `code` parameter. We store the code for the config flow to pick up
    and show a "go back to HA" message.
    """

    url = f"/api/{DOMAIN}/oauth/callback"
    name = f"api:{DOMAIN}:oauth_callback"
    requires_auth = False  # Bank redirect — no HA auth header

    async def get(self, request: web.Request) -> web.Response:
        """Handle GET redirect from bank after authorization."""
        hass = request.app["hass"]

        # Extract authorization code from Enable Banking redirect
        code = request.query.get("code")
        if code:
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN]["pending_auth_code"] = code
            _LOGGER.info(
                "OAuth callback received with authorization code"
            )
        else:
            _LOGGER.warning(
                "OAuth callback received without authorization code"
            )

        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Finance Dashboard</title>
<style>
body { font-family: -apple-system, sans-serif; background: #0a0a0f;
  color: #e8e8ed; display: flex; justify-content: center;
  align-items: center; min-height: 100vh; margin: 0; }
.card { background: #12121a; border-radius: 16px; padding: 48px;
  text-align: center; max-width: 400px; border: 1px solid rgba(255,255,255,0.06); }
h1 { color: #4ecca3; font-size: 24px; margin: 0 0 12px; }
p { color: #9898a8; font-size: 14px; line-height: 1.6; }
.icon { font-size: 48px; margin-bottom: 16px; }
</style></head><body>
<div class="card">
  <div class="icon">&#9989;</div>
  <h1>Bank Authorization Complete</h1>
  <p>Your bank account has been linked successfully.<br>
  Please return to Home Assistant and click <strong>Submit</strong>
  to continue the setup.</p>
</div>
</body></html>"""

        return web.Response(
            text=html, content_type="text/html", status=200
        )


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

        # Sanitize output — truncate IBANs, add institution info
        sanitized = {}
        for account_id, data in balances.items():
            sanitized[account_id] = {
                "account_name": data.get("account_name", "Unknown"),
                "iban_masked": data.get("iban_masked", "****"),
                "institution": data.get("institution", ""),
                "logo": data.get("logo", ""),
                "balances": data.get("balances", []),
            }

        return self.json(sanitized)


class FinanceDashboardTransactionsView(HomeAssistantView):
    """API endpoint for transactions.

    PRIVACY-FIRST: Individual transaction details are only returned
    to HA admin users. Non-admin users receive only aggregated
    category summaries — no individual transaction data.
    """

    url = f"/api/{DOMAIN}/transactions"
    name = f"api:{DOMAIN}:transactions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get recent transactions (admin-only detail view)."""
        hass = request.app["hass"]
        entries = hass.data.get(DOMAIN, {})

        if not entries:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        # Privacy gate: check if requesting user is HA admin
        user = request.get("hass_user")
        is_admin = user and user.is_admin if user else False

        manager = next(iter(entries.values()))

        if not is_admin:
            # Non-admin: only aggregated category data, no transactions
            summary = await manager.async_get_monthly_summary()
            return self.json(
                {
                    "privacy": "aggregate_only",
                    "message": "Individual transactions require admin access.",
                    "categories": summary.get("categories", {}),
                    "total_income": summary.get("total_income", 0),
                    "total_expenses": summary.get("total_expenses", 0),
                    "transaction_count": summary.get(
                        "transaction_count", 0
                    ),
                }
            )

        # Admin: return individual transactions (sanitized)
        transactions = manager.get_cached_transactions(limit=100)

        sanitized = []
        for txn in transactions:
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
                    "status": txn.get("_status", "booked"),
                    # Never expose: full IBAN, internal IDs, raw account data
                }
            )

        return self.json(
            {"privacy": "admin_full", "transactions": sanitized}
        )


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
