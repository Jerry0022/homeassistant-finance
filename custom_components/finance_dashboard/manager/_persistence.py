"""PersistenceMixin — storage read/write for FinanceDashboardManager.

Handles:
- Persisting transactions, balances, rate-limit state, and stats to
  HA's encrypted .storage/ directory.
- Loading per-account transfer-chain overrides.
- Surfacing Repair issues for corrupt storage files (R8).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class PersistenceMixin:
    """Mixin that adds persistence methods to FinanceDashboardManager."""

    async def _persist_transactions(self) -> None:
        """Write the ledger (encrypted) with refresh stamps and budget state.

        Only the ledger layer is stored: transactions and balance series.
        Categories, account tags and transfer enrichment are derived on load
        and never persisted.  Demo data is never written.
        """
        if self._demo_mode or not self._ledger_writable:
            return
        meta = self._ledger.meta
        meta["balances"] = self._balances
        meta["last_refresh"] = self._last_refresh.isoformat() if self._last_refresh else None
        meta["last_refresh_stats"] = self._last_refresh_stats
        meta["account_count"] = len(self._accounts)
        meta["bank_budget"] = self._budget.to_dict()
        try:
            await self._ledger.async_save()
        except Exception:
            _LOGGER.exception("Ledger write failed — data stays in memory only")

    async def _async_load_transfer_overrides(
        self,
    ) -> dict[str, bool]:
        """Load user overrides for transfer chains from storage."""
        data = await self._transfer_override_store.async_load()
        if data and isinstance(data, dict):
            self._transfer_overrides = data
            return data
        return {}

    def _raise_storage_corrupt_issue(self, storage_key: str, error_class: str) -> None:
        """Raise a Repair issue for a corrupt .storage/ file (R8).

        Only the storage key name and Python exception class are included
        in the repair issue — never raw exception text or stack traces.

        Marked ``is_persistent=True`` — a corrupt cache file requires manual
        intervention (the user must delete the corrupt file or re-configure)
        and must remain visible across HA restarts.
        """
        try:
            from homeassistant.helpers import issue_registry as ir

            from ..const import DOMAIN

            ir.async_create_issue(
                self._hass,
                DOMAIN,
                f"storage_corrupt_{storage_key}",
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="storage_corrupt",
                translation_placeholders={
                    "storage_key": storage_key,
                    "error_class": error_class,
                },
            )
        except Exception:
            _LOGGER.debug("Could not create storage_corrupt repair issue", exc_info=True)
