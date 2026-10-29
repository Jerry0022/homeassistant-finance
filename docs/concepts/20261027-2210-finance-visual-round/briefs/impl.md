# Implementation spec — home-screen vertical slice ("Durchstich Startseite")

Source of truth: the concept page rounds 4–5 (`rounds/04.html`, `rounds/05.html`, design `r4home`) **plus the round-5 feedback below, which overrides the mock where they differ**. Product rules: `docs/dev/product-concept.md`, project hard rules in `CLAUDE.md` (cache vs live fetch, attended vs background, account identity via IBAN, plan vs actual sign conventions, privacy). No financial data in git. Mock numbers in the concept are invented — never copy them into code or tests as "real".

Scope decided by the user: **design system + home screen (Heute · Woche · Zyklus · Jahr) with the minimal backend it needs**. Out of scope: Schulden/Einkommen/Saldo check-up, Verträge detail, Statistik pages, Transaktionssicht, AI "Was das heißt" text (see open questions), virtual-pot coverage donut, Karteikarten/points game (keep the existing categorise flow; only the star entry point with a badge is in scope), Eilmeldungen beyond what existing repairs/events provide.

## Round-5 feedback (verbatim, typos fixed) — must be applied

- Design-System: „sehr gut".
- Heute · Ben: „Warum nicht die Wechsel-Buttons Ben und Haushalt ganz unten auf dem Screen? Und eher als Toggle! Die Info ‚alle Töpfe zusammen' ist unnötig. Das ‚im Plan' kann auch raus, das sieht man ja darunter direkt. Wobei die Zahl gern auch eingefärbt wie der Status ist. Bei ‚deine Töpfe' unten gehe ich davon aus, dass die Werte über den Gesamtzyklus aggregiert sind, sprich wenn ich gestern/letzte Woche/seit Einkommenszyklus weniger ausgegeben habe, aggregiert sich das im Topf. Da wäre die Info gut, wie viel es üblicherweise pro Tag sind, als Nebeninfo, aber groß der aktuelle Topf-Saldo weiterhin. Die Labels finde ich noch naja: Pills sind gut, ‚drüber' und ‚knapp' auch, ‚im Plan' finde ich ein doofes Wording. Überlege dir auch, wie ich Töpfe erstellen und verwalten kann (Desktop und Mobile; Mobile vor allem hinzufügen, Desktop groß verwalten). Da darf gern auch ein Plus her auf der ‚Deine Töpfe'-Karte, dezent irgendwo rechts oben. Das ‚heute frei' benötigt es nicht, dann lieber eine Visualisierung von Zahlen, die man noch ausgeben kann, einführen, woran ich das immer direkt merke: oh, das kann ich noch ausgeben."
- Heute · Haushalt: „Vielleicht ist Ben / Haushalt unten eher eine ovale Menü-Pill-Toggle und Heute bis Jahr eher das Wischen! Aber bitte ohne Hinweise etc. Man versteht das Heute-bis-Jahr-Menü schon jetzt und auch, dass man es wischen kann."
- Woche: „Klasse! Wobei ich in der Grafik gern dort auch noch eine dünne gestrichelte Linie habe, die anzeigt, wo es linear wäre, wenn ich 0 Euro mitgenommen hätte. Btw, habe ich so viel Minus mitgenommen, dass ich diese Woche eigentlich nix mehr habe, sollte die gestrichelte Linie ganz unten sein bei 0. ‚Saldo zum Soll' verstehe ich nicht, zu kompliziert. Bei ‚wird diese Woche noch abgebucht' gern den Hinweis darunter weglassen."
- Zyklus: „Die Info bitte hinter einem Info-Button verstecken, der die Karte oben umdreht; der Info-Button gern direkt hinter dem Zyklus-Datum oben. Das ‚ab Gehalt Anna' kann gern hinter dem Info-Button versteckt sein. ‚Knapp im Rahmen' und ‚19 € hinter der Soll-Linie' etc. finde ich gut, aber unten haben wir doch schon die grauen Kästen plus in der Grafik Infos. Das ist mir zu viel — überlege, was in der Grafik stehen sollte und was darunter, das reicht! ‚Fixkosten gedeckt' finde ich super! Das ‚Wusstest du schon' könnte auch unter der ersten Box kommen, vor ‚Als Nächstes'!"
- Jahr: „Sehr gut hier der Vertragstab, gern mehr Vertragsanalyse auch bei Jahr! Auch der Vergleich zum letzten Jahr, insbesondere auf Desktop dann inkl. Inflation vs Gehaltsveränderungen etc. vs Bevölkerung vs Preisindex/Kaufkraft…" → in this slice: year view with per-cycle status and a "vs. Vorjahr" comparison of own data; inflation/population comparison is out of scope (needs the bundled benchmark dataset, Phase 4e) — leave a clearly marked placeholder entry, no runtime fetch.
- Eilmeldungen-Panel: „Sehr gut auch mit den Vorschlägen! ‚Information' als letztes in dem Panel braucht es nicht, das ist klar!"
- Karteikarten: „Ja, sowas ist besser!!!" (coin stack) — out of scope for code in this slice.
- Desktop Zyklus: „Sehr gut, dabei gern auch neue Töpfe vorschlagen und es ermöglichen, die Vorschläge zu verwerfen. Die ‚Was das heißt'-Analyse dann von der KI oder wie?" → open question for the user; implement rule-based suggestions only.
- Desktop Woche: „Gut, wobei die Navigation bitte wie auf Mobile."

## Earlier decisions still binding (rounds 2–5)

- Person view shows only that person's own items; Haushalt view shows shared + persons. The view source is the logged-in HA user (mapped to a person); shared devices/cards use a configured `person:` option. No free switch to another person's view — the only toggle is Person ⇄ Haushalt.
- Accounts are aggregated under persons and Haushalt; a person can own several accounts (e.g. DKB + PayPal). Accounts break down only on desktop.
- Horizons: Heute · Woche · **Zyklus** (never "Monat") · Jahr. Heute = only today (no Soll-Linie, no Als Nächstes, no Rücklagen, no accounts, no "unkategorisiert" line — the star badge is enough). Als Nächstes / Wusstest du schon / Rücklagen are Zyklus (and Jahr) topics; Woche shows only "wird diese Woche noch abgebucht" (sum + top 3, pending bookings inline with a `vorgemerkt` label, no hint text below).
- Als Nächstes: top 3 + "mehr anzeigen"; pending (vorgemerkte) bookings inside the list with a label.
- Status colours (±10 % rule): spent ≤ linear-to-date → good; up to +10 % above → "knapp" (still ok, green family); above → "drüber" (deep orange). No red. Replace the "im Plan" wording with something better (e.g. "läuft", "passt", or the coloured amount alone) — the coloured number carries the status.
- Pots ("Töpfe"): big number = current pot balance aggregated over the whole cycle (unspent days carry forward inside the cycle); side info = typical per-day amount. Personal pots fed only from personal accounts; shared pots in Haushalt. Create (mobile: a subtle "+" top-right on the "Deine Töpfe" card) and manage (desktop: full management).
- Week: daily linear budget vs actual day bars; carry-over (+/−) from the previous week **only within the current cycle**; a thin dashed line for "linear with 0 € carried" (clamped at 0 when the carry-over is so negative that nothing is left).
- Cycle rule: a person's cycle runs from their earliest highest income to the next one. Haushalt: the highest income sets the cycle start, unless another person's highest income falls within the 7 days before it — then that earlier one is the start. Show the rule and "ab Gehalt X" only behind an info button next to the cycle date that flips the top card.
- Zyklus card: tank with Soll-Linie; decide what goes into the graphic vs the boxes below — no duplication. "Fixkosten gedeckt" stays. Order: top card → Wusstest du schon → Als Nächstes → Rücklagen.
- Navigation: Person ⇄ Haushalt as an oval pill toggle at the **bottom** of the screen; Heute … Jahr as the top segment control that can also be **swiped**; no hint texts. Desktop uses the same navigation as mobile, plus extra side content; desktop-only controls carry the purple marker and may sit inline in boxes that also exist on mobile.
- Freshness icon top-left (→ Datenstand page exists already in some form? reuse the bank-status endpoint), star with badge top-right (→ existing categorise flow), Eilmeldung pill top-centre (from existing repair issues / events; light style with status edge, never black). The Eilmeldungen panel has no trailing "Information" section.
- Design system (round 5 `r5-ds`): implement as CSS custom properties in `fd-shared-styles.js` (surfaces, text levels, accent #03a9f4 family, status good/knapp/drüber, person colours incl. Anna berry, desktop-only purple, type scale, radius, spacing, notification style, chips, buttons, tank component). Use HA theme variables where they exist (`--primary-color`, `--card-background-color`, …) and map the design tokens onto them so HA light/dark themes keep working.

## Backend contract (W1 core → W2 frontend)

New module(s) under `custom_components/finance_dashboard/` (names are a suggestion; follow the codebase's style):

1. `cycle.py` (or extend `month_cycle.py`, which exists but is unwired): pure functions
   - `person_cycle(incomes, today) -> (start, end)` — highest income detection with the existing ±5-day salary tolerance.
   - `household_cycle(person_incomes, today) -> (start, end, anchor_person)` — the 7-day rule above.
2. `pots.py`: pot model + store (Fernet-encrypted like other bank-derived data? pots are plan data, not bank data — store alongside the budget plan via `BudgetPlanStore` or a sibling store). Pot = `{id, name, owner: person|"shared", cycle_budget (plan sign: positive), category_keys[], kind: "spend"|"reserve"}`. Functions:
   - `pot_status(pot, bookings_in_cycle, cycle, today)` → `{balance, per_day_typical, spent, linear_to_date, status: good|knapp|over, carry_in_week}`; balance aggregates over the whole cycle (unspent carries forward).
   - `week_status(pots, bookings, cycle, today)` → daily budget, per-day actual (Mon–Sun), carry-over from previous week clamped to the cycle, `zero_carry_line` (clamped at 0), `upcoming` (sum + items incl. pending with `pending: true`).
3. Ownership aggregation: account → owner (person id or `shared`) from the existing household/person config; aggregate per person and Haushalt. Respect the privacy rule: another person's personal data appears only as totals; a person view never includes other persons.
4. HTTP view `GET /api/finance_dashboard/home?horizon=today|week|cycle|year&view=person|household` (HA auth required; cache reads only — never a live bank fetch). Response JSON:
   ```json
   {"view":"person","person":{"id":"…","name":"…"},"horizon":"week",
    "freshness":{"as_of":"ISO","status":"fresh|stale|error"},
    "alerts":[{"id":"…","severity":"info|warn","title":"…","actions":[…]}],
    "questions_open": 3,
    "cycle":{"start":"YYYY-MM-DD","end":"YYYY-MM-DD","anchor":"person name","rule":"…"},
    "status":"good|knapp|over","remaining": 123.45,
    "pots":[{"id":"…","name":"…","owner":"…","balance":…,"per_day":…,"status":"good|knapp|over","kind":"spend|reserve"}],
    "week":{…},"next":[{"date":"…","label":"…","amount":…,"pending":false}],
    "did_you_know": null|{"text":"…"},"reserves":[…],"fixed_costs_covered": true,
    "year":{"cycles":[{"start":"…","status":"…"}],"vs_last_year":{…}}}
   ```
   Fields not relevant to the horizon may be omitted. Amounts in plan sign (expense positive) via `actual_amount_to_plan_sign`.
5. Pot CRUD: `POST/PUT/DELETE /api/finance_dashboard/pots` (admin-only or person-own for personal pots — follow `test_admin_gating.py` patterns).
6. Demo mode (`demo.py`, `api/demo.py`) must serve the same `home` contract with invented data so the panel can be shown without a bank.
7. Tests (pytest, existing conftest/fakes): cycle rule incl. the 7-day edge cases, pot carry-over within the cycle and reset at cycle start, ±10 % status thresholds, week zero-carry clamp, privacy (person view excludes other persons; household shows others' personal data as totals only), the view returns cache data without calling the bank client.

## Frontend (W2)

- Vanilla Web Components, existing `fd-*` conventions, `fd-shared-styles.js` for tokens, `locales/de.json` + `en.json` for every string (German UI wording from the concept).
- New home component (e.g. `fd-home.js`) as the panel's first view, mobile-first, `@container` breakpoint for desktop (≥ 760 px) with the side column; same navigation on desktop.
- Components: top bar (freshness icon, Eilmeldung pill, star with badge), horizon segment control with swipe (pointer events, touch-friendly, keyboard arrows), bottom Person ⇄ Haushalt pill toggle, tank (with Soll-Linie for Woche/Zyklus only), pot list with coloured balance + per-day side info + "+" add (opens a small create sheet), week chart (day bars, linear line, thin dashed zero-carry line clamped at 0), cycle card with flip-to-info button, Wusstest du schon, Als Nächstes (top 3 + mehr anzeigen, vorgemerkt label), Rücklagen, Jahr view (per-cycle status squares, vs Vorjahr, contracts entry), desktop pot management (list, edit, delete, rule-based "neuer Topf"-suggestions with dismiss).
- Tooltips, keyboard, focus rings, touch targets ≥ 44 px, no native `title` tooltips, reduced-motion respected (ui-defaults R0–R8).
- Data via `fd-data-provider.js` → the new `home` endpoint; works in demo mode.

## Open questions to report back (do not decide silently)

- "Was das heißt"-analysis: AI-generated (opt-in, HA AI functions) or rule-based text? → implemented rule-based for now.
- Better wording than "im Plan" → pick one and name it in the report.
