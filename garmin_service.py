"""Accès à Garmin Connect (lib non officielle `garminconnect`) avec cache disque.

Les jetons de connexion sont stockés dans data/garmin_tokens.json (sur ton Mac uniquement).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("sub3.garmin")

RUN_TYPES = {"running", "track_running", "treadmill_running", "trail_running", "street_running", "indoor_running", "virtual_run"}


def find(obj: Any, key: str, default: Any = None) -> Any:
    """Cherche récursivement la première valeur non nulle pour `key`."""
    if isinstance(obj, dict):
        if obj.get(key) is not None:
            return obj[key]
        for v in obj.values():
            r = find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, key)
            if r is not None:
                return r
    return default


def simplify_activity(a: dict) -> dict:
    typ = (a.get("activityType") or {}).get("typeKey", "")
    dist = a.get("distance") or 0
    dur = a.get("movingDuration") or a.get("duration") or 0
    return {
        "id": a.get("activityId"),
        "name": a.get("activityName"),
        "type": typ,
        "is_run": typ in RUN_TYPES or "run" in typ,
        "start": a.get("startTimeLocal"),
        "date": (a.get("startTimeLocal") or "")[:10],
        "distance_km": round(dist / 1000, 2),
        "duration_s": round(dur),
        "pace_s": round(dur / (dist / 1000)) if dist > 100 else None,
        "avg_hr": a.get("averageHR"),
        "max_hr": a.get("maxHR"),
        "elev_gain": a.get("elevationGain"),
        "cadence": a.get("averageRunningCadenceInStepsPerMinute"),
        "training_load": a.get("activityTrainingLoad"),
        "aerobic_te": a.get("aerobicTrainingEffect"),
        "anaerobic_te": a.get("anaerobicTrainingEffect"),
        "te_label": a.get("trainingEffectLabel"),
        "vo2max": a.get("vO2MaxValue"),
        "calories": a.get("calories"),
        "event_type": (a.get("eventType") or {}).get("typeKey"),
    }


DAY_V = 3  # version du format des journées en cache


def _clock(ms):
    """Horodatage « local » Garmin (ms) → 'HH:MM'."""
    if not isinstance(ms, (int, float)):
        return None
    return datetime.utcfromtimestamp(ms / 1000).strftime("%H:%M")


def _f_to_c(t):
    """La météo des activités Garmin est renvoyée en °F."""
    return round((t - 32) * 5 / 9, 1) if isinstance(t, (int, float)) else None


class GarminService:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.cache_dir = data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token_path = data_dir / "garmin_tokens.json"
        self.api = None
        self.pending = None  # client en attente du code MFA
        self.name = None
        self.lock = threading.Lock()
        self.last_error = None

    # ---------- connexion ----------
    def try_resume(self) -> bool:
        from garminconnect import Garmin

        candidates = [self.token_path, Path.home() / ".garminconnect"]
        for c in candidates:
            if not c.exists():
                continue
            try:
                g = Garmin()
                g.login(str(c))
                self.api = g
                self.name = g.full_name or g.display_name
                if c != self.token_path:
                    g.client.dump(str(self.token_path))
                log.info("Connecté à Garmin via %s", c)
                return True
            except Exception as e:  # jetons expirés
                log.warning("Reprise de session impossible (%s): %s", c, e)
                self.last_error = str(e)
        return False

    def login(self, email: str, password: str) -> str:
        from garminconnect import Garmin

        g = Garmin(email, password, return_on_mfa=True)
        status, _ = g.login()
        if status == "needs_mfa":
            self.pending = g
            return "mfa"
        self._finish(g)
        return "ok"

    def submit_mfa(self, code: str) -> str:
        if not self.pending:
            raise RuntimeError("Aucune connexion en attente de code")
        self.pending.resume_login(None, code.strip())
        g, self.pending = self.pending, None
        self._finish(g)
        return "ok"

    def _finish(self, g) -> None:
        g.client.dump(str(self.token_path))
        if not self.try_resume():
            raise RuntimeError("Connexion réussie mais session impossible à recharger")

    def logout(self) -> None:
        self.api = None
        if self.token_path.exists():
            self.token_path.unlink()

    @property
    def connected(self) -> bool:
        return self.api is not None

    def _call(self, fn: str, *args, default=None, **kwargs):
        if not self.api:
            raise PermissionError("Garmin non connecté")
        try:
            return getattr(self.api, fn)(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            log.warning("%s%s: %s", fn, args, msg)
            if "401" in msg or "Unauthorized" in msg:
                # session expirée : on tente une reprise silencieuse une fois
                if self.try_resume():
                    try:
                        return getattr(self.api, fn)(*args, **kwargs)
                    except Exception:
                        pass
                self.api = None
                raise PermissionError("Session Garmin expirée")
            return default

    # ---------- cache ----------
    def _cache_get(self, key: str, ttl: float | None):
        p = self.cache_dir / f"{key}.json"
        if not p.exists():
            return None
        if ttl is not None and time.time() - p.stat().st_mtime > ttl:
            return None
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def _cache_set(self, key: str, value: Any) -> None:
        (self.cache_dir / f"{key}.json").write_text(json.dumps(value))

    def clear_cache(self, prefix: str = "") -> None:
        for p in self.cache_dir.glob(f"{prefix}*.json"):
            p.unlink()

    # ---------- activités ----------
    def activities(self, days: int = 120, force: bool = False) -> list[dict]:
        start = (date.today() - timedelta(days=days)).isoformat()
        cached = self._cache_get("activities", None)
        if cached and not force and cached.get("start", "9999") <= start and self._cache_get("activities", 180):
            return [a for a in cached["items"] if a["date"] >= start]
        items: dict[str, dict] = {}
        fetch_from = start
        if cached and cached.get("start", "9999") <= start:
            # rafraîchissement incrémental : seulement les 10 derniers jours
            items = {str(a["id"]): a for a in cached["items"]}
            fetch_from = (date.today() - timedelta(days=10)).isoformat()
        raw = self._call("get_activities_by_date", fetch_from, date.today().isoformat(), default=None)
        if raw is None and cached:
            return [a for a in cached["items"] if a["date"] >= start]
        for a in raw or []:
            s = simplify_activity(a)
            items[str(s["id"])] = s
        lst = sorted(items.values(), key=lambda a: a["start"] or "", reverse=True)
        keep_start = min(start, cached.get("start", start)) if cached and fetch_from != start else start
        self._cache_set("activities", {"start": keep_start, "items": lst})
        return [a for a in lst if a["date"] >= start]

    def activity_detail(self, aid: str) -> dict:
        key = f"act_{aid}"
        c = self._cache_get(key, None)
        if c:
            return c
        act = self._call("get_activity", aid, default={}) or {}
        splits = self._call("get_activity_splits", aid, default={}) or {}
        zones = self._call("get_activity_hr_in_timezones", aid, default=[]) or []
        weather = self._call("get_activity_weather", aid, default={}) or {}
        laps = []
        for l in splits.get("lapDTOs", []) or []:
            d = l.get("distance") or 0
            t = l.get("movingDuration") or l.get("duration") or 0
            laps.append({
                "n": l.get("lapIndex"),
                "distance_m": round(d),
                "duration_s": round(t),
                "pace_s": round(t / (d / 1000)) if d > 50 else None,
                "avg_hr": l.get("averageHR"),
                "max_hr": l.get("maxHR"),
                "cadence": l.get("averageRunCadence"),
                "elev_gain": l.get("elevationGain"),
                "intensity": l.get("intensityType"),
            })
        summary = act.get("summaryDTO", {}) if isinstance(act, dict) else {}
        res = {
            "id": aid,
            "name": act.get("activityName") if isinstance(act, dict) else None,
            "summary": {
                "distance_km": round((summary.get("distance") or 0) / 1000, 2),
                "duration_s": summary.get("movingDuration") or summary.get("duration"),
                "avg_hr": summary.get("averageHR"),
                "max_hr": summary.get("maxHR"),
                "cadence": summary.get("averageRunCadence"),
                "elev_gain": summary.get("elevationGain"),
                "training_load": summary.get("activityTrainingLoad"),
                "aerobic_te": summary.get("trainingEffect"),
                "anaerobic_te": summary.get("anaerobicTrainingEffect"),
                "stride_m": summary.get("strideLength"),
                "gct_ms": summary.get("groundContactTime"),
                "vert_osc_cm": summary.get("verticalOscillation"),
                "power": summary.get("averagePower"),
                "calories": summary.get("calories"),
            },
            "laps": laps,
            "hr_zones": [{"zone": z.get("zoneNumber"), "seconds": round(z.get("secsInZone") or 0), "low": z.get("zoneLowBoundary")} for z in zones] if isinstance(zones, list) else [],
            "weather": {"temp": _f_to_c(find(weather, "temp")), "humidity": find(weather, "relativeHumidity"), "desc": find(find(weather, "weatherTypeDTO", {}), "desc")},
        }
        if res["laps"]:
            self._cache_set(key, res)
        return res

    def activity_track(self, aid: str) -> dict:
        """Tracé GPS + FC + vitesse, sous-échantillonné (≤ 1500 points) pour la carte."""
        key = f"track_{aid}"
        c = self._cache_get(key, None)
        if c:
            return c
        det = self._call("get_activity_details", aid, 2000, 4000, default={}) or {}
        idx = {d.get("key"): d.get("metricsIndex") for d in det.get("metricDescriptors", []) or []}
        pts = []
        li, lo = idx.get("directLatitude"), idx.get("directLongitude")
        hi, si, di = idx.get("directHeartRate"), idx.get("directSpeed"), idx.get("sumDistance")
        if li is not None and lo is not None:
            for row in det.get("activityDetailMetrics", []) or []:
                m = row.get("metrics") or []
                try:
                    lat, lon = m[li], m[lo]
                except IndexError:
                    continue
                if lat is None or lon is None:
                    continue
                pts.append([round(lat, 6), round(lon, 6),
                            m[hi] if hi is not None and hi < len(m) else None,
                            round(m[si], 3) if si is not None and si < len(m) and m[si] is not None else None,
                            round(m[di]) if di is not None and di < len(m) and m[di] is not None else None])
        if not pts:
            for q in (find(det, "polyline") or []):
                if q.get("lat") is not None:
                    pts.append([round(q["lat"], 6), round(q["lon"], 6), None, q.get("speed"), q.get("distanceInMeters")])
        step = max(1, len(pts) // 1500)
        pts = pts[::step]
        res = {"id": aid, "points": pts, "fields": ["lat", "lon", "hr", "speed", "dist"]}
        if pts:
            self._cache_set(key, res)
        return res

    # ---------- forme / santé ----------
    def day_metrics(self, d: str) -> dict:
        is_today = d == date.today().isoformat()
        key = f"day_{d}"
        c = self._cache_get(key, 900 if is_today else None)
        old = (date.today() - date.fromisoformat(d)).days > 35
        if c and (c.get("v") == DAY_V or old or not self.connected):
            return c
        hrv = self._call("get_hrv_data", d, default={}) or {}
        sleep = self._call("get_sleep_data", d, default={}) or {}
        summ = self._call("get_user_summary", d, default={}) or {}
        sleep_dto = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
        res = {
            "date": d,
            "hrv": find(hrv, "lastNightAvg"),
            "hrv_weekly": find(hrv, "weeklyAvg"),
            "hrv_status": find(hrv, "status"),
            "hrv_baseline_low": find(hrv, "balancedLow"),
            "hrv_baseline_high": find(hrv, "balancedUpper"),
            "sleep_score": ((sleep_dto.get("sleepScores") or {}).get("overall") or {}).get("value"),
            "sleep_s": sleep_dto.get("sleepTimeSeconds"),
            "deep_s": sleep_dto.get("deepSleepSeconds"),
            "rem_s": sleep_dto.get("remSleepSeconds"),
            "rhr": summ.get("restingHeartRate"),
            "bb_high": summ.get("bodyBatteryHighestValue"),
            "bb_now": summ.get("bodyBatteryMostRecentValue"),
            "stress": summ.get("averageStressLevel"),
            "steps": summ.get("totalSteps"),
            "kcal_total": summ.get("totalKilocalories"),
            "kcal_active": summ.get("activeKilocalories"),
            "kcal_bmr": summ.get("bmrKilocalories"),
            "bed": _clock(sleep_dto.get("sleepStartTimestampLocal")),
            "wake": _clock(sleep_dto.get("sleepEndTimestampLocal")),
            "v": DAY_V,
        }
        if not is_today and c and all(res[k] is None for k in ("hrv", "rhr", "sleep_s")):
            return c  # Garmin n'a rien renvoyé (réseau ?) : on garde l'ancienne version
        if is_today or any(res[k] is not None for k in ("hrv", "rhr", "sleep_s")):
            self._cache_set(key, res)
        return res

    def consumed(self, d: str) -> float | None:
        """Calories mangées notées dans Garmin Connect (journal alimentaire) pour un jour."""
        age = (date.today() - date.fromisoformat(d)).days
        key = f"food_{d}"
        ttl = 600 if age <= 0 else 3600 if age <= 3 else None
        c = self._cache_get(key, ttl)
        if c is not None:
            return c.get("kcal")
        kcal = None
        summ = self._call("get_user_summary", d, default={}) or {}
        if summ.get("consumedKilocalories"):
            kcal = float(summ["consumedKilocalories"])
        else:
            log_ = self._call("get_nutrition_daily_food_log", d, default=None)
            if isinstance(log_, dict):
                meals = [find(m, "calories") for m in (log_.get("mealDetails") or [])]
                meals = [x for x in meals if isinstance(x, (int, float))]
                if meals:
                    kcal = float(sum(meals))
                else:
                    foods = [find(f, "calories") for f in (log_.get("loggedFoodsWithServingSizes") or [])]
                    foods = [x for x in foods if isinstance(x, (int, float))]
                    if foods:
                        kcal = float(sum(foods))
        if summ or kcal is not None:
            self._cache_set(key, {"kcal": kcal})
        return kcal

    def trends(self, days: int = 28) -> list[dict]:
        ds = [(date.today() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        with ThreadPoolExecutor(max_workers=5) as ex:
            return list(ex.map(self.day_metrics, ds))

    def today(self) -> dict:
        d = date.today().isoformat()
        c = self._cache_get("today", 600)
        if c and c.get("date") == d:
            return c
        ready = self._call("get_training_readiness", d, default=[]) or []
        if isinstance(ready, list) and ready:
            ready = ready[0]
        status = self._call("get_training_status", d, default={}) or {}
        if not find(status, "vo2MaxPreciseValue") and not find(status, "trainingStatusFeedbackPhrase"):
            # tôt le matin, Garmin n'a pas encore calculé le statut du jour : on prend celui de la veille
            hier = (date.today() - timedelta(days=1)).isoformat()
            status = self._call("get_training_status", hier, default={}) or status
        preds = self._call("get_race_predictions", default={}) or {}
        if isinstance(preds, list) and preds:
            preds = preds[-1]
        lt = self._call("get_lactate_threshold", default={}) or {}
        end = self._call("get_endurance_score", d, default={}) or {}
        phrase = find(status, "trainingStatusFeedbackPhrase")
        res = {
            "date": d,
            "readiness": {
                "score": find(ready, "score"),
                "level": find(ready, "level"),
                "feedback": find(ready, "feedbackShort"),
                "recovery_min": find(ready, "recoveryTime"),
            },
            "status": {
                "phrase": phrase,
                "vo2max": find(status, "vo2MaxPreciseValue") or find(status, "vo2MaxValue"),
                "acute": find(status, "dailyTrainingLoadAcute"),
                "chronic": find(status, "dailyTrainingLoadChronic"),
                "acwr": find(status, "dailyAcuteChronicWorkloadRatio"),
                "acwr_status": find(status, "acwrStatus"),
                "load_aero_low": find(status, "monthlyLoadAerobicLow"),
                "load_aero_high": find(status, "monthlyLoadAerobicHigh"),
                "load_anaerobic": find(status, "monthlyLoadAnaerobic"),
            },
            "predictions": {
                "5k": find(preds, "time5K"),
                "10k": find(preds, "time10K"),
                "half": find(preds, "timeHalfMarathon"),
                "marathon": find(preds, "timeMarathon"),
            },
            "lactate": {
                "hr": find(lt, "heartRate") or find(lt, "lactateThresholdHeartRate"),
                "speed": find(lt, "speed") or find(lt, "lactateThresholdSpeed"),
            },
            "endurance_score": find(end, "overallScore"),
            "metrics": self.day_metrics(d),
        }
        self._cache_set("today", res)
        return res

    # ---------- séances ----------
    def push_workout(self, workout_json: dict, on_date: str | None, replace_id: Any = None) -> dict:
        if replace_id:
            self._call("delete_workout", replace_id)
        res = self.api.upload_workout(workout_json) if self.api else None
        if not res:
            raise PermissionError("Garmin non connecté")
        wid = res.get("workoutId")
        sched = None
        if on_date:
            sched = self.api.schedule_workout(wid, on_date)
        return {"workout_id": wid, "schedule_id": find(sched, "workoutScheduleId"), "scheduled": on_date}

    def delete_workout(self, wid: Any) -> None:
        self._call("delete_workout", wid)

    def workouts(self) -> list[dict]:
        ws = self._call("get_workouts", default=[]) or []
        return [{"id": w.get("workoutId"), "name": w.get("workoutName"), "updated": w.get("updatedDate"),
                 "distance": w.get("estimatedDistanceInMeters"), "duration": w.get("estimatedDurationInSecs")} for w in ws]
