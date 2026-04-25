"""PersistenceMixin — storage read/write for FinanceDashboardManager.

Handles:
- Persisting transactions, balances, rate-limit state, and stats to
  HA's encrypted .storage/ directory.
- Loading per-account transfer-chain overrides.
- Surfacing Repair issues for corrupt storage files (R8).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class PersistenceMixin:
    """Mixin that adds persistence methods to FinanceDashboardManager."""

    async def _persist_transactions(self) -> None:
        """Save transactions, balances, rate-limit and stats to cache.

        R5: saves the per-account dict (tx_by_account) as the canonical
        format.  The flat ``transactions`` key is kept for one-version
        backward-compatibility but is no longer the authoritative source.
        """
        await self._transaction_store.async_save(
            {
                # R5: per-account dict is the canonical storage format.
                "tx_by_account": self._tx_by_account,
                # Legacy flat list — kept so older versions can still read
                # something useful if rolled back.
                "transactions": self._transactions,
                "balances": self._balances,
                "last_refresh": (
                    self._last_refresh.isoformat()
                    if self._last_refresh
                    else None
                ),
                "rate_limited_until": (
                    self._rate_limited_until.isoformat()
                    if self._rate_limited_until
                    else None
                ),
                "last_refresh_stats": self._last_refresh_stats,
                "account_count": len(self._accounts),
            }
        )

    async def _async_load_transfer_overrides(
        self,
    ) -> dict[str, bool]:
        """Load user overrides for transfer chains from storage."""
        data = await self._transfer_override_store.async_load()
        if data and isinstance(data, dict):
            self._transfer_overrides = data
            return data
        return {}

    def _raise_storage_corrupt_issue(
        self, storage_key: str, error_class: str
    ) -> None:
        """Raise a Repair issue for a corrupt .storage/ file (R8).

        Only the storage key name and Python exception class are included
        in the repair issue — never raw exception text or stack traces.
        """
        try:
            from homeassistant.helpers import issue_registry as ir
            from ..const import DOMAIN

            ir.async_create_issue(
                self._hass,
                DOMAIN,
                f"storage_corrupt_{storage_key}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="storage_corrupt",
                translation_placeholders={
                    "storage_key": storage_key,
                    "error_class": error_class,
                },
            )
        except Exception:
            _LOGGER.debug(
                "Could not create storage_corrupt repair issue", exc_info=True
            )
