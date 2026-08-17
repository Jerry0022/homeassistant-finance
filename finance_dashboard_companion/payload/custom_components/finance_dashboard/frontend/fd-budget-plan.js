/**
 * fd-budget-plan — the migrated household spreadsheet.
 *
 * Renders the four things the workbook was used for:
 *   1. income breakdown per person (deposit − insurance ± tax = net)
 *   2. the cost ledger, grouped by owner, with buffers and expiry dates
 *   3. the split result: each person's pocket money
 *   4. the monthly transfer choreography, with the pass-through zero check
 *   5. our ratios against German averages
 *
 * Loads its own data from the plan endpoints rather than the transaction
 * provider: the plan exists independently of whether a bank is linked, so the
 * household can budget before any live data arrives.
 *
 * Properties:
 *   hass  {object} — Home Assistant connection
 *   month {number} — optional month override
 *   year  {number} — optional year override
 */

class FdBudgetPlan extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._plan = null;
    this._transfer = null;
    this._benchmark = null;
    this._error = null;
    this._loading = false;
    this._loaded = false;
  }

  set hass(v) {
    const first = this._hass === null;
    this._hass = v;
    if (first) this._load();
  }

  get hass() {
    return this._hass;
  }

  set month(v) { this._month = v; this._load(); }
  set year(v) { this._year = v; this._load(); }

  connectedCallback() {
    this._render();
  }

  /** Reload all plan data. Safe to call repeatedly; overlapping calls are dropped. */
  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._error = null;
    this._render();

    const qs = [];
    if (this._month) qs.push(`month=${this._month}`);
    if (this._year) qs.push(`year=${this._year}`);
    const suffix = qs.length ? `?${qs.join("&")}` : "";

    try {
      // Fetched in parallel — none depends on another.
      const [plan, transfer, benchmark] = await Promise.all([
        this._hass.callApi("GET", `finance_dashboard/budget_plan${suffix}`),
        this._hass
          .callApi("GET", `finance_dashboard/transfer_plan${suffix}`)
          .catch(() => null),
        this._hass
          .callApi("GET", `finance_dashboard/benchmark${suffix}`)
          .catch(() => null),
      ]);
      this._plan = plan;
      this._transfer = transfer;
      this._benchmark = benchmark;
      this._loaded = true;
    } catch (err) {
      this._error = (err && err.message) || "Haushaltsplan konnte nicht geladen werden";
    } finally {
      this._loading = false;
      this._render();
    }
  }

  /** Public: re-fetch after an import or an edit. */
  refresh() {
    this._loaded = false;
    this._load();
  }

  _render() {
    const { SHARED_CSS, escHtml, MEMBER_COLORS } = window._fd || {};
    if (!SHARED_CSS) return;

    const eur = (v) =>
      new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(v || 0);
    const pct = (v) => `${(v || 0).toFixed(1)} %`;

    const LOCAL_CSS = `
:host { display: block; margin-bottom: 20px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 7px 10px; text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; white-space: normal; }
thead th {
  font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--tx2); font-weight: 600; border-bottom: 1px solid var(--bd);
}
tbody tr + tr td { border-top: 1px solid var(--bd); }
.scroll { overflow-x: auto; padding: 4px 8px 12px; }
.neg { color: var(--bad, #d64545); }
.pos { color: var(--good, #2e9e5b); }
.muted { color: var(--tx2); }
.sub td { font-weight: 700; background: var(--bg2, rgba(127,127,127,.07)); }
.tag {
  display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: var(--bg2, rgba(127,127,127,.14)); color: var(--tx2); margin-left: 6px;
}
.badge {
  display: inline-flex; align-items: center; gap: 5px; font-size: 11px;
  padding: 2px 9px; border-radius: 10px; font-weight: 600;
}
.badge.ok { background: rgba(46,158,91,.16); color: var(--good, #2e9e5b); }
.badge.warn { background: rgba(214,69,69,.16); color: var(--bad, #d64545); }
.pockets {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px; padding: 14px 18px;
}
.pocket { border: 1px solid var(--bd); border-radius: 10px; padding: 12px 14px; }
.pocket .who { font-size: 12px; color: var(--tx2); display: flex; align-items: center; gap: 6px; }
.pocket .dot { width: 8px; height: 8px; border-radius: 3px; }
.pocket .amt { font-size: 21px; font-weight: 700; margin-top: 4px; }
.pocket .brk { font-size: 11px; color: var(--tx2); margin-top: 5px; line-height: 1.5; }
.empty { padding: 20px 18px; color: var(--tx2); font-size: 13px; line-height: 1.6; }
.empty code {
  display: block; margin-top: 10px; padding: 10px 12px; border-radius: 8px;
  background: var(--bg2, rgba(127,127,127,.1)); font-size: 12px;
  white-space: pre-wrap; word-break: break-word; color: var(--tx);
}
.bm { padding: 6px 18px 14px; }
.bm-row {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 10px; padding: 7px 0; font-size: 13px;
}
.bm-row + .bm-row { border-top: 1px solid var(--bd); }
.bm-src { font-size: 10px; color: var(--tx2); }
`;

    if (this._error) {
      this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="card">
  <div class="card-h">Haushaltsplan</div>
  <div class="empty">${escHtml(this._error)}</div>
</div>`;
      return;
    }

    if (!this._loaded) {
      this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="card">
  <div class="card-h">Haushaltsplan</div>
  <div class="empty">Wird geladen …</div>
</div>`;
      return;
    }

    const plan = this._plan || {};
    if (plan.is_empty) {
      this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="card">
  <div class="card-h">Haushaltsplan</div>
  <div class="empty">
    Noch kein Plan vorhanden. Die Haushaltskalkulation kann direkt aus der
    Excel-Datei übernommen werden — Einkommen, alle Kostenpositionen mit
    Zuordnung, Puffer und Laufzeiten.
    <code>Entwicklerwerkzeuge → Aktionen → Finance: Import Household Spreadsheet
path: /config/Kalkulation Haushalt.xlsx</code>
    Die Datei muss im Config-Verzeichnis liegen oder ihr Ordner in
    <em>allowlist_external_dirs</em> eingetragen sein.
  </div>
</div>`;
      return;
    }

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
${this._renderPockets(plan, eur, escHtml, MEMBER_COLORS)}
${this._renderIncome(plan, eur, pct, escHtml)}
${this._renderLedger(plan, eur, escHtml)}
${this._renderTransfer(eur, escHtml)}
${this._renderBenchmark(escHtml)}`;
  }

  _renderPockets(plan, eur, escHtml, colors) {
    const split = plan.split || {};
    const members = split.members || [];
    if (!members.length) return "";

    const palette = colors || ["#4b8bf5"];
    const cards = members
      .map(
        (m, i) => `
<div class="pocket">
  <div class="who">
    <span class="dot" style="background:${palette[i % palette.length]}"></span>
    ${escHtml(m.person)}
  </div>
  <div class="amt ${m.spielgeld < 0 ? "neg" : ""}">${eur(m.spielgeld)}</div>
  <div class="brk">
    Anteil am Rest ${eur(m.remainder_share)}<br>
    − eigene Fixkosten ${eur(m.individual_costs)}
  </div>
</div>`
      )
      .join("");

    return `
<div class="card">
  <div class="card-h">Taschengeld
    <span style="font-weight:400;font-size:12px;color:var(--tx2)">
      ${eur(split.spielgeld_total)} gesamt · Modell ${escHtml(split.model || "")}
    </span>
  </div>
  <div class="pockets">${cards}</div>
</div>`;
  }

  _renderIncome(plan, eur, pct, escHtml) {
    const rows = (plan.income || [])
      .map(
        (e) => `
<tr>
  <td>${escHtml(e.person)}</td>
  <td>${eur(e.deposit)}</td>
  <td class="neg">${eur(e.insurance_mandatory)}</td>
  <td>${eur(e.tax_adjustment)}</td>
  <td class="${e.net < 0 ? "neg" : ""}"><strong>${eur(e.net)}</strong></td>
  <td class="muted">${pct(e.share)}</td>
</tr>`
      )
      .join("");

    return `
<div class="card">
  <div class="card-h">Einkommen
    <span style="font-weight:400;font-size:12px;color:var(--tx2)">
      ${eur(plan.income_net_total)} netto gesamt
    </span>
  </div>
  <div class="scroll">
    <table>
      <thead><tr>
        <th>Person</th><th>Eingang</th><th>Privat-KV</th>
        <th>Steuerausgleich</th><th>Netto</th><th>Anteil</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
</div>`;
  }

  _renderLedger(plan, eur, escHtml) {
    const positions = plan.positions || [];
    if (!positions.length) return "";

    const costs = plan.costs || {};
    const groups = new Map();
    for (const p of positions) {
      if (!groups.has(p.owner)) groups.set(p.owner, []);
      groups.get(p.owner).push(p);
    }

    const label = (owner) => (owner === "__shared__" ? "Gemeinsam" : owner);
    const total = (owner) =>
      owner === "__shared__" ? costs.shared : (costs.individual || {})[owner];

    const sections = [...groups.entries()]
      .sort((a, b) => (a[0] === "__shared__" ? -1 : b[0] === "__shared__" ? 1 : 0))
      .map(([owner, items]) => {
        const rows = items
          .map((p) => {
            const tags = [];
            if (p.kind === "buffer") {
              tags.push(
                `<span class="tag">Puffer ${p.buffer_units || "?"} × ${eur(
                  p.buffer_unit_price
                )}</span>`
              );
            }
            if (p.valid_until) tags.push(`<span class="tag">bis ${escHtml(p.valid_until)}</span>`);
            if (!p.is_active) tags.push(`<span class="tag">inaktiv</span>`);
            const cls = p.effective_amount < 0 ? "pos" : "";
            return `
<tr>
  <td>${escHtml(p.name)}${tags.join("")}</td>
  <td class="muted">${escHtml(p.category || "")}</td>
  <td class="${cls}">${eur(p.effective_amount)}</td>
</tr>`;
          })
          .join("");

        return `
<div class="card">
  <div class="card-h">Kosten — ${escHtml(label(owner))}
    <span style="font-weight:400;font-size:12px;color:var(--tx2)">${eur(total(owner))}</span>
  </div>
  <div class="scroll">
    <table>
      <thead><tr><th>Position</th><th>Kategorie</th><th>Betrag</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
</div>`;
      })
      .join("");

    return sections;
  }

  _renderTransfer(eur, escHtml) {
    const tp = this._transfer;
    if (!tp || !tp.accounts || !tp.accounts.length) return "";

    const accounts = tp.accounts;
    const head = accounts
      .map((a) => `<th>${escHtml(a.label)}${a.role === "pass_through" ? '<span class="tag">Durchlauf</span>' : ""}</th>`)
      .join("");

    const rows = (tp.rows || [])
      .map((r) => {
        const cells = accounts
          .map((a) => {
            const v = r.amounts[a.id];
            if (v === undefined) return `<td class="muted">–</td>`;
            return `<td class="${v < 0 ? "neg" : v > 0 ? "pos" : "muted"}">${eur(v)}</td>`;
          })
          .join("");
        return `<tr class="${r.kind === "subtotal" ? "sub" : ""}">
  <td>${escHtml(r.label)}</td>${cells}
</tr>`;
      })
      .join("");

    const unplaced = tp.unplaced || [];
    const imbalances = Object.values(tp.imbalances || {});
    let badge;
    if (tp.balanced) {
      badge = `<span class="badge ok">Durchlaufkonto geht auf 0 auf</span>`;
    } else if (unplaced.length) {
      // An unplaced amount is worse than an imbalance: the money has no account
      // at all, so the plan is incomplete rather than merely off.
      badge = `<span class="badge warn">Nicht zuordenbar: ${unplaced
        .map((u) => eur(u.amount))
        .join(", ")}</span>`;
    } else {
      badge = `<span class="badge warn">Plan geht nicht auf: ${imbalances
        .map((v) => eur(v))
        .join(", ")}</span>`;
    }

    const unplacedNote = unplaced.length
      ? `<div class="empty" style="padding-top:0">${unplaced
          .map((u) => escHtml(u.detail || u.reason))
          .join("<br>")}</div>`
      : "";

    const settle = Object.entries(tp.settlements || {})
      .filter(([, s]) => Math.abs(s.settlement_delta) > 0.5)
      .map(
        ([person, s]) =>
          `${escHtml(person)}: ${s.settlement_delta > 0 ? "streckt vor" : "wird getragen"} ${eur(
            Math.abs(s.settlement_delta)
          )}`
      )
      .join(" · ");

    return `
<div class="card">
  <div class="card-h">Monatliche Umbuchungen ${badge}</div>
  <div class="scroll">
    <table>
      <thead><tr><th>Schritt</th>${head}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
  ${unplacedNote}
  ${settle ? `<div class="empty" style="padding-top:0">${settle}</div>` : ""}
</div>`;
  }

  _renderBenchmark(escHtml) {
    const bm = this._benchmark;
    const items = (bm && bm.comparisons) || [];
    if (!items.length) return "";

    const rows = items
      .map(
        (c) => `
<div class="bm-row">
  <div>
    ${escHtml(c.label)}
    <div class="bm-src">${escHtml(c.source || "")}${
          c.survey_year ? ` · ${c.survey_year}` : ""
        }</div>
  </div>
  <div class="${c.better ? "pos" : "neg"}">
    ${(c.user_value || 0).toFixed(c.unit === "%" ? 1 : 2)}${
          c.unit === "%" ? " %" : ` ${escHtml(c.unit || "")}`
        }
    <span class="muted">(Ø ${(c.benchmark_value || 0).toFixed(
      c.unit === "%" ? 1 : 2
    )})</span>
  </div>
</div>`
      )
      .join("");

    return `
<div class="card">
  <div class="card-h">Vergleich Deutschland</div>
  <div class="bm">${rows}</div>
</div>`;
  }
}

customElements.define("fd-budget-plan", FdBudgetPlan);
