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

- [ ] **Phase 4 - Intentions**: model user intentions/use cases; replace the hard-wired 2026
  spreadsheet model with composable building blocks; ask-and-learn categorization (the system asks
  once, remembers the answer; drag and drop learning).
- [ ] **Phase 5 - Visuals**: charts and visual design (6-month trend, spending trends).

## Open backlog

- [ ] Income recognition with +-5d window; bonus detection; month cycle wiring; logical-month
  assignment; category-level split override (see `household-model.md`)
- [ ] Cost-position editing UI (API exists, card is read-only)
- [ ] Household-labour compensation (the workbook's own open question)
- [ ] Benchmark auto-crawl beyond the Destatis savings rate
- [ ] CSV export polish, `set_budget_limit` automation trigger
