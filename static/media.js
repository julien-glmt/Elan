/* Élan – module « Vu & Lu » : séries, films, animés, mangas, livres */
"use strict";

const MT = { serie: "Série", film: "Film", anime: "Animé", manga: "Manga", livre: "Livre" };
const MT_PL = { serie: "Séries", film: "Films", anime: "Animés", manga: "Mangas", livre: "Livres" };
const MT_COL = { serie: "#ec4899", film: "#f97316", anime: "#8b5cf6", manga: "#0ea5e9", livre: "#10b981" };
const MS = { en_cours: "En cours", a_voir: "À voir / à lire", termine: "Terminé", pause: "En pause", abandonne: "Abandonné" };
const PLUS = { serie: "+1 épisode", anime: "+1 épisode", manga: "+1 chapitre", livre: "Page…", film: "Vu" };

async function mediaData() { state.media = await api("/api/media"); return state.media; }
const mItem = (id) => (state.media?.items || []).find((x) => x.id === id);

function cover(it, size = "m") {
  const ini = (it.title || "?").replace(/[^\p{L}\p{N}\s]/gu, " ").trim().split(/\s+/).filter((w, i, a) => w.length > 1 || a.length === 1).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase() || "?";
  return it.cover ? `<img class="mcov ${size}" src="${esc(it.cover)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=&quot;mcov ${size} ph&quot; style=&quot;--c:${MT_COL[it.type]}&quot;>${esc(ini)}</div>'">`
    : `<div class="mcov ${size} ph" style="--c:${MT_COL[it.type]}">${esc(ini)}</div>`;
}
function mediaHead() {
  return `<div class="m-top"><div class="m-types">${Object.entries(MT_PL).map(([k, l]) => `<span class="m-type" style="--c:${MT_COL[k]}">${l}</span>`).join("")}</div><button class="btn primary m-addbtn" id="m-add">+ Ajouter</button></div>`;
}
function bindMediaHead(view) { const b = $("#m-add", view); if (b) b.onclick = () => addMedia(); }

// ================================================================ EN COURS
async function renderMediaHome(view) {
  const S = await mediaData();
  const cur = S.current.map(mItem).filter(Boolean);
  const todo = S.items.filter((x) => x.status === "a_voir").slice(-10).reverse();
  const M = S.month;
  if (!S.items.length) {
    view.innerHTML = h`${mediaHead()}<div class="card m-empty"><div class="m-empty-ico">▶</div><h2 style="font-size:22px;margin:6px 0">Tout ce que tu regardes et lis, au même endroit</h2>
      <p class="muted">Séries, films, animés, mangas, livres : tape le titre, l'app trouve l'affiche et le nombre d'épisodes ou de pages. Ensuite, un bouton « +1 » suffit.</p>
      <div class="btns" style="justify-content:center"><button class="btn primary" id="m-first">Ajouter mon premier titre</button></div></div>`;
    bindMediaHead(view);
    $("#m-first", view).onclick = () => addMedia();
    return;
  }
  view.innerHTML = h`${mediaHead()}
    <div class="m-strip-k">Ce mois-ci <span>(sans compter ce que tu avais déjà vu ou lu avant d'ajouter un titre)</span></div>
    <div class="m-strip">
      <div><b class="num">${km(M.hours, 1)} h</b><span>de visionnage et lecture</span></div>
      <div><b class="num">${M.episodes}</b><span>épisodes vus</span></div>
      <div><b class="num">${M.chapters}</b><span>chapitres lus</span></div>
      <div><b class="num">${M.pages}</b><span>pages lues</span></div>
      <div><b class="num">${M.films}</b><span>films vus</span></div>
      <div><b class="num">${M.finished}</b><span>titres terminés</span></div>
    </div>
    <div class="section"><h2>Reprendre</h2>
      ${cur.length ? `<div class="m-resume">${cur.map(resumeCard).join("")}</div>` : `<div class="card empty small">Rien en cours. Passe un titre « à voir » en cours, ou ajoute-en un.</div>`}</div>
    <div class="cols section"><div>
      ${S.upcoming.length ? `<div class="card"><h2>Bientôt</h2>${S.upcoming.map((u) => `<div class="m-up" data-mid="${u.id}">${cover(u, "xs")}<div style="flex:1;min-width:0"><div class="ellipsis"><b>${esc(u.title)}</b></div><div class="small muted">${u.season ? `S${u.season} · ` : ""}épisode ${u.number}${u.name ? ` · ${esc(u.name)}` : ""}</div></div><span class="m-date">${relDay(u.airdate)}</span></div>`).join("")}</div>` : ""}
      <div class="card ${S.upcoming.length ? "section" : ""}"><div class="row between"><h2 style="margin:0">À voir, à lire</h2><a href="#" class="small" id="m-lib">Bibliothèque →</a></div>
        ${todo.length ? `<div class="m-shelf">${todo.map((x) => `<button class="m-poster" data-mid="${x.id}">${cover(x)}<span class="ellipsis">${esc(x.title)}</span></button>`).join("")}</div>` : `<p class="small muted">Ta liste d'envies est vide.</p>`}</div>
    </div><div>
      <div class="card"><h2>Récemment</h2>${S.recent.length ? S.recent.slice(0, 10).map((r) => `<div class="m-rec"><span class="m-dot" style="background:${MT_COL[r.type]}"></span><span class="ellipsis" style="flex:1"><b>${esc(r.title)}</b></span><span class="small muted">${r.delta > 0 ? "+" : ""}${r.delta} · ${relDay(r.date)}</span></div>`).join("") : `<p class="small muted">Ton activité apparaîtra ici.</p>`}</div>
    </div></div>`;
  bindMediaHead(view);
  $("#m-lib", view).onclick = (e) => { e.preventDefault(); setView("m-lib"); };
  bindResume(view);
  $$("[data-mid]", view).forEach((el) => { if (!el.closest(".m-card")) el.onclick = () => mediaDetail(el.dataset.mid); });
}

function relDay(d) {
  const diff = Math.round((parseD(d) - parseD(today())) / 864e5);
  if (diff === 0) return "aujourd'hui";
  if (diff === 1) return "demain";
  if (diff === -1) return "hier";
  if (diff > 1 && diff < 7) return `dans ${diff} j`;
  return fmtDay(d);
}

function resumeCard(x) {
  const total = x.total ? ` / ${x.total}` : "";
  const nxt = x.next_label ? `prochain : ${x.next_label}` : "";
  return h`<div class="m-card" style="--c:${MT_COL[x.type]}" data-mid="${x.id}">
    <div class="m-card-cov">${cover(x, "l")}</div>
    <div class="m-card-body">
      <div class="m-chip" style="--c:${MT_COL[x.type]}">${MT[x.type]}</div>
      <div class="m-title">${esc(x.title)}</div>
      <div class="small muted">${x.type === "livre" ? `page ${x.progress}${total}` : x.type === "manga" ? `chapitre ${x.progress}${total}` : `${esc(x.label || "")}${x.episodes?.length ? "" : total}`}${nxt ? ` · ${nxt}` : ""}</div>
      ${x.pct != null ? `<div class="m-bar"><i style="width:${x.pct}%"></i></div>` : ""}
      ${x.behind ? `<div class="m-behind">${x.behind} ${x.airing ? "à rattraper" : x.behind > 1 ? "restants" : "restant"}</div>` : x.next_episode?.airdate ? `<div class="small muted">prochain épisode ${relDay(x.next_episode.airdate)}</div>` : ""}
      <div class="m-actions"><button class="btn sm" data-dec="${x.id}" aria-label="Retirer un">−</button><button class="btn primary m-plus" data-inc="${x.id}">${PLUS[x.type]}</button></div>
    </div></div>`;
}
function bindResume(view) {
  $$("[data-inc]", view).forEach((b) => (b.onclick = async (e) => {
    e.stopPropagation();
    const x = mItem(b.dataset.inc);
    if (x.type === "livre") { pagePrompt(x); return; }
    try {
      const r = await api(`/api/media/${x.id}/progress`, { method: "POST", body: { delta: 1 } });
      b.closest(".m-card")?.classList.add("bump");
      toast(r.status === "termine" ? `Terminé : ${x.title}` : `${x.title} · ${r.type === "serie" ? "" : ""}${x.type === "film" ? "vu" : "+1"}`);
      setTimeout(render, 250);
    } catch (err) { toast(err.message, true); }
  }));
  $$("[data-dec]", view).forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); await api(`/api/media/${b.dataset.dec}/progress`, { method: "POST", body: { delta: -1 } }); render(); }));
  $$(".m-card", view).forEach((c) => (c.onclick = () => mediaDetail(c.dataset.mid)));
}
function pagePrompt(x) {
  openModal(h`<h3>${esc(x.title)}</h3><label class="f">Tu en es à quelle page ?${x.total ? ` (sur ${x.total})` : ""}<input id="pp-p" type="number" inputmode="numeric" value="${x.progress || ""}"></label>
    <div class="btns"><button class="btn primary" id="pp-ok">Enregistrer</button><button class="btn" id="pp-end">Je l'ai fini</button></div>`, (el) => {
    setTimeout(() => $("#pp-p", el).select(), 50);
    const go = async (v) => { await api(`/api/media/${x.id}/progress`, { method: "POST", body: { set: v } }); closeModal(); render(); };
    $("#pp-ok", el).onclick = () => go(Number($("#pp-p", el).value || 0));
    $("#pp-p", el).onkeydown = (e) => { if (e.key === "Enter") $("#pp-ok", el).click(); };
    $("#pp-end", el).onclick = async () => { if (x.total) await go(x.total); await api(`/api/media/${x.id}`, { method: "POST", body: { status: "termine" } }); closeModal(); render(); };
  });
}

// ================================================================ AJOUT
function addMedia() {
  let kind = state.mediaKind || "serie";
  openModal(h`<h3>Ajouter un titre</h3>
    <div class="seg m-kind" id="am-k" style="margin:10px 0 12px">${Object.entries(MT).map(([k, l]) => `<button data-k="${k}">${l}</button>`).join("")}</div>
    <input id="am-q" placeholder="Titre…" autocomplete="off">
    <div id="am-res" class="am-res"></div>
    <a href="#" class="small" id="am-man">Ajouter à la main</a>`, (el) => {
    const setK = (k) => { kind = k; state.mediaKind = k; $$("#am-k button", el).forEach((b) => b.classList.toggle("on", b.dataset.k === k)); run(); };
    let tm, seq = 0;
    const run = () => {
      clearTimeout(tm);
      const q = $("#am-q", el).value.trim();
      if (q.length < 2) { $("#am-res", el).innerHTML = ""; return; }
      $("#am-res", el).innerHTML = `<div class="small muted" style="padding:10px">Recherche…</div>`;
      tm = setTimeout(async () => {
        const my = ++seq;
        try {
          const R = await api(`/api/media/search?type=${kind}&q=${encodeURIComponent(q)}`);
          if (my !== seq) return;
          const res = R.results;
          $("#am-res", el).innerHTML = res.length ? res.map((r, i) => `<button class="am-row" data-i="${i}">${cover(r, "s")}<div style="flex:1;min-width:0;text-align:left"><b class="ellipsis" style="display:block">${esc(r.title)}</b>
            <span class="small muted">${[r.year, r.info, r.total && r.type !== "film" ? `${r.total} ${{ serie: "ép.", anime: "ép.", manga: "ch.", livre: "pages" }[r.type]}` : "", r.runtime && r.type === "film" ? `${r.runtime} min` : ""].filter(Boolean).map(esc).join(" · ")}</span></div></button>`).join("")
            : `<div class="small muted" style="padding:10px">Aucun résultat. Essaie un autre titre, ou ajoute-le à la main.</div>`;
          $$(".am-row", el).forEach((b) => (b.onclick = () => chooseStatus(el, res[Number(b.dataset.i)])));
        } catch (e) { if (my === seq) $("#am-res", el).innerHTML = `<div class="warn-line">${esc(e.message)}</div>`; }
      }, 380);
    };
    $$("#am-k button", el).forEach((b) => (b.onclick = () => setK(b.dataset.k)));
    $("#am-q", el).oninput = run;
    setK(kind);
    setTimeout(() => $("#am-q", el).focus(), 60);
    $("#am-man", el).onclick = (e) => { e.preventDefault(); chooseStatus(el, { type: kind, title: $("#am-q", el).value.trim(), manual: true }); };
  });
}
function chooseStatus(el, r) {
  const body = $("#modal-body");
  body.innerHTML = h`<div class="am-pick">${cover(r, "l")}<div><div class="m-chip" style="--c:${MT_COL[r.type]}">${MT[r.type]}</div><h3 style="margin:6px 0 4px">${r.manual ? "Ajout manuel" : esc(r.title)}</h3>
    <div class="small muted">${[r.year, r.info].filter(Boolean).map(esc).join(" · ")}</div></div></div>
    ${r.manual ? `<div class="grid g2" style="margin-top:12px"><label class="f">Titre<input id="cs-t" value="${esc(r.title || "")}"></label>
      <label class="f">${{ serie: "Nombre d'épisodes", anime: "Nombre d'épisodes", manga: "Nombre de chapitres", livre: "Nombre de pages", film: "Durée (min)" }[r.type]}<input id="cs-n" type="number"></label></div>` : ""}
    <p class="small" style="margin:14px 0 8px">Tu l'ajoutes comment ?</p>
    <div class="cs-btns"><button class="btn primary" data-st="en_cours">En cours</button><button class="btn" data-st="a_voir">${r.type === "livre" || r.type === "manga" ? "À lire" : "À voir"}</button><button class="btn" data-st="termine">Déjà ${r.type === "livre" || r.type === "manga" ? "lu" : "vu"}</button></div>`;
  $$("[data-st]", body).forEach((b) => (b.onclick = async () => {
    const payload = { ...r, status: b.dataset.st };
    if (r.manual) {
      payload.title = $("#cs-t", body).value.trim() || "Sans titre";
      const n = Number($("#cs-n", body).value || 0);
      if (r.type === "film") payload.runtime = n || null; else payload.total = n || null;
    }
    b.disabled = true; b.textContent = "Ajout…";
    try { await api("/api/media", { method: "POST", body: payload }); closeModal(); toast(`Ajouté : ${payload.title}`); render(); } catch (e) { toast(e.message, true); b.disabled = false; }
  }));
}

// ================================================================ FICHE
function mediaDetail(id) {
  const x = mItem(id);
  if (!x) return;
  let rating = x.rating ? Math.round(x.rating / 2) : 0;
  openModal(h`<div class="am-pick">${cover(x, "l")}<div style="min-width:0">
      <div class="m-chip" style="--c:${MT_COL[x.type]}">${MT[x.type]}</div>
      <h3 style="margin:6px 0 2px">${esc(x.title)}</h3>
      <div class="small muted">${[x.year, x.author || x.info, (x.genres || []).slice(0, 3).join(", ")].filter(Boolean).map(esc).join(" · ")}</div>
      <div class="stars" id="md-stars" style="margin-top:8px">${[1, 2, 3, 4, 5].map((n) => `<button data-n="${n}" class="${rating >= n ? "on" : ""}">★</button>`).join("")}</div></div></div>
    <div class="seg md-st" id="md-st" style="margin:14px 0 10px;flex-wrap:wrap">${Object.entries(MS).map(([k, l]) => `<button data-s="${k}" class="${x.status === k ? "on" : ""}">${l}</button>`).join("")}</div>
    ${(x.type === "serie" || x.type === "anime") && x.episodes?.length ? seasonPicker(x) : x.type !== "film" ? h`<div class="md-prog"><span class="small muted">${{ serie: "Épisodes vus", anime: "Épisodes vus", manga: "Chapitres lus", livre: "Page" }[x.type]}</span>
      <button class="btn sm" id="md-m">−</button><input id="md-p" type="number" value="${x.progress || 0}"><span class="small muted">/</span><input id="md-tot" type="number" value="${x.total || ""}" placeholder="total"><button class="btn sm" id="md-pl">+</button>
      ${x.type === "serie" && x.label ? `<span class="small"><b>${esc(x.label)}</b></span>` : ""}</div>` : ""}
    <div class="grid g2" style="margin-top:10px"><label class="f">Commencé le<input id="md-s" type="date" value="${x.started || ""}"></label><label class="f">Terminé le<input id="md-f" type="date" value="${x.finished || ""}"></label></div>
    <label class="f">Mon avis<textarea id="md-n" rows="3" placeholder="Ce que tu en as pensé…">${esc(x.notes || "")}</textarea></label>
    <div class="btns"><button class="btn primary" id="md-save">Enregistrer</button><button class="btn danger" id="md-del">Retirer</button></div>`, (el) => {
    let st = x.status;
    $$("#md-st button", el).forEach((b) => (b.onclick = () => { st = b.dataset.s; $$("#md-st button", el).forEach((y) => y.classList.toggle("on", y === b)); }));
    $$("#md-stars button", el).forEach((b) => (b.onclick = () => { const n = Number(b.dataset.n); rating = rating === n ? 0 : n; $$("#md-stars button", el).forEach((y) => y.classList.toggle("on", Number(y.dataset.n) <= rating)); }));
    const p = $("#md-p", el);
    const sync = bindSeasonPicker(el, x);
    if (p) {
      $("#md-m", el).onclick = () => { p.value = Math.max(0, Number(p.value) - 1); sync && sync(); };
      $("#md-pl", el).onclick = () => { p.value = Math.min(x.total || 1e9, Number(p.value) + 1); sync && sync(); };
    }
    $("#md-save", el).onclick = async () => {
      try {
        if ($("#md-tot", el) && $("#md-tot", el).value) await api(`/api/media/${x.id}`, { method: "POST", body: { total: $("#md-tot", el).value } });
        if (p && Number(p.value) !== (x.progress || 0)) await api(`/api/media/${x.id}/progress`, { method: "POST", body: { set: Number(p.value), nolog: true } });
        await api(`/api/media/${x.id}`, { method: "POST", body: { status: st, rating: rating ? rating * 2 : 0, notes: $("#md-n", el).value, started: $("#md-s", el).value || null, finished: $("#md-f", el).value || (st === "termine" ? today() : null) } });
        closeModal(); toast("Enregistré"); render();
      } catch (e) { toast(e.message, true); }
    };
    $("#md-del", el).onclick = async () => { if (!confirm(`Retirer « ${x.title} » ?`)) return; await api(`/api/media/${x.id}`, { method: "DELETE" }); closeModal(); render(); };
  });
}

// Séries : progression par saison (« vu jusqu'à S3 · E7 ») au lieu d'un numéro d'épisode global
function seasonPicker(x) {
  const seasons = [...new Set(x.episodes.map((e) => e[0]))];
  return h`<div class="md-prog"><span class="small muted">Vu jusqu'à</span>
      <button class="btn sm" id="md-m" aria-label="Épisode précédent">−</button>
      <select id="md-ss">${seasons.map((n) => `<option value="${n}">Saison ${n}</option>`).join("")}</select>
      <select id="md-se"></select>
      <button class="btn sm" id="md-pl" aria-label="Épisode suivant">+</button>
      <input id="md-p" type="hidden" value="${x.progress || 0}"></div>
    <div class="md-seasons" id="md-sea"></div>`;
}
function bindSeasonPicker(el, x) {
  const ss = $("#md-ss", el), se = $("#md-se", el), p = $("#md-p", el), box = $("#md-sea", el);
  if (!ss) return null;
  const eps = x.episodes;
  const idxOf = (s, e) => eps.findIndex((v) => v[0] === s && v[1] === e);
  const fillEps = (s) => {
    const list = eps.filter((v) => v[0] === s);
    se.innerHTML = `<option value="0">aucun épisode</option>` + list.map((v) => `<option value="${v[1]}">Épisode ${v[1]}</option>`).join("");
  };
  const sync = () => {
    const n = Number(p.value) || 0;
    const cur = n > 0 ? eps[Math.min(n, eps.length) - 1] : eps[0];
    ss.value = String(cur[0]); fillEps(cur[0]); se.value = n > 0 ? String(cur[1]) : "0";
    const bySeason = {};
    eps.forEach((v, i) => { const b = (bySeason[v[0]] ||= { n: 0, seen: 0, last: i }); b.n++; b.last = i; if (i < n) b.seen++; });
    box.innerHTML = Object.entries(bySeason).map(([sn, b]) => `<button class="md-sea ${b.seen === b.n ? "done" : b.seen ? "part" : ""}" data-s="${sn}" title="Vu jusqu'à la fin de la saison ${sn}">
      <b>S${sn}</b><span>${b.seen === b.n ? "✓" : `${b.seen}/${b.n}`}</span><i style="width:${Math.round((b.seen / b.n) * 100)}%"></i></button>`).join("");
    $$(".md-sea", box).forEach((btn) => (btn.onclick = () => {
      const b = bySeason[btn.dataset.s];
      p.value = Number(p.value) === b.last + 1 ? b.last + 1 - b.n : b.last + 1; // vu jusqu'à la fin de cette saison ; re-cliquer annule
      sync();
    }));
  };
  ss.onchange = () => { const s = Number(ss.value); const first = idxOf(s, eps.find((v) => v[0] === s)[1]); p.value = first + 1; sync(); };
  se.onchange = () => { const s = Number(ss.value), e = Number(se.value); p.value = e ? idxOf(s, e) + 1 : idxOf(s, eps.find((v) => v[0] === s)[1]); sync(); };
  sync();
  return sync;
}

// ================================================================ BIBLIOTHÈQUE
async function renderMediaLib(view) {
  const S = await mediaData();
  const f = state.mediaLib || { type: "", status: "", q: "" };
  let items = S.items.slice().sort((a, b) => (b.last || b.added || "").localeCompare(a.last || a.added || ""));
  if (f.type) items = items.filter((x) => x.type === f.type);
  if (f.status) items = items.filter((x) => x.status === f.status);
  if (f.q) items = items.filter((x) => x.title.toLowerCase().includes(f.q.toLowerCase()));
  view.innerHTML = h`${mediaHead()}
    <div class="card">
      <div class="m-filters"><div class="seg" id="ml-t"><button data-t="" class="${!f.type ? "on" : ""}">Tout</button>${Object.entries(MT_PL).map(([k, l]) => `<button data-t="${k}" class="${f.type === k ? "on" : ""}">${l}</button>`).join("")}</div>
        <select id="ml-s"><option value="">Tous les statuts</option>${Object.entries(MS).map(([k, l]) => `<option value="${k}" ${f.status === k ? "selected" : ""}>${l} (${S.counts[k] || 0})</option>`).join("")}</select>
        <input id="ml-q" placeholder="Chercher dans ma bibliothèque…" value="${esc(f.q)}"></div>
      ${items.length ? `<div class="m-grid">${items.map((x) => h`<button class="m-gitem" data-mid="${x.id}">${cover(x)}
        ${x.pct != null && x.status === "en_cours" ? `<div class="m-bar sm"><i style="width:${x.pct}%;background:${MT_COL[x.type]}"></i></div>` : `<div class="m-bar sm" style="visibility:hidden"></div>`}
        <span class="m-gt ellipsis">${esc(x.title)}</span><span class="m-gs"><i style="background:${MT_COL[x.type]}"></i>${MS[x.status]}${x.rating ? ` · ${"★".repeat(Math.round(x.rating / 2))}` : ""}</span></button>`).join("")}</div>`
        : `<div class="empty">Rien ici${f.type || f.status || f.q ? " avec ces filtres" : ""}.</div>`}
    </div>`;
  bindMediaHead(view);
  const set = (k, v) => { state.mediaLib = { ...f, [k]: v }; render(); };
  $$("#ml-t button", view).forEach((b) => (b.onclick = () => set("type", b.dataset.t)));
  $("#ml-s", view).onchange = (e) => set("status", e.target.value);
  let tq; $("#ml-q", view).oninput = (e) => { clearTimeout(tq); tq = setTimeout(() => set("q", e.target.value), 350); };
  if (f.q) { const q = $("#ml-q", view); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  $$("[data-mid]", view).forEach((el) => (el.onclick = () => mediaDetail(el.dataset.mid)));
}

// ================================================================ BILAN
async function renderMediaStats(view) {
  const S = await mediaData();
  const Y = S.year;
  view.innerHTML = h`${mediaHead()}
    <div class="grid g4">
      ${tile(`Terminés en ${new Date().getFullYear()}`, Y.finished, Object.entries(Y.by_type).filter(([, n]) => n).map(([t, n]) => `${n} ${MT_PL[t].toLowerCase()}`).join(" · ") || "—", "#ec4899")}
      ${tile("Heures cette année", km(Y.hours, 0), "temps estimé", "#8b5cf6", "h")}
      ${tile("Ce mois-ci", km(S.month.hours, 1), `${S.month.episodes} épisodes · ${S.month.pages} pages`, null, "h")}
      ${tile("En cours", S.counts.en_cours || 0, `${S.counts.a_voir || 0} dans la liste d'envies`)}
    </div>
    <div class="cols section"><div>
      <div class="card"><h2>Temps passé par mois</h2><div class="chart-box" style="height:240px"><canvas id="c-m-month"></canvas></div>
        <p class="small muted" style="margin:6px 0 0">Estimé d'après la durée des épisodes et des films, environ 6 min par chapitre et 1 min 30 par page.</p></div>
    </div><div>
      <div class="card"><h2>Tes genres</h2>${S.genres.length ? `<div class="chart-box" style="height:220px"><canvas id="c-m-gen"></canvas></div>` : `<p class="small muted">—</p>`}</div>
    </div></div>
    <div class="card section"><h2>Ton top de l'année</h2>${Y.top.length ? `<div class="m-shelf">${Y.top.map((x) => `<button class="m-poster" data-mid="${x.id}">${cover(x)}<span class="ellipsis">${esc(x.title)}</span><em>${"★".repeat(Math.round(x.rating / 2))}</em></button>`).join("")}</div>`
      : `<p class="small muted">Note tes titres (étoiles dans leur fiche) pour construire ton top.</p>`}</div>`;
  bindMediaHead(view);
  $$("[data-mid]", view).forEach((el) => (el.onclick = () => mediaDetail(el.dataset.mid)));
  if (typeof Chart === "undefined") return;
  chartDefaults();
  mkChart($("#c-m-month", view), { type: "bar", data: { labels: S.monthly.map((m) => MONTHS[Number(m.month.slice(5)) - 1]),
    datasets: Object.keys(MT).map((t) => ({ label: MT_PL[t], data: S.monthly.map((m) => m[t]), backgroundColor: MT_COL[t], stack: "h", borderRadius: 3 })) },
    options: { plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${km(c.raw, 1)} h` } } }, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true } } } });
  if (S.genres.length) mkChart($("#c-m-gen", view), { type: "doughnut", data: { labels: S.genres.map((g) => g[0]), datasets: [{ data: S.genres.map((g) => g[1]), backgroundColor: ["#ec4899", "#8b5cf6", "#0ea5e9", "#10b981", "#f59e0b", "#f97316", "#6366f1", "#14b8a6"], borderWidth: 0 }] },
    options: { cutout: "60%", plugins: { legend: { position: "right", labels: { boxWidth: 10 } } } } });
}
