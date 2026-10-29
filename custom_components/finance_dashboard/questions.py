"""Open questions: booked expenses the categoriser could not place.

A question is a *merchant*, not a booking: all open "other" expenses of the
cycle from one merchant collapse into one question with a count and total.
Bookings inside a transfer chain never become questions.  At most
``WEEKLY_QUESTIONS`` are offered per calendar week (answered ones count
against the quota), ordered by euro impact.  Each question carries its
bookings (date, amount, own account, counterparty, IBAN last four digits,
remittance text) and how often the merchant shows up over the whole history,
so the user can recognise what they are being asked about.  Pure functions;
no I/O.
"""

from __future__ import annotations

from typing import Any

WEEKLY_QUESTIONS = 10
SAMPLE_DATES = 3
MAX_BOOKINGS = 8


def merchant_history(bookings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per merchant over all given bookings: ``{count, first, last, months}``.

    ``months`` is the number of distinct calendar months the merchant appeared
    in -- "12 of 12 months" reads as a standing order, "1" as a one-off.
    """
    out: dict[str, dict[str, Any]] = {}
    for b in bookings:
        key = b.get("merchant")
        if not key:
            continue
        h = out.setdefault(key, {"count": 0, "first": b["date"], "last": b["date"], "months": set()})
        h["count"] += 1
        h["first"] = min(h["first"], b["date"])
        h["last"] = max(h["last"], b["date"])
        h["months"].add((b["date"].year, b["date"].month))
    return {
        k: {"count": h["count"], "first": h["first"].isoformat(), "last": h["last"].isoformat(),
            "months": len(h["months"])}
        for k, h in out.items()
    }


def select_questions(
    candidates: list[dict[str, Any]],
    *,
    week_answered: int = 0,
    suggest: Any = None,
    history: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Group candidates per merchant; return ``(visible, total_backlog)``.

    ``candidates``: dicts with ``merchant`` (key), ``display``, ``amount``
    (bank amount, expense negative), ``date`` and optional ``lid``,
    ``account``, ``counterparty``, ``counter_iban`` (last four digits only)
    and ``text``.  ``history`` comes from :func:`merchant_history`.
    ``total_backlog`` is the number of merchants waiting overall.
    """
    groups: dict[str, dict[str, Any]] = {}
    for c in candidates:
        key = c.get("merchant")
        if not key:
            continue
        g = groups.setdefault(
            key,
            {"id": key, "merchant": c.get("display") or key, "count": 0, "total": 0.0,
             "dates": [], "booking_ids": [], "bookings": []},
        )
        g["count"] += 1
        g["total"] += abs(float(c["amount"]))
        g["dates"].append(c["date"])
        if c.get("lid"):
            g["booking_ids"].append(c["lid"])
        g["bookings"].append(c)
    ordered = sorted(groups.values(), key=lambda g: (-g["total"], g["id"]))
    quota = max(0, WEEKLY_QUESTIONS - max(0, week_answered))
    visible = []
    for g in ordered[:quota]:
        dates = sorted(g.pop("dates"), reverse=True)[:SAMPLE_DATES]
        g["total"] = round(g["total"], 2)
        g["dates"] = [d.isoformat() for d in dates]
        rows = sorted(g.pop("bookings"), key=lambda c: c["date"], reverse=True)[:MAX_BOOKINGS]
        g["bookings"] = [
            {"date": c["date"].isoformat(), "amount": round(float(c["amount"]), 2),
             "account": c.get("account") or "", "counterparty": c.get("counterparty") or "",
             "iban_last4": c.get("counter_iban") or "", "text": c.get("text") or ""}
            for c in rows
        ]
        g["history"] = (history or {}).get(g["id"])
        g["suggested"] = suggest(g["id"]) if suggest else []
        visible.append(g)
    return visible, len(ordered)
