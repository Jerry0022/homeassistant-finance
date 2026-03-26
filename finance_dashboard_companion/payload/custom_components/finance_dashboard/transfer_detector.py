"""Cascading transfer detection.

Detects when the same money flow cascades through multiple accounts:
  HelloFresh -39.90 from PayPal → PayPal -39.90 from DKB → top-up DKB from savings

Without detection, this single €39.90 expense counts 3x in summaries.
The detector links these into a chain and marks intermediate legs so
the monthly summary counts the real expense only once.

IMPORTANT: Accounts like PayPal are NOT globally marked as intermediaries.
Only individual transactions are detected as pass-through when amount and
timing match across accounts.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .const import (
    REFUND_KEYWORDS,
    TRANSFER_AMOUNT_TOLERANCE,
    TRANSFER_AUTO_CONFIDENCE,
    TRANSFER_REFUND_WINDOW_DAYS,
    TRANSFER_TIME_WINDOW_DAYS,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TransferPair:
    """A matched pair of transactions across two accounts."""

    outgoing_txn_id: str
    incoming_txn_id: str
    outgoing_account_id: str
    incoming_account_id: str
    amount: float
    confidence: float
    date_delta_days: int


@dataclass
class TransferChain:
    """A chain of linked transfer pairs forming a cascade."""

    chain_id: str
    pairs: list[TransferPair] = field(default_factory=list)
    txn_ids: list[str] = field(default_factory=list)
    source_txn_id: str = ""
    destination_txn_id: str = ""
    intermediate_txn_ids: list[str] = field(default_factory=list)
    total_confidence: float = 0.0


@dataclass
class RefundPair:
    """A refund matched to its original transaction."""

    refund_id: str
    original_txn_id: str
    refund_txn_id: str
    amount: float
    creditor: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_transfer_chains(
    transactions: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> tuple[list[TransferChain], list[RefundPair]]:
    """Detect cascading transfers and refunds in transaction list.

    Args:
        transactions: All transactions (enriched with _account_id etc.)
        accounts: Account metadata list
        config: Optional overrides for tolerances/thresholds

    Returns:
        Tuple of (chains, refunds)
    """
    cfg = _merge_config(config)

    # Only process booked transactions
    booked = [t for t in transactions if t.get("_status") == "booked"]

    # Phase A — find transfer pairs
    pairs = _find_transfer_pairs(booked, accounts, cfg)
    _LOGGER.debug("Phase A: found %d transfer pairs", len(pairs))

    # Phase B — resolve cascades into chains
    chains = _resolve_chains(pairs, booked)
    _LOGGER.debug("Phase B: resolved %d chains", len(chains))

    # Phase C — detect refunds (independent of chains)
    refunds = _detect_refunds(booked, cfg)
    _LOGGER.debug("Phase C: found %d refund pairs", len(refunds))

    _LOGGER.info(
        "Transfer detection: %d chains, %d refund pairs",
        len(chains),
        len(refunds),
    )
    return chains, refunds


def enrich_transactions(
    transactions: list[dict[str, Any]],
    chains: list[TransferChain],
    refunds: list[RefundPair],
) -> list[dict[str, Any]]:
    """Add transfer chain and refund metadata to transactions.

    Mutates the transaction dicts in place and returns the same list.
    """
    # Build lookup: txn_id → chain info
    chain_lookup: dict[str, tuple[TransferChain, str]] = {}
    for chain in chains:
        for txn_id in chain.txn_ids:
            if txn_id == chain.source_txn_id:
                role = "source"
            elif txn_id == chain.destination_txn_id:
                role = "destination"
            else:
                role = "intermediate"
            chain_lookup[txn_id] = (chain, role)

    # Build lookup: txn_id → refund info
    refund_lookup: dict[str, tuple[str, str]] = {}
    for ref in refunds:
        refund_lookup[ref.original_txn_id] = (ref.refund_id, "original")
        refund_lookup[ref.refund_txn_id] = (ref.refund_id, "refund")

    for txn in transactions:
        txn_id = txn.get("transactionId", "")

        # Chain enrichment
        if txn_id in chain_lookup:
            chain, role = chain_lookup[txn_id]
            txn["_transfer_chain_id"] = chain.chain_id
            txn["_transfer_role"] = role
            txn["_transfer_linked_txns"] = [
                tid for tid in chain.txn_ids if tid != txn_id
            ]
            txn["_transfer_confidence"] = chain.total_confidence
            txn["_transfer_confirmed"] = None  # awaiting user action
        else:
            txn["_transfer_chain_id"] = None
            txn["_transfer_role"] = None
            txn["_transfer_linked_txns"] = []
            txn["_transfer_confidence"] = None
            txn["_transfer_confirmed"] = None

        # Refund enrichment
        if txn_id in refund_lookup:
            refund_id, refund_role = refund_lookup[txn_id]
            txn["_refund_pair_id"] = refund_id
            txn["_refund_role"] = refund_role
        else:
            txn["_refund_pair_id"] = None
            txn["_refund_role"] = None

    return transactions


def get_effective_transactions(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter out intermediate and destination legs of transfer chains.

    Returns only the transactions that should count in summaries:
    - Source legs of chains (the real expense/outflow)
    - All non-chain transactions
    - Rejected chains (user said "no") are kept as-is

    Intermediate and destination legs are excluded so money isn't
    double-counted when it cascades through accounts.
    """
    effective = []
    for txn in transactions:
        role = txn.get("_transfer_role")
        confirmed = txn.get("_transfer_confirmed")

        # User rejected the chain → treat as independent transaction
        if confirmed is False:
            effective.append(txn)
            continue

        # Intermediate or destination legs of a chain → skip
        if role in ("intermediate", "destination"):
            continue

        # Source leg or no chain → include
        effective.append(txn)

    return effective


def apply_overrides(
    transactions: list[dict[str, Any]],
    overrides: dict[str, bool],
) -> None:
    """Apply user confirmations/rejections to chain-detected transactions.

    Args:
        transactions: Enriched transaction list
        overrides: {chain_id: True/False} from persistent storage
    """
    for txn in transactions:
        chain_id = txn.get("_transfer_chain_id")
        if chain_id and chain_id in overrides:
            txn["_transfer_confirmed"] = overrides[chain_id]


# ---------------------------------------------------------------------------
# Phase A — Pair detection
# ---------------------------------------------------------------------------

def _find_transfer_pairs(
    transactions: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[TransferPair]:
    """Find matching transaction pairs across different accounts."""
    tolerance = config["amount_tolerance"]
    window_days = config["time_window_days"]
    auto_confidence = config["auto_confidence"]

    # Build account name lookup for creditor/debtor matching
    account_names = _build_account_name_set(accounts)

    # Separate outgoing (negative) and incoming (positive) transactions
    outgoing = []
    incoming = []
    for txn in transactions:
        amount = float(
            txn.get("transactionAmount", {}).get("amount", 0)
        )
        if amount < 0:
            outgoing.append(txn)
        elif amount > 0:
            incoming.append(txn)

    # Index incoming by amount bucket for faster lookup
    incoming_by_amount = _bucket_by_amount(incoming, tolerance)

    pairs: list[TransferPair] = []
    used_incoming: set[str] = set()

    for out_txn in outgoing:
        out_amount = abs(
            float(out_txn["transactionAmount"]["amount"])
        )
        out_date = _parse_date(out_txn.get("bookingDate", ""))
        out_account = out_txn.get("_account_id", "")
        out_id = out_txn.get("transactionId", "")

        if not out_date or not out_account:
            continue

        # Find candidate incoming transactions with similar amount
        candidates = _get_amount_candidates(
            incoming_by_amount, out_amount, tolerance
        )

        best_match: TransferPair | None = None
        best_confidence = 0.0

        for in_txn in candidates:
            in_id = in_txn.get("transactionId", "")
            if in_id in used_incoming:
                continue

            in_account = in_txn.get("_account_id", "")
            if in_account == out_account:
                continue  # Same account — not a transfer

            in_amount = float(in_txn["transactionAmount"]["amount"])
            in_date = _parse_date(in_txn.get("bookingDate", ""))
            if not in_date:
                continue

            date_delta = abs((out_date - in_date).days)
            if date_delta > window_days:
                continue

            confidence = _score_pair(
                out_txn, in_txn, out_amount, in_amount,
                date_delta, account_names, tolerance,
            )

            if confidence >= auto_confidence and confidence > best_confidence:
                best_confidence = confidence
                best_match = TransferPair(
                    outgoing_txn_id=out_id,
                    incoming_txn_id=in_id,
                    outgoing_account_id=out_account,
                    incoming_account_id=in_account,
                    amount=out_amount,
                    confidence=confidence,
                    date_delta_days=date_delta,
                )

        if best_match:
            pairs.append(best_match)
            used_incoming.add(best_match.incoming_txn_id)

    return pairs


def _score_pair(
    out_txn: dict[str, Any],
    in_txn: dict[str, Any],
    out_amount: float,
    in_amount: float,
    date_delta: int,
    account_names: set[str],
    tolerance: float,
) -> float:
    """Calculate confidence score for a candidate transfer pair."""
    score = 0.0

    # Amount match
    amount_diff = abs(out_amount - in_amount)
    if amount_diff < 0.01:
        score += 0.4
    elif amount_diff <= tolerance:
        score += 0.2

    # Date proximity
    if date_delta <= 1:
        score += 0.3
    elif date_delta <= 2:
        score += 0.2
    elif date_delta <= 3:
        score += 0.1

    # Account name appears in creditor/debtor fields
    out_account_name = _normalize(
        out_txn.get("_account_name", "")
    )
    in_account_name = _normalize(
        in_txn.get("_account_name", "")
    )

    out_creditor = _normalize(out_txn.get("creditorName", ""))
    out_debtor = _normalize(out_txn.get("debtorName", ""))
    in_creditor = _normalize(in_txn.get("creditorName", ""))
    in_debtor = _normalize(in_txn.get("debtorName", ""))
    out_remittance = _normalize(
        out_txn.get("remittanceInformationUnstructured", "")
    )
    in_remittance = _normalize(
        in_txn.get("remittanceInformationUnstructured", "")
    )

    # Does the outgoing creditor reference the incoming account?
    if in_account_name and (
        in_account_name in out_creditor
        or in_account_name in out_remittance
    ):
        score += 0.3
    # Does the incoming debtor reference the outgoing account?
    elif out_account_name and (
        out_account_name in in_debtor
        or out_account_name in in_remittance
    ):
        score += 0.3
    # Check against known account names in the system
    elif _any_account_name_match(
        out_creditor, in_debtor, account_names
    ):
        score += 0.2

    # Category is already "transfers"
    if out_txn.get("category") == "transfers":
        score += 0.1
    if in_txn.get("category") == "transfers":
        score += 0.1

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Phase B — Cascade resolution
# ---------------------------------------------------------------------------

def _resolve_chains(
    pairs: list[TransferPair],
    transactions: list[dict[str, Any]],
) -> list[TransferChain]:
    """Build transfer chains from pairs by linking cascades.

    If account B has both an incoming pair (from A) and an outgoing pair
    (to C), these are merged into a single chain A → B → C.
    """
    if not pairs:
        return []

    # Build adjacency: incoming_txn_id → pair (the pair that delivers to B)
    delivers_to: dict[str, TransferPair] = {}
    for pair in pairs:
        delivers_to[pair.incoming_txn_id] = pair

    # Build adjacency: outgoing_txn_id → pair (the pair that takes from B)
    takes_from: dict[str, TransferPair] = {}
    for pair in pairs:
        takes_from[pair.outgoing_txn_id] = pair

    # Transaction lookup for account resolution
    txn_lookup = {
        t.get("transactionId", ""): t for t in transactions
    }

    # Find chains by following the cascade
    visited_pairs: set[int] = set()
    chains: list[TransferChain] = []

    for pair in pairs:
        pair_id = id(pair)
        if pair_id in visited_pairs:
            continue

        # Walk backward to find the start of the chain
        chain_pairs = [pair]
        visited_pairs.add(pair_id)

        # Walk backward: is there a pair that delivers to our outgoing account?
        current = pair
        while True:
            # The outgoing txn of current pair — is it also an incoming txn
            # of another pair? That means money flowed IN before flowing OUT.
            out_txn = txn_lookup.get(current.outgoing_txn_id, {})
            out_account = out_txn.get("_account_id", "")

            # Find a pair where incoming_account == our outgoing_account
            # AND the incoming amount matches
            predecessor = _find_matching_predecessor(
                current, out_account, pairs, visited_pairs, txn_lookup,
            )
            if predecessor:
                chain_pairs.insert(0, predecessor)
                visited_pairs.add(id(predecessor))
                current = predecessor
            else:
                break

        # Walk forward: does the destination have an outgoing pair?
        current = pair
        while True:
            in_txn = txn_lookup.get(current.incoming_txn_id, {})
            in_account = in_txn.get("_account_id", "")

            successor = _find_matching_successor(
                current, in_account, pairs, visited_pairs, txn_lookup,
            )
            if successor:
                chain_pairs.append(successor)
                visited_pairs.add(id(successor))
                current = successor
            else:
                break

        # Build the chain
        chain = _build_chain(chain_pairs, txn_lookup)
        chains.append(chain)

    return chains


def _find_matching_predecessor(
    current: TransferPair,
    out_account: str,
    pairs: list[TransferPair],
    visited: set[int],
    txn_lookup: dict[str, dict[str, Any]],
) -> TransferPair | None:
    """Find a pair that delivers money to the outgoing account of current."""
    for pair in pairs:
        if id(pair) in visited:
            continue
        if pair.incoming_account_id != out_account:
            continue
        # Amount should be similar
        if abs(pair.amount - current.amount) > TRANSFER_AMOUNT_TOLERANCE:
            continue
        # The incoming txn date should be close to outgoing txn date
        in_txn = txn_lookup.get(pair.incoming_txn_id, {})
        out_txn = txn_lookup.get(current.outgoing_txn_id, {})
        in_date = _parse_date(in_txn.get("bookingDate", ""))
        out_date = _parse_date(out_txn.get("bookingDate", ""))
        if in_date and out_date:
            if abs((in_date - out_date).days) <= TRANSFER_TIME_WINDOW_DAYS:
                return pair
    return None


def _find_matching_successor(
    current: TransferPair,
    in_account: str,
    pairs: list[TransferPair],
    visited: set[int],
    txn_lookup: dict[str, dict[str, Any]],
) -> TransferPair | None:
    """Find a pair that takes money from the incoming account of current."""
    for pair in pairs:
        if id(pair) in visited:
            continue
        if pair.outgoing_account_id != in_account:
            continue
        if abs(pair.amount - current.amount) > TRANSFER_AMOUNT_TOLERANCE:
            continue
        in_txn = txn_lookup.get(current.incoming_txn_id, {})
        out_txn = txn_lookup.get(pair.outgoing_txn_id, {})
        in_date = _parse_date(in_txn.get("bookingDate", ""))
        out_date = _parse_date(out_txn.get("bookingDate", ""))
        if in_date and out_date:
            if abs((in_date - out_date).days) <= TRANSFER_TIME_WINDOW_DAYS:
                return pair
    return None


def _build_chain(
    chain_pairs: list[TransferPair],
    txn_lookup: dict[str, dict[str, Any]],
) -> TransferChain:
    """Build a TransferChain from an ordered list of pairs."""
    chain_id = str(uuid.uuid4())

    # Collect all unique transaction IDs in order
    all_txn_ids: list[str] = []
    seen: set[str] = set()
    for pair in chain_pairs:
        if pair.outgoing_txn_id not in seen:
            all_txn_ids.append(pair.outgoing_txn_id)
            seen.add(pair.outgoing_txn_id)
        if pair.incoming_txn_id not in seen:
            all_txn_ids.append(pair.incoming_txn_id)
            seen.add(pair.incoming_txn_id)

    # Source = first outgoing, Destination = last incoming
    source_txn_id = chain_pairs[0].outgoing_txn_id
    destination_txn_id = chain_pairs[-1].incoming_txn_id
    intermediate_txn_ids = [
        tid for tid in all_txn_ids
        if tid != source_txn_id and tid != destination_txn_id
    ]

    # Average confidence across all pairs
    avg_confidence = (
        sum(p.confidence for p in chain_pairs) / len(chain_pairs)
    )

    return TransferChain(
        chain_id=chain_id,
        pairs=chain_pairs,
        txn_ids=all_txn_ids,
        source_txn_id=source_txn_id,
        destination_txn_id=destination_txn_id,
        intermediate_txn_ids=intermediate_txn_ids,
        total_confidence=round(avg_confidence, 2),
    )


# ---------------------------------------------------------------------------
# Phase C — Refund detection
# ---------------------------------------------------------------------------

def _detect_refunds(
    transactions: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[RefundPair]:
    """Detect refund pairs: same amount, same creditor, same account."""
    window_days = config["refund_window_days"]
    refunds: list[RefundPair] = []
    used: set[str] = set()

    # Group outgoing transactions by (account, creditor)
    outgoing_index: dict[tuple[str, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for txn in transactions:
        amount = float(
            txn.get("transactionAmount", {}).get("amount", 0)
        )
        if amount >= 0:
            continue
        account = txn.get("_account_id", "")
        creditor = _normalize(txn.get("creditorName", ""))
        if account and creditor:
            outgoing_index[(account, creditor)].append(txn)

    # Search incoming transactions for refund matches
    for txn in transactions:
        amount = float(
            txn.get("transactionAmount", {}).get("amount", 0)
        )
        if amount <= 0:
            continue

        txn_id = txn.get("transactionId", "")
        if txn_id in used:
            continue

        account = txn.get("_account_id", "")
        # For refunds, the creditor on the incoming side is who sends money back
        creditor = _normalize(
            txn.get("creditorName", "")
            or txn.get("debtorName", "")
        )
        if not account or not creditor:
            continue

        # Check if this looks like a refund (text contains refund keyword)
        text = _normalize(
            txn.get("remittanceInformationUnstructured", "")
        )
        creditor_text = _normalize(txn.get("creditorName", ""))
        combined = f"{text} {creditor_text}"
        is_refund_text = any(kw in combined for kw in REFUND_KEYWORDS)
        if not is_refund_text:
            continue

        in_date = _parse_date(txn.get("bookingDate", ""))
        if not in_date:
            continue

        # Find matching outgoing transaction
        candidates = outgoing_index.get((account, creditor), [])
        for orig in candidates:
            orig_id = orig.get("transactionId", "")
            if orig_id in used:
                continue

            orig_amount = abs(
                float(orig["transactionAmount"]["amount"])
            )
            if abs(orig_amount - amount) > 0.01:
                continue

            orig_date = _parse_date(orig.get("bookingDate", ""))
            if not orig_date:
                continue

            # Refund must come AFTER the original
            delta = (in_date - orig_date).days
            if 0 <= delta <= window_days:
                refund_id = str(uuid.uuid4())
                refunds.append(
                    RefundPair(
                        refund_id=refund_id,
                        original_txn_id=orig_id,
                        refund_txn_id=txn_id,
                        amount=amount,
                        creditor=creditor,
                    )
                )
                used.add(txn_id)
                used.add(orig_id)
                break

    return refunds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_config(
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge user config with defaults."""
    defaults = {
        "amount_tolerance": TRANSFER_AMOUNT_TOLERANCE,
        "time_window_days": TRANSFER_TIME_WINDOW_DAYS,
        "refund_window_days": TRANSFER_REFUND_WINDOW_DAYS,
        "auto_confidence": TRANSFER_AUTO_CONFIDENCE,
    }
    if config:
        defaults.update(config)
    return defaults


def _parse_date(date_str: str) -> datetime | None:
    """Parse YYYY-MM-DD date string."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def _normalize(text: str) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


def _build_account_name_set(
    accounts: list[dict[str, Any]],
) -> set[str]:
    """Build a set of normalized account names and institution names."""
    names: set[str] = set()
    for acc in accounts:
        for key in ("name", "custom_name", "institution"):
            val = acc.get(key, "")
            if val:
                normalized = _normalize(val)
                if len(normalized) >= 3:  # Skip very short names
                    names.add(normalized)
    return names


def _any_account_name_match(
    creditor: str, debtor: str, account_names: set[str],
) -> bool:
    """Check if creditor or debtor contains any known account name."""
    for name in account_names:
        if name in creditor or name in debtor:
            return True
    return False


def _bucket_by_amount(
    transactions: list[dict[str, Any]],
    tolerance: float,
) -> dict[int, list[dict[str, Any]]]:
    """Index transactions by rounded amount for fast lookup."""
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for txn in transactions:
        amount = abs(
            float(txn.get("transactionAmount", {}).get("amount", 0))
        )
        # Use integer cents as bucket key
        bucket = int(round(amount * 100))
        buckets[bucket].append(txn)
    return buckets


def _get_amount_candidates(
    buckets: dict[int, list[dict[str, Any]]],
    amount: float,
    tolerance: float,
) -> list[dict[str, Any]]:
    """Get transactions with similar amounts from the bucket index."""
    target = int(round(amount * 100))
    tolerance_cents = int(round(tolerance * 100))
    candidates = []
    for bucket_key in range(
        target - tolerance_cents, target + tolerance_cents + 1
    ):
        candidates.extend(buckets.get(bucket_key, []))
    return candidates
