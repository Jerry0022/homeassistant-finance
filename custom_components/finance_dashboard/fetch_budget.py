"""Per-bank fetch budget.

The 4/day cap belongs to the *bank* (ASPSP) and, under PSD2 RTS Art. 36(5)(b),
applies only to requests made while the user is NOT in session.  So:

* **Background** calls (no PSU headers) are counted per account per local
  day (the household's "today"; a UTC day showed yesterday's 06:30 call as
  "today" until 01:00/02:00 local time).
  The scheduled daily refresh may use at most ``scheduled_share`` of the
  ``limit``; any other background call may use the whole limit.
* **Attended** calls (PSU headers present) are never capped and never gated on
  a block.  They are only debounced: a second attended refresh of the same
  bank within ``debounce_seconds`` is ignored.
* A 429 blocks *that bank's background access* until ``blocked_until``; other
  banks are unaffected.

Pure logic with injectable time, persisted via ``to_dict``/``from_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from .const import (
    ATTENDED_DEBOUNCE_SECONDS,
    ENABLEBANKING_RATE_LIMIT_DAILY,
    RATE_LIMIT_ATTENDED_BACKOFF_MINUTES,
    RATE_LIMIT_BACKOFF_HOURS,
    SCHEDULED_BACKGROUND_SHARE,
)


@dataclass(frozen=True)
class Decision:
    """Outcome of a gate check."""

    allowed: bool
    reason: str = "ok"  # ok | blocked | budget_exhausted | debounced


def _utc(now: datetime | None) -> datetime:
    now = now or datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class FetchBudget:
    """Budget + health state for every linked bank."""

    def __init__(
        self,
        limit: int = ENABLEBANKING_RATE_LIMIT_DAILY,
        scheduled_share: int = SCHEDULED_BACKGROUND_SHARE,
        debounce_seconds: int = ATTENDED_DEBOUNCE_SECONDS,
        tz: tzinfo = UTC,
    ) -> None:
        self.limit = limit
        self.tz = tz
        self.scheduled_share = scheduled_share
        self.debounce_seconds = debounce_seconds
        self._banks: dict[str, dict[str, Any]] = {}

    # -- state -------------------------------------------------------------

    def _bank(self, bank_id: str) -> dict[str, Any]:
        return self._banks.setdefault(
            bank_id,
            {
                "used": {},
                "blocked_until": None,
                "last_success": None,
                "last_error": None,
                "last_attended_at": None,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {k: dict(v) for k, v in self._banks.items()}

    def load(self, data: Any) -> None:
        self._banks = {}
        if not isinstance(data, dict):
            return
        for bank_id, state in data.items():
            if isinstance(state, dict):
                self._banks[bank_id] = {**self._bank(bank_id), **state}

    # -- queries -----------------------------------------------------------

    def _day(self, now: datetime) -> str:
        return now.astimezone(self.tz).strftime("%Y-%m-%d")

    def used_today(self, bank_id: str, now: datetime | None = None) -> int:
        """Background calls today for the busiest account of the bank."""
        now = _utc(now)
        day = self._day(now)
        counts = [
            int(rec.get("count", 0))
            for rec in self._bank(bank_id)["used"].values()
            if rec.get("day") == day
        ]
        return max(counts, default=0)

    def blocked_until(self, bank_id: str, now: datetime | None = None) -> datetime | None:
        until = _parse(self._bank(bank_id)["blocked_until"])
        return until if until and _utc(now) < until else None

    def decide(
        self,
        bank_id: str,
        *,
        attended: bool,
        scheduled: bool = False,
        now: datetime | None = None,
    ) -> Decision:
        """May a fetch of this bank start now?"""
        now = _utc(now)
        if attended:
            last = _parse(self._bank(bank_id)["last_attended_at"])
            if last and (now - last).total_seconds() < self.debounce_seconds:
                return Decision(False, "debounced")
            return Decision(True)
        if self.blocked_until(bank_id, now):
            return Decision(False, "blocked")
        cap = self.scheduled_share if scheduled else self.limit
        if self.used_today(bank_id, now) >= min(cap, self.limit):
            return Decision(False, "budget_exhausted")
        return Decision(True)

    # -- recording ---------------------------------------------------------

    def record_attempt(
        self, bank_id: str, account_key: str, *, attended: bool, now: datetime | None = None
    ) -> None:
        """Count one fetch round of one account (background only counts)."""
        now = _utc(now)
        bank = self._bank(bank_id)
        if attended:
            bank["last_attended_at"] = now.isoformat()
            return
        rec = bank["used"].get(account_key)
        day = self._day(now)
        if not rec or rec.get("day") != day:
            rec = {"day": day, "count": 0}
        rec["count"] += 1
        bank["used"][account_key] = rec

    def record_success(self, bank_id: str, now: datetime | None = None) -> None:
        bank = self._bank(bank_id)
        bank["last_success"] = _utc(now).isoformat()
        bank["last_error"] = None

    def record_error(self, bank_id: str, error: str) -> None:
        # Class-level text only — never bank payloads.
        self._bank(bank_id)["last_error"] = error[:160]

    def block(
        self,
        bank_id: str,
        *,
        retry_after_seconds: int | None = None,
        attended: bool = False,
        now: datetime | None = None,
    ) -> datetime:
        """Back off one bank after HTTP 429; honours Retry-After."""
        now = _utc(now)
        if retry_after_seconds is not None:
            until = now + timedelta(seconds=retry_after_seconds)
        elif attended:
            until = now + timedelta(minutes=RATE_LIMIT_ATTENDED_BACKOFF_MINUTES)
        else:
            until = now + timedelta(hours=RATE_LIMIT_BACKOFF_HOURS)
        bank = self._bank(bank_id)
        bank["blocked_until"] = until.isoformat()
        return until

    def status(
        self,
        bank_id: str,
        *,
        consent_valid_until: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Entity-facing status of one bank."""
        bank = self._bank(bank_id)
        blocked = self.blocked_until(bank_id, now)
        return {
            "bank_id": bank_id,
            "budget_used_today": self.used_today(bank_id, now),
            "budget_limit": self.limit,
            "blocked_until": blocked.isoformat() if blocked else None,
            "last_success": bank["last_success"],
            "last_error": bank["last_error"],
            # Attended fetches are uncapped and so absent from the budget count;
            # this keeps them visible next to it.
            "last_attended_at": bank["last_attended_at"],
            "consent_valid_until": consent_valid_until,
        }
