# Roadmap

Current version: see `manifest.json`. Branch `feat/rethink-foundation` completed the foundation.

## Done: Phases 1-2 (earlier)

Enable Banking client, credential manager, categorizer, N-person split (pooled_equal / equal /
proportional / custom), recurring detection, cost-position ledger, spreadsheet import, transfer
choreography with zero-sum invariant, settlement, plan-vs-actual, once-daily scheduled refresh,
budget Number entities, split Select, 4 automation events, benchmark with source attribution.

## Done: rethink-foundation

- [x] HACS packaging (add-on and payload sync removed)
- [x] Branding (icons, brand assets)
- [x] Bank connect as config subentries (`my.home-assistant.io` redirect)
- [x] Per-bank fetch budget (attended uncapped and debounced, 6h backoff)
- [x] Encrypted two-layer storage (raw snapshots + ledger)
- [x] Devices per bank/account, long-term statistics, diagnostics, repairs
- [x] Frontend kit, admin panel + auto-loaded cards, facts Overview tab, Household tab behind
  `show_household`

## Next (gated on explicit user approval, do not start unprompted)

The intentions are defined in `product-concept.md` (decided 2026-10-26). Phase 4 builds them in
this order, each step usable on its own:

- [ ] **Phase 4 - Intentions** (scope per `product-concept.md`):
  - [ ] 4a Household core: account owners (A / B / shared, N persons), ownership chain with saved
    rules, salary cycle wired (`month_cycle.py`), calendar-week steering, free-to-spend figure.
  - [ ] 4b Data truth: normalisation, PayPal-first enrichment, all six link types, any-interval
    series with tolerances, corrections with reach, review inbox, restatement hint in the log.
  - [ ] 4c Categorisation: learned merchant memory, opt-in AI tail (HA AI functions first, then
    Grok / Claude / ChatGPT key, 100 calls/month cap).
  - [ ] 4d Contracts and reserves: price mechanism per plan position, contract model with notice
    reminders, savings-account flag, virtual pots with coverage check, goals.
  - [ ] 4e Benchmarks: bundled versioned dataset from a source allowlist, region by postcode,
    replaces the runtime crawl in `benchmark.py`.
  - [ ] 4f Engagement: exception notifications + weekly digest, points event, setup wizard, README
    and web handbook (`handbook-outline.md`).
- [ ] **Phase 5 - Visuals**: presentation of all of the above incl. mobile; input in
  `visual-round-handoff.md`.

## Open backlog

- [ ] Income recognition with +-5d window; bonus detection; month cycle wiring; logical-month
  assignment; category-level split override (see `household-model.md`)
- [ ] Cost-position editing UI (API exists, card is read-only)
- [ ] Household-labour compensation (the workbook's own open question)
- [ ] CSV export polish, `set_budget_limit` automation trigger
