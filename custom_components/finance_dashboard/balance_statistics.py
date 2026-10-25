"""Long-term statistics: balance history per account.

Every fetch appends balance points to the ledger.  This module turns them into
external statistics (``finance_dashboard:balance_<identity key>``) so HA's
history/energy-style graphs work without the entity having to be polled.

* ``has_sum=False``, no mean: a balance is a level, not a counter.
* One value per hour (the last point of that hour), hourly aligned, tz-aware.
* Only points from the last imported hour onwards (that hour may still
  change) are sent; the call is an upsert by ``start``, so a repeat is harmless.
* Older Home Assistant versions lack ``mean_type`` / ``unit_class`` on the
  metadata — they are added only when the installed TypedDict declares them.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant

from .account_identity import account_key
from .balances import amount_of, pick_balance
from .const import STATISTICS_SOURCE

_LOGGER = logging.getLogger(__name__)

_NON_ID = re.compile(r"[^a-z0-9_]")


def statistic_id_for(key: str) -> str:
    """``finance_dashboard:balance_<sanitized identity key>``."""
    return f"{STATISTICS_SOURCE}:balance_{_NON_ID.sub('_', str(key).lower())}"


def _parse(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def hourly_points(
    history: list[dict[str, Any]], newer_than: datetime | None = None
) -> tuple[list[tuple[datetime, float]], str]:
    """Reduce a balance history to ``[(hour_start, value)]`` plus the currency.

    Points sharing a fetch timestamp are different balance types of one
    snapshot; the booked one wins (same rule as the balance sensor).  Of
    several snapshots within one hour the latest wins.
    """
    snapshots: dict[datetime, list[dict[str, Any]]] = {}
    currency = ""
    for point in history:
        at = _parse(point.get("at"))
        if at is None:
            continue
        currency = point.get("currency") or currency
        snapshots.setdefault(at, []).append(
            {
                "balanceType": point.get("type", ""),
                "balanceAmount": {"amount": point.get("amount"), "currency": point.get("currency")},
            }
        )
    per_hour: dict[datetime, float] = {}
    for at in sorted(snapshots):
        value = amount_of(pick_balance(snapshots[at]))
        if value is None:
            continue
        per_hour[at.replace(minute=0, second=0, microsecond=0)] = value
    points = sorted(per_hour.items())
    if newer_than is not None:
        points = [(h, v) for h, v in points if h >= newer_than]
    return points, currency


def _metadata(statistic_id: str, name: str, unit: str | None) -> dict[str, Any]:
    """Build StatisticMetaData, feature-detecting newer fields."""
    from homeassistant.components.recorder.models import StatisticMetaData

    declared = getattr(StatisticMetaData, "__annotations__", {})
    meta: dict[str, Any] = {
        "has_sum": False,
        "name": name,
        "source": STATISTICS_SOURCE,
        "statistic_id": statistic_id,
        "unit_of_measurement": unit,
    }
    if "mean_type" in declared:
        from homeassistant.components.recorder.models import StatisticMeanType

        meta["mean_type"] = StatisticMeanType.NONE
        if "has_mean" in declared:
            meta["has_mean"] = False
    else:
        meta["has_mean"] = False
    if "unit_class" in declared:
        meta["unit_class"] = None
    return meta


async def _last_imported(hass: HomeAssistant, statistic_id: str) -> datetime | None:
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder import statistics as rec_stats

    try:
        result = await get_instance(hass).async_add_executor_job(
            rec_stats.get_last_statistics, hass, 1, statistic_id, True, {"state"}
        )
    except Exception:
        _LOGGER.debug("Could not read last imported statistic", exc_info=True)
        return None
    rows = (result or {}).get(statistic_id) or []
    if not rows:
        return None
    start = rows[0].get("start")
    if isinstance(start, (int, float)):
        return datetime.fromtimestamp(start, tz=UTC)
    return start if isinstance(start, datetime) else None


async def async_import_balance_statistics(
    hass: HomeAssistant, manager: Any, accounts: list[dict[str, Any]] | None = None
) -> int:
    """Import new balance history; returns the number of points sent.

    Never raises: statistics are a convenience and must not break a refresh.
    """
    if "recorder" not in hass.config.components:
        return 0
    try:
        from homeassistant.components.recorder import statistics as rec_stats
        from homeassistant.components.recorder.models import StatisticData
    except ImportError:
        return 0

    watermarks: dict[str, datetime | None] = manager.__dict__.setdefault("_stat_watermarks", {})
    sent = 0
    for account in accounts if accounts is not None else manager._accounts:
        try:
            key = account_key(account)
            statistic_id = statistic_id_for(key)
            if statistic_id not in watermarks:
                watermarks[statistic_id] = await _last_imported(hass, statistic_id)
            history = manager.get_balance_history(key)
            points, currency = hourly_points(history, watermarks[statistic_id])
            if not points:
                continue
            label = account.get("custom_name") or account.get("name", "")
            name = f"{account.get('institution', '')} {label}".strip()
            meta = _metadata(
                statistic_id,
                f"{name} balance" if name else "Balance",
                currency or account.get("currency", "EUR"),
            )
            rec_stats.async_add_external_statistics(
                hass, meta, [StatisticData(start=h, state=v) for h, v in points]
            )
            watermarks[statistic_id] = points[-1][0]
            sent += len(points)
        except Exception:
            _LOGGER.exception("Balance statistics import failed for one account — continuing")
    return sent
