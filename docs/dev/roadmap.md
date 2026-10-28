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

## Visual round — home slice done, next slices (decided 2026-10-28)

The home screen (Heute · Woche · Zyklus · Jahr, pots, cycle rule, design system) shipped as the
first vertical slice. The household wants the remaining surfaces concepted the same way, one slice
at a time, each element refined in depth:

- [ ] Guided desktop check-up "Einnahmen · Ausgaben · Überschuss" (find the final wording), a rare,
  on-demand "review / improve my finances" flow; each part with its own statistics and improvement
  hints in place, visualising where action is needed and where not. Includes a debt view.
- [ ] Inside Ausgaben: fixed vs. variable costs; fixed costs split Haushalt vs. personal per person.
  Household fixed costs visible to all; a person's personal fixed and variable costs in detail only to
  that person (confirm whether others see a per-person total).
- [ ] Contracts as their own entry (payments chart, notice deadlines, more contract analysis in the
  year view) — desktop-leaning, reachable on mobile without a classic submenu.
- [ ] Statistics behind a link/icon; the household home only shows a "Wusstest du schon?" top info.
- [ ] Complex cycle analysis desktop-only (mobile: a simple summary); year comparison incl. inflation,
  salary change, population and purchasing power (needs the bundled benchmark dataset, Phase 4e).
- [ ] Transaction view as one of the last slices, desktop only, across all household accounts: who
  started with how much since cycle / month / week start, and a flow visualisation (Sankey-like) of
  where money went and came back.
- [ ] Questions as flash cards with a thematic counter (7 cards per point) and a celebration.
- [ ] Decide: "Was das heißt" analysis text AI-generated (opt-in) or rule-based (rule-based today).

Standing principle for every analysis view: never a one-dimensional "here is a statistic". Combine
dimensions (trend × plan × benchmark × owner × fixed/variable), say what it means, show where action
is needed and where not, and offer the concrete next step.

## Open backlog

- [ ] Income recognition with +-5d window; bonus detection; month cycle wiring; logical-month
  assignment; category-level split override (see `household-model.md`)
- [ ] Cost-position editing UI (API exists, card is read-only)
- [ ] Household-labour compensation (the workbook's own open question)
- [ ] CSV export polish, `set_budget_limit` automation trigger
