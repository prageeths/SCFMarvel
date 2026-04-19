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
    </tr>
  `).join("");
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      // Switch to companies tab and load buyer
      const id = tr.dataset.id;
      const program = data.items.find((x) => x.id == id);
      if (program) {
        document.querySelector('[data-tab="companies"]').click();
        loadCompanyDetail(program.buyer.id);
      }
    });
  });
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
