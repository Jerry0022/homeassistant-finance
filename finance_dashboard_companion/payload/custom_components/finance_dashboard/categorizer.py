"""Transaction auto-categorizer.

Uses rule-based pattern matching to classify banking transactions
into budget categories. Users can customize rules via the UI.

No ML/AI dependencies — pure keyword matching for reliability and
transparency. Categories are deterministic and auditable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .const import CATEGORIZATION_RULES, CATEGORY_OTHER

_LOGGER = logging.getLogger(__name__)


class TransactionCategorizer:
    """Categorize banking transactions by keyword matching."""

    def __init__(
        self, custom_rules: dict[str, list[str]] | None = None
    ) -> None:
        """Initialize with default + optional custom rules."""
        self._rules = dict(CATEGORIZATION_RULES)
        if custom_rules:
            for category, keywords in custom_rules.items():
                existing = self._rules.get(category, [])
                self._rules[category] = list(set(existing + keywords))

    def categorize(self, transaction: dict[str, Any]) -> str:
        """Categorize a single transaction.

        Checks remittance info, creditor name, and debtor name
        against keyword patterns.

        Args:
            transaction: Transaction object (normalized format)

        Returns:
            Category string (e.g., 'housing', 'food', 'income')
        """
        # Extract searchable text from transaction
        search_text = self._extract_searchable_text(transaction)
        if not search_text:
            return CATEGORY_OTHER

        search_lower = search_text.lower()

        # Check amount direction for income detection
        amount = float(
            transaction.get("transactionAmount", {}).get("amount", 0)
        )

        # Match against rules
        for category, keywords in self._rules.items():
            for keyword in keywords:
                if keyword.lower() in search_lower:
                    return category

        # Fallback: positive amounts without category → income
        if amount > 0:
            return "income"

        return CATEGORY_OTHER

    def update_rules(
        self, category: str, keywords: list[str]
    ) -> None:
        """Add or update categorization rules for a category."""
        existing = self._rules.get(category, [])
        self._rules[category] = list(set(existing + keywords))

    def get_rules(self) -> dict[str, list[str]]:
        """Get current categorization rules."""
        return dict(self._rules)

    @staticmethod
    def _extract_searchable_text(
        transaction: dict[str, Any],
    ) -> str:
        """Extract all searchable text fields from a transaction."""
        parts = []

        # Remittance information (payment reference)
        remittance = transaction.get("remittanceInformationUnstructured", "")
        if remittance:
            parts.append(remittance)

        remittance_array = transaction.get(
            "remittanceInformationUnstructuredArray", []
        )
        if remittance_array:
            parts.extend(remittance_array)

        # Creditor (who receives money)
        creditor = transaction.get("creditorName", "")
        if creditor:
            parts.append(creditor)

        # Debtor (who sends money)
        debtor = transaction.get("debtorName", "")
        if debtor:
            parts.append(debtor)

        # Additional info
        additional = transaction.get("additionalInformation", "")
        if additional:
            parts.append(additional)

        return " ".join(parts)
