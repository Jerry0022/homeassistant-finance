"""Transfer plan — the monthly cash-flow choreography.

This is the operational output of the budget model, and the piece the
spreadsheet was actually used for month after month: an ordered ledger of
"move this much from this account to that account", per account, that ends in
each person's remaining pocket money.

It reproduces the spreadsheet's ``2026`` sheet, where accounts are columns and
transfer steps are rows:

    Einzahlung Gehalt
    Umbuchung Privatversicherungen
    Umbuchung Steuerausgleich
    = Saldo Geld zur Verfügung
    Umbuchung Lebenshaltungskosten
    Umbuchung Fixkosten Individuell
    Abbuchung Privatversicherungen
    Abbuchung Lebenshaltungskosten (ohne Puffer)
    Abbuchung Essen- und Haushaltspuffer
    Abbuchung Fixkosten Individuell
    = Saldo nach Fixkosten

Two invariants the spreadsheet enforced by hand and this module enforces in
code:

1. **Pass-through accounts net to zero.** A living-costs account only receives
   transfers in order to pay debits out; a non-zero balance means the plan does
   not add up, and the spreadsheet flagged that with conditional formatting.
2. **Contributions are liquidity-aware.** Each person is asked for an equal
   share of the shared costs, but a person whose net income cannot cover their
   share contributes only what they have, and the remainder is carried by those
   with a surplus. This is why, in the source spreadsheet, one person transfers
   the entire shared-cost total while the other transfers nothing.

Because of (2), the balance left on a person's account is NOT the same as the
pocket money the split model entitles them to. The difference — how much one
person is fronting for another — is reported as ``settlement_delta``, which the
spreadsheet never made explicit.

SECURITY: in-memory arithmetic only; nothing is persisted here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .const import (
    POSITION_KIND_BUFFER,
    POSITION_KIND_FIXED,
    TRANSFER_PLAN_ZERO_TOLERANCE,
)

_LOGGER = logging.getLogger(__name__)

ROLE_PRIMARY = "primary"  # salary lands here; pocket money remains here
ROLE_PASS_THROUGH = "pass_through"  # receives transfers, pays shared debits, nets to zero
ROLE_PERSONAL = "personal"  # any further personal account

# Row kinds — the frontend styles subtotals differently from movements.
ROW_DEPOSIT = "deposit"
ROW_TRANSFER = "transfer"
ROW_DEBIT = "debit"
ROW_SUBTOTAL = "subtotal"


@dataclass
class PlanAccount:
    """An account as a column of the transfer plan."""

    id: str
    label: str
    role: str
    person: str | None = None
    bank: str = ""

    @property
    def is_pass_through(self) -> bool:
        """Whether this account only passes money through to debits."""
        return self.role == ROLE_PASS_THROUGH


@dataclass
class TransferRow:
    """One row of the plan: a labelled movement across accounts.

    ``amounts`` maps account id to a signed delta: negative leaves the account,
    positive arrives. A transfer row therefore contains both legs, which is
    what makes the zero-sum check meaningful.
    """

    order: int
    label: str
    kind: str
    amounts: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the API."""
        return {
            "order": self.order,
            "label": self.label,
            "kind": self.kind,
            "amounts": {k: round(v, 2) for k, v in self.amounts.items()},
        }


@dataclass
class TransferPlan:
    """The complete monthly plan, ready for display or execution."""

    month: int
    year: int
    accounts: list[PlanAccount]
    rows: list[TransferRow]
    final_balances: dict[str, float]
    imbalances: dict[str, float]
    settlements: dict[str, dict[str, float]]
    # Amounts that could not be placed on any account, e.g. shared costs with
    # no joint account configured. Without this they would vanish from the plan
    # and it would still report itself as balanced.
    unplaced: list[dict[str, Any]] = field(default_factory=list)

    @property
    def balanced(self) -> bool:
        """True when every pass-through account nets to zero.

        An unplaced amount also counts as unbalanced: a plan that silently drops
        the shared costs is not a balanced plan, it is an incomplete one.
        """
        return not self.imbalances and not self.unplaced

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the API."""
        return {
            "month": self.month,
            "year": self.year,
            "accounts": [
                {
                    "id": a.id,
                    "label": a.label,
                    "role": a.role,
                    "person": a.person,
                    "bank": a.bank,
                }
                for a in self.accounts
            ],
            "rows": [r.to_dict() for r in self.rows],
            "final_balances": {k: round(v, 2) for k, v in self.final_balances.items()},
            "balanced": self.balanced,
            "imbalances": {k: round(v, 2) for k, v in self.imbalances.items()},
            "settlements": self.settlements,
            "unplaced": self.unplaced,
        }


def accounts_from_config(raw_accounts: list[dict[str, Any]]) -> list[PlanAccount]:
    """Derive plan accounts from the integration's account configuration.

    An explicit ``role`` in the account config always wins. Otherwise: shared
    accounts become pass-through accounts, and a person's first personal
    account becomes their primary (salary) account.
    """
    accounts: list[PlanAccount] = []
    seen_primary: set[str] = set()

    for raw in raw_accounts:
        account_id = str(raw.get("id") or "")
        if not account_id:
            continue
        person = raw.get("person") or None
        acc_type = raw.get("type", "personal")
        role = raw.get("role")

        if not role:
            if acc_type == "shared":
                role = ROLE_PASS_THROUGH
            elif person and person not in seen_primary:
                role = ROLE_PRIMARY
                seen_primary.add(person)
            else:
                role = ROLE_PERSONAL

        accounts.append(
            PlanAccount(
                id=account_id,
                label=str(raw.get("name") or raw.get("label") or account_id),
                role=role,
                person=person,
                bank=str(raw.get("bank") or ""),
            )
        )

    return accounts


def _primary_for(person: str, accounts: list[PlanAccount]) -> PlanAccount | None:
    """The account a person's salary lands on."""
    for acc in accounts:
        if acc.person == person and acc.role == ROLE_PRIMARY:
            return acc
    for acc in accounts:
        if acc.person == person:
            return acc
    return None


def _default_pass_through(accounts: list[PlanAccount]) -> PlanAccount | None:
    """The account shared costs are paid from."""
    for acc in accounts:
        if acc.is_pass_through:
            return acc
    return None


def _resolve_debit_account(
    position: Any,
    accounts: list[PlanAccount],
    by_id: dict[str, PlanAccount],
) -> PlanAccount | None:
    """Which account a cost position is actually debited from.

    An explicit ``debit_account`` on the position wins. Otherwise shared
    positions are debited from the pass-through account and individual
    positions from their owner's primary account.
    """
    if position.debit_account and position.debit_account in by_id:
        return by_id[position.debit_account]
    if position.is_shared:
        return _default_pass_through(accounts)
    return _primary_for(position.owner, accounts)


def _distribute_shortfall(
    shortfall: float,
    surplus: dict[str, float],
) -> dict[str, float]:
    """Spread an unfunded amount across the persons who have a surplus.

    Distribution is proportional to each person's surplus, so the person with
    the most headroom carries the most. If nobody has a surplus, the shortfall
    stays unfunded and surfaces as an imbalance rather than being hidden.
    """
    total_surplus = sum(surplus.values())
    if shortfall <= 0 or total_surplus <= 0:
        return {}
    return {
        person: shortfall * (amount / total_surplus)
        for person, amount in surplus.items()
        if amount > 0
    }


def build_transfer_plan(
    plan: Any,
    raw_accounts: list[dict[str, Any]],
    month: int,
    year: int,
    split_results: list[Any] | None = None,
) -> TransferPlan:
    """Build the monthly transfer choreography from the budget plan.

    Args:
        plan: The :class:`~.budget_plan.BudgetPlan`.
        raw_accounts: The integration's account configuration.
        month: Calendar month (1-12).
        year: Calendar year.
        split_results: Optional :class:`~.household.SplitResult` list. When
            given, each person's entitled pocket money is compared against the
            balance actually left on their account, yielding the settlement
            figures.

    Returns:
        A :class:`TransferPlan`. Never raises on an inconsistent plan — an
        unbalanced result is reported via ``imbalances``, and anything that could
        not be placed on an account at all via ``unplaced``, so the UI can show
        both instead of presenting a silently incomplete plan.
    """
    accounts = accounts_from_config(raw_accounts)
    by_id = {a.id: a for a in accounts}
    persons = list(plan.persons)
    rows: list[TransferRow] = []
    balances: dict[str, float] = {a.id: 0.0 for a in accounts}
    unplaced: list[dict[str, Any]] = []
    order = 0

    def add_row(label: str, kind: str, amounts: dict[str, float]) -> None:
        nonlocal order
        amounts = {k: v for k, v in amounts.items() if abs(v) > 0.001}
        if not amounts:
            return
        order += 1
        rows.append(TransferRow(order=order, label=label, kind=kind, amounts=amounts))
        for account_id, delta in amounts.items():
            balances[account_id] = balances.get(account_id, 0.0) + delta

    def snapshot(label: str) -> None:
        nonlocal order
        order += 1
        rows.append(
            TransferRow(
                order=order,
                label=label,
                kind=ROW_SUBTOTAL,
                amounts={k: round(v, 2) for k, v in balances.items()},
            )
        )

    pass_through = _default_pass_through(accounts)

    # A household with shared costs but no joint account has nowhere to book
    # them. Reporting that is essential: otherwise every shared position is
    # skipped further down, no account ends up out of balance, and the plan
    # cheerfully declares itself balanced while omitting the largest cost block.
    shared_net_check = plan.cost_shared(month, year)
    if pass_through is None and abs(shared_net_check) > 0.001:
        unplaced.append(
            {
                "reason": "no_shared_account",
                "amount": round(shared_net_check, 2),
                "detail": (
                    "Gemeinsame Kosten können nicht gebucht werden — kein "
                    "gemeinsames Konto konfiguriert."
                ),
            }
        )

    # -- 1. salary lands on each person's primary account -------------------
    deposits: dict[str, float] = {}
    for person in persons:
        entry = plan.income.get(person)
        primary = _primary_for(person, accounts)
        if primary is None:
            # A person with no account at all cannot receive or pay anything.
            # Their income and costs would otherwise disappear without trace.
            missing = round(
                (entry.deposit if entry else 0.0) + plan.cost_individual(person, month, year),
                2,
            )
            if abs(missing) > 0.001:
                unplaced.append(
                    {
                        "reason": "no_account_for_person",
                        "person": person,
                        "amount": missing,
                        "detail": f"Kein Konto für {person} zugeordnet.",
                    }
                )
            continue
        if not entry:
            continue
        deposits[primary.id] = deposits.get(primary.id, 0.0) + entry.deposit
    add_row("Einzahlung Gehalt", ROW_DEPOSIT, deposits)

    # -- 2. move mandatory insurance to the account that debits it ----------
    # The insurance amount is part of the income breakdown (it is deducted
    # before net income), but it is a real debit that has to leave a real
    # account, so it needs both a transfer and a debit leg.
    insurance_moves: dict[str, float] = {}
    insurance_debits: dict[str, float] = {}
    for person in persons:
        entry = plan.income.get(person)
        primary = _primary_for(person, accounts)
        if not entry or not primary or not entry.insurance_mandatory:
            continue
        amount = abs(entry.insurance_mandatory)
        target = pass_through or primary
        if target.id != primary.id:
            insurance_moves[primary.id] = insurance_moves.get(primary.id, 0.0) - amount
            insurance_moves[target.id] = insurance_moves.get(target.id, 0.0) + amount
        insurance_debits[target.id] = insurance_debits.get(target.id, 0.0) - amount
    add_row("Umbuchung Privatversicherungen", ROW_TRANSFER, insurance_moves)

    # -- 3. tax-class settlement -------------------------------------------
    tax_moves: dict[str, float] = {}
    for person in persons:
        entry = plan.income.get(person)
        primary = _primary_for(person, accounts)
        if not entry or not primary or not entry.tax_adjustment:
            continue
        tax_moves[primary.id] = tax_moves.get(primary.id, 0.0) + entry.tax_adjustment
    add_row("Umbuchung Steuerausgleich", ROW_TRANSFER, tax_moves)

    snapshot("Saldo Geld zur Verfügung")

    # -- 4. fund the shared costs, liquidity-aware -------------------------
    shared_net = plan.cost_shared(month, year)
    n = len(persons) or 1
    target_share = shared_net / n

    available = {p: plan.income_net(p) for p in persons}
    contributions = {p: min(target_share, max(available[p], 0.0)) for p in persons}
    surplus = {p: max(available[p] - contributions[p], 0.0) for p in persons}
    shortfall = shared_net - sum(contributions.values())
    for person, extra in _distribute_shortfall(shortfall, surplus).items():
        contributions[person] += extra

    shared_moves: dict[str, float] = {}
    if pass_through:
        for person, amount in contributions.items():
            primary = _primary_for(person, accounts)
            if not primary or not amount:
                continue
            if primary.id == pass_through.id:
                continue
            shared_moves[primary.id] = shared_moves.get(primary.id, 0.0) - amount
            shared_moves[pass_through.id] = shared_moves.get(pass_through.id, 0.0) + amount
    add_row("Umbuchung Lebenshaltungskosten", ROW_TRANSFER, shared_moves)

    # -- 5. fund individual positions debited from a foreign account -------
    # e.g. one person's mobile contract paid from the joint account: the cost
    # stays theirs, but the money has to be where the debit happens.
    foreign_moves: dict[str, float] = {}
    for position in plan.active_positions(month, year):
        if position.is_shared:
            continue
        debit_account = _resolve_debit_account(position, accounts, by_id)
        owner_primary = _primary_for(position.owner, accounts)
        if not debit_account or not owner_primary or debit_account.id == owner_primary.id:
            continue
        amount = position.effective_amount(month, year)
        if not amount:
            continue
        foreign_moves[owner_primary.id] = foreign_moves.get(owner_primary.id, 0.0) - amount
        foreign_moves[debit_account.id] = foreign_moves.get(debit_account.id, 0.0) + amount
    add_row("Umbuchung Fixkosten Individuell", ROW_TRANSFER, foreign_moves)

    # -- 6. the actual debits ---------------------------------------------
    add_row("Abbuchung Privatversicherungen", ROW_DEBIT, insurance_debits)

    def debit_group(predicate) -> dict[str, float]:
        group: dict[str, float] = {}
        for position in plan.active_positions(month, year):
            if not predicate(position):
                continue
            amount = position.effective_amount(month, year)
            if not amount:
                continue
            debit_account = _resolve_debit_account(position, accounts, by_id)
            if not debit_account:
                # No account can pay this position. Record it instead of
                # dropping it — a silently omitted debit both understates the
                # month and lets the zero-sum check pass on an incomplete plan.
                unplaced.append(
                    {
                        "reason": "no_debit_account",
                        "position": position.name,
                        "owner": position.owner,
                        "amount": round(amount, 2),
                        "detail": (
                            f"Kein Konto für die Abbuchung von {position.name!r} gefunden."
                        ),
                    }
                )
                continue
            group[debit_account.id] = group.get(debit_account.id, 0.0) - amount
        return group

    add_row(
        "Abbuchung Lebenshaltungskosten (ohne Puffer)",
        ROW_DEBIT,
        debit_group(lambda p: p.is_shared and p.kind == POSITION_KIND_FIXED),
    )
    add_row(
        "Abbuchung Essen- und Haushaltspuffer",
        ROW_DEBIT,
        debit_group(lambda p: p.is_shared and p.kind == POSITION_KIND_BUFFER),
    )
    add_row(
        "Abbuchung Fixkosten Individuell",
        ROW_DEBIT,
        debit_group(lambda p: not p.is_shared),
    )

    snapshot("Saldo Geld zur Verfügung nach Fixkosten")

    # -- 7. invariant: pass-through accounts must net to zero --------------
    imbalances: dict[str, float] = {}
    for account in accounts:
        if not account.is_pass_through:
            continue
        residual = balances.get(account.id, 0.0)
        if abs(residual) > TRANSFER_PLAN_ZERO_TOLERANCE:
            imbalances[account.id] = round(residual, 2)
            _LOGGER.warning(
                "Transfer plan %04d-%02d: pass-through account %s does not net to zero (%.2f)",
                year,
                month,
                account.label,
                residual,
            )

    # -- 8. who is fronting for whom --------------------------------------
    settlements: dict[str, dict[str, float]] = {}
    if split_results:
        for result in split_results:
            primary = _primary_for(result.person, accounts)
            if not primary:
                continue
            actual = round(balances.get(primary.id, 0.0), 2)
            entitled = round(result.spielgeld, 2)
            settlements[result.person] = {
                "account_balance": actual,
                "entitled_pocket_money": entitled,
                # Positive: this person is holding more than the split entitles
                # them to, because they fronted another person's share.
                "settlement_delta": round(actual - entitled, 2),
            }

    for entry in unplaced:
        _LOGGER.warning(
            "Transfer plan %04d-%02d: %s (%.2f EUR unplaced)",
            year,
            month,
            entry.get("detail", entry.get("reason", "unplaced amount")),
            entry.get("amount", 0.0),
        )

    return TransferPlan(
        month=month,
        year=year,
        accounts=accounts,
        rows=rows,
        final_balances={k: round(v, 2) for k, v in balances.items()},
        imbalances=imbalances,
        settlements=settlements,
        unplaced=unplaced,
    )
