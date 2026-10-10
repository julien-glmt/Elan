/* Élan – module Finances : vue d'ensemble, transactions, budget, abonnements, patrimoine, analyse */
"use strict";

const eur = (x, dec = 0) => (x == null || isNaN(x) ? "—" : `<span class="money">${Number(x).toLocaleString("fr-FR", { minimumFractionDigits: dec, maximumFractionDigits: dec })} €</span>`);
const eurS = (x, dec = 0) => (x == null ? "—" : `<span class="money">${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toLocaleString("fr-FR", { minimumFractionDigits: dec, maximumFractionDigits: dec })} €</span>`);
const monthLabel = (ym) => `${MONTH_NAMES[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
const shiftYM = (ym, k) => { let y = Number(ym.slice(0, 4)), m = Number(ym.slice(5, 7)) - 1 + k; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return `${y}-${String(m + 1).padStart(2, "0")}`; };

function privacyOn() { try { return localStorage.getItem("elan_privacy") === "1"; } catch { return false; } }
function applyPrivacy() { document.body.classList.toggle("privacy", privacyOn()); }
applyPrivacy();
function togglePrivacy() { try { localStorage.setItem("elan_privacy", privacyOn() ? "0" : "1"); } catch { /* */ } applyPrivacy(); }

async function finData(force = false) {
  if (!force && state.fin && Date.now() - state.finAt < 8000) return state.fin;
  state.fin = await api("/api/fin/data");
  state.finAt = Date.now();
  return state.fin;
}
function finInvalidate() { state.fin = null; }
const catOf = (D, id) => D.categories.find((c) => c.id === id);
const accOf = (D, id) => D.accounts.find((a) => a.id === id);

function monthNav(ym, todayYM) {
  return h`<div class="fin-month"><button class="icon-btn" data-fm="-1" aria-label="Mois précédent"><svg viewBox="0 0 24 24"><path d="m15 6-6 6 6 6"/></svg></button>
    <div><b>${monthLabel(ym)}</b>${ym !== todayYM ? `<a href="#" data-fm="0">revenir à ce mois-ci</a>` : `<span>mois en cours</span>`}</div>
    <button class="icon-btn" data-fm="1" aria-label="Mois suivant" ${ym >= todayYM ? "disabled" : ""}><svg viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg></button></div>`;
}
function bindMonthNav(view, todayYM) {
  $$("[data-fm]", view).forEach((b) => (b.onclick = (e) => {
    e.preventDefault();
    const k = Number(b.dataset.fm);
    state.finMonth = k === 0 ? null : shiftYM(state.finMonth || todayYM, k);
    if (state.finMonth && state.finMonth > todayYM) state.finMonth = null;
    render();
  }));
}
function finHeadActions() {
  return `<div class="fin-actions"><button class="btn sm" id="fin-priv" title="Masquer les montants">${privacyOn() ? "Afficher les montants" : "Mode discret"}</button><button class="btn sm primary" id="fin-add">+ Transaction</button></div>`;
}
function bindHeadActions(view) {
  const p = $("#fin-priv", view); if (p) p.onclick = () => { togglePrivacy(); p.textContent = privacyOn() ? "Afficher les montants" : "Mode discret"; };
  const a = $("#fin-add", view); if (a) a.onclick = () => editTx({});
}

// ================================================================ CONFIGURATION
async function finSetup(view) {
  const D = await finData(true);
  view.innerHTML = h`<div class="card fin-setup">
    <div class="eyebrow-s fin-eyebrow">Finances</div>
    <h2 style="margin:2px 0 6px;font-size:24px">On met en place ton suivi</h2>
    <p class="small muted" style="margin:0 0 18px">Deux minutes : tes comptes avec leur solde du jour, et le jour où ton mois commence. Ensuite, tu ajoutes tes dépenses à la main ou en important le relevé de ta banque (CSV), et tout se calcule.</p>
    <h3>Tes comptes</h3>
    <div id="fs-accs">${D.accounts.map((a) => accRow(a, D)).join("")}</div>
    <button class="btn sm" id="fs-addacc" style="margin-top:8px">+ Ajouter un compte</button>
    <h3 style="margin-top:22px">Ton mois budgétaire</h3>
    <div class="f-row"><span class="small">Mon mois commence le</span><select id="fs-day">${Array.from({ length: 28 }, (_, i) => `<option value="${i + 1}" ${D.settings.month_start_day === i + 1 ? "selected" : ""}>${i + 1}${i === 0 ? "er du mois" : ""}</option>`).join("")}</select></div>
    <p class="small muted">Si tu es payé en fin de mois (le 28 par ex.), choisis ce jour : le salaire de fin octobre finance alors « novembre ».</p>
    <div class="btns"><button class="btn primary" id="fs-go">C'est parti</button></div></div>`;
  const addRow = () => { $("#fs-accs", view).insertAdjacentHTML("beforeend", accRow({ id: "", name: "", type: "courant", initial: 0 }, D)); };
  $("#fs-addacc", view).onclick = addRow;
  $("#fs-go", view).onclick = async (e) => {
    e.currentTarget.disabled = true;
    try {
      for (const row of $$(".acc-row", view)) {
        const name = $(".ar-name", row).value.trim();
        if (!name) { if (row.dataset.id) await api(`/api/fin/accounts/${row.dataset.id}`, { method: "DELETE" }); continue; }
        await api("/api/fin/accounts", { method: "POST", body: { id: row.dataset.id || undefined, name, type: $(".ar-type", row).value, initial: $(".ar-bal", row).value || 0, initial_date: today() } });
      }
      await api("/api/fin/settings", { method: "POST", body: { month_start_day: $("#fs-day", view).value, setup: true } });
      finInvalidate(); toast("Suivi prêt"); render();
    } catch (err) { toast(err.message, true); e.currentTarget.disabled = false; }
  };
}
function accRow(a, D) {
  return h`<div class="acc-row" data-id="${a.id || ""}"><input class="ar-name" value="${esc(a.name)}" placeholder="Nom du compte">
    <select class="ar-type">${Object.entries(D.account_types).map(([k, l]) => `<option value="${k}" ${k === a.type ? "selected" : ""}>${l}</option>`).join("")}</select>
    <input class="ar-bal" type="number" step="0.01" inputmode="decimal" value="${a.initial || ""}" placeholder="Solde du jour (€)"></div>`;
}

// ================================================================ VUE D'ENSEMBLE
async function renderFinHome(view) {
  const D0 = await finData(true);
  if (!D0.settings.setup) return finSetup(view);
  const O = await api(`/api/fin/overview${state.finMonth ? `?month=${state.finMonth}` : ""}`);
  const C = O.current, P = O.previous;
  const ym = O.month;
  const varLeft = C.var_left;
  const diff = (a, b) => (b ? Math.round(((a - b) / Math.abs(b)) * 100) : null);
  const dSpent = diff(C.spent, P.spent);
  view.innerHTML = h`
    <div class="fin-top">${monthNav(ym, O.today_month)}${finHeadActions()}</div>
    <div class="cols"><div>
      <div class="card fin-hero">
        <div class="fh-main">
          <div class="fh-label">${varLeft != null ? (varLeft >= 0 ? "Reste à dépenser ce mois" : "Budget dépassé de") : "Solde du mois"}</div>
          <div class="fh-big num">${varLeft != null ? eur(Math.abs(varLeft)) : eurS(C.net)}</div>
          <div class="fh-sub">${C.per_day_left != null && C.per_day_left > 0 ? `soit ${eur(C.per_day_left)} par jour pendant ${C.left_days} jour${C.left_days > 1 ? "s" : ""}` : `du ${fmtDay(C.from)} au ${fmtDay(C.to)}`}</div>
        </div>
        <div class="fh-kv">
          <div><span>Revenus</span><b class="num">${eur(C.income)}</b></div>
          <div><span>Dépenses</span><b class="num">${eur(C.spent)}</b><em class="${dSpent > 0 ? "neg" : "pos"}">${dSpent != null && P.n ? `${dSpent > 0 ? "+" : ""}${dSpent} % vs ${MONTH_NAMES[Number(P.month.slice(5)) - 1]}` : ""}</em></div>
          <div><span>Épargné</span><b class="num">${eur(C.saved)}</b></div>
          <div><span>Taux d'épargne</span><b class="num">${C.savings_rate != null ? C.savings_rate + " %" : "—"}</b></div>
        </div>
      </div>
      ${O.insights.length ? `<div class="card section">${O.insights.map((i) => `<div class="fin-ins ${i.level}">${esc(i.text)}</div>`).join("")}</div>` : ""}
      <div class="card section"><div class="row between"><h2 style="margin:0">Budget du mois</h2><a href="#" class="small" id="fh-budget">Tout voir →</a></div>
        ${C.budgets.length ? C.budgets.slice(0, 7).map(budgetBar).join("") : `<div class="empty small">Aucune dépense ce mois-ci.</div>`}</div>
      <div class="card section"><h2>Revenus et dépenses sur 12 mois</h2><div class="chart-box" style="height:220px"><canvas id="c-f-flow"></canvas></div></div>
    </div><div>
      <div class="card fin-nw" id="fh-nw"><div class="row between"><h2 style="margin:0">Patrimoine</h2><span class="small muted">${O.accounts.length} comptes</span></div>
        <div class="fh-big num" style="font-size:34px;margin-top:6px">${eur(O.net_worth)}</div>
        <div class="small muted">dont disponible ${eur(O.liquid)}${O.months_cover != null ? ` · ${String(O.months_cover).replace(".", ",")} mois de dépenses de côté` : ""}</div>
        <div class="chart-box" style="height:110px;margin-top:8px"><canvas id="c-f-nw"></canvas></div></div>
      <div class="card section"><h2>Où part l'argent</h2>${C.budgets.length ? `<div class="donut-wrap"><div class="chart-box" style="height:190px;width:190px"><canvas id="c-f-donut"></canvas></div>
        <div class="donut-legend">${C.budgets.slice(0, 7).map((b) => `<div><i style="background:${b.color || "#999"}"></i><span>${esc(b.name)}</span><b class="num">${eur(b.spent)}</b></div>`).join("")}</div></div>` : `<div class="empty small">—</div>`}</div>
      ${O.upcoming.length ? `<div class="card section"><h2>À venir ce mois</h2>${O.upcoming.map((u) => `<div class="fin-line"><span class="muted small">${fmtDay(u.date)}</span><span style="flex:1">${esc(u.label)}</span><b class="num ${u.amount < 0 ? "" : "pos"}">${eurS(u.amount, 2)}</b></div>`).join("")}
        <div class="small muted" style="margin-top:8px">Charges fixes : ${eur(O.monthly_fixed)} par mois.</div></div>` : ""}
      ${O.goals.length ? `<div class="card section"><h2>Objectifs d'épargne</h2>${O.goals.map(goalHtml).join("")}</div>` : ""}
      ${O.top.length ? `<div class="card section"><h2>Plus grosses dépenses</h2>${O.top.map((t) => `<div class="fin-line"><span class="muted small">${fmtDay(t.date)}</span><span style="flex:1;min-width:0" class="ellipsis">${esc(t.label || "")}<span class="muted small"> · ${esc(t.category || "sans catégorie")}</span></span><b class="num">${eurS(t.amount, 2)}</b></div>`).join("")}</div>` : ""}
      ${O.sport_year ? `<div class="card section fin-sport"><h2>Running</h2><div class="row" style="gap:18px;flex-wrap:wrap">
        <div><span class="small muted">Dépensé en ${new Date().getFullYear()}</span><div class="fh-big num" style="font-size:24px">${eur(O.sport_year)}</div></div>
        ${O.eur_per_km ? `<div><span class="small muted">Pour ${km(O.run_km_year, 0)} km courus</span><div class="fh-big num" style="font-size:24px">${eur(O.eur_per_km, 2)}<small>/km</small></div></div>` : ""}</div></div>` : ""}
    </div></div>`;
  bindMonthNav(view, O.today_month);
  bindHeadActions(view);
  $("#fh-budget", view).onclick = (e) => { e.preventDefault(); setView("f-budget"); };
  $("#fh-nw", view).onclick = () => setView("f-accounts");
  if (typeof Chart === "undefined") return;
  chartDefaults();
  const H = O.history;
  mkChart($("#c-f-flow", view), { type: "bar", data: { labels: H.map((x) => MONTHS[Number(x.month.slice(5)) - 1]), datasets: [
    { label: "Revenus", data: H.map((x) => x.income), backgroundColor: "#10b981", borderRadius: 4 },
    { label: "Dépenses", data: H.map((x) => x.spent), backgroundColor: "#6366f1", borderRadius: 4 },
    { label: "Épargné", data: H.map((x) => x.saved), backgroundColor: "#f59e0b", borderRadius: 4 },
  ] }, options: { plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${Math.round(c.raw).toLocaleString("fr-FR")} €` } } }, scales: { x: { grid: { display: false } } } } });
  mkChart($("#c-f-nw", view), { type: "line", data: { labels: O.net_worth_history.map((x) => x.month), datasets: [{ data: O.net_worth_history.map((x) => x.value), borderColor: "#6366f1", backgroundColor: "rgba(99,102,241,.12)", fill: true, pointRadius: 0, tension: 0.35 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: (c) => monthLabel(c[0].label), label: (c) => `${Math.round(c.raw).toLocaleString("fr-FR")} €` } } }, scales: { x: { display: false }, y: { display: false } } } });
  if (C.budgets.length) mkChart($("#c-f-donut", view), { type: "doughnut", data: { labels: C.budgets.map((b) => b.name), datasets: [{ data: C.budgets.map((b) => Math.max(0, b.spent)), backgroundColor: C.budgets.map((b) => b.color || "#999"), borderWidth: 0 }] },
    options: { cutout: "68%", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.label} : ${Math.round(c.raw).toLocaleString("fr-FR")} €` } } } } });
}

function budgetBar(b) {
  const pct = b.budget ? Math.min(100, (b.spent / b.budget) * 100) : 0;
  const proj = b.budget ? Math.min(100, (b.projected / b.budget) * 100) : 0;
  const over = b.budget && b.spent > b.budget;
  return h`<div class="bud"><div class="bud-top"><span><i style="background:${b.color || "#999"}"></i>${esc(b.name)}${b.kind === "bill" ? ` <em>fixe</em>` : ""}</span>
    <b class="num ${over ? "neg" : ""}">${eur(b.spent)}${b.budget ? ` <span class="muted">/ ${eur(b.budget)}</span>` : ""}</b></div>
    ${b.budget ? `<div class="bud-bar ${over ? "over" : ""}"><i style="width:${pct}%;background:${b.color || "#6366f1"}"></i>${proj > pct ? `<s style="left:${proj}%"></s>` : ""}</div>` : ""}</div>`;
}
function goalHtml(g) {
  return h`<div class="goal"><div class="bud-top"><span><i style="background:${g.color || "#6366f1"}"></i>${esc(g.name)}</span><b class="num">${eur(g.current)} <span class="muted">/ ${eur(g.target)}</span></b></div>
    <div class="bud-bar"><i style="width:${g.pct || 0}%;background:${g.color || "#6366f1"}"></i></div>
    <div class="small muted">${g.pct != null ? g.pct + " %" : ""}${g.monthly_needed ? ` · ${eur(g.monthly_needed)} par mois pour y être le ${fmtDay(g.deadline)}` : g.deadline ? ` · échéance ${fmtDay(g.deadline)}` : ""}</div></div>`;
}

// ================================================================ TRANSACTIONS
async function renderFinTx(view) {
  const D = await finData(true);
  if (!D.settings.setup) return finSetup(view);
  const ym = state.finMonth || D.today_month;
  const M = await api(`/api/fin/month/${ym}`);
  const f = state.finFilter || {};
  let txs = M.transactions;
  if (f.q) txs = txs.filter((t) => (t.label || "").toLowerCase().includes(f.q.toLowerCase()) || (t.note || "").toLowerCase().includes(f.q.toLowerCase()));
  if (f.acc) txs = txs.filter((t) => t.account === f.acc || t.to_account === f.acc);
  if (f.cat) txs = txs.filter((t) => (f.cat === "_none" ? !t.category && !t.to_account : t.category === f.cat));
  const byDay = {};
  txs.forEach((t) => (byDay[t.date] ||= []).push(t));
  view.innerHTML = h`
    <div class="fin-top">${monthNav(ym, D.today_month)}${finHeadActions()}</div>
    <div class="card">
      <div class="tx-filters">
        <input id="tf-q" placeholder="Rechercher un libellé…" value="${esc(f.q || "")}">
        <select id="tf-acc"><option value="">Tous les comptes</option>${D.accounts.filter((a) => !a.archived).map((a) => `<option value="${a.id}" ${f.acc === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select>
        <select id="tf-cat"><option value="">Toutes les catégories</option><option value="_none" ${f.cat === "_none" ? "selected" : ""}>Sans catégorie (${M.uncategorized})</option>${catOptions(D, f.cat)}</select>
        <button class="btn sm" id="tf-import">Importer un relevé</button><a class="btn sm" href="/api/fin/export.csv" download>Exporter</a>
      </div>
      <div class="tx-sum small"><span>${txs.length} opération${txs.length > 1 ? "s" : ""}</span><span>Revenus ${eur(M.income)}</span><span>Dépenses ${eur(M.spent)}</span><span>Épargne ${eur(M.saved)}</span></div>
      ${Object.keys(byDay).length ? Object.entries(byDay).map(([d, ts]) => h`<div class="tx-day"><div class="tx-day-h"><span>${fmtDay(d)}</span><span class="num">${eurS(ts.filter((t) => !t.to_account).reduce((a, t) => a + t.amount, 0), 2)}</span></div>
        ${ts.map((t) => txRow(t, D)).join("")}</div>`).join("") : `<div class="empty">Aucune opération${f.q || f.acc || f.cat ? " avec ces filtres" : " ce mois-ci"}.<br><span class="small">Ajoute-en une avec « + Transaction » ou importe le relevé CSV de ta banque.</span></div>`}
    </div>`;
  bindMonthNav(view, D.today_month);
  bindHeadActions(view);
  const setF = (k, v) => { state.finFilter = { ...(state.finFilter || {}), [k]: v }; render(); };
  let qt; $("#tf-q", view).oninput = (e) => { clearTimeout(qt); qt = setTimeout(() => { setF("q", e.target.value); }, 350); };
  $("#tf-acc", view).onchange = (e) => setF("acc", e.target.value);
  $("#tf-cat", view).onchange = (e) => setF("cat", e.target.value);
  $("#tf-import", view).onclick = () => importDialog(D);
  $$(".tx[data-id]", view).forEach((r) => (r.onclick = (e) => { if (e.target.closest(".tx-qcat")) return; editTx(M.transactions.find((t) => t.id === r.dataset.id)); }));
  $$(".tx-qcat", view).forEach((s) => (s.onchange = async () => {
    const t = M.transactions.find((x) => x.id === s.dataset.id);
    try { await api("/api/fin/transactions", { method: "POST", body: { id: t.id, category: s.value, remember: true } }); finInvalidate(); toast("Classé (et retenu pour les prochains)"); render(); } catch (e) { toast(e.message, true); }
  }));
  const qi = $("#tf-q", view); if (f.q) { qi.focus(); qi.setSelectionRange(qi.value.length, qi.value.length); }
}
function catOptions(D, sel, kind) {
  const ks = Array.isArray(kind) ? kind : kind ? [kind] : null;
  const groups = Object.entries(D.kinds).filter(([k]) => !ks || ks.includes(k));
  return groups.map(([k, l]) => `<optgroup label="${l}">${D.categories.filter((c) => c.kind === k).map((c) => `<option value="${c.id}" ${sel === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</optgroup>`).join("");
}
function txRow(t, D) {
  const c = catOf(D, t.category), a = accOf(D, t.account), to = accOf(D, t.to_account);
  const isT = !!t.to_account;
  return h`<div class="tx" data-id="${t.id}"><span class="tx-dot" style="background:${isT ? "#94a3b8" : c?.color || "#cbd5e1"}">${isT ? "⇄" : ""}</span>
    <div class="tx-main"><div class="tx-lab ellipsis">${esc(t.label || (isT ? "Virement" : "Opération"))}${t.recurring_id ? ` <em class="tag">auto</em>` : ""}${t.imported ? ` <em class="tag">importé</em>` : ""}</div>
      <div class="tx-meta">${isT ? `${esc(a?.name || "?")} → ${esc(to?.name || "?")}` : c ? esc(c.name) : `<select class="tx-qcat" data-id="${t.id}"><option value="">Choisir une catégorie…</option>${catOptions(D, null, t.amount > 0 ? null : null)}</select>`}${!isT && a ? ` · ${esc(a.name)}` : ""}${t.note ? ` · ${esc(t.note)}` : ""}</div></div>
    <b class="num tx-amt ${isT ? "" : t.amount > 0 ? "pos" : ""}">${isT ? eur(Math.abs(t.amount), 2) : eurS(t.amount, 2)}</b></div>`;
}

function editTx(t) {
  const D = state.fin;
  if (!D) { finData().then(() => editTx(t)); return; }
  const isNew = !t.id;
  let mode = t.to_account ? "transfer" : (t.amount > 0 ? "income" : "expense");
  const draw = (el) => {
    $("#te-cat-wrap", el).innerHTML = mode === "transfer" ? `<label class="f">Vers le compte<select id="te-to">${D.accounts.filter((a) => !a.archived).map((a) => `<option value="${a.id}" ${t.to_account === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>`
      : `<label class="f">Catégorie<select id="te-cat"><option value="">—</option>${catOptions(D, t.category, mode === "income" ? null : ["bill", "expense"])}</select></label>`;
    $$("#te-mode button", el).forEach((b) => b.classList.toggle("on", b.dataset.m === mode));
  };
  openModal(h`<h3>${isNew ? "Nouvelle opération" : "Modifier l'opération"}</h3>
    <div class="seg" id="te-mode" style="margin:10px 0 14px"><button data-m="expense">Dépense</button><button data-m="income">Revenu / remboursement</button><button data-m="transfer">Virement</button></div>
    <div class="grid g2">
      <label class="f">Montant (€)<input id="te-amt" type="number" step="0.01" inputmode="decimal" value="${t.amount != null ? Math.abs(t.amount) : ""}" placeholder="0,00"></label>
      <label class="f">Date<input id="te-date" type="date" value="${t.date || today()}"></label>
      <label class="f">Libellé<input id="te-lab" value="${esc(t.label || "")}" placeholder="Carrefour, resto, salaire…"></label>
      <label class="f">Compte<select id="te-acc">${D.accounts.filter((a) => !a.archived).map((a) => `<option value="${a.id}" ${(t.account || D.accounts[0]?.id) === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>
      <div id="te-cat-wrap"></div>
      <label class="f">Note<input id="te-note" value="${esc(t.note || "")}" placeholder="facultatif"></label>
    </div>
    <label class="check"><input type="checkbox" id="te-rem"> Toujours classer ce libellé dans cette catégorie</label>
    <div class="btns"><button class="btn primary" id="te-save">Enregistrer</button>${isNew ? "" : `<button class="btn danger" id="te-del">Supprimer</button>`}</div>`, (el) => {
    draw(el);
    $$("#te-mode button", el).forEach((b) => (b.onclick = () => { mode = b.dataset.m; draw(el); }));
    setTimeout(() => $("#te-amt", el).focus(), 50);
    $("#te-save", el).onclick = async () => {
      const amt = Math.abs(Number(String($("#te-amt", el).value).replace(",", ".")) || 0);
      if (!amt) { toast("Indique un montant", true); return; }
      const body = { id: t.id, date: $("#te-date", el).value, label: $("#te-lab", el).value, account: $("#te-acc", el).value, note: $("#te-note", el).value,
        amount: mode === "expense" ? -amt : amt, to_account: mode === "transfer" ? $("#te-to", el).value : null,
        category: mode === "transfer" ? null : $("#te-cat", el)?.value || null, remember: $("#te-rem", el).checked };
      try { await api("/api/fin/transactions", { method: "POST", body }); finInvalidate(); closeModal(); toast("Enregistré"); render(); } catch (e) { toast(e.message, true); }
    };
    const del = $("#te-del", el);
    if (del) del.onclick = async () => { if (!confirm("Supprimer cette opération ?")) return; await api(`/api/fin/transactions/${t.id}`, { method: "DELETE" }); finInvalidate(); closeModal(); render(); };
  });
}

// ---------------------------------------------------------------- import CSV
function importDialog(D) {
  openModal(h`<h3>Importer un relevé bancaire</h3>
    <p class="small muted">Dans l'espace client de ta banque, exporte tes opérations au format <b>CSV</b> (ou Excel → « enregistrer en CSV »). Les doublons sont détectés, et les catégories proposées automatiquement : elles s'améliorent à chaque correction.</p>
    <label class="f">Compte concerné<select id="im-acc">${D.accounts.filter((a) => !a.archived).map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select></label>
    <label class="f">Fichier CSV<input id="im-file" type="file" accept=".csv,text/csv,text/plain"></label>
    <div id="im-prev"></div>`, (el) => {
    $("#im-file", el).onchange = async (e) => {
      const file = e.target.files[0]; if (!file) return;
      const buf = await file.arrayBuffer();
      let text = new TextDecoder("utf-8").decode(buf);
      if (text.includes("�")) text = new TextDecoder("windows-1252").decode(buf);
      try {
        const P = await api("/api/fin/import/preview", { method: "POST", body: { text, account: $("#im-acc", el).value } });
        drawPrev(el, P.rows);
      } catch (err) { $("#im-prev", el).innerHTML = `<div class="warn-line">${esc(err.message)}</div>`; }
    };
  });
  function drawPrev(el, rows) {
    const nNew = rows.filter((r) => !r.duplicate).length;
    $("#im-prev", el).innerHTML = h`<div class="small" style="margin:8px 0"><b>${rows.length}</b> opérations lues · <b>${nNew}</b> nouvelles · ${rows.length - nNew} déjà présentes</div>
      <div class="im-list">${rows.map((r, i) => `<div class="im-row ${r.duplicate ? "dup" : ""}"><input type="checkbox" data-i="${i}" ${r.duplicate ? "" : "checked"}>
        <span class="muted small">${fmtDay(r.date)}</span><span class="ellipsis" style="flex:1;min-width:0">${esc(r.label)}</span>
        <select data-c="${i}"><option value="">—</option>${catOptions(D, r.category)}</select><b class="num ${r.amount > 0 ? "pos" : ""}">${eurS(r.amount, 2)}</b></div>`).join("")}</div>
      <div class="btns"><button class="btn primary" id="im-go">Importer ${nNew} opération${nNew > 1 ? "s" : ""}</button></div>`;
    $("#im-go", el).onclick = async () => {
      const out = rows.map((r, i) => ({ ...r, skip: !$(`[data-i="${i}"]`, el).checked, category: $(`[data-c="${i}"]`, el).value || null }));
      try {
        const R = await api("/api/fin/import/commit", { method: "POST", body: { account: $("#im-acc", el).value, rows: out } });
        finInvalidate(); closeModal(); toast(`${R.added} opérations importées`); render();
      } catch (err) { toast(err.message, true); }
    };
  }
}

// ================================================================ BUDGET
async function renderFinBudget(view) {
  const D = await finData(true);
  if (!D.settings.setup) return finSetup(view);
  const ym = state.finMonth || D.today_month;
  const M = await api(`/api/fin/month/${ym}`);
  const spentOf = (id) => (M.budgets.find((b) => b.id === id) || {}).spent || 0;
  const projOf = (id) => (M.budgets.find((b) => b.id === id) || {}).projected || 0;
  const group = (kind, title) => {
    const cs = D.categories.filter((c) => c.kind === kind);
    const totB = cs.reduce((a, c) => a + (c.budget || 0), 0), totS = cs.reduce((a, c) => a + spentOf(c.id), 0);
    return h`<div class="card section"><div class="row between"><h2 style="margin:0">${title}</h2><span class="small num">${eur(totS)} <span class="muted">/ ${eur(totB)}</span></span></div>
      ${cs.map((c) => { const s = spentOf(c.id); const pct = c.budget ? Math.min(100, (s / c.budget) * 100) : 0; const pr = c.budget ? Math.min(100, (projOf(c.id) / c.budget) * 100) : 0; const over = c.budget && s > c.budget;
        return h`<div class="bud editable" data-cid="${c.id}"><div class="bud-top"><span><i style="background:${c.color}"></i>${esc(c.name)}</span>
          <span class="num"><b class="${over ? "neg" : ""}">${eur(s)}</b> <span class="muted">/</span> <input class="bud-in" type="number" step="10" value="${c.budget || ""}" placeholder="budget" data-bud="${c.id}"> €</span></div>
          ${c.budget ? `<div class="bud-bar ${over ? "over" : ""}"><i style="width:${pct}%;background:${c.color}"></i>${pr > pct && kind === "expense" ? `<s style="left:${pr}%"></s>` : ""}</div>` : ""}</div>`; }).join("")}</div>`;
  };
  const totalB = D.categories.filter((c) => c.kind !== "income").reduce((a, c) => a + (c.budget || 0), 0);
  view.innerHTML = h`
    <div class="fin-top">${monthNav(ym, D.today_month)}${finHeadActions()}</div>
    <div class="grid g4">
      ${tile("Revenus", eur(M.income), `du ${fmtDay(M.from)} au ${fmtDay(M.to)}`, "#10b981")}
      ${tile("Dépensé", eur(M.spent), `budget total ${eur(totalB)}`, "#6366f1")}
      ${tile("Reste (dépenses variables)", M.var_left != null ? eur(M.var_left) : "—", M.per_day_left ? `${eur(M.per_day_left)} par jour` : "", M.var_left != null && M.var_left < 0 ? "var(--bad)" : null)}
      ${tile("Prévu pour l'épargne", eur(M.income - totalB), M.income ? `revenus − budget` : "", "#f59e0b")}
    </div>
    <p class="small muted" style="margin:12px 2px 0">Tape un montant pour fixer le budget d'une catégorie (il vaut pour tous les mois). Le petit trait indique où tu finiras le mois au rythme actuel.</p>
    <div class="cols"><div>${group("expense", "Dépenses variables")}</div><div>${group("bill", "Charges fixes")}
      <div class="card section"><div class="row between"><h2 style="margin:0">Abonnements & prélèvements</h2><a href="#" class="small" id="fb-rec">Gérer →</a></div>
        <p class="small muted" style="margin:6px 0 0">Loyer, électricité, mobile, Spotify, salle… : saisis-les une fois, ils s'ajoutent tout seuls chaque mois.</p></div>
      <div class="card section"><div class="row between"><h2 style="margin:0">Catégories</h2><button class="btn sm" id="fb-cat">+ Catégorie</button></div>
        <div class="cat-chips">${D.categories.map((c) => `<button class="cat-chip" data-cat="${c.id}"><i style="background:${c.color}"></i>${esc(c.name)}<em>${D.kinds[c.kind]}</em></button>`).join("")}</div></div>
    </div></div>`;
  bindMonthNav(view, D.today_month);
  bindHeadActions(view);
  $$("[data-bud]", view).forEach((inp) => (inp.onchange = async () => {
    try { await api("/api/fin/categories", { method: "POST", body: { id: inp.dataset.bud, budget: inp.value || 0 } }); finInvalidate(); render(); } catch (e) { toast(e.message, true); }
  }));
  $("#fb-rec", view).onclick = (e) => { e.preventDefault(); setView("f-recurring"); };
  $("#fb-cat", view).onclick = () => editCat({ kind: "expense" });
  $$("[data-cat]", view).forEach((b) => (b.onclick = () => editCat(D.categories.find((c) => c.id === b.dataset.cat))));
}
function editCat(c) {
  const D = state.fin;
  openModal(h`<h3>${c.id ? "Catégorie" : "Nouvelle catégorie"}</h3><div class="grid g2">
    <label class="f">Nom<input id="ce-name" value="${esc(c.name || "")}"></label>
    <label class="f">Type<select id="ce-kind">${Object.entries(D.kinds).map(([k, l]) => `<option value="${k}" ${c.kind === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label class="f">Budget mensuel (€)<input id="ce-bud" type="number" step="10" value="${c.budget || ""}"></label>
    <label class="f">Couleur<input id="ce-col" type="color" value="${c.color || "#6366f1"}"></label></div>
    <div class="btns"><button class="btn primary" id="ce-save">Enregistrer</button>${c.id ? `<button class="btn danger" id="ce-del">Supprimer</button>` : ""}</div>`, (el) => {
    $("#ce-save", el).onclick = async () => { await api("/api/fin/categories", { method: "POST", body: { id: c.id, name: $("#ce-name", el).value, kind: $("#ce-kind", el).value, budget: $("#ce-bud", el).value || 0, color: $("#ce-col", el).value } }); finInvalidate(); closeModal(); render(); };
    const d = $("#ce-del", el); if (d) d.onclick = async () => { if (!confirm("Supprimer la catégorie ? Les opérations resteront, sans catégorie.")) return; await api(`/api/fin/categories/${c.id}`, { method: "DELETE" }); finInvalidate(); closeModal(); render(); };
  });
}

// ================================================================ ABONNEMENTS
async function renderFinRecurring(view) {
  const D = await finData(true);
  if (!D.settings.setup) return finSetup(view);
  const act = D.recurring.filter((r) => r.active !== false);
  const monthly = act.filter((r) => !r.to_account && r.amount < 0).reduce((a, r) => a + Math.abs(r.amount) / (r.freq === "year" ? 12 : 1), 0);
  const income = act.filter((r) => !r.to_account && r.amount > 0).reduce((a, r) => a + r.amount, 0);
  const savings = act.filter((r) => r.to_account).reduce((a, r) => a + Math.abs(r.amount), 0);
  const presets = [["Loyer", -700, "Loyer", 5], ["Électricité / gaz", -55, "Énergie (Engie)", 10], ["Forfait mobile", -20, "Mobile & internet", 15], ["Spotify", -12.14, "Abonnements", 20], ["Salle de sport", -35, "Salle de sport", 1], ["Salaire", 2200, "Salaire", 28]];
  view.innerHTML = h`
    <div class="fin-top"><div></div>${finHeadActions()}</div>
    <div class="grid g3">
      ${tile("Charges fixes", eur(monthly, 2), `${eur(monthly * 12)} par an`, "#6366f1")}
      ${tile("Revenus réguliers", eur(income), "par mois", "#10b981")}
      ${tile("Épargne automatique", eur(savings), "virements programmés", "#f59e0b")}
    </div>
    <div class="card section"><div class="row between wrap"><h2 style="margin:0">Opérations récurrentes</h2><button class="btn sm primary" id="fr-add">+ Ajouter</button></div>
      <p class="small muted" style="margin:6px 0 10px">Chaque mois, le jour venu, l'opération est ajoutée automatiquement (marquée « auto »). Tu peux toujours la modifier ensuite.</p>
      ${D.recurring.length ? D.recurring.sort((a, b) => (a.day || 0) - (b.day || 0)).map((r) => { const c = catOf(D, r.category), a = accOf(D, r.account), to = accOf(D, r.to_account);
        return h`<div class="tx rec ${r.active === false ? "off" : ""}" data-rid="${r.id}"><span class="tx-dot" style="background:${r.to_account ? "#94a3b8" : c?.color || "#cbd5e1"}">${r.to_account ? "⇄" : ""}</span>
          <div class="tx-main"><div class="tx-lab">${esc(r.label)}</div><div class="tx-meta">le ${r.day} ${r.freq === "year" ? `de chaque année (${MONTH_NAMES[Number((r.start || "2026-01").slice(5, 7)) - 1]})` : "du mois"} · ${r.to_account ? `${esc(a?.name || "")} → ${esc(to?.name || "")}` : `${esc(c?.name || "sans catégorie")} · ${esc(a?.name || "")}`}${r.active === false ? " · en pause" : ""}</div></div>
          <b class="num tx-amt ${r.amount > 0 && !r.to_account ? "pos" : ""}">${r.to_account ? eur(Math.abs(r.amount), 2) : eurS(r.amount, 2)}</b></div>`; }).join("")
        : `<div class="empty small">Rien pour l'instant. Pour aller vite :</div><div class="cat-chips">${presets.map((p, i) => `<button class="cat-chip" data-pre="${i}">+ ${p[0]}</button>`).join("")}</div>`}
    </div>`;
  bindHeadActions(view);
  $("#fr-add", view).onclick = () => editRec({ day: 1, amount: null, active: true });
  $$("[data-rid]", view).forEach((r) => (r.onclick = () => editRec(D.recurring.find((x) => x.id === r.dataset.rid))));
  $$("[data-pre]", view).forEach((b) => (b.onclick = () => { const p = presets[Number(b.dataset.pre)]; editRec({ label: p[0], amount: p[1], category: D.categories.find((c) => c.name === p[2])?.id, day: p[3], active: true }); }));
}
function editRec(r) {
  const D = state.fin;
  let mode = r.to_account ? "transfer" : (r.amount > 0 ? "income" : "expense");
  openModal(h`<h3>${r.id ? "Opération récurrente" : "Nouvelle opération récurrente"}</h3>
    <div class="seg" id="re-mode" style="margin:10px 0 14px"><button data-m="expense">Prélèvement</button><button data-m="income">Revenu</button><button data-m="transfer">Virement d'épargne</button></div>
    <div class="grid g2">
      <label class="f">Libellé<input id="re-lab" value="${esc(r.label || "")}"></label>
      <label class="f">Montant (€)<input id="re-amt" type="number" step="0.01" value="${r.amount != null ? Math.abs(r.amount) : ""}"></label>
      <label class="f">Jour du mois<input id="re-day" type="number" min="1" max="31" value="${r.day || 1}"></label>
      <label class="f">Fréquence<select id="re-freq"><option value="month">Tous les mois</option><option value="year" ${r.freq === "year" ? "selected" : ""}>Tous les ans</option></select></label>
      <label class="f">Compte<select id="re-acc">${D.accounts.filter((a) => !a.archived).map((a) => `<option value="${a.id}" ${(r.account || D.accounts[0]?.id) === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>
      <div id="re-x"></div>
      <label class="f">À partir du<input id="re-start" type="date" value="${r.start || today()}"></label>
      <label class="f">Jusqu'au (facultatif)<input id="re-end" type="date" value="${r.end || ""}"></label>
    </div>
    <label class="check"><input type="checkbox" id="re-act" ${r.active !== false ? "checked" : ""}> Active</label>
    <div class="btns"><button class="btn primary" id="re-save">Enregistrer</button>${r.id ? `<button class="btn danger" id="re-del">Supprimer</button>` : ""}</div>`, (el) => {
    const draw = () => {
      $("#re-x", el).innerHTML = mode === "transfer" ? `<label class="f">Vers le compte<select id="re-to">${D.accounts.filter((a) => !a.archived).map((a) => `<option value="${a.id}" ${r.to_account === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>`
        : `<label class="f">Catégorie<select id="re-cat"><option value="">—</option>${catOptions(D, r.category)}</select></label>`;
      $$("#re-mode button", el).forEach((b) => b.classList.toggle("on", b.dataset.m === mode));
    };
    draw();
    $$("#re-mode button", el).forEach((b) => (b.onclick = () => { mode = b.dataset.m; draw(); }));
    $("#re-save", el).onclick = async () => {
      const amt = Math.abs(Number($("#re-amt", el).value) || 0);
      if (!amt) { toast("Indique un montant", true); return; }
      try {
        await api("/api/fin/recurring", { method: "POST", body: { id: r.id, label: $("#re-lab", el).value || "Opération", amount: mode === "expense" ? -amt : amt, day: $("#re-day", el).value,
          freq: $("#re-freq", el).value, account: $("#re-acc", el).value, to_account: mode === "transfer" ? $("#re-to", el).value : null, category: mode === "transfer" ? null : $("#re-cat", el).value || null,
          start: $("#re-start", el).value, end: $("#re-end", el).value || null, active: $("#re-act", el).checked } });
        finInvalidate(); closeModal(); toast("Enregistré"); render();
      } catch (e) { toast(e.message, true); }
    };
    const d = $("#re-del", el); if (d) d.onclick = async () => { if (!confirm("Supprimer ? Les opérations déjà créées restent.")) return; await api(`/api/fin/recurring/${r.id}`, { method: "DELETE" }); finInvalidate(); closeModal(); render(); };
  });
}

// ================================================================ PATRIMOINE
async function renderFinAccounts(view) {
  const D = await finData(true);
  if (!D.settings.setup) return finSetup(view);
  const O = await api("/api/fin/overview");
  const groups = {};
  O.accounts.forEach((a) => (groups[a.type] ||= []).push(a));
  view.innerHTML = h`
    <div class="fin-top"><div></div>${finHeadActions()}</div>
    <div class="cols"><div>
      <div class="card fin-hero nw"><div class="fh-label">Patrimoine net</div><div class="fh-big num">${eur(O.net_worth)}</div>
        <div class="fh-sub">dont ${eur(O.liquid)} disponible · ${O.months_cover != null ? String(O.months_cover).replace(".", ",") + " mois de dépenses de côté" : ""}</div>
        <div class="chart-box" style="height:170px;margin-top:12px"><canvas id="c-fa-nw"></canvas></div></div>
      <div class="card section"><h2>Répartition</h2><div class="donut-wrap"><div class="chart-box" style="height:180px;width:180px"><canvas id="c-fa-split"></canvas></div>
        <div class="donut-legend">${Object.entries(groups).map(([t, as]) => `<div><i style="background:${as[0].color}"></i><span>${esc(D.account_types[t])}</span><b class="num">${eur(as.reduce((x, a) => x + a.balance, 0))}</b></div>`).join("")}</div></div></div>
    </div><div>
      <div class="card"><div class="row between"><h2 style="margin:0">Comptes</h2><button class="btn sm" id="fa-add">+ Compte</button></div>
        ${Object.entries(groups).map(([t, as]) => h`<div class="acc-group"><div class="acc-gh">${esc(D.account_types[t])}</div>${as.map((a) => h`<div class="acc" data-aid="${a.id}">
          <span class="tx-dot" style="background:${a.color}"></span><div class="tx-main"><div class="tx-lab">${esc(a.name)}</div><div class="tx-meta">${["placement", "crypto", "retraite"].includes(a.type) ? "valeur mise à jour à la main" : "calculé avec tes opérations"}</div></div>
          <b class="num">${eur(a.balance, 2)}</b><button class="btn sm" data-val="${a.id}">Mettre à jour</button></div>`).join("")}</div>`).join("")}
      </div>
      <div class="card section"><div class="row between"><h2 style="margin:0">Objectifs d'épargne</h2><button class="btn sm" id="fa-goal">+ Objectif</button></div>
        ${O.goals.length ? O.goals.map((g) => `<div data-gid="${g.id}" style="cursor:pointer">${goalHtml(g)}</div>`).join("") : `<p class="small muted">Fonds d'urgence (3 à 6 mois de dépenses), matériel trail, voyage, apport… Relie un objectif à un compte pour qu'il avance tout seul.</p>`}</div>
    </div></div>`;
  bindHeadActions(view);
  $("#fa-add", view).onclick = () => editAcc({ type: "epargne" });
  $$("[data-aid]", view).forEach((r) => (r.onclick = (e) => { if (e.target.closest("[data-val]")) return; editAcc(D.accounts.find((a) => a.id === r.dataset.aid)); }));
  $$("[data-val]", view).forEach((b) => (b.onclick = () => {
    const a = O.accounts.find((x) => x.id === b.dataset.val);
    openModal(h`<h3>Solde de « ${esc(a.name)} »</h3><p class="small muted">Saisis le solde ou la valeur actuelle (relevé, appli de la banque ou du courtier). L'app recale le compte à cette date.</p>
      <div class="grid g2"><label class="f">Valeur (€)<input id="va-v" type="number" step="0.01" value="${a.balance}"></label><label class="f">Date<input id="va-d" type="date" value="${today()}"></label></div>
      <div class="btns"><button class="btn primary" id="va-s">Enregistrer</button></div>`, (el) => {
      $("#va-s", el).onclick = async () => { await api("/api/fin/valuations", { method: "POST", body: { account: a.id, value: $("#va-v", el).value, date: $("#va-d", el).value } }); finInvalidate(); closeModal(); toast("Solde mis à jour"); render(); };
    });
  }));
  $("#fa-goal", view).onclick = () => editGoal({});
  $$("[data-gid]", view).forEach((g) => (g.onclick = () => editGoal(D.goals.find((x) => x.id === g.dataset.gid))));
  if (typeof Chart === "undefined") return;
  chartDefaults();
  mkChart($("#c-fa-nw", view), { type: "line", data: { labels: O.net_worth_history.map((x) => monthLabel(x.month)), datasets: [{ data: O.net_worth_history.map((x) => x.value), borderColor: "#6366f1", backgroundColor: "rgba(99,102,241,.12)", fill: true, pointRadius: 2, tension: 0.35 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${Math.round(c.raw).toLocaleString("fr-FR")} €` } } }, scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } } } } });
  const gs = Object.entries(groups);
  mkChart($("#c-fa-split", view), { type: "doughnut", data: { labels: gs.map(([t]) => D.account_types[t]), datasets: [{ data: gs.map(([, as]) => Math.max(0, as.reduce((x, a) => x + a.balance, 0))), backgroundColor: gs.map(([, as]) => as[0].color), borderWidth: 0 }] },
    options: { cutout: "66%", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.label} : ${Math.round(c.raw).toLocaleString("fr-FR")} €` } } } } });
}
function editAcc(a) {
  const D = state.fin;
  openModal(h`<h3>${a.id ? "Compte" : "Nouveau compte"}</h3><div class="grid g2">
    <label class="f">Nom<input id="ae-n" value="${esc(a.name || "")}"></label>
    <label class="f">Type<select id="ae-t">${Object.entries(D.account_types).map(([k, l]) => `<option value="${k}" ${a.type === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label class="f">Solde de départ (€)<input id="ae-i" type="number" step="0.01" value="${a.initial ?? ""}"></label>
    <label class="f">À la date du<input id="ae-d" type="date" value="${a.initial_date || today()}"></label>
    <label class="f">Couleur<input id="ae-c" type="color" value="${a.color || "#6366f1"}"></label></div>
    <label class="check"><input type="checkbox" id="ae-ar" ${a.archived ? "checked" : ""}> Compte clôturé (archivé)</label>
    <div class="btns"><button class="btn primary" id="ae-s">Enregistrer</button>${a.id ? `<button class="btn danger" id="ae-del">Supprimer</button>` : ""}</div>`, (el) => {
    $("#ae-s", el).onclick = async () => { await api("/api/fin/accounts", { method: "POST", body: { id: a.id, name: $("#ae-n", el).value || "Compte", type: $("#ae-t", el).value, initial: $("#ae-i", el).value || 0, initial_date: $("#ae-d", el).value, color: $("#ae-c", el).value, archived: $("#ae-ar", el).checked } }); finInvalidate(); closeModal(); render(); };
    const d = $("#ae-del", el); if (d) d.onclick = async () => { if (!confirm("Supprimer ce compte ? Ses opérations resteront mais ne seront plus rattachées.")) return; await api(`/api/fin/accounts/${a.id}`, { method: "DELETE" }); finInvalidate(); closeModal(); render(); };
  });
}
function editGoal(g) {
  const D = state.fin;
  openModal(h`<h3>${g.id ? "Objectif" : "Nouvel objectif"}</h3><div class="grid g2">
    <label class="f">Nom<input id="ge-n" value="${esc(g.name || "")}" placeholder="Fonds d'urgence, matériel trail…"></label>
    <label class="f">Montant visé (€)<input id="ge-t" type="number" step="10" value="${g.target || ""}"></label>
    <label class="f">Relié au compte<select id="ge-a"><option value="">Aucun (montant saisi)</option>${D.accounts.map((a) => `<option value="${a.id}" ${g.account === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>
    <label class="f">Déjà épargné (si aucun compte)<input id="ge-s" type="number" step="10" value="${g.saved || ""}"></label>
    <label class="f">Échéance<input id="ge-d" type="date" value="${g.deadline || ""}"></label>
    <label class="f">Couleur<input id="ge-c" type="color" value="${g.color || "#10b981"}"></label></div>
    <div class="btns"><button class="btn primary" id="ge-ok">Enregistrer</button>${g.id ? `<button class="btn danger" id="ge-del">Supprimer</button>` : ""}</div>`, (el) => {
    $("#ge-ok", el).onclick = async () => { await api("/api/fin/goals", { method: "POST", body: { id: g.id, name: $("#ge-n", el).value || "Objectif", target: $("#ge-t", el).value, account: $("#ge-a", el).value || null, saved: $("#ge-s", el).value || 0, deadline: $("#ge-d", el).value || null, color: $("#ge-c", el).value } }); finInvalidate(); closeModal(); render(); };
    const d = $("#ge-del", el); if (d) d.onclick = async () => { await api(`/api/fin/goals/${g.id}`, { method: "DELETE" }); finInvalidate(); closeModal(); render(); };
  });
}

// ================================================================ ANALYSE
async function renderFinAnalysis(view) {
  const D = await finData(true);
  if (!D.settings.setup) return finSetup(view);
  const year = state.finYear || new Date().getFullYear();
  const A = await api(`/api/fin/analysis/${year}`);
  const maxCell = Math.max(1, ...A.grid.flatMap((g) => g.values));
  view.innerHTML = h`
    <div class="fin-top"><div class="fin-month"><button class="icon-btn" data-fy="-1"><svg viewBox="0 0 24 24"><path d="m15 6-6 6 6 6"/></svg></button><div><b>${year}</b><span>année</span></div>
      <button class="icon-btn" data-fy="1" ${year >= new Date().getFullYear() ? "disabled" : ""}><svg viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg></button></div>${finHeadActions()}</div>
    <div class="grid g4">
      ${tile("Revenus", eur(A.income), "sur l'année", "#10b981")}
      ${tile("Dépenses", eur(A.spent), `${eur(A.spent / Math.max(1, A.summaries.filter((s) => s.n).length))} par mois en moyenne`, "#6366f1")}
      ${tile("Épargné", eur(A.saved), "virements vers l'épargne", "#f59e0b")}
      ${tile("Taux d'épargne", A.savings_rate != null ? A.savings_rate + " %" : "—", "revenus − dépenses")}
    </div>
    <div class="card section"><h2>Mois par mois</h2><div class="chart-box" style="height:240px"><canvas id="c-an-m"></canvas></div></div>
    <div class="card section"><h2>Par catégorie</h2>
      <div class="table-scroll"><table class="heat"><thead><tr><th>Catégorie</th>${A.months.map((m) => `<th class="r">${MONTHS[Number(m.slice(5)) - 1]}</th>`).join("")}<th class="r">Total</th><th class="r">Moy.</th></tr></thead>
      <tbody>${A.grid.map((g) => `<tr><td class="nowrap"><i class="hdot" style="background:${g.color}"></i>${esc(g.name)}</td>${g.values.map((v) => `<td class="r num" style="background:${v ? `color-mix(in srgb, ${g.color} ${Math.round(8 + (v / maxCell) * 55)}%, transparent)` : "transparent"}">${v ? `<span class="money">${Math.round(v)}</span>` : ""}</td>`).join("")}<td class="r num"><b>${eur(g.total)}</b></td><td class="r num muted">${eur(g.avg)}</td></tr>`).join("") || `<tr><td colspan="15" class="muted">Aucune dépense cette année.</td></tr>`}</tbody></table></div></div>
    <div class="cols section"><div><div class="card"><h2>Où tu dépenses le plus</h2>${A.merchants.map((m, i) => `<div class="fin-line"><span class="muted small num" style="width:18px">${i + 1}</span><span style="flex:1;text-transform:capitalize" class="ellipsis">${esc(m[0])}</span><span class="small muted">${m[2]} fois</span><b class="num">${eur(m[1])}</b></div>`).join("") || `<div class="muted small">—</div>`}</div></div>
      <div><div class="card"><h2>Répartition de l'année</h2><div class="chart-box" style="height:260px"><canvas id="c-an-d"></canvas></div></div></div></div>`;
  bindHeadActions(view);
  $$("[data-fy]", view).forEach((b) => (b.onclick = () => { state.finYear = year + Number(b.dataset.fy); render(); }));
  if (typeof Chart === "undefined") return;
  chartDefaults();
  const S = A.summaries;
  mkChart($("#c-an-m", view), { data: { labels: S.map((s) => MONTHS[Number(s.month.slice(5)) - 1]), datasets: [
    { type: "bar", label: "Charges fixes", data: S.map((s) => s.bills), backgroundColor: "#a5b4fc", stack: "d", borderRadius: 3 },
    { type: "bar", label: "Dépenses variables", data: S.map((s) => s.expenses), backgroundColor: "#6366f1", stack: "d", borderRadius: 3 },
    { type: "line", label: "Revenus", data: S.map((s) => s.income), borderColor: "#10b981", backgroundColor: "#10b981", tension: 0.3, pointRadius: 3 },
  ] }, options: { plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${Math.round(c.raw).toLocaleString("fr-FR")} €` } } }, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true } } } });
  const G = A.grid.slice(0, 10);
  if (G.length) mkChart($("#c-an-d", view), { type: "doughnut", data: { labels: G.map((g) => g.name), datasets: [{ data: G.map((g) => Math.max(0, g.total)), backgroundColor: G.map((g) => g.color), borderWidth: 0 }] },
    options: { cutout: "60%", plugins: { legend: { position: "right", labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => `${c.label} : ${Math.round(c.raw).toLocaleString("fr-FR")} €` } } } } });
}
