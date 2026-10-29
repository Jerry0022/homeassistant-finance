"""QuestionsMixin -- open questions and learning from the user's answers.

Derivation always runs from the ledger (``_derive_from_ledger``); an answer
changes the memory and re-derives, it never mutates the ledger.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import CATEGORY_OTHER, DEFAULT_CATEGORIES
from ..merchants import POINT_EVERY, merchant_key
from ..points_target import EVENT_POINTS_AWARDED, async_award, person_of_user

_LOGGER = logging.getLogger(__name__)

EVENT_POINTS = EVENT_POINTS_AWARDED
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_FALLBACK_SUGGESTIONS = ("shopping", "food", "leisure")
_NOT_SUGGESTED = (CATEGORY_OTHER, "income", "transfers")
REACH_BOOKING = "booking"
REACH_MERCHANT = "merchant"
_MAX_ID = 120


class QuestionError(Exception):
    """Invalid answer; ``code`` is machine-readable."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class QuestionsMixin:
    """Question list + answering for FinanceDashboardManager."""

    def _week_answered(self) -> int:
        mem = getattr(self, "_memory", None)
        return mem.week_answered(dt_util.now().date()) if mem else 0

    def _suggest_categories(self, _merchant_id: str) -> list[str]:
        """Top 3: categories the user taught most often, padded with defaults."""
        mem = getattr(self, "_memory", None)
        counts = Counter(
            r.get("category") for r in (mem.known_merchants().values() if mem else [])
        )
        out = [c for c, _ in counts.most_common() if c and c not in _NOT_SUGGESTED]
        for c in (*_FALLBACK_SUGGESTIONS, *DEFAULT_CATEGORIES):
            if len(out) >= 3:  # noqa: PLR2004
                break
            if c not in out and c not in _NOT_SUGGESTED:
                out.append(c)
        return out[:3]

    def _question_kwargs(self) -> dict[str, Any]:
        return {"week_answered": self._week_answered(), "suggest": self._suggest_categories}

    def get_questions(self) -> dict[str, Any]:
        """Open questions of the household cycle (cache read, admin only)."""
        data = self.get_home(
            person=None, view="household", horizon="cycle", include_questions=True
        )
        mem = getattr(self, "_memory", None)
        today = dt_util.now().date()
        return {
            "questions": data.get("questions", []),
            "questions_open": data.get("questions_open", 0),
            "questions_total": data.get("questions_total", 0),
            "answered_total": mem.answered if mem else 0,
            "week_answered": mem.week_answered(today) if mem else 0,
            "points": mem.points if mem else 0,
            "points_every": POINT_EVERY,
        }

    def _valid_owners(self) -> set[str]:
        owners = {"shared"}
        owners |= {str(p.get("name")) for p in self.persons if p.get("name")}
        owners |= {str(a.get("person")) for a in self._accounts if a.get("person")}
        return owners

    async def async_answer_question(
        self,
        *,
        question_id: str,
        category: str,
        reach: str,
        owner: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply an answer; returns counters. Raises :class:`QuestionError`."""
        mem = getattr(self, "_memory", None)
        if mem is None or getattr(self, "_demo_mode", False):
            raise QuestionError("unavailable")
        if not isinstance(question_id, str) or not question_id or len(question_id) > _MAX_ID:
            raise QuestionError("invalid_id")
        if not isinstance(category, str) or not _SLUG.match(category) or category == CATEGORY_OTHER:
            raise QuestionError("invalid_category")
        if reach not in (REACH_BOOKING, REACH_MERCHANT):
            raise QuestionError("invalid_reach")
        if owner is not None and (not isinstance(owner, str) or owner not in self._valid_owners()):
            raise QuestionError("invalid_owner")

        if reach == REACH_MERCHANT:
            mem.learn_merchant(question_id, category, owner)
        else:
            lids = [
                tx["_ledger_id"]
                for tx in self._transactions
                if tx.get("_ledger_id")
                and tx.get("category") == CATEGORY_OTHER
                and not tx.get("_transfer_chain_id")
                and merchant_key(tx) == question_id
            ]
            if not lids:
                raise QuestionError("unknown_question")
            for lid in lids:
                mem.learn_booking(lid, category, owner)

        today = dt_util.now().date()
        point = mem.record_answer(today)
        await mem.async_save()
        self._derive_from_ledger(self._transfer_overrides)
        if point:
            from ..setup_wizard import async_load_state

            state = await async_load_state(self._hass)
            await async_award(
                self._hass,
                target=state.get("points_target", ""),
                user_id=user_id,
                person=person_of_user(self.persons, user_id),
                answered=mem.answered,
            )
        return {
            "answered_total": mem.answered,
            "week_answered": mem.week_answered(today),
            "point_awarded": point,
        }
