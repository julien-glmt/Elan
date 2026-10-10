"""Bilan de course : prévu vs réalisé, gestion de l'allure, cardio, ravitaillement, prépa, prédictions, leçons.

Tout est calculé à partir de l'activité Garmin de la course ; ton ressenti (notes, ce qui a marché, ce qu'il faut changer)
est stocké dans data/debriefs.json et sert ensuite au générateur de la prochaine prépa.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean


def _fmt(s: float | None) -> str | None:
    if s is None:
        return None
    s = int(round(s))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _pace(s: float | None) -> str | None:
    if not s:
        return None
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def hms(t: str) -> int | None:
    try:
        p = [int(x) for x in str(t).strip().split(":")]
        return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]
    except Exception:
        return None


# ------------------------------------------------------------------ découpage au kilomètre
def km_splits(laps: list[dict], track_pts: list[list], duration_s: float, distance_km: float) -> list[dict]:
    """Temps de passage kilomètre par kilomètre : tours automatiques de 1 km si dispo, sinon reconstruit depuis le GPS."""
    good = [l for l in laps if l.get("distance_m") and 950 <= l["distance_m"] <= 1050]
    if laps and len(good) >= 0.7 * max(1, len(laps) - 1):
        out, cum_d, cum_t = [], 0.0, 0.0
        for i, l in enumerate(laps):
            d, t = l.get("distance_m") or 0, l.get("duration_s") or 0
            if d < 30:
                continue
            cum_d += d
            cum_t += t
            out.append({"km": round(cum_d / 1000, 2), "dist_m": d, "time_s": t, "pace_s": round(t / (d / 1000)) if d else None,
                        "hr": l.get("avg_hr"), "cum_s": round(cum_t), "elev": l.get("elev_gain")})
        return out
    # reconstruction depuis le tracé : dt = Δdistance / vitesse, puis mise à l'échelle sur la durée réelle
    pts = [p for p in track_pts if p[4] is not None]
    if len(pts) > 20:
        seg = []
        for a, b in zip(pts, pts[1:]):
            dd = b[4] - a[4]
            v = ((a[3] or 0) + (b[3] or 0)) / 2
            if dd <= 0 or v <= 0.5:
                continue
            seg.append((b[4], dd / v, b[2]))
        tot = sum(s[1] for s in seg) or 1
        k = duration_s / tot if duration_s else 1
        out, t_acc, hr_acc, next_km, last_t = [], 0.0, [], 1000, 0.0
        for d, dt, hr in seg:
            t_acc += dt * k
            if hr:
                hr_acc.append(hr)
            if d >= next_km:
                st = t_acc - last_t
                out.append({"km": next_km / 1000, "dist_m": 1000, "time_s": round(st), "pace_s": round(st), "hr": round(mean(hr_acc)) if hr_acc else None,
                            "cum_s": round(t_acc), "elev": None})
                last_t, hr_acc, next_km = t_acc, [], next_km + 1000
        rest_d = distance_km * 1000 - (next_km - 1000)
        if rest_d > 50:
            st = (duration_s or t_acc) - last_t
            out.append({"km": round(distance_km, 2), "dist_m": round(rest_d), "time_s": round(st), "pace_s": round(st / (rest_d / 1000)),
                        "hr": round(mean(hr_acc)) if hr_acc else None, "cum_s": round(duration_s or t_acc), "elev": None})
        return out
    # dernier recours : les tours tels quels
    out, cum_d, cum_t = [], 0.0, 0.0
    for l in laps:
        d, t = l.get("distance_m") or 0, l.get("duration_s") or 0
        cum_d += d
        cum_t += t
        out.append({"km": round(cum_d / 1000, 2), "dist_m": d, "time_s": t, "pace_s": round(t / (d / 1000)) if d > 50 else None,
                    "hr": l.get("avg_hr"), "cum_s": round(cum_t), "elev": l.get("elev_gain")})
    return out


def _cum_at(splits: list[dict], km_: float) -> float | None:
    """Temps cumulé (s) interpolé au km donné."""
    prev_km, prev_t = 0.0, 0.0
    for s in splits:
        if s["km"] >= km_:
            f = (km_ - prev_km) / ((s["km"] - prev_km) or 1)
            return prev_t + f * (s["cum_s"] - prev_t)
        prev_km, prev_t = s["km"], s["cum_s"]
    return None


# ------------------------------------------------------------------ analyse
def analyse(*, act: dict, detail: dict, track: list, distance_km_race: float, goal_s: int | None, plan_rows: list[dict] | None,
            official_s: int | None, fuel: dict | None, plan_carbs_total: float | None, hr_zones_plan: list[dict] | None) -> dict:
    summ = detail.get("summary") or {}
    dist = float(summ.get("distance_km") or act.get("distance_km") or distance_km_race)
    watch_s = float(summ.get("duration_s") or act.get("duration_s") or 0)
    time_s = official_s or watch_s
    splits = km_splits(detail.get("laps") or [], track, watch_s, dist)

    # allure prévue au km
    ref_label = "plan de course"
    if plan_rows:
        plan_pace = {i + 1: r["pace_s"] for i, r in enumerate(plan_rows)}
        even = None
    else:
        even = (goal_s or watch_s) / dist  # sur la distance mesurée par la montre : l'écart final = écart réel
        plan_pace = {}
        ref_label = "allure objectif régulière" if goal_s else "allure moyenne"
    for i, s in enumerate(splits):
        n = i + 1
        pp = plan_pace.get(n) if plan_rows else even
        s["plan_pace_s"] = round(pp, 1) if pp else None
        s["delta_s"] = round(s["pace_s"] - pp, 1) if pp and s["pace_s"] else None

    # cumul vs plan par 5 km
    by5 = []
    plan_cum = 0.0
    plan_cum_at = {}
    for i, s in enumerate(splits):
        pp = s.get("plan_pace_s") or 0
        plan_cum += pp * (s["dist_m"] / 1000)
        plan_cum_at[s["km"]] = plan_cum
        s["plan_cum_s"] = round(plan_cum)
        s["gap_s"] = round(s["cum_s"] - plan_cum)
    marks = [k for k in range(5, int(dist) + 1, 5)] + [round(dist, 2)]
    prev_r, prev_p = 0.0, 0.0
    for m in marks:
        r = _cum_at(splits, m)
        p = None
        for s in splits:
            if s["km"] >= m:
                p = s["plan_cum_s"] - (s["km"] - m) * (s.get("plan_pace_s") or 0)
                break
        if r is None:
            continue
        seg_km = m - (by5[-1]["km"] if by5 else 0)
        by5.append({"km": m, "real_cum": _fmt(r), "real_cum_s": round(r), "plan_cum": _fmt(p) if p else None,
                    "gap_s": round(r - p) if p else None, "seg_pace": _pace((r - prev_r) / seg_km) if seg_km else None,
                    "plan_seg_pace": _pace((p - prev_p) / seg_km) if p and seg_km else None})
        prev_r, prev_p = r, p or prev_p

    # moitiés, régularité, décrochage
    half = dist / 2
    t_half = _cum_at(splits, half) or watch_s / 2
    first, second = t_half, watch_s - t_half
    split_pct = (second - first) / first * 100 if first else 0
    paces = [s["pace_s"] for s in splits if s["pace_s"] and s["dist_m"] >= 900]
    first_avg = mean(paces[: max(1, len(paces) // 2)]) if paces else None
    fade_km = None
    if paces and len(paces) >= 8:
        for i in range(len(paces) // 2, len(paces) - 2):
            if mean(paces[i:i + 3]) > first_avg * 1.05:
                fade_km = i + 1
                break
    start5 = mean(paces[:5]) if len(paces) >= 5 else None
    plan5 = mean([s["plan_pace_s"] for s in splits[:5] if s.get("plan_pace_s")] or [0]) or None
    hrs = [s["hr"] for s in splits if s.get("hr")]
    hr1 = mean(hrs[: len(hrs) // 2]) if len(hrs) > 3 else None
    hr2 = mean(hrs[len(hrs) // 2:]) if len(hrs) > 3 else None
    cv = (mean([(p - mean(paces)) ** 2 for p in paces]) ** 0.5 / mean(paces) * 100) if len(paces) > 3 else None

    # ravitaillement
    nut = None
    if fuel:
        nut = dict(fuel)
        if plan_carbs_total:
            nut["plan_carbs_total"] = round(plan_carbs_total)

    res = {
        "distance_km": round(dist, 2), "time_s": round(time_s), "time": _fmt(time_s), "watch_s": round(watch_s), "watch": _fmt(watch_s),
        "official": bool(official_s), "pace": _pace(time_s / distance_km_race), "avg_hr": summ.get("avg_hr") or act.get("avg_hr"),
        "max_hr": summ.get("max_hr") or act.get("max_hr"), "elev_gain": summ.get("elev_gain"), "cadence": summ.get("cadence"),
        "weather": detail.get("weather"), "hr_zones": detail.get("hr_zones"),
        "goal_s": goal_s, "goal": _fmt(goal_s) if goal_s else None, "gap_goal_s": round(time_s - goal_s) if goal_s else None,
        "splits": splits, "by5": by5, "ref_label": ref_label,
        "halves": {"first": _fmt(first), "second": _fmt(second), "first_s": round(first), "second_s": round(second), "split_pct": round(split_pct, 1)},
        "fade_km": fade_km, "start5_pace": _pace(start5), "plan5_pace": _pace(plan5),
        "start_delta_s": round(start5 - plan5, 1) if start5 and plan5 else None,
        "hr_first": round(hr1) if hr1 else None, "hr_second": round(hr2) if hr2 else None,
        "hr_drift_pct": round((hr2 - hr1) / hr1 * 100, 1) if hr1 and hr2 else None,
        "pace_cv": round(cv, 1) if cv else None,
        "nutrition": nut,
    }
    return res


# ------------------------------------------------------------------ prépa
def prep_recap(*, race_date: str, acts: list[dict], sessions: list[dict] | None, reviews: dict, sleep_days: list[dict],
               is_marathon: bool) -> dict:
    rd = date.fromisoformat(race_date)
    w16 = (rd - timedelta(weeks=16)).isoformat()
    runs = [a for a in acts if a.get("is_run") and w16 <= a["date"] < race_date and a.get("distance_km")]
    weeks: dict[str, float] = {}
    for a in runs:
        d = date.fromisoformat(a["date"])
        wk = (d - timedelta(days=d.weekday())).isoformat()
        weeks[wk] = weeks.get(wk, 0) + a["distance_km"]
    w8 = (rd - timedelta(weeks=8)).isoformat()
    km8 = sum(a["distance_km"] for a in runs if a["date"] >= w8)
    out = {
        "weeks": [{"start": k, "km": round(v, 1)} for k, v in sorted(weeks.items())],
        "total_km": round(sum(a["distance_km"] for a in runs)),
        "runs": len(runs),
        "peak_week_km": round(max(weeks.values()), 1) if weeks else None,
        "avg8_km": round(km8 / 8, 1),
        "longest_km": round(max((a["distance_km"] for a in runs), default=0), 1),
        "long_28": sum(1 for a in runs if a["distance_km"] >= 28) if is_marathon else None,
    }
    if sessions:
        past = [s for s in sessions if s["date"] < race_date and s["type"] not in ("REPOS", "COURSE")]
        done = [s for s in past if s.get("status") in ("done", "partial")]
        out["sessions_planned"] = len(past)
        out["sessions_done"] = len(done)
        out["adherence_pct"] = round(len(done) / len(past) * 100) if past else None
        key = [s for s in past if s["type"] in ("SEUIL", "AM", "VMA", "SEMI")]
        scores = [(reviews.get(s["id"]) or {}).get("review", {}).get("score") for s in key]
        scores = [x for x in scores if x is not None]
        out["key_sessions"] = len(key)
        out["key_score_avg"] = round(mean(scores)) if scores else None
        fast = 0
        for s in key:
            rv = (reviews.get(s["id"]) or {}).get("review") or {}
            if sum(1 for g in rv.get("segments", []) if g.get("status") == "fast" and g.get("kind") == "run") >= 2:
                fast += 1
        out["fast_quality"] = fast
    sl = [d.get("sleep_s") for d in sleep_days if d.get("sleep_s")]
    out["sleep_avg_h"] = round(mean(sl) / 3600, 1) if sl else None
    eve = next((d for d in sleep_days if d.get("date") == race_date), None)
    out["sleep_race_night_h"] = round(eve["sleep_s"] / 3600, 1) if eve and eve.get("sleep_s") else None
    return out


def prediction_check(history: list[dict], race_date: str, time_s: float) -> dict | None:
    before = [h for h in history if h["date"] <= race_date]
    if not before:
        return None
    h = before[-1]
    labels = {"estimate_s": "Prédiction maison (synthèse)", "riegel": "Riegel", "half211": "Semi × 2,11", "tanda": "Tanda (volume)",
              "mp_blocks": "Blocs allure marathon", "garmin": "Garmin"}
    rows = []
    for k, l in labels.items():
        if h.get(k):
            rows.append({"id": k, "label": l, "pred": _fmt(h[k]), "pred_s": h[k], "error_s": round(h[k] - time_s)})
    rows.sort(key=lambda r: abs(r["error_s"]))
    return {"date": h["date"], "rows": rows, "best": rows[0]["label"] if rows else None}


# ------------------------------------------------------------------ leçons
def _fr(x: float, nd: int = 1) -> str:
    return f"{x:+.{nd}f}".replace(".", ",")


def lessons(a: dict, prep: dict, pred: dict | None, is_marathon: bool) -> list[dict]:
    L = []
    ref_word = "prévu" if a.get("ref_label") == "plan de course" else ("ton allure objectif" if a.get("goal") else "ton allure moyenne")

    def add(kind, text, lid):
        L.append({"id": lid, "kind": kind, "text": text})

    if a.get("gap_goal_s") is not None:
        g = a["gap_goal_s"]
        if g <= 0:
            add("good", f"Objectif atteint avec {_fmt(-g)} d'avance.", "goal")
        else:
            add("warn", f"Objectif manqué de {_fmt(g)}.", "goal")
    sp = a["halves"]["split_pct"]
    if sp <= 0.5:
        add("good", f"Course bien gérée : 2e moitié {'plus rapide' if sp < 0 else 'au même rythme'} ({_fr(sp)} %).", "split")
    elif sp <= 3:
        add("warn", f"Léger ralentissement en 2e moitié ({_fr(sp)} %) : acceptable, à réduire.", "split")
    else:
        add("bad", f"Fort ralentissement en 2e moitié ({_fr(sp)} %)" + (f", décrochage vers le km {a['fade_km']}" if a.get("fade_km") else "")
            + ". Prochaine fois : départ plus prudent et plus de sorties longues à allure spécifique.", "split")
    if a.get("start_delta_s") is not None and a["start_delta_s"] < -3:
        add("bad" if sp > 2 else "warn", f"Départ trop rapide : {abs(a['start_delta_s']):.0f} s/km plus vite que {ref_word} sur les 5 premiers km.", "start")
    if a.get("hr_drift_pct") is not None and a["hr_drift_pct"] > 6:
        add("warn", f"Dérive cardiaque de {a['hr_drift_pct']:.0f} % entre les deux moitiés : hydratation, chaleur ou endurance spécifique à travailler.", "drift")
    n = a.get("nutrition") or {}
    if n.get("carbs_per_h") is not None:
        if n["carbs_per_h"] < 45 and is_marathon:
            add("bad", f"Ravitaillement trop faible : {n['carbs_per_h']} g/h. Vise 60-90 g/h en t'entraînant à les prendre.", "fuel")
        elif n["carbs_per_h"] >= 55:
            add("good", f"Ravitaillement solide : {n['carbs_per_h']} g/h.", "fuel")
    if prep.get("adherence_pct") is not None:
        if prep["adherence_pct"] >= 85:
            add("good", f"Prépa suivie à {prep['adherence_pct']} % : la régularité a payé.", "adh")
        elif prep["adherence_pct"] < 70:
            add("warn", f"Prépa suivie à {prep['adherence_pct']} % seulement : vise un plan plus réaliste avec ton emploi du temps.", "adh")
    if is_marathon and prep.get("avg8_km") and prep["avg8_km"] < 60:
        add("warn", f"Volume moyen de {prep['avg8_km']:.0f} km/semaine sur les 8 dernières semaines : monter vers 65-80 km est le levier principal.", "vol")
    if prep.get("fast_quality", 0) >= 2:
        add("warn", f"{prep['fast_quality']} séances de qualité courues trop vite : respecte les fourchettes, la progression vient de la régularité.", "fastq")
    if prep.get("sleep_avg_h") and prep["sleep_avg_h"] < 7:
        add("warn", f"Sommeil moyen de {str(prep['sleep_avg_h']).replace('.', ',')} h la dernière semaine : c'est le levier le plus simple.", "sleep")
    if pred and pred.get("rows"):
        b = pred["rows"][0]
        add("info", f"Méthode de prédiction la plus juste : {b['label']} ({b['pred']}, écart {'+' if b['error_s'] >= 0 else '−'}{_fmt(abs(b['error_s']))}).", "pred")
    return L


# ------------------------------------------------------------------ stockage
class DebriefStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "debriefs.json"
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def get(self, aid: str) -> dict:
        return self.load().get(str(aid), {})

    def save(self, aid: str, patch: dict) -> dict:
        with self.lock:
            d = self.load()
            cur = d.get(str(aid), {})
            cur.update(patch)
            cur["updated"] = datetime.now().isoformat(timespec="minutes")
            d[str(aid)] = cur
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
            tmp.replace(self.path)
            return cur

    def all(self) -> list[dict]:
        return [dict(v, aid=k) for k, v in self.load().items()]
