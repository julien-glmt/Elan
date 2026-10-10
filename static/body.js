/* Élan – module Nutrition : calories, poids, bilan (relié à l'entraînement) */
"use strict";

const NEED_COLOR = { race: "#ff5a1f", long: "#ff5a1f", key: "#e11d48", easy: "#12a150", rest: "#3b82f6" };
const SRC_LABEL = { garmin: "Garmin", "estimé": "estimée", manuel: "saisie" };
const nf = (x) => (x == null ? "—" : Math.round(x).toLocaleString("fr-FR"));
const signed = (x) => (x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(Math.round(x)).toLocaleString("fr-FR")}`);

async function loadBody(force = false) {
  if (!force && state.body && Date.now() - state.bodyAt < 15000) return state.body;
  state.body = await api("/api/body");
  state.bodyAt = Date.now();
  return state.body;
}

async function saveDay(day, patch) {
  state.body = await api(`/api/body/day/${day}`, { method: "POST", body: patch });
  state.bodyAt = Date.now();
  return state.body;
}

// ================================================================ AUJOURD'HUI
async function renderBodyToday(view) {
  const B = await loadBody(true);
  if (!B.setup) return renderBodySetup(view, B);
  if (B.params.start_date > B.today.date) return renderBodyNotStarted(view, B);
  const day = state.bodyDay && state.bodyDay !== B.today.date ? state.bodyDay : B.today.date;
  const isToday = day === B.today.date;
  const row = B.rows.find((r) => r.date === day) || { date: day };
  const T = B.today;
  const eaten = row.eaten;
  const burn = isToday ? T.burn : row.burn;
  const target = isToday ? T.eat_target : (row.burn != null ? row.burn - (B.params.deficit_goal || 500) : null);
  const missing = (B.missing || []).filter((d) => d !== day);
  const left = target != null ? target - (eaten || 0) : null;
  const pct = target ? Math.min(1.25, (eaten || 0) / target) : 0;
  const ringCol = pct > 1.02 ? "var(--bad)" : pct > 0.9 ? "var(--warn)" : "var(--good)";
  const C = 2 * Math.PI * 70;
  const need = isToday ? T.need : { label: row.train, level: row.train_level, advice: "" };
  const prevDay = iso(new Date(parseD(day).getTime() - 864e5));
  const nextDay = iso(new Date(parseD(day).getTime() + 864e5));
  const last7 = B.rows.slice(-7).reverse();

  view.innerHTML = h`
    <div class="day-nav">
      <button class="icon-btn" id="bd-prev" aria-label="Jour précédent"><svg viewBox="0 0 24 24"><path d="m15 6-6 6 6 6"/></svg></button>
      <div class="day-nav-label"><b>${isToday ? "Aujourd'hui" : fmtDay(day)}</b><span>${isToday ? fmtDay(day) : `<a href="#" id="bd-today">revenir à aujourd'hui</a>`}</span></div>
      <button class="icon-btn" id="bd-next" aria-label="Jour suivant" ${isToday ? "disabled" : ""}><svg viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg></button>
    </div>
    ${B.alerts.length && isToday ? B.alerts.map((a) => `<div class="warn-line" style="margin:0 0 10px">${esc(a)}</div>`).join("") : ""}
    ${isToday ? carbBanner(T) : ""}
    ${missing.length ? h`<div class="card missing-card"><div class="row between wrap" style="gap:8px"><div><b>Dépense à compléter</b><div class="small muted">Sans elle, le bilan de ces jours n'est pas calculé.</div></div></div>
      ${missing.map((d) => `<div class="miss-row"><span>${fmtDay(d)}</span><input type="number" step="10" inputmode="numeric" placeholder="kcal dépensées" data-miss="${d}"><button class="btn sm primary" data-miss-save="${d}">OK</button></div>`).join("")}</div>` : ""}
    <div class="cols"><div>
      <div class="card body-hero">
        <div class="ring-wrap">
          <svg viewBox="0 0 160 160" class="kcal-ring"><circle cx="80" cy="80" r="70" class="track"/>
            <circle cx="80" cy="80" r="70" class="fill" style="stroke:${ringCol};stroke-dasharray:${C};stroke-dashoffset:${C * (1 - Math.min(1, pct))}"/></svg>
          <div class="ring-center"><span>${left != null && left < 0 ? "Au-dessus de" : "Reste"}</span><b class="num">${left != null ? nf(Math.abs(left)) : "—"}</b><span>kcal</span></div>
        </div>
        <div class="hero-side">
          <div class="need-chip" style="--c:${NEED_COLOR[need.level] || "#999"}">${esc(need.label)}</div>
          <div class="kv3">
            <div><span>Dépense</span><b class="num">${burn != null ? nf(burn) : "?"}</b><em>${burn == null ? "à saisir" : SRC_LABEL[isToday ? T.burn_src : row.burn_src] || ""}</em></div>
            <div><span>Objectif repas</span><b class="num">${nf(target)}</b><em>${isToday ? `déficit visé ${nf(T.target_deficit)}` : ""}</em></div>
            <div><span>Mangé</span><b class="num">${nf(eaten)}</b><em>${row.balance != null ? `bilan ${signed(row.balance)}` : row.eaten_src === "garmin" ? "Garmin Connect" : "rien dans Garmin"}</em></div>
          </div>
          ${isToday && need.advice ? `<p class="small" style="margin:10px 0 0">${esc(need.advice)}</p>` : ""}
        </div>
      </div>

      <div class="card section">
        <h2>${isToday ? "Ta journée" : "Ce jour-là"}</h2>
        <p class="small muted" style="margin:-4px 0 12px">Ce que tu manges est repris tout seul de Garmin Connect. Ici, tu notes seulement ta dépense (facultatif : tu peux la mettre le lendemain) et ton poids si tu t'es pesé.</p>
        <div class="grid g2">
          <label class="f">Dépense du jour (kcal)<input id="bd-burn" type="number" step="10" inputmode="numeric" value="${row.burn_src === "manuel" ? row.burn : ""}" placeholder="${isToday && T.burn ? "≈ " + nf(T.burn) + " estimée" : "facultatif"}"></label>
          <label class="f">Poids du matin (kg)<input id="bd-weight" type="number" step="0.1" inputmode="decimal" value="${row.weight ?? ""}" placeholder="facultatif"></label>
        </div>
        <label class="f">Commentaire<input id="bd-comment" value="${esc(row.comment || "")}" placeholder="resto, repas de famille, faim en soirée…"></label>
        <div class="btns"><button class="btn primary" id="bd-save">Enregistrer</button></div>
      </div>
    </div><div>
      ${isToday ? h`<div class="card"><h2>Demain</h2>
        <div class="row" style="gap:10px;align-items:flex-start"><div class="need-chip" style="--c:${NEED_COLOR[T.tomorrow.level] || "#999"}">${esc(T.tomorrow.label)}</div>
        <p class="small" style="margin:2px 0 0;flex:1">${esc(T.tomorrow.advice)}</p></div></div>` : ""}
      <div class="card section">
        <div class="row between"><h2 style="margin:0">7 derniers jours</h2><a href="#" class="small" id="bd-log">Journal complet →</a></div>
        <table class="body-mini"><tbody>${last7.map((r) => `<tr data-day="${r.date}" class="${r.date === day ? "sel" : ""}"><td>${fmtDay(r.date)}</td><td><span class="tdot" style="background:${NEED_COLOR[r.train_level]}"></span>${esc(r.train)}</td>
          <td class="r num">${r.eaten != null ? nf(r.eaten) : "<span class='muted'>—</span>"}</td><td class="r num"><b class="${r.balance == null ? "" : r.balance >= 0 ? "pos" : "neg"}">${r.balance != null ? signed(r.balance) : ""}</b></td></tr>`).join("")}</tbody></table>
        <p class="small muted" style="margin:8px 0 0">Bilan = dépense − mangé. Positif (vert) = déficit.</p>
      </div>
      <div class="card section body-kpi-mini" id="bd-kpi">
        <div><span>Déficit cumulé</span><b class="num">${nf(B.kpi.cum)}</b><em>≈ ${km(B.kpi.loss_kg, 2)} kg</em></div>
        <div><span>Moyenne 7 j</span><b class="num">${B.kpi.avg7 != null ? signed(B.kpi.avg7) : "—"}</b><em>objectif ${nf(B.params.deficit_goal)}/j</em></div>
        <div><span>Poids</span><b class="num">${B.kpi.weight_now != null ? km(B.kpi.weight_now, 1) : "—"}</b><em>${B.kpi.weight_is_estimate ? "estimé" : "moy. 7 j"} · objectif ${B.params.goal_weight ? km(B.params.goal_weight, 1) : "—"}</em></div>
      </div>
    </div></div>`;

  const go = (d) => { state.bodyDay = d; render(); };
  $("#bd-prev", view).onclick = () => go(prevDay);
  const nx = $("#bd-next", view); if (nx && !isToday) nx.onclick = () => go(nextDay > B.today.date ? B.today.date : nextDay);
  const bt = $("#bd-today", view); if (bt) bt.onclick = (e) => { e.preventDefault(); go(null); };
  $("#bd-log", view).onclick = (e) => { e.preventDefault(); setView("b-log"); };
  $$(".body-mini tr", view).forEach((tr) => (tr.onclick = () => go(tr.dataset.day === B.today.date ? null : tr.dataset.day)));
  $$("[data-miss-save]", view).forEach((b) => (b.onclick = async () => {
    const d = b.dataset.missSave, v = $(`[data-miss="${d}"]`, view).value;
    if (!v) return;
    try { await saveDay(d, { burn: v }); toast("Dépense enregistrée"); render(); } catch (e) { toast(e.message, true); }
  }));
  $("#bd-save", view).onclick = async () => {
    try {
      await saveDay(day, { weight: $("#bd-weight", view).value, comment: $("#bd-comment", view).value, burn: $("#bd-burn", view).value });
      toast("Journée enregistrée"); render();
    } catch (e) { toast(e.message, true); }
  };
}

function renderBodyNotStarted(view, B) {
  const d = B.params.start_date;
  view.innerHTML = h`<div class="card body-setup start-soon">
    <div class="eyebrow-s">Nutrition</div>
    <h2 style="margin:2px 0 6px;font-size:24px">Ton suivi démarre ${fmtDay(d)}</h2>
    <ul class="review-list">
      <li><b>Le matin</b> : pèse-toi (à jeun, après les toilettes) et note ton poids ici. Ce sera ton poids de départ.</li>
      <li><b>Dans la journée</b> : note ce que tu manges dans Garmin Connect, l'app le récupère toute seule.</li>
      <li><b>Le soir ou le lendemain</b> : saisis ta dépense du jour (facultatif, à compléter plus tard si besoin).</li>
    </ul>
    <div class="btns"><button class="btn" id="bd-params">Réglages</button></div></div>`;
  $("#bd-params", view).onclick = () => openModal(h`<h3>Réglages du suivi</h3>${bodyParamsForm(B.params)}<div class="btns"><button class="btn primary" id="bp-save">Enregistrer</button></div>`, (el) => bindParams(el, closeModal));
}

// ================================================================ CONFIGURATION
function renderBodySetup(view, B) {
  const p = B.params;
  view.innerHTML = h`<div class="card body-setup">
    <div class="eyebrow-s">Nutrition</div>
    <h2 style="margin:2px 0 6px;font-size:22px">On règle ton suivi</h2>
    <p class="small muted" style="margin:0 0 16px">Chaque jour, ta montre donne ce que tu as dépensé, tu notes ce que tu as mangé : l'app calcule ton bilan, ta perte estimée et la date d'arrivée à ton objectif. Les jours de sortie longue et de course, elle te demande de manger à ta faim.</p>
    ${bodyParamsForm(p)}
    <div class="btns"><button class="btn primary" id="bp-save">Commencer le suivi</button></div></div>`;
  bindParams(view);
}

function bodyParamsForm(p) {
  return h`<div class="grid g2">
    <label class="f">Début du suivi<input id="bp-start" type="date" value="${p.start_date || today()}"></label>
    <label class="f">Déficit visé par jour (kcal)<input id="bp-def" type="number" step="50" value="${p.deficit_goal ?? 500}"><span class="hint">300-500 en pleine prépa, c'est le bon compromis.</span></label>
    <label class="f">Poids de départ (kg)<input id="bp-w0" type="number" step="0.1" value="${p.start_weight ?? ""}"></label>
    <label class="f">Poids objectif (kg)<input id="bp-w1" type="number" step="0.1" value="${p.goal_weight ?? ""}"></label>
    <label class="f">Masse grasse de départ (%)<input id="bp-bf0" type="number" step="0.5" value="${p.bf_start != null ? (p.bf_start <= 1 ? p.bf_start * 100 : p.bf_start) : ""}" placeholder="facultatif"></label>
    <label class="f">Masse grasse objectif (%)<input id="bp-bf1" type="number" step="0.5" value="${p.bf_goal != null ? (p.bf_goal <= 1 ? p.bf_goal * 100 : p.bf_goal) : ""}" placeholder="facultatif"></label>
    <label class="f">Maintenance sans montre (kcal)<input id="bp-maint" type="number" step="50" value="${p.maintenance ?? 2500}"><span class="hint">Utilisée seulement si Garmin n'a pas de données.</span></label>
    <label class="f">kcal par kg de gras<input id="bp-kpk" type="number" step="100" value="${p.kcal_per_kg ?? 7700}"></label>
  </div>`;
}

function bindParams(el, after) {
  $("#bp-save", el).onclick = async () => {
    try {
      state.body = await api("/api/body/params", { method: "POST", body: {
        start_date: $("#bp-start", el).value, deficit_goal: $("#bp-def", el).value, start_weight: $("#bp-w0", el).value, goal_weight: $("#bp-w1", el).value,
        bf_start: $("#bp-bf0", el).value, bf_goal: $("#bp-bf1", el).value, maintenance: $("#bp-maint", el).value, kcal_per_kg: $("#bp-kpk", el).value } });
      state.bodyAt = Date.now();
      toast("Réglages enregistrés"); if (after) after(); render();
    } catch (e) { toast(e.message, true); }
  };
}

// ================================================================ JOURNAL
async function renderBodyLog(view) {
  const B = await loadBody(true);
  if (!B.setup) return renderBodySetup(view, B);
  if (B.params.start_date > B.today.date) return renderBodyNotStarted(view, B);
  const rows = B.rows.filter((r) => r.date >= B.params.start_date).slice().reverse();
  const byMonth = {};
  rows.forEach((r) => (byMonth[r.date.slice(0, 7)] ||= []).push(r));
  view.innerHTML = h`<div class="card">
    <div class="row between wrap"><h2 style="margin:0">Journal</h2><span class="small muted">Clique sur la dépense, le poids ou le commentaire pour les modifier · mangé = Garmin Connect · bilan = dépense − mangé</span></div>
    <div class="table-scroll"><table class="body-log">
      <thead><tr><th>Jour</th><th>Entraînement</th><th class="r">Dépense</th><th class="r">Mangé</th><th class="r">Bilan</th><th class="r">Cumul</th><th class="r">Poids</th><th>Commentaire</th></tr></thead>
      ${Object.entries(byMonth).map(([m, rs]) => h`<tbody><tr class="month"><td colspan="8">${MONTH_NAMES[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}</td></tr>
        ${rs.map((r) => h`<tr data-day="${r.date}" class="${r.date === B.today.date ? "is-today" : ""}">
          <td class="nowrap">${fmtDay(r.date)}</td>
          <td class="nowrap"><span class="tdot" style="background:${NEED_COLOR[r.train_level]}"></span>${esc(r.train)}${r.km ? ` <span class="muted small">${km(r.km)} km</span>` : ""}</td>
          <td class="r num ed" data-f="burn">${r.burn != null ? nf(r.burn) : `<span class="todo">à saisir</span>`}</td>
          <td class="r num">${r.eaten != null ? nf(r.eaten) : "<span class='muted'>—</span>"}${r.eaten_src ? `<i class="src">${r.eaten_src === "garmin" ? "Garmin" : "saisi"}</i>` : ""}</td>
          <td class="r num"><b class="${r.balance == null ? "" : r.balance >= 0 ? "pos" : "neg"}">${r.balance != null ? signed(r.balance) : ""}</b>${r.flag ? `<i class="flag" title="${esc(r.flag)}">!</i>` : ""}</td>
          <td class="r num muted">${nf(r.cum)}</td>
          <td class="r num ed" data-f="weight">${r.weight != null ? km(r.weight, 1) : "<span class='muted'>+</span>"}</td>
          <td class="ed cmt" data-f="comment">${esc(r.comment || "")}</td></tr>`).join("")}</tbody>`).join("")}
    </table></div></div>`;
  $$(".body-log td.ed", view).forEach((td) => (td.onclick = () => {
    if (td.querySelector("input")) return;
    const day = td.parentElement.dataset.day, f = td.dataset.f;
    const r = B.rows.find((x) => x.date === day);
    const cur = r[f] ?? "";
    td.innerHTML = `<input class="cell-in" ${f === "comment" ? "" : `type="number" step="${f === "weight" ? "0.1" : "10"}"`} value="${esc(cur)}" placeholder="${f === "burn" ? "kcal" : ""}">`;
    const inp = td.querySelector("input");
    inp.focus(); inp.select && inp.select();
    let done = false;
    const commit = async () => {
      if (done) return; done = true;
      try { await saveDay(day, { [f]: inp.value }); } catch (e) { toast(e.message, true); }
      render();
    };
    inp.onblur = commit;
    inp.onkeydown = (e) => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { done = true; render(); } };
  }));
}

// ================================================================ BILAN
async function renderBodyDash(view) {
  const B = await loadBody(true);
  if (!B.setup) return renderBodySetup(view, B);
  if (B.params.start_date > B.today.date) return renderBodyNotStarted(view, B);
  const K = B.kpi, P = B.params;
  const rows = B.rows.filter((r) => r.date >= P.start_date);
  const etaTxt = K.eta ? fmtDay(K.eta) + " " + parseD(K.eta).getFullYear() : K.remaining_kg != null && K.remaining_kg <= 0 ? "atteint" : "—";
  view.innerHTML = h`
    <div class="grid g4">
      ${tile("Déficit cumulé", nf(K.cum), `≈ ${km(K.loss_kg, 2)} kg de gras`, "var(--good)", "kcal")}
      ${tile("Moyenne par jour", K.avg != null ? signed(K.avg) : "—", `7 derniers jours : ${K.avg7 != null ? signed(K.avg7) : "—"}`, null, "kcal")}
      ${tile("Jours réussis", K.success_pct != null ? K.success_pct + " %" : "—", `${K.deficit_days} en déficit · ${K.surplus_days} en surplus · ${K.days} suivis`)}
      ${tile("Arrivée estimée", etaTxt, K.remaining_kg != null && K.remaining_kg > 0 ? `encore ${km(K.remaining_kg, 1)} kg au rythme actuel` : "")}
    </div>
    <div class="card section">
      <div class="row between wrap"><h2 style="margin:0">Vers ton objectif</h2><button class="btn sm" id="bd-params">Réglages</button></div>
      <div class="goal-track">
        <div class="gt-end"><span>Départ</span><b class="num">${P.start_weight ? km(P.start_weight, 1) : "—"} kg</b></div>
        <div class="gt-bar"><i style="width:${K.progress_pct ?? 0}%"></i><span class="gt-now" style="left:${K.progress_pct ?? 0}%"><b class="num">${K.weight_now != null ? km(K.weight_now, 1) : "—"}</b></span></div>
        <div class="gt-end r"><span>Objectif</span><b class="num">${P.goal_weight ? km(P.goal_weight, 1) : "—"} kg</b></div>
      </div>
      <p class="small muted" style="margin:10px 0 0">${K.weight_is_estimate ? "Poids estimé à partir du déficit cumulé : pèse-toi le matin 2-3 fois par semaine pour suivre le vrai poids." : `Poids réel (moyenne 7 jours)${K.trend_kg_week != null ? ` · tendance ${K.trend_kg_week > 0 ? "+" : ""}${km(K.trend_kg_week, 2)} kg/semaine` : ""}.`}
      ${P.bf_start ? ` Masse grasse : ${km(P.bf_start <= 1 ? P.bf_start * 100 : P.bf_start, 0)} % → ${P.bf_goal ? km(P.bf_goal <= 1 ? P.bf_goal * 100 : P.bf_goal, 0) + " %" : "—"}.` : ""}</p>
    </div>
    <div class="cols section"><div>
      <div class="card"><h2>Déficit cumulé</h2><div class="chart-box" style="height:220px"><canvas id="c-b-cum"></canvas></div>
        <p class="small muted" style="margin:6px 0 0">En pointillés : la trajectoire à ${nf(P.deficit_goal)} kcal/jour.</p></div>
      <div class="card section"><h2>Bilan jour par jour</h2><div class="chart-box" style="height:200px"><canvas id="c-b-day"></canvas></div></div>
    </div><div>
      <div class="card"><h2>Poids</h2><div class="chart-box" style="height:250px"><canvas id="c-b-w"></canvas></div>
        <p class="small muted" style="margin:6px 0 0">Points : pesées · ligne : moyenne 7 jours · pointillés : poids attendu d'après le déficit.</p></div>
      ${B.alerts.length ? `<div class="card section"><h2>À surveiller</h2>${B.alerts.map((a) => `<div class="warn-line">${esc(a)}</div>`).join("")}</div>` : ""}
    </div></div>`;
  $("#bd-params", view).onclick = () => openModal(h`<h3>Réglages du suivi</h3>${bodyParamsForm(P)}<div class="btns"><button class="btn primary" id="bp-save">Enregistrer</button></div>`, (el) => bindParams(el, closeModal));
  if (typeof Chart === "undefined" || !rows.length) return;
  chartDefaults();
  const labels = rows.map((r) => shortD(r.date));
  const good = css("--good"), bad = css("--bad"), mut = css("--muted"), acc = css("--accent");
  mkChart($("#c-b-cum", view), { type: "line", data: { labels, datasets: [
    { label: "Déficit cumulé", data: rows.map((r) => r.cum), borderColor: good, backgroundColor: css("--good-soft"), fill: "origin", pointRadius: 0, tension: 0.25 },
    { label: "Trajectoire visée", data: rows.map((r, i) => (i + 1) * (P.deficit_goal || 500)), borderColor: mut, borderDash: [5, 4], pointRadius: 0 },
  ] }, options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${nf(c.raw)} kcal` } } }, scales: { x: { grid: { display: false } } } } });
  mkChart($("#c-b-day", view), { type: "bar", data: { labels, datasets: [
    { label: "Bilan", data: rows.map((r) => r.balance), borderRadius: 4, backgroundColor: rows.map((r) => (r.balance == null ? "transparent" : r.balance >= 0 ? good : bad)) },
  ] }, options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${signed(c.raw)} kcal · ${rows[c.dataIndex].train}` } } }, scales: { x: { grid: { display: false } } } } });
  const kpk = P.kcal_per_kg || 7700;
  mkChart($("#c-b-w", view), { type: "line", data: { labels, datasets: [
    { label: "Pesée", data: rows.map((r) => r.weight), showLine: false, pointRadius: 3.5, pointBackgroundColor: acc, borderColor: acc },
    { label: "Moyenne 7 j", data: rows.map((r) => r.weight_avg7), borderColor: acc, pointRadius: 0, tension: 0.3, spanGaps: true },
    ...(P.start_weight ? [{ label: "Attendu (déficit)", data: rows.map((r) => +(P.start_weight - r.cum / kpk).toFixed(2)), borderColor: mut, borderDash: [5, 4], pointRadius: 0 }] : []),
    ...(P.goal_weight ? [{ label: "Objectif", data: rows.map(() => P.goal_weight), borderColor: good, borderDash: [2, 4], pointRadius: 0 }] : []),
  ] }, options: { plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${c.raw != null ? km(c.raw, 1) + " kg" : "—"}` } } }, scales: { x: { grid: { display: false } } } } });
}


// ================================================================ AVANT COURSE : recharge glucidique
NEED_COLOR.carb = "#f59e0b";
const CL_LEVEL = { full: "Recharge complète sur 3 jours", light: "Recharge légère la veille", none: "Pas de recharge nécessaire" };

function carbBanner(T) {
  if (T.carbs) {
    const pct = Math.min(100, Math.round((T.carbs.eaten / T.carbs.target) * 100));
    return h`<div class="card cl-banner" data-go-race><div class="row between"><div><div class="cl-k">Recharge glucidique · ${esc(T.carbs.title)}</div>
      <div class="cl-big num">${T.carbs.eaten} <small>/ ${T.carbs.target} g de glucides</small></div></div><span class="btn sm">Mes repas →</span></div>
      <div class="m-bar"><i style="width:${pct}%;background:#f59e0b"></i></div></div>`;
  }
  return "";
}
document.addEventListener("click", (e) => { if (e.target.closest("[data-go-race]")) setView("b-race"); });

async function renderBodyRace(view) {
  const D = await api("/api/carbload");
  if (!D.plans.length) { view.innerHTML = `<div class="card empty">Aucune course à venir dans ton plan.</div>`; return; }
  const P = D.plans[0];
  const others = D.plans.slice(1);
  const t = today();
  const dayCard = (d) => {
    const pct = Math.min(100, Math.round((d.eaten / d.carbs) * 100));
    const isT = d.date === t, past = d.date < t;
    return h`<div class="card cl-day ${isT ? "now" : ""} ${past ? "past" : ""}">
      <div class="row between"><div><div class="cl-k">${fmtDay(d.date)}${isT ? " · aujourd'hui" : ""}</div><h2 class="cl-t">${esc(d.title)}</h2></div><div class="cl-gkg">${String(d.g_per_kg).replace(".", ",")} g/kg</div></div>
      <div class="cl-big num">${d.eaten ? `${d.eaten} <small>/ ${d.carbs} g de glucides</small>` : `${d.carbs} <small>g de glucides</small>`}</div>
      <div class="m-bar"><i style="width:${pct}%;background:#f59e0b"></i></div>
      <div class="cl-macros"><span><b>${nf(d.kcal)}</b> kcal</span><span><b>${d.protein} g</b> protéines</span><span><b>${d.fat} g</b> lipides</span><span><b>${String(d.water_l).replace(".", ",")} L</b> d'eau</span></div>
      <div class="cl-meals">${d.meals.map((m, i) => `<label class="cl-meal ${m.done ? "on" : ""}"><input type="checkbox" data-cl="${d.date}|${i}" ${m.done ? "checked" : ""}>
        <div><div class="row between"><b>${esc(m.name)}</b><span class="cl-g">${m.carbs} g</span></div><div class="small muted">${esc(m.example)}</div></div></label>`).join("")}</div>
      <ul class="cl-tips">${d.tips.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  };
  const R = P.race_day;
  view.innerHTML = h`
    <div class="card cl-hero"><div class="cl-k">Avant course</div>
      <h2 class="cl-race">${esc(P.race)}</h2>
      <div class="cl-sub">${fmtDay(P.date)} · ${P.days_to === 0 ? "c'est aujourd'hui" : `dans ${P.days_to} jour${P.days_to > 1 ? "s" : ""}`} · ${km(P.effort.km, 1)} km${P.effort.dplus ? ` · ${P.effort.dplus} m D+` : ""} · ≈ ${Math.floor(P.effort.seconds / 3600)} h ${String(Math.round((P.effort.seconds % 3600) / 60)).padStart(2, "0")}</div>
      <div class="need-chip" style="--c:#f59e0b;margin-top:10px">${CL_LEVEL[P.level]}</div>
      <p class="small" style="margin:10px 0 0">Calculé pour <b>${km(P.weight, 1)} kg</b> (ta dernière pesée). ${P.level === "full" ? "Le principe : remplir au maximum tes réserves de glycogène pour ne pas taper le mur vers le 30e km. On ne mange pas « plus de tout » : on remplace une partie des graisses et des fibres par des glucides faciles à digérer." : P.level === "light" ? "Un effort de cette durée ne demande pas de grosse recharge : une veille riche en glucides suffit." : ""}</p>
      ${P.days_to > 3 && P.days.length ? `<div class="warn-line" style="margin-top:12px">La recharge commence le ${fmtDay(P.days[0].date).replace(/\.$/, "")}. D'ici là, tu continues ton suivi normal (et ton déficit s'arrête automatiquement 3 jours avant la course).</div>` : ""}
    </div>
    ${P.days.length ? `<div class="cl-days">${P.days.map(dayCard).join("")}</div>` : ""}
    <div class="cols section"><div>
      <div class="card cl-race-day"><div class="cl-k">Jour J · départ ${esc(R.start)}</div><h2 class="cl-t">Le matin de la course</h2>
        <div class="cl-tl">
          <div><b>${esc(R.wake)}</b><span>Réveil</span></div>
          <div><b>${esc(R.breakfast_at)}</b><span>Petit-déjeuner, 3 h avant : <b>~${R.breakfast_carbs} g</b> de glucides. ${esc(R.breakfast_example.replace(/^Exemple \(~\d+ g\) : /, "Par exemple : "))}</span></div>
          <div><b>−15 min</b><span>${esc(R.pre_start)}</span></div>
          <div><b>${esc(R.start)}</b><span>${esc(R.during)} <a href="#" id="cl-ravito">Ouvrir Ravito →</a></span></div>
          <div><b>Arrivée</b><span>${esc(R.after)}</span></div>
        </div></div>
      <div class="card section"><h2>La balance va monter</h2><p class="small" style="margin:0">Pendant la recharge, compte <b>+1 à 2 kg</b> : chaque gramme de glycogène stocké retient de l'eau. C'est exactement ce qu'on veut. Les pesées de J-3 à J+3 ne sont pas comptées dans ta tendance de poids, et le suivi du déficit reprend après la course.</p></div>
      <div class="card section"><h2>À éviter ces jours-là</h2><ul class="cl-tips">${P.avoid.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    </div><div>
      <div class="card"><h2>Combien de glucides dans…</h2>
        <table class="cl-foods"><tbody>${P.foods.map((f) => `<tr><td>${esc(f.name)}</td><td class="muted">${esc(f.portion)}</td><td class="r num"><b>${f.carbs} g</b></td></tr>`).join("")}</tbody></table>
        <p class="small muted" style="margin:8px 0 0">Valeurs moyennes, pour composer tes repas. MyFitnessPal te donne le détail exact si tu notes tes repas.</p></div>
      ${others.length ? `<div class="card section"><h2>Courses suivantes</h2>${others.map((o) => `<div class="cl-other"><b>${esc(o.race)}</b><span class="small muted">${fmtDay(o.date)} · ${CL_LEVEL[o.level]}${o.days[0] ? ` · ${o.days[0].carbs} g la veille` : ""}</span></div>`).join("")}</div>` : ""}
    </div></div>`;
  $("#cl-ravito", view).onclick = (e) => { e.preventDefault(); setView("nutrition"); };
  $$("[data-cl]", view).forEach((cb) => (cb.onchange = async () => {
    const [d, i] = cb.dataset.cl.split("|");
    try { await api(`/api/carbload/${d}/${i}`, { method: "POST", body: { done: cb.checked } }); render(); } catch (e) { toast(e.message, true); }
  }));
}
