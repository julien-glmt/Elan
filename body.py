"""Module Nutrition : suivi calories / poids (bilan énergétique), relié à l'entraînement.

Chaque jour : calories dépensées (Garmin automatiquement, ou saisies à la main) − calories mangées = bilan.
Le cumul donne une perte estimée (7 700 kcal ≈ 1 kg de gras), comparée au poids réel (moyenne 7 jours).
Le module tient compte du plan d'entraînement : pas de déficit les jours de sortie longue, de séance clé
ou avant une course (sinon on dégrade l'entraînement, comme le 5 octobre).
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median

DEFAULT_PARAMS = {
    "start_date": date.today().isoformat(),
    "start_weight": None,
    "goal_weight": None,
    "bf_start": None,
    "bf_goal": None,
    "kcal_per_kg": 7700,
    "deficit_goal": 500,
    "maintenance": 2500,
}

KEY_TYPES = {"SEUIL", "VMA", "AM", "SEMI", "COURSE"}


def _f(x):
    try:
        if x is None or x == "":
            return None
        return float(str(x).replace(",", ".").replace(" ", ""))
    except Exception:
        return None


class BodyStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "body.json"
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except Exception:
            d = {}
        d.setdefault("params", {})
        d["params"] = {**DEFAULT_PARAMS, **d["params"]}
        d.setdefault("days", {})
        return d

    def save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    def set_params(self, body: dict) -> dict:
        with self.lock:
            d = self.load()
            p = d["params"]
            if body.get("start_date"):
                date.fromisoformat(body["start_date"])
                p["start_date"] = body["start_date"]
            for k in ("start_weight", "goal_weight", "bf_start", "bf_goal", "kcal_per_kg", "deficit_goal", "maintenance"):
                if k in body:
                    p[k] = _f(body[k])
            d["setup"] = True
            self.save(d)
            return p

    def set_day(self, day: str, body: dict) -> dict:
        date.fromisoformat(day)
        with self.lock:
            d = self.load()
            cur = d["days"].get(day, {})
            for k in ("eaten", "burn", "weight", "sleep_h"):
                if k in body:
                    v = _f(body[k])
                    if v is None:
                        cur.pop(k, None)
                    else:
                        cur[k] = v
            if "comment" in body:
                c = str(body.get("comment") or "")[:300]
                if c:
                    cur["comment"] = c
                else:
                    cur.pop("comment", None)
            if cur:
                d["days"][day] = cur
            else:
                d["days"].pop(day, None)
            self.save(d)
            return cur


def _train_by_day(sessions: list[dict], acts: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for s in sessions:
        out.setdefault(s["date"], {"sessions": [], "km_done": 0.0, "kcal_act": 0})
        out[s["date"]]["sessions"].append({"type": s["type"], "title": s["title"], "planned_km": s.get("planned_km"),
                                          "planned_s": s.get("planned_s")})
    for a in acts:
        if a.get("is_run"):
            o = out.setdefault(a["date"], {"sessions": [], "km_done": 0.0, "kcal_act": 0})
            o["km_done"] += a.get("distance_km") or 0
            o["kcal_act"] += a.get("calories") or 0
    return out


def day_need(info: dict | None, race_date: str | None, day: str) -> dict:
    """Déficit conseillé selon l'entraînement du jour (et du lendemain)."""
    info = info or {}
    ss = [s for s in info.get("sessions", []) if s["type"] not in ("REPOS",)]
    long_ = any(s["type"] == "SL" or (s.get("planned_km") or 0) >= 18 or (s.get("planned_s") or 0) >= 5400 for s in ss) or info.get("km_done", 0) >= 18
    key = any(s["type"] in KEY_TYPES for s in ss)
    if race_date:
        gap = (date.fromisoformat(race_date) - date.fromisoformat(day)).days
        if 0 <= gap <= 3:
            return {"level": "race", "max_deficit": 0, "label": "Course proche",
                    "advice": "Pas de déficit : charge en glucides avant la course, on reprend après."}
    if any(s["type"] == "COURSE" for s in ss):
        return {"level": "race", "max_deficit": 0, "label": "Jour de course", "advice": "Jour de course : mange à ta faim, on reprend le suivi demain."}
    if long_:
        return {"level": "long", "max_deficit": 200, "label": "Sortie longue",
                "advice": "Jour de sortie longue : vise l'équilibre (déficit de 200 kcal max) et mange pendant l'effort. Sinon, les jambes lâchent."}
    if key:
        return {"level": "key", "max_deficit": 300, "label": "Séance clé",
                "advice": "Séance de qualité : déficit léger (300 kcal max), et des glucides avant et après."}
    if ss or info.get("km_done", 0) > 0:
        return {"level": "easy", "max_deficit": None, "label": "Footing", "advice": "Jour facile : c'est le bon jour pour le déficit."}
    return {"level": "rest", "max_deficit": None, "label": "Repos", "advice": "Jour de repos : déficit normal, protéines suffisantes."}


def compute(store: dict, *, garmin_days: dict[str, dict], sessions: list[dict], acts: list[dict], race_date: str | None,
            today: date | None = None) -> dict:
    today = today or date.today()
    p = store["params"]
    kpk = p.get("kcal_per_kg") or 7700
    goal_def = p.get("deficit_goal") or 500
    start = date.fromisoformat(p["start_date"])
    train = _train_by_day(sessions, acts)

    # dépense d'un jour sans course (médiane Garmin des jours sans sortie) pour projeter aujourd'hui
    base_burn = p.get("maintenance") or 2500  # sert seulement à estimer la journée en cours
    weight_now = None

    # autour de la course, la recharge glucidique fait gagner 1-2 kg d'eau et de glycogène : ces pesées ne comptent pas dans la tendance
    carb_days: set[str] = set()
    if race_date:
        rdd = date.fromisoformat(race_date)
        carb_days = {(rdd + timedelta(days=k)).isoformat() for k in range(-3, 4)}
    rows = []
    cum = 0.0
    weights: list[tuple[str, float]] = []
    d = start
    end = today
    while d <= end:
        ds = d.isoformat()
        e = store["days"].get(ds, {})
        g = garmin_days.get(ds) or {}
        info = train.get(ds)
        # dépense : uniquement celle que tu saisis (celle de la montre n'est pas fiable) ; facultative, complétable plus tard
        burn, src = (e["burn"], "manuel") if e.get("burn") is not None else (None, None)
        est = None
        if burn is None and ds == today.isoformat():
            kw = (p.get("start_weight") or 63)
            planned_run = sum((s.get("planned_km") or 0) for s in (info or {}).get("sessions", []) if s["type"] not in ("REPOS", "RENFO"))
            run_kcal = (info or {}).get("kcal_act") or ((info or {}).get("km_done") or planned_run) * kw * 0.95
            est = base_burn + run_kcal
        # mangé : ce que tu as noté dans Garmin Connect (ou une correction saisie dans le journal)
        if e.get("eaten") is not None:
            eaten, eaten_src = e["eaten"], "manuel"
        elif g.get("consumed") is not None:
            eaten, eaten_src = g["consumed"], "garmin"
        else:
            eaten, eaten_src = None, None
        bal = round(burn - eaten) if (burn is not None and eaten is not None) else None
        if bal is not None:
            cum += bal
        if e.get("weight") and ds not in carb_days:
            weights.append((ds, e["weight"]))
        w7 = [w for (wd, w) in weights if (d - date.fromisoformat(wd)).days < 7]
        need = day_need(info, race_date, ds)
        flag = None
        if bal is not None and need["max_deficit"] is not None and bal > need["max_deficit"] + 300:
            flag = f"Déficit de {bal} kcal un jour de {need['label'].lower()} : l'entraînement en pâtit."
        rows.append({
            "date": ds, "burn": round(burn) if burn else None, "burn_src": src, "burn_est": round(est) if est else None,
            "eaten": round(eaten) if eaten is not None else None, "eaten_src": eaten_src, "balance": bal,
            "missing_burn": burn is None and ds < today.isoformat(),
            "cum": round(cum), "loss_kg": round(cum / kpk, 2), "weight": e.get("weight"),
            "weight_avg7": round(mean(w7), 2) if w7 else None, "comment": e.get("comment"), "sleep_h": e.get("sleep_h"),
            "train": need["label"], "train_level": need["level"],
            "km": round((info or {}).get("km_done") or 0, 1), "flag": flag, "carb": ds in carb_days,
        })
        d += timedelta(days=1)

    tracked = [r for r in rows if r["balance"] is not None]
    deficit_days = [r for r in tracked if r["balance"] >= 0]
    last14 = [r["balance"] for r in tracked if (today - date.fromisoformat(r["date"])).days < 14]
    last7 = [r["balance"] for r in tracked if (today - date.fromisoformat(r["date"])).days < 7]
    avg = mean([r["balance"] for r in tracked]) if tracked else None
    if weights:
        weight_now = next((r["weight_avg7"] for r in reversed(rows) if r["weight_avg7"]), weights[-1][1])
    start_w = p.get("start_weight") or (weights[0][1] if weights else None)
    est_w = (start_w - cum / kpk) if start_w else None
    cur_w = weight_now or est_w
    goal_w = p.get("goal_weight")
    remaining = round(cur_w - goal_w, 2) if (cur_w and goal_w) else None
    rate = mean(last14) if last14 else avg
    eta = None
    if remaining and remaining > 0 and rate and rate > 50:
        eta = (today + timedelta(days=round(remaining * kpk / rate))).isoformat()
    # tendance réelle du poids (kg/semaine) sur 21 jours
    trend = None
    pts = [((date.fromisoformat(wd) - today).days, w) for wd, w in weights if (today - date.fromisoformat(wd)).days <= 21]
    if len(pts) >= 4:
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        mx, my = mean(xs), mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den:
            trend = round(sum((x - mx) * (y - my) for x, y in pts) / den * 7, 2)

    # objectif du jour
    t_row = rows[-1] if rows and rows[-1]["date"] == today.isoformat() else None
    t_need = day_need(train.get(today.isoformat()), race_date, today.isoformat())
    tm = (today + timedelta(days=1)).isoformat()
    tm_need = day_need(train.get(tm), race_date, tm)
    burn_today = (t_row or {}).get("burn") or (t_row or {}).get("burn_est") or base_burn
    target_def = goal_def if t_need["max_deficit"] is None else min(goal_def, t_need["max_deficit"])
    if tm_need["level"] in ("long", "race") and t_need["max_deficit"] is None:
        target_def = min(target_def, 300)
        t_need = {**t_need, "advice": t_need["advice"] + f" Demain : {tm_need['label'].lower()}, donc déficit léger ce soir et un dîner riche en glucides."}
    eat_target = round((burn_today - target_def) / 10) * 10

    alerts = []
    if start_w and rate and rate * 7 / kpk > 0.0075 * start_w:
        alerts.append(f"Tu perds plus de 0,75 % de ton poids par semaine en rythme ({round(rate)} kcal/jour de déficit) : en pleine prépa, c'est trop. Vise 300-500 kcal/jour.")
    flagged = [r for r in tracked if r["flag"] and (today - date.fromisoformat(r["date"])).days < 14]
    if flagged:
        alerts.append(f"{len(flagged)} jour(s) d'entraînement important avec un gros déficit ces 2 dernières semaines.")
    if len(last7) >= 3 and mean(last7) < -300:
        alerts.append("Surplus moyen sur 7 jours : normal en période de charge ou de récup, sinon reprends le rythme.")

    return {
        "params": p, "setup": bool(store.get("setup")), "rows": rows, "base_burn": base_burn,
        "kpi": {
            "cum": round(cum), "loss_kg": round(cum / kpk, 2), "avg": round(avg) if avg is not None else None,
            "avg7": round(mean(last7)) if last7 else None, "days": len(tracked), "deficit_days": len(deficit_days),
            "surplus_days": len(tracked) - len(deficit_days), "success_pct": round(len(deficit_days) / len(tracked) * 100) if tracked else None,
            "weight_now": round(cur_w, 2) if cur_w else None, "weight_is_estimate": weight_now is None and cur_w is not None,
            "remaining_kg": remaining, "eta": eta, "trend_kg_week": trend,
            "progress_pct": round(min(100, max(0, (start_w - cur_w) / (start_w - goal_w) * 100))) if (start_w and goal_w and cur_w and start_w != goal_w) else None,
        },
        "missing": [r["date"] for r in rows if r["missing_burn"] and (today - date.fromisoformat(r["date"])).days <= 7],
        "today": {"date": today.isoformat(), "burn": round(burn_today), "burn_src": (t_row or {}).get("burn_src") or "estimé",
                  "eaten": (t_row or {}).get("eaten"), "weight": (t_row or {}).get("weight"), "comment": (t_row or {}).get("comment"),
                  "need": t_need, "target_deficit": target_def, "eat_target": eat_target,
                  "left": round(eat_target - ((t_row or {}).get("eaten") or 0)), "tomorrow": tm_need},
        "alerts": alerts,
    }
