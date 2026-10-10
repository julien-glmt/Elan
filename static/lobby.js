/* Élan – page d'accueil animée : choix du module */
"use strict";

const ELAN_MARK = `<svg viewBox="0 0 24 24" class="elan-mark"><path d="M4 17.5 9.5 9l4 5.5L20 5.5"/><circle cx="20" cy="5.5" r="1.6"/></svg>`;

function hideLobby() {
  const L = $("#lobby");
  if (!L || L.classList.contains("hidden")) return;
  L.classList.add("leaving");
  document.body.classList.remove("in-lobby");
  setTimeout(() => { L.classList.add("hidden"); L.classList.remove("leaving"); L.innerHTML = ""; }, 420);
}

function sparkPath(vals, w = 120, hgt = 34) {
  const v = vals.map((x) => (x == null ? null : x));
  const nums = v.filter((x) => x != null);
  if (nums.length < 2) return "";
  const lo = Math.min(0, ...nums), hi = Math.max(0, ...nums);
  const y = (x) => hgt - 3 - ((x - lo) / (hi - lo || 1)) * (hgt - 6);
  const step = w / (v.length - 1);
  const bars = v.map((x, i) => (x == null ? "" : `<rect x="${i * step - 2.5}" y="${Math.min(y(x), y(0))}" width="5" height="${Math.max(1.5, Math.abs(y(x) - y(0)))}" rx="1.5" class="${x >= 0 ? "pos" : "neg"}"/>`)).join("");
  return `<svg class="lb-spark" viewBox="-4 0 ${w + 8} ${hgt}" preserveAspectRatio="none"><line x1="-4" x2="${w + 4}" y1="${y(0)}" y2="${y(0)}" class="zero"/>${bars}</svg>`;
}

async function showLobby(intro = false) {
  const L = $("#lobby");
  destroyCharts();
  document.body.classList.add("in-lobby");
  L.classList.remove("hidden", "leaving");
  L.classList.toggle("intro", !!intro);
  const now = new Date();
  const hr = now.getHours();
  const first = (state.status.name || "").split(" ")[0].replace(/\(.*\)/, "").trim();
  const hello = hr < 5 ? "Bonne nuit" : hr < 18 ? "Bonjour" : "Bonsoir";
  L.innerHTML = h`
    <div class="lb-bg"><i class="o1"></i><i class="o2"></i><i class="o3"></i><div class="lb-grain"></div></div>
    <div class="lb-top">
      <div class="lb-brand"><span class="lb-logo">${ELAN_MARK}</span><span class="lb-word">${[..."Élan"].map((c, i) => `<b style="--i:${i}">${c}</b>`).join("")}</span></div>
      <div class="lb-actions">
        <button class="icon-btn theme-btn" id="lb-theme" aria-label="Thème"><svg class="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/></svg><svg class="i-moon" viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg></button>
        <button class="icon-btn" id="lb-settings" aria-label="Réglages"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg></button>
      </div>
    </div>
    <div class="lb-main">
      <div class="lb-hello">
        <div class="lb-date">${DAY_NAMES[now.getDay()]} ${now.getDate()} ${MONTH_NAMES[now.getMonth()]}</div>
        <h1>${hello}${first ? ` ${esc(first)}` : ""}.</h1>
        <p>On s'occupe de quoi aujourd'hui ?</p>
      </div>
      <section class="td" id="lb-today"></section>
      <div class="lb-cards">
        <button class="lb-card run" data-go="running" style="--d:0">
          <div class="lb-glow"></div>
          <div class="lb-card-top"><span class="lb-ico"><svg viewBox="0 0 24 24"><circle cx="14" cy="4.5" r="2"/><path d="m7 21 3-6.5 3 2.5v4.5M10 14.5l1.2-5.2 4 3.2h3.3M11.2 9.3 8 10.5 6 13.5"/></svg></span><span class="lb-arrow">→</span></div>
          <div class="lb-title">Running</div>
          <div class="lb-sub">Plan, séances sur la montre, Jour J</div>
          <div class="lb-live" id="lb-run"></div>
        </button>
        <button class="lb-card body" data-go="body" style="--d:1">
          <div class="lb-glow"></div>
          <div class="lb-card-top"><span class="lb-ico"><svg viewBox="0 0 24 24"><path d="M12 21c4.5 0 7-3.2 7-7.2 0-3-1.6-5.4-3.6-7.3-.4 2-1.7 3.3-3 3.6.6-2.8-.6-5.6-3.2-7.1C9.4 6 5 8.6 5 13.8 5 17.8 7.5 21 12 21z"/></svg></span><span class="lb-arrow">→</span></div>
          <div class="lb-title">Nutrition</div>
          <div class="lb-sub">Calories, poids, bilan du jour</div>
          <div class="lb-live" id="lb-body"></div>
        </button>
        <button class="lb-card fin" data-go="fin" style="--d:2">
          <div class="lb-glow"></div>
          <div class="lb-card-top"><span class="lb-ico"><svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="13" rx="3"/><path d="M3 10h18M16 14.5h2"/></svg></span><span class="lb-arrow">→</span></div>
          <div class="lb-title">Finances</div>
          <div class="lb-sub">Budget, dépenses, épargne, patrimoine</div>
          <div class="lb-live" id="lb-fin"></div>
        </button>
        <button class="lb-card media" data-go="media" style="--d:3">
          <div class="lb-glow"></div>
          <div class="lb-card-top"><span class="lb-ico"><svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9.5 4.5 2.5-4.5 2.5z"/></svg></span><span class="lb-arrow">→</span></div>
          <div class="lb-title">Vu &amp; Lu</div>
          <div class="lb-sub">Séries, films, animés, mangas, livres</div>
          <div class="lb-live" id="lb-media"></div>
        </button>
      </div>
      <div class="lb-foot">Ton coach perso · course, nutrition, et la suite</div>
    </div>`;
  $("#lb-theme", L).onclick = () => applyTheme(currentTheme() === "dark" ? "light" : "dark");
  $("#lb-settings", L).onclick = () => showSettings();
  $$(".lb-card", L).forEach((c) => {
    c.onclick = () => enterModule(c);
    c.onpointermove = (e) => {
      const r = c.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      c.style.setProperty("--rx", `${(-y * 6).toFixed(2)}deg`);
      c.style.setProperty("--ry", `${(x * 8).toFixed(2)}deg`);
      c.style.setProperty("--mx", `${((x + 0.5) * 100).toFixed(1)}%`);
      c.style.setProperty("--my", `${((y + 0.5) * 100).toFixed(1)}%`);
    };
    c.onpointerleave = () => { c.style.setProperty("--rx", "0deg"); c.style.setProperty("--ry", "0deg"); };
  });
  loadToday(L);
  const SK = `<div class="lb-sk"><i style="width:38%;height:30px"></i><i style="width:62%"></i><i style="width:100%"></i><i style="width:80%"></i></div>`;
  const runBox = $("#lb-run", L), bodyBox = $("#lb-body", L);
  const cached = (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };
  const keep = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* */ } };
  const drawRun = (R) => {
    if (!runBox || !R) return;
    const today = R.today.length ? R.today.map((s) => esc(s.title)).join(" + ") : "Repos";
    const pct = R.week_planned ? Math.min(100, (R.week_done / R.week_planned) * 100) : 0;
    runBox.innerHTML = h`<div class="lb-big num">${R.days_to_race >= 0 ? `J-${R.days_to_race}` : "✓"}</div>
      <div class="lb-meta">${esc(R.race)}</div>
      <div class="lb-row"><span>Aujourd'hui</span><b>${today}${R.today.some((s) => s.status === "done") ? " ✓" : ""}</b></div>
      ${R.week_planned ? `<div class="lb-row"><span>Semaine</span><b class="num">${km(R.week_done, 0)} / ${km(R.week_planned, 0)} km</b></div><div class="lb-bar"><i style="width:${pct}%"></i></div>` : ""}`;
  };
  const drawBody = (B) => {
    if (!bodyBox || !B) return;
    if (!B.setup) {
      bodyBox.innerHTML = `<div class="lb-big">Nouveau</div><div class="lb-meta">Configure ton suivi en 30 secondes : poids de départ, objectif, déficit visé.</div>`;
      return;
    }
    if (B.not_started) {
      bodyBox.innerHTML = `<div class="lb-big">Demain</div><div class="lb-meta">Ton suivi démarre ${esc(fmtDay(B.start_date))} : pèse-toi au réveil.</div>`;
      return;
    }
    const T = B.today, K = B.kpi;
    bodyBox.innerHTML = h`<div class="lb-big num">${T.eaten != null ? `${Math.max(0, T.left).toLocaleString("fr-FR")}` : `${T.eat_target.toLocaleString("fr-FR")}`}<small> kcal</small></div>
      <div class="lb-meta">${T.eaten != null ? "restantes aujourd'hui" : "à manger aujourd'hui"} · ${esc(T.need.label.toLowerCase())}</div>
      ${sparkPath(B.spark || [])}
      <div class="lb-row"><span>Poids</span><b class="num">${K.weight_now != null ? km(K.weight_now, 1) + " kg" : "—"}${K.remaining_kg != null && K.remaining_kg > 0 ? ` · encore ${km(K.remaining_kg, 1)} kg` : ""}</b></div>`;
  };
  const fallback = (box, txt) => { if (box && box.querySelector(".lb-sk")) box.innerHTML = `<div class="lb-meta lb-fallback">${txt}</div>`; };
  // affichage immédiat des derniers chiffres connus, puis mise à jour
  const cr = cached("elan_lobby_run"), cb = cached("elan_lobby_body");
  if (cr) drawRun(cr); else if (runBox) runBox.innerHTML = SK;
  if (cb) drawBody(cb); else if (bodyBox) bodyBox.innerHTML = SK;
  api("/api/lobby/run").then((R) => { keep("elan_lobby_run", R); drawRun(R); })
    .catch(() => fallback(runBox, "Ton plan, tes séances et le Jour J. Clique pour ouvrir."));
  const finBox = $("#lb-fin", L);
  const drawFin = (F) => {
    if (!finBox || !F) return;
    if (!F.setup) { finBox.innerHTML = `<div class="lb-big">Nouveau</div><div class="lb-meta">Tes comptes, ton budget du mois et ton épargne, au même endroit.</div>`; return; }
    finBox.innerHTML = h`<div class="lb-big num">${F.var_left != null ? eur(Math.max(0, F.var_left)) : eur(F.spent)}</div>
      <div class="lb-meta">${F.var_left != null ? (F.var_left >= 0 ? "reste à dépenser ce mois" : "budget dépassé") : "dépensés ce mois"}${F.per_day_left ? ` · ${eur(F.per_day_left)}/jour` : ""}</div>
      <div class="lb-row"><span>Patrimoine</span><b class="num">${eur(F.net_worth)}</b></div>
      <div class="lb-row"><span>Taux d'épargne</span><b class="num">${F.savings_rate != null ? F.savings_rate + " %" : "—"}</b></div>`;
  };
  const cf = cached("elan_lobby_fin");
  if (cf) drawFin(cf); else if (finBox) finBox.innerHTML = SK;
  api("/api/lobby/fin").then((F) => { keep("elan_lobby_fin", F); drawFin(F); }).catch(() => fallback(finBox, "Ton budget et tes comptes. Clique pour ouvrir."));
  const medBox = $("#lb-media", L);
  const drawMed = (M) => {
    if (!medBox || !M) return;
    if (!M.n) { medBox.innerHTML = `<div class="lb-big">Nouveau</div><div class="lb-meta">Tape un titre, coche tes épisodes et tes pages d'un geste.</div>`; return; }
    const up = M.upcoming && M.upcoming[0];
    medBox.innerHTML = h`<div class="lb-big num">${km(M.hours, 1)}<small> h</small></div>
      <div class="lb-meta">ce mois-ci${up ? ` · ${esc(up.title)} ${up.airdate === today() ? "aujourd'hui" : "le " + esc(fmtDay(up.airdate))}` : ""}</div>
      ${M.current.length ? M.current.map((c) => `<div class="lb-row"><span class="ellipsis">${esc(c.title)}</span><b class="num">${esc(c.label || (c.pct != null ? c.pct + " %" : ""))}</b></div>`).join("") : `<div class="lb-row"><span>En cours</span><b>rien pour l'instant</b></div>`}`;
  };
  const cm = cached("elan_lobby_media");
  if (cm) drawMed(cm); else if (medBox) medBox.innerHTML = SK;
  api("/api/lobby/media").then((M) => { keep("elan_lobby_media", M); drawMed(M); }).catch(() => fallback(medBox, "Tes séries, films et lectures. Clique pour ouvrir."));
  api("/api/lobby/body").then((B) => { keep("elan_lobby_body", B); drawBody(B); })
    .catch(() => fallback(bodyBox, "Ta journée, ton journal et ton bilan. Clique pour ouvrir."));
  setTimeout(() => {
    fallback(runBox, "Ton plan, tes séances et le Jour J. Clique pour ouvrir.");
    fallback(bodyBox, "Les chiffres arrivent (première synchro avec ta montre)… Clique pour ouvrir.");
  }, 12000);
}

function enterModule(card) {
  const mod = card.dataset.go;
  let v = null;
  try { v = localStorage.getItem(MOD_LAST[mod]); } catch { /* */ }
  v = v || MOD_HOME[mod];
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) { setView(v); return; }
  const r = card.getBoundingClientRect();
  const ghost = document.createElement("div");
  ghost.className = `lb-zoom ${mod === "body" ? "body" : mod === "fin" ? "fin" : mod === "media" ? "media" : "run"}`;
  Object.assign(ghost.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
  document.body.appendChild(ghost);
  card.classList.add("chosen");
  $("#lobby").classList.add("zooming");
  requestAnimationFrame(() => requestAnimationFrame(() => {
    Object.assign(ghost.style, { left: "0px", top: "0px", width: "100vw", height: "100vh", borderRadius: "0px" });
  }));
  setTimeout(() => {
    setView(v);
    $("#lobby").classList.remove("zooming");
    ghost.classList.add("fade");
    setTimeout(() => ghost.remove(), 450);
  }, 480);
}


// ================================================================ « Ta journée » (accueil)
const TD_ICO = {
  night: `<svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>`,
  run: `<svg viewBox="0 0 24 24"><circle cx="14" cy="4.5" r="2"/><path d="m7 21 3-6.5 3 2.5v4.5M10 14.5l1.2-5.2 4 3.2h3.3M11.2 9.3 8 10.5 6 13.5"/></svg>`,
  body: `<svg viewBox="0 0 24 24"><path d="M12 21c4.5 0 7-3.2 7-7.2 0-3-1.6-5.4-3.6-7.3-.4 2-1.7 3.3-3 3.6.6-2.8-.6-5.6-3.2-7.1C9.4 6 5 8.6 5 13.8 5 17.8 7.5 21 12 21z"/></svg>`,
  fin: `<svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="13" rx="3"/><path d="M3 10h18M16 14.5h2"/></svg>`,
  media: `<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9.5 4.5 2.5-4.5 2.5z"/></svg>`,
};
const hFr = (x) => (x == null ? "—" : `${Math.floor(x)} h ${String(Math.round((x % 1) * 60)).padStart(2, "0")}`);
const minFr = (s) => { if (!s) return ""; const m = Math.round(s / 60); return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`; };

async function loadToday(L) {
  const box = $("#lb-today", L);
  if (!box) return;
  let c = null;
  try { c = JSON.parse(localStorage.getItem("elan_today") || "null"); } catch { /* */ }
  if (c && c.date === today()) drawToday(box, c);
  else box.innerHTML = `<div class="td-head"><h2>Ta journée</h2></div><div class="td-row">${'<div class="td-tile sk"></div>'.repeat(5)}</div>`;
  try {
    const T = await api("/api/today");
    try { localStorage.setItem("elan_today", JSON.stringify(T)); } catch { /* */ }
    if ($("#lb-today")) drawToday($("#lb-today"), T);
  } catch { if (!c) box.innerHTML = ""; }
}

function drawToday(box, T) {
  const R = T.run, N = T.night, B = T.body, F = T.fin, M = T.media, RV = T.review;
  const tiles = [];
  // Nuit
  if (N && (N.sleep_h || N.target_bed)) {
    tiles.push(h`<button class="td-tile night" data-go="home"><div class="td-k">${TD_ICO.night}Nuit</div>
      <div class="td-v num">${N.sleep_h ? hFr(N.sleep_h) : "—"}</div>
      <div class="td-s">${[N.score ? `score ${N.score}` : "", N.readiness ? `forme ${N.readiness}` : ""].filter(Boolean).join(" · ") || "synchronise ta montre"}</div>
      ${N.target_bed ? `<div class="td-foot">Ce soir au lit vers <b>${N.target_bed.replace(":", " h ")}</b></div>` : ""}</button>`);
  }
  // Séance
  if (R) {
    const s = R.today[0];
    tiles.push(s ? h`<button class="td-tile run" data-go="plan"><div class="td-k">${TD_ICO.run}Séance</div>
        <div class="td-v">${s.status === "done" ? `${km(s.done_km)} km ✓` : s.planned_km ? `${km(s.planned_km)} km` : esc(s.title)}</div>
        <div class="td-s ellipsis2">${esc(s.title)}${s.planned_s && s.status !== "done" ? ` · ${minFr(s.planned_s)}` : ""}</div>
        <div class="td-foot">${R.days_to_race >= 0 ? `J-${R.days_to_race} · ${esc(R.race)}` : ""}</div></button>`
      : h`<button class="td-tile run" data-go="plan"><div class="td-k">${TD_ICO.run}Séance</div><div class="td-v">Repos</div>
        <div class="td-s ellipsis2">${R.tomorrow[0] ? `Demain : ${esc(R.tomorrow[0].title)}` : "Rien de prévu demain"}</div>
        <div class="td-foot">${R.days_to_race >= 0 ? `J-${R.days_to_race} · ${esc(R.race)}` : ""}</div></button>`);
  }
  // Assiette
  if (B && B.setup && !B.not_started) {
    const t = B.today;
    tiles.push(h`<button class="td-tile body" data-go="${t.carbs ? "b-race" : "b-today"}"><div class="td-k">${TD_ICO.body}Assiette</div>
      ${t.carbs ? `<div class="td-v num">${Math.max(0, t.carbs.target - t.carbs.eaten)}<small> g de glucides</small></div>
      <div class="td-s">encore à manger · recharge avant course</div>` : `<div class="td-v num">${(t.eaten != null ? Math.max(0, t.left) : t.eat_target).toLocaleString("fr-FR")}<small> kcal</small></div>
      <div class="td-s">${t.eaten != null ? "restantes" : "à manger"} · ${esc(t.need.label.toLowerCase())}</div>`}
      <div class="td-foot">${t.weight ? `Pesée : <b>${km(t.weight, 1)} kg</b>` : "Pense à te peser"}</div></button>`);
  }
  // Budget
  if (F && F.setup) {
    tiles.push(h`<button class="td-tile fin" data-go="f-home"><div class="td-k">${TD_ICO.fin}Budget</div>
      <div class="td-v num">${F.per_day_left != null ? eur(F.per_day_left) : eur(F.var_left)}<small>${F.per_day_left != null ? " /jour" : ""}</small></div>
      <div class="td-s">${F.spent_today ? `${eur(F.spent_today)} dépensés aujourd'hui` : "rien dépensé aujourd'hui"}</div>
      <div class="td-foot">${F.due.length ? F.due.slice(0, 2).map((d) => `${esc(d.label)} ${d.when}`).join(" · ") : "Aucun prélèvement prévu"}</div></button>`);
  }
  // Ce soir
  if (M && (M.current.length || M.airing_today.length)) {
    const c = M.current[0], a = M.airing_today[0];
    tiles.push(h`<button class="td-tile media" data-go="m-home"><div class="td-k">${TD_ICO.media}Ce soir</div>
      <div class="td-v ellipsis">${esc(c ? c.title : a.title)}</div>
      <div class="td-s">${c && c.next ? `à suivre : ${esc(c.next)}` : ""}</div>
      <div class="td-foot">${a ? `Nouvel épisode : <b>${esc(a.title)}</b>` : M.current[1] ? `ou ${esc(M.current[1].title)}` : ""}</div></button>`);
  }
  const pr = (RV && RV.priorities) || [];
  box.innerHTML = h`<div class="td-head"><h2>Ta journée</h2>
      <button class="td-rv ${RV && RV.due && !RV.done ? "due" : ""}" id="td-rv">${RV && RV.due && !RV.done ? "Ta revue de la semaine t'attend →" : "Revue de la semaine →"}</button></div>
    <div class="td-row">${tiles.join("")}</div>
    ${pr.length ? `<div class="td-pr"><span class="td-pr-k">Tes priorités de la semaine</span>${pr.map((p, i) => `<label class="td-chk ${p.done ? "on" : ""}"><input type="checkbox" data-pi="${i}" ${p.done ? "checked" : ""}><span>${esc(p.text)}</span></label>`).join("")}</div>` : ""}`;
  $$(".td-tile[data-go]", box).forEach((b) => (b.onclick = () => setView(b.dataset.go)));
  $("#td-rv", box).onclick = () => showReview();
  $$("[data-pi]", box).forEach((cb) => (cb.onchange = async () => {
    cb.closest(".td-chk").classList.toggle("on", cb.checked);
    try { await api(`/api/today/priority/${cb.dataset.pi}`, { method: "POST", body: { done: cb.checked } }); localStorage.removeItem("elan_today"); } catch { /* */ }
  }));
}

// ================================================================ Revue de la semaine
const RV_MOODS = ["Difficile", "Moyenne", "Correcte", "Bonne", "Excellente"];
const RV_MOD = { run: "#ff5a1f", sleep: "#6366f1", body: "#10b981", fin: "#4f46e5", media: "#ec4899" };
const STATUS_COL = { done: "#10b981", partial: "#f59e0b", missed: "#ef4444", upcoming: "var(--card-3)", today: "#ff5a1f", extra: "#10b981", rest: "var(--card-3)" };

async function showReview(week) {
  const L = $("#lobby");
  destroyCharts();
  document.body.classList.add("in-lobby");
  L.classList.remove("hidden", "leaving", "intro");
  L.innerHTML = `<div class="lb-bg"><i class="o1"></i><i class="o2"></i><i class="o3"></i></div><div class="rv"><div class="rv-load">Je prépare ta semaine…</div></div>`;
  let D;
  try { D = await api(`/api/review${week ? `?week=${week}` : ""}`); } catch (e) { $(".rv", L).innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  const S = D.saved || {};
  const d0 = parseD(D.week), d1 = parseD(D.end);
  const span = d0.getMonth() === d1.getMonth() ? `du ${d0.getDate()} au ${d1.getDate()} ${MONTH_NAMES[d1.getMonth()]}` : `du ${d0.getDate()} ${MONTH_NAMES[d0.getMonth()]} au ${d1.getDate()} ${MONTH_NAMES[d1.getMonth()]}`;
  const shift = (k) => { const d = parseD(D.week); d.setDate(d.getDate() + 7 * k); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const canNext = shift(1) <= today();
  const R = D.run, SL = D.sleep, B = D.body, F = D.fin, M = D.media;
  const prio = (S.priorities || []).concat([{}, {}, {}]).slice(0, 3);
  const cards = [];
  if (R) {
    const pct = R.planned_km ? Math.min(130, Math.round((R.km / R.planned_km) * 100)) : null;
    cards.push(h`<div class="card rv-card" style="--c:${RV_MOD.run}"><div class="rv-k">${TD_ICO.run}Running</div>
      <div class="rv-big num">${km(R.km)}<small> / ${km(R.planned_km)} km</small></div>
      ${pct != null ? `<div class="m-bar"><i style="width:${Math.min(100, pct)}%;background:var(--c)"></i></div>` : ""}
      <div class="rv-kv"><span>Séances</span><b>${R.n_done} / ${R.n_planned}</b><span>Temps</span><b>${minFr(R.time_s) || "—"}</b>
        <span>Plus longue</span><b>${R.longest ? `${km(R.longest.km)} km` : "—"}</b><span>D+</span><b>${R.elev} m</b>
        <span>Semaine d'avant</span><b>${km(R.prev_km)} km</b></div>
      <div class="rv-sess">${R.sessions.map((s) => `<div><i style="background:${STATUS_COL[s.status] || "var(--card-3)"}"></i><span class="small muted">${DAYS[parseD(s.date).getDay()]}</span><span class="ellipsis">${esc(s.title)}</span><b class="small">${s.done_km ? km(s.done_km) + " km" : ""}</b></div>`).join("")}</div>
      ${R.next.planned_km ? `<div class="rv-next"><b>Semaine prochaine : ${km(R.next.planned_km)} km</b>${R.next.key.map((k) => `<div class="small muted">${fmtDay(k.date)} · ${esc(k.title)}</div>`).join("")}</div>` : ""}
      <div class="small muted" style="margin-top:8px">${R.days_to_race >= 0 ? `${esc(R.race)} dans ${R.days_to_race} jours` : ""}</div></div>`);
  }
  if (SL) {
    const mx = Math.max(9, ...SL.series.map((x) => x.h));
    cards.push(h`<div class="card rv-card" style="--c:${RV_MOD.sleep}"><div class="rv-k">${TD_ICO.night}Sommeil</div>
      <div class="rv-big num">${hFr(SL.avg_h)}<small> / nuit</small></div>
      <div class="rv-bars">${SL.series.map((x) => `<div title="${fmtDay(x.date)} : ${hFr(x.h)}"><i style="height:${(x.h / mx) * 100}%;background:${x.h < 6 ? "#ef4444" : x.h < SL.goal_h - 0.25 ? "#f59e0b" : "var(--c)"}"></i><span>${DAYS[parseD(x.date).getDay()].slice(0, 1).toUpperCase()}</span></div>`).join("")}<em style="bottom:${(SL.goal_h / mx) * 100}%"></em></div>
      <div class="rv-kv"><span>Objectif</span><b>${hFr(SL.goal_h)}</b><span>Coucher moyen</span><b>${SL.avg_bed || "—"}</b><span>Nuits &lt; 6 h</span><b>${SL.short}</b>${SL.score ? `<span>Score moyen</span><b>${SL.score}</b>` : ""}</div></div>`);
  }
  if (B) {
    cards.push(h`<div class="card rv-card" style="--c:${RV_MOD.body}"><div class="rv-k">${TD_ICO.body}Nutrition</div>
      <div class="rv-big num">${B.avg_balance != null ? `${B.avg_balance > 0 ? "−" : "+"}${Math.abs(B.avg_balance)}` : "—"}<small> kcal/jour</small></div>
      <div class="small muted">${B.avg_balance != null ? (B.avg_balance > 0 ? "de déficit moyen" : "de surplus moyen") : "complète tes dépenses pour voir ton bilan"}</div>
      <div class="rv-kv"><span>Jours suivis</span><b>${B.tracked} / ${B.days}</b><span>Mangé en moyenne</span><b>${B.avg_eaten ? B.avg_eaten.toLocaleString("fr-FR") + " kcal" : "—"}</b>
        <span>Pesées</span><b>${B.weighins}</b><span>Poids (moy. 7 j)</span><b>${B.avg7_end ? km(B.avg7_end, 1) + " kg" : "—"}</b>
        ${B.w_first && B.w_last && B.weighins > 1 ? `<span>Évolution</span><b>${B.w_last - B.w_first > 0 ? "+" : ""}${km(B.w_last - B.w_first, 1)} kg</b>` : ""}</div></div>`);
  }
  if (F) {
    cards.push(h`<div class="card rv-card" style="--c:${RV_MOD.fin}"><div class="rv-k">${TD_ICO.fin}Finances</div>
      <div class="rv-big num">${eur(F.spent)}</div><div class="small muted">de dépenses courantes${F.avg8 ? ` · moyenne ${eur(F.avg8)}/semaine` : ""}</div>
      <div class="rv-kv">${F.top.map((t) => `<span>${esc(t.name)}</span><b>${eur(t.amount)}</b>`).join("")}
        ${F.bills ? `<span>Charges fixes (loyer…)</span><b>${eur(F.bills)}</b>` : ""}
        ${F.month && F.month.var_left != null ? `<span>Reste ce mois</span><b>${eur(F.month.var_left)}</b>` : ""}</div></div>`);
  }
  if (M) {
    cards.push(h`<div class="card rv-card" style="--c:${RV_MOD.media}"><div class="rv-k">${TD_ICO.media}Vu &amp; Lu</div>
      <div class="rv-big num">${km(M.hours)}<small> h</small></div>
      <div class="rv-kv"><span>Épisodes</span><b>${M.episodes}</b><span>Chapitres</span><b>${M.chapters}</b><span>Pages</span><b>${M.pages}</b></div>
      ${M.finished.length ? `<div class="small" style="margin-top:8px">Terminé : <b>${M.finished.map(esc).join(", ")}</b></div>` : ""}</div>`);
  }
  $(".rv", L).innerHTML = h`
    <div class="rv-top"><button class="btn" id="rv-back">← Accueil</button>
      <div class="rv-nav"><button class="icon-btn" id="rv-prev" aria-label="Semaine précédente">‹</button><div><div class="lb-date">Revue de la semaine</div><h1>${span}</h1></div>
      <button class="icon-btn" id="rv-next" aria-label="Semaine suivante" ${canNext ? "" : "disabled"}>›</button></div></div>
    ${D.insights.length ? `<div class="card rv-ins">${D.insights.map((i) => `<div class="rv-in ${i.level}"><i style="background:${RV_MOD[i.mod]}"></i><span>${esc(i.text)}</span></div>`).join("")}</div>` : ""}
    <div class="rv-grid">${cards.join("") || `<div class="card empty">Pas encore de données pour cette semaine.</div>`}</div>
    <div class="rv-form card">
      ${D.prev_priorities.length ? `<h2>Tes priorités de la semaine dernière</h2><div class="rv-prev">${D.prev_priorities.map((p, i) => `<label class="td-chk ${p.done ? "on" : ""}"><input type="checkbox" data-pp="${i}" ${p.done ? "checked" : ""}><span>${esc(p.text)}</span></label>`).join("")}</div>` : ""}
      <h2>Ta semaine en un mot</h2>
      <div class="rv-mood" id="rv-mood">${RV_MOODS.map((l, i) => `<button data-m="${i + 1}" class="${S.mood === i + 1 ? "on" : ""}"><b>${i + 1}</b>${l}</button>`).join("")}</div>
      <div class="grid g2" style="margin-top:14px">
        <label class="f">Ce qui a bien marché<textarea id="rv-good" rows="3" placeholder="Ex. toutes les séances faites, couché avant minuit 3 soirs…">${esc(S.good || "")}</textarea></label>
        <label class="f">Ce qui a coincé<textarea id="rv-bad" rows="3" placeholder="Ex. trop de grignotage le soir, nuit courte avant le fractionné…">${esc(S.bad || "")}</textarea></label></div>
      <label class="f">Ce que je retiens<textarea id="rv-learn" rows="2">${esc(S.learn || "")}</textarea></label>
      <h2 style="margin-top:16px">Tes 3 priorités pour la semaine prochaine</h2>
      <div class="rv-pr">${prio.map((p, i) => `<label><b>${i + 1}</b><input data-pr="${i}" value="${esc(p.text || "")}" placeholder="${["Ex. me coucher avant 23 h 30 en semaine", "Ex. réussir la sortie longue de dimanche", "Ex. 3 soirs d'espagnol"][i]}"></label>`).join("")}</div>
      <div class="btns" style="margin-top:14px"><button class="btn primary" id="rv-save">${S.saved ? "Mettre à jour" : "Enregistrer ma revue"}</button>${S.saved ? `<span class="small muted">Enregistrée le ${fmtDay(S.saved)}</span>` : ""}</div>
      ${D.history.length > 1 ? `<div class="rv-hist"><span class="small muted">Tes dernières semaines</span>${D.history.map((x) => `<i title="${fmtDay(x.week)} : ${x.mood ? RV_MOODS[x.mood - 1] : "—"}" style="height:${(x.mood || 0) * 7 + 4}px"></i>`).join("")}</div>` : ""}
    </div>`;
  let mood = S.mood || null;
  $("#rv-back", L).onclick = () => showLobby();
  $("#rv-prev", L).onclick = () => showReview(shift(-1));
  if (canNext) $("#rv-next", L).onclick = () => showReview(shift(1));
  $$("#rv-mood button", L).forEach((b) => (b.onclick = () => { mood = Number(b.dataset.m); $$("#rv-mood button", L).forEach((y) => y.classList.toggle("on", y === b)); }));
  $$("[data-pp]", L).forEach((cb) => (cb.onchange = () => cb.closest(".td-chk").classList.toggle("on", cb.checked)));
  $("#rv-save", L).onclick = async () => {
    const body = { mood, good: $("#rv-good", L).value, bad: $("#rv-bad", L).value, learn: $("#rv-learn", L).value,
      priorities: $$("[data-pr]", L).map((x) => ({ text: x.value.trim(), done: false })).filter((p) => p.text) };
    const pp = $$("[data-pp]", L);
    if (pp.length) body.prev_done = pp.map((x) => x.checked);
    try { await api(`/api/review/${D.week}`, { method: "POST", body }); localStorage.removeItem("elan_today"); toast("Revue enregistrée. Bonne semaine !"); showReview(D.week); } catch (e) { toast(e.message, true); }
  };
  L.scrollTop = 0;
}

{ const b = document.getElementById("nav-review"); if (b) b.addEventListener("click", () => showReview()); }
