"""Household budget model — N-person split engine.

Supports:
- N household members with individual income and costs
- 4 split modes:
  * ``pooled_equal`` (default) — the household spreadsheet's model: shared
    costs are paid from the POOLED net income, the remainder is split equally,
    and each person then pays their own individual fixed costs out of that
    share. A person with negative net income is carried by the pool.
  * ``equal`` — shared costs split evenly, each person keeps their own income
  * ``proportional`` — shared costs split by income ratio
  * ``custom`` — manual percentages
- Remainder split: no split (each keeps own) or equal distribution
- Category-level split overrides (optional)
- Bonus detection and separation from regular income
- Month cycle: calendar or salary-based per person

The difference between ``pooled_equal`` and ``equal`` is not cosmetic. With
incomes 4874.39 / -275.40 and shared costs 3851.56, ``equal`` yields wildly
asymmetric pocket money (each person nets their own income minus half the
shared costs), while ``pooled_equal`` yields 196.21 / 186.07 — the two persons
differ only by their individual costs. The spreadsheet uses the latter.

SECURITY: This module operates purely on in-memory data.
No financial values are persisted by this module — persistence
is handled by the Manager via .storage/.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .const import (
    DEFAULT_SPLIT_MODEL,
    SPLIT_MODEL_CUSTOM,
    SPLIT_MODEL_EQUAL,
    SPLIT_MODEL_POOLED_EQUAL,
    SPLIT_MODEL_PROPORTIONAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class HouseholdMember:
    """A person in the household."""

    name: str
    gross_income: float = 0.0
    net_income: float = 0.0
    individual_costs: float = 0.0
    individual_cost_items: list[dict[str, Any]] = field(default_factory=list)
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
    # Pooled models only: this person's equal share of the pooled income that
    # remains after shared costs, before their own individual costs.
    remainder_share: float = 0.0

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

        # The pooled model does not distribute shared costs by ratio at all —
        # it pools the net income FIRST, pays the shared costs out of the pool,
        # and only then splits what is left. Handle it before the ratio modes.
        if self.split_mode == SPLIT_MODEL_POOLED_EQUAL:
            return self._calculate_pooled_equal(shared_costs, adjusted_incomes, bonuses, ratios)

        # Calculate shared cost distribution
        if shared_cost_items and self.category_overrides:
            # Category-level split: apply per-category overrides
            cost_shares = self._calculate_category_split(shared_cost_items, ratios)
        else:
            # Global split: one ratio for all shared costs
            cost_shares = {m.name: shared_costs * ratios.get(m.name, 0) for m in self.members}

        # Build results
        results = []
        for member in self.members:
            share = cost_shares.get(member.name, 0)
            spielgeld = adjusted_incomes[member.name] - share - member.individual_costs
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

    def _calculate_pooled_equal(
        self,
        shared_costs: float,
        adjusted_incomes: dict[str, float],
        bonuses: dict[str, float],
        ratios: dict[str, float],
    ) -> list[SplitResult]:
        """The household spreadsheet's split model.

        ``rest_total       = pooled_net_income - shared_costs``
        ``remainder_share  = rest_total / n``
        ``spielgeld[P]     = remainder_share - individual_costs[P]``

        Two consequences that the ratio-based modes cannot reproduce:

        - a person with negative net income is carried by the pool instead of
          ending up with an absurd negative Spielgeld
        - the only difference between two persons' Spielgeld is their own
          individual costs

        ``remainder_mode`` is deliberately ignored here: the remainder is
        already split equally by definition, so applying it again would flatten
        the individual-cost differences that this model exists to preserve.
        """
        n = len(self.members)
        if not n:
            return []

        pooled_income = sum(adjusted_incomes.values())
        rest_total = pooled_income - shared_costs
        remainder_share = rest_total / n
        # Reported for transparency: everyone carries the same share of the
        # shared costs in this model.
        equal_cost_share = shared_costs / n

        return [
            SplitResult(
                person=member.name,
                gross_income=member.gross_income,
                net_income=member.net_income,
                income_ratio=ratios.get(member.name, 0.0),
                shared_costs_share=round(equal_cost_share, 2),
                individual_costs=member.individual_costs,
                spielgeld=round(remainder_share - member.individual_costs, 2),
                bonus_amount=round(bonuses.get(member.name, 0.0), 2),
                remainder_share=round(remainder_share, 2),
            )
            for member in self.members
        ]

    def _calculate_ratios(self) -> dict[str, float]:
        """Calculate split ratios based on the selected mode.

        For ``pooled_equal`` the returned ratio is the person's actual share of
        the pooled net income. It is informational only — the pooled model does
        not use it to distribute costs — and it may be negative or exceed 1.0
        when another person's net income is negative.
        """
        n = len(self.members)

        if self.split_mode == SPLIT_MODEL_POOLED_EQUAL:
            total = sum(m.net_income for m in self.members)
            if total == 0:
                return {m.name: 1.0 / n for m in self.members} if n else {}
            return {m.name: m.net_income / total for m in self.members}

        if self.split_mode == SPLIT_MODEL_EQUAL:
            return {m.name: 1.0 / n for m in self.members} if n else {}

        elif self.split_mode == SPLIT_MODEL_PROPORTIONAL:
            total_income = sum(max(m.net_income, 0) for m in self.members)
            if total_income <= 0:
                # Fallback to equal if no positive income
                return {m.name: 1.0 / n for m in self.members} if n else {}
            return {m.name: max(m.net_income, 0) / total_income for m in self.members}

        elif self.split_mode == SPLIT_MODEL_CUSTOM:
            # Normalize custom ratios to sum to 1.0
            total = sum(self.custom_ratios.values())
            if total <= 0:
                n = len(self.members)
                return {m.name: 1.0 / n for m in self.members}
            return {name: pct / total for name, pct in self.custom_ratios.items()}

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
            ratios = self.category_overrides.get(category, default_ratios)

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
    def from_config(cls, config: dict[str, Any]) -> HouseholdModel:
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


def model_from_plan(
    plan: Any,
    month: int,
    year: int,
    split_mode: str = DEFAULT_SPLIT_MODEL,
    remainder_mode: str = "none",
    custom_ratios: dict[str, float] | None = None,
) -> tuple[HouseholdModel, float]:
    """Build a household model from a :class:`~.budget_plan.BudgetPlan`.

    This is the bridge between the PLAN side (what the household budgeted) and
    the split engine. Income and individual costs come from the plan's own
    per-person figures rather than being inferred from which account a debit
    happened to land on.

    Returns the model plus the month's net shared costs, ready to pass to
    :meth:`HouseholdModel.calculate_split`.
    """
    members = [
        HouseholdMember(
            name=person,
            gross_income=plan.income[person].deposit if person in plan.income else 0.0,
            net_income=plan.income_net(person),
            individual_costs=plan.cost_individual(person, month, year),
            individual_cost_items=[
                p.to_dict() for p in plan.positions_for(person) if p.is_active(month, year)
            ],
        )
        for person in plan.persons
    ]

    model = HouseholdModel(
        members=members,
        split_mode=split_mode,
        remainder_mode=remainder_mode,
        custom_ratios=custom_ratios or {},
    )
    return model, plan.cost_shared(month, year)
