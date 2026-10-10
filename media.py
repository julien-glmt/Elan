"""Module « Vu & Lu » : séries, films, animés, mangas et livres.

Recherche dans des catalogues gratuits, sans compte ni clé :
- séries : TVmaze (api.tvmaze.com) — épisodes, durée, prochain épisode
- films : iTunes Search (itunes.apple.com) — affiche, année, durée
- animés & mangas : AniList (graphql.anilist.co) — épisodes / chapitres / tomes, prochain épisode
- livres : Google Books, avec Open Library en secours — pages, auteur, couverture
Tout est stocké localement dans data/media.json ; si un catalogue ne répond pas, on peut toujours ajouter à la main.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

TYPES = {"serie": "Série", "film": "Film", "anime": "Animé", "manga": "Manga", "livre": "Livre"}
UNITS = {"serie": "épisode", "film": "film", "anime": "épisode", "manga": "chapitre", "livre": "page"}
STATUSES = {"en_cours": "En cours", "a_voir": "À voir / à lire", "termine": "Terminé", "pause": "En pause", "abandonne": "Abandonné"}
# minutes par unité, si le catalogue ne le dit pas
DEFAULT_MIN = {"serie": 42, "film": 110, "anime": 24, "manga": 6, "livre": 1.5}
UA = {"User-Agent": "Elan/1.0 (app perso)", "Accept": "application/json"}


def _get(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: float = 8.0):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={**UA, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ------------------------------------------------------------------ catalogues
def search_tvmaze(q: str, kind: str = "serie") -> list[dict]:
    data = _get("https://api.tvmaze.com/search/shows?q=" + urllib.parse.quote(q))
    out = []
    for r in data[:10]:
        s = r.get("show") or {}
        if kind == "anime" and not (s.get("type") == "Animation" or "Anime" in (s.get("genres") or [])):
            continue
        img = (s.get("image") or {})
        out.append({"type": kind, "source": "tvmaze", "source_id": str(s.get("id")), "title": s.get("name"),
                    "year": (s.get("premiered") or "")[:4] or None, "cover": (img.get("medium") or img.get("original") or "").replace("http://", "https://") or None,
                    "genres": s.get("genres") or [], "runtime": s.get("averageRuntime") or s.get("runtime"),
                    "info": " · ".join(x for x in [(s.get("network") or s.get("webChannel") or {}).get("name"), {"Ended": "terminée", "Running": "en cours"}.get(s.get("status"), "")] if x),
                    "summary": _strip_html(s.get("summary"))[:300]})
    return out


def tvmaze_details(sid: str) -> dict:
    eps = _get(f"https://api.tvmaze.com/shows/{sid}/episodes")
    show = _get(f"https://api.tvmaze.com/shows/{sid}?embed=nextepisode")
    nxt = ((show.get("_embedded") or {}).get("nextepisode")) or None
    episodes = [[e.get("season"), e.get("number"), e.get("airdate")] for e in eps if e.get("number") is not None]
    rts = [e.get("runtime") for e in eps if e.get("runtime")]
    return {"total": len(episodes), "episodes": episodes, "runtime": round(sum(rts) / len(rts)) if rts else show.get("averageRuntime"),
            "next_episode": {"season": nxt.get("season"), "number": nxt.get("number"), "airdate": nxt.get("airdate"), "name": nxt.get("name")} if nxt else None,
            "airing": show.get("status") == "Running"}


def search_itunes(q: str) -> list[dict]:
    data = _get("https://itunes.apple.com/search?" + urllib.parse.urlencode({"term": q, "media": "movie", "entity": "movie", "country": "FR", "limit": 10}))
    out = []
    for r in data.get("results", []):
        if r.get("kind") not in (None, "feature-movie"):
            continue
        art = r.get("artworkUrl100") or ""
        out.append({"type": "film", "source": "itunes", "source_id": str(r.get("trackId")), "title": r.get("trackName"),
                    "year": (r.get("releaseDate") or "")[:4] or None, "cover": art.replace("100x100", "300x300") or None,
                    "genres": [r["primaryGenreName"]] if r.get("primaryGenreName") else [], "total": 1,
                    "runtime": round((r.get("trackTimeMillis") or 0) / 60000) or None, "info": r.get("artistName") or "",
                    "summary": (r.get("longDescription") or r.get("shortDescription") or "")[:300]})
    return out


def search_imdb(q: str) -> list[dict]:
    """Suggestions publiques d'IMDb (sans clé) : titres, années, affiches."""
    slug = urllib.parse.quote(q.lower().strip())
    data = _get(f"https://v3.sg.media-imdb.com/suggestion/x/{slug}.json")
    out = []
    for r in data.get("d", []):
        if r.get("qid") not in ("movie", "tvMovie", "short", "video"):
            continue
        img = (r.get("i") or {}).get("imageUrl")
        if img and "._V1_" in img:
            img = img.replace("._V1_", "._V1_UX300_")
        out.append({"type": "film", "source": "imdb", "source_id": r.get("id"), "title": r.get("l"), "year": str(r["y"]) if r.get("y") else None,
                    "cover": img, "genres": [], "total": 1, "runtime": None, "info": r.get("s") or ""})
    return out


def search_wikidata_films(q: str) -> list[dict]:
    data = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": q, "language": "fr", "uselang": "fr", "type": "item", "limit": 15, "format": "json"}))
    out = []
    for r in data.get("search", []):
        desc = (r.get("description") or "")
        if "film" not in desc.lower():
            continue
        y = re.search(r"\b(19|20)\d{2}\b", desc)
        out.append({"type": "film", "source": "wikidata", "source_id": r.get("id"), "title": r.get("label"), "year": y.group(0) if y else None,
                    "cover": None, "genres": [], "total": 1, "runtime": None, "info": desc[:80]})
    return out


def search_films(q: str) -> list[dict]:
    """iTunes (titres français, durée) puis IMDb (affiches) puis Wikidata, selon ce qui répond."""
    errors, seen, out = [], set(), []
    for fn in (search_itunes, search_imdb, search_wikidata_films):
        try:
            res = fn(q)
        except Exception as e:  # un catalogue en panne ne doit pas bloquer les autres
            errors.append(f"{fn.__name__}: {e}")
            continue
        for r in res:
            key = ((r.get("title") or "").lower(), r.get("year"))
            if key not in seen:
                seen.add(key)
                out.append(r)
        if len(out) >= 5:
            break
    if not out and len(errors) == 3:
        raise RuntimeError(" ; ".join(errors))
    return out[:12]

def search_anilist(q: str, kind: str) -> list[dict]:
    data = _post("https://graphql.anilist.co", {"query": ANILIST_Q, "variables": {"q": q, "t": "ANIME" if kind == "anime" else "MANGA"}})
    out = []
    for m in ((data.get("data") or {}).get("Page") or {}).get("media") or []:
        t = m.get("title") or {}
        out.append(_anilist_item(m, kind) | {"title": t.get("userPreferred") or t.get("romaji") or t.get("english"),
                                           "info": " · ".join(x for x in [m.get("format"), {"RELEASING": "en cours", "FINISHED": "terminé"}.get(m.get("status"), "")] if x),
                                           "summary": _strip_html(m.get("description"))[:300]})
    return out


def _anilist_item(m: dict, kind: str) -> dict:
    nxt = m.get("nextAiringEpisode")
    return {"type": kind, "source": "anilist", "source_id": str(m.get("id")), "year": str((m.get("startDate") or {}).get("year") or "") or None,
            "cover": (m.get("coverImage") or {}).get("large") or (m.get("coverImage") or {}).get("medium"), "genres": m.get("genres") or [],
            "total": m.get("episodes") if kind == "anime" else m.get("chapters"), "volumes": m.get("volumes"),
            "runtime": m.get("duration") if kind == "anime" else None, "airing": m.get("status") == "RELEASING",
            "next_episode": {"number": nxt["episode"], "airdate": datetime.fromtimestamp(nxt["airingAt"]).date().isoformat()} if nxt else None}


def anilist_details(sid: str, kind: str) -> dict:
    q = """query ($id: Int) { Media(id: $id) { id episodes chapters volumes duration status coverImage { large } startDate { year } genres nextAiringEpisode { episode airingAt } } }"""
    m = ((_post("https://graphql.anilist.co", {"query": q, "variables": {"id": int(sid)}}).get("data") or {}).get("Media")) or {}
    return _anilist_item(m, kind)


def search_books(q: str) -> list[dict]:
    out = []
    try:
        data = _get("https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode({"q": q, "maxResults": 12, "printType": "books"}))
        for it in data.get("items", []):
            v = it.get("volumeInfo") or {}
            img = (v.get("imageLinks") or {})
            out.append({"type": "livre", "source": "gbooks", "source_id": it.get("id"),
                        "title": v.get("title") + (f" — {v['subtitle']}" if v.get("subtitle") else ""),
                        "year": (v.get("publishedDate") or "")[:4] or None, "author": ", ".join(v.get("authors") or []),
                        "cover": (img.get("thumbnail") or img.get("smallThumbnail") or "").replace("http://", "https://") or None,
                        "genres": v.get("categories") or [], "total": v.get("pageCount") or None, "info": ", ".join(v.get("authors") or []),
                        "summary": (v.get("description") or "")[:300]})
    except Exception:
        pass
    if out:
        return out
    data = _get("https://openlibrary.org/search.json?" + urllib.parse.urlencode({"q": q, "limit": 12, "fields": "key,title,author_name,first_publish_year,number_of_pages_median,cover_i,subject"}))
    for d in data.get("docs", []):
        out.append({"type": "livre", "source": "openlibrary", "source_id": d.get("key"), "title": d.get("title"),
                    "year": str(d.get("first_publish_year") or "") or None, "author": ", ".join(d.get("author_name") or [])[:120],
                    "cover": f"https://covers.openlibrary.org/b/id/{d['cover_i']}-M.jpg" if d.get("cover_i") else None,
                    "genres": (d.get("subject") or [])[:3], "total": d.get("number_of_pages_median"), "info": ", ".join(d.get("author_name") or [])[:80]})
    return out


def search(kind: str, q: str) -> list[dict]:
    q = (q or "").strip()
    if len(q) < 2:
        return []
    if kind == "serie":
        return search_tvmaze(q)
    if kind == "film":
        return search_films(q)
    if kind == "anime":
        # TVmaze d'abord : une seule fiche par animé, toutes saisons réunies (AniList sépare chaque saison)
        out = []
        try:
            out = search_tvmaze(q, "anime")
            for r in out:
                r["info"] = " · ".join(x for x in [r.get("info"), "toutes saisons"] if x)
        except Exception:
            pass
        try:
            extra = search_anilist(q, kind)
        except Exception:
            if not out:
                raise
            extra = []
        for r in extra:
            r["info"] = " · ".join(x for x in [r.get("info"), "une saison"] if x)
        return out + extra[: max(3, 8 - len(out))]
    if kind == "manga":
        return search_anilist(q, kind)
    if kind == "livre":
        return search_books(q)
    return []


def details(item: dict) -> dict:
    """Infos complètes (nombre d'épisodes, prochain épisode…) pour un titre du catalogue."""
    try:
        if item.get("source") == "tvmaze":
            return tvmaze_details(item["source_id"])
        if item.get("source") == "anilist":
            return anilist_details(item["source_id"], item["type"])
    except Exception:
        return {}
    return {}


# ------------------------------------------------------------------ stockage
class MediaStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "media.json"
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except Exception:
            d = {}
        d.setdefault("items", [])
        d.setdefault("log", [])
        d.setdefault("refreshed", None)
        return d

    def save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False))
        tmp.replace(self.path)

    def add(self, body: dict) -> dict:
        kind = body.get("type") if body.get("type") in TYPES else "serie"
        it = {"id": uuid.uuid4().hex[:10], "type": kind, "title": str(body.get("title") or "Sans titre")[:200], "added": date.today().isoformat()}
        for k in ("year", "cover", "source", "source_id", "author", "info"):
            if body.get(k):
                it[k] = str(body[k])[:400]
        it["genres"] = [str(g)[:40] for g in (body.get("genres") or [])][:5]
        for k in ("total", "runtime", "volumes"):
            if body.get(k) not in (None, ""):
                try:
                    it[k] = int(float(body[k]))
                except (TypeError, ValueError):
                    pass
        if kind == "film":
            it["total"] = 1
        extra = details(it) if body.get("source") in ("tvmaze", "anilist") else {}
        for k in ("total", "episodes", "runtime", "next_episode", "airing", "volumes"):
            if extra.get(k) is not None:
                it[k] = extra[k]
        st = body.get("status") if body.get("status") in STATUSES else "en_cours"
        it["status"] = st
        it["progress"] = 0
        if st == "en_cours":
            it["started"] = date.today().isoformat()
        with self.lock:
            d = self.load()
            d["items"].append(it)
            self.save(d)
        if st == "termine":
            self.progress(it["id"], {"set": it.get("total") or 1})
            return self.get(it["id"])
        return it

    def get(self, iid: str) -> dict | None:
        return next((x for x in self.load()["items"] if x["id"] == iid), None)

    def update(self, iid: str, body: dict) -> dict:
        with self.lock:
            d = self.load()
            it = next((x for x in d["items"] if x["id"] == iid), None)
            if not it:
                raise KeyError(iid)
            if body.get("status") in STATUSES and body["status"] != it.get("status"):
                it["status"] = body["status"]
                if body["status"] == "en_cours" and not it.get("started"):
                    it["started"] = date.today().isoformat()
                if body["status"] == "termine":
                    it["finished"] = date.today().isoformat()
            for k in ("title", "notes", "author"):
                if k in body:
                    it[k] = str(body[k] or "")[:2000] or None
            if "rating" in body:
                r = body.get("rating")
                it["rating"] = max(0, min(10, float(r))) if r not in (None, "", 0, "0") else None
            for k in ("total", "runtime"):
                if body.get(k) not in (None, ""):
                    it[k] = int(float(body[k]))
            for k in ("started", "finished"):
                if k in body:
                    it[k] = body[k] or None
            self.save(d)
            return it

    def progress(self, iid: str, body: dict) -> dict:
        """+1 / −1 ou valeur exacte ; enregistre le temps passé dans le journal."""
        with self.lock:
            d = self.load()
            it = next((x for x in d["items"] if x["id"] == iid), None)
            if not it:
                raise KeyError(iid)
            old = it.get("progress") or 0
            if "set" in body:
                new = int(float(body["set"]))
            else:
                new = old + int(body.get("delta", 1))
            total = it.get("total")
            new = max(0, min(new, total) if total else new)
            delta = new - old
            it["progress"] = new
            if new > 0 and it.get("status") in ("a_voir", None):
                it["status"] = "en_cours"
                it.setdefault("started", date.today().isoformat())
            if total and new >= total and it.get("status") != "termine":
                if not (it.get("airing") and it["type"] in ("serie", "anime", "manga")):
                    it["status"] = "termine"
                    it["finished"] = date.today().isoformat()
            it["last"] = datetime.now().isoformat(timespec="minutes")
            if delta and not body.get("nolog"):
                per = it.get("runtime") or DEFAULT_MIN[it["type"]]
                d["log"].append({"date": date.today().isoformat(), "item": iid, "type": it["type"], "delta": delta, "minutes": round(delta * per, 1)})
            self.save(d)
            return it

    def delete(self, iid: str) -> None:
        with self.lock:
            d = self.load()
            d["items"] = [x for x in d["items"] if x["id"] != iid]
            d["log"] = [x for x in d["log"] if x["item"] != iid]
            self.save(d)

    def refresh_airing(self, force: bool = False) -> int:
        """Met à jour épisodes et prochains épisodes des séries / animés suivis (au plus toutes les 12 h)."""
        d = self.load()
        if not force and d.get("refreshed") and (datetime.now() - datetime.fromisoformat(d["refreshed"])).total_seconds() < 12 * 3600:
            return 0
        n = 0
        todo = [x for x in d["items"] if x.get("source") in ("tvmaze", "anilist") and x.get("status") in ("en_cours", "pause", "a_voir")
                and x["type"] in ("serie", "anime", "manga")]
        updates = {}
        for it in todo:
            ex = details(it)
            if ex:
                updates[it["id"]] = ex
        with self.lock:
            d = self.load()
            for it in d["items"]:
                ex = updates.get(it["id"])
                if not ex:
                    continue
                for k in ("total", "episodes", "next_episode", "airing", "runtime", "volumes"):
                    if k in ex and ex[k] is not None:
                        it[k] = ex[k]
                if "next_episode" in ex and ex["next_episode"] is None:
                    it["next_episode"] = None
                n += 1
            d["refreshed"] = datetime.now().isoformat(timespec="seconds")
            self.save(d)
        return n


# ------------------------------------------------------------------ affichage
def ep_label(it: dict, n: int | None = None) -> str | None:
    """« S2 · E5 » pour une série (d'après la liste des épisodes), sinon « ép. 5 »."""
    n = it.get("progress", 0) if n is None else n
    if it["type"] in ("serie", "anime") and it.get("episodes"):
        if n <= 0:
            return "pas commencée"
        idx = min(n, len(it["episodes"])) - 1
        s, e = it["episodes"][idx][:2]
        return f"S{s} · E{e}"
    unit = {"anime": "ép.", "manga": "ch.", "livre": "p.", "serie": "ép."}.get(it["type"])
    return f"{unit} {n}" if unit else None


def next_label(it: dict) -> str | None:
    if it["type"] in ("serie", "anime") and it.get("episodes"):
        n = it.get("progress", 0)
        if n < len(it["episodes"]):
            s, e = it["episodes"][n][:2]
            return f"S{s} · E{e}"
        return None
    return None


def summary(d: dict, today: date | None = None) -> dict:
    today = today or date.today()
    items = d["items"]
    by_id = {x["id"]: x for x in items}
    for it in items:
        it["label"] = ep_label(it)
        it["next_label"] = next_label(it)
        it["pct"] = round(min(100, (it.get("progress", 0) / it["total"]) * 100)) if it.get("total") else None
        it["unit"] = UNITS[it["type"]]
        # épisodes déjà sortis mais pas encore vus
        it["behind"] = None
        if it.get("status") == "en_cours":
            if it["type"] in ("serie", "anime") and it.get("episodes"):
                aired = sum(1 for e in it["episodes"] if len(e) < 3 or not e[2] or e[2] <= today.isoformat())
                it["behind"] = max(0, aired - it.get("progress", 0))
            elif it["type"] == "anime" and it.get("next_episode"):
                it["behind"] = max(0, it["next_episode"]["number"] - 1 - it.get("progress", 0))
    month = today.isoformat()[:7]
    year = today.isoformat()[:4]
    mins = defaultdict(float)
    counts = defaultdict(int)
    monthly = defaultdict(lambda: defaultdict(float))
    for l in d["log"]:
        monthly[l["date"][:7]][l["type"]] += l["minutes"] / 60
        if l["date"][:7] == month:
            mins[l["type"]] += l["minutes"]
            counts[l["type"]] += l["delta"]
    fin_month = [x for x in items if (x.get("finished") or "")[:7] == month and x.get("status") == "termine"]
    fin_year = [x for x in items if (x.get("finished") or "")[:4] == year and x.get("status") == "termine"]
    months = []
    y, m = today.year, today.month
    for k in range(11, -1, -1):
        mm = m - k
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        key = f"{yy}-{mm:02d}"
        months.append({"month": key, **{t: round(monthly[key].get(t, 0), 1) for t in TYPES}})
    genres = defaultdict(int)
    for x in items:
        if x.get("status") in ("en_cours", "termine"):
            for g in x.get("genres") or []:
                genres[g] += 1
    upcoming = sorted([{"id": x["id"], "title": x["title"], "cover": x.get("cover"), "type": x["type"], **x["next_episode"]}
                       for x in items if x.get("next_episode") and x.get("status") in ("en_cours", "pause", "a_voir") and x["next_episode"].get("airdate")
                       and x["next_episode"]["airdate"] >= (today - timedelta(days=1)).isoformat()], key=lambda u: u["airdate"])[:10]
    recent = []
    for l in reversed(d["log"][-60:]):
        it = by_id.get(l["item"])
        if it:
            recent.append({"date": l["date"], "title": it["title"], "type": it["type"], "delta": l["delta"], "cover": it.get("cover")})
    current = sorted([x for x in items if x.get("status") == "en_cours"], key=lambda x: x.get("last") or x.get("added") or "", reverse=True)
    return {
        "items": items, "types": TYPES, "statuses": STATUSES, "current": [x["id"] for x in current], "upcoming": upcoming,
        "month": {"hours": round(sum(mins.values()) / 60, 1), "by_type": {t: round(v / 60, 1) for t, v in mins.items()},
                  "episodes": counts.get("serie", 0) + counts.get("anime", 0), "chapters": counts.get("manga", 0), "pages": counts.get("livre", 0),
                  "films": sum(1 for x in fin_month if x["type"] == "film"), "finished": len(fin_month)},
        "year": {"finished": len(fin_year), "by_type": {t: sum(1 for x in fin_year if x["type"] == t) for t in TYPES},
                 "hours": round(sum(l["minutes"] for l in d["log"] if l["date"][:4] == year) / 60, 1),
                 "top": sorted([x for x in items if x.get("rating") and (x.get("finished") or (x.get("added") or ""))[:4] == year], key=lambda x: -x["rating"])[:8]},
        "monthly": months, "genres": sorted(genres.items(), key=lambda g: -g[1])[:8], "recent": recent[:20],
        "counts": {s: sum(1 for x in items if x.get("status") == s) for s in STATUSES},
    }


def demo_search(kind: str, q: str) -> list[dict]:
    """Résultats fictifs pour le mode démo (sans Internet)."""
    base = {"serie": [("Dark", 26, 55), ("Severance", 19, 50), ("The Bear", 38, 30)], "film": [("Dune : deuxième partie", 1, 166), ("Inception", 1, 148)],
            "anime": [("Frieren", 28, 24), ("One Piece", 1100, 24)], "manga": [("Vagabond", 327, None), ("One Piece", 1130, None)],
            "livre": [("Dune", 896, None), ("L'Étranger", 184, None)]}[kind]
    return [{"type": kind, "source": "demo", "source_id": f"{kind}-{i}", "title": f"{n}" if q.lower() in n.lower() or i == 0 else n, "year": "2020",
             "cover": None, "genres": ["Drame"], "total": tot, "runtime": rt, "info": "démo"} for i, (n, tot, rt) in enumerate(base)]
