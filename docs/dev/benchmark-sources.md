# Benchmark sources

The household benchmark is a **bundled, versioned dataset**:
`custom_components/finance_dashboard/data/benchmarks_de.json`. `benchmark.py` reads only this
file - no network, no `.storage/` cache (CLAUDE.md: "no runtime benchmark fetch"). A new dataset
ships with a release.

## Allowlist

Only official statistics and recognised bodies. The machine-readable list is `allowed_domains`
in the dataset. `tests/test_benchmark_dataset.py` fails if a source URL is outside it.

| Body | Domains | Used for |
|---|---|---|
| Statistisches Bundesamt (Destatis) - LWR, EVS, Zensus, Mikrozensus / EU-SILC, VGR | destatis.de, zensus2022.de, regionalstatistik.de, statistikportal.de | consumption by category and household size, rent per m², savings rate, equivalised income |
| Statistische Landesämter | statistik-nord.de, statistik.bayern.de, statistik-bw.de, it.nrw and others (see JSON) | state-level values |
| BDEW (Strompreisanalyse, Gaspreisanalyse, Stromverbrauch im Haushalt) | bdew.de | electricity and gas prices, kWh by household size |
| Bundesnetzagentur (Monitoringbericht) | bundesnetzagentur.de | energy prices (not yet used) |
| BMAS / Bundesgesetzblatt | bmas.de, recht.bund.de | Regelbedarf (floor) |
| Deutsche Bundesbank | bundesbank.de | debt ratio (not yet used) |

Not allowed: comparison portals (Verivox, Check24), Statista, press articles, blogs - even when
they quote an allowlisted body, take the number from the body itself.

## Dataset 2026.10.1 - coverage

| Dimension | Status | Source, statistic, reference year |
|---|---|---|
| rent_per_sqm | DE + 7 states | Zensus 2022 (PM 45, 2024-06-25), mean, 2022. Destatis publishes only HH, BY, HE, BW, ST, TH, SN in the release text. HH confirmed by Statistik Nord |
| electricity_price | DE | BDEW Strompreisanalyse 10/2026, mean, 2026 YTD, 3,500 kWh |
| electricity_consumption | DE, 1/2/3/4+ persons | BDEW Stromverbrauch im Haushalt 2025 (05/2026), mean |
| heating_gas_price | DE, single/multi-family | BDEW Gaspreisanalyse 10/2026, mean, 2026 YTD |
| heating_district_heating_price, heating_oil_price, heating_heat_pump_price | null | not sourced yet |
| housing_energy, food, mobility, communication, consumption_total | DE, all/1/2/3/4/5+ persons | Destatis LWR 2024 by household size (Stand 2026-08-17), mean |
| insurance | null | the LWR consumption line excludes most premiums - misleading |
| debt_ratio | null | not sourced yet |
| savings_rate | DE | Destatis PM N059 (2025-10-28), sector ratio, 2024 |
| equivalised_income | DE | derived: Destatis PM 039 (2026-02-03) threshold / 0.6, median, income year 2024 |
| poverty_threshold | DE, 1 and 4 persons | Destatis PM 039, 60 % of median |
| regelbedarf | DE, RBS 1-6 | RBSFV 2026, BGBl. 2025 I Nr. 243, statutory |

No dimension has postcode or district values yet. Lookups fall back to state, then Germany.

## Value schema

Every entry in `dimensions.DIM.values[]` carries `level` (postcode/district/state/country),
`region` (`DE`, `DE-BY`, a postcode or an AGS district key), `household_size` (`all`, `1` to `4`,
`4+`, `5+`), `value`, `statistic` (one of `statistics`), `source` (an id in `sources[]`),
`reference_year`, `publication_year`, optionally `variant`, `basis`, `derived` + `derivation`.
A dimension without a sourced value keeps `values: []` and a `note` starting with
"Not sourced". Never invent or interpolate a number. An arithmetic derivation from a published
definition must set `derived: true` and explain itself in `derivation`.

## How to update

1. Check each source in `sources[]` for a newer edition (LWR yearly around August, BDEW price
   analyses several times a year, Regelbedarf each autumn for 1 January, Destatis savings rate
   with the national accounts, EU-SILC first results around February).
2. Take the number from the primary document (table or PDF of the body itself). Prefer median
   where published, else mean, and record which.
3. Edit the JSON: update `value`, `reference_year`, `publication_year`, and the source's `url`,
   `published`, `reference_period`. Add a new source id rather than reusing one for a different
   edition.
4. Bump `dataset_version` (`YYYY.MM.N`) and `generated`.
5. For state values add entries with `level: "state"` and the ISO code. For district values use
   `level: "district"` with the AGS key. Postcode values only from an allowlisted body.
6. Run `tests/test_benchmark_dataset.py` and update the coverage table above.
