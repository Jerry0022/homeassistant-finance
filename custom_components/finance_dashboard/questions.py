"""Open questions: booked expenses the categoriser could not place.

A question is a *merchant*, not a booking: all open "other" expenses of the
cycle from one merchant collapse into one question with a count and total.
Bookings inside a transfer chain never become questions.  At most
``WEEKLY_QUESTIONS`` are offered per calendar week (answered ones count
against the quota), ordered by euro impact.  Pure functions; no I/O.
"""

from __future__ import annotations

from typing import Any

WEEKLY_QUESTIONS = 10
SAMPLE_DATES = 3


def select_questions(
    candidates: list[dict[str, Any]],
    *,
    week_answered: int = 0,
    suggest: Any = None,
) -> tuple[list[dict[str, Any]], int]:
    """Group candidates per merchant; return ``(visible, total_backlog)``.

    ``candidates``: dicts with ``merchant`` (key), ``display``, ``amount``
    (bank amount, expense negative), ``date`` and optional ``lid``.
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
             "dates": [], "booking_ids": []},
        )
        g["count"] += 1
        g["total"] += abs(float(c["amount"]))
        g["dates"].append(c["date"])
        if c.get("lid"):
            g["booking_ids"].append(c["lid"])
    ordered = sorted(groups.values(), key=lambda g: (-g["total"], g["id"]))
    quota = max(0, WEEKLY_QUESTIONS - max(0, week_answered))
    visible = []
    for g in ordered[:quota]:
        dates = sorted(g.pop("dates"), reverse=True)[:SAMPLE_DATES]
        g["total"] = round(g["total"], 2)
        g["dates"] = [d.isoformat() for d in dates]
        g["suggested"] = suggest(g["id"]) if suggest else []
        visible.append(g)
    return visible, len(ordered)
