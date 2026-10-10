"""Conversion des séances (format simple de l'app) vers le format JSON Garmin Connect.

Format d'une étape dans l'app :
  {"kind": "warmup"|"run"|"recovery"|"cooldown"|"rest",
   "dur": {"type": "time", "value": 600} | {"type": "distance", "value": 3000} | {"type": "lap"},
   "target": {"pace": "AM"} | {"from": "4:20", "to": "4:10"} | {"hr": 2} | None,
   "note": "texte libre (optionnel)"}
  {"kind": "repeat", "times": 5, "steps": [ ...étapes simples... ]}

Les allures sont exprimées en min:s par km. "pace": "AM" fait référence aux zones
définies dans le plan (plan["paces"]), ce qui permet de changer une allure partout.
"""
from __future__ import annotations

from typing import Any

STEP_TYPES = {
    "warmup": (1, "warmup"),
    "cooldown": (2, "cooldown"),
    "run": (3, "interval"),
    "recovery": (4, "recovery"),
    "rest": (5, "rest"),
}

KIND_LABELS = {
    "warmup": "Échauffement",
    "run": "Course",
    "recovery": "Récup",
    "cooldown": "Retour au calme",
    "rest": "Repos",
}


def pace_to_sec(p: str | int | float | None) -> float | None:
    """'4:15' -> 255 secondes par km."""
    if p is None or p == "":
        return None
    if isinstance(p, (int, float)):
        return float(p)
    p = str(p).strip().replace("'", ":").replace("’", ":").replace("/km", "")
    if ":" in p:
        m, s = p.split(":", 1)
        return int(m) * 60 + float(s or 0)
    return float(p) * 60


def sec_to_pace(sec: float | None) -> str:
    if not sec:
        return "—"
    sec = round(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def fmt_duration(sec: float | None) -> str:
    if sec is None:
        return "—"
    sec = int(round(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}" if h else f"{m}:{s:02d}"


def resolve_target(target: dict | None, paces: dict) -> dict | None:
    """Retourne {'slow': s/km, 'fast': s/km} ou {'hr': zone} ou None."""
    if not target:
        return None
    if "hr" in target and target["hr"]:
        return {"hr": int(target["hr"])}
    if target.get("pace"):
        rng = paces.get(target["pace"])
        if not rng:
            return None
        a, b = pace_to_sec(rng[0]), pace_to_sec(rng[1])
        return {"slow": max(a, b), "fast": min(a, b), "zone": target["pace"]}
    if target.get("from") and target.get("to"):
        a, b = pace_to_sec(target["from"]), pace_to_sec(target["to"])
        return {"slow": max(a, b), "fast": min(a, b)}
    return None


def _mid_pace(t: dict | None, paces: dict) -> float:
    """Allure moyenne utilisée pour estimer distance/durée d'une étape."""
    if t and "slow" in t:
        return (t["slow"] + t["fast"]) / 2
    ef = paces.get("EF") or ["5:30", "5:00"]
    return (pace_to_sec(ef[0]) + pace_to_sec(ef[1])) / 2


def estimate(steps: list[dict], paces: dict) -> dict:
    """Estime durée (s) et distance (m) totales d'une liste d'étapes."""
    total_t = 0.0
    total_d = 0.0
    for st in steps or []:
        if st.get("kind") == "repeat":
            sub = estimate(st.get("steps", []), paces)
            n = int(st.get("times", 1))
            total_t += sub["seconds"] * n
            total_d += sub["meters"] * n
            continue
        t = resolve_target(st.get("target"), paces)
        pace = _mid_pace(t, paces)
        dur = st.get("dur") or {}
        if st.get("kind") == "rest":
            total_t += float(dur.get("value") or 0) if dur.get("type") == "time" else 0
            continue
        if dur.get("type") == "distance":
            d = float(dur.get("value") or 0)
            total_d += d
            total_t += d / 1000 * pace
        elif dur.get("type") == "time":
            s = float(dur.get("value") or 0)
            total_t += s
            total_d += s / pace * 1000
    return {"seconds": round(total_t), "meters": round(total_d)}


def _end_condition(dur: dict) -> tuple[dict, float | None]:
    typ = (dur or {}).get("type", "lap")
    if typ == "time":
        return {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}, float(dur["value"])
    if typ == "distance":
        return {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}, float(dur["value"])
    return {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True}, None


def _exec_step(st: dict, order: int, paces: dict, child_id: int | None) -> dict:
    type_id, type_key = STEP_TYPES.get(st.get("kind", "run"), STEP_TYPES["run"])
    end, val = _end_condition(st.get("dur"))
    step: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key, "displayOrder": type_id},
        "endCondition": end,
        "endConditionValue": val,
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
    }
    if st.get("dur", {}).get("type") == "distance":
        step["preferredEndConditionUnit"] = {"unitKey": "kilometer"}
    if child_id is not None:
        step["childStepId"] = child_id
    t = resolve_target(st.get("target"), paces)
    if t and "hr" in t:
        step["targetType"] = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}
        step["zoneNumber"] = t["hr"]
    elif t and "slow" in t:
        step["targetType"] = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}
        # Garmin attend des vitesses en m/s : valeur 1 = la plus lente, valeur 2 = la plus rapide
        step["targetValueOne"] = round(1000 / t["slow"], 4)
        step["targetValueTwo"] = round(1000 / t["fast"], 4)
    if st.get("note"):
        step["description"] = str(st["note"])[:500]
    return step


def to_garmin(name: str, steps: list[dict], paces: dict, description: str = "") -> dict:
    """Construit le JSON de séance accepté par l'API workout-service de Garmin."""
    order = 0
    child_counter = 0
    out: list[dict] = []
    for st in steps or []:
        if st.get("kind") == "repeat":
            order += 1
            child_counter += 1
            group_order = order
            children = []
            for sub in st.get("steps", []):
                order += 1
                children.append(_exec_step(sub, order, paces, child_counter))
            n = int(st.get("times", 1))
            out.append({
                "type": "RepeatGroupDTO",
                "stepOrder": group_order,
                "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                "childStepId": child_counter,
                "numberOfIterations": n,
                "smartRepeat": False,
                "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
                "endConditionValue": float(n),
                "workoutSteps": children,
            })
        else:
            order += 1
            out.append(_exec_step(st, order, paces, None))
    est = estimate(steps, paces)
    sport = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
    return {
        "workoutName": name[:80],
        "description": (description or "")[:1000],
        "sportType": sport,
        "estimatedDurationInSecs": est["seconds"],
        "estimatedDistanceInMeters": est["meters"],
        "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": out}],
    }


def describe(steps: list[dict], paces: dict) -> str:
    """Résumé lisible : '3 km EF + 3 × (3 km AM / 2:00 récup) + 2 km EF'."""
    def one(st: dict) -> str:
        dur = st.get("dur") or {}
        if dur.get("type") == "distance":
            v = dur["value"]
            d = f"{v/1000:g} km" if v >= 1000 else f"{v:g} m"
        elif dur.get("type") == "time":
            d = fmt_duration(dur["value"])
        else:
            d = "lap"
        tg = st.get("target") or {}
        if tg.get("pace"):
            d += f" {tg['pace']}"
        elif tg.get("from"):
            d += f" @{tg['from']}-{tg['to']}"
        elif tg.get("hr"):
            d += f" Z{tg['hr']}"
        if st.get("kind") in ("recovery", "rest"):
            d += " récup"
        return d

    parts = []
    for st in steps or []:
        if st.get("kind") == "repeat":
            parts.append(f"{st.get('times')} × ({' / '.join(one(s) for s in st.get('steps', []))})")
        else:
            parts.append(one(st))
    return " + ".join(parts)
