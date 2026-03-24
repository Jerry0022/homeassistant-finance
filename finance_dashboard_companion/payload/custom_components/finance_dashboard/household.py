"""Household budget model — N-person split engine.

Supports:
- N household members with individual income and costs
- 3 split modes: equal, proportional (by income), custom (manual %)
- Remainder split: no split (each keeps own) or equal distribution
- Category-level split overrides (optional)
- Bonus detection and separation from regular income
- Month cycle: calendar or salary-based per person

SECURITY: This module operates purely on in-memory data.
No financial values are persisted by this module — persistence
is handled by the Manager via .storage/.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import DEFAULT_CATEGORIES, DEFAULT_SPLIT_MODEL

_LOGGER = logging.getLogger(__name__)


@dataclass
class HouseholdMember:
    """A person in the household."""

    name: str
    gross_income: float = 0.0
    net_income: float = 0.0
    individual_costs: float = 0.0
    individual_cost_items: list[dict[str, Any]] = field(
        default_factory=list
    )
    account_ids: list[str] = field(default_factory=list)
    # Month cycle: "calendar" or "salary"
    month_cycle: str = "calendar"
    # Expected salary day (1-31), used for salary-based cycle
    salary_day: int = 25
    # 3-month income average for bonus detection
    income_history: list[float] = field(default_factory=list)

    @property
    def income_average_3m(self) -> float:
        """3-month rolling average income."""
        recent = self.income_history[-3:] if self.income_history else []
        return sum(recent) / len(recent) if recent else 0.0


@dataclass
class SplitResult:
    """Result of a budget split calculation for one person."""

    person: str
    gross_income: float
    net_income: float
    income_ratio: float  # 0.0 - 1.0
    shared_costs_share: float
    individual_costs: float
    spielgeld: float  # Free budget after all deductions
    bonus_amount: float = 0.0  # Detected bonus (not in balance)

    @property
    def total_deductions(self) -> float:
        return self.shared_costs_share + self.individual_costs


class HouseholdModel:
    """N-person household budget calculator.

    Calculates how shared costs are distributed across household
    members based on the selected split model.
    """

    def __init__(
        self,
        members: list[HouseholdMember] | None = None,
        split_mode: str = DEFAULT_SPLIT_MODEL,
        custom_ratios: dict[str, float] | None = None,
        remainder_mode: str = "none",
        category_overrides: dict[str, dict[str, float]] | None = None,
        bonus_threshold: float = 0.15,
    ) -> None:
        """Initialize the household model.

        Args:
            members: List of household members
            split_mode: "equal", "proportional", or "custom"
            custom_ratios: {person_name: percentage} for custom mode
            remainder_mode: "none" (each keeps own) or "equal_split"
            category_overrides: {category: {person: pct}} optional per-category split
            bonus_threshold: Income increase % to trigger bonus detection (default 15%)
        """
        self.members = members or []
        self.split_mode = split_mode
        self.custom_ratios = custom_ratios or {}
        self.remainder_mode = remainder_mode
        self.category_overrides = category_overrides or {}
        self.bonus_threshold = bonus_threshold

    def add_member(self, member: HouseholdMember) -> None:
        """Add a household member."""
        self.members.append(member)

    def remove_member(self, name: str) -> None:
        """Remove a household member by name."""
        self.members = [m for m in self.members if m.name != name]

    def get_member(self, name: str) -> HouseholdMember | None:
        """Get a member by name."""
        for m in self.members:
            if m.name == name:
                return m
        return None

    def calculate_split(
        self,
        shared_costs: float,
        shared_cost_items: list[dict[str, Any]] | None = None,
    ) -> list[SplitResult]:
        """Calculate the budget split for all members.

        Args:
            shared_costs: Total shared fixed costs for the month
            shared_cost_items: Optional itemized shared costs with categories

        Returns:
            List of SplitResult, one per member
        """
        if not self.members:
            return []

        # Calculate income ratios
        ratios = self._calculate_ratios()

        # Detect bonuses and adjust incomes
        adjusted_incomes: dict[str, float] = {}
        bonuses: dict[str, float] = {}
        for member in self.members:
            bonus = self._detect_bonus(member)
            bonuses[member.name] = bonus
            adjusted_incomes[member.name] = member.net_income - bonus

        # Calculate shared cost distribution
        if shared_cost_items and self.category_overrides:
            # Category-level split: apply per-category overrides
            cost_shares = self._calculate_category_split(
                shared_cost_items, ratios
            )
        else:
            # Global split: one ratio for all shared costs
            cost_shares = {
                m.name: shared_costs * ratios.get(m.name, 0)
                for m in self.members
            }

        # Build results
        results = []
        for member in self.members:
            share = cost_shares.get(member.name, 0)
            spielgeld = (
                adjusted_incomes[member.name]
                - share
                - member.individual_costs
            )
            results.append(
                SplitResult(
                    person=member.name,
                    gross_income=member.gross_income,
                    net_income=member.net_income,
                    income_ratio=ratios.get(member.name, 0),
                    shared_costs_share=round(share, 2),
                    individual_costs=member.individual_costs,
                    spielgeld=round(spielgeld, 2),
                    bonus_amount=round(bonuses[member.name], 2),
                )
            )

        # Apply remainder split if configured
        if self.remainder_mode == "equal_split":
            results = self._apply_equal_remainder(results)

        return results

    def _calculate_ratios(self) -> dict[str, float]:
        """Calculate split ratios based on the selected mode."""
        if self.split_mode == "equal":
            n = len(self.members)
            return {m.name: 1.0 / n for m in self.members} if n else {}

        elif self.split_mode == "proportional":
            total_income = sum(
                max(m.net_income, 0) for m in self.members
            )
            if total_income <= 0:
                # Fallback to equal if no positive income
                n = len(self.members)
                return {m.name: 1.0 / n for m in self.members}
            return {
                m.name: max(m.net_income, 0) / total_income
                for m in self.members
            }

        elif self.split_mode == "custom":
            # Normalize custom ratios to sum to 1.0
            total = sum(self.custom_ratios.values())
            if total <= 0:
                n = len(self.members)
                return {m.name: 1.0 / n for m in self.members}
            return {
                name: pct / total
                for name, pct in self.custom_ratios.items()
            }

        # Fallback
        n = len(self.members)
        return {m.name: 1.0 / n for m in self.members} if n else {}

    def _calculate_category_split(
        self,
        cost_items: list[dict[str, Any]],
        default_ratios: dict[str, float],
    ) -> dict[str, float]:
        """Calculate per-category split with overrides."""
        shares: dict[str, float] = {m.name: 0 for m in self.members}

        for item in cost_items:
            category = item.get("category", "other")
            amount = abs(float(item.get("amount", 0)))

            # Use category override if available, else default ratios
            ratios = self.category_overrides.get(
                category, default_ratios
            )

            for member in self.members:
                ratio = ratios.get(member.name, 0)
                shares[member.name] += amount * ratio

        return shares

    def _detect_bonus(self, member: HouseholdMember) -> float:
        """Detect if current income contains a bonus.

        Returns the bonus amount (excess over average) or 0.
        Bonus = income that is ≥ threshold% above 3-month average.
        """
        avg = member.income_average_3m
        if avg <= 0 or member.net_income <= 0:
            return 0.0

        increase_pct = (member.net_income - avg) / avg
        if increase_pct >= self.bonus_threshold:
            bonus = member.net_income - avg
            _LOGGER.info(
                "Bonus detected for %s: %.2f EUR (%.0f%% above average)",
                member.name,
                bonus,
                increase_pct * 100,
            )
            return bonus
        return 0.0

    @staticmethod
    def _apply_equal_remainder(
        results: list[SplitResult],
    ) -> list[SplitResult]:
        """Redistribute Spielgeld equally across all members."""
        total_spielgeld = sum(r.spielgeld for r in results)
        equal_share = total_spielgeld / len(results) if results else 0

        for r in results:
            r.spielgeld = round(equal_share, 2)

        return results

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model configuration (no financial data)."""
        return {
            "split_mode": self.split_mode,
            "custom_ratios": self.custom_ratios,
            "remainder_mode": self.remainder_mode,
            "category_overrides": self.category_overrides,
            "bonus_threshold": self.bonus_threshold,
            "member_count": len(self.members),
            "members": [
                {
                    "name": m.name,
                    "month_cycle": m.month_cycle,
                    "salary_day": m.salary_day,
                    "account_count": len(m.account_ids),
                }
                for m in self.members
            ],
        }

    @classmethod
    def from_config(
        cls, config: dict[str, Any]
    ) -> HouseholdModel:
        """Create a HouseholdModel from stored configuration."""
        members = []
        for m_data in config.get("members", []):
            members.append(
                HouseholdMember(
                    name=m_data["name"],
                    month_cycle=m_data.get("month_cycle", "calendar"),
                    salary_day=m_data.get("salary_day", 25),
                    account_ids=m_data.get("account_ids", []),
                )
            )

        return cls(
            members=members,
            split_mode=config.get("split_mode", DEFAULT_SPLIT_MODEL),
            custom_ratios=config.get("custom_ratios", {}),
            remainder_mode=config.get("remainder_mode", "none"),
            category_overrides=config.get("category_overrides", {}),
            bonus_threshold=config.get("bonus_threshold", 0.15),
        )
