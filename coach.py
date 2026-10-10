"""Le « coach » de Sub3 : bilan automatique des séances et feu du matin.

Tout est calculé localement, sans IA externe, à partir du plan et des données Garmin.
"""
from __future__ import annotations

import copy
import re
from statistics import mean
from typing import Any

import workouts as W

VERSION = "3"  # à incrémenter quand la logique de bilan change (invalide le cache des bilans)
QUALITY_ZONES = {"AM", "SEUIL", "SEUILC", "SEMI", "VMA"}
EASY_ZONES = {"EF", "RECUP"}
PACE_TOL = 3  # s/km de tolérance autour de la fourchette


def fr(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def fmt_pace(s: float | None) -> str:
    return W.sec_to_pace(s) if s else "—"


def hr_zone_bounds(plan: dict, zone: int) -> tuple[int, int] | None:
    for z in plan.get("hr_zones", []):
        if z.get("zone") == zone:
            m = re.match(r"\s*(\d+)\s*-\s*(\d+)", z.get("range", ""))
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


# =====================================================================================
#  BILAN DE SÉANCE
# =====================================================================================
def flatten(steps: list[dict], paces: dict) -> list[dict]:
    """Déplie les blocs répétés : une entrée par étape réellement courue."""
    out: list[dict] = []
    ef_mid = None
    if paces.get("EF"):
        a, b = (W.pace_to_sec(x) for x in paces["EF"])
        ef_mid = (a + b) / 2

    def add(st: dict, group: int | None, rep: int | None):
        tgt = W.resolve_target(st.get("target"), paces)
        dur = st.get("dur") or {}
        mid = (tgt["slow"] + tgt["fast"]) / 2 if tgt and "slow" in tgt else (ef_mid or 300)
        if dur.get("type") == "distance":
            m, s = float(dur["value"]), float(dur["value"]) / 1000 * mid
        elif dur.get("type") == "time":
            s = float(dur["value"])
            m = 0.0 if st.get("kind") == "rest" else s / mid * 1000
        else:
            m, s = 0.0, 0.0
        zone = (st.get("target") or {}).get("pace")
        quality = zone in QUALITY_ZONES or bool(tgt and "slow" in tgt and ef_mid and tgt["fast"] < ef_mid - 30)
        out.append({
            "kind": st.get("kind", "run"), "dur": dur, "planned_m": m, "planned_s": s, "target": tgt,
            "zone": zone or ("PERSO" if tgt and "slow" in tgt else None), "quality": quality,
            "group": group, "rep": rep, "label": _step_label(st),
        })

    for gi, st in enumerate(steps or []):
        if st.get("kind") == "repeat":
            for r in range(int(st.get("times", 1))):
                for sub in st.get("steps", []):
                    add(sub, gi, r + 1)
        else:
            add(st, None, None)
    return out


def _step_label(st: dict) -> str:
    kind = {"warmup": "Échauffement", "cooldown": "Retour au calme", "run": "Course", "recovery": "Récup", "rest": "Repos"}.get(st.get("kind"), "Course")
    dur = st.get("dur") or {}
    if dur.get("type") == "distance":
        v = dur["value"]
        amount = f"{v/1000:g} km".replace(".", ",") if v >= 1000 else f"{v:g} m"
    elif dur.get("type") == "time":
        amount = W.fmt_duration(dur["value"])
    else:
        amount = "lap"
    tg = st.get("target") or {}
    z = f" {tg['pace']}" if tg.get("pace") else (f" @{tg['from']}-{tg['to']}" if tg.get("from") else "")
    return f"{kind} {amount}{z}"


def _merge(laps: list[dict]) -> dict:
    d = sum(l.get("distance_m") or 0 for l in laps)
    t = sum(l.get("duration_s") or 0 for l in laps)
    hr_w = [(l["avg_hr"], l.get("duration_s") or 0) for l in laps if l.get("avg_hr")]
    hr = sum(h * w for h, w in hr_w) / sum(w for _, w in hr_w) if hr_w and sum(w for _, w in hr_w) else None
    return {"distance_m": d, "duration_s": t, "pace_s": t / (d / 1000) if d > 50 else None, "avg_hr": round(hr) if hr else None}


INTENSITY_CAT = {"WARMUP": "warmup", "COOLDOWN": "cooldown", "ACTIVE": "run", "INTERVAL": "run",
                 "RECOVERY": "recovery", "REST": "recovery"}
KIND_CAT = {"warmup": "warmup", "cooldown": "cooldown", "run": "run", "recovery": "recovery", "rest": "recovery"}


def _align_intensity(expected: list[dict], laps: list[dict]) -> list[dict | None] | None:
    """Séance lancée depuis la montre : Garmin marque chaque tour (échauffement, effort, récup, retour au calme).
    On regroupe les tours d'échauffement / retour au calme, puis on associe catégorie par catégorie, dans l'ordre."""
    if not laps or not all(l.get("intensity") for l in laps if (l.get("distance_m") or 0) > 50):
        return None
    groups: list[tuple[str, list[dict]]] = []
    for l in laps:
        if (l.get("distance_m") or 0) <= 50 and (l.get("duration_s") or 0) < 20:
            continue
        cat = INTENSITY_CAT.get(l["intensity"])
        if not cat:
            return None
        if groups and cat in ("warmup", "cooldown") and groups[-1][0] == cat:
            groups[-1][1].append(l)
        else:
            groups.append((cat, [l]))
    by_cat: dict[str, list[dict]] = {}
    for cat, ls in groups:
        by_cat.setdefault(cat, []).append(_merge(ls))
    exp_cat: dict[str, list[int]] = {}
    for i, e in enumerate(expected):
        exp_cat.setdefault(KIND_CAT.get(e["kind"], "run"), []).append(i)
    # les efforts doivent correspondre exactement ; échauffement / retour au calme peuvent être regroupés
    if len(by_cat.get("run", [])) != len(exp_cat.get("run", [])):
        return None
    res: list[dict | None] = [None] * len(expected)
    for cat, idxs in exp_cat.items():
        got = by_cat.get(cat, [])
        if cat in ("warmup", "cooldown") and len(idxs) == 1 and len(got) >= 1:
            res[idxs[0]] = _merge([{"distance_m": g["distance_m"], "duration_s": g["duration_s"], "avg_hr": g["avg_hr"]} for g in got])
            continue
        for i, g in zip(idxs, got):
            res[i] = g
    return res


def _align_structured(expected: list[dict], laps: list[dict]) -> list[dict | None] | None:
    """Séance lancée depuis la montre : un tour par étape."""
    if not laps or len(laps) < len(expected) - 1 or len(laps) > len(expected) + 3:
        return None
    ok = checked = 0
    for e, l in zip(expected, laps):
        if e["dur"].get("type") == "distance" and e["planned_m"] >= 200:
            checked += 1
            if abs((l.get("distance_m") or 0) - e["planned_m"]) <= max(60, 0.12 * e["planned_m"]):
                ok += 1
        elif e["dur"].get("type") == "time" and e["planned_s"] >= 30:
            checked += 1
            if abs((l.get("duration_s") or 0) - e["planned_s"]) <= max(8, 0.12 * e["planned_s"]):
                ok += 1
    if checked == 0 or ok / checked < 0.7:
        return None
    return [_merge([l]) if l else None for l in (laps + [None] * len(expected))[: len(expected)]]


def _align_cumulative(expected: list[dict], laps: list[dict]) -> list[dict | None]:
    """Séance courue librement (tours auto au km) : on découpe la sortie selon la distance prévue."""
    # positions cumulées des tours
    bounds = []
    pos = 0.0
    for l in laps:
        d = l.get("distance_m") or 0
        bounds.append((pos, pos + d, l))
        pos += d
    total = pos
    planned_total = sum(e["planned_m"] for e in expected) or 1
    scale = total / planned_total if 0.85 <= total / planned_total <= 1.15 else 1.0
    res: list[dict | None] = []
    start = 0.0
    for e in expected:
        end = start + e["planned_m"] * scale
        if e["planned_m"] < 1800 or end > total + 200:
            res.append(None)  # trop court pour être isolé avec des tours au km
        else:
            d = t = hw = hsum = 0.0
            for a, b, l in bounds:
                ov = min(b, end) - max(a, start)
                if ov <= 0 or not l.get("distance_m"):
                    continue
                f = ov / l["distance_m"]
                d += ov
                t += (l.get("duration_s") or 0) * f
                if l.get("avg_hr"):
                    hsum += l["avg_hr"] * (l.get("duration_s") or 0) * f
                    hw += (l.get("duration_s") or 0) * f
            res.append({"distance_m": d, "duration_s": t, "pace_s": t / (d / 1000) if d > 50 else None,
                        "avg_hr": round(hsum / hw) if hw else None, "approx": True})
        start = end
    return res


def _match_fast_km_laps(expected: list[dict], laps: list[dict], aligned: list, paces: dict) -> None:
    """Tours auto au km : on retrouve les répétitions d'un km (ou multiples) parmi les tours rapides."""
    reps = [i for i, e in enumerate(expected) if e["quality"] and e["kind"] == "run" and aligned[i] is None]
    if not reps or not paces.get("EF"):
        return
    if any(expected[i]["dur"].get("type") != "distance" or expected[i]["planned_m"] % 1000 for i in reps):
        return
    ef_fast = min(W.pace_to_sec(x) for x in paces["EF"])
    fast = [l for l in laps if (l.get("distance_m") or 0) >= 900 and l.get("pace_s") and l["pace_s"] < ef_fast - 15]
    need = sum(int(expected[i]["planned_m"] // 1000) for i in reps)
    if len(fast) != need:
        return
    k = 0
    for i in reps:
        n = int(expected[i]["planned_m"] // 1000)
        m = _merge(fast[k:k + n])
        m["approx"] = True
        aligned[i] = m
        k += n


def _drift(laps: list[dict], pace_max: float | None = None) -> float | None:
    """Découplage allure/FC (%) entre 1re et 2e moitié de la partie régulière de la sortie."""
    steady = [l for l in laps if l.get("avg_hr") and l.get("pace_s") and (l.get("distance_m") or 0) >= 400
              and (pace_max is None or l["pace_s"] >= pace_max)]
    if len(steady) < 6 or sum(l["duration_s"] for l in steady) < 35 * 60:
        return None
    half = sum(l["duration_s"] for l in steady) / 2
    acc, first, second = 0, [], []
    for l in steady:
        (first if acc < half else second).append(l)
        acc += l["duration_s"]

    def eff(ls):
        m = _merge(ls)
        return (1000 / m["pace_s"]) / m["avg_hr"] if m["pace_s"] and m["avg_hr"] else None

    e1, e2 = eff(first), eff(second)
    if not e1 or not e2:
        return None
    return round((e1 - e2) / e1 * 100, 1)


def review_session(session: dict, plan: dict, details: list[dict]) -> dict:
    paces = plan["paces"]
    expected = flatten(session.get("steps", []), paces)
    laps: list[dict] = []
    for d in details:
        laps.extend([l for l in d.get("laps", []) if (l.get("distance_m") or 0) > 0 or (l.get("duration_s") or 0) > 0])
    done_m = sum(d.get("summary", {}).get("distance_km", 0) or 0 for d in details) * 1000
    done_s = sum(d.get("summary", {}).get("duration_s", 0) or 0 for d in details)
    hr_all = [d["summary"]["avg_hr"] for d in details if d.get("summary", {}).get("avg_hr")]
    planned_m = sum(e["planned_m"] for e in expected)

    rev: dict[str, Any] = {
        "km_done": round(done_m / 1000, 2), "km_planned": round(planned_m / 1000, 1),
        "time_done": done_s, "avg_hr": round(mean(hr_all)) if hr_all else None,
        "segments": [], "intervals": [], "comments": [], "warnings": [], "tip": None, "mode": None, "drift": None,
    }
    if not details:
        rev.update(score=None, verdict="Pas d'activité associée", color="muted")
        return rev
    if not expected:
        rev.update(score=None, verdict="Séance sans structure (rien à comparer)", color="muted")
        return rev

    aligned = _align_intensity(expected, laps) or _align_structured(expected, laps)
    rev["mode"] = "structured" if aligned else "cumulative"
    if not aligned:
        aligned = _align_cumulative(expected, laps)
        _match_fast_km_laps(expected, laps, aligned, paces)

    z2 = hr_zone_bounds(plan, 2)
    penalty = 0.0
    run_weight = sum(e["planned_m"] for e in expected if e["kind"] in ("run", "warmup", "cooldown") and e["target"] and "slow" in e["target"]) or 1

    # --- étapes
    for e, got in zip(expected, aligned):
        seg = {"label": e["label"], "kind": e["kind"], "zone": e["zone"], "group": e["group"], "rep": e["rep"],
               "target": f"{fmt_pace(e['target']['slow'])}–{fmt_pace(e['target']['fast'])}" if e["target"] and "slow" in e["target"] else None,
               "pace": fmt_pace(got["pace_s"]) if got and got.get("pace_s") else None,
               "pace_s": got.get("pace_s") if got else None,
               "hr": got.get("avg_hr") if got else None,
               "dist": round(got["distance_m"]) if got else None,
               "approx": bool(got and got.get("approx")), "status": "na", "delta": None}
        t = e["target"]
        if got and got.get("pace_s") and t and "slow" in t and e["kind"] != "rest":
            p = got["pace_s"]
            if p < t["fast"] - PACE_TOL:
                seg["status"], seg["delta"] = "fast", round(t["fast"] - p)
            elif p > t["slow"] + PACE_TOL:
                seg["status"], seg["delta"] = "slow", round(p - t["slow"])
            else:
                seg["status"] = "ok"
            if e["kind"] in ("run", "warmup", "cooldown") and seg["status"] != "ok":
                w = e["planned_m"] / run_weight
                d = seg["delta"]
                if e["zone"] in EASY_ZONES:
                    # en EF, un peu trop vite est le défaut classique ; trop lent n'est pas grave
                    pts = min(35, d * 1.3) if seg["status"] == "fast" else min(8, d * 0.2)
                else:
                    pts = min(30, d * 1.5)
                penalty += pts * w * (1 if e["quality"] else 0.6) * 2
        rev["segments"].append(seg)

    # --- fractionnés : synthèse par bloc répété
    groups: dict[int, list[dict]] = {}
    for seg, e in zip(rev["segments"], expected):
        if e["group"] is not None and e["kind"] == "run" and e["quality"]:
            groups.setdefault(e["group"], []).append(seg)
    for gi, segs in groups.items():
        measured = [s for s in segs if s["pace_s"]]
        if not measured:
            rev["intervals"].append({"label": segs[0]["label"], "reps": len(segs), "measured": 0})
            continue
        in_range = sum(1 for s in measured if s["status"] == "ok")
        fast = sum(1 for s in measured if s["status"] == "fast")
        slow = sum(1 for s in measured if s["status"] == "slow")
        paces_r = [s["pace_s"] for s in measured]
        fade = round(paces_r[-1] - paces_r[0]) if len(paces_r) >= 3 else None
        rev["intervals"].append({"label": segs[0]["label"], "reps": len(segs), "measured": len(measured),
                                 "in_range": in_range, "fast": fast, "slow": slow, "target": segs[0]["target"],
                                 "avg_pace": fmt_pace(mean(paces_r)), "avg_s": mean(paces_r),
                                 "fast_s": expected[[i for i, e in enumerate(expected) if e["group"] == gi][0]]["target"]["fast"] if expected[[i for i, e in enumerate(expected) if e["group"] == gi][0]]["target"] and "fast" in expected[[i for i, e in enumerate(expected) if e["group"] == gi][0]]["target"] else None, "best": fmt_pace(min(paces_r)), "worst": fmt_pace(max(paces_r)),
                                 "fade": fade, "hr_last": measured[-1]["hr"]})

    # --- FC sur les répétitions au seuil (garde-fou)
    z4 = hr_zone_bounds(plan, 4)
    if z4:
        thr = [s for s, e in zip(rev["segments"], expected) if e["zone"] in ("SEUIL", "SEUILC") and e["kind"] == "run" and s["hr"]]
        over = [s for s in thr if s["hr"] > z4[1]]
        if thr and len(over) >= max(1, len(thr) / 2):
            penalty += 8
            rev["warnings"].append(f"FC au-dessus de la zone seuil ({z4[0]}-{z4[1]}) sur {len(over)}/{len(thr)} répétitions "
                                   f"(jusqu'à {max(s['hr'] for s in over)} bpm) : c'était plus proche du VO2max que du seuil.")

    # --- volume
    ratio = done_m / planned_m if planned_m else 1
    if ratio < 0.9:
        penalty += (0.9 - ratio) * 80
    elif ratio > 1.5:
        penalty += 20
    elif ratio > 1.2:
        penalty += 5

    # --- FC en endurance
    easy_segs = [s for s, e in zip(rev["segments"], expected) if e["zone"] in EASY_ZONES and s["hr"] and e["kind"] == "run"]
    if z2 and easy_segs:
        over = [s for s in easy_segs if s["hr"] > z2[1] + 2]
        if over:
            penalty += 12
            rev["warnings"].append(f"FC au-dessus de la Z2 ({z2[0]}-{z2[1]}) sur la partie endurance : {', '.join(str(s['hr']) for s in over[:3])} bpm. Sur l'EF, c'est la FC qui prime : ralentis.")

    # --- dérive cardiaque (sorties longues / EF de plus de 35 min)
    ef_fast = W.pace_to_sec(paces["EF"][1]) - 15 if paces.get("EF") else None
    if session.get("type") in ("EF", "SL") or done_s >= 60 * 60:
        rev["drift"] = _drift(laps, ef_fast)

    score = max(0, min(100, round(100 - penalty)))
    rev["score"] = score
    q_segs = [s for s, e in zip(rev["segments"], expected) if e["quality"] and e["kind"] == "run"]
    if q_segs and all(s["status"] == "na" for s in q_segs):
        rev["score"], rev["verdict"], rev["color"] = None, "Partie qualité non mesurable", "muted"
        _write_comments(rev, session, expected, ratio, z2)
        if not rev["intervals"]:
            rev["comments"].insert(0, "La sortie n'a pas un tour par étape : impossible de vérifier les allures du fractionné. "
                                      "Lance la séance depuis la montre (Entraînement → Mes entraînements) pour un bilan complet.")
        return rev
    if score >= 85:
        rev["verdict"], rev["color"] = "Séance parfaitement exécutée", "good"
    elif score >= 70:
        rev["verdict"], rev["color"] = "Bonne séance", "good"
    elif score >= 50:
        rev["verdict"], rev["color"] = "Séance correcte, avec des écarts", "warn"
    else:
        rev["verdict"], rev["color"] = "Séance loin du plan", "bad"

    _write_comments(rev, session, expected, ratio, z2)
    return rev


def _write_comments(rev: dict, session: dict, expected: list[dict], ratio: float, z2) -> None:
    c, tip = rev["comments"], None
    km_d, km_p = rev["km_done"], rev["km_planned"]
    if ratio < 0.9:
        c.append(f"Volume en dessous du prévu : {fr(km_d)} km sur {fr(km_p)} km.")
    elif ratio > 1.2:
        c.append(f"Tu as couru plus que prévu ({fr(km_d)} km pour {fr(km_p)}). Attention à ne pas grignoter la récup.")
    else:
        c.append(f"Volume respecté : {fr(km_d)} km.")

    for it in rev["intervals"]:
        if not it.get("measured"):
            c.append(f"{it['reps']} répétitions ({it['label']}) : pas de tour par répétition, impossible de les juger une par une. Lance la séance depuis la montre (Entraînements) pour un bilan précis.")
            continue
        s = f"Fractionné {it['label'].replace('Course ', '')} : {it['in_range']}/{it['measured']} dans la cible ({it['target']}), moyenne {it['avg_pace']}/km."
        if it["fast"] >= max(2, it["measured"] / 2):
            s += " Trop rapide sur la majorité des répétitions."
            tip = f"Sur ta prochaine séance de ce type, cale-toi sur la borne lente ({it['target'].split('–')[0]}/km) : l'objectif est la durée à l'allure, pas la vitesse."
        elif it["slow"] >= max(2, it["measured"] / 2):
            s += " Plutôt en dessous de l'allure visée."
            tip = "Si les sensations étaient mauvaises, regarde ton feu du matin et ta récup : ce n'est pas forcément un problème de forme."
        elif it.get("fast_s") and it["avg_s"] < it["fast_s"]:
            s += f" Moyenne plus rapide que la fourchette : sur les prochaines, vise le milieu ({fmt_pace(it['fast_s'] + 5)}/km)."
        if it.get("fade") is not None and it["fade"] >= 8:
            s += f" La dernière répétition est {it['fade']} s/km plus lente que la première : fatigue en fin de séance."
        elif it.get("fade") is not None and it["fade"] <= -8:
            s += " Tu as accéléré au fil des répétitions : départ peut-être trop prudent, ou belle gestion."
        c.append(s)

    # segments longs à allure spécifique (AM, seuil continu, perso)
    for seg, e in zip(rev["segments"], expected):
        if e["group"] is None and e["quality"] and e["planned_m"] >= 3000 and seg["pace"]:
            word = {"ok": "dans la cible", "fast": f"trop rapide de {seg['delta']} s/km", "slow": f"trop lent de {seg['delta']} s/km"}.get(seg["status"], "")
            hr = f", FC moy {seg['hr']}" if seg["hr"] else ""
            c.append(f"{seg['label']} : {seg['pace']}/km {word}{hr}{' (estimé avec les tours au km)' if seg['approx'] else ''}.")
            if seg["status"] == "fast" and not tip:
                tip = "Sur les blocs à allure marathon, l'enjeu est la régularité : mieux vaut être pile dans la fourchette que 5 s/km trop vite."

    easy = [(s, e) for s, e in zip(rev["segments"], expected) if e["zone"] in EASY_ZONES and e["kind"] == "run" and s["pace"]]
    if easy and not any(e["quality"] for e in expected):
        fast = [s for s, _ in easy if s["status"] == "fast"]
        if fast:
            c.append(f"Endurance un peu rapide ({fast[0]['pace']}/km pour {fast[0]['target']}). En EF, plus lent = mieux pour encaisser le volume.")
        else:
            c.append("Allure d'endurance bien respectée.")

    d = rev.get("drift")
    if d is not None:
        if d < 3.5:
            c.append(f"Dérive cardiaque {fr(d)} % : excellente endurance, la FC est restée stable à allure égale.")
        elif d < 5:
            c.append(f"Dérive cardiaque {fr(d)} % : bonne endurance.")
        elif d < 8:
            c.append(f"Dérive cardiaque {fr(d)} % : la FC grimpe au fil de la sortie. Normal en fin de grosse semaine, à surveiller si ça se répète.")
        else:
            c.append(f"Dérive cardiaque {fr(d)} % : forte. Chaleur, déshydratation, fatigue ou allure trop ambitieuse ?")
            tip = tip or "Pense à boire pendant les sorties de plus d'1h et vérifie ton sommeil des derniers jours."
    rev["comments"] = c + rev["warnings"]
    rev["tip"] = tip


# =====================================================================================
#  FEU DU MATIN
# =====================================================================================
def is_quality(session: dict | None, paces: dict) -> bool:
    if not session:
        return False
    if session.get("type") in ("SEUIL", "VMA", "AM", "SEMI", "COURSE"):
        return True
    return any(e["quality"] for e in flatten(session.get("steps", []), paces))


def morning_light(today: dict, trends: list[dict], session: dict | None, plan: dict, sleep_goal_h: float = 7.5) -> dict:
    m = (today or {}).get("metrics", {}) or {}
    st = (today or {}).get("status", {}) or {}
    rd = (today or {}).get("readiness", {}) or {}
    reasons: list[dict] = []
    if not m.get("sleep_s") and not m.get("hrv"):
        return {"color": "unknown", "title": "Feu du matin en attente", "reasons": [],
                "advice": "Il se calcule à partir de ta nuit : synchronise ta montre au réveil (ouvre Garmin Connect sur ton téléphone), puis rafraîchis.",
                "actions": [], "session_id": session.get("id") if session else None}

    def add(label, value, level, weight=1.0, detail=""):
        reasons.append({"label": label, "value": value, "level": level, "weight": weight, "detail": detail})

    # VFC
    hrv, lo, hi = m.get("hrv"), m.get("hrv_baseline_low"), m.get("hrv_baseline_high")
    if hrv:
        if lo and hrv < lo * 0.9:
            add("VFC", f"{hrv} ms", 2, 1.5, f"nettement sous ta zone habituelle ({lo}-{hi})")
        elif lo and hrv < lo:
            add("VFC", f"{hrv} ms", 1, 1.5, f"sous ta zone habituelle ({lo}-{hi})")
        elif m.get("hrv_status") in ("LOW", "POOR"):
            add("VFC", f"{hrv} ms", 2, 1.5, "statut Garmin bas")
        elif m.get("hrv_status") == "UNBALANCED":
            add("VFC", f"{hrv} ms", 1, 1.5, "statut déséquilibré")
        else:
            add("VFC", f"{hrv} ms", 0, 1.5, f"dans ta zone ({lo}-{hi})" if lo else "normale")

    # FC repos vs moyenne 7 j
    prev = [t["rhr"] for t in trends[-8:-1] if t.get("rhr")]
    rhr = m.get("rhr")
    if rhr and len(prev) >= 3:
        base = mean(prev)
        dlt = rhr - base
        lvl = 0 if dlt <= 2 else (1 if dlt <= 5 else 2)
        add("FC repos", f"{rhr} bpm", lvl, 1.3, f"{'+' if dlt >= 0 else ''}{dlt:.0f} vs ta moyenne 7 j ({base:.0f})")

    # Sommeil
    sc, sl = m.get("sleep_score"), m.get("sleep_s")
    if sc or sl:
        h = (sl or 0) / 3600
        if (sc and sc < 55) or (sl and h < 5):
            lvl = 2
        elif (sc and sc < 70) or (sl and h < 6.5):
            lvl = 1
        else:
            lvl = 0
        add("Sommeil", f"{sc or '—'}" + (f" · {int(h)}h{int((h % 1) * 60):02d}" if sl else ""), lvl, 1.0,
            "" if lvl == 0 else ("nuit courte" if sl and h < 6.5 else "qualité moyenne"))

    # Dette de sommeil sur les 3 dernières nuits
    l3 = [t["sleep_s"] / 3600 for t in trends[-3:] if t.get("sleep_s")]
    if len(l3) >= 2:
        debt = sum(max(0.0, sleep_goal_h - h) for h in l3)
        if debt > 3:
            add("Dette de sommeil", f"{fr(debt)} h", 2 if debt > 5 else 1, 1.0,
                f"{fr(debt)} h manquantes sur {len(l3)} nuits (objectif {fr(sleep_goal_h, 1)} h)")

    # Body Battery
    bb = m.get("bb_high")
    if bb is not None:
        add("Body Battery", str(bb), 0 if bb >= 60 else (1 if bb >= 40 else 2), 0.8)

    # Disponibilité Garmin
    if rd.get("score") is not None:
        s = rd["score"]
        add("Disponibilité", str(s), 0 if s >= 60 else (1 if s >= 35 else 2), 0.8)

    # Ratio de charge
    acwr = st.get("acwr")
    if acwr:
        add("Charge 7 j / 28 j", fr(acwr), 0 if acwr <= 1.3 else (1 if acwr <= 1.5 else 2), 0.8,
            "charge récente élevée" if acwr > 1.3 else "équilibrée")

    if not reasons:
        return {"color": "unknown", "title": "Pas encore de données ce matin", "reasons": [],
                "advice": "Synchronise ta montre (ouvre Garmin Connect sur ton téléphone) puis rafraîchis.", "actions": []}

    score = sum(r["level"] * r["weight"] for r in reasons)
    hard_red = any(r["level"] == 2 and r["label"] in ("VFC", "FC repos") for r in reasons)
    if hard_red or score >= 4:
        color = "red"
    elif score >= 1.8 or any(r["level"] == 2 for r in reasons):
        color = "orange"
    else:
        color = "green"

    q = is_quality(session, plan["paces"])
    rest_day = not session or session.get("type") in ("REPOS", "RENFO")
    race = session and session.get("type") == "COURSE"
    adjusted = bool(session and session.get("original"))
    actions: list[dict] = []
    if race:
        title = {"green": "Feu vert", "orange": "Feu orange", "red": "Feu rouge"}[color]
        advice = "Jour de course : ne change rien. Pars prudemment et laisse les sensations décider sur la deuxième moitié."
    elif rest_day:
        title = {"green": "Feu vert", "orange": "Feu orange", "red": "Feu rouge"}[color]
        advice = {"green": "Jour de repos prévu : profites-en pour bien récupérer.",
                  "orange": "Jour de repos : bonne nouvelle, ton corps en a besoin.",
                  "red": "Jour de repos, et c'est mérité. Dors bien ce soir et surveille demain matin."}[color]
    elif color == "green":
        title, advice = "Feu vert", "Tous les voyants sont bons : séance maintenue telle que prévue."
    elif color == "orange":
        title = "Feu orange"
        if q:
            advice = "Récupération incomplète. Tu peux faire la séance en restant sur la borne lente, ou l'alléger d'un tiers."
            actions = [{"id": "lighten", "label": "Alléger la séance"}, {"id": "swap_next", "label": "Décaler à demain"}]
        else:
            advice = "Récupération incomplète : reste en bas de zone, voire raccourcis un peu."
            actions = [{"id": "shorten", "label": "Raccourcir de 25 %"}]
    else:
        title = "Feu rouge"
        if q:
            advice = "Plusieurs signaux de fatigue. Pas de qualité aujourd'hui : footing facile ou repos, et on décale la séance clé."
            actions = [{"id": "easy", "label": "Transformer en footing facile"}, {"id": "swap_next", "label": "Décaler à demain"}, {"id": "rest", "label": "Repos"}]
        else:
            advice = "Plusieurs signaux de fatigue : raccourcis franchement en Z1, ou prends ta journée."
            actions = [{"id": "shorten", "label": "Raccourcir de 25 %"}, {"id": "rest", "label": "Repos"}]
    if session and session.get("activities") and not race:
        actions = []
        advice = {"green": "Séance du jour déjà faite. Bonne récup !",
                  "orange": "Séance du jour déjà faite. Ce soir : hydratation, repas complet et coucher tôt.",
                  "red": "Séance du jour déjà faite, mais tes voyants sont dans le rouge : priorité absolue à la récup ce soir."}[color]
    elif adjusted:
        actions = [{"id": "undo", "label": "Annuler l'ajustement"}]
    return {"color": color, "title": title, "advice": advice, "reasons": reasons, "actions": actions,
            "session_id": session.get("id") if session else None, "quality": q, "adjusted": adjusted}


# =====================================================================================
#  AJUSTEMENTS
# =====================================================================================
def _round_km(m: float) -> int:
    return max(500, int(round(m / 500.0)) * 500)


def _scale_steps(steps: list[dict], f: float, only_quality: bool, paces: dict) -> list[dict]:
    out = copy.deepcopy(steps)
    for st in out:
        if st.get("kind") == "repeat":
            if not only_quality or any(((s.get("target") or {}).get("pace") in QUALITY_ZONES) or (s.get("target") or {}).get("from") for s in st.get("steps", [])):
                st["times"] = max(1, round(st["times"] * f))
            continue
        tg = st.get("target") or {}
        q = tg.get("pace") in QUALITY_ZONES or bool(tg.get("from"))
        if only_quality and not q:
            continue
        d = st.get("dur") or {}
        if d.get("type") == "distance" and d["value"] >= 1000:
            d["value"] = _round_km(d["value"] * f)
        elif d.get("type") == "time" and d["value"] >= 120:
            d["value"] = int(round(d["value"] * f / 30) * 30)
    return out


def adjust(session: dict, action: str, paces: dict) -> dict:
    """Retourne la séance modifiée (sans toucher à la date). L'original est conservé dans session['original']."""
    s = copy.deepcopy(session)
    if action != "undo" and not s.get("original"):
        s["original"] = {k: copy.deepcopy(s.get(k)) for k in ("type", "title", "steps", "description", "date")}
    if action == "lighten":
        s["steps"] = _scale_steps(s["steps"], 2 / 3, True, paces)
        s["title"] = s["title"] + " (allégée)"
    elif action == "shorten":
        s["steps"] = _scale_steps(s["steps"], 0.75, False, paces)
        s["title"] = s["title"] + " (raccourcie)"
    elif action == "easy":
        planned = W.estimate(s["steps"], paces)["meters"]
        s["steps"] = [{"kind": "run", "dur": {"type": "distance", "value": _round_km(planned * 0.6)}, "target": {"pace": "RECUP"}}]
        s["type"] = "EF"
        s["title"] = "Footing facile (adapté)"
    elif action == "rest":
        s["steps"] = []
        s["type"] = "REPOS"
        s["title"] = "Repos (adapté)"
    elif action == "undo" and s.get("original"):
        for k, v in s["original"].items():
            if k != "date":
                s[k] = v
        s.pop("original", None)
    s["adjusted_reason"] = None if action == "undo" else action
    return s
