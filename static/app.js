// ===================================================================== utilitaires
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const eur0 = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const fmt = (n) => eur.format(n);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const monthLabel = (m, long = false) => {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString("fr-FR", long ? { month: "long", year: "numeric" } : { month: "short", year: "2-digit" });
};
const currentMonth = () => new Date().toISOString().slice(0, 7);

async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers = { "Content-Type": "application/json" }; }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { toast(data.error || `Erreur ${res.status}`, true); throw new Error(data.error); }
  return data;
}

let toastTimer;
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 2600);
}

// ===================================================================== état global
const state = { accounts: [], categories: [], months: [], transactions: [], selected: new Set(), stats: null };

async function loadRefs() {
  [state.accounts, state.categories, state.months] = await Promise.all([
    api("/api/accounts"), api("/api/categories"), api("/api/months"),
  ]);
  fillSelects();
}

const KIND_LABEL = { expense: "Dépenses", income: "Revenus", transfer: "Virements internes" };
function categoryOptions(selected, { empty = "— Non catégorisé —" } = {}) {
  let html = empty !== null ? `<option value="">${empty}</option>` : "";
  for (const kind of ["expense", "income", "transfer"]) {
    const cats = state.categories.filter((c) => c.kind === kind);
    if (!cats.length) continue;
    html += `<optgroup label="${KIND_LABEL[kind]}">` +
      cats.map((c) => `<option value="${c.id}" ${c.id == selected ? "selected" : ""}>${esc(c.name)}</option>`).join("") +
      "</optgroup>";
  }
  return html;
}

function fillSelects() {
  for (const sel of $$(".account-select")) {
    const prev = sel.value;
    const all = sel.dataset.all;
    sel.innerHTML = (all ? `<option value="">${all}</option>` : "") +
      state.accounts.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
    if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  }
  for (const sel of $$(".category-select")) {
    const prev = sel.value;
    sel.innerHTML = categoryOptions(prev, { empty: "— Aucune —" });
  }
  const txCat = $("#tx-category"), prevCat = txCat.value;
  txCat.innerHTML = `<option value="">Toutes</option><option value="none">Non catégorisées</option>` + categoryOptions(null, { empty: null });
  txCat.value = prevCat;
  $("#bulk-category").innerHTML = categoryOptions(null);

  const months = state.months.length ? state.months : [currentMonth()];
  for (const id of ["#dash-month", "#tx-month"]) {
    const sel = $(id), prev = sel.value;
    sel.innerHTML = (id === "#tx-month" ? `<option value="">Tous</option>` : "") +
      months.map((m) => `<option value="${m}">${monthLabel(m, true)}</option>`).join("");
    if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  }
}

// ===================================================================== onglets
const tabLoaders = {
  dashboard: loadDashboard, transactions: loadTransactions,
  categories: loadCategoriesTab, accounts: loadAccountsTab, import: () => {},
};
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + name));
  location.hash = name;
  tabLoaders[name]();
}
$("#tabs").addEventListener("click", (e) => { if (e.target.dataset.tab) showTab(e.target.dataset.tab); });

// ===================================================================== tableau de bord
const charts = {};
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function baseOptions({ stacked = false, onClick } = {}) {
  const text2 = cssVar("--text-2"), grid = cssVar("--grid");
  return {
    responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
    interaction: { mode: "index", intersect: false },
    onClick,
    onHover: onClick ? (e, els) => (e.native.target.style.cursor = els.length ? "pointer" : "default") : undefined,
    plugins: {
      legend: { position: "bottom", labels: { color: text2, boxWidth: 10, boxHeight: 10, useBorderRadius: true, borderRadius: 3, padding: 14 } },
      tooltip: {
        itemSort: (a, b) => b.raw - a.raw,
        filter: (item) => item.raw !== 0,
        callbacks: {
          title: (items) => monthLabel(state.stats.months[items[0].dataIndex], true),
          label: (item) => ` ${item.dataset.label} : ${fmt(item.raw)}`,
          footer: stacked ? (items) => `Total : ${fmt(items.reduce((s, i) => s + i.raw, 0))}` : undefined,
        },
      },
    },
    scales: {
      x: { stacked, grid: { display: false }, ticks: { color: text2 }, border: { color: grid } },
      y: { stacked, grid: { color: grid }, border: { display: false }, ticks: { color: text2, callback: (v) => eur0.format(v) } },
    },
  };
}

function barDataset(label, data, color, extra = {}) {
  return {
    label, data, backgroundColor: color, borderColor: cssVar("--surface"), borderWidth: 1,
    borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 36, ...extra,
  };
}

function drawChart(id, config) {
  charts[id]?.destroy();
  charts[id] = new Chart($("#" + id), config);
}

async function loadDashboard() {
  await loadRefs();
  const dashMonth = $("#dash-month");
  if (!dashMonth.value) dashMonth.value = state.months[0] || currentMonth();
  const params = new URLSearchParams({ end: dashMonth.value, months: $("#dash-range").value, account: $("#dash-account").value });
  const s = (state.stats = await api("/api/stats?" + params));
  const labels = s.months.map((m) => monthLabel(m));
  const last = s.months.length - 1;

  renderKpis(s, last);
  renderBreakdown(s, last);

  // dépenses par catégorie (barres empilées) ; on segmente avec un liseré couleur de fond
  const stackedOpts = baseOptions({
    stacked: true,
    onClick: (e, els) => { if (els.length) { renderBreakdown(s, els[0].index); renderKpis(s, els[0].index); } },
  });
  drawChart("chart-categories", {
    type: "bar",
    data: { labels, datasets: s.categories.map((c) => barDataset(c.category, c.values, c.color, { borderRadius: 0, borderWidth: { top: 2 } })) },
    options: stackedOpts,
  });

  drawChart("chart-balance", {
    type: "bar",
    data: {
      labels,
      datasets: [
        barDataset("Revenus", s.income, matchMedia("(prefers-color-scheme: dark)").matches ? "#199e70" : "#1baf7a", { borderWidth: 0 }),
        barDataset("Dépenses", s.expense, cssVar("--accent"), { borderWidth: 0 }),
      ],
    },
    options: { ...baseOptions(), datasets: { bar: { categoryPercentage: 0.7, barPercentage: 0.9 } } },
  });

  drawChart("chart-recurring", {
    type: "bar",
    data: {
      labels,
      datasets: [
        barDataset("Récurrentes", s.recurring, "#4a3aa7", { borderRadius: 0, borderWidth: { top: 2 } }),
        barDataset("Ponctuelles", s.one_off, "#eda100", { borderRadius: 0, borderWidth: { top: 2 } }),
      ],
    },
    options: baseOptions({ stacked: true }),
  });
}

function renderKpis(s, i) {
  const pct = (a, b) => (b ? Math.round(((a - b) / Math.abs(b)) * 100) : null);
  const delta = (cur, prev, invert = false) => {
    if (i === 0) return `<div class="k-delta">&nbsp;</div>`;
    const p = pct(cur, prev);
    if (p === null) return `<div class="k-delta">—</div>`;
    const cls = p > 0 ? "up" : p < 0 ? "down" : "";
    return `<div class="k-delta ${invert ? "inv" : ""}"><span class="${cls}">${p > 0 ? "▲" : p < 0 ? "▼" : ""} ${Math.abs(p)} %</span> vs mois précédent</div>`;
  };
  const bal = s.income[i] - s.expense[i], balPrev = i ? s.income[i - 1] - s.expense[i - 1] : 0;
  const recShare = s.expense[i] ? Math.round((s.recurring[i] / s.expense[i]) * 100) : 0;
  $("#kpis").innerHTML = `
    <div class="kpi"><div class="k-label">Dépenses · ${monthLabel(s.months[i], true)}</div><div class="k-value">${fmt(s.expense[i])}</div>${delta(s.expense[i], s.expense[i - 1])}</div>
    <div class="kpi"><div class="k-label">Revenus</div><div class="k-value">${fmt(s.income[i])}</div>${delta(s.income[i], s.income[i - 1], true)}</div>
    <div class="kpi"><div class="k-label">Solde du mois</div><div class="k-value" style="color:var(${bal >= 0 ? "--good" : "--bad"})">${bal >= 0 ? "+" : ""}${fmt(bal)}</div>${delta(bal, balPrev, true)}</div>
    <div class="kpi"><div class="k-label">Dépenses récurrentes</div><div class="k-value">${fmt(s.recurring[i])}</div><div class="k-delta">${recShare} % des dépenses du mois</div></div>`;
}

function renderBreakdown(s, i) {
  const month = s.months[i];
  $("#breakdown-title").textContent = "Répartition · " + monthLabel(month, true);
  const items = s.categories.map((c) => ({ ...c, v: c.values[i] })).filter((c) => c.v > 0).sort((a, b) => b.v - a.v);
  const total = items.reduce((a, c) => a + c.v, 0);
  if (!items.length) { $("#breakdown").innerHTML = `<div class="empty">Aucune dépense ce mois-ci</div>`; return; }
  const max = items[0].v;
  $("#breakdown").innerHTML = items.map((c) => `
    <div class="bd-row" data-cat="${esc(c.category)}" data-month="${month}" title="Voir les opérations">
      <div class="bd-name"><span class="dot" style="background:${c.color}"></span>${esc(c.category)}</div>
      <div class="bd-val">${fmt(c.v)}<small>${Math.round((c.v / total) * 100)} %</small></div>
      <div class="bd-bar"><span style="width:${(c.v / max) * 100}%;background:${c.color}"></span></div>
    </div>`).join("");
}

// clic sur une catégorie de la répartition -> opérations filtrées
$("#breakdown").addEventListener("click", (e) => {
  const row = e.target.closest(".bd-row");
  if (!row) return;
  const cat = state.categories.find((c) => c.name === row.dataset.cat);
  $("#tx-month").value = row.dataset.month;
  $("#tx-category").value = cat ? cat.id : "none";
  $("#tx-account").value = $("#dash-account").value;
  showTab("transactions");
});
["#dash-month", "#dash-range", "#dash-account"].forEach((id) => $(id).addEventListener("change", loadDashboard));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => $("#tab-dashboard.active") && loadDashboard());

// ===================================================================== opérations
async function loadTransactions() {
  await loadRefs();
  const params = new URLSearchParams({
    month: $("#tx-month").value, account: $("#tx-account").value, category: $("#tx-category").value,
    recurring: $("#tx-recurring").value, q: $("#tx-search").value.trim(),
  });
  state.transactions = await api("/api/transactions?" + params);
  state.selected.clear();
  renderTransactions();
}

function renderTransactions() {
  const txs = state.transactions;
  const out = txs.filter((t) => t.amount < 0).reduce((s, t) => s + t.amount, 0);
  const inc = txs.filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0);
  const uncat = txs.filter((t) => !t.category_id).length;
  $("#tx-summary").innerHTML = `
    <span><b>${txs.length}</b> opération${txs.length > 1 ? "s" : ""}</span>
    <span>Débits <b>${fmt(out)}</b></span><span>Crédits <b>${fmt(inc)}</b></span>
    ${uncat ? `<span style="color:#c98500">${uncat} non catégorisée${uncat > 1 ? "s" : ""}</span>` : ""}`;

  if (!txs.length) {
    $("#tx-body").innerHTML = `<tr><td colspan="9" class="empty">Aucune opération. Importez un relevé depuis l'onglet « Import CSV ».</td></tr>`;
  } else {
    $("#tx-body").innerHTML = txs.map((t) => `
      <tr data-id="${t.id}" class="${state.selected.has(t.id) ? "selected" : ""}">
        <td><input type="checkbox" class="tx-check" ${state.selected.has(t.id) ? "checked" : ""}></td>
        <td class="num">${new Date(t.date).toLocaleDateString("fr-FR")}</td>
        <td><span class="account-tag"><span class="dot" style="background:${t.account_color}"></span>${esc(t.account_name)}</span></td>
        <td class="label"><div title="${esc(t.label)}">${esc(t.label)}</div></td>
        <td class="num ${t.amount > 0 ? "pos" : ""}">${t.amount > 0 ? "+" : ""}${fmt(t.amount)}</td>
        <td><select class="tx-cat ${t.category_id ? "" : "uncat"}">${categoryOptions(t.category_id)}</select></td>
        <td><label class="toggle"><input type="checkbox" class="tx-rec" ${t.recurring ? "checked" : ""}><span></span></label></td>
        <td><input class="note" value="${esc(t.note)}" placeholder="…"></td>
        <td style="white-space:nowrap">
          <button class="icon-btn tx-rule" title="Créer une règle à partir de ce libellé">⚡</button>
          <button class="icon-btn tx-del" title="Supprimer">✕</button>
        </td>
      </tr>`).join("");
  }
  $("#tx-check-all").checked = txs.length > 0 && state.selected.size === txs.length;
  updateBulkbar();
}

function updateBulkbar() {
  const n = state.selected.size;
  $("#bulkbar").classList.toggle("hidden", n === 0);
  $("#bulk-count").textContent = `${n} sélectionnée${n > 1 ? "s" : ""}`;
}

const txById = (id) => state.transactions.find((t) => t.id === id);
const patchTx = (ids, fields) => api("/api/transactions", { method: "PATCH", body: { ids, ...fields } });

$("#tx-body").addEventListener("change", async (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  const id = Number(tr.dataset.id), tx = txById(id);
  if (e.target.classList.contains("tx-check")) {
    e.target.checked ? state.selected.add(id) : state.selected.delete(id);
    tr.classList.toggle("selected", e.target.checked);
    updateBulkbar();
  } else if (e.target.classList.contains("tx-cat")) {
    tx.category_id = e.target.value ? Number(e.target.value) : null;
    e.target.classList.toggle("uncat", !tx.category_id);
    await patchTx([id], { category_id: tx.category_id });
    toast("Catégorie enregistrée");
  } else if (e.target.classList.contains("tx-rec")) {
    tx.recurring = e.target.checked ? 1 : 0;
    await patchTx([id], { recurring: tx.recurring });
  } else if (e.target.classList.contains("note")) {
    tx.note = e.target.value;
    await patchTx([id], { note: tx.note });
    toast("Note enregistrée");
  }
});

$("#tx-body").addEventListener("click", async (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  const id = Number(tr.dataset.id);
  if (e.target.classList.contains("tx-del")) {
    if (!confirm("Supprimer cette opération ?")) return;
    await api("/api/transactions", { method: "DELETE", body: { ids: [id] } });
    loadTransactions();
  } else if (e.target.classList.contains("tx-rule")) {
    openRuleDialog(txById(id));
  }
});

$("#tx-check-all").addEventListener("change", (e) => {
  state.selected = new Set(e.target.checked ? state.transactions.map((t) => t.id) : []);
  renderTransactions();
});

let searchTimer;
$("#tx-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadTransactions, 250); });
["#tx-month", "#tx-account", "#tx-category", "#tx-recurring"].forEach((id) => $(id).addEventListener("change", loadTransactions));

// actions groupées
$("#bulk-apply-cat").addEventListener("click", async () => {
  const v = $("#bulk-category").value;
  await patchTx([...state.selected], { category_id: v ? Number(v) : null });
  toast("Catégorie appliquée"); loadTransactions();
});
$("#bulk-rec-on").addEventListener("click", async () => { await patchTx([...state.selected], { recurring: 1 }); loadTransactions(); });
$("#bulk-rec-off").addEventListener("click", async () => { await patchTx([...state.selected], { recurring: 0 }); loadTransactions(); });
$("#bulk-delete").addEventListener("click", async () => {
  if (!confirm(`Supprimer ${state.selected.size} opération(s) ?`)) return;
  await api("/api/transactions", { method: "DELETE", body: { ids: [...state.selected] } });
  loadTransactions();
});

// saisie manuelle
$("#tx-add-btn").addEventListener("click", () => {
  const f = $("#tx-form");
  f.reset();
  f.date.value = new Date().toISOString().slice(0, 10);
  $("#tx-dialog").showModal();
});
$("#tx-dialog").addEventListener("close", async () => {
  if ($("#tx-dialog").returnValue !== "ok") return;
  const f = $("#tx-form");
  await api("/api/transactions", {
    method: "POST",
    body: {
      account_id: Number(f.account_id.value), date: f.date.value, label: f.label.value, amount: f.amount.value,
      category_id: f.category_id.value ? Number(f.category_id.value) : null, recurring: f.recurring.checked,
    },
  });
  toast("Opération ajoutée"); loadTransactions();
});

// règle depuis une opération
function suggestPattern(label) {
  // retire les préfixes bancaires usuels, les dates et les numéros
  return label.toUpperCase()
    .replace(/\b(PAIEMENT|PAR|CARTE|CB|PRLV|SEPA|VIR|VIREMENT|INST|RECU|EMIS|DE|FACTURE)\b/g, " ")
    .replace(/\d{2}[\/.-]\d{2}([\/.-]\d{2,4})?/g, " ")
    .replace(/\S*\d{3,}\S*/g, " ")
    .replace(/\s+/g, " ").trim().split(" ").slice(0, 2).join(" ");
}
function openRuleDialog(tx) {
  const f = $("#rule-dialog-form");
  f.reset();
  $("#rule-dialog-label").textContent = tx.label;
  f.pattern.value = suggestPattern(tx.label);
  f.category_id.value = tx.category_id ?? "";
  f.recurring.value = tx.recurring ? "1" : "";
  $("#rule-dialog").showModal();
}
$("#rule-dialog").addEventListener("close", async () => {
  if ($("#rule-dialog").returnValue !== "ok") return;
  const f = $("#rule-dialog-form");
  const r = await api("/api/rules", { method: "POST", body: ruleBody(f) });
  // la règle s'applique aussi aux opérations déjà catégorisées qui correspondent
  const all = await api("/api/rules/apply", { method: "POST", body: { only_uncategorized: false } });
  toast(`Règle créée · ${r.applied + all.applied} opération(s) mises à jour`);
  if ($("#tab-transactions.active")) loadTransactions();
});
function ruleBody(f) {
  return {
    pattern: f.pattern.value, category_id: f.category_id.value ? Number(f.category_id.value) : null,
    recurring: f.recurring.value === "" ? null : Number(f.recurring.value),
  };
}

// ===================================================================== import CSV
let importFile = null, importPreview = null;
const ROLES = [
  ["date", "Date *"], ["label", "Libellé *"], ["label2", "Libellé (complément)"],
  ["amount", "Montant (signé)"], ["debit", "Débit"], ["credit", "Crédit"],
];

async function previewFile(file) {
  importFile = file;
  $("#imp-file-name").textContent = "📄 " + file.name;
  const form = new FormData();
  form.append("file", file);
  importPreview = await api("/api/import/preview", { method: "POST", form });
  renderMapping();
  $("#imp-mapping-card").classList.remove("hidden");
  $("#imp-result").classList.add("hidden");
}

function renderMapping() {
  const p = importPreview;
  const delimName = { ";": "point-virgule", ",": "virgule", "\t": "tabulation", "|": "barre verticale" }[p.delimiter] || p.delimiter;
  $("#imp-info").textContent = `${p.count} lignes détectées · séparateur : ${delimName}. Utilisez soit une colonne « Montant » signée, soit les colonnes « Débit » + « Crédit ».`;
  const opts = (sel) => `<option value="">—</option>` + p.header.map((h, i) => `<option value="${i}" ${sel === i ? "selected" : ""}>${esc(h || `Colonne ${i + 1}`)}</option>`).join("");
  $("#imp-mapping").innerHTML = ROLES.map(([k, lbl]) => `<label>${lbl}<select data-role="${k}">${opts(p.mapping[k])}</select></label>`).join("");
  renderPreviewTable();
}

function currentMapping() {
  return Object.fromEntries($$("#imp-mapping select").map((s) => [s.dataset.role, s.value === "" ? null : Number(s.value)]));
}

function renderPreviewTable() {
  const p = importPreview, m = currentMapping();
  const roleOf = (i) => ROLES.find(([k]) => m[k] === i)?.[1].replace(" *", "");
  $("#imp-preview").innerHTML =
    `<thead><tr>${p.header.map((h, i) => `<th class="${roleOf(i) ? "mapped" : ""}">${esc(h)}${roleOf(i) ? `<br><small>→ ${roleOf(i)}</small>` : ""}</th>`).join("")}</tr></thead>` +
    `<tbody>${p.rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

$("#imp-mapping").addEventListener("change", renderPreviewTable);
$("#imp-file").addEventListener("change", (e) => e.target.files[0] && previewFile(e.target.files[0]));
const drop = $("#file-drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); e.dataTransfer.files[0] && previewFile(e.dataTransfer.files[0]); });

$("#imp-commit").addEventListener("click", async () => {
  const m = currentMapping();
  if (m.date === null || m.label === null) return toast("Indiquez au moins la date et le libellé", true);
  if (m.amount === null && m.debit === null && m.credit === null) return toast("Indiquez la colonne Montant ou Débit/Crédit", true);
  if (!$("#imp-account").value) return toast("Créez d'abord un compte", true);
  const form = new FormData();
  form.append("file", importFile);
  form.append("account_id", $("#imp-account").value);
  form.append("mapping", JSON.stringify(m));
  form.append("invert", $("#imp-invert").checked ? "1" : "0");
  const r = await api("/api/import/commit", { method: "POST", form });
  const box = $("#imp-result");
  box.classList.remove("hidden");
  box.innerHTML = `
    <h2>Résultat</h2>
    <p class="result-ok">✓ ${r.inserted} opération(s) importée(s)</p>
    <p>${r.duplicates} doublon(s) ignoré(s) · ${r.categorized} catégorisée(s) automatiquement par vos règles</p>
    ${r.error_count ? `<p>${r.error_count} ligne(s) illisible(s) :</p><div class="errors">${r.errors.map(esc).join("<br>")}</div>` : ""}
    <div class="row"><button class="btn primary" id="goto-uncat">Catégoriser les opérations importées →</button></div>`;
  $("#goto-uncat").onclick = () => {
    $("#tx-month").value = ""; $("#tx-category").value = "none"; $("#tx-account").value = $("#imp-account").value;
    showTab("transactions");
  };
  $("#imp-mapping-card").classList.add("hidden");
  $("#imp-file").value = "";
  $("#imp-file-name").textContent = "Glissez un fichier CSV ici ou cliquez pour choisir";
});

// ===================================================================== catégories & règles
async function loadCategoriesTab() {
  await loadRefs();
  const kindSel = (k) => ["expense", "income", "transfer"].map((v) =>
    `<option value="${v}" ${v === k ? "selected" : ""}>${{ expense: "Dépense", income: "Revenu", transfer: "Virement interne" }[v]}</option>`).join("");
  $("#cat-list").innerHTML = state.categories.map((c) => `
    <tr data-id="${c.id}">
      <td style="width:48px"><input type="color" value="${c.color}" data-f="color"></td>
      <td><input value="${esc(c.name)}" data-f="name"></td>
      <td><select data-f="kind">${kindSel(c.kind)}</select></td>
      <td><span class="badge">${c.tx_count} op.</span></td>
      <td><button class="icon-btn del" title="Supprimer">✕</button></td>
    </tr>`).join("");

  const rules = await api("/api/rules");
  const recSel = (r) => [["", "Inchangée"], ["1", "Récurrente"], ["0", "Ponctuelle"]].map(([v, l]) =>
    `<option value="${v}" ${String(r ?? "") === v ? "selected" : ""}>${l}</option>`).join("");
  $("#rule-list").innerHTML = rules.length ? rules.map((r) => `
    <tr data-id="${r.id}">
      <td><input value="${esc(r.pattern)}" name="pattern"></td>
      <td><select name="category_id">${categoryOptions(r.category_id, { empty: "— Aucune —" })}</select></td>
      <td><select name="recurring">${recSel(r.recurring)}</select></td>
      <td><button class="icon-btn del" title="Supprimer">✕</button></td>
    </tr>`).join("") : `<tr><td class="empty">Aucune règle. Astuce : le bouton ⚡ dans la liste des opérations crée une règle en un clic.</td></tr>`;
}

$("#cat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  await api("/api/categories", { method: "POST", body: { name: f.name.value, color: f.color.value, kind: f.kind.value } });
  f.reset(); loadCategoriesTab();
});
$("#cat-list").addEventListener("change", async (e) => {
  const tr = e.target.closest("tr");
  await api(`/api/categories/${tr.dataset.id}`, { method: "PUT", body: { [e.target.dataset.f]: e.target.value } });
  toast("Catégorie mise à jour"); loadRefs();
});
$("#cat-list").addEventListener("click", async (e) => {
  if (!e.target.classList.contains("del")) return;
  if (!confirm("Supprimer cette catégorie ? Les opérations concernées redeviendront non catégorisées.")) return;
  await api(`/api/categories/${e.target.closest("tr").dataset.id}`, { method: "DELETE" });
  loadCategoriesTab();
});

$("#rule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await api("/api/rules", { method: "POST", body: ruleBody(e.target) });
  toast(`Règle ajoutée · ${r.applied} opération(s) catégorisée(s)`);
  e.target.reset(); loadCategoriesTab();
});
$("#rule-list").addEventListener("change", async (e) => {
  const tr = e.target.closest("tr");
  const get = (n) => $(`[name=${n}]`, tr);
  await api(`/api/rules/${tr.dataset.id}`, { method: "PUT", body: ruleBody({ pattern: get("pattern"), category_id: get("category_id"), recurring: get("recurring") }) });
  toast("Règle mise à jour");
});
$("#rule-list").addEventListener("click", async (e) => {
  if (!e.target.classList.contains("del")) return;
  await api(`/api/rules/${e.target.closest("tr").dataset.id}`, { method: "DELETE" });
  loadCategoriesTab();
});
$("#rules-apply").addEventListener("click", async () => {
  const r = await api("/api/rules/apply", { method: "POST", body: { only_uncategorized: true } });
  toast(`${r.applied} opération(s) catégorisée(s)`); loadCategoriesTab();
});
$("#rules-apply-all").addEventListener("click", async () => {
  if (!confirm("Les règles écraseront les catégories des opérations correspondantes, y compris celles choisies à la main. Continuer ?")) return;
  const r = await api("/api/rules/apply", { method: "POST", body: { only_uncategorized: false } });
  toast(`${r.applied} opération(s) mises à jour`); loadCategoriesTab();
});
$("#detect-recurring").addEventListener("click", async () => {
  const r = await api("/api/recurring/detect", { method: "POST" });
  toast(`${r.marked} opération(s) marquées comme récurrentes`);
});

// ===================================================================== comptes
async function loadAccountsTab() {
  await loadRefs();
  $("#acc-list").innerHTML = state.accounts.map((a) => `
    <tr data-id="${a.id}">
      <td style="width:48px"><input type="color" value="${a.color}" data-f="color"></td>
      <td><input value="${esc(a.name)}" data-f="name"></td>
      <td><span class="badge">${a.tx_count} op.</span></td>
      <td><button class="icon-btn del" title="Supprimer">✕</button></td>
    </tr>`).join("");
}
$("#acc-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/accounts", { method: "POST", body: { name: e.target.name.value, color: e.target.color.value } });
  e.target.reset(); loadAccountsTab();
});
$("#acc-list").addEventListener("change", async (e) => {
  await api(`/api/accounts/${e.target.closest("tr").dataset.id}`, { method: "PUT", body: { [e.target.dataset.f]: e.target.value } });
  toast("Compte mis à jour"); loadRefs();
});
$("#acc-list").addEventListener("click", async (e) => {
  if (!e.target.classList.contains("del")) return;
  const tr = e.target.closest("tr");
  const acc = state.accounts.find((a) => a.id == tr.dataset.id);
  if (!confirm(`Supprimer « ${acc.name} » et ses ${acc.tx_count} opération(s) ? Cette action est définitive.`)) return;
  await api(`/api/accounts/${tr.dataset.id}`, { method: "DELETE" });
  loadAccountsTab();
});

// ===================================================================== démarrage
showTab(location.hash.slice(1) in tabLoaders ? location.hash.slice(1) : "dashboard");
