/* Sub3 – Saison : bilans de course (prévu vs réalisé) et générateur de la prochaine prépa */
"use strict";

const PHASES = {
  base: { label: "Foncier", color: "#3b82f6", desc: "Volume facile, côtes et vitesse courte : on construit le moteur." },
  dev: { label: "Développement", color: "#8b5cf6", desc: "VMA et seuil : on élève le plafond." },
  spec: { label: "Spécifique", color: "#ff5a1f", desc: "Allure de course et sorties longues clés." },
  taper: { label: "Affûtage", color: "#12a150", desc: "Le volume baisse, l'intensité reste : on arrive frais." },
  cut: { label: "Coupure", color: "#9ca3af", desc: "Fin de saison : on récupère avant de reconstruire." },
  vol: { label: "Volume trail", color: "#0ea5e9", desc: "Sorties longues sur sentiers et week-ends enchaînés." },
  spec1: { label: "Bloc trail d'avril", color: "#f59e0b", desc: "Sorties longues avec dénivelé, répétition générale le 10 avril." },
  recup: { label: "Récupération", color: "#9ca3af", desc: "On récupère du trail, puis on repart." },
};
const PH = (p) => PHASES[p] || { label: p, color: "#999", desc: "" };
function phaseSegments(weeks) {
  const out = [];
  weeks.forEach((w) => { if (out.length && out[out.length - 1].phase === w.phase) out[out.length - 1].n++; else out.push({ phase: w.phase, n: 1 }); });
  return out;
}
const DIST_LABEL = { marathon: "Marathon", semi: "Semi-marathon", "10k": "10 km" };
const DIST_LABEL_ALL = { ...DIST_LABEL, ultra: "Ultra-trail" };
const RATING_LABELS = { jambes: "Jambes", souffle: "Souffle", ventre: "Ventre", mental: "Mental" };
const LESSON_ICON = { good: "✓", warn: "!", bad: "✕", info: "i" };

function seasonTab() { try { return localStorage.getItem("sub3_season_tab") || "bilans"; } catch { return "bilans"; } }
function setSeasonTab(t) { try { localStorage.setItem("sub3_season_tab", t); } catch { /* */ } state.debrief = null; render(); }

async function renderSeason(view) {
  const tab = state.debrief ? "bilans" : seasonTab();
  view.innerHTML = h`${raceNutriSwitch("season")}
    <div class="row between wrap" style="gap:10px;margin-bottom:14px">
      <div class="seg" id="season-tab"><button data-t="bilans" class="${tab === "bilans" ? "on" : ""}">Bilans de course</button><button data-t="prepa" class="${tab === "prepa" ? "on" : ""}">Prochaine prépa</button></div>
    </div><div id="season-body"><div class="skeleton"><i></i><i></i></div></div>`;
  bindRaceNutriSwitch(view);
  $$("#season-tab button", view).forEach((b) => (b.onclick = () => setSeasonTab(b.dataset.t)));
  const body = $("#season-body", view);
  if (state.debrief) return renderDebrief(body, state.debrief.aid, state.debrief.sid);
  if (tab === "prepa") return renderNextPrep(body);
  return renderRaceList(body);
}

function openDebrief(aid, sid) {
  state.debrief = { aid, sid };
  if (state.view !== "season") setView("season"); else { window.scrollTo({ top: 0 }); render(); }
}

// ================================================================ LISTE DES COURSES
async function renderRaceList(box) {
  const R = await api("/api/debriefs");
  if (!R.races.length) {
    box.innerHTML = `<div class="card empty">Aucune course pour l'instant.<br><span class="small">Tes courses du plan et celles marquées « Course » dans Garmin apparaîtront ici.</span></div>`;
    return;
  }
  box.innerHTML = h`<div class="card">
    <h2>Tes courses</h2>
    <p class="small muted" style="margin:-4px 0 10px">Après chaque course : ce qui était prévu, ce que tu as fait, et ce qu'on garde pour la suite.</p>
    ${R.races.map((r) => {
      const st = r.upcoming ? ["À venir", "var(--muted)"] : !r.done ? ["Pas d'activité liée", "var(--faint)"] : r.has_debrief ? ["Bilan fait", "var(--good)"] : ["Bilan à faire", "var(--accent)"];
      const d = parseD(r.date);
      return h`<div class="sess race-row ${r.done ? "" : "is-rest"}" data-aid="${r.aid || ""}" data-sid="${r.sid || ""}">
        <div class="sess-date"><b class="num">${d.getDate()}</b><span>${MONTHS[d.getMonth()]}</span></div>
        <div class="sess-main"><div class="sess-title">${esc(r.name)} ${r.is_main ? `<span class="chip COURSE">Objectif</span>` : ""}</div>
          <div class="sess-sum">${d.getFullYear()}${r.km ? ` · ${km(r.km)} km` : r.planned_km ? ` · ${km(r.planned_km)} km` : ""}</div></div>
        <div class="sess-side">${r.time_s && r.done ? `<b class="num">${hms(r.time_s)}</b>` : ""}<div class="small" style="color:${st[1]};font-weight:700">${st[0]}</div></div></div>`;
    }).join("")}</div>`;
  $$(".race-row", box).forEach((el) => {
    if (!el.dataset.aid) return;
    el.style.cursor = "pointer";
    el.onclick = () => openDebrief(el.dataset.aid, el.dataset.sid || null);
  });
}

// ================================================================ BILAN D'UNE COURSE
async function renderDebrief(box, aid, sid) {
  const B = await api(`/api/debrief/${aid}${sid ? `?sid=${sid}` : ""}`);
  const A = B.analysis, P = B.prep, fb = B.feedback || {};
  const gap = A.gap_goal_s;
  const gapHtml = gap == null ? "" : `<div class="debrief-gap ${gap <= 0 ? "good" : "bad"}">${gap <= 0 ? "−" : "+"}${dur(Math.abs(gap))} <span>vs objectif ${esc(A.goal)}</span></div>`;
  const sp = A.halves.split_pct;
  const spCol = sp <= 0.5 ? "var(--good)" : sp <= 3 ? "var(--warn)" : "var(--bad)";
  box.innerHTML = h`
    <button class="btn sm" id="db-back" style="margin-bottom:12px">← Toutes les courses</button>
    <div class="card debrief-hero">
      <div class="eyebrow-s">${fmtDay(B.date)} ${parseD(B.date).getFullYear()} · ${km(A.distance_km, A.distance_km % 1 ? 1 : 0)} km</div>
      <h2 style="margin:2px 0 10px;font-size:22px">${esc(B.name)}</h2>
      <div class="row wrap" style="gap:18px;align-items:flex-end">
        <div><div class="debrief-time num">${A.time}</div><div class="small muted">${A.pace}/km · ${A.official ? "temps officiel" : `temps montre${B.is_main ? " (ajoute ton temps officiel plus bas)" : ""}`}</div></div>
        ${gapHtml}
      </div>
      <div class="kv" style="margin-top:14px">
        <div><span>1re moitié</span><b class="num">${A.halves.first}</b></div>
        <div><span>2e moitié</span><b class="num">${A.halves.second}</b><span style="color:${spCol};font-weight:700">${sp > 0 ? "+" : ""}${km(sp)} %</span></div>
        <div><span>FC moyenne</span><b class="num">${A.avg_hr ?? "—"}</b><span>max ${A.max_hr ?? "—"}</span></div>
        <div><span>Conditions</span><b class="num">${A.weather?.temp != null ? Math.round(A.weather.temp) + " °C" : "—"}</b><span>${esc(A.weather?.desc || "")}${A.elev_gain ? ` · D+ ${Math.round(A.elev_gain)} m` : ""}</span></div>
      </div>
    </div>

    <div class="card section">
      <div class="row between wrap"><h2 style="margin:0">Allure kilomètre par kilomètre</h2><span class="small muted">référence : ${esc(A.ref_label)}</span></div>
      <div class="chart-box" style="height:260px;margin-top:10px"><canvas id="c-db-pace"></canvas></div>
      <div class="chart-box" style="height:150px;margin-top:8px"><canvas id="c-db-gap"></canvas></div>
      <p class="small muted" style="margin:6px 0 0">En bas : avance (au-dessus de 0) ou retard sur la référence.</p>
    </div>

    <div class="cols section"><div>
      <div class="card"><h2>Passages tous les 5 km</h2>
        <table class="db-table"><thead><tr><th>km</th><th class="r">Réel</th><th class="r">Prévu</th><th class="r">Écart</th><th class="r">Allure</th></tr></thead><tbody>
        ${A.by5.map((r) => `<tr><td class="num">${typeof r.km === "number" && r.km % 1 ? km(r.km) : r.km}</td><td class="r num"><b>${r.real_cum}</b></td><td class="r num muted">${r.plan_cum || "—"}</td>
          <td class="r num" style="color:${r.gap_s == null ? "inherit" : r.gap_s <= 0 ? "var(--good)" : "var(--bad)"}">${r.gap_s == null ? "—" : (r.gap_s <= 0 ? "−" : "+") + dur(Math.abs(r.gap_s))}</td>
          <td class="r num">${r.seg_pace || "—"}${r.plan_seg_pace ? `<span class="muted small"> / ${r.plan_seg_pace}</span>` : ""}</td></tr>`).join("")}
        </tbody></table>
        <div class="kv" style="margin-top:12px">
          <div><span>Départ (5 premiers km)</span><b class="num">${A.start5_pace || "—"}</b><span>${A.start_delta_s != null ? `${A.start_delta_s < 0 ? "" : "+"}${km(A.start_delta_s, 0)} s/km vs prévu` : ""}</span></div>
          <div><span>Décrochage</span><b class="num">${A.fade_km ? "km " + A.fade_km : "aucun"}</b><span>3 km à plus de 5 % du rythme du début</span></div>
          <div><span>Dérive cardiaque</span><b class="num">${A.hr_drift_pct != null ? (A.hr_drift_pct > 0 ? "+" : "") + km(A.hr_drift_pct) + " %" : "—"}</b><span>${A.hr_first ?? "—"} → ${A.hr_second ?? "—"} bpm</span></div>
        </div>
      </div>
      <div class="card" id="db-fuel"></div>
    </div><div>
      <div class="card"><div class="row between"><h2 style="margin:0">Ce qu'on retient</h2></div>
        <p class="small muted" style="margin:4px 0 10px">Coche ce que tu veux garder : ces leçons seront proposées dans ta prochaine prépa.</p>
        <div id="db-lessons">${B.lessons.map((l) => `<label class="lesson ${l.kind}"><input type="checkbox" data-lid="${l.id}" ${l.keep ? "checked" : ""}><i>${LESSON_ICON[l.kind] || "•"}</i><span>${esc(l.text)}</span></label>`).join("") || `<div class="muted small">Rien de particulier.</div>`}</div>
      </div>
      ${B.prediction ? h`<div class="card section"><h2>Les prédictions face au résultat</h2>
        <p class="small muted" style="margin:-4px 0 10px">Dernières prédictions avant la course (${fmtDay(B.prediction.date)}).</p>
        <table><tbody>${B.prediction.rows.map((r, i) => `<tr><td>${i === 0 ? "<b>" : ""}${esc(r.label)}${i === 0 ? "</b> <span class='chip AM'>la plus juste</span>" : ""}</td><td class="r num">${r.pred}</td>
          <td class="r num" style="color:${Math.abs(r.error_s) <= 120 ? "var(--good)" : Math.abs(r.error_s) <= 300 ? "var(--warn)" : "var(--bad)"}">${r.error_s >= 0 ? "+" : "−"}${dur(Math.abs(r.error_s))}</td></tr>`).join("")}</tbody></table></div>` : ""}
      <div class="card section"><h2>La prépa en chiffres</h2>
        <div class="kv">
          <div><span>16 dernières semaines</span><b class="num">${P.total_km} km</b><span>${P.runs} sorties</span></div>
          <div><span>Semaine la plus chargée</span><b class="num">${P.peak_week_km != null ? km(P.peak_week_km, 0) + " km" : "—"}</b></div>
          <div><span>Moyenne 8 dernières sem.</span><b class="num">${km(P.avg8_km, 0)} km</b></div>
          <div><span>Plus longue sortie</span><b class="num">${km(P.longest_km)} km</b>${P.long_28 != null ? `<span>${P.long_28} sortie${P.long_28 > 1 ? "s" : ""} de 28 km et +</span>` : ""}</div>
          ${P.adherence_pct != null ? `<div><span>Séances réalisées</span><b class="num">${P.adherence_pct} %</b><span>${P.sessions_done} / ${P.sessions_planned}</span></div>` : ""}
          ${P.key_score_avg != null ? `<div><span>Note moyenne séances clés</span><b class="num">${P.key_score_avg}</b><span>${P.key_sessions} séances</span></div>` : ""}
          <div><span>Sommeil, semaine d'avant</span><b class="num">${P.sleep_avg_h != null ? hfr(P.sleep_avg_h) : "—"}</b><span>${P.sleep_race_night_h != null ? `nuit d'avant : ${hfr(P.sleep_race_night_h)}` : ""}</span></div>
        </div>
        ${P.weeks.length > 2 ? `<div class="chart-box" style="height:150px;margin-top:12px"><canvas id="c-db-weeks"></canvas></div>` : ""}
      </div>
    </div></div>

    <div class="card section" id="db-feel">
      <h2>Ton ressenti</h2>
      <div class="grid g2">
        <div>${Object.entries(RATING_LABELS).map(([k, l]) => `<div class="rate-row"><span>${l}</span><div class="stars" data-k="${k}">${[1, 2, 3, 4, 5].map((n) => `<button data-n="${n}" class="${((fb.ratings || {})[k] || 0) >= n ? "on" : ""}">★</button>`).join("")}</div></div>`).join("")}
          <label class="f" style="margin-top:12px">Effort ressenti (1 à 10) : <b id="db-rpe-v">${fb.rpe || "—"}</b><input id="db-rpe" type="range" min="1" max="10" value="${fb.rpe || 8}"></label>
          <div class="grid g2"><label class="f">Temps officiel<input id="db-official" placeholder="h:mm:ss" value="${esc(fb.official_time || "")}"></label>
            <label class="f">Classement<input id="db-place" placeholder="ex. 312e / 9 000" value="${esc(fb.place || "")}"></label></div>
          ${B.is_main ? "" : `<label class="f">Objectif que tu avais<input id="db-goal" placeholder="h:mm:ss" value="${esc(fb.goal || "")}"></label>`}
        </div>
        <div>
          <label class="f">Ce qui a marché<textarea id="db-worked" rows="3" placeholder="Gestion du départ, gels toutes les 30 min, ...">${esc(fb.worked || "")}</textarea></label>
          <label class="f">À changer la prochaine fois (une idée par ligne)<textarea id="db-change" rows="3" placeholder="Plus de sorties longues à allure marathon&#10;Tester la boisson du ravito">${esc(fb.to_change || "")}</textarea></label>
          <label class="f">Incidents, douleurs, crampes<textarea id="db-incidents" rows="2">${esc(fb.incidents || "")}</textarea></label>
        </div>
      </div>
      <div class="btns"><button class="btn primary" id="db-save">Enregistrer le bilan</button><button class="btn" id="db-next">Préparer la prochaine prépa →</button></div>
    </div>
    <div class="card section" id="db-map"></div>`;

  $("#db-back", box).onclick = () => { state.debrief = null; render(); };
  // ---- graphiques
  if (typeof Chart !== "undefined") {
    chartDefaults();
    const S = A.splits.filter((s) => s.dist_m >= 300);
    const labels = S.map((s, i) => (s.dist_m >= 900 ? String(i + 1) : km(s.km)));
    const acc = css("--accent"), good = css("--good"), bad = css("--bad"), mut = css("--muted");
    const pv = S.map((s) => s.pace_s).concat(S.map((s) => s.plan_pace_s).filter(Boolean));
    const fast = Math.min(...pv) - 6, slow = Math.max(...pv) + 6;
    mkChart($("#c-db-pace", box), {
      data: { labels, datasets: [
        { type: "bar", label: "Allure réelle", data: S.map((s) => [slow, s.pace_s]), yAxisID: "y", borderRadius: 4, borderSkipped: false,
          backgroundColor: S.map((s) => (s.delta_s == null ? acc : s.delta_s <= 2 ? good : s.delta_s <= 8 ? css("--warn") : bad)) },
        { type: "line", label: "Prévu", data: S.map((s) => s.plan_pace_s), yAxisID: "y", borderColor: mut, borderDash: [5, 4], pointRadius: 0, borderWidth: 2 },
        { type: "line", label: "FC", data: S.map((s) => s.hr), yAxisID: "y2", borderColor: "#e5383b88", pointRadius: 0, borderWidth: 1.5, tension: 0.3 },
      ] },
      options: {
        scales: {
          y: { reverse: true, min: fast, max: slow, ticks: { callback: (v) => pace(v) } },
          y2: { position: "right", grid: { display: false }, ticks: { callback: (v) => `${v}` } }, x: { grid: { display: false } },
        },
        plugins: { tooltip: { callbacks: { label: (c) => (c.dataset.yAxisID === "y2" ? `FC ${Math.round(c.raw)} bpm` : `${c.dataset.label} ${pace(Array.isArray(c.raw) ? c.raw[1] : c.raw)}/km`) } } },
      },
    });
    mkChart($("#c-db-gap", box), {
      type: "line",
      data: { labels, datasets: [{ label: "Avance / retard", data: S.map((s) => -s.gap_s), borderColor: acc, backgroundColor: css("--accent-soft"), fill: "origin", pointRadius: 0, tension: 0.25 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => (c.raw >= 0 ? `${dur(c.raw)} d'avance` : `${dur(-c.raw)} de retard`) } } },
        scales: { x: { grid: { display: false } }, y: { ticks: { callback: (v) => (v === 0 ? "0" : `${v > 0 ? "+" : "−"}${dur(Math.abs(v))}`) } } } },
    });
    if (P.weeks.length > 2) {
      mkChart($("#c-db-weeks", box), {
        type: "bar",
        data: { labels: P.weeks.map((w) => shortD(w.start)), datasets: [{ label: "km", data: P.weeks.map((w) => w.km), backgroundColor: css("--z-ef"), borderRadius: 4 }] },
        options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } } } },
      });
    }
  }
  // ---- ravitaillement
  const qty = {};
  (B.fuel_log.items || []).forEach((it) => { if (it.product_id) qty[it.product_id] = it.qty; });
  const fuelBox = $("#db-fuel", box);
  const drawFuel = () => {
    const n = A.nutrition;
    fuelBox.innerHTML = h`<h2>Ravitaillement</h2>
      <p class="small muted" style="margin:-4px 0 10px">Ce que tu as vraiment pris pendant la course${n?.plan_carbs_total ? ` (prévu : ${n.plan_carbs_total} g)` : ""}.</p>
      ${B.products.filter((p) => p.kind !== "boisson" || true).map((p) => `<div class="fuel-item"><span style="flex:1;min-width:0"><b>${esc((p.brand ? p.brand + " " : "") + p.name)}</b> <span class="small muted">${p.carbs_g} g</span></span>
        <button class="btn sm" data-q="${p.id}" data-d="-1">−</button><b class="num" style="min-width:24px;text-align:center">${qty[p.id] || 0}</b><button class="btn sm" data-q="${p.id}" data-d="1">+</button></div>`).join("")}
      <div class="row" style="gap:10px;margin-top:10px"><label class="small muted" style="flex:1">Eau / boisson bue (ml)</label><input id="db-water" type="number" step="50" style="width:110px" value="${B.fuel_log.water_ml || ""}"></div>
      ${n && n.carbs_per_h != null ? `<div class="fuel-res ${n.level}"><b class="num">${n.carbs_per_h} g/h</b> · ${n.water_per_h} ml/h<div class="small">${esc(n.verdict || "")} ${esc(n.water_verdict || "")}</div></div>` : ""}`;
    $$("[data-q]", fuelBox).forEach((b) => (b.onclick = () => { const w = $("#db-water", fuelBox).value; qty[b.dataset.q] = Math.max(0, (qty[b.dataset.q] || 0) + Number(b.dataset.d)); drawFuel(); $("#db-water", fuelBox).value = w; }));
  };
  drawFuel();
  // ---- ressenti
  const ratings = { ...(fb.ratings || {}) };
  const feel = $("#db-feel", box);
  $$(".stars", feel).forEach((s) => $$("button", s).forEach((b) => (b.onclick = () => {
    const n = Number(b.dataset.n); ratings[s.dataset.k] = ratings[s.dataset.k] === n ? 0 : n;
    $$("button", s).forEach((x) => x.classList.toggle("on", Number(x.dataset.n) <= ratings[s.dataset.k]));
  })));
  let rpeTouched = !!fb.rpe;
  $("#db-rpe", feel).oninput = (e) => { rpeTouched = true; $("#db-rpe-v", feel).textContent = e.target.value; };
  const save = async () => {
    const keep = {};
    $$("#db-lessons input", box).forEach((c) => (keep[c.dataset.lid] = c.checked));
    await api(`/api/debrief/${aid}`, { method: "POST", body: {
      sid: B.sid, fuel_key: B.fuel_key, lessons_keep: keep,
      fuel: { items: Object.entries(qty).map(([product_id, q]) => ({ product_id, qty: q })), water_ml: Number($("#db-water", box).value || 0) },
      feedback: { ratings, rpe: rpeTouched ? $("#db-rpe", feel).value : null, official_time: $("#db-official", feel).value.trim(), place: $("#db-place", feel).value,
        goal: $("#db-goal", feel)?.value.trim() || fb.goal || "", worked: $("#db-worked", feel).value, to_change: $("#db-change", feel).value, incidents: $("#db-incidents", feel).value },
    } });
  };
  $("#db-save", feel).onclick = async (e) => {
    e.currentTarget.disabled = true;
    try { await save(); toast("Bilan enregistré"); render(); } catch (err) { toast(err.message, true); e.currentTarget.disabled = false; }
  };
  $("#db-next", feel).onclick = async () => {
    try { await save(); } catch (err) { toast(err.message, true); return; }
    state.debrief = null; try { localStorage.setItem("sub3_season_tab", "prepa"); } catch { /* */ } render();
  };
  trackMap($("#db-map", box), aid).then(() => { if (!$("#db-map .map", box)) $("#db-map", box)?.remove(); });
}

// ================================================================ PROCHAINE PRÉPA
async function renderNextPrep(box) {
  const N = await api("/api/nextprep");
  state.nextprep = N;
  if (N.draft && !state.prepEdit) return renderDraft(box, N);
  return renderPrepForm(box, N);
}

function weeksBetween(a, b) {
  if (!a || !b) return null;
  const s = parseD(a), r = parseD(b);
  const mon = (d) => { const x = new Date(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
  return Math.round((mon(r) - mon(s)) / (7 * 864e5)) + 1;
}

function renderPrepForm(box, N) {
  const S = N.suggest;
  const prev = N.draft?.meta?.params || {};
  const v = (k, d) => (prev[k] ?? d);
  let dist = v("distance", "marathon");
  box.innerHTML = h`
    <div class="card">
      <div class="eyebrow-s">Prochaine prépa</div>
      <h2 style="margin:2px 0 6px;font-size:22px">Construis ton prochain plan</h2>
      <p class="small muted" style="margin:0">Le plan est calculé à partir de ta forme actuelle (méthode VDOT de Jack Daniels), de ton historique de volume et des leçons de tes bilans. Tu pourras le relire semaine par semaine avant de l'activer.</p>
      <div class="ref-box">
        <div><span class="small muted">Ta référence</span><div><b>${esc(S.ref.label)}</b> · ${S.ref.time} sur ${km(S.ref.distance_km, S.ref.distance_km % 1 ? 1 : 0)} km</div></div>
        <div class="vdot-badge"><b class="num">${km(S.ref.vdot)}</b><span>VDOT</span></div>
      </div>
      <div class="kv" style="margin-top:10px">
        <div><span>Ton niveau sur 10 km</span><b class="num">${S.equivalents["10k"].replace(/^0:/, "")}</b></div>
        <div><span>Sur semi</span><b class="num">${S.equivalents.semi}</b></div>
        <div><span>Sur marathon</span><b class="num">${S.equivalents.marathon}</b></div>
        <div><span>Ta plus grosse semaine</span><b class="num">${S.peak_week_km} km</b></div>
      </div>
    </div>

    <div class="card section prep-form">
      <h2>La course visée</h2>
      <div class="grid g2">
        <label class="f">Nom de la course<input id="pf-name" placeholder="ex. Marathon de Paris" value="${esc(v("race_name", ""))}"></label>
        <label class="f">Ville<input id="pf-city" value="${esc(v("city", ""))}"></label>
      </div>
      <div class="f-row"><span class="small muted">Distance</span><div class="seg" id="pf-dist">${Object.entries(DIST_LABEL).map(([k, l]) => `<button data-v="${k}" class="${k === dist ? "on" : ""}">${l}</button>`).join("")}</div></div>
      <div class="grid g2" style="margin-top:12px">
        <label class="f">Date de la course<input id="pf-date" type="date" value="${esc(v("race_date", ""))}"></label>
        <label class="f">Objectif (h:mm:ss)<input id="pf-goal" placeholder="${S.goal_suggest[dist]}" value="${esc(v("goal", ""))}">
          <span class="hint" id="pf-goal-hint"></span></label>
      </div>

      <h2 class="section">Ton organisation</h2>
      <div class="grid g2">
        <label class="f">Début de la prépa<input id="pf-start" type="date" value="${esc(v("start_date", S.start_date))}"><span class="hint">Lundi après une semaine de coupure suite à ta dernière course.</span></label>
        <div><span class="small muted" style="font-weight:600">Durée</span><div id="pf-weeks" class="weeks-pill">—</div></div>
      </div>
      <div class="f-row"><span class="small muted">Séances de course par semaine</span><div class="seg" id="pf-days">${[3, 4, 5, 6].map((n) => `<button data-v="${n}" class="${n === Number(v("days_per_week", 5)) ? "on" : ""}">${n}</button>`).join("")}</div></div>
      <div class="f-row"><span class="small muted">Sortie longue le</span><div class="seg" id="pf-long"><button data-v="sam" class="${v("long_day", "dim") === "sam" ? "on" : ""}">Samedi</button><button data-v="dim" class="${v("long_day", "dim") === "dim" ? "on" : ""}">Dimanche</button></div></div>
      <div class="grid g2" style="margin-top:12px">
        <label class="f">Volume de départ (km/semaine)<input id="pf-startkm" type="number" step="5" value="${v("start_km", S.start_km)}"><span class="hint">Conseillé : ${S.start_km} km, environ 60 % de ta plus grosse semaine.</span></label>
        <label class="f">Pic de volume (km/semaine)<input id="pf-peak" type="number" step="5" value="${v("peak_km", S.peak_km)}"><span class="hint">Conseillé : ${S.peak_km} km. Au-dessus de ce que tu as déjà fait, monte prudemment.</span></label>
      </div>
      <label class="check"><input type="checkbox" id="pf-renfo" ${v("renfo", true) ? "checked" : ""}> Ajouter du renforcement (20 min après certains footings)</label>

      ${S.lessons.length ? h`<h2 class="section">Leçons de tes bilans</h2>
        <p class="small muted" style="margin:-4px 0 8px">Elles seront ajoutées aux règles du plan et lues par le coach.</p>
        ${S.lessons.map((l, i) => `<label class="lesson info"><input type="checkbox" class="pf-lesson" data-i="${i}" checked><i>i</i><span>${esc(l)}</span></label>`).join("")}` : ""}
      <label class="f section">Autre chose à prendre en compte (une idée par ligne)<textarea id="pf-extra" rows="2" placeholder="ex. Pas de séance le mercredi">${esc((prev.lessons || []).filter((x) => !S.lessons.includes(x)).join("\n"))}</textarea></label>

      <div class="btns"><button class="btn primary" id="pf-go">Générer le plan</button>${N.draft ? `<button class="btn" id="pf-cancel">Revenir au brouillon</button>` : ""}</div>
    </div>`;

  const seg = (id, cb) => $$(`#${id} button`, box).forEach((b) => (b.onclick = () => { $$(`#${id} button`, box).forEach((x) => x.classList.toggle("on", x === b)); cb && cb(b.dataset.v); }));
  const upd = () => {
    const w = weeksBetween($("#pf-start", box).value, $("#pf-date", box).value);
    $("#pf-weeks", box).innerHTML = w == null ? "Choisis la date de course" : w < 6 ? `<span style="color:var(--bad)">${w} semaines : trop court</span>` : `<b class="num">${w}</b> semaines${w > 24 ? " (long : le foncier sera étiré)" : w < 12 ? " (court : on ira à l'essentiel)" : ""}`;
    $("#pf-goal", box).placeholder = S.goal_suggest[dist];
    $("#pf-goal-hint", box).innerHTML = `Aujourd'hui tu vaux ≈ ${S.equivalents[dist].replace(/^0:/, "")}. Objectif réaliste après une bonne prépa : <a href="#" id="pf-goal-use">${S.goal_suggest[dist].replace(/^0:/, "")}</a>`;
    $("#pf-goal-use", box).onclick = (e) => { e.preventDefault(); $("#pf-goal", box).value = S.goal_suggest[dist]; };
  };
  seg("pf-dist", (x) => { dist = x; upd(); });
  seg("pf-days"); seg("pf-long");
  ["#pf-start", "#pf-date"].forEach((s) => ($(s, box).oninput = upd));
  upd();
  const cancel = $("#pf-cancel", box);
  if (cancel) cancel.onclick = () => { state.prepEdit = false; render(); };
  $("#pf-go", box).onclick = async (e) => {
    const btn = e.currentTarget;
    const lessons = $$(".pf-lesson", box).filter((c) => c.checked).map((c) => S.lessons[Number(c.dataset.i)])
      .concat($("#pf-extra", box).value.split("\n").map((x) => x.trim()).filter(Boolean));
    const body = {
      race_name: $("#pf-name", box).value.trim(), city: $("#pf-city", box).value.trim(), distance: dist,
      race_date: $("#pf-date", box).value, start_date: $("#pf-start", box).value, goal: $("#pf-goal", box).value.trim() || S.goal_suggest[dist],
      days_per_week: Number($("#pf-days button.on", box).dataset.v), long_day: $("#pf-long button.on", box).dataset.v,
      start_km: Number($("#pf-startkm", box).value), peak_km: Number($("#pf-peak", box).value), renfo: $("#pf-renfo", box).checked, lessons,
    };
    if (!body.race_date) { toast("Indique la date de la course", true); return; }
    btn.disabled = true; btn.textContent = "Calcul du plan…";
    try {
      await api("/api/nextprep/generate", { method: "POST", body });
      state.prepEdit = false; render(); toast("Plan généré : relis-le avant de l'activer");
    } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Générer le plan"; }
  };
}

function renderDraft(box, N) {
  const D = N.draft, M = D.meta, prm = M.params;
  const weeks = M.weeks;
  const bridge = N.current.bridge || [];
  const goalS = hms_to_s(D.race.goal);
  const peak = Math.max(...weeks.filter((w) => !w.race).map((w) => w.planned_km));
  const totalKm = weeks.reduce((a, w) => a + w.planned_km, 0);
  const ultra = prm.distance === "ultra";
  const keyS = D.sessions.filter((s) => ["AM", "SEMI", "COURSE"].includes(s.type) && !ultra || s.type === "COURSE" || (s.type === "SL" && (s.planned_km >= (D.race.distance_km > 40 ? 28 : 18) || /AM|semi/.test(s.title)))).slice(ultra ? -12 : -8);
  const zoneRows = ["RECUP", "EF", "ULTRA", "AM", "SEMI", "SEUILC", "SEUIL", "VMA"].filter((z) => D.paces[z]);
  box.innerHTML = h`
    <div class="card draft-hero">
      <div class="row between wrap" style="gap:12px">
        <div><div class="eyebrow-s">${M.custom ? "Plan sur mesure" : "Brouillon"} · ${DIST_LABEL_ALL[prm.distance] || ""}</div>
          <h2 style="margin:2px 0 4px;font-size:24px">${esc(D.race.name)}</h2>
          <div class="small muted">${fmtDay(D.race.date)} ${parseD(D.race.date).getFullYear()}${prm.city ? " · " + esc(prm.city) : ""}</div></div>
        <div style="text-align:right"><div class="small muted">Objectif</div>${D.race.finish_only
          ? `<div class="debrief-time" style="font-size:34px">Finir</div><div class="small muted" style="max-width:240px">${esc(D.race.goal_note || "")}</div>`
          : `<div class="debrief-time num" style="font-size:34px">${esc(D.race.goal)}</div><div class="small num">${pace(goalS / D.race.distance_km)}/km</div>`}</div>
      </div>
      <div class="kv" style="margin-top:14px">
        <div><span>Durée</span><b class="num">${M.n_weeks} sem.</b><span>du ${fmtDay(prm.start_date)}</span></div>
        <div><span>Volume au pic</span><b class="num">${km(peak, 0)} km</b><span>${km(totalKm, 0)} km au total</span></div>
        <div><span>Séances / semaine</span><b class="num">${prm.days_per_week}</b><span>sortie longue le ${prm.long_day === "sam" ? "samedi" : "dimanche"}</span></div>
        ${M.vdot_ref ? `<div><span>VDOT</span><b class="num">${km(M.vdot_ref)} → ${km(M.vdot_goal)}</b><span>${M.vdot_goal - M.vdot_ref > 0 ? "+" : ""}${km(M.vdot_goal - M.vdot_ref)} point${Math.abs(M.vdot_goal - M.vdot_ref) >= 2 ? "s" : ""} à gagner</span></div>`
          : `<div><span>Plus longue sortie</span><b class="num">${M.longest_km} km</b><span>${(M.extra_races || []).map((r) => esc(r.name) + " le " + fmtDay(r.date)).join(", ")}</span></div>`}
      </div>
      ${M.warnings.map((w) => `<div class="warn-line">${esc(w)}</div>`).join("")}
    </div>

    <div class="card section">
      <h2>Les phases</h2>
      <div class="phase-bar">${phaseSegments(weeks).map((g) => `<div style="flex:${g.n};background:${PH(g.phase).color}" title="${esc(PH(g.phase).label)}"><b>${PH(g.phase).label}</b><span>${g.n} sem.</span></div>`).join("")}</div>
      <div class="phase-legend">${[...new Set(weeks.map((w) => w.phase))].map((p) => `<div><i style="background:${PH(p).color}"></i><b>${PH(p).label}</b> <span class="muted">${PH(p).desc}</span></div>`).join("")}</div>
      <div class="chart-box" style="height:210px;margin-top:14px"><canvas id="c-draft"></canvas></div>
      <p class="small muted" style="margin:6px 0 0">Barres claires : semaines allégées (toutes les 4 semaines). Progression de 10 % maximum par semaine.</p>
    </div>

    <div class="cols section"><div>
      <div class="card"><h2>Tes nouvelles allures</h2>
        <table><thead><tr><th>Zone</th><th class="r">Plan actuel</th><th class="r">Nouveau plan</th></tr></thead><tbody>
          ${zoneRows.map((z) => `<tr><td><span class="zdot" style="background:${ZONE_COLORS[z] || "#999"}"></span>${esc(D.pace_labels[z] || z)}</td>
            <td class="r num muted">${N.current.paces[z] ? N.current.paces[z].join("–") : "—"}</td><td class="r num"><b>${D.paces[z].join("–")}</b></td></tr>`).join("")}
        </tbody></table>
        <p class="small muted" style="margin:8px 0 0">${M.vdot_train ? `Calculées sur ta forme actuelle (VDOT ${km(M.vdot_train)}) : on s'entraîne à son niveau, pas à celui visé. L'allure spécifique, elle, est celle de ton objectif.`
          : "Tes allures actuelles, plus l'allure 100 km (sur le plat). En trail, c'est la fréquence cardiaque (Z2) qui pilote les sorties longues, pas l'allure. Elles seront recalibrées après ton marathon."}</p>
      </div>
      <div class="card section"><h2>Les règles de ce plan</h2>
        <ul class="review-list small">${D.rules.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
    </div><div>
      <div class="card"><h2>Les séances clés</h2>
        ${bridge.flatMap((w) => w.sessions.filter((s) => s.type === "COURSE")).map((s) => sessionRow(s)).join("")}${keyS.map((s) => draftRow(s, M)).join("") || `<div class="muted small">—</div>`}</div>
    </div></div>

    <div class="card section"><div class="row between wrap"><h2 style="margin:0">Semaine par semaine</h2><button class="btn sm" id="dr-expand">Tout déplier</button></div>
      <div id="dr-weeks" style="margin-top:10px">${bridge.length ? `<div class="bridge-head">Avant la prépa · ton plan actuel</div>` : ""}${bridge.map((w) => h`<details class="week-acc bridge" ${w.start <= today() && today() <= iso(new Date(parseD(w.start).getTime() + 6 * 864e5)) ? "open" : ""}><summary>
          <span class="wk-n num">—</span><span class="wk-d">${fmtDay(w.start)}</span>
          <span class="wk-ph">${w.race ? `Course : ${esc(w.sessions.filter((s) => s.type === "COURSE").map((s) => s.title.split(" –")[0]).join(", "))}` : "Plan actuel"}</span>
          <span class="wk-km num"><b>${km(w.planned_km, 0)}</b> km</span></summary>
          ${w.sessions.map((s) => sessionRow(s)).join("")}</details>`).join("")}
        ${bridge.length ? `<div class="bridge-head" style="margin-top:14px">${esc(D.race.name)}</div>` : ""}${weeks.map((w, i) => {
        const end = iso(new Date(parseD(w.start).getTime() + 6 * 864e5));
        const ss = D.sessions.filter((s) => s.date >= w.start && s.date <= end);
        return h`<details class="week-acc" ${i === 0 && !bridge.length ? "open" : ""}><summary>
          <span class="wk-n num">S${i + 1}</span><span class="wk-d">${fmtDay(w.start)}</span>
          <span class="wk-ph" style="color:${PH(w.phase).color}">${w.race ? "Course" : PH(w.phase).label}${w.cutback ? " · allégée" : ""}</span>
          <span class="wk-km num"><b>${km(w.planned_km, 0)}</b> km</span></summary>
          ${w.note ? `<div class="small muted" style="padding:2px 4px 6px">${esc(w.note)}</div>` : ""}${ss.map((s) => draftRow(s, M)).join("")}</details>`;
      }).join("")}</div></div>

    <div class="card section activate-card">
      <h2>Activer ce plan</h2>
      <p class="small" style="margin:0 0 6px">À l'activation :</p>
      <ul class="review-list small">
        <li>ton plan actuel (${esc(N.current.race.name)}) est archivé, et l'historique des séances passées reste dans le Plan et les statistiques ;</li>
        <li>les séances à partir du ${fmtDay(prm.start_date)} sont remplacées par ce nouveau plan, la page Jour J passe sur ${esc(D.race.name)} ;</li>
        <li>l'envoi automatique sur la montre et le coach continuent avec le nouveau plan.</li>
      </ul>
      ${N.current.end && N.current.end >= prm.start_date ? `<div class="warn-line">Ton plan actuel a encore des séances après le ${fmtDay(prm.start_date)} : elles seront remplacées.</div>` : ""}
      ${M.auto_activate ? `<div class="sched-line">✓ Activation automatique programmée le ${fmtDay(prm.start_date)} au matin.</div>` : ""}
      <div class="btns">${prm.start_date > today()
        ? `${M.auto_activate ? `<button class="btn" id="dr-unsched">Annuler l'activation automatique</button>` : `<button class="btn primary" id="dr-sched">Activer automatiquement le ${fmtDay(prm.start_date)}</button>`}<button class="btn" id="dr-activate">Activer maintenant</button>`
        : `<button class="btn primary" id="dr-activate">Activer ce plan</button>`}
        ${M.custom ? "" : `<button class="btn" id="dr-edit">Modifier les réglages</button>`}<button class="btn danger" id="dr-del">Supprimer le brouillon</button></div>
      ${M.custom ? `<p class="small muted" style="margin:10px 0 0">Plan construit sur mesure : pour le modifier, demande-le au coach ou dans Cowork.</p>` : ""}
      ${N.archives.length ? `<p class="small muted" style="margin:12px 0 0">Plans archivés : ${N.archives.map(esc).join(", ")}</p>` : ""}
    </div>`;

  if (typeof Chart !== "undefined") {
    chartDefaults();
    mkChart($("#c-draft", box), {
      type: "bar",
      data: { labels: bridge.map((w) => shortD(w.start)).concat(weeks.map((w, i) => `S${i + 1}`)), datasets: [{ label: "km", data: bridge.map((w) => w.planned_km).concat(weeks.map((w) => w.planned_km)), borderRadius: 5,
        backgroundColor: bridge.map((w) => (w.race ? "#ff5a1f99" : "#9ca3af88")).concat(weeks.map((w) => PH(w.phase).color + (w.cutback ? "66" : "ee"))) }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: (c) => { const i = c[0].dataIndex; return i < bridge.length ? `Semaine du ${fmtDay(bridge[i].start)}` : `${c[0].label} · ${fmtDay(weeks[i - bridge.length].start)}`; },
        label: (c) => { const i = c.dataIndex; if (i < bridge.length) return `${km(c.raw, 0)} km · plan actuel${bridge[i].race ? " (course)" : ""}`; const w = weeks[i - bridge.length]; return `${km(c.raw, 0)} km · ${PH(w.phase).label}${w.cutback ? " (allégée)" : ""}`; } } } },
        scales: { x: { grid: { display: false } } } },
    });
  }
  $$(".draft-row", box).forEach((el) => (el.onclick = () => showDraftSession(D, el.dataset.sid)));
  $$(".sess[data-sid]:not(.draft-row)", box).forEach((el) => (el.onclick = () => showSession(el.dataset.sid)));
  $("#dr-expand", box).onclick = (e) => { const open = e.currentTarget.textContent === "Tout déplier"; $$(".week-acc", box).forEach((d) => (d.open = open)); e.currentTarget.textContent = open ? "Tout replier" : "Tout déplier"; };
  const ed = $("#dr-edit", box);
  if (ed) ed.onclick = () => { state.prepEdit = true; render(); };
  const sc = $("#dr-sched", box), us = $("#dr-unsched", box);
  if (sc) sc.onclick = async () => { await api("/api/nextprep/schedule", { method: "POST", body: { on: true } }); toast(`Activation programmée le ${fmtDay(prm.start_date)}`); render(); };
  if (us) us.onclick = async () => { await api("/api/nextprep/schedule", { method: "POST", body: { on: false } }); render(); };
  $("#dr-del", box).onclick = async () => { if (!confirm("Supprimer ce brouillon ?")) return; await api("/api/nextprep", { method: "DELETE" }); render(); };
  $("#dr-activate", box).onclick = () => {
    openModal(h`<h3>Activer « ${esc(D.race.name)} » ?</h3>
      ${prm.start_date > today() ? `<div class="warn-line">Attention : la prépa démarre le ${fmtDay(prm.start_date)}. En activant maintenant, la page Jour J passe tout de suite sur ${esc(D.race.name)}, alors que ton plan actuel n'est pas terminé.</div>` : ""}
      <p class="small">Ton plan actuel est archivé (rien n'est perdu). Les séances à partir du ${fmtDay(prm.start_date)} sont remplacées et celles déjà envoyées sur la montre après cette date sont retirées.</p>
      <div class="btns"><button class="btn primary" id="act-go">Oui, activer</button><button class="btn" id="act-no">Annuler</button></div>`, (el) => {
      $("#act-no", el).onclick = closeModal;
      $("#act-go", el).onclick = async (e) => {
        e.currentTarget.disabled = true;
        try {
          await api("/api/nextprep/activate", { method: "POST" });
          closeModal(); state.plan = null; state.race = null; toast("Nouveau plan activé, bonne prépa !"); setView("plan");
        } catch (err) { toast(err.message, true); e.currentTarget.disabled = false; }
      };
    });
  };
}

function hms_to_s(t) { const p = String(t).split(":").map(Number); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + (p[1] || 0); }

function draftRow(s, M) {
  const d = parseD(s.date);
  const rest = s.type === "REPOS";
  return h`<div class="sess draft-row ${rest ? "is-rest" : ""}" data-sid="${s.id}" style="${rest ? "" : "cursor:pointer"}">
    <div class="sess-date"><b class="num">${d.getDate()}</b><span>${DAYS[d.getDay()]}</span></div>
    <div class="sess-main"><div class="sess-title">${rest ? "" : `<span class="chip ${s.type}">${s.type}</span> `}${esc(s.title)}</div>
      ${rest ? "" : `<div class="sess-sum">${esc(M.summaries?.[s.id] || "")}</div>`}</div>
    <div class="sess-side">${rest ? "" : `<div class="num"><b>${km(s.planned_km)}</b> km</div>`}</div></div>`;
}

function showDraftSession(D, sid) {
  const s = D.sessions.find((x) => x.id === sid);
  if (!s || s.type === "REPOS") return;
  openModal(h`<div class="eyebrow-s">${fmtDay(s.date)} ${parseD(s.date).getFullYear()} · brouillon</div>
    <h3><span class="chip ${s.type}">${s.type}</span> ${esc(s.title)}</h3>
    <div class="small muted">${estimateText(s.steps, D.paces)}</div>
    ${profileHtml(s.steps, D.paces)}
    ${stepsReadable(s.steps, D.paces)}
    ${s.description ? `<p class="small" style="margin-top:12px">${esc(s.description)}</p>` : ""}`);
}
