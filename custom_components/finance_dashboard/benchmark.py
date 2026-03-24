"""Benchmark data provider — German national average comparisons.

Auto-crawls statistical data from public sources and caches locally.
Each datapoint includes: value, source, survey year, fetch date.

Sources:
- Destatis (Statistisches Bundesamt): housing, food, savings
- Bundesbank: debt/credit ratios
- GDV (Gesamtverband der Versicherungswirtschaft): insurance
- Deutscher Mieterbund: utility costs (Betriebskostenspiegel)

Display: text-based comparison, no visual gauges.
Example: "Wohnkosten: 35% (DE Ø 36%, Destatis 2024)"

SECURITY: Only public statistical data is fetched. No user data
is sent to any external service. Cached in .storage/.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

BENCHMARK_STORE_KEY = f"{DOMAIN}_benchmark"
BENCHMARK_CHECK_INTERVAL_DAYS = 30

# Embedded baseline data — updated manually with each release.
# Auto-crawl attempts to refresh these values monthly.
BASELINE_BENCHMARKS: list[dict[str, Any]] = [
    {
        "id": "housing_pct",
        "category": "housing",
        "label": "Wohnkosten",
        "metric": "Anteil am Haushaltseinkommen",
        "value": 36.0,
        "unit": "%",
        "source": "Destatis — Einkommens- und Verbrauchsstichprobe",
        "survey_year": 2023,
        "url": "https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/_inhalt.html",
    },
    {
        "id": "food_pct",
        "category": "food",
        "label": "Nahrungsmittel",
        "metric": "Anteil am Haushaltseinkommen",
        "value": 15.0,
        "unit": "%",
        "source": "Destatis — Einkommens- und Verbrauchsstichprobe",
        "survey_year": 2023,
        "url": "https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Einkommen-Konsum-Lebensbedingungen/_inhalt.html",
    },
    {
        "id": "savings_rate",
        "category": "savings",
        "label": "Sparquote",
        "metric": "Private Sparquote",
        "value": 11.4,
        "unit": "%",
        "source": "Destatis — Volkswirtschaftliche Gesamtrechnungen",
        "survey_year": 2024,
        "url": "https://www.destatis.de/DE/Themen/Wirtschaft/Volkswirtschaftliche-Gesamtrechnungen-Inlandsprodukt/_inhalt.html",
    },
    {
        "id": "debt_ratio",
        "category": "loans",
        "label": "Kreditbelastung",
        "metric": "Schuldendienstquote privater Haushalte",
        "value": 7.0,
        "unit": "%",
        "source": "Deutsche Bundesbank — Finanzstabilitätsbericht",
        "survey_year": 2024,
        "url": "https://www.bundesbank.de/de/publikationen/berichte/finanzstabilitaetsberichte",
    },
    {
        "id": "insurance_eur",
        "category": "insurance",
        "label": "Versicherungen",
        "metric": "Durchschnittliche monatliche Ausgaben",
        "value": 200.0,
        "unit": "EUR",
        "source": "GDV — Statistisches Taschenbuch der Versicherungswirtschaft",
        "survey_year": 2023,
        "url": "https://www.gdv.de/gdv/medien/zahlen-und-fakten",
    },
    {
        "id": "utilities_sqm",
        "category": "utilities",
        "label": "Nebenkosten",
        "metric": "Betriebskosten pro m² (warm)",
        "value": 2.88,
        "unit": "EUR/m²",
        "source": "Deutscher Mieterbund — Betriebskostenspiegel",
        "survey_year": 2022,
        "url": "https://www.mieterbund.de/mietrecht/betriebskostenspiegel.html",
    },
    {
        "id": "transport_eur",
        "category": "transport",
        "label": "Mobilität",
        "metric": "Monatliche Mobilitätskosten pro Haushalt",
        "value": 350.0,
        "unit": "EUR",
        "source": "Destatis / ADAC",
        "survey_year": 2023,
        "url": "https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Einkommen-Konsum-Lebensbedingungen/_inhalt.html",
    },
]


class BenchmarkProvider:
    """Provides German national average benchmark data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the benchmark provider."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, BENCHMARK_STORE_KEY)
        self._data: list[dict[str, Any]] = []
        self._last_check: datetime | None = None

    async def async_initialize(self) -> None:
        """Load cached benchmark data or use baseline."""
        cached = await self._store.async_load()
        if cached and "benchmarks" in cached:
            self._data = cached["benchmarks"]
            last_check = cached.get("last_check")
            if last_check:
                self._last_check = datetime.fromisoformat(last_check)
            _LOGGER.debug(
                "Loaded %d cached benchmarks (checked: %s)",
                len(self._data),
                self._last_check,
            )
        else:
            # Use embedded baseline
            self._data = BASELINE_BENCHMARKS
            await self._persist()
            _LOGGER.info("Initialized with %d baseline benchmarks", len(self._data))

    async def async_check_for_updates(self) -> bool:
        """Check if newer benchmark data is available.

        Runs monthly. Attempts to fetch updated values from public
        statistical APIs. Falls back to baseline if fetch fails.

        Returns True if data was updated.
        """
        if self._last_check:
            days_since = (datetime.now() - self._last_check).days
            if days_since < BENCHMARK_CHECK_INTERVAL_DAYS:
                return False

        _LOGGER.info("Checking for benchmark data updates...")
        updated = False

        try:
            # Attempt to fetch Destatis savings rate (public JSON API)
            savings = await self._fetch_destatis_savings_rate()
            if savings is not None:
                self._update_value("savings_rate", savings)
                updated = True
        except Exception:
            _LOGGER.debug("Destatis savings rate fetch failed, using cached")

        self._last_check = datetime.now()
        await self._persist()

        if updated:
            _LOGGER.info("Benchmark data updated")
        else:
            _LOGGER.debug("No benchmark updates available")

        return updated

    def get_benchmarks(self) -> list[dict[str, Any]]:
        """Get all benchmark datapoints."""
        return self._data

    def get_benchmark(self, benchmark_id: str) -> dict[str, Any] | None:
        """Get a specific benchmark by ID."""
        for b in self._data:
            if b["id"] == benchmark_id:
                return b
        return None

    def compare(
        self, category: str, user_value: float
    ) -> dict[str, Any] | None:
        """Compare a user's value against the national average.

        Returns comparison result with formatted text.
        Example: {
            "label": "Wohnkosten",
            "user_value": 35.0,
            "benchmark_value": 36.0,
            "difference": -1.0,
            "better": True,
            "text": "Wohnkosten: 35% (DE Ø 36%, Destatis 2023)"
        }
        """
        # Find benchmark by category
        benchmark = None
        for b in self._data:
            if b["category"] == category:
                benchmark = b
                break

        if not benchmark:
            return None

        bv = benchmark["value"]
        diff = user_value - bv
        unit = benchmark.get("unit", "%")

        # "Better" depends on context:
        # For costs: lower is better
        # For savings: higher is better
        better_is_lower = category != "savings"
        is_better = diff < 0 if better_is_lower else diff > 0

        # Format comparison text
        source_short = benchmark["source"].split("—")[0].strip()
        text = (
            f"{benchmark['label']}: {user_value:.0f}{unit} "
            f"(DE Ø {bv:.0f}{unit}, {source_short} {benchmark['survey_year']})"
        )

        return {
            "label": benchmark["label"],
            "category": category,
            "user_value": user_value,
            "benchmark_value": bv,
            "difference": round(diff, 1),
            "better": is_better,
            "unit": unit,
            "source": benchmark["source"],
            "survey_year": benchmark["survey_year"],
            "fetch_date": (
                self._last_check.strftime("%Y-%m-%d")
                if self._last_check
                else "embedded"
            ),
            "text": text,
        }

    def _update_value(
        self, benchmark_id: str, new_value: float
    ) -> None:
        """Update a benchmark value."""
        for b in self._data:
            if b["id"] == benchmark_id:
                old = b["value"]
                b["value"] = new_value
                b["fetch_date"] = datetime.now().strftime("%Y-%m-%d")
                _LOGGER.info(
                    "Benchmark %s updated: %.1f → %.1f",
                    benchmark_id,
                    old,
                    new_value,
                )
                break

    async def _fetch_destatis_savings_rate(self) -> float | None:
        """Attempt to fetch the latest savings rate from Destatis GENESIS API."""
        # Destatis GENESIS-Online has a public REST API for some datasets
        # Table 81000-0120: Sparquote der privaten Haushalte
        url = (
            "https://www-genesis.destatis.de/genesisWS/rest/2020/"
            "data/tablefile?username=GEST&password=GEST&"
            "name=81000-0120&area=all&compress=false&"
            "format=ffcsv&language=de"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # Parse CSV for latest savings rate
                        return self._parse_destatis_csv(text)
                    _LOGGER.debug("Destatis API returned %d", resp.status)
        except Exception:
            _LOGGER.debug("Destatis API not reachable")
        return None

    @staticmethod
    def _parse_destatis_csv(csv_text: str) -> float | None:
        """Parse Destatis CSV for the latest savings rate value."""
        lines = csv_text.strip().split("\n")
        # Look for the last data line with a numeric value
        for line in reversed(lines):
            parts = line.split(";")
            for part in reversed(parts):
                part = part.strip().replace(",", ".")
                try:
                    val = float(part)
                    if 0 < val < 100:  # Sanity check for percentage
                        return val
                except ValueError:
                    continue
        return None

    async def _persist(self) -> None:
        """Save benchmark data to .storage/."""
        await self._store.async_save(
            {
                "benchmarks": self._data,
                "last_check": (
                    self._last_check.isoformat()
                    if self._last_check
                    else None
                ),
            }
        )
