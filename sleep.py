"""Sommeil : objectif, dette, heure de coucher conseillée et lien avec la qualité des séances."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, median

FALL_ASLEEP_MIN = 15  # temps d'endormissement compté dans l'heure de coucher conseillée


def _min(hhmm: str | None, is_bed: bool = False) -> int | None:
    """'23:40' → minutes. Pour un coucher, les heures après minuit comptent comme +24 h."""
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    v = h * 60 + m
    if is_bed and h < 12:
        v += 24 * 60
    return v


def _fmt(mins: float | None) -> str | None:
    if mins is None:
        return None
    mins = int(round(mins)) % (24 * 60)
    return f"{mins // 60:02d}:{mins % 60:02d}"


def insights(trends: list[dict], sessions: list[dict], reviews: dict, goal_h: float = 7.5, today: date | None = None) -> dict:
    today = today or date.today()
    nights = [t for t in trends if t.get("sleep_s")]
    hours = {t["date"]: t["sleep_s"] / 3600 for t in nights}
    last = lambda n: [t for t in nights if (today - date.fromisoformat(t["date"])).days < n]

    def avg_h(n):
        v = [t["sleep_s"] / 3600 for t in last(n)]
        return round(mean(v), 2) if v else None

    l3 = last(3)
    debt3 = round(sum(max(0.0, goal_h - t["sleep_s"] / 3600) for t in l3), 1) if l3 else None
    short14 = sum(1 for t in last(14) if t["sleep_s"] < 6 * 3600)

    # réveil habituel (semaine / week-end) : la nuit du jour J se termine le matin de J
    wk = [_min(t.get("wake")) for t in last(21) if t.get("wake") and date.fromisoformat(t["date"]).weekday() < 5]
    we = [_min(t.get("wake")) for t in last(28) if t.get("wake") and date.fromisoformat(t["date"]).weekday() >= 5]
    wake_wk = median(wk) if len(wk) >= 3 else None
    wake_we = median(we) if len(we) >= 2 else wake_wk
    tomorrow = today + timedelta(days=1)
    wake_tomorrow = wake_we if tomorrow.weekday() >= 5 else wake_wk
    target_bed = wake_tomorrow - goal_h * 60 - FALL_ASLEEP_MIN if wake_tomorrow is not None else None
    if target_bed is not None and target_bed < 12 * 60:
        target_bed += 24 * 60  # même échelle que les couchers (après minuit = +24 h)
    beds = [_min(t.get("bed"), True) for t in last(7) if t.get("bed")]
    avg_bed = mean(beds) if beds else None

    # Lien sommeil de la nuit précédente ↔ séances
    buckets = {"< 6 h": [], "6-7 h": [], "≥ 7 h": []}
    detail = []
    for s in sessions:
        if not s.get("activities") or s["date"] not in hours:
            continue
        h = hours[s["date"]]
        rv = (reviews.get(s["id"]) or {}).get("review") or {}
        b = "< 6 h" if h < 6 else ("6-7 h" if h < 7 else "≥ 7 h")
        item = {"date": s["date"], "title": s["title"], "type": s["type"], "sleep_h": round(h, 1),
                "score": rv.get("score"), "rpe": (s.get("feedback") or {}).get("rpe"),
                "hr": s["activities"][0].get("avg_hr") if s.get("activities") else None}
        buckets[b].append(item)
        detail.append(item)
    corr = []
    for b, items in buckets.items():
        sc = [i["score"] for i in items if i["score"] is not None]
        rp = [i["rpe"] for i in items if i["rpe"]]
        corr.append({"bucket": b, "n": len(items), "score": round(mean(sc)) if sc else None, "rpe": round(mean(rp), 1) if rp else None})

    a7 = avg_h(7)
    if a7 is None:
        message = "Pas encore de données de sommeil : porte ta montre la nuit."
    elif short14 >= 4:
        message = f"{short14} nuits de moins de 6 h sur 14 jours : c'est ton principal frein à la récupération en ce moment."
    elif a7 < goal_h - 0.5:
        message = f"Tu dors {str(round(a7, 1)).replace('.', ',')} h en moyenne sur 7 jours, pour un objectif de {str(goal_h).replace('.', ',')} h."
    else:
        message = "Sommeil dans l'objectif : continue comme ça, surtout avant les séances clés."

    series = [{"date": t["date"], "h": round(t["sleep_s"] / 3600, 2) if t.get("sleep_s") else None, "score": t.get("sleep_score"),
               "bed": t.get("bed"), "wake": t.get("wake")} for t in trends[-28:]]
    return {
        "goal_h": goal_h, "avg7_h": a7, "avg28_h": avg_h(28), "score7": round(mean([t["sleep_score"] for t in last(7) if t.get("sleep_score")]) ) if any(t.get("sleep_score") for t in last(7)) else None,
        "short14": short14, "debt3_h": debt3, "last_night_h": round(nights[-1]["sleep_s"] / 3600, 2) if nights and nights[-1]["date"] == today.isoformat() else None,
        "wake_weekday": _fmt(wake_wk), "wake_weekend": _fmt(wake_we), "target_bed": _fmt(target_bed),
        "avg_bed": _fmt(avg_bed), "bed_late_by_min": round(avg_bed - target_bed) if avg_bed is not None and target_bed is not None else None,
        "correlation": corr, "detail": sorted(detail, key=lambda x: x["date"], reverse=True)[:20],
        "series": series, "message": message,
    }
