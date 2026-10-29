# UI concept gap: live 0.20.2 against the decided concept

Status: spec for two frontend bundles, written 2026-10-29. Read-only audit, no code changed.

**Verdict:** the live panel is not the concept. Only one slice of the concept shipped: the
home screen (`fd-home`). It sits inside a pre-concept shell with three top tabs (Start · Übersicht ·
Haushalt). Two of those tabs are the old component tree (`fd-overview`, plus the sensor-driven
Household tree). The concept has no tabs. It has **one** screen: the horizon segment (Heute · Woche ·
Zyklus · Jahr) at the top, the Person ⇄ Haushalt pill toggle at the bottom, and everything else
behind icons and entries that open subpages. Even the home slice is incomplete: the person view is
empty, the toggle disappears in the household view, the segment has no date sub-labels, there is
no desktop analysis column, and there is no settings entry point.

## 0. Sources of truth

The decided visual concept is **not** under `docs/dev/` (`product-concept.md` says the decision
pages were not kept). It survives in git, in the session autosave commits:

| Ref | What | How to read it |
|---|---|---|
| **VR-impl** | `docs/concepts/20261027-2210-finance-visual-round/briefs/impl.md` (commit `bf2951b`): the binding implementation spec of the home slice, incl. round-5 feedback verbatim and "Earlier decisions still binding (rounds 2–5)" | `git show bf2951b:docs/concepts/20261027-2210-finance-visual-round/briefs/impl.md` |
| **VR-r2…r5** | Briefs `02.md`–`05.md` (user feedback per round, verbatim) and the mock rounds `rounds/02.html`–`05.html` (round 5 = final mocks `r5-ds`, `r5-s1`…`r5-s11`) | same commit, same folder |
| **VR-api** | `briefs/home-api-contract.md`: final `/home` contract | same commit |
| **VR-later** | `briefs/later.md`: later slices + the standing analysis principle | same commit |
| PC | `docs/dev/product-concept.md` | repo |
| HO | `docs/dev/visual-round-handoff.md` | repo |
| RM | `docs/dev/roadmap.md` § "Visual round — home slice done, next slices" | repo |
| HS | `docs/dev/contracts/household-summary.md` | repo |
| SW | `docs/dev/contracts/setup-wizard.md` + `custom_components/finance_dashboard/api/setup.py` docstring (plan_prefill, goals, points, ai endpoints already merged in this worktree) | repo |
| LA | `docs/concepts/20261028-2350-finance-live-audit/rounds/01.html` (yesterday's audit page, untracked) | worktree |

Recommendation (outside both bundles): restore the visual-round folder from `bf2951b` into
`docs/concepts/` so the next agent does not have to dig through autosave commits.

### Live evidence base

The live HA at `homeassistant.local:8123/finance-dashboard`, Finance **v0.20.2** (panel footer),
inspected read-only on 2026-10-29. Desktop: viewport 1568×777. Mobile: 375 px wide (same-origin
iframe in the signed-in Chrome; the built-in browser pane was not signed in, so I did not enter any
credentials). I made no clicks that change data, only clicks on the tabs, segments and view toggle.
API state from cache reads: `/home` (person + household), `/household_summary`, `/budget_plan`
(0 positions), `/setup` (current_step `done`, plan `skipped`, notifications `enabled: false`).

---

## 1. Concept target per surface

### 1.1 Navigation shell (mobile = desktop)

- **No top tab bar.** In round 3 the user rejected "ganz viele Seiten… Navigation 0 smart"
  (VR-r3 § feedback on round 2) and picked r3b "Zoom durch die Zeit": a single screen whose horizon
  zoom morphs the content (VR-r4 § feedback on round 3, favourite r3b).
- **Axis 1: horizon.** Segment control Heute · Woche · Zyklus · Jahr at the top. It can be swiped,
  shows no hint texts, and never reads "Monat" (VR-impl § Earlier decisions, "Navigation"; round-5
  feedback "Heute · Haushalt"). The round-5 mocks give every segment a sub-label: `Heute / Mi 28.10.`,
  `Woche / KW 44`, `Zyklus / noch 8 Tage` (or `15.10.–14.11.`), `Jahr / 2026` (VR-r5 `r5-s1`,
  `r5-s4`).
- **Axis 2: perspective.** Person ⇄ Haushalt as an **oval pill toggle at the bottom of the screen**
  (VR-impl round-5 feedback "Heute · Ben": "Wechsel-Buttons … ganz unten auf dem Screen … als
  Toggle"; "Heute · Haushalt": "ovale Menü-Pill-Toggle"). Mock content: an avatar initial plus short
  name plus a sub-label: `B Ben · deine Töpfe` / `⌂ Haushalt · gemeinsam` (VR-r5 `r5-s1`, `r5-s2`).
  The person comes from the logged-in HA user. There is no free switch to another person
  (VR-r3 § decision `r2-sicht-quelle`).
- **Desktop = the same navigation** plus a side column ("Desktop Woche: … die Navigation bitte wie
  auf Mobile", VR-impl round-5 feedback). Desktop-only controls carry the purple marker and may sit
  inline in boxes that also exist on mobile (VR-r5 brief § Desktop; VR-impl).
- **Everything else is behind an icon or entry and opens a subpage** without a classic submenu:
  freshness icon → Datenstand; star → Fragen (flash cards); Jahr → Verträge (entry), Vergleich;
  "Statistik behind a link/icon" (VR-later 2–3, RM).

### 1.2 Header (top bar) per page

- **Start:** freshness icon top-left showing status + time (`✓ 06:30`, desktop `✓ aktuell · 06:30`),
  Eilmeldung pill top-centre only when there is news (it collapses once seen: VR-r3 feedback d3),
  and the star with a badge and progress ring top-right (VR-r4 `r4-s1` brief, VR-r5 `r5-s1`,
  `r5-s10`). The mocks have **no "Finance" title text** in the bar.
- **Subpages** (Datenstand `r5-s9`, Fragen `r5-s7`, Verträge, Vergleich): the concept does not
  draw their headers explicitly. **Decision (mine):** one subpage header pattern for all of them:
  `[← back, 44 px] [Title] [optional page actions right]`, the same top position as the Start bar,
  and no tab row above it.
- **Settings entry point on desktop:** the concept does not place one. Round 2 relied on HA's own
  sidebar "Einstellungen" (VR-r2 d4 desktop mock), which is not a Finance settings entry. The user
  now explicitly misses it. **Decision (mine):** a gear icon button in the Start top bar, right of the
  star, on **all** widths (HO § Form factors: "every interaction needs a touch path"). It opens the
  Einstellungen subpage. On mobile the gear sits in the same row; the bar has room because the
  "Finance" title text goes away.

### 1.3 Start per horizon (VR-impl § Earlier decisions; VR-r5)

| Horizon | Person view | Household view |
|---|---|---|
| Heute | Coloured "noch frei" figure (colour carries status, no "im Plan" word), a visualisation of what can still be spent, "Deine Töpfe" with the cycle-aggregated balance big and Ø/day small, and a subtle "+" top-right on the card. No Soll-Linie, no Als Nächstes, no Wusstest du schon, no Rücklagen, no accounts, no "unkategorisiert" line. | Same, for the shared pots ("Gemeinsame Töpfe") + persons as totals |
| Woche | Verdict dominates the box; day bars against the linear line; carry-over ±, only within the cycle ("+21 € aus KW 43 mitgenommen"); a thin dashed zero-carry line clamped at 0; "wird diese Woche noch abgebucht" (sum + top 3, `vorgemerkt` inline, no hint text below) | same, shared |
| Zyklus | Tank with Soll-Linie; info button next to the cycle date flips the card (rule, "ab Gehalt X"); "Fixkosten gedeckt"; order: top card → Wusstest du schon → Als Nächstes (top 3 + mehr anzeigen) → Rücklagen | same; Wusstest du schon is a household topic |
| Jahr | Per-cycle status squares, vs. Vorjahr, Rücklagen progress, Verträge as an entry ("gern mehr Vertragsanalyse"), benchmark placeholder | same |

Desktop side column per horizon (VR-r5 brief § 3, `r5-s10`, `r5-s11`): **Zyklus → Optimierung**
(per pot: plan, deviation, last 6 cycles, similar households, "Was das heißt", concrete next steps
with purple buttons), **Woche → Budget anpassen** (shift budget between pots, accept carry-over),
**Jahr → Optimierung**, plus **"Konten · nur Desktop"**: the per-person/Haushalt account breakdown
(another person's accounts as a total only: "2 Konten · nur die Summe, Details sieht nur Anna").
Pot management with dismissible "neuer Topf" suggestions also lives in the side column (VR-impl
round-5 feedback "Desktop Zyklus").

### 1.4 Person view without own pots: already solved in the concept

The user is right ("das haben wir schon längst gelöst"). The concept decides it in three places:

1. **VR-r3 § annotation answers (round-2 feedback, d1 "Annas Sicht"):** "warum soll das noch
   überhaupt interessieren was gemeinsamer spielraum ist wenn man doch schon zu der person gewechselt
   ist… gemeinsam kann ja jeder sehen" → *person view shows only that person's own things; shared
   lives in Haushalt.* Restated as binding in VR-impl: "Person view shows only that person's own
   items; Haushalt view shows shared + persons."
2. **VR-r4 `r4-s1` mock:** the person's tank is **"dein Spielraum heute … noch frei bis …"** with
   the Soll-Linie, i.e. the person's own free money. Pots are a separate, additional item
   ("Persönliche Töpfe (aus eigenem Konto)" in the round-4 placement map, and "Personal pots fed
   only from personal accounts" in VR-impl).
3. **VR-impl:** pots are created through a subtle "+" (mobile) and full desktop management with
   rule-based suggestions, so they are opt-in.

**Therefore:** with no own pot, the person view still shows *their own* Spielraum (own income − own
spend in their cycle, Soll-Linie, own next debits) and an empty "Deine Töpfe" card with "+" and the
history-based suggestions. Yesterday's audit recommendation (LA `d-glance`: "show your share of the
shared pots") **contradicts** the concept and is withdrawn.

Data for this without new backend: `GET household_summary?cycle=current&view=person` returns the
viewer's own `owners[]` row (`income`, `expenses`, `surplus`, `fixed`, `variable`). `/home?view=person`
already returns `next`/`next_all` and `cycle`. When a plan exists, the person's variable plan
budget replaces income as the tank size. Exposing that as a `/home` field is a core follow-up, not
part of these bundles.

### 1.5 Household content (formerly the Haushalt tab)

PC § Rhythms "Cycle: plan vs. actual, settle-up"; RM slices "guided desktop check-up Einnahmen ·
Ausgaben · Überschuss", "Inside Ausgaben: fixed vs. variable … split Haushalt vs. personal",
"Complex cycle analysis desktop-only (mobile: a simple summary)"; VR-r4 feedback "Mobile kann alles
was Desktop kann außer die komplexe Monatsanalyse (einfache Zusammenfassung ok)". The concept puts
this content **into Start · Zyklus (Haushalt) and the desktop side column**, never into its own tab.
HS says the household numbers come from `/household_summary`; the live audit decided "Auf die
Haushalt-API umstellen" (LA `d-tab`, recommended), meaning no sensor attributes.

### 1.6 Overview content (formerly the Übersicht tab)

There is no Übersicht in the concept. Its parts map as follows: accounts → desktop "Konten · nur
Desktop" (r5-s10); bank status, import log, Neu importieren / Aktualisieren, validity check →
**Datenstand** (VR-r4 `r4-s7`: "per bank last fetch + budget left, import log …, Monats-Validität");
transaction list → "Transaktionssicht … desktop only" (VR-later 5, RM: one of the last slices);
persons & accounts assignment, setup wizard entry → Einstellungen.

### 1.7 Subpages

Datenstand (r5-s9), Fragen as flash cards with a coin-stack counter, 7 cards per point (r5-s7/s8),
Verträge (timeline, notice deadlines; desktop-leaning, reachable on mobile), Vergleich (statistic,
source and year on every figure, Regelbedarf floor; HO), Einrichtung (a guided wizard that resumes
until it is completed once; PC § Setup wizard: persons, accounts → owner, postcode/state, payday,
plan prefilled from history, notifications and digest, AI with provider and budget, savings goals,
points system).

---

## 2. Live state per surface (evidence)

| # | Surface | Live (desktop 1568 / mobile 375) | Rendered by |
|---|---|---|---|
| L1 | Shell | Top tab row **Start · Übersicht · Haushalt** above everything, on both widths. `.fd` max-width 1200 px, padding 24 px (on a phone: 24 px gutters plus the HA menu button row) | `finance-dashboard-panel.js:336-340` (tabs), `:282-286` (.fd), `:169-182` (_selectTab) |
| L2 | Start top bar | `✓` + "Daten aktuell" (desktop only, **no time**) · centred text **"Finance"** · star with ring + badge. **No gear.** The freshness icon opens an inline panel, not the Datenstand page | `fd-home.js:402-418` (_topHtml), `:428` (inline fresh panel) |
| L3 | Segment | Plain labels Heute/Woche/Zyklus/Jahr, **no sub-labels** (date, KW, days left, year) | `fd-home.js:370-374` |
| L4 | Toggle | Pill at the end of the content (`position: sticky; bottom: 12px`), so on short pages it floats mid-screen (mobile screenshot: y≈657 of 760 under an empty card; desktop under the side column). Label is the **full name** "Jeremy Treder", no avatar, no sub-label. **In the household view the toggle disappears entirely**, so there is no way back to the person view without reloading | `fd-home.js:144-147`, `:383-389`: `hidden = !!d && !hasPerson`, and `/home?view=household` returns `person: null` (verified live) |
| L5 | Start · Person · Heute/Woche/Zyklus | Only a card **"Noch keine Töpfe – Lege Töpfe an … + Neuer Topf"**. The API delivers `remaining`, `status`, 3× `next`, `cycle` for the person, but nothing is shown | `fd-home.js:443` (`_body`: any horizon ≠ year with budget ≤ 0 → `_setupCard`), `:455-466` |
| L6 | Start · Person · Jahr | "Dein Jahr in Zyklen" shows **Jul–Sep + striped Oct** only; "Vergleich zum Vorjahr – Noch keine Vorjahresdaten"; entries Verträge, Vergleich mit dem Durchschnitt; Rücklagen empty | `fd-home.js:643-666` |
| L7 | Start · Haushalt · Heute | "13 € noch übrig · passt", meter, tiles "Heute ausgegeben 0,00 €" / "reicht für 1 Tage · 13,00 € pro Tag" (**"1 Tage"** grammar bug), "Gemeinsame Töpfe: Food Ø 13,00 €/Tag 13 €". **Persons totals missing** (`persons: []`) | `fd-home.js:495-515` |
| L8 | Start · Haushalt · Woche | 52 € "Diese Woche noch frei · passt", line chart; the dashed zero-carry line is not distinguishable; day values are "·"; "Wird diese Woche noch abgebucht" 1 row (Bäckerei … `vorgemerkt`) | `fd-home.js:545+` |
| L9 | Start · Haushalt · Zyklus | "Zyklus 29. Okt. – 27. Nov. ⓘ · Tag 1 von 30 · Gut dabei · 13 € vor der Soll-Linie", tank, tiles Budget/Ausgaben/Pro Tag übrig; Als Nächstes lists **"Treder vorgemerkt 640,62 €"** (an own-name transfer, fixed server-side in wave 1); Rücklagen empty. **No "Fixkosten gedeckt"** (null without a plan), no Wusstest du schon | `fd-home.js:583-640` |
| L10 | Desktop side column | Every horizon shows the same: "Töpfe verwalten ◆ Nur am Desktop" + "Vorschläge für neue Töpfe" (Wohnen, Kredite, Lebensmittel/Nebenkosten). **No Optimierung, no Budget anpassen, no Konten column**. The main column is ~60 % width with a large empty area under the person empty-state | `fd-home.js:685+` (_sideHtml), `:167-174` |
| L11 | Übersicht tab | Action bar **"Noch keine Daten — klicke „Aktualisieren“"** (false: data exists, and the button it names is not in this bar) + Demo + Neu importieren + Bank hinzufügen; Personen & Haushalt balance cards (PayPal shows `PayPal 1 · ****  –`); Bankverbindungen with **a second** Neu importieren + Aktualisieren + Aktualität & Prüfung + "Bank hinzufügen / verwalten" (a second add-bank); **Transaktionen** with all ~650 bookings inline; then Einrichtung → "Einrichtung öffnen"; then **Personen & Konten (the only settings UI), below the whole transaction list** | `fd-header.js` + `locales/de.json:21` (`header.ts.empty`), `fd-overview.js:272-281`, `fd-settings.js` |
| L12 | Haushalt tab | "Willkommen beim Finance Dashboard – Bank hinzufügen / Demo starten" (orange buttons, off the design system). The cause is the stale sensor crash, but the structural problem remains: the tree is `fd-household-cycle` (API) + `fd-household-section`, `fd-category-section`, `fd-cost-distribution`, `fd-recurring-list` (all **sensor/`/summary` via fd-data-provider**) + `fd-budget-plan` (API), gated on sensor `accountCount` | `finance-dashboard-panel.js:580-608` (_ensureComponents), `:664-705` (onboarding on `accountCount === 0`), `fd-household-section.js:50`, `fd-category-section.js:32-35`, `fd-cost-distribution.js:42-43` |
| L13 | Settings (Personen & Konten) | Person switches are solid pills with no knob/state affordance; the name field is free text but there is **no separate short name/nickname** (backend `nicknames` exists in `api/setup.py:109-153`, `/home` still returns `person.name = id`, `home.py:527`). Owner chips per account: 4 chips incl. "Ecxon Alfonso Duran Ruiz" → **3 rows of chips per account at 375 px** | `fd-settings.js:289-299`, chip rows |
| L14 | Refresh paths | `_maybeAutoRefresh` posts a bank fetch on panel open (refresh-on-open was retired server-side in wave 1); bare `POST /refresh` without a trigger body in two places | `finance-dashboard-panel.js:123, 216-236, 513`; `fd-data-provider.js:239` |

### Overflow and clipping measurements (375 px, `scrollWidth > clientWidth`)

| id | Where | Measured | Cause |
|---|---|---|---|
| O1 | `fd-overview` → `fd-settings > div.root` | 320 in 317 | settings card wider than the column |
| O2 | `fd-settings` person row | 305 in 287; `button.sw` 65 in 46, `span.hit` 66 in 48 | switch drawn wider than its hit box, pushes the row |
| O3 | `fd-overview > div.tx` (every row) | 300 in 289 | unbroken remittance tokens (`1054053076427/PP.9623.PP/.…`, `2026-10-29T05:09 Debitk. 0 2099-12 …`) and the meta line "29.10.2026 · Jeremy Treder und Ecxon Alfonso Duran Ruiz" |
| O4 | `finance-dashboard-panel > div.fd` / `fd-overview` | 340 in 317 | sum of O1–O3; the page itself does not scroll sideways (`docSW 365 < 375`), the content is clipped |
| O5 | Owner chips (settings) | wrap to 3 lines per account | full person names as chip labels |
| O6 | Start toggle | fits for "Jeremy Treder"; for the second user the label "Ecxon Alfonso Duran Ruiz" is ≈ 190 px in a `min-width:96px` button and the pill grows to ≈ 320 px | full name instead of nickname |
| O7 | Als Nächstes rows (mobile) | "Baeckerei Geisen GmbH Vallendar DE" wraps over 2 lines, the `vorgemerkt` tag drops to line 2, and the amount column has no `flex:none` guarantee | `fd-home.js:538-541` |
| O8 | Small targets | Overview `select` and the tag chips are < 40 px high | 44 px rule (ui-defaults) |

---

## 3. Gap list

Severity: **P0** breaks navigation or misrepresents data · **P1** concept surface missing or wrong ·
**P2** concept detail · **P3** polish. Bundle: A or B (section 4).

| id | Surface | M/D | Concept says | Live shows | Fix | Sev | Bundle |
|---|---|---|---|---|---|---|---|
| G1 | Shell | both | One screen, horizon segment top, Person⇄Haushalt pill bottom, no tabs (1.1) | Tab row Start/Übersicht/Haushalt (L1) | Delete `#tabs`, `_selectTab`, `#viewOverview`, `#viewHousehold`, `#components`, `#overlay` from `finance-dashboard-panel.js`. The shell hosts `fd-home` + a **subpage router** (`fd-navigate {target}` → full-screen view with the subpage header). Targets: `freshness`, `questions`, `contracts`, `benchmark`, `plan`, `settings`, `setup`, `transactions`. Browser back closes a subpage (`history.pushState` with `#sub=…`) | P0 | A |
| G2 | Toggle | both | Pill always reachable at the screen bottom (1.1) | Vanishes in the household view; floats mid-screen (L4) | `fd-home.js:383`: base visibility on "the user maps to a person" (remember `person` from the last person response, or the `/settings` viewer mapping), not on `d.person`. `.nav` → `position: fixed; bottom: max(12px, env(safe-area-inset-bottom))`, centred inside the panel's content box (offset by the HA sidebar on desktop), main gets `padding-bottom: 88px` | P0 | A |
| G3 | Person view | both | Own Spielraum + own next debits; pots optional; no shared items (1.4) | Empty "Noch keine Töpfe" on 3 horizons (L5) | Replace the `_body` short-circuit (`fd-home.js:443`). Person view without pots renders: the tank "dein Spielraum" from `household_summary?view=person` own owner row (income − expenses, Soll-Linie over the person's cycle), Als Nächstes (own, Zyklus only), Woche from own spend, "Deine Töpfe" empty card with "+" and up to 2 suggestions inline (purple on desktop). The setup card only when `setup` says persons/accounts are unassigned | P0 | A |
| G4 | Settings entry | both (user: desktop) | Touch-reachable settings (1.2 decision) | None; settings buried under ~650 bookings in Übersicht (L11) | Gear `ib` button in `_topHtml` after the star, `aria-label="Einstellungen"`, tooltip label tier → `fd-navigate {target:"settings"}`. Hotkey `,` (mnemonic-free, desktop hint on hover) is optional | P0 | A (button + route), B (page content) |
| G5 | Household tab | both | Content folded into Start · Zyklus (Haushalt) + desktop column; API only (1.5) | Sensor-driven legacy tree, currently a false onboarding (L12) | Retire the tab (G1). Start · Zyklus · Haushalt gets: **mobile** a one-line "Einnahmen · Ausgaben · Überschuss" strip under the tank (from `/household_summary`, `savings_rate:null` → "–", `income_pending` → "Gehalt erwartet am …"); **desktop** side column "Zyklus im Detail ◆": owner split mine/yours/ours (restricted rows = totals only), fixed vs. variable, previous-cycle delta, one rule-based sentence per block, plus plan-vs-actual per position (`/plan_vs_actual`) when a plan exists. Port the logic of `fd-household-cycle.js` into a new `fd-cycle-detail.js`; do not mount the old element | P1 | A |
| G6 | Overview tab | both | No Übersicht; parts move (1.6) | Facts page with duplicated actions (L11) | Retire `fd-overview` as a view. Persons & account cards → desktop side column "Konten ◆ nur Desktop" on every horizon (person view: own accounts; household: shared + persons, another person's accounts as a total + "Details sieht nur X"). Bank connections + Neu importieren + Aktualisieren + validity → `fd-freshness` (Datenstand). Transactions → `fd-transactions` subpage, desktop-only link in Datenstand. Persons & Konten + Einrichtung → Einstellungen | P1 | A (B for the settings part) |
| G7 | Top bar header | both | `✓ 06:30` left, pill centre only with news, star right, no title (1.2) | "Daten aktuell" without time, "Finance" title, inline fresh panel (L2) | Freshness label = `as_of` time (`HH:MM`; "gestern 06:30" when older than today; desktop prefix "aktuell ·"); a click opens the **Datenstand subpage** (the inline popover goes). Remove the `.ttl` "Finance" text. Mobile row: `ha-menu-button` (narrow only) · fresh · [pill] · star · gear, all 44 px | P1 | A |
| G8 | Segment | both | Sub-labels per horizon (1.1) | Plain labels (L3) | Two-line segment buttons: label + `small` sub-label from `/home` `cycle` and today: `Mi 29.10.`, `KW 44`, `noch N Tage` (desktop: `dd.mm.–dd.mm.`), `2026`. Truncate sub-labels with ellipsis at 375 px; keep min-height 44 | P2 | A |
| G9 | Toggle label | both | Avatar initial + short name + sub-label (1.1) | Full name (L4, O6) | `B` avatar circle (person colour) + `display_name` (nickname, fallback = first name token) + `small` "deine Töpfe" / "gemeinsam". Requires `/home` to return `person.display_name` (core follow-up; until then take the first token of `name`) | P2 | A |
| G10 | Desktop analysis | D | Zyklus → Optimierung, Woche → Budget anpassen, Jahr → Optimierung (1.3) | Only pot management on every horizon (L10) | Side column per horizon: Zyklus = "Optimierung ◆" (per pot: plan, deviation, trend; rule-based "Was das heißt"; buttons "Regel anlegen" / "Plan anpassen" / "Zum Vertrag", all purple) above Konten and pot management; Woche = "Budget anpassen ◆" (move budget between pots via `PUT /pots`, carry-over accept); Jahr = Optimierung light + Verträge summary. Empty data → say what is missing ("Ohne Plan keine Abweichung – Plan anlegen") instead of hiding | P1 | A |
| G11 | Heute | both | No "im Plan" word; coloured number; visualise what can still be spent; pots: big balance, Ø/day small (1.3) | "passt" chip + "noch übrig"; "reicht für 1 Tage" (L7) | Drop the chip on Heute (colour carries status); fix the plural (`home.today.days` one/other); persons totals (`persons[]`) under the household pots as in the mock | P2 | A |
| G12 | Woche | both | Thin dashed zero-carry line; carry-over line "+x € aus KW nn mitgenommen" (1.3) | Dashed line not visible; no carry-over sentence (L8) | Draw `zero_carry_line` as a 1 px dashed stroke in `--fd-t3`; add the carry-over line under the verdict; replace the "·" day labels with amounts only for past days | P2 | A |
| G13 | Zyklus | both | Fixkosten gedeckt; Wusstest du schon before Als Nächstes (1.3) | Neither (null without a plan) (L9) | With `fixed_costs_covered: null` show "Fixkosten: Plan fehlt → Plan anlegen" (link to the plan subpage) instead of hiding; render `did_you_know` in the concept order | P2 | A |
| G14 | Jahr | both | Calendar year Jan–Dec with status squares (VR-r3 "Kalenderjahr ist schon gut") | Jul–Sep + Oct only (L6) | Render 12 slots Jan–Dec; months without data = `fut`/empty with a tooltip "keine Daten"; plus a "Budgetplan" entry next to Verträge / Vergleich | P2 | A |
| G15 | Subpage header | both | One consistent subpage header (1.2) | Verträge/Vergleich open inline in Jahr with a "← Zurück · X" text button; Datenstand has its own back; Fragen is a layer | Shared `fd-subpage-header` pattern (back 44 px, title, actions) used by every subpage; Verträge/Vergleich become shell subpages, not inline in `#main` | P2 | A |
| G16 | Refresh / import | both | Live calls only via explicit user action; Neu importieren = attended bank fetch; Aktualisieren = `POST /reprocess` (CLAUDE.md hard rules, ARCHITECTURE-FRONTEND) | Auto refresh on open; bare `POST /refresh` (L14) | Delete `_maybeAutoRefresh` and its call (`finance-dashboard-panel.js:123, 216-236`). The only bank fetch is the Datenstand "Neu importieren" button → `POST finance_dashboard/refresh` with body `{"trigger":"user_import"}` (`finance-dashboard-panel.js:513`). Remove the bare POST at `fd-data-provider.js:239` (the provider never fetches). "Aktualisieren" → `POST /reprocess` only | P0 | A |
| G17 | Onboarding | both | Not configured → setup / connect bank | Decided from sensor `accountCount` (false "Noch keine Bank verbunden") | Onboarding decision from `/home` (404 not configured) and `/refresh_status.account_count`, never from sensors; design-system buttons (no orange) | P1 | A |
| G18 | Legacy action bar | both | — | "Noch keine Daten — klicke Aktualisieren", duplicate Demo/Import/Add-bank (L11) | Retire the `fd-header` bar; keep toasts in a minimal shell toast host (`fd-toast` inside the panel). Demo toggle → Einstellungen › Erweitert (B); add bank → Datenstand + Einstellungen | P1 | A |
| G19 | Overflow tx rows | both | — | O3 | In the new `fd-transactions`: `overflow-wrap:anywhere` on remittance, `min-width:0` on the text column, amount `flex:none`, meta line ellipsis; account owner shown as nickname | P2 | A |
| G20 | Overflow Als Nächstes | M | — | O7 | Row grid `1fr auto`; label `overflow-wrap:anywhere`, max 2 lines (`-webkit-line-clamp:2`); `vorgemerkt` tag inline after the date, not after the label | P3 | A |
| G21 | Overflow settings | M | — | O1, O2, O5 | `fd-settings`: switch = 52×32 track inside a 44 px hit box, `flex:none`; owner choice = a segmented chip row with **avatar initial + nickname** (full name in the tooltip), horizontal scroll-snap fallback when it does not fit; card `min-width:0` | P2 | B |
| G22 | Nicknames | both | Short names ("Ben", "Anna") throughout (mocks) | Full legal names everywhere | Settings › Personen: a "Kurzname" field per person → `PUT /setup {nicknames:[{person, display_name}]}`; wizard step persons asks for it too | P1 | B |
| G23 | Wizard: plan | both | "plan prefilled from history (detected series)" (PC § Setup wizard; LA `d-plan`) | Plan step only explains import, skipped live | Plan step: list `GET /setup/plan_prefill` positions (name, amount, owner, interval) with confirm/strike per row → `POST /setup/plan_prefill`; xlsx upload / Sheets link stay as alternatives | P1 | B |
| G24 | Wizard: goals | both | Savings goals (PC § Setup wizard, § Goals) | Missing | New step "Sparziele": amount by date / category cap / savings rate → `POST /setup/goals`, list + delete | P1 | B |
| G25 | Wizard: points | both | Connect the points system (PC § Points) | Missing | New step "Punkte": pick a `counter.*` / `input_number.*` entity (HA entity picker style, own styling) → `PUT /setup/points`; explain "30 Antworten = 1 Punkt" | P1 | B |
| G26 | Wizard: AI | both | Opt-in, HA AI first, else own key Grok/Claude/ChatGPT; 100 calls/month cap (PC § AI) | Opt-in toggle only | AI step: provider choice (HA AI task/conversation agent first; then xAI Grok, Anthropic, OpenAI with key field), monthly budget (calls, default 100, max 100) → `GET/PUT /setup/ai` | P1 | B |
| G27 | Notifications | both | Exceptions + digest on (PC § Jobs 2, SW defaults `enabled: true`) | `enabled: false` live; wizard shows "aus" | Wizard + settings default to on and show the stored value; changing it needs the user's click (no silent write) | P2 | B |
| G28 | Settings page | both | Settings as its own subpage (1.2 decision) | Section inside Übersicht | `fd-settings` renders as a full page with sections: Personen & Kurznamen, Konten → Besitzer, Zahltag, Region, Benachrichtigungen, KI, Punkte, Sparziele, Banken (link to the integration page), Erweitert (Demo, Einrichtung erneut starten). Desktop: two columns (section nav left), mobile: a stacked list with anchors | P1 | B |

### Legacy components: verdict per file (checked against concept and live usage)

| Component | Live use | Concept verdict | Action |
|---|---|---|---|
| `fd-header.js` | Overview action bar + toast host (`finance-dashboard-panel.js:341`) | No equivalent; actions belong in Datenstand | **Retire** (G18); toast host → shell |
| `finance-status-chip.js` | Kit only, no panel use | Superseded by the freshness icon | Keep as a Lovelace card for now, not in the panel; no work |
| `fd-overview.js` | Übersicht tab | No Übersicht in the concept | **Retire**; split into Konten column, Datenstand, `fd-transactions`, settings (G6) |
| `fd-household-section.js` + `fd-person-card.js` | Haushalt tab, sensor/`/summary` | Persons = totals in the household home + Konten column | **Retire** |
| `fd-stats-row.js` + `fd-stat-card.js` | Not mounted (only loaded by the kit) | Calendar-month KPIs; concept uses cycles | **Retire** (remove from the kit list) |
| `fd-category-section.js` + `fd-donut-chart.js` | Haushalt tab, sensor | Categories are drill-downs, "Statistik behind an icon" (RM); the pot coverage donut is a different, later component | **Retire** both |
| `fd-cost-distribution.js` | Haushalt tab, sensor | Owner split comes from `/household_summary` | **Retire** |
| `fd-recurring-list.js` | Haushalt tab, sensor | Superseded by `fd-contracts` (Verträge) | **Retire** |
| `fd-household-cycle.js` | Haushalt tab, API | Content is right (HS), placement wrong | **Replace** with `fd-cycle-detail.js` (G5); delete after porting |
| `fd-budget-plan.js` | Haushalt tab, API | Plan is the front door (PC § Purpose) | **Keep**, mounted as subpage "Budgetplan" (entry in Jahr, and links from "Fixkosten: Plan fehlt") |
| `fd-data-provider.js` | Entity bridge for the legacy tree | Sensors are aggregates only; the panel reads the API | **Shrink**: no `POST /refresh`, no onboarding source; remove from the panel if nothing else needs it after G5/G6 |
| `finance-dashboard-card.js` | Lovelace card (balance) | HO "Glance card": status, free to spend, next debits, freshness, pending apart; `person:` card option (VR-r3) | **Replace** later with a glance card on `/home?horizon=today` (A, last, optional) |
| `fd-budget-config.js`, `fd-categorize.js` | Lovelace cards; `fd-categorize` via the desktop link in Fragen | Not contradicted | Keep; `fd-budget-config` reads its options from the select entities. `fd-transactions-log.js` retired (its data source fd-data-provider is gone; `fd-transactions` replaces it) |

---

## 4. Bundles (non-overlapping file ownership)

### Bundle A: shell, header, navigation, Start, household content, Overview retirement, overflow, refresh paths

Gaps: G1–G3, G4 (button + route), G5–G20.

Owns (create/modify/delete):
- `frontend/finance-dashboard-panel.js` (shell, subpage router, toast host, onboarding, refresh paths)
- `frontend/fd-home.js` (top bar incl. gear, segment, toggle, all horizons, desktop side column)
- `frontend/fd-freshness.js` (Datenstand gains bank connections, Neu importieren, Aktualisieren, link to transactions)
- `frontend/fd-data-provider.js` (remove the refresh POST, shrink)
- `frontend/fd-contracts.js`, `frontend/fd-benchmark.js`, `frontend/fd-budget-plan.js`, `frontend/fd-questions.js` (only: adopt the subpage header; no content redesign)
- new `frontend/fd-cycle-detail.js`, `frontend/fd-transactions.js` (extracted from `fd-overview.js`), optional `frontend/fd-subpage-header.js`
- delete: `fd-overview.js`, `fd-header.js`, `fd-household-section.js`, `fd-person-card.js`, `fd-household-cycle.js`, `fd-stats-row.js`, `fd-stat-card.js`, `fd-category-section.js`, `fd-donut-chart.js`, `fd-cost-distribution.js`, `fd-recurring-list.js`
- `frontend/finance-dashboard-kit.js` (load list), `frontend/fd-shared-styles.js` (tokens: nav, subpage header, avatar)
- `frontend/locales/de.json`, `frontend/locales/en.json` (sole owner)
- optional, last: `frontend/finance-dashboard-card.js` (glance card)
- docs: `docs/ARCHITECTURE-FRONTEND.md`

Data sources A must use: `/home`, `/household_summary` (incl. `view=person`), `/plan_vs_actual`,
`/budget_plan`, `/balances`, `/bank_status`, `/freshness`, `/refresh_status`, `/transactions`,
`/pots`. Sensor attributes must not be used.

### Bundle B: setup wizard + settings

Gaps: G4 (page content), G21–G28.

Owns: `frontend/fd-setup.js`, `frontend/fd-settings.js`. Nothing else.
- Strings go in the components' own fallback dictionaries (the existing pattern in `fd-overview.js`
  `ov.*`). Bundle B does **not** edit `locales/*.json`; A or a later pass moves them.
- Uses tokens from `fd-shared-styles.js` read-only.
- Endpoints: `/setup` (incl. `nicknames`, `region`, `notifications`), `/setup/plan_prefill`,
  `/setup/goals`, `/setup/points`, `/setup/ai`, `/setup/ai/test`, `/setup/payday_suggestions`, `/setup/pot_suggestions`,
  `/assignments`, `/demo/toggle`.

### Interface contract between A and B (fixed now)

- A opens settings with `fd-navigate {target:"settings", section?: "persons"|"accounts"|"payday"|"region"|"notifications"|"ai"|"points"|"goals"|"banks"|"advanced"}`
  and mounts `<fd-settings mode="page" section="…">` inside its subpage frame (A draws the subpage header
  "Einstellungen"; B draws only the body).
- A opens the wizard with `fd-navigate {target:"setup"}` and mounts `<fd-setup>` as today.
- B emits the existing `fd-assignments-saved` / `fd-settings-saved` / toast events; A's shell
  reloads `/home` on them and shows toasts.
- B emits `fd-navigate {target:"settings-closed"}` or relies on A's back button; B never navigates the HA router.

## 5. Decisions recorded (no user available)

1. Settings entry = gear in the Start top bar on all widths (the concept left this open).
2. Subpage header pattern shared by every subpage (the concept left this open).
3. Person view without pots follows round 2/4 ("only own things", "dein Spielraum"); LA `d-glance`
   "share of shared pots" is rejected as contrary to the concept.
4. Household cycle detail: simple strip on mobile, full analysis desktop-only (VR-r4 feedback).
5. Transactions: desktop-only subpage from Datenstand (VR-later 5); no mobile entry.
6. `finance-status-chip`, `fd-categorize` stay untouched; `fd-budget-config` reads the select entities' own options; `fd-transactions-log` is retired.

## 6. Follow-ups outside both bundles (core)

- `/home` returns `person.display_name` (nickname) and a person-view Spielraum field
  (`person_budget {budget, spent, remaining, source: plan|history}`) so the frontend no longer derives
  it from `household_summary`.
- `/home?view=household` reports whether the viewer maps to a person (e.g. `viewer_person`), so the
  toggle does not depend on the person response (G2 works without it, but this is cleaner).
- Restore the visual-round concept folder from `bf2951b` into `docs/concepts/`.
