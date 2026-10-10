"""Prédiction maison du chrono marathon, à partir de plusieurs méthodes transparentes.

1. Course de référence (semi) → formule de Riegel (exposant 1,06) : souvent optimiste au marathon.
2. Course de référence × 2,11 : règle empirique pour un coureur bien préparé au marathon.
3. Volume (déjà couru + prévu au plan sur les 8 semaines avant la course) et allure d'entraînement → formule de Tanda (2011),
   établie sur des marathoniens amateurs : pénalise un volume hebdo faible.
4. Blocs à allure marathon des sorties longues (≥ 5 km) : si tu les tiens avec un cardio maîtrisé,
   ils donnent une estimation directe (allure tenue + 2 % de fatigue sur la distance complète).
5. Prédiction Garmin (si disponible).

Synthèse : moyenne pondérée (les méthodes basées sur des performances réelles pèsent plus lourd).
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

MARATHON_KM = 42.195


def _hms(s: str) -> int:
    p = [int(x) for x in str(s).split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def fmt(s: float | None) -> str | None:
    if not s:
        return None
    s = int(round(s))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def predict(*, acts: list[dict], sessions: list[dict], reviews: dict, race_cfg: dict, garmin_pred_s: float | None,
            hr_zones: list[dict] | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    methods = []
    D = float(race_cfg.get("distance_km") or MARATHON_KM)
    is_mara = abs(D - MARATHON_KM) < 0.5
    if D > 50:  # ultra / trail : les formules route n'ont pas de sens (dénivelé, marche, ravitos)
        return {"methods": [], "estimate_s": None, "note": "Pas de prédiction chiffrée pour un ultra."}
    ref = race_cfg.get("ref_race") or ({"distance_km": 21.0975, "time": race_cfg["ref_half"]} if race_cfg.get("ref_half") else None)
    if ref and ref.get("time"):
        rs, rd_ = _hms(ref["time"]), float(ref["distance_km"])
        lbl = "ton semi" if abs(rd_ - 21.0975) < 0.3 else ("ton marathon" if abs(rd_ - MARATHON_KM) < 0.5 else f"tes {rd_:g} km")
        methods.append({"id": "riegel", "label": f"Riegel depuis {lbl}", "seconds": rs * (D / rd_) ** 1.06, "weight": 0.25,
                        "detail": f"{ref['time']} sur {rd_:g} km × ({D:g}/{rd_:g})^1,06."
                                  + (" Suppose que tu es aussi endurant que rapide : souvent optimiste." if D > rd_ else "")})
        if is_mara and abs(rd_ - 21.0975) < 0.3:
            methods.append({"id": "half211", "label": "Semi × 2,11", "seconds": rs * 2.11, "weight": 0.25,
                            "detail": "Règle empirique pour un coureur bien préparé spécifiquement au marathon."})

    # Tanda : K = km/semaine moyens sur les 8 semaines AVANT LA COURSE, P = allure moyenne d'entraînement (s/km).
    # La formule a été établie sur les 8 dernières semaines avant le marathon : en pleine prépa, on prend donc
    # les km déjà courus dans cette fenêtre + les km prévus au plan d'ici la course (prédiction « si tu suis le plan »).
    since_now = (today - timedelta(weeks=8)).isoformat()
    runs = [a for a in acts if a.get("is_run") and a["date"] >= since_now and a.get("distance_km") and a.get("duration_s")]
    if is_mara and len(runs) >= 10:
        P = sum(a["duration_s"] for a in runs) / sum(a["distance_km"] for a in runs)
        K_now = sum(a["distance_km"] for a in runs) / 8
        K, K_done, K_plan = K_now, None, None
        rd = race_cfg.get("date")
        if rd and date.fromisoformat(rd) > today:
            race_d = date.fromisoformat(rd)
            w0 = (race_d - timedelta(weeks=8)).isoformat()
            K_done = sum(a["distance_km"] for a in acts if a.get("is_run") and w0 <= a["date"] <= today.isoformat() and a.get("distance_km"))
            K_plan = sum(float(s.get("planned_km") or 0) for s in sessions
                         if today.isoformat() < s["date"] < rd and s.get("type") not in ("REPOS", "RENFO", "COURSE"))
            K = (K_done + K_plan) / 8
        pm = 17.1 + 140.0 * math.exp(-0.0053 * K) + 0.55 * P
        pm_now = 17.1 + 140.0 * math.exp(-0.0053 * K_now) + 0.55 * P
        detail = (f"Volume moyen sur les 8 semaines avant la course : {K:.0f} km/semaine "
                  + (f"({K_done:.0f} km déjà courus + {K_plan:.0f} km prévus au plan), " if K_plan is not None else "")
                  + f"allure moyenne d'entraînement {int(P // 60)}:{int(P % 60):02d}/km. "
                  + f"Avec ton volume actuel ({K_now:.0f} km/semaine sur les 8 dernières semaines), elle donnerait {fmt(pm_now * MARATHON_KM)}. "
                  "C'est la méthode la plus sévère : elle pénalise les volumes modestes.")
        methods.append({"id": "tanda", "label": "Volume d'entraînement (Tanda)", "seconds": pm * MARATHON_KM, "weight": 0.10,
                        "detail": detail,
                        "inputs": {"km_week": round(K, 1), "km_week_now": round(K_now, 1), "avg_pace_s": round(P),
                                   "tanda_now_s": round(pm_now * MARATHON_KM)}})

    # Blocs à allure marathon (sorties longues)
    z3_hi = None
    for z in hr_zones or []:
        if z.get("zone") == 3:
            try:
                z3_hi = int(str(z["range"]).split("-")[1])
            except Exception:
                pass
    blocks = []
    for s in sessions:
        if s["date"] < (today - timedelta(weeks=6)).isoformat() or s["date"] > today.isoformat():
            continue
        rv = (reviews.get(s["id"]) or {}).get("review") or {}
        for seg in rv.get("segments", []):
            tgt = seg.get("target") or ""
            if seg.get("pace_s") and seg.get("dist") and seg["dist"] >= 5000 and seg.get("kind") == "run" \
                    and (seg.get("zone") == "AM" or tgt.startswith("4:1") or tgt.startswith("4:2")):
                blocks.append({"date": s["date"], "km": round(seg["dist"] / 1000, 1), "pace_s": seg["pace_s"], "hr": seg.get("hr")})
    if blocks and is_mara:
        ok = [b for b in blocks if not z3_hi or not b["hr"] or b["hr"] <= z3_hi]
        use = ok or blocks
        pace = sum(b["pace_s"] * b["km"] for b in use) / sum(b["km"] for b in use)
        methods.append({"id": "mp_blocks", "label": "Tes blocs à allure marathon", "seconds": pace * MARATHON_KM * 1.02, "weight": 0.35 if ok else 0.15,
                        "detail": f"{len(use)} bloc(s) de 5 km et plus, à {int(pace // 60)}:{int(pace % 60):02d}/km en moyenne"
                                  + (", cardio maîtrisé" if ok else ", mais cardio au-dessus de la Z3") + ", +2 % pour la fatigue sur 42 km.",
                        "blocks": use[-5:]})
    if garmin_pred_s:
        methods.append({"id": "garmin", "label": "Prédiction Garmin", "seconds": float(garmin_pred_s), "weight": 0.15,
                        "detail": "Calculée par ta montre (VO2max, historique)."})

    if not methods:
        return {"methods": [], "estimate_s": None}
    goal_lbl = race_cfg.get("goal", "2:59:00")
    w = sum(m["weight"] for m in methods)
    est = sum(m["seconds"] * m["weight"] for m in methods) / w
    perf = [m["seconds"] for m in methods if m["id"] in ("riegel", "half211", "mp_blocks", "garmin")]
    lo, hi = (min(perf), max(perf)) if perf else (est, est)
    goal = _hms(race_cfg.get("goal", "2:59:00"))
    for m in methods:
        m["time"] = fmt(m["seconds"])
        m["pace"] = f"{int(m['seconds'] / D // 60)}:{int(m['seconds'] / D % 60):02d}"
        m["share"] = round(m["weight"] / w * 100)
    gap = est - goal
    if gap <= -60:
        verdict = f"Objectif {goal_lbl} dans tes cordes : garde la tête froide au départ."
    elif gap <= 60:
        verdict = f"Objectif {goal_lbl} jouable mais serré : tout se jouera sur la gestion, la nutrition et le sommeil d'ici là."
    elif gap <= 240:
        verdict = f"Objectif {goal_lbl} ambitieux aujourd'hui : les prochaines séances spécifiques seront décisives."
    else:
        verdict = f"Objectif {goal_lbl} très ambitieux en l'état : on refera le point après les prochaines séances clés."
    t_iso = today.isoformat()
    keys = [s for s in sessions if t_iso < s["date"] < race_cfg.get("date", "9999")
            and (s.get("type") in ("AM", "SEMI") or (s.get("type") == "SL" and ("AM" in s.get("title", "") or "allure" in s.get("title", "").lower())))][:2]
    levers = [f"Séance clé du {date.fromisoformat(s['date']).strftime('%d/%m')} : {s['title']}, cardio maîtrisé." for s in keys]
    levers += ["Volume : enchaîner les semaines prévues sans casse.", "Sommeil : rembourser la dette avant les séances clés.",
               "Nutrition : 60 g/h testés en sortie longue." if is_mara else "Récupération : arriver frais sur les séances de qualité."]
    return {"methods": methods, "estimate_s": round(est), "estimate": fmt(est), "range": [fmt(lo), fmt(hi)],
            "pace": f"{int(est / D // 60)}:{int(est / D % 60):02d}", "goal_s": goal, "gap_s": round(gap),
            "verdict": verdict, "mp_blocks": blocks[-6:], "levers": levers}


def record_history(path: Path, pred: dict) -> list[dict]:
    try:
        hist = json.loads(path.read_text())
    except Exception:
        hist = []
    if pred.get("estimate_s"):
        t = date.today().isoformat()
        hist = [h for h in hist if h["date"] != t] + [{"date": t, "estimate_s": pred["estimate_s"],
                                                        **{m["id"]: round(m["seconds"]) for m in pred["methods"]}}]
        hist = hist[-180:]
        path.write_text(json.dumps(hist))
    return hist
