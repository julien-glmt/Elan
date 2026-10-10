"""Générateur de plan pour la prochaine prépa (marathon, semi ou 10 km).

Principes :
- Allures calculées avec le modèle VDOT de Jack Daniels (VO2 de course + % soutenable selon la durée),
  à partir de ta dernière course de référence ; l'allure spécifique (AM / semi / 10 km) vient de ton objectif.
- Périodisation : foncier → développement → spécifique → affûtage, avec une semaine allégée toutes les 4 semaines.
- Volume : progression de 10 % maximum par semaine, du volume de départ vers ton pic.
- Séances clés tirées d'une bibliothèque par phase et par distance, avec une progression d'une semaine à l'autre.
- Tes données et les leçons de tes bilans de course sont ajoutées au plan (règles, descriptions des séances).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import workouts as W

DISTANCES = {"marathon": 42.195, "semi": 21.0975, "10k": 10.0}
DIST_LABELS = {"marathon": "Marathon", "semi": "Semi-marathon", "10k": "10 km"}
RACE_PACE_KEY = {"marathon": "AM", "semi": "SEMI", "10k": "VMA"}

PACE_LABELS = {
    "RECUP": "Récupération (Z1 / bas Z2)",
    "EF": "Endurance fondamentale (Z2 en pratique)",
    "AM": "Allure marathon",
    "SEMI": "Allure semi-marathon",
    "SEUILC": "Seuil continu",
    "SEUIL": "Seuil fractionné",
    "VMA": "VMA / fractionné court",
}


# ------------------------------------------------------------------ modèle VDOT (Daniels & Gilbert)
def _vo2(v_m_min: float) -> float:
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min ** 2


def _pct(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot(dist_km: float, t_s: float) -> float:
    t = t_s / 60
    return _vo2(dist_km * 1000 / t) / _pct(t)


def race_time(vd: float, dist_km: float) -> float:
    """Temps (s) prédit sur dist_km pour un VDOT donné (bissection)."""
    lo, hi = 60.0, 8 * 3600.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot(dist_km, mid) > vd:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def pace_at(vd: float, frac: float) -> float:
    """Allure (s/km) correspondant à frac × VDOT."""
    target = vd * frac
    a, b, c = 0.000104, 0.182258, -(target + 4.60)
    v = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    return 60000 / v


def fmt_pace(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def fmt_hms(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def hms(t: str) -> int:
    p = [int(x) for x in str(t).strip().split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def paces_for(vd_train: float, goal_s: float, dist_key: str) -> dict:
    """Fourchettes d'allure [lente, rapide] pour chaque zone."""
    rp = goal_s / DISTANCES[dist_key]

    def rng(f_slow, f_fast):
        return [fmt_pace(pace_at(vd_train, f_slow)), fmt_pace(pace_at(vd_train, f_fast))]

    am = rp if dist_key == "marathon" else race_time(vd_train, 42.195) / 42.195
    semi = rp if dist_key == "semi" else race_time(vd_train, 21.0975) / 21.0975
    p = {
        "RECUP": rng(0.56, 0.61),
        "EF": rng(0.60, 0.675),
        "AM": [fmt_pace(am + 2), fmt_pace(am - 2)],
        "SEMI": [fmt_pace(semi + 2), fmt_pace(semi - 2)],
        "SEUILC": rng(0.845, 0.865),
        "SEUIL": rng(0.875, 0.90),
        "VMA": rng(0.975, 1.02),
    }
    if dist_key == "10k":
        p["VMA"] = [fmt_pace(min(rp + 2, pace_at(vd_train, 0.965))), fmt_pace(min(rp - 6, pace_at(vd_train, 1.0)))]
    return p


# ------------------------------------------------------------------ étapes
def km(x, kind="run", pace=None, note=None):
    st = {"kind": kind, "dur": {"type": "distance", "value": int(round(x * 1000))}}
    if pace:
        st["target"] = {"pace": pace}
    if note:
        st["note"] = note
    return st


def secs(s, kind="run", pace=None, note=None):
    st = {"kind": kind, "dur": {"type": "time", "value": int(s)}}
    if pace:
        st["target"] = {"pace": pace}
    if note:
        st["note"] = note
    return st


def rep(n, *steps):
    return {"kind": "repeat", "times": int(n), "steps": list(steps)}


def wu(k=3):
    return km(k, "warmup", "EF")


def cd(k=2):
    return km(k, "cooldown", "EF")


def strides(n=5):
    return rep(n, km(0.08, "run", None, "Ligne droite : accélération progressive, relâché"), secs(60, "recovery", None, "Retour en trottinant"))


def jog(s):
    return secs(s, "recovery", None, "Récup en trottinant")


# ------------------------------------------------------------------ bibliothèque de séances
# Chaque entrée : (type, titre, étapes, description). k = rang de la séance dans la phase (0, 1, 2…).
def q_base(k, slot):
    if slot == 1:
        n = [8, 10, 10, 12, 12][min(k, 4)]
        return ("VMA", f"Côtes {n} × 45 s",
                [wu(3), rep(n, secs(45, "run", None, "Montée dynamique, effort ≈ VMA, bon gainage"), secs(90, "recovery", None, "Descente en trottinant")), cd(2)],
                "Force spécifique et économie de course. Pas besoin de chrono : cherche une foulée tonique, pas l'épuisement.")
    n = [10, 12, 15, 15, 18][min(k, 4)]
    return ("VMA", f"VMA courte {n} × 30/30",
            [wu(3), rep(n, secs(30, "run", "VMA", "30 s vite"), secs(30, "recovery", None, "30 s trot")), cd(2)],
            "On réveille la vitesse sans fatigue : tu dois finir en te disant que tu aurais pu en faire 3 de plus.")


def q_dev(k, slot, dist_key):
    if slot == 1:
        opts = [(6, 0.8, 120), (5, 1.0, 150), (6, 1.0, 150), (4, 1.2, 180), (5, 1.2, 180), (6, 1.2, 180)]
        n, d, r = opts[min(k, len(opts) - 1)]
        return ("VMA", f"VMA {n} × {int(d * 1000)} m",
                [wu(3), rep(n, km(d, "run", "VMA"), jog(r)), cd(2)],
                "Allure VMA régulière sur toutes les répétitions : la dernière doit être aussi rapide que la première, pas plus.")
    opts = [(4, 1.5, 90), (3, 2.0, 90), (3, 2.5, 120), (3, 3.0, 120), (2, 4.0, 150), (2, 5.0, 150)]
    n, d, r = opts[min(k, len(opts) - 1)]
    return ("SEUIL", f"Seuil {n} × {str(d).rstrip('0').rstrip('.').replace('.', ',')} km",
            [wu(3), rep(n, km(d, "run", "SEUIL"), jog(r)), cd(2)],
            "Seuil = « confortablement difficile » : tu peux dire quelques mots. Mieux vaut le haut de la fourchette que trop vite.")


def q_spec(k, slot, dist_key):
    if dist_key == "marathon":
        if slot == 1:
            opts = [(5, 1.0), (6, 1.0), (4, 1.5), (3, 2.0), (4, 2.0), (3, 2.0)]
            n, d = opts[min(k, len(opts) - 1)]
            return ("SEUIL", f"Seuil {n} × {str(d).rstrip('0').rstrip('.').replace('.', ',')} km",
                    [wu(2.5), rep(n, km(d, "run", "SEUIL"), jog(75)), cd(1.5)],
                    "Entretien du seuil pendant le bloc spécifique : volume modéré pour garder de la fraîcheur pour l'allure marathon.")
        opts = [(3, 3), (3, 4), (2, 6), (3, 5), (2, 7), (2, 8)]
        n, d = opts[min(k, len(opts) - 1)]
        title = f"Allure marathon {n} × {d} km" if n > 1 else f"{d} km à allure marathon"
        steps = [wu(3), rep(n, km(d, "run", "AM"), jog(120)), cd(2)] if n > 1 else [wu(3), km(d, "run", "AM"), cd(2)]
        return ("AM", title, steps, "Le cœur de la prépa : allure objectif, cardio maîtrisé (Z3). Teste ton ravitaillement de course.")
    if dist_key == "semi":
        if slot == 1:
            opts = [(5, 1.2, 120), (6, 1.0, 90), (4, 1.5, 120), (5, 1.5, 120)]
            n, d, r = opts[min(k, len(opts) - 1)]
            return ("VMA", f"VMA longue {n} × {int(d * 1000)} m",
                    [wu(3), rep(n, km(d, "run", "VMA"), jog(r)), cd(2)], "Développe la vitesse au-dessus de l'allure semi.")
        opts = [(3, 3, "SEMI"), (2, 5, "SEMI"), (3, 4, "SEMI"), (2, 6, "SEMI"), (1, 12, "SEMI")]
        n, d, z = opts[min(k, len(opts) - 1)]
        steps = [wu(3), rep(n, km(d, "run", z), jog(120)), cd(2)] if n > 1 else [wu(3), km(d, "run", z), cd(2)]
        return ("SEMI", f"Allure semi {n} × {d} km" if n > 1 else f"{d} km allure semi", steps,
                "Allure objectif du semi : régulière, relâchée, cardio en Z4 basse.")
    # 10 km
    if slot == 1:
        opts = [(10, 0.4, 75), (8, 0.6, 90), (6, 0.8, 120), (5, 1.0, 120), (12, 0.4, 60)]
        n, d, r = opts[min(k, len(opts) - 1)]
        return ("VMA", f"Allure 10 km {n} × {int(d * 1000)} m",
                [wu(3), rep(n, km(d, "run", "VMA"), jog(r)), cd(2)], "Allure 10 km objectif, récupération courte.")
    opts = [(3, 2.0), (2, 3.0), (4, 1.5), (2, 4.0)]
    n, d = opts[min(k, len(opts) - 1)]
    return ("SEUIL", f"Seuil {n} × {str(d).rstrip('0').rstrip('.').replace('.', ',')} km", [wu(3), rep(n, km(d, "run", "SEUIL"), jog(90)), cd(2)], "Seuil pour tenir l'allure 10 km plus longtemps.")


def q_taper(slot, dist_key, last: bool):
    if dist_key == "marathon":
        if slot == 1:
            return ("SEUIL", "Rappel seuil 4 × 1 km", [wu(3), rep(4, km(1, "run", "SEUIL"), jog(90)), cd(2)], "Garder du rythme sans fatigue.")
        if last:
            return ("AM", "Rappel allure marathon 3 × 1 km", [wu(2), rep(3, km(1, "run", "AM"), jog(90)), cd(1.5)], "Juste pour sentir l'allure. Rien à prouver.")
        return ("AM", "Allure marathon 2 × 4 km", [wu(3), rep(2, km(4, "run", "AM"), jog(120)), cd(2)], "Allure de course, sensations faciles.")
    if dist_key == "semi":
        return ("SEMI", "Rappel allure semi 3 × 2 km", [wu(3), rep(3, km(2, "run", "SEMI"), jog(90)), cd(2)], "Garder le rythme, pas de fatigue.")
    return ("VMA", "Rappel 6 × 400 m allure 10 km", [wu(3), rep(6, km(0.4, "run", "VMA"), jog(75)), cd(2)], "Vivacité avant la course.")


def long_run(dist_key, phase, k, sl_km, fuel_note):
    sl_km = round(sl_km)
    if phase == "spec" and dist_key == "marathon":
        mp = [6, 8, 10, 12, 14, 16][min(k, 5)]
        mp = min(mp, max(4, sl_km - 12))
        steps = [km(sl_km - mp, "run", "EF"), km(mp, "run", "AM", "Allure marathon en fin de sortie")]
        return ("SL", f"Sortie longue {sl_km} km dont {mp} km AM", steps,
                f"Répétition générale : les {mp} derniers km à allure marathon, comme le jour J. {fuel_note}")
    if phase == "spec" and dist_key == "semi":
        sp = min(8, 3 + 2 * k)
        return ("SL", f"Sortie longue {sl_km} km dont {sp} km allure semi",
                [km(sl_km - sp, "run", "EF"), km(sp, "run", "SEMI")], f"Fin de sortie à allure semi. {fuel_note}")
    if phase == "dev" and k % 2 == 1:
        prog = min(5, max(3, round(sl_km * 0.15)))
        return ("SL", f"Sortie longue {sl_km} km progressive",
                [km(sl_km - prog, "run", "EF"), km(prog, "run", "AM" if dist_key == "marathon" else "SEMI", "Fin progressive")],
                f"Les {prog} derniers km plus vite, en restant relâché. {fuel_note}")
    return ("SL", f"Sortie longue {sl_km} km", [km(sl_km, "run", "EF")], f"Endurance fondamentale, allure facile du début à la fin. {fuel_note}")


# ------------------------------------------------------------------ suggestions à partir des données
def suggest(*, acts: list[dict], current_plan: dict, debriefs: list[dict], today: date) -> dict:
    """Valeurs par défaut du formulaire + constats tirés de tes données."""
    runs = [a for a in acts if a.get("is_run") and a.get("distance_km")]
    # semaines (lundi) → km
    weeks: dict[str, float] = {}
    for a in runs:
        d = date.fromisoformat(a["date"])
        wk = (d - timedelta(days=d.weekday())).isoformat()
        weeks[wk] = weeks.get(wk, 0) + a["distance_km"]
    peak_week = max(weeks.values()) if weeks else 50
    longest = max((a["distance_km"] for a in runs), default=20)

    # référence : dernier bilan de course, sinon course Garmin la plus récente, sinon semi du plan
    ref = None
    for d in sorted(debriefs, key=lambda x: x.get("date", ""), reverse=True):
        if d.get("time_s") and d.get("distance_km"):
            ref = {"label": d.get("name") or "Course", "date": d.get("date"), "distance_km": d["distance_km"], "time_s": d["time_s"]}
            break
    if not ref:
        races = [a for a in runs if a.get("event_type") == "race" and a["distance_km"] >= 5]
        if races:
            r = max(races, key=lambda a: a["date"])
            dk = next((d for d in (42.195, 21.0975, 10.0, 5.0) if abs(r["distance_km"] - d) / d < 0.04), r["distance_km"])
            ref = {"label": r.get("name") or "Course", "date": r["date"], "distance_km": dk, "time_s": r["duration_s"]}
    if not ref:
        ath = (current_plan or {}).get("athlete", {})
        ref = {"label": "Semi de référence", "date": None, "distance_km": 21.0975, "time_s": hms("1:30:00")}
        if ath.get("ref"):
            ref["label"] = ath["ref"]
    vd = vdot(ref["distance_km"], ref["time_s"])

    plan_end = max((s["date"] for s in (current_plan or {}).get("sessions", [])), default=today.isoformat())
    start = max(today, date.fromisoformat(plan_end) + timedelta(days=1))
    start = start + timedelta(days=(7 - start.weekday()) % 7)  # lundi suivant
    start = start + timedelta(days=7)  # une semaine de coupure après la dernière course

    equiv = {k: fmt_hms(race_time(vd, d)) for k, d in DISTANCES.items()}
    goal_vd = vd + 1.5
    goal_suggest = {k: fmt_hms(race_time(goal_vd, d)) for k, d in DISTANCES.items()}
    lessons = []
    for d in debriefs:
        lessons += [l["text"] for l in d.get("lessons", []) if l.get("keep", True)]
        lessons += [x for x in (d.get("feedback", {}).get("to_change") or "").split("\n") if x.strip()]
    return {
        "ref": ref | {"time": fmt_hms(ref["time_s"]), "vdot": round(vd, 1)},
        "equivalents": equiv,
        "goal_suggest": goal_suggest,
        "start_date": start.isoformat(),
        "peak_week_km": round(peak_week),
        "longest_km": round(longest, 1),
        "start_km": int(round(max(25, peak_week * 0.6) / 5) * 5),
        "peak_km": int(round(min(peak_week * 1.12, peak_week + 15) / 5) * 5),
        "lessons": lessons[:10],
    }


# ------------------------------------------------------------------ génération
def generate(params: dict, *, base_plan: dict, ref: dict, sleep_avg_h: float | None = None,
             review_flags: dict | None = None, favorite_gel: dict | None = None) -> dict:
    dist_key = params.get("distance", "marathon")
    D = DISTANCES[dist_key]
    race_d = date.fromisoformat(params["race_date"])
    start = date.fromisoformat(params["start_date"])
    start = start - timedelta(days=start.weekday())
    goal_s = hms(params["goal"])
    days = max(3, min(6, int(params.get("days_per_week", 5))))
    long_wd = 5 if params.get("long_day") == "sam" else 6
    start_km = float(params.get("start_km") or 40)
    peak_km = float(params.get("peak_km") or 70)
    renfo = bool(params.get("renfo", True))

    race_week = race_d - timedelta(days=race_d.weekday())
    N = (race_week - start).days // 7 + 1
    if N < 6:
        raise ValueError("Il faut au moins 6 semaines entre le début de la prépa et la course.")
    if N > 30:
        raise ValueError("Prépa trop longue (plus de 30 semaines) : décale la date de début.")

    vd_ref = vdot(ref["distance_km"], ref["time_s"])
    vd_goal = vdot(D, goal_s)
    vd_train = min(vd_goal, vd_ref + 0.5)  # on s'entraîne à son niveau actuel, pas à celui visé
    paces = paces_for(vd_train, goal_s, dist_key)

    # ---- phases
    taper = {"marathon": 3 if N >= 12 else 2, "semi": 2, "10k": 1}[dist_key]
    M = N - taper
    spec = min(7, max(2, round(M * 0.4)))
    dev = min(7, max(2, round(M * 0.35)))
    base = max(0, M - spec - dev)
    phases = ["base"] * base + ["dev"] * dev + ["spec"] * spec + ["taper"] * taper
    # semaines allégées : toutes les 4 semaines pendant la construction, jamais juste avant l'affûtage
    cut = [False] * N
    for i in range(3, M - 1, 4):
        cut[i] = True

    # ---- volume
    build_idx = [i for i in range(M) if not cut[i]]
    vol = [0.0] * N
    nb = len(build_idx)
    peak_at = max(1, nb - 2)  # pic atteint 2 semaines de construction avant la fin
    v = start_km
    for j, i in enumerate(build_idx):
        target = start_km + (peak_km - start_km) * min(1, j / max(1, peak_at - 1))
        v = min(target, v * 1.10) if j else start_km
        vol[i] = v
    for i in range(M):
        if cut[i]:
            prev = vol[i - 1] if i else start_km
            vol[i] = prev * 0.75
    reached = max(vol[:M]) if M else start_km
    taper_f = {"marathon": [0.75, 0.6, 0.4], "semi": [0.75, 0.5], "10k": [0.6]}[dist_key][-taper:]
    if dist_key == "marathon" and taper == 2:
        taper_f = [0.7, 0.4]
    for t in range(taper):
        vol[M + t] = reached * taper_f[t]

    # ---- jours de la semaine
    L = long_wd
    q1d, ef1d, q2d, ef2d = (L - 5) % 7, (L - 4) % 7, (L - 3) % 7, (L - 1) % 7
    xd = (L + 1) % 7
    if days == 3:
        layout = {q1d: "Q1", q2d: "EF", L: "SL"}
    elif days == 4:
        layout = {q1d: "Q1", q2d: "Q2", ef2d: "EF", L: "SL"}
    elif days == 5:
        layout = {q1d: "Q1", ef1d: "EF", q2d: "Q2", ef2d: "EF", L: "SL"}
    else:
        layout = {xd: "EFR", q1d: "Q1", ef1d: "EF", q2d: "Q2", ef2d: "EF", L: "SL"}

    fuel = ""
    if favorite_gel:
        fuel = f"Ravito : 1 {favorite_gel.get('brand', '')} {favorite_gel.get('name', '')} toutes les 30-35 min dès 45 min, et de l'eau."
    else:
        fuel = "Ravito : 1 gel toutes les 30-35 min dès 45 min, et de l'eau."

    sl_cap = {"marathon": 32, "semi": 22, "10k": 18}[dist_key]
    sessions = []
    counters = {"base": 0, "dev": 0, "spec": 0}
    sid = 0
    renfo_left = 0
    weeks_meta = []

    def add(d: date, typ, title, steps, desc=""):
        nonlocal sid
        sid += 1
        sessions.append({"id": f"n{sid:03d}", "date": d.isoformat(), "type": typ, "title": title, "steps": steps, "description": desc})

    for w in range(N):
        wk = start + timedelta(weeks=w)
        ph = phases[w]
        target_km = vol[w]
        is_race_week = w == N - 1
        k = counters.get(ph, 0)
        week_sessions = []
        renfo_left = 2 if renfo and ph in ("base", "dev") else (1 if renfo and ph == "spec" else 0)

        if is_race_week:
            # semaine de course : sur mesure
            for d_off in range(7):
                day = wk + timedelta(days=d_off)
                gap = (race_d - day).days
                if gap == 0:
                    add(day, "COURSE", params.get("race_name") or DIST_LABELS[dist_key],
                        [km(D, "run", RACE_PACE_KEY[dist_key], f"Objectif {params['goal']}")],
                        f"Objectif {params['goal']} ({fmt_pace(goal_s / D)}/km). Départ prudent, ravitaillement comme répété à l'entraînement.")
                elif gap == 1:
                    add(day, "EF", "Veille de course : 20 min + 4 lignes droites", [secs(1200, "run", "EF"), strides(4)],
                        "Juste pour délier les jambes. Dossard, tenue, gels prêts ce soir. Dîner tôt et connu.")
                elif gap == 3:
                    typ, title, steps, desc = q_taper(2, dist_key, last=True)
                    add(day, typ, title, steps, desc)
                elif gap == 5:
                    add(day, "EF", "Footing 8 km" if dist_key == "marathon" else "Footing 6 km",
                        [km(8 if dist_key == "marathon" else 6, "run", "EF")], "Footing facile, on garde de la fraîcheur.")
                elif gap == 6 and days >= 6:
                    add(day, "EF", "Footing 6 km récup", [km(6, "run", "RECUP")], "")
                else:
                    add(day, "REPOS", "Repos" if gap > 0 else "Récupération", [], "" if gap > 0 else "Bravo. Marche, mange, dors : pas de course avant plusieurs jours.")
            weeks_meta.append({"start": wk.isoformat(), "phase": ph, "target_km": round(target_km), "cutback": False, "race": True})
            continue

        # longueur de la sortie longue
        lo_sl, max_share = {"marathon": (14, 0.42), "semi": (12, 0.36), "10k": (11, 0.33)}[dist_key]
        prog = min(1.0, w / max(1, M - 2))
        sl_km = min(sl_cap, lo_sl + (sl_cap - lo_sl) * prog, max(lo_sl, target_km * max_share))
        if cut[w]:
            sl_km = min(sl_km, max(12, target_km * 0.3))
        if ph == "taper":
            t_i = w - M
            sl_taper = {"marathon": [26, 19] if taper == 3 else [22], "semi": [16], "10k": []}[dist_key]
            sl_km = sl_taper[min(t_i, len(sl_taper) - 1)] if sl_taper else 10

        used = 0.0
        for d_off in range(7):
            role = layout.get(d_off)
            if not role:
                continue
            day = wk + timedelta(days=d_off)
            if role == "SL":
                typ, title, steps, desc = long_run(dist_key, ph if not cut[w] else "dev0", k, sl_km, fuel if sl_km >= 16 else "")
            elif role in ("Q1", "Q2"):
                slot = 1 if role == "Q1" else 2
                if days <= 4 and slot == 2 and ph in ("base",):
                    continue
                if ph == "base":
                    typ, title, steps, desc = q_base(k, slot)
                elif ph == "dev":
                    typ, title, steps, desc = q_dev(k, slot, dist_key)
                elif ph == "spec":
                    typ, title, steps, desc = q_spec(k, slot, dist_key)
                else:
                    typ, title, steps, desc = q_taper(slot, dist_key, last=False)
                if cut[w] and slot == 2:
                    typ, title, steps, desc = ("EF", "Footing + lignes droites", [km(7, "run", "EF"), strides(5)], "Semaine allégée : on laisse le corps assimiler.")
            else:
                continue
            week_sessions.append([day, typ, title, steps, desc])
            used += W.estimate(steps, paces)["meters"] / 1000

        # footings pour compléter le volume
        ef_days = [d for d, r in layout.items() if r in ("EF", "EFR")]
        rest_km = max(0.0, target_km - used)
        n_ef = len(ef_days)
        for j, d_off in enumerate(sorted(ef_days)):
            day = wk + timedelta(days=d_off)
            role = layout[d_off]
            each = rest_km / n_ef if n_ef else 0
            if role == "EFR":
                each = min(each, 8)
            k_ef = max(5.0, min(16.0, round(each * 2) / 2))
            zone = "RECUP" if role == "EFR" else "EF"
            title = f"Footing {k_ef:g} km".replace(".", ",") + (" récup" if role == "EFR" else "")
            steps = [km(k_ef, "run", zone)]
            desc = "Allure facile, conversation possible."
            if role == "EF" and ph in ("dev", "spec") and j == 0 and not cut[w]:
                steps.append(strides(5))
                title += " + lignes droites"
            if renfo_left and role == "EF":
                title += " + renfo"
                desc += " Renfo 20 min après : gainage, fentes, mollets, proprioception."
                renfo_left -= 1
            week_sessions.append([day, "EF", title, steps, desc])
        week_sessions.sort(key=lambda x: x[0])
        for day, typ, title, steps, desc in week_sessions:
            add(day, typ, title, steps, desc)
        # repos explicites
        for d_off in range(7):
            day = wk + timedelta(days=d_off)
            if not any(s["date"] == day.isoformat() for s in sessions):
                add(day, "REPOS", "Repos", [], "")
        if not cut[w] and ph in counters:
            counters[ph] += 1
        weeks_meta.append({"start": wk.isoformat(), "phase": ph, "target_km": round(target_km), "cutback": cut[w], "race": False})

    sessions.sort(key=lambda s: (s["date"], s["id"]))
    for wm in weeks_meta:
        end = (date.fromisoformat(wm["start"]) + timedelta(days=6)).isoformat()
        wm["planned_km"] = round(sum(W.estimate(s["steps"], paces)["meters"] / 1000 for s in sessions if wm["start"] <= s["date"] <= end), 1)

    # ---- règles personnalisées
    rules = [
        "EF et sorties longues : laisse la FC primer si l'allure et le cardio ne concordent pas.",
        "Séances de qualité : l'allure pilote, la FC sert de garde-fou.",
        "Une semaine allégée toutes les 4 semaines : ne la saute pas, c'est là que tu progresses.",
        "Le plan est une trame : si tu es cuit, on décale une séance plutôt que de forcer.",
    ]
    insights = []
    if review_flags and review_flags.get("fast_quality", 0) >= 2:
        rules.insert(0, "Tu pars souvent trop vite sur les séances de seuil : vise le haut (le plus lent) de la fourchette.")
        insights.append("Seuil souvent trop rapide dans la dernière prépa : les fourchettes sont à respecter, pas à battre.")
    if sleep_avg_h and sleep_avg_h < 7:
        rules.append(f"Sommeil : {sleep_avg_h:.1f} h en moyenne pendant la dernière prépa. Objectif 7 h 30 les nuits avant les séances clés.")
        insights.append(f"Sommeil moyen de {sleep_avg_h:.1f} h : c'est ton levier le plus simple.")
    for l in params.get("lessons") or []:
        rules.append("Leçon : " + l)

    ath = dict(base_plan.get("athlete") or {})
    ath["ref"] = f"{ref.get('label', 'Course')} : {fmt_hms(ref['time_s'])} sur {ref['distance_km']:g} km (VDOT {vd_ref:.1f})"
    return {
        "race": {"name": params.get("race_name") or DIST_LABELS[dist_key], "date": race_d.isoformat(), "goal": params["goal"], "distance_km": D},
        "paces": paces,
        "pace_labels": PACE_LABELS,
        "athlete": ath,
        "hr_zones": base_plan.get("hr_zones") or [],
        "rules": rules,
        "sessions": sessions,
        "meta": {
            "generated": date.today().isoformat(), "params": params, "weeks": weeks_meta, "insights": insights,
            "vdot_ref": round(vd_ref, 1), "vdot_goal": round(vd_goal, 1), "vdot_train": round(vd_train, 1),
            "ref": {**ref, "time": fmt_hms(ref["time_s"])},
            "goal_equiv_ref": fmt_hms(race_time(vd_ref, D)),
            "phase_counts": {p: phases.count(p) for p in ("base", "dev", "spec", "taper")},
            "peak_reached_km": round(reached), "n_weeks": N,
            "warnings": ([f"Pic ramené à {round(reached)} km/semaine pour respecter +10 % par semaine maximum."] if reached < peak_km - 2 else [])
                        + ([f"Objectif ambitieux : il demande {vd_goal - vd_ref:+.1f} points de VDOT par rapport à ta référence (≈ +1 à +3 sur une prépa est réaliste)."]
                           if vd_goal - vd_ref > 3 else []),
        },
    }
