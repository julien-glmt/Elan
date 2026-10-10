"""Données simulées pour tester l'app sans compte Garmin (SUB3_DEMO=1)."""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

from garmin_service import GarminService


class DemoService(GarminService):
    def __init__(self, data_dir):
        super().__init__(data_dir)
        self.api = object()
        self.name = "Athlète (démo)"
        self.pushed = []
        rnd = random.Random(42)
        self._acts = []
        today = date.today()
        aid = 1000
        for i in range(140, 0, -1):
            d = today - timedelta(days=i - 1)
            wd = d.weekday()
            if wd in (0, 4) and rnd.random() < 0.8:
                continue
            build = 1 + (140 - i) / 140 * 0.4
            if wd == 6:
                dist, pace, hr, name = rnd.uniform(16, 26) * build / 1.2, rnd.uniform(305, 320), rnd.randint(140, 150), "Sortie longue"
            elif wd == 1:
                dist, pace, hr, name = rnd.uniform(11, 14), rnd.uniform(270, 285), rnd.randint(155, 165), "Seuil"
            else:
                dist, pace, hr, name = rnd.uniform(7, 11), rnd.uniform(300, 318), rnd.randint(136, 146), "Footing"
            aid += 1
            dur = dist * pace
            self._acts.append({
                "id": aid, "name": name, "type": "running", "is_run": True,
                "start": f"{d.isoformat()} 12:30:00", "date": d.isoformat(),
                "distance_km": round(dist, 2), "duration_s": round(dur), "pace_s": round(pace),
                "avg_hr": hr, "max_hr": hr + 18, "elev_gain": rnd.randint(10, 60), "cadence": rnd.randint(166, 176),
                "training_load": round(dur / 60 * (hr - 100) / 25), "aerobic_te": round(rnd.uniform(2.5, 4.2), 1),
                "anaerobic_te": round(rnd.uniform(0, 2), 1), "te_label": "TEMPO" if name == "Seuil" else "AEROBIC_BASE",
                "vo2max": 58, "calories": round(dist * 62), "event_type": "training",
            })
        # À partir du début du plan : des sorties qui suivent les séances prévues (tours par étape)
        import json as _j
        from pathlib import Path as _P
        import coach as _c
        plan = _j.loads((_P(__file__).with_name("plan_initial.json")).read_text())
        self._laps = {}
        by_date = {s["date"]: s for s in plan["sessions"] if s.get("steps")}
        self._acts = [a for a in self._acts if a["date"] not in by_date]
        hr_by_zone = {"EF": 146, "RECUP": 140, "AM": 162, "SEUIL": 172, "SEUILC": 168, "VMA": 178, "PERSO": 160, None: 150}
        for d, s in by_date.items():
            if d > today.isoformat():
                continue
            aid += 1
            laps, n = [], 0
            for e in _c.flatten(s["steps"], plan["paces"]):
                t = e["target"]
                if t and "slow" in t:
                    p = rnd.uniform(t["fast"] - 6, t["slow"] + 2)
                else:
                    p = 600 if e["kind"] == "recovery" else 310
                dist = e["planned_m"] if e["dur"].get("type") == "distance" else (e["planned_s"] / p * 1000)
                secs_ = e["planned_s"] if e["dur"].get("type") == "time" else dist / 1000 * p
                n += 1
                laps.append({"n": n, "distance_m": round(dist), "duration_s": round(secs_), "pace_s": round(secs_ / (dist / 1000)) if dist > 50 else None,
                             "avg_hr": hr_by_zone.get(e["zone"], 150) + rnd.randint(-3, 4) + (n // 6), "max_hr": None, "cadence": 172, "elev_gain": 2})
            dist_t = sum(l["distance_m"] for l in laps)
            dur_t = sum(l["duration_s"] for l in laps)
            self._laps[aid] = laps
            self._acts.append({"id": aid, "name": s["title"], "type": "running", "is_run": True, "start": f"{d} 12:30:00", "date": d,
                               "distance_km": round(dist_t / 1000, 2), "duration_s": dur_t, "pace_s": round(dur_t / (dist_t / 1000)),
                               "avg_hr": 152, "max_hr": 175, "elev_gain": 30, "cadence": 172, "training_load": round(dur_t / 30),
                               "aerobic_te": 3.4, "anaerobic_te": 1.0, "te_label": "TEMPO", "vo2max": 58, "calories": round(dist_t / 16), "event_type": "training"})
        # une course (semi) marquée « course » dans Garmin, avec des tours de 1 km
        rd = "2026-09-13"
        if rd <= today.isoformat():
            self._acts = [a for a in self._acts if a["date"] != rd]
            aid += 1
            laps, tot = [], 0
            for k in range(22):
                dist = 1000 if k < 21 else 240
                p = 238 + (k - 14) * 1.6 if k > 14 else 238 + rnd.uniform(-3, 2) - (4 if k < 3 else 0)
                laps.append({"n": k + 1, "distance_m": dist, "duration_s": round(p * dist / 1000), "pace_s": round(p),
                             "avg_hr": 170 + k * 0.6, "max_hr": None, "cadence": 176, "elev_gain": rnd.randint(0, 12)})
                tot += round(p * dist / 1000)
            self._laps[aid] = laps
            self._acts.append({"id": aid, "name": "Pluneret Course", "type": "running", "is_run": True, "start": f"{rd} 10:00:00", "date": rd,
                               "distance_km": 21.24, "duration_s": tot, "pace_s": round(tot / 21.24), "avg_hr": 181, "max_hr": 192, "elev_gain": 165,
                               "cadence": 174, "training_load": 280, "aerobic_te": 5.0, "anaerobic_te": 1.4, "te_label": "VO2MAX", "vo2max": 59,
                               "calories": 1306, "event_type": "race"})
        self._acts.sort(key=lambda a: a["start"], reverse=True)

    def try_resume(self):
        return True

    def activities(self, days=120, force=False):
        start = (date.today() - timedelta(days=days)).isoformat()
        return [a for a in self._acts if a["date"] >= start]

    def activity_detail(self, aid):
        a = next((x for x in self._acts if str(x["id"]) == str(aid)), self._acts[0])
        rnd = random.Random(int(a["id"]))
        laps = []
        n = int(a["distance_km"])
        for k in range(n):
            p = a["pace_s"] + rnd.uniform(-8, 8)
            laps.append({"n": k + 1, "distance_m": 1000, "duration_s": round(p), "pace_s": round(p),
                         "avg_hr": a["avg_hr"] + round(k * 0.6) - 3, "max_hr": a["avg_hr"] + 8, "cadence": a["cadence"], "elev_gain": rnd.randint(0, 8)})
        tot = a["duration_s"]
        if a["id"] in getattr(self, "_laps", {}):
            laps = self._laps[a["id"]]
        return {"id": aid, "name": a["name"], "summary": {"distance_km": a["distance_km"], "duration_s": tot, "avg_hr": a["avg_hr"], "max_hr": a["max_hr"],
                "cadence": a["cadence"], "elev_gain": a["elev_gain"], "training_load": a["training_load"], "aerobic_te": a["aerobic_te"],
                "anaerobic_te": a["anaerobic_te"], "stride_m": 1.18, "gct_ms": 232, "vert_osc_cm": 8.4, "power": 312, "calories": a["calories"]},
                "laps": laps,
                "hr_zones": [{"zone": z, "seconds": round(tot * w), "low": b} for z, w, b in [(1, .05, 98), (2, .35, 118), (3, .4, 138), (4, .17, 158), (5, .03, 176)]],
                "weather": {"temp": 14, "humidity": 70, "desc": "Nuageux"}}

    def activity_track(self, aid):
        a = next((x for x in self._acts if str(x["id"]) == str(aid)), self._acts[0])
        rnd = random.Random(int(a["id"]))
        n = 600
        R = a["distance_km"] / (2 * math.pi) / 111.0
        pts = []
        for i in range(n):
            t = 2 * math.pi * i / n
            lat = 47.2063 + R * math.sin(t) * 0.9
            lon = -1.5536 + R * math.cos(t) * 1.4
            sp = 1000 / (a["pace_s"] + 18 * math.sin(3 * t) + rnd.uniform(-6, 6))
            hr = a["avg_hr"] + 8 * math.sin(2 * t) + i / n * 6
            pts.append([round(lat, 6), round(lon, 6), round(hr), round(sp, 3), round(a["distance_km"] * 1000 * i / n)])
        return {"id": aid, "points": pts, "fields": ["lat", "lon", "hr", "speed", "dist"]}

    def consumed(self, d):
        if d == date.today().isoformat():
            return 1240.0
        return float(random.Random(hash(d) % 1000).choice([1900, 2100, 2250, 2400, 2600, 2800, 3100]))

    def day_metrics(self, d):
        k = (date.fromisoformat(d) - date(2026, 1, 1)).days
        rnd = random.Random(k)
        return {"date": d, "hrv": round(68 + 6 * math.sin(k / 5) + rnd.uniform(-5, 5)), "hrv_weekly": 67, "hrv_status": "BALANCED",
                "hrv_baseline_low": 58, "hrv_baseline_high": 76, "sleep_score": rnd.randint(62, 90), "sleep_s": rnd.randint(22000, 29000),
                "deep_s": 5400, "rem_s": 6300, "rhr": rnd.randint(43, 48), "bb_high": rnd.randint(70, 98), "bb_now": rnd.randint(30, 80),
                "stress": rnd.randint(18, 32), "steps": rnd.randint(9000, 19000), "v": 3,
                "kcal_total": 2450 + round(sum(a["distance_km"] for a in self._acts if a["date"] == d) * 62) + rnd.randint(-120, 150),
                "kcal_bmr": 1610,
                "bed": rnd.choice(["22:40", "23:05", "23:30", "00:15", "01:10", "23:50"]),
                "wake": rnd.choice(["06:45", "07:00", "07:10", "06:30", "08:20"]),
                **({"sleep_score": 61, "sleep_s": 22300, "rhr": 50, "hrv": 61, "kcal_total": 1820} if d == date.today().isoformat() else {})}

    def today(self):
        d = date.today().isoformat()
        return {"date": d, "readiness": {"score": 48, "level": "MODERATE", "feedback": "WELL_RECOVERED", "recovery_min": 420},
                "status": {"phrase": "PRODUCTIVE_6", "vo2max": 58.4, "acute": 712, "chronic": 640, "acwr": 1.1, "acwr_status": "OPTIMAL",
                           "load_aero_low": 820, "load_aero_high": 640, "load_anaerobic": 180},
                "predictions": {"5k": 1080, "10k": 2265, "half": 5040, "marathon": 10690},
                "lactate": {"hr": 172, "speed": 0.39}, "endurance_score": 7350, "metrics": self.day_metrics(d)}

    def push_workout(self, workout_json, on_date, replace_id=None):
        wid = 900000 + len(self.pushed)
        self.pushed.append(workout_json)
        return {"workout_id": wid, "schedule_id": wid + 1, "scheduled": on_date}

    def delete_workout(self, wid):
        pass

    def workouts(self):
        return [{"id": 900000 + i, "name": w["workoutName"], "distance": w["estimatedDistanceInMeters"], "duration": w["estimatedDurationInSecs"]} for i, w in enumerate(self.pushed)]

    def login(self, email, password):
        return "ok"

    def logout(self):
        pass
