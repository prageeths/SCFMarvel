// SCF.AI dashboard logic — single-page application backed by /api endpoints.
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const fmtUsd = (v) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const n = Number(v);
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
};
const fmtPct = (v) => (v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(2)}%`);
const fmtTs = (s) => {
  if (!s) return "";
  const d = new Date(s);
  return d.toLocaleString();
};

// ---------- tabs ----------
function setupTabs() {
  $$(".nav-link").forEach((link) => {
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      const tab = link.dataset.tab;
      $$(".nav-link").forEach((l) => l.classList.remove("active"));
      link.classList.add("active");
      $$(".tab-panel").forEach((p) => p.classList.remove("active"));
      $(`#${tab}`).classList.add("active");
      if (tab === "agents") loadEvents();
      if (tab === "programs") loadPrograms();
      if (tab === "companies") loadCompanies();
      if (tab === "dashboard") loadDashboard();
      if (tab === "transactions") loadTransactions();
    });
  });
}

// ---------- meta ----------
async function loadMeta() {
  const r = await fetch("/api/meta").then((r) => r.json());
  $("#base-rate-value").textContent = r.base_rate_pct;
  const cs = $("#currency-select");
  cs.innerHTML = r.currencies.map((c) => `<option value="${c}">${c}</option>`).join("");
}

// ---------- dashboard ----------
async function loadDashboard() {
  const data = await fetch("/api/summary").then((r) => r.json());
  const grid = $("#stat-grid");
  grid.innerHTML = `
    <div class="stat"><div class="stat-label">Companies</div><div class="stat-value">${data.totals.companies.toLocaleString()}</div><div class="stat-sub">in roster</div></div>
    <div class="stat"><div class="stat-label">Programs</div><div class="stat-value">${data.totals.programs.toLocaleString()}</div><div class="stat-sub">active financing relationships</div></div>
    <div class="stat"><div class="stat-label">Invoices</div><div class="stat-value">${data.totals.invoices.toLocaleString()}</div><div class="stat-sub">all-time</div></div>
    <div class="stat"><div class="stat-label">Agent Events</div><div class="stat-value">${data.totals.agent_events.toLocaleString()}</div><div class="stat-sub">decisions logged</div></div>
    <div class="stat"><div class="stat-label">Base Rate</div><div class="stat-value">${(data.base_rate*100).toFixed(2)}%</div><div class="stat-sub">today's quote</div></div>
  `;

  // Recent decisions
  const feed = $("#recent-decisions");
  feed.innerHTML = data.recent_decisions
    .map((d) => renderEvent({ ...d, severity: "DECISION" }))
    .join("") || `<div class="muted">No decisions yet.</div>`;

  // Status table
  const sTbl = $("#status-table");
  const statusRows = Object.entries(data.by_status)
    .sort((a,b) => b[1].count - a[1].count)
    .map(([s, v]) => `<tr><td><span class="badge ${s}">${s}</span></td><td>${v.count.toLocaleString()}</td><td>${fmtUsd(v.amount_usd)}</td></tr>`)
    .join("");
  sTbl.innerHTML = `<thead><tr><th>Status</th><th>Count</th><th>Amount (USD)</th></tr></thead><tbody>${statusRows}</tbody>`;

  // Product table
  const pTbl = $("#product-table");
  const productRows = Object.entries(data.by_product)
    .map(([p, v]) => `<tr><td>${p.replaceAll("_"," ")}</td><td>${v.count.toLocaleString()}</td><td>${fmtUsd(v.amount_usd)}</td></tr>`)
    .join("");
  pTbl.innerHTML = `<thead><tr><th>Product</th><th>Count</th><th>Amount (USD)</th></tr></thead><tbody>${productRows}</tbody>`;
}

// ---------- events ----------
function renderEvent(e) {
  const sev = e.severity || "INFO";
  const tagCls = `agent-tag ${e.agent}`;
  return `
    <div class="event severity-${sev}">
      <span class="${tagCls}">${e.agent}</span>
      <div class="body">
        <div class="head">
          <span>${e.action}</span>
          <span>·</span>
          <span>${fmtTs(e.timestamp)}</span>
          ${e.invoice_id ? `<span>· invoice #${e.invoice_id}</span>` : ""}
          ${e.company_id ? `<span>· company #${e.company_id}</span>` : ""}
          ${e.program_id ? `<span>· program #${e.program_id}</span>` : ""}
        </div>
        <div class="msg">${e.message}</div>
      </div>
    </div>
  `;
}

async function loadEvents() {
  const agent = $("#filter-agent").value;
  const severity = $("#filter-severity").value;
  const params = new URLSearchParams();
  if (agent) params.set("agent", agent);
  if (severity) params.set("severity", severity);
  params.set("limit", "200");
  const data = await fetch("/api/events?" + params.toString()).then((r) => r.json());
  $("#event-list").innerHTML = data.items.map(renderEvent).join("") || `<div class="muted">No events.</div>`;
}

// ---------- programs ----------
async function loadPrograms() {
  const data = await fetch("/api/programs?limit=100").then((r) => r.json());
  const tbody = $("#programs-table tbody");
  tbody.innerHTML = data.items.map((p) => `
    <tr data-id="${p.id}">
      <td>#${p.id}</td>
      <td>${p.name}</td>
      <td><span class="badge">${p.product.replaceAll("_"," ")}</span></td>
      <td>${p.buyer.name}</td>
      <td>${p.seller.name}</td>
      <td>${fmtUsd(p.credit_limit_usd)}</td>
      <td>${fmtUsd(p.utilised_usd)}</td>
      <td><span class="badge ${p.status}">${p.status}</span></td>
      <td><button class="ghost explain-btn" data-id="${p.id}">Explain</button></td>
    </tr>
  `).join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", (ev) => {
      if (ev.target.classList.contains("explain-btn")) return;
      const id = tr.dataset.id;
      const program = data.items.find((x) => x.id == id);
      if (program) {
        document.querySelector('[data-tab="companies"]').click();
        loadCompanyDetail(program.buyer.id);
      }
    });
  });
  tbody.querySelectorAll(".explain-btn").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const id = btn.dataset.id;
      const card = $("#programs-facility-card");
      const body = $("#programs-facility-body");
      card.hidden = false;
      body.innerHTML = `<div class="muted">Loading explanation...</div>`;
      const data = await fetch(`/api/programs/${id}/facility`).then((r) => r.json());
      $("#programs-facility-title").textContent = `Facility Limit Explanation — ${data.program.name}`;
      body.innerHTML = renderFacility(data);
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderFacility(data) {
  const t = data.totals;
  const fxRows = data.open_invoices_by_currency
    .sort((a, b) => b.amount_usd - a.amount_usd)
    .map((r) => `
      <tr>
        <td><span class="badge">${r.currency}</span></td>
        <td>${r.count}</td>
        <td>${r.amount_native.toLocaleString()} ${r.currency}</td>
        <td>${r.fx_to_usd}</td>
        <td>${fmtUsd(r.amount_usd)}</td>
      </tr>
    `).join("") || `<tr><td colspan="5" class="muted">No live invoices.</td></tr>`;

  const buyerBreakdown = Object.entries(data.buyer_hierarchy_breakdown)
    .map(([k, v]) => `<tr><td>${k}</td><td>${fmtUsd(v)}</td></tr>`).join("");
  const sellerBreakdown = Object.entries(data.seller_hierarchy_breakdown)
    .map(([k, v]) => `<tr><td>${k}</td><td>${fmtUsd(v)}</td></tr>`).join("");

  const stepsHtml = data.explanation.map((s) => `
    <div class="step">
      <div class="step-num">${s.step}</div>
      <div>
        <div class="step-title">${s.title}</div>
        <div class="step-detail">${s.detail.replaceAll("**", "")}</div>
      </div>
    </div>
  `).join("");

  return `
    <div class="kv">
      <div class="k">Program</div><div>#${data.program.id} · ${data.program.name}</div>
      <div class="k">Product</div><div><span class="badge">${data.program.product}</span></div>
      <div class="k">Buyer</div><div>${data.program.buyer.name}</div>
      <div class="k">Seller</div><div>${data.program.seller.name}</div>
      <div class="k">Bilateral limit</div><div>${fmtUsd(t.program_limit_usd)}</div>
      <div class="k">Utilised</div><div>${fmtUsd(t.program_utilised_usd)}</div>
      <div class="k">Program headroom</div><div>${fmtUsd(t.program_headroom_usd)}</div>
      <div class="k">Buyer subtree headroom</div><div>${fmtUsd(t.buyer_subtree_headroom_usd)}</div>
      <div class="k">Seller subtree headroom</div><div>${fmtUsd(t.seller_subtree_headroom_usd)}</div>
      <div class="k">Binding constraint</div>
      <div><span class="badge REVIEW">${t.binding_constraint}</span> at ${fmtUsd(t.binding_headroom_usd)}</div>
    </div>

    <div class="section-title">Live Invoices Aggregated by Currency</div>
    <table class="data-table">
      <thead><tr><th>Currency</th><th>Count</th><th>Native amount</th><th>FX → USD</th><th>USD</th></tr></thead>
      <tbody>${fxRows}</tbody>
      <tfoot><tr><td colspan="4"><strong>Total open exposure</strong></td><td><strong>${fmtUsd(t.open_amount_usd)}</strong></td></tr></tfoot>
    </table>

    <div class="section-title">Step-by-step Reasoning</div>
    <div class="steps">${stepsHtml}</div>

    <div class="grid-2">
      <div>
        <div class="section-title">Buyer Hierarchical Breakdown</div>
        <table class="data-table">
          <thead><tr><th>Limit (ancestor : product)</th><th>Headroom</th></tr></thead>
          <tbody>${buyerBreakdown || `<tr><td colspan="2" class="muted">—</td></tr>`}</tbody>
        </table>
      </div>
      <div>
        <div class="section-title">Seller Hierarchical Breakdown</div>
        <table class="data-table">
          <thead><tr><th>Limit (ancestor : product)</th><th>Headroom</th></tr></thead>
          <tbody>${sellerBreakdown || `<tr><td colspan="2" class="muted">—</td></tr>`}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------- transactions ----------
async function loadTransactions() {
  const data = await fetch("/api/transactions/summary").then((r) => r.json());
  const t = data.totals;
  $("#tx-stat-grid").innerHTML = `
    <div class="stat"><div class="stat-label">Invoices</div><div class="stat-value">${t.invoice_count.toLocaleString()}</div><div class="stat-sub">all-time</div></div>
    <div class="stat"><div class="stat-label">Total Volume</div><div class="stat-value">${fmtUsd(t.amount_usd)}</div><div class="stat-sub">USD-equivalent</div></div>
    <div class="stat"><div class="stat-label">Funded</div><div class="stat-value">${fmtUsd(t.funded_usd)}</div><div class="stat-sub">net of fees</div></div>
    <div class="stat"><div class="stat-label">Fees Earned</div><div class="stat-value">${fmtUsd(t.fee_usd)}</div><div class="stat-sub">platform revenue</div></div>
    <div class="stat"><div class="stat-label">Base Rate</div><div class="stat-value">${(data.base_rate*100).toFixed(2)}%</div><div class="stat-sub">today's quote</div></div>
  `;

  const sRows = Object.entries(data.by_status)
    .sort((a,b) => b[1].count - a[1].count)
    .map(([s, v]) => `<tr><td><span class="badge ${s}">${s}</span></td><td>${v.count.toLocaleString()}</td><td>${fmtUsd(v.amount_usd)}</td><td>${fmtUsd(v.fee_usd)}</td></tr>`)
    .join("");
  $("#tx-status-table").innerHTML = `<thead><tr><th>Status</th><th>Count</th><th>Amount</th><th>Fees</th></tr></thead><tbody>${sRows}</tbody>`;

  const pRows = Object.entries(data.by_product)
    .map(([p, v]) => `<tr><td>${p.replaceAll("_"," ")}</td><td>${v.count.toLocaleString()}</td><td>${fmtUsd(v.amount_usd)}</td><td>${fmtUsd(v.fee_usd)}</td></tr>`)
    .join("");
  $("#tx-product-table").innerHTML = `<thead><tr><th>Product</th><th>Count</th><th>Amount (USD)</th><th>Fees (USD)</th></tr></thead><tbody>${pRows}</tbody>`;

  const cRows = Object.entries(data.by_currency)
    .sort((a,b) => b[1].count - a[1].count)
    .map(([c, v]) => `<tr><td><span class="badge">${c}</span></td><td>${v.count.toLocaleString()}</td><td>${v.amount_native.toLocaleString()} ${c}</td></tr>`)
    .join("");
  $("#tx-currency-table").innerHTML = `<thead><tr><th>Currency</th><th>Count</th><th>Native amount</th></tr></thead><tbody>${cRows}</tbody>`;

  const topRows = data.top_programs.map((p) => `
    <tr data-id="${p.program_id}">
      <td>#${p.program_id} · ${p.name}</td>
      <td><span class="badge">${p.product.replaceAll("_"," ")}</span></td>
      <td>${p.buyer.name}</td>
      <td>${p.seller.name}</td>
      <td>${p.invoice_count.toLocaleString()}</td>
      <td>${fmtUsd(p.amount_usd)}</td>
      <td><button class="ghost tx-explain-btn" data-id="${p.program_id}">Explain</button></td>
    </tr>
  `).join("");
  $("#tx-top-programs-table tbody").innerHTML = topRows;

  $$("#tx-top-programs-table .tx-explain-btn").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const id = btn.dataset.id;
      const card = $("#facility-card");
      const body = $("#facility-explanation");
      card.hidden = false;
      body.innerHTML = `<div class="muted">Loading explanation...</div>`;
      const fdata = await fetch(`/api/programs/${id}/facility`).then((r) => r.json());
      $("#facility-card-title").textContent = `Facility Limit Explanation — ${fdata.program.name}`;
      body.innerHTML = renderFacility(fdata);
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  // recent invoices
  const recRows = data.recent_invoices.map((inv) => `
    <tr>
      <td>#${inv.id}</td>
      <td>${inv.invoice_number}</td>
      <td>${inv.seller.name}</td>
      <td>${inv.buyer.name}</td>
      <td>${inv.product.replaceAll("_"," ")}</td>
      <td>${inv.amount.toLocaleString()} ${inv.currency}</td>
      <td>${fmtUsd(inv.amount_usd)}</td>
      <td><span class="badge ${inv.status}">${inv.status}</span></td>
    </tr>
  `).join("");
  $("#tx-recent-table tbody").innerHTML = recRows;
}

// ---------- companies ----------
let companyCache = [];
async function loadCompanies() {
  const q = $("#company-search").value;
  const role = $("#company-role").value;
  const params = new URLSearchParams();
  if (role) params.set("role", role);
  params.set("limit", "200");
  const data = await fetch("/api/companies?" + params.toString()).then((r) => r.json());
  let items = data.items;
  if (q) items = items.filter((c) => c.name.toLowerCase().includes(q.toLowerCase()));
  companyCache = items;
  const tbody = $("#companies-table tbody");
  tbody.innerHTML = items.map((c) => `
    <tr data-id="${c.id}">
      <td>${c.name}</td>
      <td><span class="badge">${c.role}</span></td>
      <td>${c.industry ?? ""}</td>
      <td>${c.country ?? ""}</td>
    </tr>
  `).join("");
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => loadCompanyDetail(tr.dataset.id));
  });
}

async function loadCompanyDetail(id) {
  const c = await fetch(`/api/companies/${id}`).then((r) => r.json());
  const card = $("#company-detail-card");
  const rp = c.risk_profile;
  const limits = c.credit_limits.map((cl) => `
    <tr>
      <td>${cl.product}</td>
      <td>${fmtUsd(cl.limit_usd)}</td>
      <td>${fmtUsd(cl.utilised_usd)}</td>
      <td>${fmtUsd(cl.headroom_usd)}</td>
    </tr>
  `).join("") || `<tr><td colspan="4" class="muted">No limits set.</td></tr>`;

  const programs = c.programs.map((p) => `
    <tr>
      <td>#${p.id}</td>
      <td>${p.name}</td>
      <td><span class="badge">${p.product}</span></td>
      <td>${fmtUsd(p.credit_limit_usd)}</td>
      <td>${fmtUsd(p.utilised_usd)}</td>
      <td><span class="badge ${p.status}">${p.status}</span></td>
    </tr>
  `).join("") || `<tr><td colspan="6" class="muted">No programs.</td></tr>`;

  const childrenTree = c.children.map((ch) => `<li><a href="#" data-id="${ch.id}">${ch.name}</a> <span class="muted">(${ch.role})</span></li>`).join("");
  const parentLine = c.parent ? `<li class="root"><a href="#" data-id="${c.parent.id}">${c.parent.name}</a> <span class="muted">(parent)</span></li>` : "";

  card.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
      <div>
        <h2 style="margin-bottom:4px;">${c.name}</h2>
        <div class="muted">${c.industry ?? ""} · ${c.country ?? ""} · ${c.role}</div>
      </div>
      ${rp ? `<div class="badge" style="background:rgba(184,141,255,0.18);border-color:#b88dff;color:#e6d6ff;">Rating ${rp.rating}</div>` : ""}
    </div>

    <div class="kv">
      <div class="k">Legal name</div><div>${c.legal_name ?? "—"}</div>
      <div class="k">Annual revenue</div><div>${fmtUsd(c.annual_revenue_usd)}</div>
      <div class="k">Employees</div><div>${(c.employees ?? 0).toLocaleString()}</div>
      <div class="k">Founded</div><div>${c.founded_year ?? "—"}</div>
      <div class="k">Tax ID</div><div>${c.tax_id ?? "—"}</div>
      <div class="k">Website</div><div>${c.website ?? "—"}</div>
      ${rp ? `
        <div class="k">Credit spread</div><div>${fmtPct(rp.credit_spread)}</div>
        <div class="k">PD (1y)</div><div>${fmtPct(rp.pd_1y)}</div>
        <div class="k">Industry risk</div><div>${fmtPct(rp.industry_risk)}</div>
        <div class="k">Country risk</div><div>${fmtPct(rp.country_risk)}</div>
        <div class="k">Last reviewed</div><div>${fmtTs(rp.last_reviewed)}</div>
      ` : ""}
    </div>

    <div class="section-title">Hierarchy</div>
    <ul class="tree">
      ${parentLine}
      <li class="root"><strong>${c.name}</strong></li>
      ${childrenTree ? `<li class="root"><ul class="tree">${childrenTree}</ul></li>` : `<li class="muted">No children.</li>`}
    </ul>

    <div class="section-title">Credit Limits</div>
    <table class="data-table">
      <thead><tr><th>Product</th><th>Limit</th><th>Used</th><th>Headroom</th></tr></thead>
      <tbody>${limits}</tbody>
    </table>

    <div class="section-title">Programs (${c.programs.length})</div>
    <table class="data-table">
      <thead><tr><th>ID</th><th>Name</th><th>Product</th><th>Limit</th><th>Used</th><th>Status</th></tr></thead>
      <tbody>${programs}</tbody>
    </table>
  `;

  card.querySelectorAll("a[data-id]").forEach((a) => {
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      loadCompanyDetail(a.dataset.id);
    });
  });
}

// ---------- new invoice form ----------
function setupAutocomplete(inputId, panelId, role) {
  const input = $(inputId);
  const panel = $(panelId);
  let activeReq = 0;

  input.addEventListener("input", async () => {
    const q = input.value.trim();
    if (q.length < 1) {
      panel.classList.remove("show");
      return;
    }
    const seq = ++activeReq;
    const data = await fetch(`/api/companies/search?q=${encodeURIComponent(q)}&role=${role}&limit=8`).then((r) => r.json());
    if (seq !== activeReq) return;
    panel.innerHTML = data.map((c) => `
      <div class="autocomplete-item" data-name="${c.name.replace(/"/g, '&quot;')}">
        ${c.name}<span class="meta">${c.industry ?? ""} · ${c.country ?? ""}</span>
      </div>
    `).join("");
    panel.classList.toggle("show", data.length > 0);
    panel.querySelectorAll(".autocomplete-item").forEach((item) => {
      item.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        input.value = item.dataset.name;
        panel.classList.remove("show");
      });
    });
  });
  input.addEventListener("blur", () => setTimeout(() => panel.classList.remove("show"), 150));
}

function setupForm() {
  setupAutocomplete("#seller-input", "#seller-suggestions", "SELLER");
  setupAutocomplete("#buyer-input", "#buyer-suggestions", "BUYER");

  $("#invoice-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const payload = {
      seller_name: fd.get("seller_name"),
      buyer_name: fd.get("buyer_name"),
      product: fd.get("product"),
      amount: parseFloat(fd.get("amount")),
      currency: fd.get("currency"),
      tenor_days: parseInt(fd.get("tenor_days"), 10),
      grace_period_days: parseInt(fd.get("grace_period_days") || "0", 10),
    };
    const submitBtn = ev.target.querySelector("button[type='submit']");
    submitBtn.disabled = true;
    submitBtn.textContent = "Working...";
    try {
      const resp = await fetch("/api/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      const card = $("#result-card");
      card.hidden = false;
      if (!resp.ok) {
        $("#decision-summary").innerHTML = `<div class="summary-banner error">Error: ${data.detail || "Unknown error"}</div>`;
        $("#decision-events").innerHTML = "";
        return;
      }
      const inv = data.invoice;
      $("#decision-summary").innerHTML = `
        <div class="summary-banner">${data.summary}</div>
        <div class="kv">
          <div class="k">Invoice</div><div>${inv.invoice_number}</div>
          <div class="k">Status</div><div><span class="badge ${inv.status}">${inv.status}</span></div>
          <div class="k">Seller → Buyer</div><div>${inv.seller.name} → ${inv.buyer.name}</div>
          <div class="k">Product</div><div>${inv.product}</div>
          <div class="k">Amount</div><div>${inv.amount.toLocaleString()} ${inv.currency} (${fmtUsd(inv.amount_usd)})</div>
          <div class="k">Tenor / Grace</div><div>${inv.tenor_days}d / ${inv.grace_period_days}d</div>
          <div class="k">Base rate</div><div>${fmtPct(inv.base_rate)}</div>
          <div class="k">Credit spread</div><div>${fmtPct(inv.credit_spread)}</div>
          <div class="k">All-in fee</div><div>${fmtUsd(inv.fee_usd)}</div>
          <div class="k">Funded amount</div><div>${fmtUsd(inv.funded_amount_usd)}</div>
        </div>
      `;
      $("#decision-events").innerHTML = data.events.map(renderEvent).join("");
      // Refresh dashboard data for next visit
      loadDashboard();
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit to Agents";
    }
  });
}

// ---------- bootstrap ----------
window.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadMeta();
  loadDashboard();
  setupForm();

  $("#refresh-events").addEventListener("click", loadEvents);
  $("#filter-agent").addEventListener("change", loadEvents);
  $("#filter-severity").addEventListener("change", loadEvents);
  $("#company-search").addEventListener("input", loadCompanies);
  $("#company-role").addEventListener("change", loadCompanies);
});
