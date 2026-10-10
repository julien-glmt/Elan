"""Jour J : plan d'allure kilomètre par kilomètre, nutrition et checklist.

Repères utilisés (consensus des recommandations en nutrition du sport d'endurance) :
- charge glucidique : 8-10 g de glucides / kg / jour les 36-48 h avant (on part sur 3 jours progressifs) ;
- petit-déjeuner : 2-3 g/kg, 3 h avant le départ ;
- pendant la course : 60-90 g/h (60 g/h est un bon point de départ si l'estomac n'est pas entraîné) ;
- boisson : 400-800 ml/h selon la chaleur, sodium 300-600 mg/h.
Ce sont des repères généraux, pas une prescription médicale : on les teste à l'entraînement.
"""
from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

DEFAULTS = {
    "name": "Mon marathon",
    "date": "2026-11-08",
    "start_time": "08:00",
    "city": "",
    "goal": "2:59:00",
    "distance_km": 42.195,
    "strategy": "even",          # even | negative | prudent
    "temp_c": 10,
    "ref_half": "",
    "weight_kg": 63,
    "gel_carbs": 25,             # g de glucides par gel
    "carbs_per_hour": 60,        # objectif g/h
    "first_gel_min": 30,
    "caffeine_from_km": 28,      # gel caféiné à partir de ce km (0 = jamais)
    "ravitos": [5, 10, 15, 20, 25, 30, 35, 40],
    "profile": None,             # [{km, gain, loss, ele}] issu d'un GPX
    "checklist": {},
}

CHECKLIST = [
    ("Administratif", ["Dossard + épingles (ou porte-dossard)", "Puce / dossard à puce vérifié", "Certificat / licence si demandé", "Plan d'accès + parking / transport"]),
    ("Tenue", ["Chaussures de course (déjà rodées, 40-80 km)", "Chaussettes testées en sortie longue", "Short / cuissard + tee-shirt de course", "Tenue jetable ou sac poubelle pour l'attente", "Casquette / lunettes selon météo", "Montre chargée à 100 % + séance course chargée"]),
    ("Nutrition", ["Gels (nombre prévu + 1 de secours)", "Gel caféiné", "Boisson pour l'attente (500 ml)", "Petit-déj testé (prévu la veille)", "Pansements / anti-frottements (vaseline, Nok)"]),
    ("Après", ["Vêtements secs + veste", "Collation / boisson de récup", "Claquettes", "Sac de consigne étiqueté"]),
]

STRATEGIES = {
    "even": "Allure régulière",
    "negative": "Léger negative split (2e semi 1 min plus rapide)",
    "prudent": "Départ prudent (5 premiers km +5 s/km)",
}


def hms_to_s(t: str) -> int:
    parts = [int(x) for x in str(t).strip().split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = (parts[0], parts[1], 0) if parts[0] <= 9 else (0, parts[0], parts[1])
    else:
        h, m, s = 0, parts[0], 0
    return h * 3600 + m * 60 + s


def s_to_hms(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def s_to_pace(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


# ------------------------------------------------------------------ prédictions
def predictions(cfg: dict, garmin_pred_s: float | None = None) -> dict:
    out = {"goal_s": hms_to_s(cfg["goal"])}
    if cfg.get("ref_half"):
        half = hms_to_s(cfg["ref_half"])
        # Formule de Riegel (exposant 1,06) — souvent optimiste au marathon si le volume est juste
        out["riegel_s"] = half * (cfg["distance_km"] / 21.0975) ** 1.06
        # Règle prudente : x2 + 10 min (plus réaliste pour un premier marathon rapide)
        out["conservative_s"] = half * 2 + 600
    if garmin_pred_s:
        out["garmin_s"] = garmin_pred_s
    return out


# ------------------------------------------------------------------ GPX
def _haversine(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(d))


def parse_gpx(text: str, race_km: float = 42.195) -> dict:
    root = ET.fromstring(text)
    pts = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("trkpt", "rtept"):
            ele = None
            for c in el:
                if c.tag.split("}")[-1] == "ele" and c.text:
                    ele = float(c.text)
            pts.append((float(el.get("lat")), float(el.get("lon")), ele))
    if len(pts) < 10:
        raise ValueError("Fichier GPX sans tracé exploitable")
    dist = [0.0]
    for a, b in zip(pts, pts[1:]):
        dist.append(dist[-1] + _haversine(a, b))
    total = dist[-1]
    scale = race_km * 1000 / total if total else 1
    # lissage de l'altitude (moyenne glissante sur ~5 points) pour éviter de compter le bruit GPS
    eles = [p[2] for p in pts]
    if all(e is None for e in eles):
        eles = [0.0] * len(pts)
    eles = [e if e is not None else 0.0 for e in eles]
    sm = []
    for i in range(len(eles)):
        w = eles[max(0, i - 2): i + 3]
        sm.append(sum(w) / len(w))
    n_km = math.ceil(race_km)
    prof = []
    j = 0
    for k in range(n_km):
        lo, hi = k * 1000, min((k + 1) * 1000, race_km * 1000)
        gain = loss = 0.0
        start_ele = None
        while j < len(dist) - 1 and dist[j] * scale < hi:
            if dist[j] * scale >= lo:
                if start_ele is None:
                    start_ele = sm[j]
                d = sm[j + 1] - sm[j]
                if d > 0:
                    gain += d
                else:
                    loss -= d
            j += 1
        prof.append({"km": k + 1, "gain": round(gain, 1), "loss": round(loss, 1), "ele": round(start_ele if start_ele is not None else sm[min(j, len(sm) - 1)], 1)})
    return {"profile": prof, "start": {"lat": pts[0][0], "lon": pts[0][1]}, "gpx_km": round(total / 1000, 2),
            "gain": round(sum(p["gain"] for p in prof)), "loss": round(sum(p["loss"] for p in prof))}


# ------------------------------------------------------------------ plan d'allure
def heat_factor(temp_c: float | None) -> float:
    """Au-delà de ~12 °C, on perd environ 0,4 % par degré sur marathon (ordre de grandeur)."""
    if temp_c is None or temp_c <= 12:
        return 1.0
    return 1 + 0.004 * (temp_c - 12)


def pacing(cfg: dict) -> dict:
    dist = float(cfg["distance_km"])
    goal = hms_to_s(cfg["goal"])
    hf = heat_factor(cfg.get("temp_c"))
    target = goal * hf
    n = math.ceil(dist)
    lens = [1.0] * (n - 1) + [round(dist - (n - 1), 3)]
    half_km = dist / 2

    # 1) poids de stratégie (secondes/km relatives)
    off = []
    for i in range(n):
        km_mid = i + lens[i] / 2
        o = 0.0
        if cfg.get("strategy") == "negative":
            o = 1.4 if km_mid < half_km else -1.4      # ≈ 1 min d'écart entre les deux semis
        elif cfg.get("strategy") == "prudent":
            o = 5.0 if i < 5 else 0.0
        off.append(o)

    # 2) dénivelé : +3,3 % par % de pente en montée, -1,8 % par % en descente (effort constant)
    prof = cfg.get("profile") or []
    grade_f = []
    for i in range(n):
        p = prof[i] if i < len(prof) else None
        if p:
            up = p["gain"] / (lens[i] * 1000) * 100
            down = p["loss"] / (lens[i] * 1000) * 100
            grade_f.append(1 + 0.033 * up - 0.018 * down)
        else:
            grade_f.append(1.0)

    base = target / dist
    raw = [(base + off[i]) * grade_f[i] for i in range(n)]
    tot = sum(r * l for r, l in zip(raw, lens))
    k = target / tot
    paces = [r * k for r in raw]

    start_dt = datetime.combine(date.fromisoformat(cfg["date"]), datetime.strptime(cfg.get("start_time") or "09:00", "%H:%M").time())
    rows, cum = [], 0.0
    ravitos = set(int(x) for x in cfg.get("ravitos") or [])
    for i in range(n):
        cum += paces[i] * lens[i]
        km_label = dist if i == n - 1 else i + 1
        p = prof[i] if i < len(prof) else None
        rows.append({
            "km": round(km_label, 3), "len": lens[i], "pace_s": round(paces[i], 1), "pace": s_to_pace(paces[i]),
            "cum_s": round(cum), "cum": s_to_hms(cum), "clock": (start_dt + timedelta(seconds=cum)).strftime("%H:%M"),
            "gain": p["gain"] if p else None, "loss": p["loss"] if p else None, "ele": p["ele"] if p else None,
            "ravito": (i + 1) in ravitos, "notes": [],
        })
    splits5 = []
    for k5 in list(range(5, n, 5)) + [None]:
        r = rows[-1] if k5 is None else rows[k5 - 1]
        prev = splits5[-1]["cum_s"] if splits5 else 0
        seg_len = (r["km"] - (splits5[-1]["km"] if splits5 else 0))
        splits5.append({"km": r["km"], "cum_s": r["cum_s"], "cum": r["cum"], "clock": r["clock"],
                        "split": s_to_pace(r["cum_s"] - prev),
                        "pace": s_to_pace((r["cum_s"] - prev) / seg_len)})
    half_t = next(r["cum_s"] for r in rows if r["km"] >= 21) - paces[20] * (21 - half_km)
    return {"rows": rows, "splits5": splits5, "target_s": round(target), "target": s_to_hms(target), "goal_s": goal,
            "heat_factor": round(hf, 3), "half_s": round(half_t), "half": s_to_hms(half_t),
            "avg_pace": s_to_pace(target / dist), "start": start_dt.isoformat(timespec="minutes"),
            "strategy_label": STRATEGIES.get(cfg.get("strategy"), "")}


# ------------------------------------------------------------------ nutrition
def nutrition(cfg: dict, pace: dict) -> dict:
    w = float(cfg.get("weight_kg") or 63)
    rows = pace["rows"]
    start = datetime.fromisoformat(pace["start"])
    race_day = date.fromisoformat(cfg["date"])

    loading = []
    for d_before, gkg, note in [(3, 7, "On augmente les féculents, on réduit fibres et graisses."),
                                (2, 9, "Pic de la charge : féculents à chaque repas + collations sucrées."),
                                (1, 9, "Dernier dîner tôt, simple et connu. Pas de nouveauté.")]:
        d = race_day - timedelta(days=d_before)
        loading.append({"date": d.isoformat(), "label": f"J-{d_before}", "g_per_kg": gkg, "grams": round(w * gkg / 10) * 10, "note": note})

    breakfast_time = start - timedelta(hours=3)
    bf_g = round(w * 2.5 / 5) * 5

    # Gels : intervalle selon la cible g/h, premier gel après first_gel_min
    cph = max(30, float(cfg.get("carbs_per_hour") or 60))
    gel_g = max(10, float(cfg.get("gel_carbs") or 25))
    interval = gel_g / cph * 60  # minutes
    gels = []
    t = float(cfg.get("first_gel_min") or 30)
    total_min = pace["target_s"] / 60
    caf_km = float(cfg.get("caffeine_from_km") or 0)
    caf_done = False
    ravitos = [int(x) for x in cfg.get("ravitos") or []]
    while t < total_min - 12:
        # km correspondant
        km_at = next((r["km"] for r in rows if r["cum_s"] >= t * 60), rows[-1]["km"])
        # on se cale sur un ravito à moins d'1 km pour prendre de l'eau avec le gel
        near = [k for k in ravitos if abs(k - km_at) <= 1.0]
        km_take = near[0] if near else round(km_at)
        r = rows[min(len(rows) - 1, max(0, int(math.ceil(km_take)) - 1))]
        caf = bool(caf_km and not caf_done and km_take >= caf_km)
        caf_done = caf_done or caf
        gels.append({"n": len(gels) + 1, "km": km_take, "clock": r["clock"], "elapsed": r["cum"], "caffeine": caf, "with_water": bool(near)})
        t += interval
    for g in gels:
        idx = max(0, int(math.ceil(g["km"])) - 1)
        rows[idx]["notes"].append(f"Gel {g['n']}" + (" caféiné" if g["caffeine"] else ""))
    for r in rows:
        if r["ravito"]:
            r["notes"].insert(0, "Ravito")

    temp = cfg.get("temp_c")
    fluid = 400 if temp is None or temp < 10 else (550 if temp < 18 else 750)
    sodium = 300 if temp is None or temp < 15 else 500

    return {
        "weight_kg": w,
        "loading": loading,
        "breakfast": {"time": breakfast_time.strftime("%H:%M"), "grams": bf_g,
                      "examples": [f"{round(bf_g * 0.45)} g de glucides en pain blanc / brioche + confiture ou miel",
                                   f"{round(bf_g * 0.25)} g via une boisson sucrée / jus",
                                   f"{round(bf_g * 0.30)} g via riz au lait, compote ou banane",
                                   "Café si habitude, 300-500 ml d'eau, pas de nouveauté"]},
        "pre_start": [{"when": "H-45 min", "what": "Dernières gorgées d'eau (150-250 ml) puis toilettes"},
                      {"when": "H-15 min", "what": "Un gel (ou demi-gel) avec un peu d'eau"}],
        "gels": gels, "gel_count": len(gels), "spare_gels": 1,
        "carbs_total": round(len(gels) * gel_g), "carbs_per_hour_real": round(len(gels) * gel_g / (total_min / 60)),
        "fluid_ml_h": fluid, "sodium_mg_h": sodium,
        "loading_foods": [
            ("Pâtes / riz / semoule (cuits)", "≈ 30 g de glucides pour 100 g"),
            ("Pain blanc / baguette", "≈ 50 g pour 100 g (une demi-baguette ≈ 60 g)"),
            ("Pomme de terre", "≈ 17 g pour 100 g"),
            ("Jus de fruits / sirop", "≈ 10-12 g pour 100 ml"),
            ("Compote, banane, fruits secs", "15-25 g par portion"),
            ("Gâteau de riz, pain d'épices, barres", "20-40 g par portion"),
        ],
    }


# ------------------------------------------------------------------ séance « course » pour la montre
def race_steps(pace: dict, nut: dict) -> list[dict]:
    """Découpe en blocs de 5 km avec une fourchette ±4 s autour de l'allure du bloc. Les gels sont dans les notes."""
    rows = pace["rows"]
    steps = []
    start = 0
    bounds = list(range(5, len(rows), 5)) + [len(rows)]
    for b in bounds:
        seg = rows[start:b]
        length = sum(r["len"] for r in seg)
        t = sum(r["pace_s"] * r["len"] for r in seg)
        p = t / length
        notes = [n for r in seg for n in r["notes"] if n.startswith("Gel")]
        km_from, km_to = start, seg[-1]["km"]
        note = f"Km {km_from:g}→{km_to:g} à {s_to_pace(p)} · passage {seg[-1]['cum']}"
        if notes:
            gk = [f"{n} km {math.ceil(r['km'])}" for r in seg for n in r["notes"] if n.startswith("Gel")]
            note += " · " + ", ".join(gk)
        steps.append({"kind": "run", "dur": {"type": "distance", "value": int(round(length * 1000))},
                      "target": {"from": s_to_pace(p + 4), "to": s_to_pace(p - 4)}, "note": note})
        start = b
    return steps


def checklist(cfg: dict) -> list[dict]:
    st = cfg.get("checklist") or {}
    out = []
    for cat, items in CHECKLIST:
        out.append({"cat": cat, "items": [{"id": re.sub(r"\W+", "_", it.lower())[:40], "label": it, "done": bool(st.get(re.sub(r"\W+", "_", it.lower())[:40]))} for it in items]})
    return out


def merged(cfg: dict | None, plan_race: dict | None = None, athlete: dict | None = None) -> dict:
    c = copy.deepcopy(DEFAULTS)
    if athlete and athlete.get("weight_kg"):
        c["weight_kg"] = athlete["weight_kg"]
    if cfg:
        c.update(cfg)
    if plan_race:  # nom, date, objectif et distance viennent toujours du plan
        for k in ("name", "date", "goal", "distance_km"):
            if plan_race.get(k):
                c[k] = plan_race[k]
    return c
