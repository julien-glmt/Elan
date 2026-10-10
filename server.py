"""Élan – coach perso : running (prépa, séances Garmin) + nutrition (calories, poids).

Lancement : python server.py   (ou double-clic sur « Lancer Sub3.command »)
"""
from __future__ import annotations

import copy
import json
import logging
import os
import secrets
import socket
import threading
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import coach
import coach_ai
import race as RACE
import sleep as SLEEP
import nutrition as NUTRI
import prediction as PRED
import debrief as DEBRIEF
import planner as PLANNER
import body as BODY
import finance as FIN
import media as MEDIA
import backup as BACKUP
import carbload as CARB
import report as REPORT
import hashlib
import workouts as W
from garmin_service import GarminService

ROOT = Path(__file__).parent
DEMO = os.environ.get("SUB3_DEMO") == "1"
DATA = Path(os.environ.get("SUB3_DATA", ROOT / ("data_demo" if DEMO else "data")))
DATA.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("SUB3_PORT", "8742"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sub3")

# ---------------------------------------------------------------- config / PIN
CONFIG_PATH = DATA / "config.json"
config = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
if not config.get("pin"):
    config["pin"] = f"{secrets.randbelow(10**6):06d}"
config.setdefault("auto_push", True)       # envoie tout seul la séance du lendemain sur la montre
config.setdefault("auto_push_hour", 18)
config.setdefault("sleep_goal_h", 7.5)
CONFIG_PATH.write_text(json.dumps(config, indent=1))

# ---------------------------------------------------------------- plan
PLAN_PATH = DATA / "plan.json"
plan_lock = threading.Lock()


def load_plan() -> dict:
    if not PLAN_PATH.exists():
        PLAN_PATH.write_text((ROOT / "plan_initial.json").read_text())
    return json.loads(PLAN_PATH.read_text())


def save_plan(plan: dict) -> None:
    plan["sessions"].sort(key=lambda s: (s["date"], s["id"]))
    tmp = PLAN_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    tmp.replace(PLAN_PATH)


REVIEWS_PATH = DATA / "reviews.json"
reviews_lock = threading.Lock()


def load_reviews() -> dict:
    try:
        return json.loads(REVIEWS_PATH.read_text())
    except Exception:
        return {}


def save_review(sid: str, key: str, review: dict) -> None:
    with reviews_lock:
        r = load_reviews()
        r[sid] = {"key": key, "review": review, "at": datetime.now().isoformat(timespec="minutes")}
        REVIEWS_PATH.write_text(json.dumps(r, ensure_ascii=False))


# ---------------------------------------------------------------- Garmin
if DEMO:
    from demo_service import DemoService
    garmin: GarminService = DemoService(DATA / "demo")
else:
    garmin = GarminService(DATA)

app = FastAPI(title="Élan")
coach_store = coach_ai.CoachStore(DATA)
nutri = NUTRI.NutritionStore(DATA)


def _coach_loop():
    import time as _t
    if not DEMO:
        garmin.try_resume()
    while True:
        try:
            coach_store.ingest()
            _auto_activate()
            if not DEMO:
                try:
                    mediastore.refresh_airing()
                except Exception as e:
                    log.warning("Vu & Lu : mise à jour des épisodes impossible (%s)", e)
            try:
                _backup_tick()
            except Exception as e:
                log.warning("sauvegarde impossible (%s)", e)
            if garmin.connected:
                auto_push()
                refresh_context()
        except Exception as e:
            log.warning("contexte coach: %s", e)
        _t.sleep(5 * 60)


@app.on_event("startup")
def _startup():
    threading.Thread(target=_coach_loop, daemon=True).start()


@app.middleware("http")
async def pin_guard(request: Request, call_next):
    path = request.url.path
    host = request.client.host if request.client else ""
    local = host in ("127.0.0.1", "::1", "localhost", "testclient")
    if path.startswith("/api/") and path != "/api/ping" and not local:
        pin = request.headers.get("x-pin") or request.cookies.get("sub3_pin")
        if pin != config["pin"]:
            return JSONResponse({"detail": "PIN requis", "pin_required": True}, status_code=401)
    try:
        resp = await call_next(request)
        if path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-cache"  # le navigateur revalide : jamais de vieux CSS/JS après une mise à jour
        return resp
    except PermissionError as e:
        return JSONResponse({"detail": str(e), "garmin_disconnected": True}, status_code=409)


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------- helpers
def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def session_km(s: dict, paces: dict) -> float:
    if s.get("distance_km"):
        return float(s["distance_km"])
    return round(W.estimate(s.get("steps", []), paces)["meters"] / 1000, 1)


def enrich_plan(plan: dict, acts: list[dict]) -> dict:
    today = date.today().isoformat()
    by_id = {str(a["id"]): a for a in acts}
    linked = {str(i) for s in plan["sessions"] for i in (s.get("activity_ids") or [])}
    by_day = defaultdict(list)
    for a in acts:
        if a.get("is_run") and str(a["id"]) not in linked:
            by_day[a["date"]].append(a)
    reviews = load_reviews()
    paces = plan["paces"]
    weeks: dict[str, dict] = {}
    for s in plan["sessions"]:
        est = W.estimate(s.get("steps", []), paces)
        s["planned_km"] = session_km(s, paces)
        s["planned_s"] = est["seconds"]
        s["summary"] = W.describe(s.get("steps", []), paces)
        if s.get("activity_ids") is not None:
            done = [by_id[str(i)] for i in s["activity_ids"] if str(i) in by_id]
        else:
            done = by_day.get(s["date"], [])
        s["linked"] = s.get("activity_ids") is not None
        rv = reviews.get(s["id"])
        if rv and done and rv.get("key", "").split("|")[0] == ",".join(sorted(str(a["id"]) for a in done)):
            s["review_score"] = rv["review"].get("score")
            s["review_color"] = rv["review"].get("color")
        s["done_km"] = round(sum(a["distance_km"] for a in done), 1)
        s["activities"] = [{"id": a["id"], "name": a["name"], "km": a["distance_km"], "pace_s": a["pace_s"], "avg_hr": a["avg_hr"],
                            "start": a["start"], "date": a["date"], "duration_s": a.get("duration_s")} for a in sorted(done, key=lambda a: a["start"] or "")]
        if s["type"] in ("REPOS", "RENFO"):
            s["status"] = "extra" if done else "rest"
        elif s["date"] > today:
            s["status"] = "upcoming"
        elif s["done_km"] >= 0.8 * s["planned_km"]:
            s["status"] = "done"
        elif s["done_km"] > 0:
            s["status"] = "partial"
        else:
            s["status"] = "today" if s["date"] == today else "missed"
        wk = monday(date.fromisoformat(s["date"])).isoformat()
        w = weeks.setdefault(wk, {"start": wk, "planned_km": 0.0, "sessions": []})
        w["planned_km"] += s["planned_km"]
        w["sessions"].append(s)
    for wk, w in weeks.items():
        end = (date.fromisoformat(wk) + timedelta(days=6)).isoformat()
        w["end"] = end
        w["done_km"] = round(sum(a["distance_km"] for a in acts if a.get("is_run") and wk <= a["date"] <= end), 1)
        w["planned_km"] = round(w["planned_km"], 1)
        w["current"] = wk <= today <= end
    plan["weeks"] = sorted(weeks.values(), key=lambda w: w["start"])
    return plan


# ---------------------------------------------------------------- API : statut & auth
@app.get("/api/ping")
def ping():
    return {"ok": True}


@app.get("/api/status")
def status():
    return {"connected": garmin.connected, "demo": DEMO, "name": garmin.name, "mfa_pending": garmin.pending is not None,
            "lan_url": f"http://{lan_ip()}:{PORT}", "pin": config["pin"], "error": garmin.last_error}


@app.post("/api/auth/login")
async def auth_login(body: dict):
    try:
        r = await run_in_threadpool(garmin.login, body.get("email", "").strip(), body.get("password", ""))
        return {"status": r}
    except Exception as e:
        raise HTTPException(400, f"Connexion Garmin refusée : {e}")


@app.post("/api/auth/mfa")
async def auth_mfa(body: dict):
    try:
        return {"status": await run_in_threadpool(garmin.submit_mfa, body.get("code", ""))}
    except Exception as e:
        raise HTTPException(400, f"Code refusé : {e}")


@app.post("/api/auth/logout")
def auth_logout():
    garmin.logout()
    return {"ok": True}


# ---------------------------------------------------------------- API : données
@app.get("/api/dashboard")
async def dashboard():
    plan = load_plan()
    acts = await run_in_threadpool(garmin.activities, 120)
    today_data = await run_in_threadpool(garmin.today)
    plan = enrich_plan(plan, acts)
    t = date.today().isoformat()
    week = next((w for w in plan["weeks"] if w["current"]), None)
    nxt = [s for s in plan["sessions"] if s["date"] >= t and s["type"] != "REPOS"][:3]
    race_d = date.fromisoformat(plan["race"]["date"])
    runs_7 = [a for a in acts if a["is_run"] and a["date"] > (date.today() - timedelta(days=7)).isoformat()]
    trends_ = await run_in_threadpool(garmin.trends, 28)
    today_main = next((s for s in plan["sessions"] if s["date"] == t and s["type"] not in ("REPOS",)), None) \
        or next((s for s in plan["sessions"] if s["date"] == t), None)
    light = coach.morning_light(today_data, trends_, today_main, plan, config['sleep_goal_h'])
    last_done = next((s for s in reversed(plan["sessions"]) if s["date"] <= t and s.get("activities") and s.get("steps")), None)
    last_review = None
    if last_done:
        try:
            last_review = {"session": last_done, "review": await _review(last_done, plan)}
        except Exception as e:  # le bilan ne doit jamais casser l'accueil
            log.warning("bilan impossible: %s", e)
    _warm_reviews_async(plan)
    cnotes = coach_store.notes()
    coach_today = {
        "morning": next((n for n in reversed(cnotes) if n["type"] == "morning" and n["date"] == t), None),
        "latest": next((n for n in reversed(cnotes) if n["type"] in ("session", "weekly", "answer")), None),
        "unread": sum(1 for n in cnotes if not n.get("read")),
    }
    try:
        sleep_info = SLEEP.insights(trends_, plan["sessions"], load_reviews(), config["sleep_goal_h"])
        sleep_info.pop("series", None)
        sleep_info.pop("detail", None)
    except Exception as e:
        log.warning("sommeil: %s", e)
        sleep_info = None
    try:
        nb = nutrition_bundle(plan)
        prep = prep_cards(plan, nb["favorite"])
        nut_short = {"gel_stock": nb["gel_stock"], "gels_missing": nb["gels_missing"], "gels_needed": nb["gels_needed"]}
    except Exception as e:
        log.warning("nutrition accueil: %s", e)
        prep, nut_short = [], None
    try:
        pr = await run_in_threadpool(compute_prediction, plan, acts)
        pred_short = {k: pr.get(k) for k in ("estimate", "range", "pace", "gap_s", "verdict")}
    except Exception as e:
        log.warning("prédiction accueil: %s", e)
        pred_short = None
    debrief_todo = None
    try:
        store = debriefs.load()
        for s in plan["sessions"]:
            if s["type"] == "COURSE" and s.get("activities") and s["date"] >= (date.today() - timedelta(days=30)).isoformat():
                aid = str(s["activities"][0]["id"])
                if not (store.get(aid) or {}).get("feedback"):
                    debrief_todo = {"aid": aid, "sid": s["id"], "name": s["title"], "date": s["date"]}
    except Exception as e:
        log.warning("bilan à faire: %s", e)
    return {
        "debrief_todo": debrief_todo, "next_draft": NEXT_PATH.exists(),
        "prep": prep, "nutrition": nut_short, "prediction": pred_short,
        "sleep": sleep_info,
        "coach": coach_today,
        "light": light, "last_review": last_review,
        "race": plan["race"], "days_to_race": (race_d - date.today()).days,
        "goal_pace_s": round(_goal_pace(plan["race"])),
        "today_sessions": [s for s in plan["sessions"] if s["date"] == t],
        "next_sessions": nxt, "week": week, "garmin": today_data,
        "last7": {"km": round(sum(a["distance_km"] for a in runs_7), 1), "runs": len(runs_7),
                  "load": sum(a["training_load"] or 0 for a in runs_7)},
        "last_activity": next((a for a in acts if a["is_run"]), None),
        "paces": plan["paces"],
    }


def _goal_pace(race: dict) -> float:
    h, m, s = (list(map(int, race["goal"].split(":"))) + [0, 0])[:3]
    return (h * 3600 + m * 60 + s) / float(race.get("distance_km", 42.195))


@app.get("/api/activities")
async def activities(days: int = 60, refresh: bool = False):
    return await run_in_threadpool(garmin.activities, days, refresh)


@app.get("/api/activity/{aid}")
async def activity(aid: str):
    return await run_in_threadpool(garmin.activity_detail, aid)


@app.get("/api/trends")
async def trends(days: int = 28):
    days = max(7, min(days, 90))
    return await run_in_threadpool(garmin.trends, days)


def compute_weekly(acts: list[dict], plan: dict, weeks: int = 16) -> list[dict]:
    plan = enrich_plan(plan, acts)
    planned = {w["start"]: w["planned_km"] for w in plan["weeks"]}
    start = monday(date.today()) - timedelta(weeks=weeks - 1)
    end = max([date.fromisoformat(w) for w in planned] + [monday(date.today())])
    out = []
    d = start
    while d <= end:
        e = d + timedelta(days=6)
        runs = [a for a in acts if a["is_run"] and d.isoformat() <= a["date"] <= e.isoformat()]
        km = sum(a["distance_km"] for a in runs)
        out.append({"start": d.isoformat(), "km": round(km, 1), "planned_km": planned.get(d.isoformat()),
                    "runs": len(runs), "load": sum(a["training_load"] or 0 for a in runs),
                    "long_km": round(max([a["distance_km"] for a in runs] or [0]), 1),
                    "future": d > date.today()})
        d += timedelta(days=7)
    return out


@app.get("/api/weekly")
async def weekly(weeks: int = 16):
    acts = await run_in_threadpool(garmin.activities, weeks * 7 + 7)
    return compute_weekly(acts, load_plan(), weeks)


# ---------------------------------------------------------------- API : plan
@app.get("/api/plan")
async def get_plan():
    acts = await run_in_threadpool(garmin.activities, 120)
    return enrich_plan(load_plan(), acts)


CLEAN_KEYS = {"planned_km", "planned_s", "summary", "done_km", "activities", "status", "linked", "review_score", "review_color"}


def _clean(s: dict) -> dict:
    return {k: v for k, v in s.items() if k not in CLEAN_KEYS}


@app.post("/api/plan/session")
def create_session(body: dict):
    with plan_lock:
        plan = load_plan()
        s = _clean(body)
        s["id"] = "u" + uuid.uuid4().hex[:8]
        s.setdefault("steps", [])
        s.setdefault("type", "EF")
        plan["sessions"].append(s)
        save_plan(plan)
    return s


@app.put("/api/plan/session/{sid}")
def update_session(sid: str, body: dict):
    with plan_lock:
        plan = load_plan()
        for i, s in enumerate(plan["sessions"]):
            if s["id"] == sid:
                new = {**s, **_clean(body), "id": sid}
                if new.get("steps") != s.get("steps") or new.get("date") != s.get("date") or new.get("title") != s.get("title"):
                    new["garmin_dirty"] = bool(s.get("garmin_workout_id"))
                plan["sessions"][i] = new
                save_plan(plan)
                return new
    raise HTTPException(404, "Séance introuvable")


@app.delete("/api/plan/session/{sid}")
async def delete_session(sid: str):
    with plan_lock:
        plan = load_plan()
        s = next((x for x in plan["sessions"] if x["id"] == sid), None)
        if not s:
            raise HTTPException(404)
        plan["sessions"].remove(s)
        save_plan(plan)
    if s.get("garmin_workout_id") and garmin.connected:
        await run_in_threadpool(garmin.delete_workout, s["garmin_workout_id"])
    return {"ok": True}


@app.put("/api/plan/settings")
def update_settings(body: dict):
    with plan_lock:
        plan = load_plan()
        if "race" in body:
            plan["race"].update(body["race"])
        if "paces" in body:
            for k, v in body["paces"].items():
                if isinstance(v, list) and len(v) == 2 and all(W.pace_to_sec(x) for x in v):
                    plan["paces"][k] = v
        save_plan(plan)
    return {"race": plan["race"], "paces": plan["paces"]}


@app.post("/api/plan/reset")
def reset_plan():
    with plan_lock:
        if PLAN_PATH.exists():
            PLAN_PATH.rename(DATA / f"plan_backup_{datetime.now():%Y%m%d_%H%M%S}.json")
        load_plan()
    return {"ok": True}


def _workout_name(s: dict) -> str:
    d = date.fromisoformat(s["date"])
    return f"{d:%d/%m} {s['title']}"


async def _push_session(s: dict, plan: dict) -> dict:
    if not s.get("steps"):
        raise HTTPException(400, "Cette séance n'a pas d'étapes à envoyer")
    wj = W.to_garmin(_workout_name(s), s["steps"], plan["paces"], s.get("description", ""))
    res = await run_in_threadpool(garmin.push_workout, wj, s["date"], s.get("garmin_workout_id"))
    return res


@app.post("/api/plan/session/{sid}/push")
async def push_session(sid: str):
    plan = load_plan()
    s = next((x for x in plan["sessions"] if x["id"] == sid), None)
    if not s:
        raise HTTPException(404)
    res = await _push_session(s, plan)
    with plan_lock:
        plan = load_plan()
        for x in plan["sessions"]:
            if x["id"] == sid:
                x["garmin_workout_id"] = res["workout_id"]
                x["garmin_schedule_id"] = res["schedule_id"]
                x["garmin_pushed_at"] = datetime.now().isoformat(timespec="minutes")
                x["garmin_dirty"] = False
        save_plan(plan)
    return res


@app.post("/api/plan/week/{start}/push")
async def push_week(start: str):
    plan = load_plan()
    end = (date.fromisoformat(start) + timedelta(days=6)).isoformat()
    t = date.today().isoformat()
    todo = [s for s in plan["sessions"] if start <= s["date"] <= end and s["date"] >= t and s.get("steps") and s["type"] != "REPOS"]
    results = []
    for s in todo:
        try:
            results.append({"id": s["id"], **(await push_session(s["id"]))})
        except HTTPException as e:
            results.append({"id": s["id"], "error": e.detail})
    return results


@app.delete("/api/plan/session/{sid}/garmin")
async def unpush_session(sid: str):
    with plan_lock:
        plan = load_plan()
        s = next((x for x in plan["sessions"] if x["id"] == sid), None)
        if not s:
            raise HTTPException(404)
        wid = s.pop("garmin_workout_id", None)
        s.pop("garmin_schedule_id", None)
        s.pop("garmin_pushed_at", None)
        save_plan(plan)
    if wid:
        await run_in_threadpool(garmin.delete_workout, wid)
    return {"ok": True}


# ---------------------------------------------------------------- API : bilan, ressenti, association, ajustements
def _review_key(s: dict, plan: dict) -> str:
    ids = ",".join(sorted(str(a["id"]) for a in s.get("activities", [])))
    h = hashlib.md5(json.dumps([s.get("steps"), plan["paces"], plan.get("hr_zones"), coach.VERSION], sort_keys=True).encode()).hexdigest()[:10]
    return f"{ids}|{h}"


async def _review(s: dict, plan: dict) -> dict:
    """s doit être enrichi (enrich_plan) : s['activities'] contient les sorties associées."""
    key = _review_key(s, plan)
    cached = load_reviews().get(s["id"])
    if cached and cached.get("key") == key:
        return cached["review"]
    acts = sorted(s.get("activities", []), key=lambda a: str(a.get("start") or a["id"]))
    details = [await run_in_threadpool(garmin.activity_detail, str(a["id"])) for a in acts]
    rv = coach.review_session(s, plan, details)
    if s.get("activities"):
        save_review(s["id"], key, rv)
    return rv


_warming = threading.Event()


def _warm_reviews_async(plan: dict) -> None:
    """Calcule en tâche de fond les bilans des 21 derniers jours (pour les badges du plan)."""
    if _warming.is_set():
        return
    _warming.set()
    since = (date.today() - timedelta(days=21)).isoformat()
    todo = [s for s in plan["sessions"] if s["date"] >= since and s.get("activities") and s.get("steps")]

    def run():
        import asyncio
        try:
            for s in todo:
                try:
                    asyncio.run(_review(s, plan))
                except Exception as e:
                    log.debug("warm review %s: %s", s["id"], e)
        finally:
            _warming.clear()
    threading.Thread(target=run, daemon=True).start()


async def _enriched_session(sid: str) -> tuple[dict, dict]:
    acts = await run_in_threadpool(garmin.activities, 120)
    plan = enrich_plan(load_plan(), acts)
    s = next((x for x in plan["sessions"] if x["id"] == sid), None)
    if not s:
        raise HTTPException(404, "Séance introuvable")
    return s, plan


@app.get("/api/plan/session/{sid}/review")
async def session_review(sid: str):
    s, plan = await _enriched_session(sid)
    return await _review(s, plan)


@app.post("/api/plan/session/{sid}/feedback")
def session_feedback(sid: str, body: dict):
    with plan_lock:
        plan = load_plan()
        for s in plan["sessions"]:
            if s["id"] == sid:
                rpe = body.get("rpe")
                s["feedback"] = {"rpe": int(rpe) if rpe not in (None, "") else None, "note": (body.get("note") or "")[:1000],
                                 "at": datetime.now().isoformat(timespec="minutes")}
                save_plan(plan)
                return s["feedback"]
    raise HTTPException(404)


@app.get("/api/plan/session/{sid}/candidates")
async def session_candidates(sid: str):
    s, plan = await _enriched_session(sid)
    acts = await run_in_threadpool(garmin.activities, 120)
    d0 = date.fromisoformat(s["date"])
    lo, hi = (d0 - timedelta(days=3)).isoformat(), (d0 + timedelta(days=3)).isoformat()
    owner = {}
    for x in plan["sessions"]:
        for a in x.get("activities", []):
            owner[str(a["id"])] = x
    out = []
    for a in acts:
        if a["is_run"] and lo <= a["date"] <= hi:
            o = owner.get(str(a["id"]))
            out.append({**a, "current_session": {"id": o["id"], "title": o["title"], "date": o["date"]} if o else None,
                        "selected": o is not None and o["id"] == sid})
    return sorted(out, key=lambda a: a["start"] or "")


@app.post("/api/plan/session/{sid}/link")
def session_link(sid: str, body: dict):
    ids = body.get("activity_ids")
    with plan_lock:
        plan = load_plan()
        target = next((x for x in plan["sessions"] if x["id"] == sid), None)
        if not target:
            raise HTTPException(404)
        if ids is None:
            target.pop("activity_ids", None)       # retour à l'association automatique par date
        else:
            ids = [str(i) for i in ids]
            for x in plan["sessions"]:             # une sortie n'appartient qu'à une séance
                if x["id"] != sid and x.get("activity_ids"):
                    x["activity_ids"] = [i for i in x["activity_ids"] if str(i) not in ids]
            target["activity_ids"] = ids
        save_plan(plan)
    return {"ok": True}


@app.post("/api/plan/session/{sid}/adjust")
async def session_adjust(sid: str, body: dict):
    action = body.get("action")
    if action not in ("lighten", "shorten", "easy", "rest", "swap_next", "undo"):
        raise HTTPException(400, "Action inconnue")
    changed: list[dict] = []
    with plan_lock:
        plan = load_plan()
        s = next((x for x in plan["sessions"] if x["id"] == sid), None)
        if not s:
            raise HTTPException(404)
        if action == "swap_next" or (action == "undo" and s.get("swapped_with")):
            other_id = s.get("swapped_with")
            if action == "swap_next":
                nxt = sorted([x for x in plan["sessions"] if x["date"] > s["date"] and x["type"] != "COURSE"], key=lambda x: x["date"])
                if not nxt or (date.fromisoformat(nxt[0]["date"]) - date.fromisoformat(s["date"])).days > 3:
                    raise HTTPException(400, "Pas de séance dans les 3 jours suivants avec laquelle échanger")
                other = nxt[0]
                for x in (s, other):
                    x.setdefault("original", {k: copy.deepcopy(x.get(k)) for k in ("type", "title", "steps", "description", "date")})
                s["swapped_with"], other["swapped_with"] = other["id"], s["id"]
                s["adjusted_reason"] = other["adjusted_reason"] = "swap_next"
            else:
                other = next((x for x in plan["sessions"] if x["id"] == other_id), None)
                for x in [s] + ([other] if other else []):
                    x.pop("swapped_with", None)
                    x.pop("original", None)
                    x["adjusted_reason"] = None
            if other:
                s["date"], other["date"] = other["date"], s["date"]
                changed = [s, other]
            else:
                changed = [s]
        else:
            if action == "undo" and s.get("original"):
                orig_date = s["original"].get("date")
                new = coach.adjust(s, "undo", plan["paces"])
                if orig_date:
                    new["date"] = orig_date
            else:
                new = coach.adjust(s, action, plan["paces"])
            plan["sessions"][plan["sessions"].index(s)] = new
            changed = [new]
        for x in changed:
            if x.get("garmin_workout_id"):
                x["garmin_dirty"] = True
        save_plan(plan)
    # Mise à jour de la montre si les séances y étaient déjà
    synced = []
    for x in changed:
        if not x.get("garmin_workout_id") or not garmin.connected:
            continue
        try:
            if x["type"] == "REPOS" or not x.get("steps"):
                await unpush_session(x["id"])
            else:
                await push_session(x["id"])
            synced.append(x["id"])
        except Exception as e:
            log.warning("resync Garmin %s: %s", x["id"], e)
    return {"ok": True, "changed": [x["id"] for x in changed], "garmin_synced": synced}


# ---------------------------------------------------------------- API : jour J
RACE_PATH = DATA / "race.json"


def load_race_cfg() -> dict:
    try:
        return json.loads(RACE_PATH.read_text())
    except Exception:
        return {}


def save_race_cfg(cfg: dict) -> None:
    RACE_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))


def _favorite_gel() -> dict | None:
    try:
        prods = [dict(x, **NUTRI.tier_of(x)) for x in nutri.load()["products"] if x.get("kind") == "gel"]
    except Exception:
        return None
    ranked = sorted([x for x in prods if x.get("tier")], key=lambda x: (NUTRI.TIERS.index(x["tier"]), -(x.get("score") or 0)))
    return ranked[0] if ranked else None


def _race_bundle() -> dict:
    plan = load_plan()
    raw = load_race_cfg()
    cfg = RACE.merged(raw, plan["race"], plan.get("athlete"))
    fav = _favorite_gel()
    if fav and "gel_carbs" not in raw:  # par défaut, le plan de course utilise ton gel préféré
        cfg["gel_carbs"] = fav.get("carbs_g") or cfg["gel_carbs"]
        cfg["gel_name"] = f"{fav.get('brand', '')} {fav.get('name', '')}".strip()
    pace = RACE.pacing(cfg)
    nut = RACE.nutrition(cfg, pace)
    return {"plan": plan, "cfg": cfg, "pace": pace, "nut": nut}


@app.get("/api/race")
async def get_race():
    b = _race_bundle()
    garmin_pred = None
    try:
        t = await run_in_threadpool(garmin.today)
        garmin_pred = (t.get("predictions") or {}).get("marathon")
    except Exception:
        pass
    cfg = {k: v for k, v in b["cfg"].items() if k != "checklist"}
    race_session = next((s for s in b["plan"]["sessions"] if s["date"] == cfg["date"] and s["type"] == "COURSE"), None)
    last_week = [s for s in b["plan"]["sessions"]
                 if (date.fromisoformat(cfg["date"]) - timedelta(days=7)).isoformat() <= s["date"] <= cfg["date"]]
    return {"cfg": cfg, "pace": b["pace"], "nutrition": b["nut"], "predictions": RACE.predictions(b["cfg"], garmin_pred),
            "checklist": RACE.checklist(b["cfg"]), "strategies": RACE.STRATEGIES,
            "race_session": {"id": race_session["id"], "garmin_workout_id": race_session.get("garmin_workout_id"),
                             "garmin_dirty": race_session.get("garmin_dirty")} if race_session else None,
            "last_week": [{"date": s["date"], "type": s["type"], "title": s["title"], "description": s.get("description", "")} for s in last_week]}


RACE_KEYS = {"start_time", "city", "strategy", "temp_c", "ref_half", "weight_kg", "gel_carbs", "carbs_per_hour",
             "first_gel_min", "caffeine_from_km", "ravitos"}


@app.put("/api/race")
def put_race(body: dict):
    cfg = load_race_cfg()
    for k in RACE_KEYS & set(body):
        cfg[k] = body[k]
    if body.get("goal"):
        RACE.hms_to_s(body["goal"])  # valide le format
    with plan_lock:
        plan = load_plan()
        for k in ("name", "date", "goal", "distance_km"):
            if body.get(k):
                plan["race"][k] = body[k]
        save_plan(plan)
    save_race_cfg(cfg)
    return {"ok": True}


@app.post("/api/race/gpx")
async def race_gpx(request: Request):
    text = (await request.body()).decode("utf-8", errors="ignore")
    plan = load_plan()
    try:
        g = RACE.parse_gpx(text, float(plan["race"].get("distance_km", 42.195)))
    except Exception as e:
        raise HTTPException(400, f"GPX illisible : {e}")
    cfg = load_race_cfg()
    cfg.update(profile=g["profile"], course_start=g["start"], gpx_km=g["gpx_km"], gpx_gain=g["gain"], gpx_loss=g["loss"])
    save_race_cfg(cfg)
    return {"ok": True, "gain": g["gain"], "loss": g["loss"], "gpx_km": g["gpx_km"]}


@app.delete("/api/race/gpx")
def race_gpx_delete():
    cfg = load_race_cfg()
    for k in ("profile", "course_start", "gpx_km", "gpx_gain", "gpx_loss"):
        cfg.pop(k, None)
    save_race_cfg(cfg)
    return {"ok": True}


@app.put("/api/race/checklist")
def race_checklist(body: dict):
    cfg = load_race_cfg()
    cl = cfg.setdefault("checklist", {})
    for k, v in body.items():
        cl[str(k)] = bool(v)
    save_race_cfg(cfg)
    return {"ok": True}


@app.get("/api/race/weather")
async def race_weather():
    """Prévision Open-Meteo (gratuite, sans clé) à l'heure du départ — disponible ~16 jours avant."""
    import urllib.parse
    import urllib.request
    b = _race_bundle()
    cfg = b["cfg"]
    lat = lon = None
    if cfg.get("course_start"):
        lat, lon = cfg["course_start"]["lat"], cfg["course_start"]["lon"]
    elif cfg.get("city"):
        q = urllib.parse.urlencode({"name": cfg["city"], "count": 1, "language": "fr"})
        def geo():
            with urllib.request.urlopen(f"https://geocoding-api.open-meteo.com/v1/search?{q}", timeout=10) as r:
                return json.loads(r.read())
        try:
            res = (await run_in_threadpool(geo)).get("results") or []
        except Exception as e:
            raise HTTPException(502, f"Géocodage impossible : {e}")
        if not res:
            raise HTTPException(404, f"Ville introuvable : {cfg['city']}")
        lat, lon = res[0]["latitude"], res[0]["longitude"]
    else:
        raise HTTPException(400, "Renseigne la ville de la course (ou importe le GPX)")
    days = (date.fromisoformat(cfg["date"]) - date.today()).days
    if days > 15:
        return {"available": False, "days": days, "message": f"Prévision disponible à partir de J-15 (dans {days - 15} jours)."}
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation_probability,dew_point_2m",
                                "start_date": cfg["date"], "end_date": cfg["date"], "timezone": "auto"})
    def fc():
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=10) as r:
            return json.loads(r.read())
    try:
        data = await run_in_threadpool(fc)
    except Exception as e:
        raise HTTPException(502, f"Météo indisponible : {e}")
    h = data.get("hourly", {})
    start_h = int(cfg.get("start_time", "09:00")[:2])
    hours = []
    for i, t in enumerate(h.get("time", [])):
        hh = int(t[11:13])
        if start_h - 1 <= hh <= start_h + 3:
            hours.append({"time": t[11:16], "temp": h["temperature_2m"][i], "humidity": h["relative_humidity_2m"][i],
                          "wind": h["wind_speed_10m"][i], "rain": h["precipitation_probability"][i], "dew": h["dew_point_2m"][i]})
    avg = round(sum(x["temp"] for x in hours[1:5]) / max(1, len(hours[1:5])), 1) if hours else None
    return {"available": True, "hours": hours, "race_avg_temp": avg}


@app.post("/api/race/push")
async def race_push():
    b = _race_bundle()
    steps = RACE.race_steps(b["pace"], b["nut"])
    cfg = b["cfg"]
    with plan_lock:
        plan = load_plan()
        s = next((x for x in plan["sessions"] if x["date"] == cfg["date"] and x["type"] == "COURSE"), None)
        if not s:
            s = {"id": "u" + uuid.uuid4().hex[:8], "date": cfg["date"], "type": "COURSE", "title": cfg["name"], "description": ""}
            plan["sessions"].append(s)
        s["steps"] = steps
        s["description"] = f"Objectif {b['pace']['target']} · {b['pace']['strategy_label']} · gels : " + \
            ", ".join(f"km {g['km']:g}" + (" (caféine)" if g["caffeine"] else "") for g in b["nut"]["gels"])
        if s.get("garmin_workout_id"):
            s["garmin_dirty"] = True
        save_plan(plan)
        sid = s["id"]
    if not garmin.connected:
        return {"ok": True, "pushed": False, "session_id": sid}
    res = await push_session(sid)
    return {"ok": True, "pushed": True, "session_id": sid, **res}


# ---------------------------------------------------------------- sommeil, réglages, envoi automatique
AUTOPUSH_LOG = DATA / "autopush.json"


def _autopush_log() -> list:
    try:
        return json.loads(AUTOPUSH_LOG.read_text())
    except Exception:
        return []


def auto_push() -> list[dict]:
    """À partir de auto_push_hour, envoie sur la montre la séance du lendemain (et celle du jour si oubliée)."""
    if not config.get("auto_push") or not garmin.connected:
        return []
    import asyncio
    now = datetime.now()
    days = [date.today()]
    if now.hour >= int(config.get("auto_push_hour", 18)):
        days.append(date.today() + timedelta(days=1))
    acts = garmin.activities(30)
    plan = enrich_plan(load_plan(), acts)
    done = []
    for d in days:
        for s in plan["sessions"]:
            if s["date"] != d.isoformat() or not s.get("steps") or s["type"] in ("REPOS", "RENFO"):
                continue
            if s.get("activities") or (s.get("garmin_workout_id") and not s.get("garmin_dirty")):
                continue
            try:
                asyncio.run(push_session(s["id"]))
                done.append({"at": now.isoformat(timespec="minutes"), "session_id": s["id"], "date": s["date"], "title": s["title"], "ok": True})
            except Exception as e:
                done.append({"at": now.isoformat(timespec="minutes"), "session_id": s["id"], "date": s["date"], "title": s["title"], "ok": False, "error": str(e)[:200]})
    if done:
        log.info("envoi automatique : %s", done)
        AUTOPUSH_LOG.write_text(json.dumps((_autopush_log() + done)[-50:], ensure_ascii=False, indent=1))
    return done


@app.get("/api/settings")
def get_settings():
    return {k: config.get(k) for k in ("auto_push", "auto_push_hour", "sleep_goal_h")} | {"autopush_log": _autopush_log()[-10:]}


@app.put("/api/settings")
def put_settings(body: dict):
    if "auto_push" in body:
        config["auto_push"] = bool(body["auto_push"])
    if body.get("auto_push_hour") is not None:
        config["auto_push_hour"] = max(0, min(23, int(body["auto_push_hour"])))
    if body.get("sleep_goal_h"):
        config["sleep_goal_h"] = max(5.0, min(10.0, float(body["sleep_goal_h"])))
    CONFIG_PATH.write_text(json.dumps(config, indent=1))
    return get_settings()


@app.get("/api/sleep")
async def sleep_api():
    acts = await run_in_threadpool(garmin.activities, 60)
    plan = enrich_plan(load_plan(), acts)
    trends_ = await run_in_threadpool(garmin.trends, 42)
    return SLEEP.insights(trends_, plan["sessions"], load_reviews(), config["sleep_goal_h"])


# ---------------------------------------------------------------- nutrition, préparation, prédiction, tracé
def _session_duration(s: dict) -> float | None:
    d = sum(a.get("duration_s") or 0 for a in s.get("activities", []))
    return d or None


def nutrition_bundle(plan: dict) -> dict:
    b = _race_bundle()
    summ = nutri.summary(plan["sessions"], b["nut"]["gel_count"])
    prods = {p["id"]: p for p in summ["products"]}
    analyses = {}
    for s in plan["sessions"]:
        lg = summ["logs"].get(s["id"])
        if lg:
            analyses[s["id"]] = {"date": s["date"], "title": s["title"], **NUTRI.analyse_log(lg, _session_duration(s), prods)}
    summ["analyses"] = dict(sorted(analyses.items(), key=lambda kv: kv[1]["date"], reverse=True))
    return summ


def prep_cards(plan: dict, favorite: dict | None) -> list[dict]:
    t = date.today()
    out = []
    for d in (t, t + timedelta(days=1)):
        for s in plan["sessions"]:
            if s["date"] == d.isoformat() and not s.get("activities") and s.get("type") not in ("REPOS", "RENFO", "COURSE"):
                c = NUTRI.prep_card(s, favorite)
                if c:
                    c["when"] = "aujourd'hui" if d == t else "demain"
                    out.append(c)
    return out


def _safe_km(s: dict, paces: dict) -> float:
    try:
        return session_km(s, paces)
    except Exception:
        return 0.0


def compute_prediction(plan: dict, acts: list[dict]) -> dict:
    b = _race_bundle()
    garmin_pred = None
    try:
        dist = float(plan["race"].get("distance_km") or 42.195)
        key = next((v for k, v in GARMIN_PRED_KEY.items() if abs(k - dist) < 0.5), "marathon")
        garmin_pred = (garmin.today().get("predictions") or {}).get(key)
    except Exception:
        pass
    paces = plan.get("paces") or {}
    sess = [dict(s, planned_km=s.get("planned_km") if s.get("planned_km") is not None else _safe_km(s, paces)) for s in plan["sessions"]]
    pred = PRED.predict(acts=acts, sessions=sess, reviews=load_reviews(), race_cfg=b["cfg"],
                        garmin_pred_s=garmin_pred, hr_zones=plan.get("hr_zones"))
    pred["history"] = PRED.record_history(DATA / "prediction_history.json", pred)
    return pred


@app.get("/api/nutrition")
async def nutrition_get():
    acts = await run_in_threadpool(garmin.activities, 120)
    plan = enrich_plan(load_plan(), acts)
    nb = nutrition_bundle(plan)
    nb["prep"] = prep_cards(plan, nb["favorite"])
    return nb


@app.post("/api/nutrition/products")
def nutrition_product(body: dict):
    return nutri.upsert_product(body)


@app.delete("/api/nutrition/products/{pid}")
def nutrition_product_delete(pid: str):
    nutri.delete_product(pid)
    return {"ok": True}


@app.get("/api/nutrition/log/{sid}")
async def nutrition_log_get(sid: str):
    s, plan = await _enriched_session(sid)
    d = nutri.load()
    prods = {p["id"]: p for p in d["products"]}
    lg = d["logs"].get(sid, {"items": [], "water_ml": 0, "notes": ""})
    dur = _session_duration(s) or s.get("planned_s")
    return {"log": lg, "products": d["products"], "analysis": NUTRI.analyse_log(lg, dur, prods), "duration_s": dur}


@app.post("/api/nutrition/log/{sid}")
async def nutrition_log_post(sid: str, body: dict):
    nutri.save_log(sid, body)
    return await nutrition_log_get(sid)


@app.get("/api/prediction")
async def prediction_get():
    acts = await run_in_threadpool(garmin.activities, 120)
    plan = enrich_plan(load_plan(), acts)
    return await run_in_threadpool(compute_prediction, plan, acts)


@app.get("/api/activity/{aid}/track")
async def activity_track(aid: str):
    return await run_in_threadpool(garmin.activity_track, aid)



# ---------------------------------------------------------------- API : module Nutrition (calories / poids)
bodystore = BODY.BodyStore(DATA)


def body_bundle(acts: list[dict] | None = None) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    acts = acts if acts is not None else garmin.activities(120)
    plan = enrich_plan(load_plan(), acts)
    st = bodystore.load()
    start = date.fromisoformat(st["params"]["start_date"])
    first = max(start, date.today() - timedelta(days=60))
    ds = [(first + timedelta(days=i)).isoformat() for i in range((date.today() - first).days + 1)]
    gd = {}
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for d_, kcal in zip(ds, ex.map(garmin.consumed, ds)):
                gd[d_] = {"consumed": kcal}
    except Exception as e:
        log.warning("nutrition : calories mangées Garmin indisponibles (%s)", e)
    out = BODY.compute(st, garmin_days=gd, sessions=plan["sessions"], acts=acts, race_date=plan["race"]["date"])
    try:  # pendant la recharge glucidique, l'objectif du jour vient du plan de recharge
        cd = CARB.active_day(_carb_plans(plan, st), date.today().isoformat())
        if cd:
            t = out["today"]
            t["eat_target"] = cd["kcal"]
            t["left"] = round(cd["kcal"] - (t.get("eaten") or 0))
            t["target_deficit"] = 0
            t["carbs"] = {"target": cd["carbs"], "eaten": cd["eaten"], "title": cd["title"]}
            t["need"] = {**t["need"], "level": "carb", "label": "Recharge glucidique",
                         "advice": f"{cd['title']} : vise {cd['carbs']} g de glucides ({cd['g_per_kg']} g/kg). Détail repas par repas dans « Avant course »."}
    except Exception as e:
        log.warning("recharge glucidique : %s", e)
    return out


carbstore = CARB.CarbStore(DATA)


def _carb_weight(st: dict | None = None) -> float:
    st = st or bodystore.load()
    ws = [v["weight"] for k, v in sorted(st.get("days", {}).items()) if v.get("weight")]
    if ws:
        return ws[-1]
    return float(st.get("params", {}).get("start_weight") or (load_plan().get("athlete") or {}).get("weight_kg") or 64)


def _carb_plans(plan: dict, st: dict | None = None) -> list[dict]:
    start = (load_race_cfg() or {}).get("start_time") or "08:00"
    return CARB.plans(plan["sessions"], plan["race"], _carb_weight(st), start, done=carbstore.load()["done"])


@app.get("/api/carbload")
async def carbload_get():
    def go():
        acts = garmin.activities(60)
        plan = enrich_plan(load_plan(), acts)
        ps = _carb_plans(plan)
        return {"plans": ps, "today": CARB.active_day(ps, date.today().isoformat()), "weight": _carb_weight()}
    return await run_in_threadpool(go)


@app.post("/api/carbload/{day}/{idx}")
def carbload_toggle(day: str, idx: int, body: dict):
    carbstore.toggle(day, idx, bool(body.get("done")))
    _lobby_body_cache.clear()
    _today_cache.clear()
    return {"ok": True}


@app.get("/api/body")
async def body_get():
    return await run_in_threadpool(body_bundle)


@app.post("/api/body/day/{day}")
async def body_day(day: str, body: dict):
    try:
        bodystore.set_day(day, body)
        _lobby_body_cache.clear()
    except ValueError:
        raise HTTPException(400, "Date invalide")
    return await run_in_threadpool(body_bundle)


@app.post("/api/body/params")
async def body_params(body: dict):
    try:
        bodystore.set_params(body)
        _lobby_body_cache.clear()
    except ValueError:
        raise HTTPException(400, "Date de début invalide")
    return await run_in_threadpool(body_bundle)


def _lobby_run() -> dict:
    acts = garmin.activities(120)
    plan = enrich_plan(load_plan(), acts)
    t = date.today().isoformat()
    week = next((w for w in plan["weeks"] if w["current"]), None)
    today_s = [s for s in plan["sessions"] if s["date"] == t and s["type"] != "REPOS"]
    nxt = next((s for s in plan["sessions"] if s["date"] > t and s["type"] not in ("REPOS",)), None)
    return {"race": plan["race"]["name"], "race_date": plan["race"]["date"], "days_to_race": (date.fromisoformat(plan["race"]["date"]) - date.today()).days,
            "today": [{"title": s["title"], "type": s["type"], "status": s.get("status")} for s in today_s],
            "next": {"title": nxt["title"], "date": nxt["date"], "type": nxt["type"]} if nxt else None,
            "week_done": week["done_km"] if week else None, "week_planned": week["planned_km"] if week else None}


_lobby_body_cache: dict = {}


def _lobby_body() -> dict:
    c = _lobby_body_cache.get("v")
    if c and (datetime.now() - c[0]).total_seconds() < 60:
        return c[1]
    b = body_bundle()
    out = {"setup": b["setup"], "today": b["today"], "kpi": b["kpi"], "spark": [r["balance"] for r in b["rows"][-14:]],
           "not_started": b["params"]["start_date"] > date.today().isoformat(), "start_date": b["params"]["start_date"]}
    _lobby_body_cache["v"] = (datetime.now(), out)
    return out


@app.get("/api/lobby/run")
async def lobby_run():
    return await run_in_threadpool(_lobby_run)


@app.get("/api/lobby/body")
async def lobby_body():
    return await run_in_threadpool(_lobby_body)


# ---------------------------------------------------------------- API : module Vu & Lu
mediastore = MEDIA.MediaStore(DATA)


@app.get("/api/media")
def media_get():
    return MEDIA.summary(mediastore.load())


@app.get("/api/media/search")
async def media_search(type: str, q: str):
    def go():
        if DEMO:
            return MEDIA.demo_search(type, q)
        try:
            return MEDIA.search(type, q)
        except Exception as e:
            log.warning("recherche %s « %s » : %s", type, q, e)
            raise HTTPException(502, "Le catalogue ne répond pas pour l'instant : tu peux ajouter le titre à la main.")
    return {"results": await run_in_threadpool(go)}


@app.post("/api/media")
async def media_add(body: dict):
    return await run_in_threadpool(mediastore.add, body)


@app.post("/api/media/refresh")
async def media_refresh():
    n = await run_in_threadpool(mediastore.refresh_airing, True)
    return {"updated": n}


@app.post("/api/media/{iid}")
def media_update(iid: str, body: dict):
    try:
        return mediastore.update(iid, body)
    except KeyError:
        raise HTTPException(404, "Titre introuvable")


@app.post("/api/media/{iid}/progress")
def media_progress(iid: str, body: dict):
    try:
        return mediastore.progress(iid, body)
    except KeyError:
        raise HTTPException(404, "Titre introuvable")


@app.delete("/api/media/{iid}")
def media_delete(iid: str):
    mediastore.delete(iid)
    return {"ok": True}


@app.get("/api/lobby/media")
def lobby_media():
    s = MEDIA.summary(mediastore.load())
    by = {x["id"]: x for x in s["items"]}
    cur = [by[i] for i in s["current"][:3]]
    return {"n": len(s["items"]), "current": [{"title": x["title"], "label": x.get("label"), "pct": x.get("pct"), "type": x["type"], "cover": x.get("cover")} for x in cur],
            "hours": s["month"]["hours"], "upcoming": s["upcoming"][:1]}


# ---------------------------------------------------------------- API : module Finances
fin = FIN.FinanceStore(DATA)


def _cur_month() -> str:
    sd = fin.load()["settings"]["month_start_day"]
    return FIN.month_of(date.today().isoformat(), sd)


def _run_km_year() -> float | None:
    try:
        y = str(date.today().year)
        return round(sum(a["distance_km"] for a in garmin.activities(365) if a.get("is_run") and a["date"][:4] == y), 1)
    except Exception:
        return None


@app.get("/api/fin/overview")
async def fin_overview(month: str | None = None):
    def go():
        fin.apply_recurring()
        d = fin.load()
        ym = month or FIN.month_of(date.today().isoformat(), d["settings"]["month_start_day"])
        o = FIN.overview(d, ym, _run_km_year())
        o["today_month"] = _cur_month()
        o["categories"] = d["categories"]
        o["kinds"] = FIN.KINDS
        o["account_types"] = FIN.ACCOUNT_TYPES
        return o
    return await run_in_threadpool(go)


@app.get("/api/fin/data")
def fin_data():
    d = fin.load()
    d["balances"] = FIN.balances(d)
    d["kinds"] = FIN.KINDS
    d["account_types"] = FIN.ACCOUNT_TYPES
    d["today_month"] = FIN.month_of(date.today().isoformat(), d["settings"]["month_start_day"])
    return d


@app.get("/api/fin/month/{ym}")
def fin_month(ym: str):
    d = fin.load()
    s = FIN.month_summary(d, ym)
    s["transactions"] = sorted([t for t in d["transactions"] if s["from"] <= t["date"] <= s["to"]], key=lambda t: (t["date"], t["id"]), reverse=True)
    return s


@app.get("/api/fin/analysis/{year}")
def fin_analysis(year: int):
    return FIN.analysis(fin.load(), year)


@app.post("/api/fin/settings")
def fin_settings(body: dict):
    return fin.set_settings(body)


@app.post("/api/fin/import/preview")
def fin_import_preview(body: dict):
    try:
        return fin.parse_csv(body.get("text") or "", body.get("account") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/fin/import/commit")
def fin_import_commit(body: dict):
    if not body.get("account"):
        raise HTTPException(400, "Choisis le compte")
    return {"added": fin.commit_import(body["account"], body.get("rows") or [])}


@app.get("/api/fin/export.csv")
def fin_export():
    from fastapi.responses import Response
    return Response(FIN.export_csv(fin.load()), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="finances-{date.today().isoformat()}.csv"'})


@app.post("/api/fin/{coll}")
def fin_upsert(coll: str, body: dict):
    try:
        out = fin.upsert(coll, body)
        if coll == "recurring":
            fin.apply_recurring()
        if coll == "transactions" and body.get("remember") and out.get("category") and out.get("label"):
            pat = FIN._label_key(out["label"])
            if pat:
                fin.upsert("rules", {"pattern": pat, "category": out["category"]})
        return out
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/fin/{coll}/{iid}")
def fin_delete(coll: str, iid: str):
    try:
        fin.delete(coll, iid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/lobby/fin")
def lobby_fin():
    d = fin.load()
    if not d["settings"].get("setup"):
        return {"setup": False}
    ym = FIN.month_of(date.today().isoformat(), d["settings"]["month_start_day"])
    s = FIN.month_summary(d, ym)
    bal = FIN.balances(d)
    return {"setup": True, "net_worth": round(sum(v for k, v in bal.items() if not next((a for a in d["accounts"] if a["id"] == k), {}).get("archived")), 2),
            "spent": s["spent"], "income": s["income"], "var_left": s["var_left"], "per_day_left": s["per_day_left"],
            "savings_rate": s["savings_rate"], "month": ym}


# ---------------------------------------------------------------- Élan : « Aujourd'hui », revue de la semaine, sauvegarde
WEEK_REVIEWS = DATA / "week_reviews.json"
_today_cache: dict = {}


def _load_wr() -> dict:
    try:
        return json.loads(WEEK_REVIEWS.read_text())
    except Exception:
        return {}


def _review_week_default(today: date | None = None) -> date:
    t = today or date.today()
    m = monday(t)
    return m if t.weekday() >= 5 else m - timedelta(days=7)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        log.warning("élan : %s", e)
        return default


def _today_bundle() -> dict:
    c = _today_cache.get("v")
    if c and (datetime.now() - c[0]).total_seconds() < 90:
        return c[1]
    t = date.today()
    ts, tm = t.isoformat(), (t + timedelta(days=1)).isoformat()
    acts = _safe(lambda: garmin.activities(120), []) or []
    plan = enrich_plan(load_plan(), acts)
    out: dict = {"date": ts, "weekday": t.weekday()}

    def run_part():
        sess = [s for s in plan["sessions"] if s["date"] == ts and s["type"] != "REPOS"]
        nxt = [s for s in plan["sessions"] if s["date"] == tm and s["type"] != "REPOS"]
        pick = lambda s: {"id": s["id"], "title": s["title"], "type": s["type"], "summary": s.get("summary"), "planned_km": s.get("planned_km"),
                          "planned_s": s.get("planned_s"), "status": s.get("status"), "done_km": s.get("done_km")}
        return {"today": [pick(s) for s in sess], "tomorrow": [pick(s) for s in nxt], "race": plan["race"]["name"],
                "days_to_race": (date.fromisoformat(plan["race"]["date"]) - t).days}
    out["run"] = _safe(run_part)

    def night_part():
        td = garmin.today()
        m = td.get("metrics") or {}
        trends_ = garmin.trends(28)
        si = SLEEP.insights(trends_, plan["sessions"], {}, config["sleep_goal_h"])
        return {"sleep_h": round(m["sleep_s"] / 3600, 1) if m.get("sleep_s") else None, "score": m.get("sleep_score"),
                "bed": m.get("bed"), "wake": m.get("wake"), "readiness": (td.get("readiness") or {}).get("score"),
                "bb": m.get("bb_high"), "target_bed": si.get("target_bed"), "avg_bed": si.get("avg_bed"), "goal_h": config["sleep_goal_h"],
                "avg7_h": si.get("avg7_h")}
    out["night"] = _safe(night_part)
    out["body"] = _safe(_lobby_body)

    def fin_part():
        d = fin.load()
        if not d["settings"].get("setup"):
            return {"setup": False}
        lf = lobby_fin()
        due = []
        for r in d["recurring"]:
            if not r.get("active", True):
                continue
            for day in (t, t + timedelta(days=1)):
                if int(r.get("day") or 1) == day.day and (r.get("freq") != "year" or (r.get("start") and date.fromisoformat(r["start"]).month == day.month)):
                    due.append({"label": r["label"], "amount": r["amount"], "when": "aujourd'hui" if day == t else "demain"})
        spent_today = round(-sum(x["amount"] for x in d["transactions"] if x["date"] == ts and x["amount"] < 0 and not x.get("to_account")), 2)
        return {**lf, "due": due, "spent_today": spent_today}
    out["fin"] = _safe(fin_part)

    def media_part():
        s = MEDIA.summary(mediastore.load())
        by = {x["id"]: x for x in s["items"]}
        cur = [by[i] for i in s["current"][:2]]
        return {"current": [{"id": x["id"], "title": x["title"], "type": x["type"], "next": x.get("next_label") or x.get("label"), "cover": x.get("cover")} for x in cur],
                "airing_today": [u for u in s["upcoming"] if u["airdate"] == ts]}
    out["media"] = _safe(media_part)
    ws = _review_week_default(t).isoformat()
    wr = _load_wr()
    out["review"] = {"week": ws, "done": bool((wr.get(ws) or {}).get("saved")), "due": t.weekday() >= 5 or (t.weekday() == 0 and not (wr.get(ws) or {}).get("saved")),
                     "priorities": [p for p in ((wr.get((monday(t) - timedelta(days=7)).isoformat()) or {}).get("priorities") or []) if p.get("text")]}
    _today_cache["v"] = (datetime.now(), out)
    return out


@app.get("/api/today")
async def today_api():
    return await run_in_threadpool(_today_bundle)


def _week_review_data(ws: date) -> dict:
    we = ws + timedelta(days=6)
    a, b = ws.isoformat(), we.isoformat()
    t = date.today()
    back = max(28, (t - ws).days + 21)
    acts = _safe(lambda: garmin.activities(back), []) or []
    plan = enrich_plan(load_plan(), acts)
    out: dict = {"week": a, "end": b, "is_current": ws <= t <= we}
    ins: list[dict] = []

    # --- running
    def run_part():
        sess = [s for s in plan["sessions"] if a <= s["date"] <= b and s["type"] not in ("REPOS",)]
        runs = [x for x in acts if x.get("is_run") and a <= x["date"] <= b]
        pa, pb = (ws - timedelta(days=7)).isoformat(), (ws - timedelta(days=1)).isoformat()
        prev_km = round(sum(x["distance_km"] for x in acts if x.get("is_run") and pa <= x["date"] <= pb), 1)
        planned = round(sum(s.get("planned_km") or 0 for s in sess if s["type"] not in ("RENFO",)), 1)
        km = round(sum(x["distance_km"] for x in runs), 1)
        dur = sum(x.get("duration_s") or 0 for x in runs)
        long_ = max(runs, key=lambda x: x["distance_km"], default=None)
        key = [s for s in sess if s["type"] not in ("RENFO",)]
        done = [s for s in key if s.get("status") in ("done", "partial") or (s["type"] == "COURSE" and s.get("activities"))]
        missed = [s for s in key if s.get("status") == "missed"]
        nws, nwe = (ws + timedelta(days=7)).isoformat(), (ws + timedelta(days=13)).isoformat()
        nxt = [s for s in plan["sessions"] if nws <= s["date"] <= nwe and s["type"] not in ("REPOS",)]
        return {"km": km, "planned_km": planned, "prev_km": prev_km, "runs": len(runs), "time_s": dur,
                "elev": round(sum(x.get("elev_gain") or 0 for x in runs)), "load": round(sum(x.get("training_load") or 0 for x in runs)),
                "longest": {"km": long_["distance_km"], "date": long_["date"], "name": long_["name"]} if long_ else None,
                "sessions": [{"date": s["date"], "title": s["title"], "type": s["type"], "status": s.get("status"), "done_km": s.get("done_km"),
                              "planned_km": s.get("planned_km"), "color": s.get("review_color")} for s in sess],
                "n_planned": len(key), "n_done": len(done), "n_missed": len(missed),
                "next": {"planned_km": round(sum(s.get("planned_km") or 0 for s in nxt if s["type"] != "RENFO"), 1),
                         "key": [{"date": s["date"], "title": s["title"], "type": s["type"]} for s in nxt if s["type"] not in ("EF", "RECUP", "RENFO")][:4]},
                "race": plan["race"]["name"], "days_to_race": (date.fromisoformat(plan["race"]["date"]) - t).days}
    R = out["run"] = _safe(run_part)
    if R:
        if R["planned_km"]:
            pct = round(R["km"] / R["planned_km"] * 100)
            ins.append({"mod": "run", "level": "good" if 85 <= pct <= 115 else "warn",
                        "text": f"Running : {km_fr(R['km'])} km sur {km_fr(R['planned_km'])} prévus ({pct} %), {R['n_done']}/{R['n_planned']} séances faites."})
        if R["prev_km"] and R["km"] > R["prev_km"] * 1.2 and R["km"] - R["prev_km"] > 8:
            ins.append({"mod": "run", "level": "warn", "text": f"Volume en hausse de {round((R['km'] / R['prev_km'] - 1) * 100)} % par rapport à la semaine d'avant : surveille la fatigue."})
        if R["n_missed"]:
            ins.append({"mod": "run", "level": "info", "text": f"{R['n_missed']} séance(s) manquée(s) : pas de rattrapage, on reprend le plan normalement."})

    # --- sommeil
    def sleep_part():
        days = (t - ws).days + 1
        tr = [x for x in garmin.trends(min(max(days, 7), 60)) if a <= x["date"] <= b and x.get("sleep_s")]
        if not tr:
            return None
        hs = [x["sleep_s"] / 3600 for x in tr]
        beds = [SLEEP._min(x.get("bed"), True) for x in tr if x.get("bed")]
        sc = [x["sleep_score"] for x in tr if x.get("sleep_score")]
        return {"avg_h": round(sum(hs) / len(hs), 2), "nights": len(tr), "short": sum(1 for h in hs if h < 6), "goal_h": config["sleep_goal_h"],
                "score": round(sum(sc) / len(sc)) if sc else None, "avg_bed": SLEEP._fmt(sum(beds) / len(beds)) if beds else None,
                "series": [{"date": x["date"], "h": round(x["sleep_s"] / 3600, 2), "bed": x.get("bed")} for x in tr]}
    S = out["sleep"] = _safe(sleep_part)
    if S:
        g = S["goal_h"]
        ins.append({"mod": "sleep", "level": "good" if S["avg_h"] >= g - 0.25 else "warn",
                    "text": f"Sommeil : {_hfr(S['avg_h'])} par nuit en moyenne (objectif {_hfr(g)})" + (f", coucher moyen {S['avg_bed']}." if S["avg_bed"] else ".")})
        if S["short"] >= 2:
            ins.append({"mod": "sleep", "level": "warn", "text": f"{S['short']} nuits sous les 6 h : c'est le levier le plus simple pour mieux récupérer."})

    # --- nutrition
    def body_part():
        bb = body_bundle(acts)
        rows = [r for r in bb["rows"] if a <= r["date"] <= b]
        if not bb["setup"] or not rows:
            return None
        tracked = [r for r in rows if r["balance"] is not None]
        eaten = [r["eaten"] for r in rows if r["eaten"] is not None]
        ws_ = [r["weight"] for r in rows if r.get("weight")]
        return {"days": len(rows), "tracked": len(tracked), "missing_burn": sum(1 for r in rows if r["missing_burn"]),
                "balance": sum(r["balance"] for r in tracked), "avg_balance": round(sum(r["balance"] for r in tracked) / len(tracked)) if tracked else None,
                "avg_eaten": round(sum(eaten) / len(eaten)) if eaten else None, "weighins": len(ws_),
                "w_first": ws_[0] if ws_ else None, "w_last": ws_[-1] if ws_ else None,
                "avg7_end": next((r["weight_avg7"] for r in reversed(rows) if r.get("weight_avg7")), None),
                "goal_deficit": bb["params"].get("deficit_goal"), "flags": sum(1 for r in rows if r.get("flag"))}
    B = out["body"] = _safe(body_part)
    if B:
        if B["avg_balance"] is not None:
            gd = B["goal_deficit"] or 500
            ins.append({"mod": "body", "level": "good" if 0 < B["avg_balance"] <= gd + 150 else "warn",
                        "text": f"Nutrition : déficit moyen de {B['avg_balance']} kcal/jour sur {B['tracked']} jour(s) suivis, soit ≈ {km_fr(B['balance'] / 7700, 2)} kg."})
        if B["missing_burn"]:
            ins.append({"mod": "body", "level": "info", "text": f"{B['missing_burn']} jour(s) sans dépense saisie : complète-les pour un bilan juste."})

    # --- finances
    def fin_part():
        d = fin.load()
        if not d["settings"].get("setup"):
            return None
        cats = {c["id"]: c for c in d["categories"]}
        def wk_spent(x0, x1):
            tot, bills, by = 0.0, 0.0, defaultdict(float)
            for x in d["transactions"]:
                if not (x0 <= x["date"] <= x1) or x.get("to_account"):
                    continue
                c = cats.get(x.get("category"))
                if (c and c["kind"] == "income") or (not c and x["amount"] > 0):
                    continue
                if c and c["kind"] == "bill":  # loyer, énergie… : charges fixes, à part
                    bills += -x["amount"]
                    continue
                tot += -x["amount"]
                by[(c or {}).get("name") or "Sans catégorie"] += -x["amount"]
            return round(tot, 2), by, round(bills, 2)
        tot, by, bills = wk_spent(a, b)
        prev = [wk_spent((ws - timedelta(days=7 * k)).isoformat(), (we - timedelta(days=7 * k)).isoformat())[0] for k in range(1, 9)]
        prev = [p for p in prev if p]
        return {"spent": tot, "bills": bills, "avg8": round(sum(prev) / len(prev), 2) if prev else None,
                "top": [{"name": k, "amount": round(v, 2)} for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:4]],
                "month": lobby_fin()}
    F = out["fin"] = _safe(fin_part)
    if F and F["spent"]:
        txt = f"Finances : {FIN.fmt_eur(F['spent'])} de dépenses courantes cette semaine"
        if F["avg8"]:
            diff = F["spent"] - F["avg8"]
            txt += f" ({'+' if diff >= 0 else '−'}{FIN.fmt_eur(abs(diff))} par rapport à ta moyenne)"
        ins.append({"mod": "fin", "level": "warn" if F["avg8"] and F["spent"] > F["avg8"] * 1.3 else "info", "text": txt + "."})

    # --- Vu & Lu
    def media_part():
        md = mediastore.load()
        lg = [x for x in md["log"] if a <= x["date"] <= b]
        if not lg and not any(a <= (x.get("finished") or "") <= b for x in md["items"]):
            return None
        sm = lambda typ: sum(x["delta"] for x in lg if x["type"] in typ and x["delta"] > 0)
        return {"hours": round(sum(x["minutes"] for x in lg) / 60, 1), "episodes": sm(("serie", "anime")), "chapters": sm(("manga",)),
                "pages": sm(("livre",)), "finished": [x["title"] for x in md["items"] if a <= (x.get("finished") or "") <= b and x.get("status") == "termine"]}
    M = out["media"] = _safe(media_part)
    if M and M["hours"]:
        ins.append({"mod": "media", "level": "info", "text": f"Vu & Lu : {km_fr(M['hours'])} h d'écran et de lecture" + (f", terminé : {', '.join(M['finished'][:3])}." if M["finished"] else ".")})

    out["insights"] = ins
    wr = _load_wr()
    out["saved"] = wr.get(a) or {}
    prev_r = wr.get((ws - timedelta(days=7)).isoformat()) or {}
    out["prev_priorities"] = [p for p in (prev_r.get("priorities") or []) if p.get("text")]
    out["history"] = [{"week": k, "mood": v.get("mood")} for k, v in sorted(wr.items())[-12:] if v.get("saved")]
    return out


def _hfr(x: float) -> str:
    m = round(x * 60)
    return f"{m // 60} h {m % 60:02d}"


def km_fr(x, nd: int = 1) -> str:
    return (f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else str(round(x))).replace(".", ",")


@app.get("/api/review")
async def review_get(week: str | None = None):
    ws = monday(date.fromisoformat(week)) if week else _review_week_default()
    return await run_in_threadpool(_week_review_data, ws)


@app.post("/api/review/{week}")
def review_save(week: str, body: dict):
    ws = monday(date.fromisoformat(week)).isoformat()
    wr = _load_wr()
    cur = wr.get(ws) or {}
    for k in ("good", "bad", "learn"):
        if k in body:
            cur[k] = str(body[k] or "")[:2000]
    if "mood" in body:
        cur["mood"] = max(0, min(5, int(body["mood"] or 0))) or None
    if "priorities" in body:
        cur["priorities"] = [{"text": str(p.get("text") or "")[:200], "done": bool(p.get("done"))} for p in (body["priorities"] or [])[:3]]
    cur["saved"] = datetime.now().isoformat(timespec="minutes")
    wr[ws] = cur
    if "prev_done" in body:  # cases cochées sur les priorités de la semaine précédente
        pk = (date.fromisoformat(ws) - timedelta(days=7)).isoformat()
        if wr.get(pk):
            for i, p in enumerate(wr[pk].get("priorities") or []):
                if i < len(body["prev_done"]):
                    p["done"] = bool(body["prev_done"][i])
    tmp = WEEK_REVIEWS.with_suffix(".tmp")
    tmp.write_text(json.dumps(wr, ensure_ascii=False, indent=1))
    tmp.replace(WEEK_REVIEWS)
    _today_cache.clear()
    return {"ok": True, "saved": cur["saved"]}


@app.post("/api/today/priority/{i}")
def today_priority(i: int, body: dict):
    """Coche une priorité de la semaine depuis l'écran d'accueil."""
    pk = (monday(date.today()) - timedelta(days=7)).isoformat()
    wr = _load_wr()
    ps = (wr.get(pk) or {}).get("priorities") or []
    if i < len(ps):
        ps[i]["done"] = bool(body.get("done"))
        WEEK_REVIEWS.write_text(json.dumps(wr, ensure_ascii=False, indent=1))
    _today_cache.clear()
    return {"ok": True}


# --- sauvegarde
def _backup_tick(force: bool = False) -> dict:
    if DEMO:
        return {"ok": False, "error": "Pas de sauvegarde en mode démo."}
    return BACKUP.run(ROOT, config, force=force)


@app.get("/api/backup")
def backup_status():
    return BACKUP.status(config) if not DEMO else {"ok": False, "error": "mode démo"}


@app.post("/api/backup")
async def backup_now():
    return await run_in_threadpool(_backup_tick, True)


# ---------------------------------------------------------------- API : bilans de course + prochaine prépa
debriefs = DEBRIEF.DebriefStore(DATA)
NEXT_PATH = DATA / "next_plan.json"
ARCHIVE_DIR = DATA / "archive"
GARMIN_PRED_KEY = {42.195: "marathon", 21.0975: "half", 10.0: "10k", 5.0: "5k"}


def _race_list(plan: dict, acts: list[dict]) -> list[dict]:
    """Courses du plan (COURSE) + activités marquées « course » dans Garmin."""
    store = debriefs.load()
    out, seen = [], set()
    for s in plan["sessions"]:
        if s["type"] != "COURSE":
            continue
        a = (s.get("activities") or [None])[0]
        aid = str(a["id"]) if a else None
        if aid:
            seen.add(aid)
        db = store.get(aid or "", {})
        out.append({"sid": s["id"], "aid": aid, "date": s["date"], "name": s["title"], "planned_km": s.get("planned_km"),
                    "is_main": s["date"] == plan["race"]["date"], "done": bool(a), "km": a["km"] if a else None,
                    "time_s": db.get("time_s") or (a.get("duration_s") if a else None), "has_debrief": bool(db.get("feedback")),
                    "upcoming": s["date"] > date.today().isoformat()})
    for a in acts:
        if a.get("event_type") == "race" and a.get("is_run") and str(a["id"]) not in seen:
            db = store.get(str(a["id"]), {})
            out.append({"sid": None, "aid": str(a["id"]), "date": a["date"], "name": a.get("name") or "Course", "km": a["distance_km"],
                        "time_s": db.get("time_s") or a.get("duration_s"), "done": True, "has_debrief": bool(db.get("feedback")),
                        "is_main": False, "upcoming": False})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def _std_distance(km_: float) -> float:
    for d in (42.195, 21.0975, 10.0, 5.0):
        if abs(km_ - d) / d < 0.04:
            return d
    return round(km_, 2)


def build_debrief(aid: str, sid: str | None) -> dict:
    acts = garmin.activities(365)
    plan = enrich_plan(load_plan(), acts)
    act = next((a for a in acts if str(a["id"]) == str(aid)), None)
    if not act:
        raise HTTPException(404, "Activité introuvable")
    s = next((x for x in plan["sessions"] if x["id"] == sid), None) if sid else None
    if not s:
        s = next((x for x in plan["sessions"] if x["type"] == "COURSE" and any(str(a["id"]) == str(aid) for a in x.get("activities") or [])), None)
    detail = garmin.activity_detail(str(aid))
    track = (garmin.activity_track(str(aid)) or {}).get("points") or []
    saved = debriefs.get(aid)
    fb = saved.get("feedback") or {}
    is_main = bool(s and s["date"] == plan["race"]["date"])
    dist_race = float(plan["race"]["distance_km"]) if is_main else _std_distance(act["distance_km"])
    goal_s = None
    if fb.get("goal"):
        goal_s = DEBRIEF.hms(fb["goal"])
    elif is_main:
        goal_s = DEBRIEF.hms(plan["race"]["goal"])
    plan_rows, carbs_plan = None, None
    if is_main:
        try:
            b = _race_bundle()
            plan_rows, carbs_plan = b["pace"]["rows"], b["nut"].get("carbs_total")
        except Exception as e:
            log.warning("bilan : plan de course indisponible (%s)", e)
    # ravitaillement : clé = séance du plan, sinon l'activité
    fuel_key = s["id"] if s else f"act_{aid}"
    nd = nutri.load()
    prods = {p["id"]: p for p in nd["products"]}
    lg = nd["logs"].get(fuel_key)
    fuel = NUTRI.analyse_log(lg, act.get("duration_s"), prods) if lg else None
    official = DEBRIEF.hms(fb["official_time"]) if fb.get("official_time") else None
    A = DEBRIEF.analyse(act=act, detail=detail, track=track, distance_km_race=dist_race, goal_s=goal_s, plan_rows=plan_rows,
                        official_s=official, fuel=fuel, plan_carbs_total=carbs_plan, hr_zones_plan=plan.get("hr_zones"))
    rd = act["date"]
    sleep_days = []
    for i in range(7, -1, -1):
        try:
            sleep_days.append(garmin.day_metrics((date.fromisoformat(rd) - timedelta(days=i)).isoformat()))
        except Exception:
            pass
    prep = DEBRIEF.prep_recap(race_date=rd, acts=acts, sessions=plan["sessions"] if s else None, reviews=load_reviews(),
                              sleep_days=sleep_days, is_marathon=dist_race > 40)
    pred = None
    if is_main:
        try:
            hist = json.loads((DATA / "prediction_history.json").read_text())
            pred = DEBRIEF.prediction_check(hist, rd, A["time_s"])
        except Exception:
            pass
    auto = DEBRIEF.lessons(A, prep, pred, dist_race > 40)
    kept = saved.get("lessons_keep") or {}
    for l in auto:
        l["keep"] = kept.get(l["id"], l["kind"] in ("bad", "warn"))
    name = (s["title"] if s else None) or act.get("name") or "Course"
    snap = {"name": name, "date": rd, "distance_km": dist_race, "time_s": A["time_s"], "sid": s["id"] if s else None,
            "lessons": [l for l in auto if l["keep"]]}
    if saved.get("time_s") != A["time_s"] or saved.get("name") != name or saved.get("lessons") != snap["lessons"]:
        debriefs.save(aid, snap)
    return {"aid": str(aid), "sid": s["id"] if s else None, "name": name, "date": rd, "is_main": is_main, "distance_km": dist_race,
            "analysis": A, "prep": prep, "prediction": pred, "lessons": auto, "feedback": fb, "fuel_key": fuel_key,
            "fuel_log": lg or {"items": [], "water_ml": 0}, "products": nd["products"],
            "activity": {"name": act.get("name"), "start": act.get("start")}}


@app.get("/api/debriefs")
async def debriefs_list():
    acts = await run_in_threadpool(garmin.activities, 365)
    plan = enrich_plan(load_plan(), acts)
    return {"races": _race_list(plan, acts)}


@app.get("/api/debrief/{aid}")
async def debrief_get(aid: str, sid: str | None = None):
    return await run_in_threadpool(build_debrief, aid, sid)


@app.post("/api/debrief/{aid}")
async def debrief_post(aid: str, body: dict):
    fb = body.get("feedback") or {}
    clean = {"ratings": {k: int(v) for k, v in (fb.get("ratings") or {}).items() if str(v).isdigit()},
             "rpe": int(fb["rpe"]) if str(fb.get("rpe", "")).isdigit() else None}
    for k in ("worked", "to_change", "incidents", "official_time", "goal", "place"):
        clean[k] = str(fb.get(k) or "")[:2000]
    if clean["official_time"] and not DEBRIEF.hms(clean["official_time"]):
        raise HTTPException(400, "Temps officiel au format h:mm:ss")
    patch = {"feedback": clean}
    if "lessons_keep" in body:
        patch["lessons_keep"] = {str(k): bool(v) for k, v in body["lessons_keep"].items()}
    debriefs.save(aid, patch)
    if body.get("fuel") is not None and body.get("fuel_key"):
        nutri.save_log(body["fuel_key"], body["fuel"])
    return await run_in_threadpool(build_debrief, aid, body.get("sid"))


def _review_flags(plan: dict) -> dict:
    reviews = load_reviews()
    fast = 0
    for s in plan["sessions"]:
        if s["type"] in ("SEUIL", "VMA", "AM"):
            rv = (reviews.get(s["id"]) or {}).get("review") or {}
            if sum(1 for g in rv.get("segments", []) if g.get("status") == "fast" and g.get("kind") == "run") >= 2:
                fast += 1
    return {"fast_quality": fast}


def _sleep_avg(days: int = 42) -> float | None:
    try:
        tr = garmin.trends(days)
        v = [d["sleep_s"] for d in tr if d.get("sleep_s")]
        return round(sum(v) / len(v) / 3600, 1) if v else None
    except Exception:
        return None


def _next_state() -> dict:
    acts = garmin.activities(365)
    plan = load_plan()
    sug = PLANNER.suggest(acts=acts, current_plan=plan, debriefs=debriefs.all(), today=date.today())
    draft = json.loads(NEXT_PATH.read_text()) if NEXT_PATH.exists() else None
    archives = sorted([p.name for p in ARCHIVE_DIR.glob("plan-*.json")], reverse=True) if ARCHIVE_DIR.exists() else []
    cur_end = max((s["date"] for s in plan["sessions"]), default=None)
    upcoming = sum(1 for s in plan["sessions"] if s["date"] >= date.today().isoformat() and s["type"] != "REPOS")
    bridge = []
    if draft:
        try:
            ep = enrich_plan(load_plan(), acts)
            start = draft["meta"]["params"]["start_date"]
            mon = date.today() - timedelta(days=date.today().weekday())
            for s in ep["sessions"]:
                if mon.isoformat() <= s["date"] < start:
                    d = date.fromisoformat(s["date"])
                    wk = (d - timedelta(days=d.weekday())).isoformat()
                    if not bridge or bridge[-1]["start"] != wk:
                        bridge.append({"start": wk, "planned_km": 0.0, "sessions": [], "race": False})
                    bridge[-1]["sessions"].append(_clean(s) | {k: s.get(k) for k in ("planned_km", "planned_s", "summary", "status", "done_km", "review_score", "review_color")})
                    bridge[-1]["planned_km"] = round(bridge[-1]["planned_km"] + (s.get("planned_km") or 0), 1)
                    bridge[-1]["race"] = bridge[-1]["race"] or s["type"] == "COURSE"
        except Exception as e:
            log.warning("semaines avant la prépa: %s", e)
        draft["meta"]["summaries"] = {s["id"]: W.describe(s.get("steps", []), draft["paces"]) for s in draft["sessions"]}
        for s in draft["sessions"]:
            s["planned_km"] = session_km(s, draft["paces"])
    return {"suggest": sug, "draft": draft, "archives": archives, "current": {"race": plan["race"], "paces": plan["paces"], "end": cur_end,
                                                                              "upcoming": upcoming, "bridge": bridge}}


@app.get("/api/nextprep")
async def nextprep_get():
    return await run_in_threadpool(_next_state)


@app.post("/api/nextprep/generate")
async def nextprep_generate(body: dict):
    def go():
        for k in ("race_date", "start_date", "goal"):
            if not body.get(k):
                raise HTTPException(400, f"Champ manquant : {k}")
        if body.get("distance") not in PLANNER.DISTANCES:
            raise HTTPException(400, "Distance inconnue")
        if not PLANNER.hms(body["goal"]):
            raise HTTPException(400, "Objectif au format h:mm:ss")
        acts = garmin.activities(365)
        plan = load_plan()
        sug = PLANNER.suggest(acts=acts, current_plan=plan, debriefs=debriefs.all(), today=date.today())
        ref = sug["ref"]
        if body.get("ref_time") and body.get("ref_distance"):
            ref = {"label": "Référence saisie", "distance_km": float(body["ref_distance"]), "time_s": PLANNER.hms(body["ref_time"])}
        params = {k: body.get(k) for k in ("race_name", "race_date", "start_date", "goal", "distance", "days_per_week", "long_day",
                                           "start_km", "peak_km", "renfo", "city", "ref_time", "ref_distance")}
        params["lessons"] = [str(x)[:200] for x in body.get("lessons") or [] if str(x).strip()][:10]
        try:
            draft = PLANNER.generate(params, base_plan=plan, ref=ref, sleep_avg_h=_sleep_avg(), review_flags=_review_flags(plan),
                                     favorite_gel=_favorite_gel())
        except ValueError as e:
            raise HTTPException(400, str(e))
        NEXT_PATH.write_text(json.dumps(draft, ensure_ascii=False, indent=1))
        return _next_state()
    return await run_in_threadpool(go)


@app.delete("/api/nextprep")
def nextprep_delete():
    if NEXT_PATH.exists():
        NEXT_PATH.unlink()
    return {"ok": True}


@app.post("/api/nextprep/schedule")
def nextprep_schedule(body: dict):
    if not NEXT_PATH.exists():
        raise HTTPException(404, "Aucun brouillon")
    d = json.loads(NEXT_PATH.read_text())
    d["meta"]["auto_activate"] = bool(body.get("on"))
    NEXT_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    return {"ok": True, "auto_activate": d["meta"]["auto_activate"]}


def _auto_activate() -> None:
    """Active tout seul le brouillon programmé, le matin de son premier jour."""
    if not NEXT_PATH.exists():
        return
    try:
        d = json.loads(NEXT_PATH.read_text())
        m = d.get("meta") or {}
        if m.get("auto_activate") and date.today().isoformat() >= m["params"]["start_date"]:
            log.info("Activation automatique du plan %s", d["race"]["name"])
            nextprep_activate()
    except Exception as e:
        log.warning("activation automatique: %s", e)


@app.post("/api/nextprep/activate")
def nextprep_activate():
    if not NEXT_PATH.exists():
        raise HTTPException(404, "Aucun brouillon à activer")
    draft = json.loads(NEXT_PATH.read_text())
    start = draft["meta"]["params"]["start_date"]
    with plan_lock:
        cur = load_plan()
        ARCHIVE_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        slug = "".join(c if c.isalnum() else "-" for c in cur["race"]["name"].lower()).strip("-")[:40]
        (ARCHIVE_DIR / f"plan-{cur['race']['date']}-{slug}-{stamp}.json").write_text(json.dumps(cur, ensure_ascii=False, indent=1))
        if RACE_PATH.exists():
            (ARCHIVE_DIR / f"race-{cur['race']['date']}-{slug}-{stamp}.json").write_text(RACE_PATH.read_text())
        # on garde l'historique (séances avant le début de la nouvelle prépa) pour les stats et le calendrier
        old_ids = {s["id"] for s in cur["sessions"] if s["date"] < start}
        kept = [s for s in cur["sessions"] if s["date"] < start]
        used = set(old_ids)
        new_sessions = []
        for s in draft["sessions"]:
            if s["id"] in used:
                n = 1
                while f"{s['id']}b{n}" in used:
                    n += 1
                s = dict(s, id=f"{s['id']}b{n}")
            used.add(s["id"])
            new_sessions.append(s)
        meta = draft.pop("meta")
        new_plan = {**draft, "sessions": kept + new_sessions, "season": {"started": start, "generated": meta.get("generated"),
                                                                         "params": meta.get("params"), "weeks": meta.get("weeks"),
                                                                         "vdot_ref": meta.get("vdot_ref"), "ref": meta.get("ref")}}
        # supprime de la montre les séances futures de l'ancien plan déjà envoyées
        for s in cur["sessions"]:
            if s["date"] >= start and s.get("garmin_workout_id"):
                try:
                    garmin.delete_workout(s["garmin_workout_id"])
                except Exception as e:
                    log.warning("suppression séance montre %s : %s", s["id"], e)
        save_plan(new_plan)
        params = meta.get("params") or {}
        ref = meta.get("ref") or {}
        rc = {"city": params.get("city") or ""}
        if params.get("start_time"):
            rc["start_time"] = params["start_time"]
        if ref.get("distance_km") and abs(float(ref["distance_km"]) - 21.0975) < 0.5:
            rc["ref_half"] = ref.get("time")
        elif ref.get("distance_km") and ref.get("time_s"):
            rc["ref_race"] = {"distance_km": ref["distance_km"], "time": ref.get("time")}
        save_race_cfg(rc)
        NEXT_PATH.unlink()
    try:
        (DATA / "prediction_history.json").rename(ARCHIVE_DIR / f"prediction-{cur['race']['date']}-{stamp}.json")
    except Exception:
        pass
    return {"ok": True, "race": new_plan["race"]}


# ---------------------------------------------------------------- API : coach IA (tâche planifiée Claude)
COACH_RUNS = ["07:20", "21:40"]
_ctx_lock = threading.Lock()


def _review_sync(s: dict, plan: dict) -> dict | None:
    key = _review_key(s, plan)
    cached = load_reviews().get(s["id"])
    if cached and cached.get("key") == key:
        return cached["review"]
    details = [garmin.activity_detail(str(a["id"])) for a in sorted(s.get("activities", []), key=lambda a: str(a.get("start") or a["id"]))]
    rv = coach.review_session(s, plan, details)
    save_review(s["id"], key, rv)
    return rv


def refresh_context() -> dict:
    """Écrit data/coach/context.json (toutes les 5 min) : tout ce dont le coach a besoin, en un seul fichier."""
    with _ctx_lock:
        acts = garmin.activities(120)
        plan = enrich_plan(load_plan(), acts)
        t = date.today().isoformat()
        since = (date.today() - timedelta(days=21)).isoformat()
        for s in plan["sessions"]:
            if since <= s["date"] <= t and s.get("activities") and s.get("steps"):
                try:
                    _review_sync(s, plan)
                except Exception as e:
                    log.debug("review %s: %s", s["id"], e)
        today_data = garmin.today()
        trends_ = garmin.trends(14)
        main = next((s for s in plan["sessions"] if s["date"] == t and s["type"] != "REPOS"), None) \
            or next((s for s in plan["sessions"] if s["date"] == t), None)
        light = coach.morning_light(today_data, trends_, main, plan, config['sleep_goal_h'])
        b = _race_bundle()
        race_summary = {"name": b["cfg"]["name"], "date": b["cfg"]["date"], "start_time": b["cfg"]["start_time"],
                        "city": b["cfg"].get("city"), "goal": b["cfg"]["goal"], "days_to_race": (date.fromisoformat(b["cfg"]["date"]) - date.today()).days,
                        "plan_target": b["pace"]["target"], "half_split": b["pace"]["half"], "strategy": b["pace"]["strategy_label"],
                        "gels_km": [g["km"] for g in b["nut"]["gels"]]}
        ctx = coach_ai.build_context(plan=plan, sessions=plan["sessions"], reviews=load_reviews(), trends=trends_, today=today_data,
                                     light=light, weekly=compute_weekly(acts, load_plan(), 8), race_summary=race_summary,
                                     questions=coach_store.questions(), notes=coach_store.notes(), today_iso=t)
        try:
            si = SLEEP.insights(garmin.trends(28), plan["sessions"], load_reviews(), config["sleep_goal_h"])
            si.pop("series", None)
            ctx["sleep"] = si
        except Exception as e:
            log.warning("sommeil contexte: %s", e)
        try:
            nb = nutrition_bundle(plan)
            ctx["nutrition"] = {"favorite_gel": nb["favorite"] and {k: nb["favorite"].get(k) for k in ("brand", "name", "carbs_g", "tier")},
                                "gel_stock": nb["gel_stock"], "gels_needed_until_race": nb["gels_needed"], "gels_missing": nb["gels_missing"],
                                "tier_list": {t: [p["brand"] + " " + p["name"] for p in ps] for t, ps in nb["board"].items() if ps},
                                "recent_fuel_logs": list(nb["analyses"].values())[:6],
                                "prep_cards": prep_cards(plan, nb["favorite"])}
            pr = compute_prediction(plan, acts)
            ctx["prediction"] = {k: pr.get(k) for k in ("estimate", "range", "pace", "gap_s", "verdict")} | {
                "methods": [{k: m.get(k) for k in ("label", "time", "share", "detail")} for m in pr["methods"]]}
        except Exception as e:
            log.warning("nutrition/prédiction contexte: %s", e)
        try:
            bb = body_bundle(acts)
            ctx["nutrition_tracking"] = {"today": bb["today"], "kpi": bb["kpi"], "alerts": bb["alerts"], "goal_weight": bb["params"].get("goal_weight"),
                                         "last7": [{k: r[k] for k in ("date", "burn", "eaten", "balance", "train", "flag")} for r in bb["rows"][-7:]]}
        except Exception as e:
            log.warning("suivi nutrition contexte: %s", e)
        try:
            ctx["season"] = {"next_plan_draft": NEXT_PATH.exists(),
                             "debriefs": [{"name": d.get("name"), "date": d.get("date"), "time": PLANNER.fmt_hms(d["time_s"]) if d.get("time_s") else None,
                                           "lessons": [l["text"] for l in d.get("lessons", [])],
                                           "to_change": (d.get("feedback") or {}).get("to_change"), "worked": (d.get("feedback") or {}).get("worked")}
                                          for d in sorted(debriefs.all(), key=lambda x: x.get("date", ""))[-3:]]}
        except Exception as e:
            log.warning("saison contexte: %s", e)
        ctx["auto_push"] = {"enabled": config["auto_push"], "hour": config["auto_push_hour"], "log": _autopush_log()[-5:]}
        coach_store.write_context(ctx)
        try:
            em = _weekly_email(REPORT.report_week(date.today()), plan, acts, garmin.trends(21))
            (coach_store.dir / "weekly_email.html").write_text(em["html"])
            (coach_store.dir / "weekly_email.json").write_text(json.dumps({k: v for k, v in em.items() if k != "html"}, ensure_ascii=False))
        except Exception as e:
            log.warning("mail hebdo: %s", e)
        return ctx


def _weekly_email(ws: date, plan: dict, acts: list[dict], trends_: list[dict]) -> dict:
    we = ws + timedelta(days=6)
    notes = coach_store.notes()
    note = next((n for n in reversed(notes) if n["type"] == "weekly"
                 and we.isoformat() <= n["date"] <= (we + timedelta(days=1)).isoformat()), None)
    b = _race_bundle()
    return REPORT.build_weekly_email(week_start=ws, plan=plan, acts=acts, reviews=load_reviews(), trends=trends_,
                                     weekly=compute_weekly(acts, load_plan(), 10), coach_note=note,
                                     race={"name": b["cfg"]["name"], "date": b["cfg"]["date"], "goal": b["cfg"]["goal"]})


@app.get("/api/report/weekly", response_class=HTMLResponse)
async def report_weekly(start: str | None = None):
    ws = date.fromisoformat(start) if start else REPORT.report_week(date.today())
    ws = ws - timedelta(days=ws.weekday())
    acts = await run_in_threadpool(garmin.activities, 120)
    plan = enrich_plan(load_plan(), acts)
    days_back = max(21, (date.today() - ws).days + 8)
    trends_ = await run_in_threadpool(garmin.trends, min(days_back, 90))
    return HTMLResponse(_weekly_email(ws, plan, acts, trends_)["html"])


@app.get("/api/coach")
def coach_get():
    notes = coach_store.notes()
    return {"notes": list(reversed(notes))[:150], "questions": coach_store.questions(), "runs": COACH_RUNS,
            "context_age_min": coach_store.context_age_min(), "unread": sum(1 for n in notes if not n.get("read"))}


@app.post("/api/coach/refresh")
async def coach_refresh():
    await run_in_threadpool(refresh_context)
    return {"ok": True, "context_age_min": coach_store.context_age_min()}


@app.post("/api/coach/questions")
async def coach_ask(body: dict):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Question vide")
    q = coach_store.ask(text, body.get("session_id"))
    if garmin.connected:
        threading.Thread(target=refresh_context, daemon=True).start()
    return q


@app.delete("/api/coach/questions/{qid}")
def coach_delete_q(qid: str):
    coach_store.delete_question(qid)
    return {"ok": True}


@app.post("/api/coach/read")
def coach_read(body: dict):
    coach_store.mark_read(body.get("ids") or [])
    return {"ok": True}


@app.post("/api/coach/proposals/{nid}/{pid}")
async def coach_proposal(nid: str, pid: str, body: dict):
    decision = body.get("decision")
    p = coach_store.get_proposal(nid, pid)
    if not p:
        raise HTTPException(404, "Proposition introuvable")
    if p["status"] != "pending":
        raise HTTPException(400, "Déjà traitée")
    if decision == "reject":
        coach_store.set_proposal_status(nid, pid, "rejected")
        return {"ok": True, "status": "rejected"}
    fields = {k: v for k, v in (p.get("fields") or {}).items() if k in ("date", "type", "title", "description", "steps")}
    if "steps" in fields:
        try:
            W.to_garmin("test", fields["steps"], load_plan()["paces"])
        except Exception as e:
            raise HTTPException(400, f"Étapes proposées invalides : {e}")
    synced = False
    if p["action"] == "update":
        s = update_session(p["session_id"], fields)
        if s.get("garmin_workout_id") and garmin.connected:
            if s.get("type") == "REPOS" or not s.get("steps"):
                await unpush_session(s["id"])
            else:
                await push_session(s["id"])
            synced = True
    elif p["action"] == "create":
        if not fields.get("date"):
            raise HTTPException(400, "Date manquante")
        fields.setdefault("type", "EF")
        fields.setdefault("title", "Séance du coach")
        create_session(fields)
    elif p["action"] == "delete":
        await delete_session(p["session_id"])
    coach_store.set_proposal_status(nid, pid, "accepted")
    if garmin.connected:
        threading.Thread(target=refresh_context, daemon=True).start()
    return {"ok": True, "status": "accepted", "garmin_synced": synced}


# ---------------------------------------------------------------- API : constructeur de séances
@app.post("/api/workout/preview")
def preview(body: dict):
    plan = load_plan()
    steps = body.get("steps", [])
    est = W.estimate(steps, plan["paces"])
    return {"estimate": est, "summary": W.describe(steps, plan["paces"]),
            "garmin": W.to_garmin(body.get("name", "Séance"), steps, plan["paces"], body.get("description", ""))}


@app.post("/api/workout/push")
async def push_free(body: dict):
    plan = load_plan()
    steps = body.get("steps", [])
    if not steps:
        raise HTTPException(400, "Aucune étape")
    name = body.get("name") or "Séance Sub3"
    wj = W.to_garmin(name, steps, plan["paces"], body.get("description", ""))
    res = await run_in_threadpool(garmin.push_workout, wj, body.get("date") or None)
    if body.get("add_to_plan") and body.get("date"):
        s = create_session({"date": body["date"], "type": body.get("type", "EF"), "title": name, "steps": steps,
                            "description": body.get("description", "")})
        with plan_lock:
            plan = load_plan()
            for x in plan["sessions"]:
                if x["id"] == s["id"]:
                    x["garmin_workout_id"] = res["workout_id"]
                    x["garmin_schedule_id"] = res["schedule_id"]
                    x["garmin_pushed_at"] = datetime.now().isoformat(timespec="minutes")
            save_plan(plan)
    return res


@app.get("/api/garmin/workouts")
async def garmin_workouts():
    return await run_in_threadpool(garmin.workouts)


@app.post("/api/cache/clear")
def cache_clear():
    garmin.clear_cache("today")
    garmin.clear_cache("day_" + date.today().isoformat())
    garmin.clear_cache("activities")
    return {"ok": True}


# ---------------------------------------------------------------- front
STATIC = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC / "favicon.ico", media_type="image/x-icon")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


if __name__ == "__main__":
    ip = lan_ip()
    print("\n" + "=" * 58)
    print("  Élan est lancé" + ("  (MODE DÉMO)" if DEMO else ""))
    print(f"  Sur ce Mac      : http://localhost:{PORT}")
    print(f"  Sur ton tél.    : http://{ip}:{PORT}   (même wifi)")
    print(f"  Code PIN tél.   : {config['pin']}")
    print("  Pour arrêter    : ferme cette fenêtre (ou Ctrl+C)")
    print("=" * 58 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
