/* Élan – nutrition (tier list, stock, carnet), fiche de préparation, prédiction, carte, calendrier mois */
"use strict";

const TIER_COLORS = { S: "#ff6b6b", A: "#ff9f43", B: "#feca57", C: "#48dbfb", D: "#a29bfe", "?": "var(--card-3)" };
const KIND_LABELS_N = { gel: "Gel", boisson: "Boisson", solide: "Solide" };

// ================================================================ NUTRITION (vue)
async function renderNutrition(view) {
  const N = await api("/api/nutrition");
  state.nutrition = N;
  const crit = N.criteria;
  const tierRow = (t) => {
    const items = N.board[t] || [];
    return `<div class="tier-row"><div class="tier-label" style="background:${TIER_COLORS[t]}">${t === "?" ? "À tester" : t}</div>
      <div class="tier-items">${items.length ? items.map(prodChip).join("") : `<span class="muted small" style="padding:10px">—</span>`}</div></div>`;
  };
  const missing = N.gels_missing;
  view.innerHTML = h`
    ${raceNutriSwitch("nutrition")}
    <div class="grid g4">
      ${tile("Gels en stock", N.gel_stock, "tous parfums confondus")}
      ${tile("Besoin d'ici la course", N.gels_needed, "sorties longues + course")}
      ${tile("À racheter", missing, missing ? `≈ ${km(N.restock_cost, 0)} € en ${esc(N.favorite?.brand || "")}` : "stock suffisant", missing ? "var(--warn)" : "var(--good)")}
      ${tile("Gel favori", N.favorite ? `<span style="font-size:18px">${esc(N.favorite.brand)}</span>` : "—", N.favorite ? `${esc(N.favorite.name)} · ${N.favorite.carbs_g} g` : "note tes gels", N.favorite?.tier ? TIER_COLORS[N.favorite.tier] : null)}
    </div>
    ${N.prep.map(prepCardHtml).join("")}
    <div class="card section">
      <div class="row between wrap"><h2 style="margin:0">Classement de tes produits</h2><button class="btn sm" id="np-add">+ Produit</button></div>
      <p class="small muted" style="margin:6px 0 12px">Note chaque produit après l'avoir testé en sortie (${Object.values(crit).join(", ").toLowerCase()}) : le rang se calcule tout seul. Le ventre compte le plus.</p>
      <div class="tier-board">${["S", "A", "B", "C", "D", "?"].map(tierRow).join("")}</div>
    </div>
    <div class="cols section"><div>
      <div class="card"><h2>Carnet de ravitaillement</h2>
        ${Object.keys(N.analyses).length ? Object.entries(N.analyses).map(([sid, a]) => `<div class="fuel-row" data-sid="${sid}">
            <div class="fuel-gauge ${a.level || ""}"><b class="num">${a.carbs_per_h ?? "—"}</b><span>g/h</span></div>
            <div style="flex:1;min-width:0"><div class="sess-title">${esc(a.title)}</div><div class="small muted">${fmtDay(a.date)} · ${a.carbs_g} g · ${a.water_ml} ml${a.target ? ` · objectif ${a.target[0]}-${a.target[1]} g/h` : ""}</div>
            <div class="small" style="color:var(--${a.level === "good" ? "good" : a.level === "warn" ? "warn" : "bad"})">${esc(a.verdict || "")}</div></div></div>`).join("")
          : `<div class="empty small">Rien de noté pour l'instant.<br>Ouvre une sortie longue dans le Plan → « Ravitaillement ».</div>`}
      </div></div><div>
      <div class="card"><h2>Gels à prévoir</h2>
        ${N.needs.length ? `<table><tbody>${N.needs.map((n) => `<tr><td>${n.date === "course" ? "<b>Jour J</b>" : fmtDay(n.date)}</td><td class="small">${esc(n.title)}</td><td class="r num"><b>${n.gels}</b></td></tr>`).join("")}</tbody></table>` : `<div class="muted small">Aucune sortie longue à venir.</div>`}
        <p class="small muted" style="margin:10px 0 0">Calcul : 45 g/h (2h30 et moins) ou 60 g/h au-delà, avec ton gel favori, en comptant qu'une partie peut venir de la boisson.</p>
      </div>
    </div></div>`;
  bindRaceNutriSwitch(view);
  $$(".prod-chip", view).forEach((c) => (c.onclick = () => editProduct(N.products.find((p) => p.id === c.dataset.pid))));
  $("#np-add", view).onclick = () => editProduct({ kind: "gel", ratings: {}, stock: 0 });
  $$(".fuel-row", view).forEach((r) => (r.onclick = () => showSession(r.dataset.sid)));
}

function prodChip(p) {
  return `<button class="prod-chip" data-pid="${p.id}"><b>${esc(p.brand || "")} ${esc(p.name)}</b><span>${p.carbs_g} g · ${KIND_LABELS_N[p.kind] || ""}${p.price_eur ? ` · ${km(p.price_eur, 2)} €` : ""}</span>
    ${["gel", "solide"].includes(p.kind) ? `<i class="stock ${p.stock ? "" : "zero"}">${p.stock} en stock</i>` : ""}</button>`;
}

function editProduct(p) {
  const crit = state.nutrition?.criteria || { ventre: "Ventre", gout: "Goût", pratique: "Ouverture / prise en courant", texture: "Texture" };
  const r = { ...(p.ratings || {}) };
  openModal(h`<h3>${p.id ? esc((p.brand || "") + " " + p.name) : "Nouveau produit"}</h3>
    <div class="grid g2" style="margin-top:12px">
      <label class="f">Marque<input id="pp-brand" value="${esc(p.brand || "")}"></label>
      <label class="f">Nom<input id="pp-name" value="${esc(p.name || "")}"></label>
      <label class="f">Type<select id="pp-kind">${Object.entries(KIND_LABELS_N).map(([k, l]) => `<option value="${k}" ${k === p.kind ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="f">Glucides par unité (g)<input id="pp-carbs" type="number" value="${p.carbs_g ?? ""}"></label>
      <label class="f">Caféine (mg)<input id="pp-caf" type="number" value="${p.caffeine_mg ?? 0}"></label>
      <label class="f">Prix unitaire (€)<input id="pp-price" type="number" step="0.01" value="${p.price_eur ?? ""}"></label>
    </div>
    <div class="row" style="gap:10px;margin:4px 0 14px"><span class="small muted" style="flex:1">Stock</span>
      <button class="btn sm" id="pp-minus">−</button><b class="num" id="pp-stock" style="min-width:30px;text-align:center;font-size:18px">${p.stock || 0}</b><button class="btn sm" id="pp-plus">+</button>
      <button class="btn sm" id="pp-plus6">+6</button></div>
    <h2>Ta note</h2>
    ${Object.entries(crit).map(([k, l]) => `<div class="rate-row"><span>${l}</span><div class="stars" data-k="${k}">${[1, 2, 3, 4, 5].map((n) => `<button data-n="${n}" class="${(r[k] || 0) >= n ? "on" : ""}">★</button>`).join("")}</div></div>`).join("")}
    <label class="f" style="margin-top:10px">Forcer le rang<select id="pp-tier"><option value="">Automatique</option>${["S", "A", "B", "C", "D"].map((t) => `<option ${p.tier_override === t ? "selected" : ""}>${t}</option>`).join("")}</select></label>
    <label class="f">Notes<textarea id="pp-notes">${esc(p.notes || "")}</textarea></label>
    <div class="btns"><button class="btn primary" id="pp-save">Enregistrer</button>${p.id ? `<button class="btn danger" id="pp-del">Supprimer</button>` : ""}</div>`, (el) => {
    let stock = Number(p.stock || 0);
    const setStock = (v) => { stock = Math.max(0, v); $("#pp-stock", el).textContent = stock; };
    $("#pp-minus", el).onclick = () => setStock(stock - 1);
    $("#pp-plus", el).onclick = () => setStock(stock + 1);
    $("#pp-plus6", el).onclick = () => setStock(stock + 6);
    $$(".stars", el).forEach((s) => $$("button", s).forEach((b) => (b.onclick = () => {
      const n = Number(b.dataset.n); r[s.dataset.k] = r[s.dataset.k] === n ? 0 : n;
      $$("button", s).forEach((x) => x.classList.toggle("on", Number(x.dataset.n) <= r[s.dataset.k]));
    })));
    $("#pp-save", el).onclick = async () => {
      try {
        await api("/api/nutrition/products", { method: "POST", body: { id: p.id, brand: $("#pp-brand", el).value, name: $("#pp-name", el).value || "Produit",
          kind: $("#pp-kind", el).value, carbs_g: $("#pp-carbs", el).value, caffeine_mg: $("#pp-caf", el).value, price_eur: $("#pp-price", el).value,
          stock, ratings: r, tier_override: $("#pp-tier", el).value || null, notes: $("#pp-notes", el).value } });
        toast("Produit enregistré"); closeModal(); render();
      } catch (e) { toast(e.message, true); }
    };
    const del = $("#pp-del", el);
    if (del) del.onclick = async () => { if (!confirm("Supprimer ce produit ?")) return; await api(`/api/nutrition/products/${p.id}`, { method: "DELETE" }); closeModal(); render(); };
  });
}

function raceNutriSwitch(active) {
  return `<div class="seg" id="rn-switch" style="margin-bottom:14px"><button data-v="race" class="${active === "race" ? "on" : ""}">Course</button><button data-v="nutrition" class="${active === "nutrition" ? "on" : ""}">Nutrition</button><button data-v="season" class="${active === "season" ? "on" : ""}">Saison</button></div>`;
}
function bindRaceNutriSwitch(view) {
  $$("#rn-switch button", view).forEach((b) => (b.onclick = () => { state.debrief = null; setView(b.dataset.v); }));
}

// ================================================================ FICHE DE PRÉPARATION
function prepCardHtml(c) {
  const times = c.gel_times_min.map((m) => (m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}` : `${m} min`)).join(" · ");
  return h`<div class="card prep section">
    <div class="row between wrap"><div><div class="eyebrow-s">Sortie longue ${esc(c.when)}</div><h3 style="margin:2px 0 0">${esc(c.title)}</h3></div>
      <span class="small muted num">≈ ${dur(c.duration_s)}</span></div>
    <div class="kv" style="margin-top:12px">
      <div><span>À emporter</span><b class="num">${c.gels} gel${c.gels > 1 ? "s" : ""}</b><span>${esc(c.gel)}</span></div>
      <div><span>Boisson</span><b class="num">${c.water_ml} ml</b><span>idéalement avec du sucre et du sel</span></div>
      <div><span>Objectif</span><b class="num">${c.target_gph} g/h</b><span>premier gel à 30 min</span></div>
    </div>
    <div class="small" style="margin-top:10px"><b>Gels à :</b> ${times}</div>
    <ul class="review-list small"><li>${esc(c.meal_evening)}</li><li>${esc(c.meal_morning)}</li><li>${esc(c.evening_before)}</li><li>${esc(c.carry)}.</li></ul>
  </div>`;
}

// ================================================================ RAVITAILLEMENT DANS UNE SÉANCE
async function fuelSection(box, s) {
  let F;
  try { F = await api(`/api/nutrition/log/${s.id}`); } catch { return; }
  const qty = {};
  (F.log.items || []).forEach((it) => { if (it.product_id) qty[it.product_id] = it.qty; });
  const render_ = () => {
    box.innerHTML = h`<div class="section"><h2>Ravitaillement</h2>
      ${F.products.map((p) => `<div class="fuel-item"><span style="flex:1;min-width:0"><b>${esc((p.brand ? p.brand + " " : "") + p.name)}</b> <span class="small muted">${p.carbs_g} g</span></span>
        <button class="btn sm" data-q="${p.id}" data-d="-1">−</button><b class="num" style="min-width:24px;text-align:center">${qty[p.id] || 0}</b><button class="btn sm" data-q="${p.id}" data-d="1">+</button></div>`).join("")}
      <div class="row" style="gap:10px;margin-top:10px"><label class="small muted" style="flex:1">Eau / boisson bue (ml)</label><input id="fu-water" type="number" step="50" style="width:110px" value="${F.log.water_ml || ""}"></div>
      ${F.analysis.carbs_per_h != null ? `<div class="fuel-res ${F.analysis.level}"><b class="num">${F.analysis.carbs_per_h} g/h</b> · ${F.analysis.water_per_h} ml/h<div class="small">${esc(F.analysis.verdict || "")} ${esc(F.analysis.water_verdict || "")}</div></div>` : ""}
      <div class="btns" style="margin-top:8px"><button class="btn sm primary" id="fu-save">Enregistrer le ravitaillement</button></div></div>`;
    $$("[data-q]", box).forEach((b) => (b.onclick = () => { qty[b.dataset.q] = Math.max(0, (qty[b.dataset.q] || 0) + Number(b.dataset.d)); const w = $("#fu-water", box).value; render_(); $("#fu-water", box).value = w; }));
    $("#fu-save", box).onclick = async () => {
      try {
        F = await api(`/api/nutrition/log/${s.id}`, { method: "POST", body: { items: Object.entries(qty).map(([product_id, q]) => ({ product_id, qty: q })), water_ml: Number($("#fu-water", box).value || 0) } });
        toast("Ravitaillement enregistré (stock mis à jour)"); render_();
      } catch (e) { toast(e.message, true); }
    };
  };
  render_();
}

// ================================================================ PRÉDICTION
function predictionShort(P) {
  if (!P || !P.estimate) return "";
  const col = P.gap_s <= 0 ? "var(--good)" : P.gap_s <= 120 ? "var(--warn)" : "var(--bad)";
  return h`<div class="card section" id="home-pred" style="cursor:pointer">
    <div class="row between"><h2 style="margin:0">Prédiction marathon</h2><span class="small muted">fourchette ${P.range[0]} – ${P.range[1]}</span></div>
    <div class="row" style="gap:14px;margin-top:8px;align-items:baseline"><div style="font-family:var(--font-display);font-size:34px;font-weight:900;letter-spacing:-.04em" class="num">${P.estimate}</div>
      <div class="small" style="color:${col};font-weight:700">${P.gap_s <= 0 ? "−" : "+"}${dur(Math.abs(P.gap_s))} vs objectif</div></div>
    <div class="small muted">${esc(P.verdict)}</div></div>`;
}

async function predictionSection(box) {
  let P;
  try { P = await api("/api/prediction"); } catch (e) { box.innerHTML = ""; return; }
  if (!P.estimate) { box.innerHTML = ""; return; }
  const col = P.gap_s <= 0 ? "var(--good)" : P.gap_s <= 120 ? "var(--warn)" : "var(--bad)";
  box.innerHTML = h`<div class="card section">
    <div class="row between wrap"><h2 style="margin:0">Prédiction marathon</h2><span class="small muted">mise à jour chaque jour</span></div>
    <div class="row wrap" style="gap:18px;margin:10px 0 4px;align-items:flex-end">
      <div><div style="font-family:var(--font-display);font-size:44px;font-weight:900;letter-spacing:-.045em;line-height:1" class="num">${P.estimate}</div><div class="small muted">${P.pace}/km · fourchette ${P.range[0]} – ${P.range[1]}</div></div>
      <div style="color:${col};font-weight:800">${P.gap_s <= 0 ? "−" : "+"}${dur(Math.abs(P.gap_s))} vs ${esc(state.race?.cfg?.goal || "objectif")}</div>
    </div>
    <p style="margin:8px 0 12px">${esc(P.verdict)}</p>
    ${P.methods.map((m) => `<div class="method"><div class="row between"><b>${esc(m.label)}</b><span class="num"><b>${m.time}</b> <span class="muted small">${m.pace}/km</span></span></div>
      <div class="bar" style="height:5px;margin:6px 0"><i style="width:${m.share}%"></i></div><div class="small muted">${esc(m.detail)} · poids ${m.share} %</div></div>`).join("")}
    ${P.history && P.history.length > 1 ? `<div class="chart-box" style="height:170px;margin-top:12px"><canvas id="c-pred"></canvas></div>` : ""}
    <div class="section"><h2>Ce qui fera bouger la prédiction</h2><ul class="review-list small">${P.levers.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>
  </div>`;
  if (P.history && P.history.length > 1 && typeof Chart !== "undefined") {
    chartDefaults();
    mkChart($("#c-pred", box), {
      type: "line",
      data: { labels: P.history.map((x) => shortD(x.date)), datasets: [
        { label: "Prédiction", data: P.history.map((x) => x.estimate_s), borderColor: css("--accent"), backgroundColor: css("--accent"), tension: 0.3, pointRadius: 2 },
        { label: "Objectif", data: P.history.map(() => P.goal_s), borderColor: css("--muted"), borderDash: [4, 3], pointRadius: 0 },
      ] },
      options: { scales: { y: { reverse: true, ticks: { callback: (v) => hms(v) } }, x: { grid: { display: false } } }, plugins: { tooltip: { callbacks: { label: (c) => hms(c.raw) } } } },
    });
  }
}

// ================================================================ CARTE DU PARCOURS
async function trackMap(box, aid) {
  if (typeof L === "undefined") return;
  let T;
  try { T = await api(`/api/activity/${aid}/track`); } catch { return; }
  const pts = (T.points || []).filter((p) => p[0] != null);
  if (pts.length < 2) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="section"><div class="row between wrap"><h2 style="margin:0">Parcours</h2>
    <div class="seg" id="map-mode"><button data-m="pace" class="on">Allure</button><button data-m="hr">FC</button></div></div>
    <div id="map" class="map"></div><div class="map-legend" id="map-legend"></div></div>`;
  const dark = currentTheme() === "dark";
  const map = L.map($("#map", box), { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
  L.tileLayer(`https://{s}.basemaps.cartocdn.com/${dark ? "dark_all" : "light_all"}/{z}/{x}/{y}{r}.png`, {
    maxZoom: 19, subdomains: "abcd", attribution: "© OpenStreetMap, © CARTO",
  }).addTo(map);
  const layer = L.layerGroup().addTo(map);
  map.fitBounds(L.latLngBounds(pts.map((p) => [p[0], p[1]])), { padding: [18, 18] });
  const ramp = ["#2563eb", "#06b6d4", "#22c55e", "#eab308", "#f97316", "#dc2626"];
  const draw = (mode) => {
    layer.clearLayers();
    const val = (p) => (mode === "hr" ? p[2] : p[3] ? 1000 / p[3] : null);
    const vals = pts.map(val).filter((v) => v != null && isFinite(v)).sort((a, b) => a - b);
    if (!vals.length) return;
    const q = (f) => vals[Math.min(vals.length - 1, Math.floor(f * vals.length))];
    const lo = q(0.05), hi = q(0.95);
    const color = (v) => {
      if (v == null) return "#888";
      let t = Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1)));
      if (mode === "pace") t = 1 - t; // allure : plus rapide = plus chaud
      return ramp[Math.min(ramp.length - 1, Math.floor(t * ramp.length))];
    };
    for (let i = 1; i < pts.length; i++) {
      L.polyline([[pts[i - 1][0], pts[i - 1][1]], [pts[i][0], pts[i][1]]], { color: color(val(pts[i])), weight: 4.5, opacity: 0.95, lineCap: "round" }).addTo(layer);
    }
    L.circleMarker([pts[0][0], pts[0][1]], { radius: 6, color: "#fff", weight: 2, fillColor: "#16a34a", fillOpacity: 1 }).addTo(layer);
    L.circleMarker([pts[pts.length - 1][0], pts[pts.length - 1][1]], { radius: 6, color: "#fff", weight: 2, fillColor: "#111", fillOpacity: 1 }).addTo(layer);
    const f = (v) => (mode === "hr" ? `${Math.round(v)} bpm` : `${pace(v)}/km`);
    $("#map-legend", box).innerHTML = `<span>${mode === "hr" ? f(lo) : f(hi)}</span><i style="background:linear-gradient(90deg,${ramp.join(",")})"></i><span>${mode === "hr" ? f(hi) : f(lo)}</span>`;
  };
  draw("pace");
  $$("#map-mode button", box).forEach((b) => (b.onclick = () => { $$("#map-mode button", box).forEach((x) => x.classList.toggle("on", x === b)); draw(b.dataset.m); }));
  setTimeout(() => map.invalidateSize(), 250);
}

// ================================================================ CALENDRIER MOIS
function monthCalendar(p) {
  const t = today();
  const ref = state.calMonth || t.slice(0, 7);
  const [y, m] = ref.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const days = new Date(y, m, 0).getDate();
  const byDate = {};
  p.sessions.forEach((s) => (byDate[s.date] ||= []).push(s));
  let cells = "";
  for (let i = 0; i < startOffset; i++) cells += `<div class="cal-cell empty"></div>`;
  let kmMonth = 0, doneMonth = 0;
  for (let d = 1; d <= days; d++) {
    const ds = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const ss = byDate[ds] || [];
    ss.forEach((s) => { kmMonth += s.planned_km || 0; doneMonth += s.done_km || 0; });
    cells += `<div class="cal-cell ${ds === t ? "today" : ""} ${ds < t ? "past" : ""}"><div class="cal-day">${d}</div>
      ${ss.map((s) => `<button class="cal-sess t-${s.type}" data-sid="${s.id}" title="${esc(s.title)}"><span class="cal-type">${s.type === "REPOS" ? "Repos" : s.type}</span>${s.planned_km ? `<span class="num">${km(s.planned_km, 0)}</span>` : ""}${s.status === "done" ? "<i>✓</i>" : s.status === "missed" ? "<i class='x'>✗</i>" : ""}</button>`).join("")}</div>`;
  }
  const label = new Date(y, m - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  return h`<div class="card cal">
    <div class="row between" style="margin-bottom:12px"><button class="icon-btn" data-cal="-1" aria-label="Mois précédent"><svg viewBox="0 0 24 24"><path d="m15 6-6 6 6 6"/></svg></button>
      <div style="text-align:center"><div style="font-family:var(--font-display);font-weight:800;font-size:18px;text-transform:capitalize">${label}</div><div class="small muted num">${km(doneMonth, 0)} / ${km(kmMonth, 0)} km</div></div>
      <button class="icon-btn" data-cal="1" aria-label="Mois suivant"><svg viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg></button></div>
    <div class="cal-grid">${["L", "M", "M", "J", "V", "S", "D"].map((x) => `<div class="cal-head">${x}</div>`).join("")}${cells}</div>
  </div>`;
}
function bindCalendar(view) {
  $$("[data-cal]", view).forEach((b) => (b.onclick = () => {
    const [y, m] = (state.calMonth || today().slice(0, 7)).split("-").map(Number);
    const d = new Date(y, m - 1 + Number(b.dataset.cal), 1);
    state.calMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    render();
  }));
  $$(".cal-sess", view).forEach((b) => (b.onclick = () => showSession(b.dataset.sid)));
}
