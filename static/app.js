/* Élan – front (vanilla JS, aucune étape de build) */
"use strict";

// ---------------------------------------------------------------- utilitaires
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const h = (strings, ...vals) => strings.reduce((a, s, i) => a + s + (i < vals.length ? vals[i] ?? "" : ""), "");

const DAYS = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"];
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const parseD = (s) => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const today = () => iso(new Date());
const fmtDay = (s) => { const d = parseD(s); return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const pace = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}` : "—");
const dur = (s) => {
  if (s == null) return "—";
  s = Math.round(s); const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return hh ? `${hh}h${String(mm).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
};
const hms = (s) => { if (!s) return "—"; s = Math.round(s); return `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
const paceToSec = (p) => { if (!p) return null; const [m, s] = String(p).split(":").map(Number); return m * 60 + (s || 0); };
const km = (x, d = 1) => (x == null ? "—" : Number(x).toFixed(d).replace(".", ","));

const ZONE_COLORS = { ULTRA: "#0d9488", EF: "#3b82f6", AM: "#fc5200", SEMI: "#f59e0b", SEUILC: "#db2777", SEUIL: "#e11d48", VMA: "#7c3aed", RECUP: "#94a3b8" };
const TYPES = ["EF", "SL", "AM", "SEUIL", "VMA", "SEMI", "COURSE", "REPOS", "RENFO", "AUTRE"];
const TYPE_LABELS = { EF: "Endurance", SL: "Sortie longue", AM: "Allure marathon", SEUIL: "Seuil", VMA: "VMA", SEMI: "Allure semi", COURSE: "Course", REPOS: "Repos", RENFO: "Renfo", AUTRE: "Autre" };
const STATUS_LABELS = { done: "✓ Fait", partial: "◐ Partiel", missed: "✗ Manqué", upcoming: "", rest: "", today: "Aujourd'hui", extra: "Bonus" };

const TS_PHRASES = [
  ["PRODUCTIVE", "Productif", "var(--good)"], ["PEAKING", "Pic de forme", "var(--good)"], ["MAINTAINING", "Maintien", "var(--info)"],
  ["RECOVERY", "Récupération", "var(--info)"], ["UNPRODUCTIVE", "Improductif", "var(--warn)"], ["OVERREACHING", "Surcharge", "var(--bad)"],
  ["STRAINED", "Sous tension", "var(--bad)"], ["DETRAINING", "Désentraînement", "var(--warn)"], ["NO_STATUS", "Pas de statut", "var(--muted)"],
];
const tsPhrase = (p) => { if (!p) return ["—", "var(--muted)"]; const f = TS_PHRASES.find(([k]) => p.startsWith(k)); return f ? [f[1], f[2]] : [p, "var(--muted)"]; };
const LEVELS = { PRIME: ["Optimale", "var(--good)"], HIGH: ["Élevée", "var(--good)"], MODERATE: ["Modérée", "var(--warn)"], LOW: ["Faible", "var(--bad)"], POOR: ["Très faible", "var(--bad)"] };
const HRV_STATUS = { BALANCED: ["Équilibrée", "var(--good)"], UNBALANCED: ["Déséquilibrée", "var(--warn)"], LOW: ["Basse", "var(--bad)"], POOR: ["Faible", "var(--bad)"] };

// ---------------------------------------------------------------- API
let PIN = (() => { try { return localStorage.getItem("sub3_pin") || ""; } catch { return ""; } })();
if (PIN) document.cookie = `sub3_pin=${PIN}; max-age=31536000; path=/`;
async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", "X-Pin": PIN },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* vide */ }
  if (res.status === 401 && data?.pin_required) { askPin(); throw new Error("PIN requis"); }
  if (res.status === 409 && data?.garmin_disconnected) { state.status.connected = false; updatePill(); showLogin(); throw new Error(data.detail); }
  if (!res.ok) throw new Error(data?.detail || `Erreur ${res.status}`);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), err ? 5000 : 2800);
}

function openModal(html, onMount) {
  $("#modal-body").innerHTML = html;
  $("#modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  onMount && onMount($("#modal-body"));
}
function closeModal() { $("#modal").classList.add("hidden"); document.body.style.overflow = ""; $("#modal-body").innerHTML = ""; }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal" || e.target.closest(".modal-close")) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// ---------------------------------------------------------------- état & navigation
const state = { status: {}, view: "home", plan: null, charts: [], builder: null, actFilter: "run",
  planMode: (() => { try { return localStorage.getItem("sub3_planmode") || "weeks"; } catch { return "weeks"; } })() };

const NAV = () => $$(".side-nav button, #tabs button");
const VIEW_TITLES = { home: "Résumé", plan: "Plan", builder: "Séance", race: "Jour J", nutrition: "Ravitaillement", season: "Saison", "b-today": "Aujourd'hui", "b-log": "Journal", "b-dash": "Bilan", "b-race": "Avant course", "f-home": "Finances", "f-tx": "Opérations", "f-budget": "Budget", "f-recurring": "Abonnements", "f-accounts": "Patrimoine", "f-analysis": "Analyse des dépenses", "m-home": "Vu & Lu", "m-lib": "Bibliothèque", "m-stats": "Bilan Vu & Lu", data: "Analyse", acts: "Activités", coach: "Coach" };
const DAY_NAMES = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const MONTH_NAMES = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
function setHeader(v) {
  const now = new Date();
  const first = (state.status.name || "").split(" ")[0].replace(/\(.*\)/, "").trim();
  const hour = now.getHours();
  const hello = hour < 5 ? "Bonne nuit" : hour < 18 ? "Bonjour" : "Bonsoir";
  $("#page-title").textContent = v === "home" ? `${hello}${first ? " " + first : ""}` : VIEW_TITLES[v] || "Élan";
  $("#page-eyebrow").textContent = v === "home" ? `${DAY_NAMES[now.getDay()]} ${now.getDate()} ${MONTH_NAMES[now.getMonth()]}` : "";
  document.title = `${VIEW_TITLES[v] || "Accueil"} · Élan`;
}
const MOD_OF = (v) => { const s = String(v || ""); return s.startsWith("b-") ? "body" : s.startsWith("f-") ? "fin" : s.startsWith("m-") ? "media" : "running"; };
const MOD_LAST = { running: "elan_last_run", body: "elan_last_body", fin: "elan_last_fin", media: "elan_last_media" };
const MOD_HOME = { running: "home", body: "b-today", fin: "f-home", media: "m-home" };
function applyModule(m) {
  document.body.dataset.mod = m;
  $$("#mod-switch button").forEach((b) => b.classList.toggle("on", b.dataset.mod === m));
}
function setView(v) {
  if (!v) return;
  state.view = v;
  const m = MOD_OF(v);
  applyModule(m);
  try { localStorage.setItem(MOD_LAST[m], v); } catch { /* */ }
  if (typeof hideLobby === "function") hideLobby();
  NAV().forEach((b) => b.classList.toggle("active", b.dataset.view === v || (["nutrition", "season"].includes(v) && b.dataset.view === "race" && !!b.closest("#tabs"))));
  $("#btn-coach").classList.toggle("active", v === "coach");
  try { localStorage.setItem("sub3_view", v); } catch { /* */ }
  window.scrollTo({ top: 0 });
  render();
}
NAV().forEach((b) => b.addEventListener("click", () => (b.dataset.lobby ? showLobby() : b.dataset.view ? setView(b.dataset.view) : null)));
$$("#mod-switch button").forEach((b) => b.addEventListener("click", () => {
  let v = null;
  try { v = localStorage.getItem(MOD_LAST[b.dataset.mod]); } catch { /* */ }
  setView(v || MOD_HOME[b.dataset.mod]);
}));
$("#brand-home").addEventListener("click", () => showLobby());
$("#btn-settings").addEventListener("click", showSettings);
["#garmin-pill", "#garmin-pill-side"].forEach((s) => $(s).addEventListener("click", () => (state.status.connected ? showSettings() : showLogin())));
$("#btn-refresh").addEventListener("click", async (e) => {
  const b = e.currentTarget; b.classList.add("spin");
  try { await api("/api/cache/clear", { method: "POST" }); state.plan = null; await render(); toast("Données Garmin rafraîchies"); }
  catch (err) { toast(err.message, true); } finally { b.classList.remove("spin"); }
});

// ---------------------------------------------------------------- thème clair / sombre
function currentTheme() {
  const t = document.documentElement.dataset.theme;
  if (t) return t;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("sub3_theme", t); } catch { /* */ }
  $$('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", t === "dark" ? "#0a0b0d" : "#f5f5f2"));
}
$("#btn-theme").addEventListener("click", () => {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
  if (state.charts.length) render(); // les graphiques reprennent les couleurs du thème
});
if (!document.documentElement.dataset.theme) applyTheme(currentTheme());

function destroyCharts() { state.charts.forEach((c) => c.destroy()); state.charts = []; }

async function render() {
  destroyCharts();
  const view = $("#view");
  if (!state.status.connected) { renderLogin(view); return; }
  setHeader(state.view);
  view.innerHTML = `<div class="skeleton"><i></i><i></i><i></i></div>`;
  try {
    await ({ home: renderHome, plan: renderPlan, builder: renderBuilder, race: renderRace, nutrition: renderNutrition, season: renderSeason, "b-today": renderBodyToday, "b-log": renderBodyLog, "b-dash": renderBodyDash, "b-race": renderBodyRace, "f-home": renderFinHome, "f-tx": renderFinTx, "f-budget": renderFinBudget, "f-recurring": renderFinRecurring, "f-accounts": renderFinAccounts, "f-analysis": renderFinAnalysis, "m-home": renderMediaHome, "m-lib": renderMediaLib, "m-stats": renderMediaStats, data: renderData, acts: renderActs, coach: renderCoach }[state.view] || renderHome)(view);
  } catch (e) {
    if (state.status.connected) view.innerHTML = `<div class="card empty">Erreur : ${esc(e.message)}</div>`;
  }
}

function updatePill() {
  const s = state.status;
  ["#garmin-pill", "#garmin-pill-side"].forEach((sel) => {
    const p = $(sel); if (!p) return;
    if (s.connected) { p.className = "pill ok" + (sel === "#garmin-pill" ? " mobile-only" : ""); p.textContent = s.demo ? "Démo" : "Garmin connecté"; }
    else { p.className = "pill ko" + (sel === "#garmin-pill" ? " mobile-only" : ""); p.textContent = "Garmin déconnecté"; }
  });
}

// ---------------------------------------------------------------- PIN & connexion
function askPin() {
  openModal(h`<h3>Code d'accès</h3>
    <p class="muted small">Le code PIN s'affiche dans la fenêtre du Mac où Élan tourne (et dans Réglages sur le Mac).</p>
    <label class="f">PIN<input id="pin-in" inputmode="numeric" autocomplete="one-time-code" maxlength="6"></label>
    <div class="btns"><button class="btn primary" id="pin-ok">Valider</button></div>`, (el) => {
    $("#pin-in", el).focus();
    const go = async () => { PIN = $("#pin-in", el).value.trim(); document.cookie = `sub3_pin=${PIN}; max-age=31536000; path=/`; try { localStorage.setItem("sub3_pin", PIN); } catch { /* */ } closeModal(); await boot(); };
    $("#pin-ok", el).onclick = go;
    $("#pin-in", el).onkeydown = (e) => e.key === "Enter" && go();
  });
}

function renderLogin(view) {
  view.innerHTML = h`<div class="card login">
    <h3>Connecte ton compte Garmin</h3>
    <p class="muted small">Tes identifiants partent directement de ce Mac vers Garmin. Seul un jeton de session est gardé, dans le dossier <code>data/</code> de l'app.</p>
    <div id="login-step1">
      <label class="f">E-mail Garmin<input id="lg-email" type="email" autocomplete="username"></label>
      <label class="f">Mot de passe<input id="lg-pass" type="password" autocomplete="current-password"></label>
      <div class="btns"><button class="btn primary" id="lg-go">Se connecter</button></div>
    </div>
    <div id="login-step2" hidden>
      <p class="small">Garmin t'a envoyé un code de vérification (e-mail ou SMS).</p>
      <label class="f">Code<input id="lg-code" inputmode="numeric" autocomplete="one-time-code"></label>
      <div class="btns"><button class="btn primary" id="lg-mfa">Valider le code</button></div>
    </div>
    <p id="lg-err" class="small" style="color:var(--bad)"></p>
  </div>`;
  const err = (m) => ($("#lg-err").textContent = m || "");
  $("#lg-go").onclick = async (e) => {
    e.target.disabled = true; err("Connexion…");
    try {
      const r = await api("/api/auth/login", { method: "POST", body: { email: $("#lg-email").value, password: $("#lg-pass").value } });
      if (r.status === "mfa") { $("#login-step1").hidden = true; $("#login-step2").hidden = false; err(""); $("#lg-code").focus(); }
      else { err(""); await boot(); }
    } catch (ex) { err(ex.message); } finally { e.target.disabled = false; }
  };
  $("#lg-pass").onkeydown = (e) => e.key === "Enter" && $("#lg-go").click();
  $("#lg-mfa").onclick = async (e) => {
    e.target.disabled = true; err("Vérification…");
    try { await api("/api/auth/mfa", { method: "POST", body: { code: $("#lg-code").value } }); err(""); await boot(); }
    catch (ex) { err(ex.message); } finally { e.target.disabled = false; }
  };
}
function showLogin() { closeModal(); state.status.connected = false; updatePill(); render(); }

// ---------------------------------------------------------------- ACCUEIL
function tile(label, value, sub = "", color = null, unit = "") {
  return h`<div class="tile"><div class="label"><span>${label}</span>${color ? `<span class="dot" style="background:${color}"></span>` : ""}</div>
    <div class="value num">${value ?? "—"}${unit && value != null && value !== "—" ? `<small> ${unit}</small>` : ""}</div><div class="sub">${sub}</div></div>`;
}

function sessionRow(s, opts = {}) {
  const d = parseD(s.date);
  const isToday = s.date === today();
  const st = STATUS_LABELS[s.status] || "";
  const g = s.garmin_workout_id ? `<div class="gtag ${s.garmin_dirty ? "dirty" : ""}">${s.garmin_dirty ? "⟳ à renvoyer" : "⌚ sur la montre"}</div>` : "";
  const side = s.type === "REPOS"
    ? (s.done_km ? `<div class="status st-extra">${km(s.done_km)} km</div>` : "")
    : h`<div class="num"><b>${km(s.planned_km)}</b> km</div>
       ${s.done_km ? `<div class="num small muted">fait ${km(s.done_km)}</div>` : ""}
       <div class="status st-${s.status}">${st}</div>${s.review_score != null ? `<span class="badge-score ${s.review_color}">${s.review_score}</span>` : ""}${g}`;
  return h`<div class="sess ${isToday ? "is-today" : ""} ${s.type === "REPOS" ? "is-rest" : ""}" data-sid="${s.id}">
    <div class="sess-date"><b class="num">${d.getDate()}</b><span>${DAYS[d.getDay()]}</span></div>
    <div class="sess-main"><div class="sess-title"><span class="chip ${s.type}">${s.type}</span> ${esc(s.title)}</div>
      <div class="sess-sum">${esc(s.summary || s.description || "")}${s.planned_s && s.type !== "REPOS" ? ` · ~${dur(s.planned_s)}` : ""}</div></div>
    <div class="sess-side">${side}</div></div>`;
}

function bindSessionRows(el) {
  $$(".sess[data-sid]", el).forEach((r) => r.addEventListener("click", () => showSession(r.dataset.sid)));
}

async function renderHome(view) {
  const d = await api("/api/dashboard");
  state.paces = d.paces;
  const g = d.garmin || {}, m = g.metrics || {}, st = g.status || {}, rd = g.readiness || {};
  const isMara = Math.abs((d.race.distance_km || 42.195) - 42.195) < 0.5;
  const predM = isMara ? g.predictions?.marathon : null;
  const goalS = d.goal_pace_s * d.race.distance_km;
  const delta = predM ? predM - goalS : null;
  const [tsLabel, tsColor] = tsPhrase(st.phrase);
  const [rdLabel, rdColor] = LEVELS[rd.level] || ["", null];
  const [hrvLabel, hrvColor] = HRV_STATUS[m.hrv_status] || ["", null];
  const wk = d.week;
  const pct = wk && wk.planned_km ? Math.min(100, (wk.done_km / wk.planned_km) * 100) : 0;
  const todayS = d.today_sessions.filter((s) => s.type !== "REPOS" && s.type !== "RENFO" && !s.activities?.length && (s.steps || []).length);

  view.innerHTML = h`
  <div class="cols"><div>
    <div class="card hero">
      <div class="row between"><div><div class="muted small">${esc(d.race.name)} · ${fmtDay(d.race.date)}</div>
        <div class="hero-big num">${d.days_to_race >= 0 ? `J-${d.days_to_race}` : "Terminé"}</div></div>
        <div style="text-align:right"><div class="muted small">Objectif</div><div style="font-size:24px;font-weight:800" class="num">${d.race.finish_only ? "Finir" : esc(d.race.goal)}</div>
        <div class="small num">${d.race.finish_only ? `${km(d.race.distance_km, 0)} km` : pace(d.goal_pace_s) + "/km"}</div></div></div>
      <div class="hero-grid">
        ${isMara ? `<div><span>Prédiction</span><b class="num">${predM ? hms(predM) : "—"}</b></div>` : `<div><span>Semaines</span><b class="num">${Math.ceil(d.days_to_race / 7)}</b></div>`}
        ${isMara ? `<div><span>Écart</span><b class="num">${delta == null ? "—" : (delta <= 0 ? "−" : "+") + dur(Math.abs(delta))}</b></div>` : `<div><span>Cette semaine</span><b class="num">${wk ? km(wk.planned_km, 0) + " km" : "—"}</b></div>`}
        <div><span>7 jours</span><b class="num">${km(d.last7.km)} km</b></div>
      </div>
    </div>

    ${d.debrief_todo ? h`<div class="card section season-cta" data-aid="${d.debrief_todo.aid}" data-sid="${d.debrief_todo.sid}">
      <div><div class="eyebrow-s">Course terminée</div><h3 style="margin:2px 0 2px">Fais le bilan de ${esc(d.debrief_todo.name)}</h3>
      <div class="small muted">Prévu vs réalisé, gestion de l'allure, ravitaillement : 3 minutes pour préparer la suite.</div></div><span class="cta-arrow">→</span></div>` : ""}
    ${d.days_to_race < 0 && !d.debrief_todo ? h`<div class="card section season-cta" data-prep="1">
      <div><div class="eyebrow-s">Et maintenant ?</div><h3 style="margin:2px 0 2px">${d.next_draft ? "Ton prochain plan t'attend" : "Prépare ta prochaine saison"}</h3>
      <div class="small muted">${d.next_draft ? "Relis le brouillon et active-le quand tu es prêt." : "Choisis ta prochaine course : le plan se construit à partir de tes données."}</div></div><span class="cta-arrow">→</span></div>` : ""}
    ${d.light ? lightCard(d.light) : ""}
    ${(d.prep || []).map(prepCardHtml).join("")}
    ${d.coach?.morning ? noteHtml(d.coach.morning) : ""}
    ${d.sleep && d.sleep.avg7_h != null ? h`<div class="card section" id="home-sleep" style="cursor:pointer">
      <div class="row between"><h2 style="margin:0">Sommeil</h2><span class="small muted">objectif ${hfr(d.sleep.goal_h)}</span></div>
      <div class="row" style="gap:16px;margin-top:8px;flex-wrap:wrap">
        <div><div class="small muted">Ce soir, au lit avant</div><div style="font-size:26px;font-weight:900" class="num">${d.sleep.target_bed || "—"}</div></div>
        <div><div class="small muted">Dette 3 nuits</div><div style="font-size:20px;font-weight:800;color:${d.sleep.debt3_h > 3 ? "var(--warn)" : "inherit"}" class="num">${d.sleep.debt3_h != null ? km(d.sleep.debt3_h) + " h" : "—"}</div></div>
        <div><div class="small muted">Moyenne 7 j</div><div style="font-size:20px;font-weight:800" class="num">${hfr(d.sleep.avg7_h)}</div></div>
      </div>
      <div class="small muted" style="margin-top:6px">${esc(d.sleep.message)}</div></div>` : ""}

    <div class="card section">
      <h2>Aujourd'hui</h2>
      ${d.today_sessions.length ? d.today_sessions.map((s) => sessionRow(s)).join("") : `<div class="muted">Rien de prévu au plan.</div>`}
      ${todayS.length ? h`<div class="btns">${todayS.map((s) => `<button class="btn primary sm" data-push="${s.id}">⌚ ${s.garmin_workout_id && !s.garmin_dirty ? "Renvoyer" : "Envoyer"} sur la montre</button>`).join("")}</div>` : ""}
    </div>

    <div class="card section">
      <div class="row between"><h2 style="margin:0">Semaine en cours</h2>
        ${wk ? `<span class="num small"><b>${km(wk.done_km)}</b> / ${km(wk.planned_km, 0)} km</span>` : ""}</div>
      ${wk ? h`<div class="bar" style="margin:10px 0 14px"><i style="width:${pct}%"></i></div>
        <div id="week-list">${wk.sessions.map((s) => sessionRow(s)).join("")}</div>
        <div class="btns"><button class="btn sm" id="push-week" data-week="${wk.start}">⌚ Envoyer la semaine sur Garmin</button></div>`
        : `<div class="muted">Pas de plan cette semaine.</div>`}
    </div>
  </div><div>
    ${predictionShort(d.prediction).replace('card section', 'card')}
    <div class="section">
      <h2>Forme du jour</h2>
      <div class="grid g2">
        ${tile("Disponibilité", rd.score, rdLabel, rdColor)}
        ${tile("VFC nuit", m.hrv, hrvLabel ? `${hrvLabel} · moy. 7j ${m.hrv_weekly ?? "—"}` : "", hrvColor, "ms")}
        ${tile("Sommeil", m.sleep_score, m.sleep_s ? `${dur(m.sleep_s)} de sommeil` : "")}
        ${tile("Body Battery", m.bb_high, m.bb_now != null ? `actuel ${m.bb_now}` : "max du jour")}
        ${tile("FC repos", m.rhr, "", null, "bpm")}
        ${tile("Statut", `<span style="font-size:18px">${tsLabel}</span>`, st.acwr ? `ratio charge ${Number(st.acwr).toFixed(1)}` : "", tsColor)}
        ${tile("VO2max", st.vo2max ? Number(st.vo2max).toFixed(1) : null, "")}
        ${tile("Charge aiguë", st.acute ? Math.round(st.acute) : null, st.chronic ? `chronique ${Math.round(st.chronic)}` : "")}
      </div>
    </div>
    <div class="card section">
      <h2>Prédictions Garmin</h2>
      <table><tbody>
        ${[["5 km", g.predictions?.["5k"], 5], ["10 km", g.predictions?.["10k"], 10], ["Semi", g.predictions?.half, 21.0975], ["Marathon", predM, 42.195]]
          .map(([l, t, dk]) => `<tr><td>${l}</td><td class="r num"><b>${t ? hms(t) : "—"}</b></td><td class="r num muted">${t ? pace(t / dk) + "/km" : ""}</td></tr>`).join("")}
      </tbody></table>
    </div>
    <div class="card section">
      <h2>Allures cibles</h2>
      <table><tbody>${Object.entries(d.paces).map(([k, v]) => `<tr><td><span class="dot" style="background:${ZONE_COLORS[k] || "#999"}"></span> ${k}</td><td class="r num">${v[0]} → ${v[1]}</td></tr>`).join("")}</tbody></table>
    </div>
    ${d.coach?.latest && d.coach.latest.id !== d.coach?.morning?.id ? noteHtml(d.coach.latest) : ""}
    ${d.last_review ? h`<div class="card section" id="last-review" data-sid="${d.last_review.session.id}" style="cursor:pointer"><h2>Dernier bilan · ${fmtDay(d.last_review.session.date)}</h2>
      <div class="sess-title" style="margin-bottom:8px"><span class="chip ${d.last_review.session.type}">${d.last_review.session.type}</span> ${esc(d.last_review.session.title)}</div>
      ${reviewHtml(d.last_review.review, true)}</div>` : ""}
    ${d.last_activity ? h`<div class="card section"><h2>Dernière sortie</h2>${actRow(d.last_activity)}</div>` : ""}
  </div></div>`;

  bindSessionRows(view);
  $$("[data-push]", view).forEach((b) => (b.onclick = () => pushSession(b.dataset.push, b)));
  const pw = $("#push-week", view);
  if (pw) pw.onclick = () => pushWeek(pw.dataset.week, pw);
  $$(".act[data-aid]", view).forEach((r) => (r.onclick = () => showActivity(r.dataset.aid)));
  const hp = $("#home-pred", view);
  if (hp) hp.onclick = () => setView("race");
  $$(".season-cta", view).forEach((c) => (c.onclick = () => {
    if (c.dataset.aid) openDebrief(c.dataset.aid, c.dataset.sid || null);
    else { try { localStorage.setItem("sub3_season_tab", "prepa"); } catch { /* */ } setView("season"); }
  }));
  const hs = $("#home-sleep", view);
  if (hs) hs.onclick = () => setView("data");
  const lr = $("#last-review", view);
  if (lr) lr.onclick = () => showSession(lr.dataset.sid);
  bindLight(view);
  bindNotes(view);
  updateCoachBadge(d.coach?.unread || 0);
}

// ---------------------------------------------------------------- COACH : feu du matin & bilans
const LIGHT_EMOJI = { green: "Feu vert", orange: "Feu orange", red: "Feu rouge" };
function lightCard(L) {
  return h`<div class="card light ${L.color} section" style="margin-top:12px">
    <div class="light-dot"></div>
    <div style="flex:1;min-width:0">
      <div class="small muted">Feu du matin</div>
      <div class="light-title">${esc(L.title)}</div>
      <div class="reasons">${L.reasons.map((r) => `<span class="reason lv${r.level}" title="${esc(r.detail || "")}"><span class="dot"></span>${esc(r.label)} <b class="num">${esc(r.value)}</b></span>`).join("")}</div>
      ${L.reasons.filter((r) => r.level > 0 && r.detail).map((r) => `<div class="small muted">• ${esc(r.label)} : ${esc(r.detail)}</div>`).join("")}
      <p style="margin:8px 0 0">${esc(L.advice)}</p>
      ${L.actions.length ? `<div class="btns">${L.actions.map((a) => `<button class="btn sm ${a.id === "undo" ? "" : "primary"}" data-adjust="${a.id}" data-sid="${L.session_id}">${esc(a.label)}</button>`).join("")}</div>` : ""}
    </div></div>`;
}
function bindLight(el) {
  $$("[data-adjust]", el).forEach((b) => (b.onclick = () => adjustSession(b.dataset.sid, b.dataset.adjust, b)));
}
const ADJUST_MSG = { lighten: "Séance allégée", shorten: "Séance raccourcie", easy: "Transformée en footing facile", rest: "Remplacée par du repos", swap_next: "Séance décalée à demain", undo: "Ajustement annulé" };
async function adjustSession(sid, action, btn) {
  if (btn) btn.disabled = true;
  try {
    const r = await api(`/api/plan/session/${sid}/adjust`, { method: "POST", body: { action } });
    state.plan = null;
    toast(ADJUST_MSG[action] + (r.garmin_synced?.length ? " · montre mise à jour ⌚" : ""));
    closeModal(); await render();
  } catch (e) { toast(e.message, true); if (btn) btn.disabled = false; }
}

const SEG_ICON = { ok: "✓", fast: "▲", slow: "▼", na: "·" };
function reviewHtml(rv, compact = false) {
  if (!rv) return "";
  if (rv.score == null) return `<div class="muted small">${esc(rv.verdict)}</div>`;
  const head = h`<div class="row" style="gap:12px"><div class="score ${rv.color}" style="--v:${rv.score}"><span class="num">${rv.score}</span></div>
    <div><div style="font-weight:750">${esc(rv.verdict)}</div><div class="small muted num">${km(rv.km_done)} / ${km(rv.km_planned)} km · ${dur(rv.time_done)}${rv.avg_hr ? ` · FC ${rv.avg_hr}` : ""}${rv.drift != null ? ` · dérive ${km(rv.drift)} %` : ""}</div></div></div>`;
  const comments = (compact ? rv.comments.slice(0, 3) : rv.comments);
  const list = comments.length ? `<ul class="review-list">${comments.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "";
  const tip = rv.tip ? `<div class="tip">💡 ${esc(rv.tip)}</div>` : "";
  if (compact) return head + list + tip;
  const segs = (rv.segments || []).filter((s) => s.kind !== "rest" && s.kind !== "recovery");
  const table = segs.length ? h`<div class="table-wrap" style="margin-top:12px"><table>
    <thead><tr><th>Étape</th><th class="r">Cible</th><th class="r">Réalisé</th><th class="r">FC</th><th></th></tr></thead>
    <tbody>${segs.map((s) => `<tr><td class="small">${s.rep ? `<span class="muted">#${s.rep}</span> ` : ""}${esc(s.label.replace("Course ", ""))}</td><td class="r num small muted">${s.target || "—"}</td><td class="r num">${s.pace ? s.pace + (s.approx ? "*" : "") : "—"}</td><td class="r num">${s.hr ?? "—"}</td><td class="r seg-${s.status}" title="${s.delta ? s.delta + " s/km" : ""}">${SEG_ICON[s.status]}${s.delta ? `<span class="small"> ${s.delta}s</span>` : ""}</td></tr>`).join("")}</tbody>
  </table></div>
  <div class="small muted" style="margin-top:4px">✓ dans la cible · ▲ trop rapide · ▼ trop lent${segs.some((s) => s.approx) ? " · * estimé à partir des tours au km" : ""}${rv.mode === "cumulative" && segs.some((s) => s.status === "na") ? " · · non mesurable sans un tour par étape (lance la séance depuis la montre)" : ""}</div>` : "";
  return head + list + tip + table;
}

async function pushSession(sid, btn) {
  if (btn) { btn.disabled = true; btn.textContent = "Envoi…"; }
  try { await api(`/api/plan/session/${sid}/push`, { method: "POST" }); toast("Séance envoyée et planifiée sur Garmin ⌚"); await render(); }
  catch (e) { toast(e.message, true); if (btn) btn.disabled = false; }
}
async function pushWeek(start, btn) {
  btn.disabled = true; btn.textContent = "Envoi…";
  try {
    const r = await api(`/api/plan/week/${start}/push`, { method: "POST" });
    const ok = r.filter((x) => !x.error).length, ko = r.length - ok;
    toast(`${ok} séance(s) envoyée(s)${ko ? `, ${ko} en erreur` : ""}`, ko > 0);
    await render();
  } catch (e) { toast(e.message, true); btn.disabled = false; }
}

// ---------------------------------------------------------------- PLAN
async function renderPlan(view) {
  const p = await api("/api/plan");
  state.plan = p; state.paces = p.paces;
  const t = today();
  const totalPlanned = p.weeks.reduce((a, w) => a + w.planned_km, 0);
  view.innerHTML = h`
    <div class="row between wrap" style="margin-bottom:12px">
      <div><h3>${esc(p.race.name)} — ${esc(p.race.goal)}</h3><div class="muted small">${p.weeks.length} semaines · ${km(totalPlanned, 0)} km prévus · ${fmtDay(p.race.date)}</div></div>
      <div class="row"><div class="seg" id="plan-mode"><button data-m="weeks" class="${state.planMode !== "month" ? "on" : ""}">Semaines</button><button data-m="month" class="${state.planMode === "month" ? "on" : ""}">Mois</button></div>
      <button class="btn primary sm" id="add-sess">+ Séance</button></div>
    </div>
    ${p.hr_zones || p.rules ? h`<details class="card" style="margin-bottom:12px"><summary style="cursor:pointer;font-weight:650">Repères du coach</summary>
      ${p.athlete ? `<p class="small muted">FC max ${p.athlete.hr_max} · FC repos ${p.athlete.hr_rest} · ${esc(p.athlete.ref || "")}</p>` : ""}
      <div class="grid" style="margin-top:8px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))"><div><h2>Zones FC</h2><table><tbody>${(p.hr_zones || []).map((z) => `<tr><td>Z${z.zone}</td><td class="num">${esc(z.range)}</td><td class="muted small">${esc(z.use)}</td></tr>`).join("")}</tbody></table></div>
      <div><h2>Allures</h2><table><tbody>${Object.entries(p.paces).map(([k, v]) => `<tr><td><span class="dot" style="background:${ZONE_COLORS[k] || "#999"}"></span> ${k}</td><td class="num">${v[0]}–${v[1]}</td><td class="muted small">${esc(p.pace_labels?.[k] || "")}</td></tr>`).join("")}</tbody></table></div></div>
      ${(p.rules || []).length ? `<h2 style="margin-top:12px">Règles</h2><ul class="small" style="margin:0;padding-left:18px">${p.rules.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
    </details>` : ""}
    ${state.planMode === "month" ? monthCalendar(p) : p.weeks.map((w, i) => {
      const past = w.end < t;
      const pct = w.planned_km ? Math.min(100, (w.done_km / w.planned_km) * 100) : 0;
      return h`<div class="card week ${w.current ? "current" : ""} ${past ? "collapsed" : ""}" data-week="${w.start}">
        <div class="week-head">
          <div style="flex:1;min-width:0"><div><b>S${i}</b> ${w.current ? `<span class="week-tag">EN COURS</span>` : ""}</div>
            <div class="small muted">${fmtDay(w.start)} → ${fmtDay(w.end)}</div></div>
          <div class="bar"><i style="width:${pct}%"></i></div>
          <div class="num small" style="text-align:right;min-width:72px"><b>${km(w.done_km)}</b> / ${km(w.planned_km, 0)} km</div>
        </div>
        <div class="week-body">${w.sessions.map((s) => sessionRow(s)).join("")}
          ${!past ? `<div class="btns"><button class="btn sm" data-pushweek="${w.start}">⌚ Envoyer la semaine</button></div>` : ""}
        </div></div>`;
    }).join("")}`;
  $$("#plan-mode button", view).forEach((b) => (b.onclick = () => { state.planMode = b.dataset.m; try { localStorage.setItem("sub3_planmode", b.dataset.m); } catch { /* */ } render(); }));
  if (state.planMode === "month") bindCalendar(view);
  $$(".week-head", view).forEach((hd) => (hd.onclick = () => hd.parentElement.classList.toggle("collapsed")));
  bindSessionRows(view);
  $$("[data-pushweek]", view).forEach((b) => (b.onclick = () => pushWeek(b.dataset.pushweek, b)));
  $("#add-sess", view).onclick = () => editSession({ id: null, date: today(), type: "EF", title: "", steps: [{ kind: "run", dur: { type: "distance", value: 10000 }, target: { pace: "EF" } }], description: "" });
  const cur = $(".week.current", view);
  if (cur) cur.scrollIntoView({ block: "start", behavior: "instant" in window ? "instant" : "auto" });
}

async function findSession(sid) {
  if (!state.plan || !state.plan.sessions.find((s) => s.id === sid)) state.plan = await api("/api/plan");
  return state.plan.sessions.find((s) => s.id === sid);
}

async function showSession(sid) {
  const s = await findSession(sid);
  if (!s) return;
  const prof = profileHtml(s.steps || [], state.plan.paces);
  openModal(h`
    <div class="small muted">${fmtDay(s.date)}</div>
    <h3><span class="chip ${s.type}">${s.type}</span> ${esc(s.title)}</h3>
    ${s.type !== "REPOS" ? h`<div class="row wrap small" style="gap:14px;margin:6px 0 12px"><span>≈ <b class="num">${km(s.planned_km)}</b> km</span><span>≈ <b class="num">${dur(s.planned_s)}</b></span>
      <span class="status st-${s.status}">${STATUS_LABELS[s.status] || ""}</span></div>${prof}` : ""}
    ${s.description ? `<p>${esc(s.description)}</p>` : ""}
    ${(s.steps || []).length ? `<div class="section"><h2>Déroulé</h2>${stepsReadable(s.steps, state.plan.paces)}</div>` : ""}
    ${s.activities?.length && (s.steps || []).length ? `<div class="section"><h2>Bilan</h2><div id="ms-review" class="muted small">Analyse de la séance…</div></div>` : ""}
    <div id="ms-fuel"></div>
    <div id="ms-coach"></div>
    ${s.activities?.length ? h`<div class="section"><h2>Réalisé</h2>${s.activities.map((a) => `<div class="act" data-aid="${a.id}"><div class="act-ico">✓</div><div class="act-main"><div class="act-name">${esc(a.name)}</div><div class="act-stats"><span><b>${km(a.km, 2)}</b> km</span><span><b>${pace(a.pace_s)}</b>/km</span><span>FC <b>${a.avg_hr ?? "—"}</b></span></div></div></div>`).join("")}</div>` : ""}
    ${s.date <= today() && !["REPOS"].includes(s.type) ? h`<div class="section"><h2>Ressenti</h2>
      <div class="small muted">Effort perçu (1 = très facile, 10 = maximal)</div>
      <div class="rpe" id="ms-rpe">${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => `<button data-v="${n}" class="${s.feedback?.rpe === n ? "on" : ""}">${n}</button>`).join("")}</div>
      <textarea id="ms-note" placeholder="Sensations, douleurs, conditions, nutrition…" style="width:100%">${esc(s.feedback?.note || "")}</textarea>
      <div class="btns" style="margin-top:6px"><button class="btn sm" id="ms-fb">Enregistrer le ressenti</button>
      <button class="btn sm" id="ms-link">${s.activities?.length ? "Changer la sortie associée" : "Associer une sortie"}</button></div></div>` : ""}
    ${s.garmin_workout_id ? `<p class="small muted">⌚ Envoyée sur Garmin le ${esc((s.garmin_pushed_at || "").replace("T", " à "))}${s.garmin_dirty ? " — <b style='color:var(--warn)'>modifiée depuis, à renvoyer</b>" : ""}</p>` : ""}
    <div class="btns">
      ${(s.steps || []).length && s.type !== "REPOS" && s.date >= today() ? `<button class="btn primary" id="ms-push">⌚ ${s.garmin_workout_id ? "Renvoyer" : "Envoyer"} sur Garmin</button>` : ""}
      <button class="btn" id="ms-edit">Modifier</button>
      <button class="btn" id="ms-dup">Dupliquer</button>
      ${s.original ? `<button class="btn" data-adjust="undo" data-sid="${s.id}">Annuler l'ajustement</button>` : ""}
      ${s.garmin_workout_id ? `<button class="btn" id="ms-unpush">Retirer de Garmin</button>` : ""}
      <button class="btn danger" id="ms-del">Supprimer</button>
    </div>`, (el) => {
    $$(".act[data-aid]", el).forEach((r) => (r.onclick = () => showActivity(r.dataset.aid)));
    api("/api/coach").then((C) => {
      const ns = C.notes.filter((n) => n.session_id === s.id);
      const box = $("#ms-coach", el); if (!box) return;
      box.innerHTML = ns.map((n) => noteHtml(n, { noLink: true })).join("") +
        `<div class="section"><h2>Une question sur cette séance ?</h2><textarea id="ms-q" placeholder="Pose ta question au coach" style="width:100%"></textarea><div class="btns" style="margin-top:6px"><button class="btn sm" id="ms-qsend">Envoyer au coach</button></div></div>`;
      bindNotes(box);
      $("#ms-qsend", box).onclick = async () => {
        const text = $("#ms-q", box).value.trim(); if (!text) return;
        await api("/api/coach/questions", { method: "POST", body: { text, session_id: s.id } }); toast("Question transmise au coach"); $("#ms-q", box).value = "";
      };
    }).catch(() => {});
    const fuelBox = $("#ms-fuel", el);
    if (fuelBox && s.type !== "REPOS" && s.type !== "RENFO" && (s.activities?.length || (s.planned_s || 0) >= 75 * 60)) fuelSection(fuelBox, s);
    const rvBox = $("#ms-review", el);
    if (rvBox) api(`/api/plan/session/${s.id}/review`).then((rv) => { rvBox.className = ""; rvBox.innerHTML = reviewHtml(rv); }).catch((e) => (rvBox.textContent = e.message));
    let rpe = s.feedback?.rpe ?? null;
    $$("#ms-rpe button", el).forEach((b) => (b.onclick = () => { rpe = Number(b.dataset.v); $$("#ms-rpe button", el).forEach((x) => x.classList.toggle("on", x === b)); }));
    const fb = $("#ms-fb", el);
    if (fb) fb.onclick = async () => {
      try { await api(`/api/plan/session/${s.id}/feedback`, { method: "POST", body: { rpe, note: $("#ms-note", el).value } }); state.plan = null; toast("Ressenti enregistré"); }
      catch (e) { toast(e.message, true); }
    };
    bindLight(el);
    const lk = $("#ms-link", el);
    if (lk) lk.onclick = () => linkActivities(s);
    const push = $("#ms-push", el);
    if (push) push.onclick = async () => { await pushSession(s.id, push); closeModal(); };
    $("#ms-edit", el).onclick = () => editSession(JSON.parse(JSON.stringify(s)));
    $("#ms-dup", el).onclick = () => editSession({ ...JSON.parse(JSON.stringify(s)), id: null, garmin_workout_id: null });
    const un = $("#ms-unpush", el);
    if (un) un.onclick = async () => { await api(`/api/plan/session/${s.id}/garmin`, { method: "DELETE" }); toast("Retirée de Garmin"); closeModal(); render(); };
    $("#ms-del", el).onclick = async () => {
      if (!confirm("Supprimer cette séance du plan ?")) return;
      await api(`/api/plan/session/${s.id}`, { method: "DELETE" }); toast("Séance supprimée"); closeModal(); render();
    };
  });
}

async function linkActivities(s) {
  openModal(`<div class="skeleton">Recherche des sorties autour du ${fmtDay(s.date)}…</div>`);
  let cands;
  try { cands = await api(`/api/plan/session/${s.id}/candidates`); } catch (e) { $("#modal-body").innerHTML = esc(e.message); return; }
  openModal(h`<h3>Sortie(s) pour « ${esc(s.title)} »</h3>
    <p class="small muted">Prévue le ${fmtDay(s.date)} — coche la ou les sorties qui correspondent (±3 jours). Utile si tu as décalé la séance ou découpé ta sortie.</p>
    <div>${cands.length ? cands.map((a) => `<label class="cand"><input type="checkbox" value="${a.id}" ${a.selected ? "checked" : ""} style="width:auto">
      <div style="flex:1;min-width:0"><div><b>${fmtDay(a.date)}</b> · ${esc(a.name)}</div><div class="small muted num">${km(a.distance_km, 2)} km · ${pace(a.pace_s)}/km${a.avg_hr ? ` · FC ${a.avg_hr}` : ""}${a.current_session && !a.selected ? ` · actuellement : ${esc(a.current_session.title)}` : ""}</div></div></label>`).join("")
      : `<div class="empty">Aucune sortie dans les 3 jours autour.</div>`}</div>
    <div class="btns"><button class="btn primary" id="lk-save">Associer</button><button class="btn" id="lk-auto">Revenir à l'automatique (par date)</button></div>`, (el) => {
    $("#lk-save", el).onclick = async () => {
      const ids = $$("input[type=checkbox]:checked", el).map((i) => i.value);
      await api(`/api/plan/session/${s.id}/link`, { method: "POST", body: { activity_ids: ids } });
      state.plan = null; toast("Association enregistrée"); closeModal(); await render(); showSession(s.id);
    };
    $("#lk-auto", el).onclick = async () => {
      await api(`/api/plan/session/${s.id}/link`, { method: "POST", body: { activity_ids: null } });
      state.plan = null; toast("Association automatique rétablie"); closeModal(); render();
    };
  });
}

function editSession(s) {
  const paces = state.paces || state.plan?.paces;
  const work = { steps: JSON.parse(JSON.stringify(s.steps || [])) };
  openModal(h`
    <h3>${s.id ? "Modifier la séance" : "Nouvelle séance"}</h3>
    <div class="grid g2" style="margin-top:12px">
      <label class="f">Date<input type="date" id="es-date" value="${s.date}"></label>
      <label class="f">Type<select id="es-type">${TYPES.map((t) => `<option value="${t}" ${t === s.type ? "selected" : ""}>${t} – ${TYPE_LABELS[t]}</option>`).join("")}</select></label>
    </div>
    <label class="f">Titre<input id="es-title" value="${esc(s.title)}"></label>
    <label class="f">Notes / consignes<textarea id="es-desc">${esc(s.description || "")}</textarea></label>
    <h2 style="margin-top:8px">Étapes</h2>
    <div id="es-prof"></div>
    <div id="es-steps"></div>
    <div class="btns"><button class="btn primary" id="es-save">Enregistrer</button>${s.id ? "" : `<button class="btn" id="es-save-push">Enregistrer + envoyer sur Garmin</button>`}</div>`, (el) => {
    const refresh = () => {
      $("#es-prof", el).innerHTML = work.steps.length ? profileHtml(work.steps, paces) + `<div class="small muted" style="margin:6px 0 10px">${estimateText(work.steps, paces)}</div>` : "";
    };
    stepEditor($("#es-steps", el), work, paces, refresh);
    refresh();
    const save = async (push) => {
      const body = { date: $("#es-date", el).value, type: $("#es-type", el).value, title: $("#es-title", el).value || TYPE_LABELS[$("#es-type", el).value], description: $("#es-desc", el).value, steps: work.steps };
      if (body.type === "REPOS") body.steps = [];
      try {
        const r = s.id ? await api(`/api/plan/session/${s.id}`, { method: "PUT", body }) : await api("/api/plan/session", { method: "POST", body });
        if (push) await api(`/api/plan/session/${r.id}/push`, { method: "POST" });
        toast(push ? "Enregistrée et envoyée sur Garmin ⌚" : "Séance enregistrée");
        closeModal(); state.plan = null; render();
      } catch (e) { toast(e.message, true); }
    };
    $("#es-save", el).onclick = () => save(false);
    const sp = $("#es-save-push", el);
    if (sp) sp.onclick = () => save(true);
  });
}

// ---------------------------------------------------------------- étapes : estimation / affichage / éditeur
function targetPaces(t, paces) {
  if (!t) return null;
  if (t.pace && paces[t.pace]) { const a = paceToSec(paces[t.pace][0]), b = paceToSec(paces[t.pace][1]); return { slow: Math.max(a, b), fast: Math.min(a, b), zone: t.pace }; }
  if (t.from && t.to) { const a = paceToSec(t.from), b = paceToSec(t.to); return { slow: Math.max(a, b), fast: Math.min(a, b) }; }
  return null;
}
function flatten(steps) {
  const out = [];
  for (const s of steps) {
    if (s.kind === "repeat") for (let i = 0; i < (s.times || 1); i++) out.push(...flatten(s.steps || []));
    else out.push(s);
  }
  return out;
}
function stepMetrics(s, paces) {
  const tp = targetPaces(s.target, paces);
  const ef = paces.EF ? (paceToSec(paces.EF[0]) + paceToSec(paces.EF[1])) / 2 : 310;
  const p = tp ? (tp.slow + tp.fast) / 2 : ef;
  const d = s.dur || {};
  if (s.kind === "rest") return { sec: d.type === "time" ? d.value : 0, m: 0, p };
  if (d.type === "distance") return { sec: (d.value / 1000) * p, m: d.value, p };
  if (d.type === "time") return { sec: d.value, m: (d.value / p) * 1000, p };
  return { sec: 0, m: 0, p };
}
function estimateText(steps, paces) {
  let sec = 0, m = 0;
  for (const s of flatten(steps)) { const x = stepMetrics(s, paces); sec += x.sec; m += x.m; }
  return `≈ ${km(m / 1000)} km · ≈ ${dur(sec)}`;
}
function zoneColor(s) {
  if (s.target?.pace) return ZONE_COLORS[s.target.pace] || "#888";
  if (s.target?.hr) return ["#94a3b8", "#3b82f6", "#22c55e", "#f59e0b", "#e11d48"][s.target.hr - 1] || "#888";
  if (s.target?.from) return "#14b8a6";
  return s.kind === "recovery" || s.kind === "rest" ? "#cbd5e1" : "#64748b";
}
function profileHtml(steps, paces) {
  const fl = flatten(steps);
  const mets = fl.map((s) => stepMetrics(s, paces));
  const total = mets.reduce((a, x) => a + x.sec, 0) || 1;
  const pmax = 420, pmin = 190;
  return `<div class="profile">${fl.map((s, i) => {
    const hgt = Math.max(18, Math.min(100, ((pmax - mets[i].p) / (pmax - pmin)) * 100));
    return `<i title="${esc(stepLabel(s))}" style="flex:${mets[i].sec / total};height:${hgt}%;background:${zoneColor(s)}"></i>`;
  }).join("")}</div>`;
}
const KIND_LABELS = { warmup: "Échauffement", run: "Course", recovery: "Récup", cooldown: "Retour calme", rest: "Repos" };
function stepLabel(s) {
  const d = s.dur || {};
  const amount = d.type === "distance" ? (d.value >= 1000 ? `${km(d.value / 1000, d.value % 1000 ? 1 : 0)} km` : `${d.value} m`) : d.type === "time" ? dur(d.value) : "jusqu'au lap";
  let tgt = "";
  if (s.target?.pace) tgt = ` · ${s.target.pace}`;
  else if (s.target?.from) tgt = ` · ${s.target.from}–${s.target.to}/km`;
  else if (s.target?.hr) tgt = ` · FC Z${s.target.hr}`;
  return `${KIND_LABELS[s.kind] || s.kind} ${amount}${tgt}`;
}
function stepsReadable(steps, paces) {
  const line = (s) => {
    const tp = targetPaces(s.target, paces);
    return `<div class="row" style="padding:5px 0"><span class="dot" style="background:${zoneColor(s)}"></span><span>${esc(stepLabel(s))}</span><span class="spacer"></span><span class="num small muted">${tp ? pace(tp.slow) + "–" + pace(tp.fast) : ""}</span></div>${s.note ? `<div class="small muted" style="margin-left:16px">${esc(s.note)}</div>` : ""}`;
  };
  return steps.map((s) => s.kind === "repeat"
    ? `<div class="repeat" style="margin:6px 0"><div class="repeat-head">${s.times} ×</div>${(s.steps || []).map(line).join("")}</div>`
    : line(s)).join("");
}

function targetValue(t) {
  if (!t) return "none";
  if (t.pace) return "p:" + t.pace;
  if (t.hr) return "hr:" + t.hr;
  if (t.from) return "custom";
  return "none";
}
function stepEditor(container, work, paces, onChange) {
  const zoneOpts = Object.keys(paces).map((k) => `<option value="p:${k}">${k} (${paces[k][0]}–${paces[k][1]})</option>`).join("");
  const hrOpts = [1, 2, 3, 4, 5].map((z) => `<option value="hr:${z}">FC zone ${z}</option>`).join("");

  const stepHtml = (s, path) => {
    const d = s.dur || { type: "lap" };
    const val = d.type === "distance" ? String(d.value / 1000).replace(".", ",") : d.type === "time" ? dur(d.value) : "";
    const tv = targetValue(s.target);
    return h`<div class="step" style="border-left-color:${zoneColor(s)}" data-path="${path}">
      <div class="step-row">
        <select data-f="kind">${Object.entries(KIND_LABELS).map(([k, l]) => `<option value="${k}" ${k === s.kind ? "selected" : ""}>${l}</option>`).join("")}</select>
        <select data-f="dtype"><option value="distance" ${d.type === "distance" ? "selected" : ""}>km</option><option value="time" ${d.type === "time" ? "selected" : ""}>durée</option><option value="lap" ${d.type === "lap" ? "selected" : ""}>lap</option></select>
        ${d.type !== "lap" ? `<input class="val num" data-f="val" value="${val}" placeholder="${d.type === "time" ? "mm:ss" : "km"}" inputmode="decimal">` : ""}
        <span class="step-actions"><button data-a="up" title="Monter">↑</button><button data-a="down" title="Descendre">↓</button><button data-a="del" title="Supprimer">✕</button></span>
      </div>
      <div class="step-row">
        <select data-f="target"><option value="none" ${tv === "none" ? "selected" : ""}>Sans cible</option>${zoneOpts.replace(`value="${tv}"`, `value="${tv}" selected`)}${hrOpts.replace(`value="${tv}"`, `value="${tv}" selected`)}<option value="custom" ${tv === "custom" ? "selected" : ""}>Allure perso…</option></select>
        ${tv === "custom" ? `<input class="pace num" data-f="from" value="${esc(s.target.from)}" placeholder="4:20"> → <input class="pace num" data-f="to" value="${esc(s.target.to)}" placeholder="4:10"> /km` : ""}
      </div>
    </div>`;
  };

  const draw = () => {
    container.innerHTML = `<div class="steps">${work.steps.map((s, i) => s.kind === "repeat"
      ? h`<div class="repeat" data-path="${i}"><div class="repeat-head">Répéter <input class="num" type="number" min="1" data-f="times" value="${s.times}"> fois
          <span class="step-actions"><button data-a="up">↑</button><button data-a="down">↓</button><button data-a="del">✕</button></span></div>
          ${(s.steps || []).map((c, j) => stepHtml(c, `${i}.${j}`)).join("")}
          <div class="add-row"><button class="btn sm" data-add="run" data-in="${i}">+ Effort</button><button class="btn sm" data-add="recovery" data-in="${i}">+ Récup</button></div></div>`
      : stepHtml(s, String(i))).join("")}
      <div class="add-row"><button class="btn sm" data-add="warmup">+ Échauffement</button><button class="btn sm" data-add="run">+ Course</button><button class="btn sm" data-add="repeat">+ Bloc répété</button><button class="btn sm" data-add="cooldown">+ Retour calme</button></div></div>`;
    onChange && onChange();
  };

  const get = (path) => {
    const [a, b] = path.split(".").map(Number);
    return b === undefined ? { list: work.steps, i: a } : { list: work.steps[a].steps, i: b };
  };
  const defStep = (kind) => ({
    warmup: { kind: "warmup", dur: { type: "distance", value: 3000 }, target: { pace: "EF" } },
    cooldown: { kind: "cooldown", dur: { type: "distance", value: 2000 }, target: { pace: "EF" } },
    run: { kind: "run", dur: { type: "distance", value: 1000 }, target: { pace: "SEUIL" } },
    recovery: { kind: "recovery", dur: { type: "time", value: 90 }, target: { pace: "RECUP" } },
    repeat: { kind: "repeat", times: 5, steps: [{ kind: "run", dur: { type: "distance", value: 1000 }, target: { pace: "VMA" } }, { kind: "recovery", dur: { type: "time", value: 90 }, target: { pace: "RECUP" } }] },
  }[kind]);

  container.addEventListener("change", (e) => {
    const f = e.target.dataset.f; if (!f || !e.target.isConnected) return;
    const host = e.target.closest("[data-path]");
    const { list, i } = get(host.dataset.path);
    const s = list[i];
    const v = e.target.value;
    if (f === "times") s.times = Math.max(1, parseInt(v) || 1);
    if (f === "kind") s.kind = v;
    if (f === "dtype") s.dur = v === "distance" ? { type: "distance", value: 1000 } : v === "time" ? { type: "time", value: 300 } : { type: "lap" };
    if (f === "val") {
      if (s.dur.type === "distance") s.dur.value = Math.round(parseFloat(v.replace(",", ".")) * 1000) || 0;
      else { const parts = v.split(":").map(Number); s.dur.value = parts.length > 1 ? parts[0] * 60 + (parts[1] || 0) : Math.round((parseFloat(v.replace(",", ".")) || 0) * 60); }
    }
    if (f === "target") {
      if (v === "none") delete s.target;
      else if (v.startsWith("p:")) s.target = { pace: v.slice(2) };
      else if (v.startsWith("hr:")) s.target = { hr: Number(v.slice(3)) };
      else s.target = { from: "4:20", to: "4:10" };
    }
    if (f === "from" || f === "to") s.target[f] = v.trim();
    setTimeout(draw, 0);
  });
  container.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    e.preventDefault();
    if (b.dataset.add) {
      const st = defStep(b.dataset.add);
      if (b.dataset.in !== undefined) work.steps[Number(b.dataset.in)].steps.push(st);
      else {
        const cdIdx = work.steps.findIndex((x) => x.kind === "cooldown");
        if (b.dataset.add !== "cooldown" && cdIdx >= 0) work.steps.splice(cdIdx, 0, st); else work.steps.push(st);
      }
      draw(); return;
    }
    const a = b.dataset.a; if (!a) return;
    const { list, i } = get(b.closest("[data-path]").dataset.path);
    if (a === "del") list.splice(i, 1);
    if (a === "up" && i > 0) [list[i - 1], list[i]] = [list[i], list[i - 1]];
    if (a === "down" && i < list.length - 1) [list[i + 1], list[i]] = [list[i], list[i + 1]];
    draw();
  });
  draw();
}

// ---------------------------------------------------------------- CONSTRUCTEUR
const R = (km_, pace_) => ({ kind: "run", dur: { type: "distance", value: km_ * 1000 }, target: { pace: pace_ } });
const T = (min, kind, pace_) => ({ kind, dur: { type: "time", value: min * 60 }, ...(pace_ ? { target: { pace: pace_ } } : {}) });
const WU = (k = 3) => ({ kind: "warmup", dur: { type: "distance", value: k * 1000 }, target: { pace: "EF" } });
const CD = (k = 2) => ({ kind: "cooldown", dur: { type: "distance", value: k * 1000 }, target: { pace: "EF" } });
const TEMPLATES = {
  "Footing EF": { type: "EF", steps: [R(10, "EF")] },
  "Seuil 3 × 3 km": { type: "SEUIL", steps: [WU(), { kind: "repeat", times: 3, steps: [R(3, "SEUIL"), T(2, "recovery", "RECUP")] }, CD()] },
  "Seuil 2 × 5 km": { type: "SEUIL", steps: [WU(), { kind: "repeat", times: 2, steps: [R(5, "SEUIL"), T(3, "recovery", "RECUP")] }, CD()] },
  "VMA 10 × 400 m": { type: "VMA", steps: [WU(), { kind: "repeat", times: 10, steps: [{ kind: "run", dur: { type: "distance", value: 400 }, target: { from: "3:20", to: "3:10" } }, T(1.25, "recovery", "RECUP")] }, CD()] },
  "VMA 6 × 1000 m": { type: "VMA", steps: [WU(), { kind: "repeat", times: 6, steps: [R(1, "VMA"), T(1.5, "recovery", "RECUP")] }, CD()] },
  "Allure marathon 12 km": { type: "AM", steps: [WU(2), R(12, "AM"), CD(2)] },
  "SL 30 km dont 3 × 6 km AM": { type: "SL", steps: [WU(6), { kind: "repeat", times: 3, steps: [R(6, "AM"), { kind: "recovery", dur: { type: "distance", value: 1000 }, target: { pace: "EF" } }] }, CD(3)] },
  "Fartlek 10 × 1'/1'": { type: "VMA", steps: [WU(), { kind: "repeat", times: 10, steps: [T(1, "run", "VMA"), T(1, "recovery", "EF")] }, CD()] },
  "Côtes 10 × 45\"": { type: "VMA", steps: [WU(), { kind: "repeat", times: 10, steps: [{ kind: "run", dur: { type: "time", value: 45 }, note: "Côte, effort fort" }, { kind: "recovery", dur: { type: "lap" }, note: "Redescente trottinée, lap en bas" }] }, CD()] },
};

async function renderBuilder(view) {
  if (!state.paces) state.paces = (await api("/api/plan")).paces;
  if (!state.builder) state.builder = { name: "Seuil 3 × 3 km", date: today(), type: "SEUIL", description: "", steps: JSON.parse(JSON.stringify(TEMPLATES["Seuil 3 × 3 km"].steps)) };
  const b = state.builder;
  view.innerHTML = h`
  <div class="cols"><div>
    <div class="card">
      <h2>Créer une séance</h2>
      <label class="f">Partir d'un modèle<select id="b-tpl"><option value="">— choisir —</option>${Object.keys(TEMPLATES).map((k) => `<option>${esc(k)}</option>`).join("")}</select></label>
      <label class="f">Nom (affiché sur la montre)<input id="b-name" value="${esc(b.name)}" maxlength="60"></label>
      <div class="grid g2">
        <label class="f">Date<input type="date" id="b-date" value="${b.date}"></label>
        <label class="f">Type<select id="b-type">${TYPES.filter((t) => t !== "REPOS").map((t) => `<option value="${t}" ${t === b.type ? "selected" : ""}>${t} – ${TYPE_LABELS[t]}</option>`).join("")}</select></label>
      </div>
      <label class="f">Notes<textarea id="b-desc" placeholder="Consignes affichées sur la montre">${esc(b.description)}</textarea></label>
    </div>
    <div class="card section"><h2>Étapes</h2><div id="b-steps"></div></div>
  </div><div>
    <div class="card" style="position:sticky;top:70px">
      <h2>Aperçu</h2>
      <div id="b-prof"></div>
      <div id="b-est" class="num" style="font-size:20px;font-weight:800;margin:10px 0 4px"></div>
      <div id="b-read"></div>
      <label class="row small" style="margin-top:14px;gap:8px"><input type="checkbox" id="b-addplan" checked style="width:auto"> Ajouter aussi au plan</label>
      <div class="btns">
        <button class="btn primary" id="b-push">⌚ Envoyer sur Garmin</button>
        <button class="btn" id="b-save">Ajouter au plan seulement</button>
      </div>
      <p class="small muted">La séance apparaît dans le calendrier Garmin Connect à la date choisie ; elle se synchronise sur la montre à la prochaine connexion.</p>
    </div>
  </div></div>`;

  const refresh = () => {
    $("#b-prof").innerHTML = profileHtml(b.steps, state.paces);
    $("#b-est").textContent = estimateText(b.steps, state.paces);
    $("#b-read").innerHTML = stepsReadable(b.steps, state.paces);
  };
  stepEditor($("#b-steps"), b, state.paces, refresh);
  $("#b-tpl").onchange = (e) => {
    const t = TEMPLATES[e.target.value]; if (!t) return;
    Object.assign(b, { name: e.target.value, type: t.type, steps: JSON.parse(JSON.stringify(t.steps)) });
    renderBuilder(view);
  };
  $("#b-name").oninput = (e) => (b.name = e.target.value);
  $("#b-date").onchange = (e) => (b.date = e.target.value);
  $("#b-type").onchange = (e) => (b.type = e.target.value);
  $("#b-desc").oninput = (e) => (b.description = e.target.value);
  $("#b-push").onclick = async (e) => {
    e.target.disabled = true;
    try {
      await api("/api/workout/push", { method: "POST", body: { ...b, add_to_plan: $("#b-addplan").checked } });
      toast(`« ${b.name} » envoyée sur Garmin pour le ${fmtDay(b.date)} ⌚`); state.plan = null;
    } catch (ex) { toast(ex.message, true); } finally { e.target.disabled = false; }
  };
  $("#b-save").onclick = async () => {
    try { await api("/api/plan/session", { method: "POST", body: { date: b.date, type: b.type, title: b.name, steps: b.steps, description: b.description } }); toast("Ajoutée au plan"); state.plan = null; }
    catch (ex) { toast(ex.message, true); }
  };
}

// ---------------------------------------------------------------- COACH IA
const CTYPE = { morning: "Message du matin", session: "Analyse de séance", weekly: "Bilan de la semaine", answer: "Réponse", info: "Info" };
function md(text) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<i>$2</i>");
  return `<div class="md">${String(text || "").split(/\n{2,}/).map((block) => {
    const lines = block.split("\n");
    if (lines.every((l) => /^\s*[-•]\s+/.test(l))) return `<ul>${lines.map((l) => `<li>${inline(l.replace(/^\s*[-•]\s+/, ""))}</li>`).join("")}</ul>`;
    return `<p>${lines.map(inline).join("<br>")}</p>`;
  }).join("")}</div>`;
}
function propHtml(n, p) {
  const f = p.fields || {};
  const what = p.action === "create" ? `Ajouter ${f.date ? fmtDay(f.date) : ""} : ${esc(f.title || "séance")}`
    : p.action === "delete" ? `Supprimer la séance ${esc(p.session_id)}`
    : `Modifier ${f.date ? fmtDay(f.date) + " · " : ""}${esc(f.title || p.session_id)}`;
  const steps = f.steps && state.paces ? `<div class="small muted">${f.steps.length ? stepsReadable(f.steps, state.paces) + estimateText(f.steps, state.paces) : "sans étapes"}</div>` : "";
  return `<div class="prop ${p.status}"><div><b>${what}</b></div>${steps}${p.reason ? `<div class="small">${esc(p.reason)}</div>` : ""}
    ${p.status === "pending" ? `<div class="btns" style="margin-top:6px"><button class="btn sm primary" data-prop="${n.id}/${p.pid}" data-dec="accept">Accepter</button><button class="btn sm" data-prop="${n.id}/${p.pid}" data-dec="reject">Refuser</button></div>`
      : `<div class="small muted">${p.status === "accepted" ? "✓ Acceptée" : "Refusée"}</div>`}</div>`;
}
function noteHtml(n, opts = {}) {
  return `<div class="card cnote ${n.type} section" data-nid="${n.id}">
    <div class="meta">${!n.read ? `<span class="unread-dot"></span>` : ""}<span class="ctype">${CTYPE[n.type] || n.type}</span><span>${fmtDay(n.date)}</span><span class="spacer"></span>${n.session_id && !opts.noLink ? `<a href="#" data-opensess="${n.session_id}" class="small">voir la séance</a>` : ""}</div>
    ${n.title ? `<h3 style="margin-top:6px">${esc(n.title)}</h3>` : ""}
    ${md(n.body)}
    ${(n.proposals || []).length ? `<div class="section"><h2>Ajustements proposés</h2>${n.proposals.map((p) => propHtml(n, p)).join("")}
      ${n.proposals.filter((p) => p.status === "pending").length > 1 ? `<div class="btns"><button class="btn sm primary" data-propall="${n.id}">Tout accepter</button></div>` : ""}</div>` : ""}
  </div>`;
}
function bindNotes(el) {
  $$("[data-opensess]", el).forEach((a) => (a.onclick = (e) => { e.preventDefault(); showSession(a.dataset.opensess); }));
  $$("[data-prop]", el).forEach((b) => (b.onclick = () => decideProposal(b.dataset.prop, b.dataset.dec, b)));
  $$("[data-propall]", el).forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    for (const x of $$(`[data-prop^="${b.dataset.propall}/"][data-dec="accept"]`, el)) await decideProposal(x.dataset.prop, "accept", x, true);
    toast("Ajustements appliqués"); state.plan = null; render();
  }));
}
async function decideProposal(key, dec, btn, silent = false) {
  const [nid, pid] = key.split("/");
  if (btn) btn.disabled = true;
  try {
    const r = await api(`/api/coach/proposals/${nid}/${pid}`, { method: "POST", body: { decision: dec } });
    if (!silent) { toast(dec === "accept" ? "Ajustement appliqué au plan" + (r.garmin_synced ? " · montre mise à jour ⌚" : "") : "Proposition refusée"); state.plan = null; render(); }
  } catch (e) { toast(e.message, true); if (btn) btn.disabled = false; }
}
async function updateCoachBadge(n) {
  if (n == null) { try { n = (await api("/api/coach")).unread; } catch { return; } }
  $$("[data-coach-badge]").forEach((b) => { b.textContent = n; b.classList.toggle("hidden", !n); });
}
$("#btn-coach").addEventListener("click", () => setView("coach"));

async function renderCoach(view) {
  const C = await api("/api/coach");
  if (!state.paces) state.paces = (await api("/api/plan")).paces;
  const f = state.coachFilter || "all";
  const notes = C.notes.filter((n) => f === "all" || n.type === f);
  const pending = C.questions.filter((q) => !q.answered);
  const age = C.context_age_min;
  view.innerHTML = h`
    <div class="row between wrap" style="margin-bottom:8px"><a class="btn sm" href="/api/report/weekly" target="_blank">✉️ Aperçu du mail hebdo</a>
      <span class="small muted">Passages : ${C.runs.join(" et ")} chaque jour${age != null ? ` · données transmises il y a ${age < 60 ? Math.round(age) + " min" : Math.round(age / 60) + " h"}` : ""}</span></div>
    <div class="card">
      <h2>Poser une question</h2>
      <textarea id="cq-text" placeholder="Ex. « Grosse fatigue ce matin, je garde le seuil de demain ? » ou « Quelle allure pour la sortie longue de lundi ? »" style="width:100%;min-height:80px"></textarea>
      <div class="btns"><button class="btn primary" id="cq-send">Envoyer au coach</button></div>
      <p class="small muted" style="margin:6px 0 0">Réponse au prochain passage (${C.runs.join(" ou ")}). Pour une réponse immédiate, pose-la-moi directement dans Claude.</p>
      ${pending.length ? `<div class="section"><h2>En attente de réponse</h2>${pending.map((q) => `<div class="q-pending section" style="margin-top:6px"><span style="flex:1">${esc(q.text)}<div class="small muted">${esc(q.created_at.replace("T", " "))}</div></span><button class="btn sm" data-delq="${q.id}">✕</button></div>`).join("")}</div>` : ""}
    </div>
    <div class="row between wrap section"><div class="seg" id="cf">${[["all", "Tout"], ["morning", "Matin"], ["session", "Séances"], ["weekly", "Bilans"], ["answer", "Réponses"]].map(([k, l]) => `<button data-f="${k}" class="${k === f ? "on" : ""}">${l}</button>`).join("")}</div></div>
    ${notes.length ? notes.map((n) => noteHtml(n)).join("") : `<div class="card empty section">Pas encore de message du coach.<br><span class="small">Premier passage à ${C.runs[0]} ou ${C.runs[1]}.</span></div>`}`;
  $("#cq-send").onclick = async () => {
    const text = $("#cq-text").value.trim(); if (!text) return;
    try { await api("/api/coach/questions", { method: "POST", body: { text } }); toast("Question transmise au coach"); render(); } catch (e) { toast(e.message, true); }
  };
  $$("[data-delq]", view).forEach((b) => (b.onclick = async () => { await api(`/api/coach/questions/${b.dataset.delq}`, { method: "DELETE" }); render(); }));
  $$("#cf button", view).forEach((b) => (b.onclick = () => { state.coachFilter = b.dataset.f; render(); }));
  bindNotes(view);
  const unreadIds = C.notes.filter((n) => !n.read).map((n) => n.id);
  if (unreadIds.length) { await api("/api/coach/read", { method: "POST", body: { ids: unreadIds } }); updateCoachBadge(0); }
}

// ---------------------------------------------------------------- JOUR J
async function renderRace(view) {
  const R = await api("/api/race");
  const c = R.cfg, P = R.pace, N = R.nutrition, pr = R.predictions;
  state.race = R;
  const predRows = [
    ["Objectif", pr.goal_s, "Ton chrono cible"],
    ["Avec la météo prévue", P.target_s, P.heat_factor > 1 ? `+${km((P.heat_factor - 1) * 100)} % à ${c.temp_c} °C` : `${c.temp_c ?? "—"} °C : pas d'impact`],
    ["Formule de Riegel", pr.riegel_s, `depuis ton semi ${esc(c.ref_half)} (souvent optimiste)`],
    ["Règle prudente", pr.conservative_s, "semi × 2 + 10 min"],
    ["Prédiction Garmin", pr.garmin_s, "selon ta montre"],
  ].filter((r) => r[1]);
  const daysTo = Math.round((parseD(c.date) - parseD(today())) / 864e5);
  view.innerHTML = h`
  ${raceNutriSwitch("race")}
  <div class="card hero">
    <div class="row between"><div><div class="muted small">${esc(c.name)} · ${fmtDay(c.date)} · départ ${esc(c.start_time)}${c.city ? " · " + esc(c.city) : ""}</div>
      <div class="hero-big num">${esc(c.goal)}</div><div class="small">${esc(P.strategy_label)} · ${P.avg_pace}/km de moyenne${P.heat_factor > 1 ? ` · plan calé sur <b>${P.target}</b> (${c.temp_c} °C)` : ""}</div></div>
      <div style="text-align:right"><div class="muted small">Dans</div><div style="font-size:28px;font-weight:900;white-space:nowrap" class="num">J-${daysTo}</div></div></div>
    <div class="hero-grid">
      <div><span>Passage semi</span><b class="num">${P.half}</b></div>
      <div><span>Arrivée</span><b class="num">${P.rows[P.rows.length - 1].clock}</b></div>
      <div><span>Gels</span><b class="num">${N.gel_count} + 1</b></div>
    </div>
  </div>

  <div class="cols section"><div>
    <div class="card">
      <div class="row between wrap"><h2 style="margin:0">Plan d'allure</h2>
        <div class="row"><button class="btn sm" id="rc-print">🖨 Bracelet</button><button class="btn sm primary" id="rc-push">⌚ ${R.race_session?.garmin_workout_id ? "Renvoyer" : "Envoyer"} sur la montre</button></div></div>
      <div class="table-wrap" style="margin-top:10px"><table>
        <thead><tr><th>Km</th><th class="r">Passage</th><th class="r">Heure</th><th class="r">Tronçon</th><th class="r">Allure</th></tr></thead>
        <tbody>${P.splits5.map((s) => `<tr><td><b>${String(s.km).replace(".", ",")}</b></td><td class="r num"><b>${s.cum}</b></td><td class="r num muted">${s.clock}</td><td class="r num">${s.split}</td><td class="r num">${s.pace}</td></tr>`).join("")}</tbody>
      </table></div>
      <div class="chart-box" style="margin-top:12px;height:200px"><canvas id="c-race"></canvas></div>
      <details style="margin-top:10px"><summary class="small" style="cursor:pointer">Détail kilomètre par kilomètre</summary>
        <div class="table-wrap"><table><thead><tr><th>Km</th><th class="r">Allure</th><th class="r">Cumul</th><th class="r">Heure</th>${c.profile ? `<th class="r">D+/D−</th>` : ""}<th>Notes</th></tr></thead>
        <tbody>${P.rows.map((r) => `<tr><td>${String(r.km).replace(".", ",")}</td><td class="r num">${r.pace}</td><td class="r num">${r.cum}</td><td class="r num muted">${r.clock}</td>${c.profile ? `<td class="r num small">${r.gain != null ? `+${Math.round(r.gain)}/−${Math.round(r.loss)}` : ""}</td>` : ""}<td>${r.notes.map((n) => `<span class="note-pill ${n === "Ravito" ? "rav" : ""}">${esc(n)}</span>`).join("")}</td></tr>`).join("")}</tbody></table></div>
      </details>
      <p class="small muted" style="margin-bottom:0">Sur la montre : 9 blocs de 5 km avec une fourchette de ±4 s/km, les gels sont indiqués dans chaque bloc. Lance-la depuis Entraînement → Calendrier le jour J.</p>
    </div>

    <div id="rc-pred"></div>

    <details class="card section" id="rc-settings">
      <summary>Réglages de la course</summary>
      <div class="grid g2" style="margin-top:12px">
        <label class="f">Nom<input data-k="name" value="${esc(c.name)}"></label>
        <label class="f">Ville (pour la météo)<input data-k="city" value="${esc(c.city || "")}" placeholder="ex. Lyon"></label>
        <label class="f">Date<input type="date" data-k="date" value="${c.date}"></label>
        <label class="f">Heure de départ<input type="time" data-k="start_time" value="${c.start_time}"></label>
        <label class="f">Objectif (h:mm:ss)<input data-k="goal" value="${esc(c.goal)}"></label>
        <label class="f">Stratégie<select data-k="strategy">${Object.entries(R.strategies).map(([k, l]) => `<option value="${k}" ${k === c.strategy ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label class="f">Température prévue (°C)<input type="number" data-k="temp_c" value="${c.temp_c ?? ""}"></label>
        <label class="f">Semi de référence<input data-k="ref_half" value="${esc(c.ref_half || "")}"></label>
        <label class="f">Poids (kg)<input type="number" data-k="weight_kg" value="${c.weight_kg}"></label>
        <label class="f">Glucides par gel (g)<input type="number" data-k="gel_carbs" value="${c.gel_carbs}"></label>
        <label class="f">Objectif glucides (g/h)<input type="number" data-k="carbs_per_hour" value="${c.carbs_per_hour}"></label>
        <label class="f">1er gel après (min)<input type="number" data-k="first_gel_min" value="${c.first_gel_min}"></label>
        <label class="f">Gel caféiné à partir du km (0 = non)<input type="number" data-k="caffeine_from_km" value="${c.caffeine_from_km}"></label>
        <label class="f">Ravitos (km)<input data-k="ravitos" value="${(c.ravitos || []).join(", ")}"></label>
      </div>
      <label class="f">Parcours GPX (pour adapter l'allure au dénivelé)<input type="file" id="rc-gpx" accept=".gpx,application/gpx+xml"></label>
      ${c.profile ? `<p class="small">Parcours importé : ${km(c.gpx_km, 1)} km, +${c.gpx_gain} m / −${c.gpx_loss} m <button class="btn sm danger" id="rc-gpx-del">Retirer</button></p>` : ""}
      <div class="btns"><button class="btn primary" id="rc-save">Enregistrer</button><button class="btn" id="rc-weather">☁️ Météo du jour J</button></div>
      <div id="rc-weather-out" class="small" style="margin-top:8px"></div>
    </details>
  </div><div>
    <div class="card">
      <h2>Nutrition</h2>
      <div class="small muted" style="margin-bottom:8px">Charge glucidique (${km(N.weight_kg, 0)} kg)</div>
      <div class="grid" style="grid-template-columns:repeat(3,1fr)">${N.loading.map((l) => `<div class="load-card"><div class="small muted">${l.label} · ${fmtDay(l.date)}</div><b class="num">${l.grams} g</b><div class="small muted">${l.g_per_kg} g/kg</div></div>`).join("")}</div>
      <ul class="review-list small">${N.loading.map((l) => `<li><b>${l.label}</b> : ${esc(l.note)}</li>`).join("")}</ul>
      <details style="margin-top:8px"><summary class="small" style="cursor:pointer">Repères pour compter</summary>
        <table class="small"><tbody>${N.loading_foods.map(([f, v]) => `<tr><td>${esc(f)}</td><td class="r muted">${esc(v)}</td></tr>`).join("")}</tbody></table></details>

      <h2 style="margin-top:16px">Matin de course</h2>
      <div class="gel-line"><div class="gel-n" style="background:var(--info)">☕</div><div><b>${N.breakfast.time}</b> · petit-déj ≈ ${N.breakfast.grams} g de glucides<div class="small muted">${N.breakfast.examples.map(esc).join(" · ")}</div></div></div>
      ${N.pre_start.map((x) => `<div class="gel-line"><div class="gel-n" style="background:var(--muted)">⏱</div><div><b>${x.when}</b> · ${esc(x.what)}</div></div>`).join("")}

      <h2 style="margin-top:16px">Pendant la course</h2>
      ${N.gels.map((g) => `<div class="gel-line"><div class="gel-n ${g.caffeine ? "caf" : ""}">${g.n}</div><div style="flex:1"><b>Km ${String(g.km).replace(".", ",")}</b> · ${g.clock} <span class="muted small">(${g.elapsed})</span>${g.caffeine ? ` <span class="note-pill">caféine</span>` : ""}<div class="small muted">${g.with_water ? "Avec l'eau du ravito" : "Hors ravito : quelques gorgées d'eau portée ou au ravito suivant"}</div></div></div>`).join("")}
      <div class="kv" style="margin-top:10px">
        <div><span>Glucides</span><b class="num">${N.carbs_total} g</b><span>≈ ${N.carbs_per_hour_real} g/h (+ gel de départ)</span></div>
        <div><span>Boisson</span><b class="num">${N.fluid_ml_h} ml/h</b><span>par petites gorgées</span></div>
        <div><span>Sodium</span><b class="num">${N.sodium_mg_h} mg/h</b><span>boisson d'effort ou pastilles</span></div>
      </div>
      <div class="tip">💡 Répète exactement ce protocole (petit-déj, gels, timing) sur la séance clé du 25 octobre. Rien de nouveau le jour J.</div>
    </div>

    <div class="card section"><h2>Dernière semaine</h2>
      ${R.last_week.map((s) => `<div class="gel-line"><span class="chip ${s.type}">${s.type}</span><div style="flex:1"><b>${fmtDay(s.date)}</b> · ${esc(s.title)}${N.loading.find((l) => l.date === s.date) ? `<div class="small" style="color:var(--accent)">Charge glucidique : ${N.loading.find((l) => l.date === s.date).grams} g</div>` : ""}${s.description ? `<div class="small muted">${esc(s.description)}</div>` : ""}</div></div>`).join("")}
    </div>

    <div class="card section"><h2>Checklist du sac</h2>
      ${R.checklist.map((g) => `<div class="small muted" style="margin-top:8px;font-weight:700">${esc(g.cat)}</div>${g.items.map((it) => `<label class="check ${it.done ? "done" : ""}"><input type="checkbox" data-cl="${it.id}" ${it.done ? "checked" : ""}><span>${esc(it.label)}</span></label>`).join("")}`).join("")}
    </div>
  </div></div>`;

  // graphique allure / dénivelé
  if (typeof Chart !== "undefined") {
    chartDefaults();
    const ds = [{ type: "bar", label: "Allure", data: P.rows.map((r) => r.pace_s), backgroundColor: P.rows.map((r) => (r.notes.some((n) => n.startsWith("Gel")) ? css("--accent") : "rgba(252,82,0,.35)")), borderRadius: 3, yAxisID: "y" }];
    if (c.profile) ds.push({ type: "line", label: "Altitude", data: P.rows.map((r) => r.ele), borderColor: css("--muted"), pointRadius: 0, fill: false, tension: 0.3, yAxisID: "y2" });
    const ys = P.rows.map((r) => r.pace_s);
    mkChart($("#c-race"), {
      data: { labels: P.rows.map((r) => Math.ceil(r.km)), datasets: ds },
      options: { scales: { y: { reverse: true, min: Math.min(...ys) - 6, max: Math.max(...ys) + 6, ticks: { callback: (v) => pace(v) } }, y2: { display: !!c.profile, position: "right", grid: { display: false } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 9 } } },
        plugins: { tooltip: { callbacks: { label: (x) => (x.dataset.label === "Allure" ? `${pace(x.raw)}/km · ${P.rows[x.dataIndex].cum}` : `${x.raw} m`) } } } },
    });
  }

  // actions
  bindRaceNutriSwitch(view);
  predictionSection($("#rc-pred", view));
  $("#rc-print").onclick = () => printBand(R);
  $("#rc-push").onclick = async (e) => {
    e.target.disabled = true;
    try { const r = await api("/api/race/push", { method: "POST" }); toast(r.pushed ? "Séance course envoyée sur la montre ⌚" : "Séance course enregistrée dans le plan (Garmin non connecté)"); state.plan = null; }
    catch (ex) { toast(ex.message, true); } finally { e.target.disabled = false; }
  };
  $("#rc-save").onclick = async () => {
    const body = {};
    $$("[data-k]", view).forEach((i) => {
      const k = i.dataset.k; let v = i.value.trim();
      if (["temp_c", "weight_kg", "gel_carbs", "carbs_per_hour", "first_gel_min", "caffeine_from_km"].includes(k)) v = v === "" ? null : Number(v.replace(",", "."));
      if (k === "ravitos") v = v.split(/[,; ]+/).map(Number).filter((x) => x > 0);
      body[k] = v;
    });
    try { await api("/api/race", { method: "PUT", body }); toast("Réglages enregistrés"); state.plan = null; render(); }
    catch (ex) { toast(ex.message, true); }
  };
  $("#rc-gpx").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const text = await f.text();
    try {
      const res = await fetch("/api/race/gpx", { method: "POST", headers: { "X-Pin": PIN, "Content-Type": "application/gpx+xml" }, body: text });
      const d = await res.json(); if (!res.ok) throw new Error(d.detail);
      toast(`Parcours importé : +${d.gain} m / −${d.loss} m`); render();
    } catch (ex) { toast(ex.message, true); }
  };
  const gd = $("#rc-gpx-del");
  if (gd) gd.onclick = async () => { await api("/api/race/gpx", { method: "DELETE" }); render(); };
  $("#rc-weather").onclick = async () => {
    const out = $("#rc-weather-out"); out.textContent = "Recherche de la prévision…";
    try {
      const w = await api("/api/race/weather");
      if (!w.available) { out.textContent = w.message; return; }
      out.innerHTML = `<table><thead><tr><th>Heure</th><th class="r">Temp.</th><th class="r">Rosée</th><th class="r">Vent</th><th class="r">Pluie</th></tr></thead><tbody>${w.hours.map((x) => `<tr><td>${x.time}</td><td class="r num">${x.temp} °C</td><td class="r num">${x.dew} °C</td><td class="r num">${x.wind} km/h</td><td class="r num">${x.rain ?? "—"} %</td></tr>`).join("")}</tbody></table>
        ${w.race_avg_temp != null ? `<button class="btn sm" id="rc-use-temp" style="margin-top:6px">Utiliser ${w.race_avg_temp} °C pour le plan</button>` : ""}`;
      const u = $("#rc-use-temp");
      if (u) u.onclick = async () => { await api("/api/race", { method: "PUT", body: { temp_c: w.race_avg_temp } }); render(); };
    } catch (ex) { out.textContent = ex.message; }
  };
  $$("[data-cl]", view).forEach((cb) => (cb.onchange = async () => {
    cb.closest(".check").classList.toggle("done", cb.checked);
    try { await api("/api/race/checklist", { method: "PUT", body: { [cb.dataset.cl]: cb.checked } }); } catch (ex) { toast(ex.message, true); }
  }));
}

function printBand(R) {
  const P = R.pace, c = R.cfg;
  const rows = P.rows;
  const cols = [rows.slice(0, 14), rows.slice(14, 28), rows.slice(28)];
  $("#print-area").innerHTML = `<div class="band-title">${esc(c.name)} · objectif ${esc(c.goal)} · ${esc(P.strategy_label)} · départ ${esc(c.start_time)}</div>
    <div class="band">${cols.map((col) => `<table><thead><tr><th>Km</th><th>Passage</th><th>Allure</th><th></th></tr></thead><tbody>${col.map((r) => `<tr class="${Number.isInteger(r.km) && r.km % 5 === 0 ? "k5" : ""}"><td>${String(r.km).replace(".", ",")}</td><td>${r.cum}</td><td>${r.pace}</td><td>${r.notes.filter((n) => n.startsWith("Gel")).map(() => "G").join("")}${r.notes.includes("Ravito") ? "💧" : ""}</td></tr>`).join("")}</tbody></table>`).join("")}</div>
    <p style="margin-top:4mm">Semi : <b>${P.half}</b> · G = gel · 💧 = ravito · Découpe chaque colonne et colle-la sur ton avant-bras (scotch transparent).</p>`;
  window.print();
}

// ---------------------------------------------------------------- ANALYSE
function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function chartDefaults() {
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--line");
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.animation = false;
}
function mkChart(el, cfg) { const c = new Chart(el, cfg); state.charts.push(c); return c; }
const shortD = (s) => { const d = parseD(s); return `${d.getDate()}/${d.getMonth() + 1}`; };

const hfr = (h) => (h == null ? "—" : `${Math.floor(h)}h${String(Math.round((h % 1) * 60)).padStart(2, "0")}`);
function renderSleepCard(box, S) {
  const toMin = (hhmm, bed) => { if (!hhmm) return null; const [a, b] = hhmm.split(":").map(Number); let v = a * 60 + b; if (v < 12 * 60) v += 24 * 60; return v - 18 * 60; };
  box.innerHTML = h`<h2>Sommeil</h2>
    <p style="margin:0 0 10px">${esc(S.message)}</p>
    <div class="kv">
      <div><span>Moyenne 7 j</span><b class="num">${hfr(S.avg7_h)}</b><span>objectif ${hfr(S.goal_h)}</span></div>
      <div><span>Moyenne 28 j</span><b class="num">${hfr(S.avg28_h)}</b><span>score 7 j ${S.score7 ?? "—"}</span></div>
      <div><span>Nuits &lt; 6 h (14 j)</span><b class="num" style="color:${S.short14 >= 3 ? "var(--bad)" : "inherit"}">${S.short14}</b><span>&nbsp;</span></div>
      <div><span>Dette 3 nuits</span><b class="num" style="color:${S.debt3_h > 3 ? "var(--warn)" : "inherit"}">${S.debt3_h != null ? km(S.debt3_h) + " h" : "—"}</b><span>vs objectif</span></div>
      <div><span>Coucher moyen</span><b class="num">${S.avg_bed || "—"}</b><span>conseillé ${S.target_bed || "—"}</span></div>
    </div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr));margin-top:12px">
      <div><div class="small muted">Durée (28 j)</div><div class="chart-box" style="height:190px"><canvas id="c-sl-dur"></canvas></div></div>
      <div><div class="small muted">Horaires (coucher → réveil)</div><div class="chart-box" style="height:190px"><canvas id="c-sl-time"></canvas></div></div>
    </div>
    <div class="section"><div class="small muted" style="margin-bottom:4px">Ta nuit de la veille et tes séances</div>
      <table><thead><tr><th>Nuit</th><th class="r">Séances</th><th class="r">Bilan moyen</th><th class="r">Ressenti</th></tr></thead>
      <tbody>${S.correlation.map((c) => `<tr><td>${c.bucket}</td><td class="r num">${c.n}</td><td class="r num">${c.score ?? "—"}</td><td class="r num">${c.rpe != null ? km(c.rpe) + "/10" : "—"}</td></tr>`).join("")}</tbody></table>
      <p class="small muted" style="margin:6px 0 0">Note ton ressenti après chaque séance : c'est ce qui rendra ce tableau parlant.</p></div>`;
  const ser = S.series;
  const lbl = ser.map((x) => shortD(x.date));
  mkChart($("#c-sl-dur", box), {
    data: { labels: lbl, datasets: [
      { type: "bar", label: "Sommeil", data: ser.map((x) => x.h), backgroundColor: ser.map((x) => (x.h == null ? "transparent" : x.h < 6 ? "#dc2626" : x.h < S.goal_h ? "#f59e0b" : "#16a34a")), borderRadius: 4 },
      { type: "line", label: "Objectif", data: ser.map(() => S.goal_h), borderColor: css("--muted"), borderDash: [4, 3], pointRadius: 0 },
    ] },
    options: { scales: { y: { min: 3, max: 10, ticks: { callback: (v) => v + " h" } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 7 } } },
      plugins: { tooltip: { callbacks: { label: (c) => (c.datasetIndex ? `Objectif ${hfr(S.goal_h)}` : `${hfr(c.raw)} · score ${ser[c.dataIndex].score ?? "—"}`) } } } },
  });
  const tb = toMin(S.target_bed);
  mkChart($("#c-sl-time", box), {
    data: { labels: lbl, datasets: [
      { type: "bar", label: "Nuit", data: ser.map((x) => (x.bed && x.wake ? [toMin(x.bed), toMin(x.wake)] : null)), backgroundColor: "#6366f1", borderRadius: 4, borderSkipped: false },
      ...(tb != null ? [{ type: "line", label: "Coucher conseillé", data: ser.map(() => tb), borderColor: "#16a34a", borderDash: [4, 3], pointRadius: 0 }] : []),
    ] },
    options: { scales: { y: { reverse: true, min: 3 * 60, max: 16 * 60, ticks: { stepSize: 120, callback: (v) => `${String(Math.floor((v / 60 + 18) % 24)).padStart(2, "0")}h` } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 7 } } },
      plugins: { tooltip: { callbacks: { label: (c) => (c.datasetIndex ? `Coucher conseillé ${S.target_bed}` : `${ser[c.dataIndex].bed} → ${ser[c.dataIndex].wake}`) } } } },
  });
}

async function renderData(view) {
  if (typeof Chart === "undefined") { view.innerHTML = `<div class="card empty">Graphiques indisponibles (pas d'accès internet pour charger Chart.js).</div>`; return; }
  chartDefaults();
  const days = state.trendDays || 28;
  view.innerHTML = h`
    <div class="row between wrap" style="margin-bottom:14px"><span class="muted small">Tendances sur ${days} jours</span>
      <div class="seg" id="seg-days">${[14, 28, 56, 90].map((d) => `<button data-d="${d}" class="${d === days ? "on" : ""}">${d} j</button>`).join("")}</div></div>
    <div class="card"><h2>Volume hebdomadaire</h2><div class="chart-box tall"><canvas id="c-week"></canvas></div>
      <div class="legend"><span><i style="background:var(--accent)"></i>Réalisé</span><span><i style="background:var(--card-2);border:1px dashed var(--muted)"></i>Prévu</span><span><i style="background:#0ea5e9"></i>Plus longue sortie</span></div></div>
    <div class="card section" id="sleep-card"><h2>Sommeil</h2><div class="muted small">Chargement…</div></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr));margin-top:12px">
      <div class="card"><h2>VFC (nuit)</h2><div class="chart-box"><canvas id="c-hrv"></canvas></div><div class="legend"><span><i style="background:rgba(22,163,74,.18)"></i>Zone de référence</span></div></div>
      <div class="card"><h2>FC de repos</h2><div class="chart-box"><canvas id="c-rhr"></canvas></div></div>
      <div class="card"><h2>Charge par jour</h2><div class="chart-box"><canvas id="c-load"></canvas></div></div>
    </div>
    <div class="card section"><h2>Efficacité aérobie (sorties faciles)</h2>
      <p class="small muted" style="margin-top:-4px">Mètres parcourus par battement cardiaque sur tes footings. Si la courbe monte, tu cours plus vite pour le même cardio : l'endurance progresse.</p>
      <div class="chart-box"><canvas id="c-eff"></canvas></div></div>
    <div class="card section"><h2>Allure moyenne vs FC (toutes les sorties)</h2><div class="chart-box"><canvas id="c-scatter"></canvas></div></div>`;
  $$("#seg-days button", view).forEach((b) => (b.onclick = () => { state.trendDays = Number(b.dataset.d); render(); }));

  const [weekly, trends, acts, sleepI] = await Promise.all([api("/api/weekly?weeks=16"), api(`/api/trends?days=${days}`), api(`/api/activities?days=${Math.max(days, 90)}`), api("/api/sleep").catch(() => null)]);
  const accent = css("--accent");
  if (sleepI) renderSleepCard($("#sleep-card"), sleepI);

  mkChart($("#c-week"), {
    type: "bar",
    data: {
      labels: weekly.map((w) => shortD(w.start)),
      datasets: [
        { label: "Prévu", data: weekly.map((w) => w.planned_km), backgroundColor: "transparent", borderColor: css("--muted"), borderWidth: 1.5, borderDash: [4, 3], borderRadius: 6, grouped: false, order: 2 },
        { label: "Réalisé", data: weekly.map((w) => (w.future ? null : w.km)), backgroundColor: accent, borderRadius: 6, grouped: false, order: 3, barPercentage: 0.7 },
        { label: "Plus longue", type: "line", data: weekly.map((w) => (w.future ? null : w.long_km)), borderColor: "#0ea5e9", backgroundColor: "#0ea5e9", pointRadius: 3, tension: 0.3, order: 1 },
      ],
    },
    options: { scales: { y: { beginAtZero: true, ticks: { callback: (v) => v + " km" } }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${c.raw == null ? "—" : km(c.raw)} km` } } } },
  });

  const labels = trends.map((t) => shortD(t.date));
  const last = [...trends].reverse().find((t) => t.hrv_baseline_low) || {};
  mkChart($("#c-hrv"), {
    type: "line",
    data: { labels, datasets: [
      { data: trends.map(() => last.hrv_baseline_high ?? null), borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: "rgba(22,163,74,.15)" },
      { data: trends.map(() => last.hrv_baseline_low ?? null), borderWidth: 0, pointRadius: 0 },
      { label: "VFC", data: trends.map((t) => t.hrv), borderColor: "#16a34a", backgroundColor: "#16a34a", tension: 0.3, pointRadius: 2, spanGaps: true },
      { label: "Moy. 7 j", data: trends.map((t) => t.hrv_weekly), borderColor: css("--muted"), borderDash: [4, 3], pointRadius: 0, tension: 0.3, spanGaps: true },
    ] },
    options: { scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } } }, plugins: { tooltip: { filter: (i) => i.datasetIndex >= 2 } } },
  });
  mkChart($("#c-rhr"), {
    type: "line",
    data: { labels, datasets: [{ label: "FC repos", data: trends.map((t) => t.rhr), borderColor: "#e11d48", backgroundColor: "#e11d48", tension: 0.3, pointRadius: 2, spanGaps: true }] },
    options: { scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { ticks: { callback: (v) => v + " bpm" } } } },
  });
  const loadByDay = {};
  acts.forEach((a) => { loadByDay[a.date] = (loadByDay[a.date] || 0) + (a.training_load || 0); });
  mkChart($("#c-load"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Charge", data: trends.map((t) => Math.round(loadByDay[t.date] || 0)), backgroundColor: accent, borderRadius: 4 }] },
    options: { scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } } } },
  });

  const efMin = paceToSec(state.paces?.EF?.[1] || "4:55") - 10;
  const easy = acts.filter((a) => a.is_run && a.avg_hr && a.pace_s && a.pace_s >= efMin && a.distance_km >= 5).reverse();
  mkChart($("#c-eff"), {
    type: "line",
    data: { labels: easy.map((a) => shortD(a.date)), datasets: [{ label: "m / battement", data: easy.map((a) => +((1000 / a.pace_s) * 60 / a.avg_hr).toFixed(2)), borderColor: "#0ea5e9", backgroundColor: "#0ea5e9", pointRadius: 3, tension: 0.35 }] },
    options: { scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } } },
      plugins: { tooltip: { callbacks: { afterLabel: (c) => { const a = easy[c.dataIndex]; return `${km(a.distance_km)} km · ${pace(a.pace_s)}/km · ${a.avg_hr} bpm`; } } } } },
  });
  const runs = acts.filter((a) => a.is_run && a.avg_hr && a.pace_s && a.pace_s < 480);
  mkChart($("#c-scatter"), {
    type: "scatter",
    data: { datasets: [{ data: runs.map((a) => ({ x: a.avg_hr, y: a.pace_s, a })), backgroundColor: runs.map((a) => (a.date >= iso(new Date(Date.now() - 21 * 864e5)) ? accent : "rgba(148,163,184,.6)")), pointRadius: 4 }] },
    options: { scales: { y: { reverse: true, ticks: { callback: (v) => pace(v) } }, x: { title: { display: true, text: "FC moyenne (bpm)" } } },
      plugins: { tooltip: { callbacks: { label: (c) => `${shortD(c.raw.a.date)} · ${esc(c.raw.a.name)} · ${pace(c.raw.y)}/km · ${c.raw.x} bpm` } } } },
  });
}

// ---------------------------------------------------------------- ACTIVITÉS
function actRow(a) {
  const ico = a.is_run ? (a.distance_km >= 18 ? "SL" : "CàP") : (a.type || "").slice(0, 3).toUpperCase();
  return h`<div class="act" data-aid="${a.id}"><div class="act-ico">${ico}</div><div class="act-main">
    <div class="act-name">${esc(a.name)}</div>
    <div class="act-stats"><span>${fmtDay(a.date)}</span><span><b>${km(a.distance_km, 2)}</b> km</span><span><b>${pace(a.pace_s)}</b>/km</span><span><b>${dur(a.duration_s)}</b></span>${a.avg_hr ? `<span>FC <b>${a.avg_hr}</b></span>` : ""}${a.training_load ? `<span>charge <b>${Math.round(a.training_load)}</b></span>` : ""}</div>
  </div></div>`;
}
async function renderActs(view) {
  const acts = await api("/api/activities?days=90");
  const f = state.actFilter;
  const list = acts.filter((a) => f === "all" || a.is_run);
  view.innerHTML = h`<div class="row between wrap" style="margin-bottom:12px"><span class="muted small">90 derniers jours</span>
    <div class="seg" id="seg-act"><button data-f="run" class="${f === "run" ? "on" : ""}">Course</button><button data-f="all" class="${f === "all" ? "on" : ""}">Tout</button></div></div>
    <div class="card">${list.length ? list.map(actRow).join("") : `<div class="empty">Aucune activité</div>`}</div>`;
  $$("#seg-act button", view).forEach((b) => (b.onclick = () => { state.actFilter = b.dataset.f; render(); }));
  $$(".act[data-aid]", view).forEach((r) => (r.onclick = () => showActivity(r.dataset.aid)));
}

async function showActivity(aid) {
  openModal(`<div class="skeleton">Chargement…</div>`);
  let d;
  try { d = await api(`/api/activity/${aid}`); } catch (e) { $("#modal-body").innerHTML = `<p>${esc(e.message)}</p>`; return; }
  const s = d.summary || {};
  const zTot = (d.hr_zones || []).reduce((a, z) => a + z.seconds, 0) || 1;
  const zc = ["#94a3b8", "#3b82f6", "#22c55e", "#f59e0b", "#e11d48"];
  const fastest = Math.min(...(d.laps || []).filter((l) => l.pace_s && l.distance_m > 300).map((l) => l.pace_s));
  $("#modal-body").innerHTML = h`
    <h3>${esc(d.name)}</h3>
    ${d.weather?.temp != null ? `<div class="small muted">${Math.round(d.weather.temp)}°C${d.weather.humidity ? ` · ${d.weather.humidity}% hum.` : ""}${d.weather.desc ? ` · ${esc(d.weather.desc)}` : ""}</div>` : ""}
    <div class="grid g4" style="margin-top:12px">
      ${tile("Distance", km(s.distance_km, 2), "", null, "km")}
      ${tile("Durée", dur(s.duration_s))}
      ${tile("Allure", s.distance_km ? pace(s.duration_s / s.distance_km) : "—", "", null, "/km")}
      ${tile("FC moy.", s.avg_hr ? Math.round(s.avg_hr) : null, s.max_hr ? `max ${Math.round(s.max_hr)}` : "")}
      ${tile("Cadence", s.cadence ? Math.round(s.cadence) : null, "", null, "ppm")}
      ${tile("Charge", s.training_load ? Math.round(s.training_load) : null, s.aerobic_te ? `TE aéro ${Number(s.aerobic_te).toFixed(1)} · ana ${Number(s.anaerobic_te || 0).toFixed(1)}` : "")}
      ${tile("Dénivelé +", s.elev_gain != null ? Math.round(s.elev_gain) : null, "", null, "m")}
      ${tile("Foulée", s.stride_m ? Number(s.stride_m > 10 ? s.stride_m / 100 : s.stride_m).toFixed(2) : null, s.gct_ms ? `contact ${Math.round(s.gct_ms)} ms` : "", null, "m")}
    </div>
    <div id="act-map"></div>
    ${d.hr_zones?.length ? h`<div class="section"><h2>Zones cardiaques</h2>
      <div class="profile" style="height:14px;align-items:stretch">${d.hr_zones.map((z, i) => `<i style="flex:${z.seconds / zTot};background:${zc[i] || "#888"}"></i>`).join("")}</div>
      <div class="legend">${d.hr_zones.map((z, i) => `<span><i style="background:${zc[i]}"></i>Z${z.zone} ${Math.round((z.seconds / zTot) * 100)}% · ${dur(z.seconds)}</span>`).join("")}</div></div>` : ""}
    ${d.laps?.length ? h`<div class="section"><h2>Tours</h2><div class="table-wrap"><table>
      <thead><tr><th>#</th><th class="r">Dist.</th><th class="r">Temps</th><th class="r">Allure</th><th class="r">FC</th><th class="r">Cad.</th></tr></thead>
      <tbody>${d.laps.map((l) => `<tr><td>${l.n}</td><td class="r num">${l.distance_m >= 1000 ? km(l.distance_m / 1000, 2) + " km" : l.distance_m + " m"}</td><td class="r num">${dur(l.duration_s)}</td><td class="r num" style="${l.pace_s === fastest ? "color:var(--accent);font-weight:700" : ""}">${pace(l.pace_s)}</td><td class="r num">${l.avg_hr ? Math.round(l.avg_hr) : "—"}</td><td class="r num">${l.cadence ? Math.round(l.cadence) : "—"}</td></tr>`).join("")}</tbody>
    </table></div></div>` : ""}`;
  trackMap($("#act-map"), aid);
}

// ---------------------------------------------------------------- RÉGLAGES
async function showSettings() {
  const [st, plan, cfg, bk] = await Promise.all([api("/api/status"), api("/api/plan"), api("/api/settings"), api("/api/backup").catch(() => null)]);
  openModal(h`
    <h3>Réglages</h3>
    <div class="section"><h2>Garmin</h2>
      <div class="row between"><span>${st.connected ? `Connecté${st.name ? " · " + esc(st.name) : ""}` : "Non connecté"}${st.demo ? " (mode démo)" : ""}</span>
      ${st.connected ? `<button class="btn sm danger" id="st-logout">Déconnecter</button>` : `<button class="btn sm primary" id="st-login">Connecter</button>`}</div></div>
    <div class="section"><h2>Accès depuis le téléphone</h2>
      <p class="small">Sur le même wifi, ouvre <b class="num">${esc(st.lan_url)}</b> puis « Partager → Sur l'écran d'accueil ».<br>Code PIN : <b class="num" style="font-size:18px">${esc(st.pin)}</b></p></div>
    <div class="section"><h2>Sauvegarde</h2>
      <p class="small" id="st-bk">${!bk ? "—" : bk.error && !bk.ok ? esc(bk.error) : bk.last ? `Dernière sauvegarde : <b>${fmtDay(bk.last)} à ${bk.last.slice(11, 16)}</b> (${String(bk.size_mb).replace(".", ",")} Mo, ${bk.count} gardée${bk.count > 1 ? "s" : ""})<br><span class="muted">Dans ${esc(bk.dir)}</span>` : "Aucune sauvegarde pour l'instant."}</p>
      <p class="small muted" style="margin-top:-4px">Tout Élan (code + tes données) est copié chaque jour dans iCloud Drive. Si ton Mac lâche : dézippe la dernière sauvegarde sur un autre ordinateur et relance « Lancer Élan ».</p>
      ${bk && bk.ok ? `<button class="btn sm" id="st-bk-now">Sauvegarder maintenant</button>` : ""}</div>
    <div class="section"><h2>Automatismes</h2>
      <label class="check"><input type="checkbox" id="st-ap" ${cfg.auto_push ? "checked" : ""}><span>Envoyer tout seul la séance du lendemain sur la montre</span></label>
      <div class="grid g2">
        <label class="f">À partir de (heure)<input type="number" id="st-aph" min="0" max="23" value="${cfg.auto_push_hour}"></label>
        <label class="f">Objectif de sommeil (h)<input type="number" id="st-sg" step="0.25" min="5" max="10" value="${cfg.sleep_goal_h}"></label>
      </div>
      ${(cfg.autopush_log || []).length ? `<div class="small muted">Derniers envois automatiques : ${cfg.autopush_log.slice(-3).reverse().map((x) => `${esc(x.title)} (${fmtDay(x.date)}) ${x.ok ? "✓" : "✗"}`).join(" · ")}</div>` : ""}
    </div>
    <div class="section"><h2>Objectif</h2>
      <div class="grid g2">
        <label class="f">Nom de la course<input id="st-rname" value="${esc(plan.race.name)}"></label>
        <label class="f">Date<input type="date" id="st-rdate" value="${plan.race.date}"></label>
        <label class="f">Objectif (h:mm:ss)<input id="st-rgoal" value="${esc(plan.race.goal)}"></label>
        <label class="f">Distance (km)<input id="st-rdist" value="${plan.race.distance_km}" inputmode="decimal"></label>
      </div></div>
    <div class="section"><h2>Allures (min/km, lente → rapide)</h2>
      <p class="small muted" style="margin-top:-4px">Elles s'appliquent à toutes les séances qui y font référence. Renvoie ensuite les séances déjà sur la montre.</p>
      ${Object.entries(plan.paces).map(([k, v]) => `<div class="row" style="margin-bottom:6px"><span class="dot" style="background:${ZONE_COLORS[k] || "#999"}"></span><b style="width:64px">${k}</b><span class="small muted" style="flex:1">${esc(plan.pace_labels?.[k] || "")}</span><input class="num" style="width:70px" data-pz="${k}" data-i="0" value="${v[0]}"> → <input class="num" style="width:70px" data-pz="${k}" data-i="1" value="${v[1]}"></div>`).join("")}
    </div>
    <div class="btns"><button class="btn primary" id="st-save">Enregistrer</button><button class="btn danger" id="st-reset">Réinitialiser le plan</button></div>`, (el) => {
    const lo = $("#st-logout", el);
    if (lo) lo.onclick = async () => { await api("/api/auth/logout", { method: "POST" }); state.status.connected = false; updatePill(); closeModal(); render(); };
    const bn = $("#st-bk-now", el);
    if (bn) bn.onclick = async () => { bn.disabled = true; bn.textContent = "Sauvegarde…"; try { const r = await api("/api/backup", { method: "POST" }); if (r.error && !r.ok) throw new Error(r.error); toast("Sauvegarde faite"); $("#st-bk", el).innerHTML = `Dernière sauvegarde : <b>maintenant</b> (${String(r.size_mb).replace(".", ",")} Mo)<br><span class="muted">Dans ${esc(r.dir)}</span>`; } catch (e) { toast(e.message, true); } bn.disabled = false; bn.textContent = "Sauvegarder maintenant"; };
    const li = $("#st-login", el);
    if (li) li.onclick = showLogin;
    $("#st-save", el).onclick = async () => {
      const paces = {};
      $$("[data-pz]", el).forEach((i) => { (paces[i.dataset.pz] ||= ["", ""])[Number(i.dataset.i)] = i.value.trim(); });
      try {
        await api("/api/settings", { method: "PUT", body: { auto_push: $("#st-ap", el).checked, auto_push_hour: Number($("#st-aph", el).value), sleep_goal_h: Number(String($("#st-sg", el).value).replace(",", ".")) } });
        await api("/api/plan/settings", { method: "PUT", body: { race: { name: $("#st-rname", el).value, date: $("#st-rdate", el).value, goal: $("#st-rgoal", el).value, distance_km: parseFloat($("#st-rdist", el).value.replace(",", ".")) }, paces } });
        state.paces = null; state.plan = null; toast("Réglages enregistrés"); closeModal(); render();
      } catch (e) { toast(e.message, true); }
    };
    $("#st-reset", el).onclick = async () => {
      if (!confirm("Remettre le plan d'origine ? L'actuel est sauvegardé dans data/.")) return;
      await api("/api/plan/reset", { method: "POST" }); state.plan = null; toast("Plan réinitialisé"); closeModal(); render();
    };
  });
}

// ---------------------------------------------------------------- démarrage
async function boot() {
  try {
    state.status = await api("/api/status");
    if (!state.status.connected) await new Promise((r) => setTimeout(r, 1500)).then(async () => (state.status = await api("/api/status")));
  } catch (e) { return; }
  updatePill();
  try { const v = localStorage.getItem("sub3_view"); if (v) state.view = v; } catch { /* */ }
  applyModule(MOD_OF(state.view));
  NAV().forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
  $("#btn-coach").classList.toggle("active", state.view === "coach");
  if (!state.status.connected) { render(); return; }
  showLobby(true);
}
boot();
