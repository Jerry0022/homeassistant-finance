"""Data read endpoints for Finance.

Cache-read endpoints — never hit the banking API. Unbounded calls safe.

Provides:
- BalancesView        — per-account balance data
- TransactionsView    — admin: full list; non-admin: aggregate summary
- SummaryView         — monthly spending summary
- TransferChainsView  — transfer chain detection + confirmation
"""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN
from ._helpers import _get_manager

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardBalanceView(HomeAssistantView):
    """API endpoint for account balances."""

    url = f"/api/{DOMAIN}/balances"
    name = f"api:{DOMAIN}:balances"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get balances for all linked accounts."""
        hass = request.app["hass"]
        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        balances = await manager.async_get_balance()

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
        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        user = request.get("hass_user")
        is_admin = user and user.is_admin if user else False

        if not is_admin:
            summary = await manager.async_get_monthly_summary()
            return self.json(
                {
                    "privacy": "aggregate_only",
                    "message": "Individual transactions require admin access.",
                    "categories": summary.get("categories", {}),
                    "total_income": summary.get("total_income", 0),
                    "total_expenses": summary.get(
                        "total_expenses", 0
                    ),
                    "transaction_count": summary.get(
                        "transaction_count", 0
                    ),
                }
            )

        transactions = manager.get_cached_transactions(limit=100)

        sanitized = []
        for txn in transactions:
            entry = {
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
                "account_name": txn.get("_account_name", ""),
            }

            # Transfer chain metadata
            chain_id = txn.get("_transfer_chain_id")
            if chain_id:
                entry["transfer_chain_id"] = chain_id
                entry["transfer_role"] = txn.get(
                    "_transfer_role", ""
                )
                entry["transfer_confidence"] = txn.get(
                    "_transfer_confidence"
                )
                entry["transfer_confirmed"] = txn.get(
                    "_transfer_confirmed"
                )

            # Refund metadata
            refund_id = txn.get("_refund_pair_id")
            if refund_id:
                entry["refund_pair_id"] = refund_id
                entry["refund_role"] = txn.get("_refund_role", "")

            sanitized.append(entry)

        return self.json(
            {"privacy": "admin_full", "transactions": sanitized}
        )


class FinanceDashboardTransferChainsView(HomeAssistantView):
    """API endpoint for transfer chain data.

    Returns detected cascading transfer chains for the frontend.
    Supports confirming/rejecting chains via POST.
    """

    url = f"/api/{DOMAIN}/transfer_chains"
    name = f"api:{DOMAIN}:transfer_chains"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get all detected transfer chains."""
        hass = request.app["hass"]
        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        user = request.get("hass_user")
        is_admin = user and user.is_admin if user else False

        if not is_admin:
            return self.json(
                {"error": "Admin access required"},
                status_code=403,
            )

        chains = manager.get_transfer_chains()
        return self.json({"chains": chains})

    async def post(self, request: web.Request) -> web.Response:
        """Confirm or reject a transfer chain."""
        hass = request.app["hass"]
        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        user = request.get("hass_user")
        is_admin = user and user.is_admin if user else False

        if not is_admin:
            return self.json(
                {"error": "Admin access required"},
                status_code=403,
            )

        try:
            body = await request.json()
        except Exception:
            return self.json(
                {"error": "Invalid JSON body"}, status_code=400
            )

        chain_id = body.get("chain_id", "")
        confirmed = body.get("confirmed")

        if not chain_id or confirmed is None:
            return self.json(
                {"error": "chain_id and confirmed required"},
                status_code=400,
            )

        await manager.async_confirm_transfer_chain(
            chain_id, bool(confirmed)
        )
        return self.json(
            {"success": True, "chain_id": chain_id}
        )


class FinanceDashboardSummaryView(HomeAssistantView):
    """API endpoint for monthly summary."""

    url = f"/api/{DOMAIN}/summary"
    name = f"api:{DOMAIN}:summary"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get monthly spending summary."""
        hass = request.app["hass"]
        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        summary = await manager.async_get_monthly_summary()
        return self.json(summary)
