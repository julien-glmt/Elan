"""Coach IA de Sub3 — échange de fichiers avec la tâche planifiée Claude (Cowork).

Fonctionnement :
  1. Le serveur Sub3 écrit régulièrement data/coach/context.json (tout ce que le coach doit savoir).
  2. Une tâche Claude programmée (7h20 et 21h40) lit ce contexte + data/coach/questions.json
     et dépose ses messages dans data/coach/out/*.json (un fichier par message).
  3. Le serveur ingère ces fichiers dans data/coach/notes.json et les affiche dans l'app.
Aucune clé API : c'est ton abonnement Claude qui fait tourner la tâche.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

NOTE_TYPES = {"morning", "session", "weekly", "answer", "info"}
ACTIONS = {"update", "create", "delete"}


class CoachStore:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "coach"
        self.out = self.dir / "out"
        self.out.mkdir(parents=True, exist_ok=True)
        self.notes_path = self.dir / "notes.json"
        self.questions_path = self.dir / "questions.json"
        self.context_path = self.dir / "context.json"
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- io
    def _read(self, p: Path, default):
        try:
            return json.loads(p.read_text())
        except Exception:
            return default

    def _write(self, p: Path, data) -> None:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        tmp.replace(p)

    # ---------------------------------------------------------------- questions
    def questions(self) -> list[dict]:
        return self._read(self.questions_path, [])

    def ask(self, text: str, session_id: str | None = None) -> dict:
        with self.lock:
            qs = self.questions()
            q = {"id": "q" + uuid.uuid4().hex[:8], "text": text.strip()[:2000], "session_id": session_id,
                 "created_at": datetime.now().isoformat(timespec="minutes"), "answered": False}
            qs.append(q)
            self._write(self.questions_path, qs)
            return q

    def delete_question(self, qid: str) -> None:
        with self.lock:
            self._write(self.questions_path, [q for q in self.questions() if q["id"] != qid])

    # ---------------------------------------------------------------- notes
    def ingest(self) -> int:
        """Récupère les messages déposés par la tâche Claude dans out/."""
        files = sorted(self.out.glob("*.json"))
        if not files:
            return 0
        with self.lock:
            notes = self._read(self.notes_path, [])
            qs = self.questions()
            n = 0
            for f in files:
                try:
                    raw = json.loads(f.read_text())
                except Exception:
                    f.rename(f.with_suffix(".invalid"))
                    continue
                items = raw if isinstance(raw, list) else [raw]
                for it in items:
                    note = self._clean_note(it, f.stem)
                    if not note:
                        continue
                    notes.append(note)
                    n += 1
                    if note.get("question_id"):
                        for q in qs:
                            if q["id"] == note["question_id"]:
                                q["answered"] = True
                                q["answer_id"] = note["id"]
                f.unlink()
            notes.sort(key=lambda x: x["created_at"])
            self._write(self.notes_path, notes[-400:])
            self._write(self.questions_path, qs)
            return n

    def _clean_note(self, it: dict, stem: str) -> dict | None:
        if not isinstance(it, dict) or not it.get("body"):
            return None
        typ = it.get("type") if it.get("type") in NOTE_TYPES else "info"
        props = []
        for i, p in enumerate(it.get("proposals") or []):
            if not isinstance(p, dict) or p.get("action") not in ACTIONS:
                continue
            props.append({"pid": f"p{i + 1}", "action": p["action"], "session_id": p.get("session_id"),
                          "fields": p.get("fields") or {}, "reason": str(p.get("reason") or "")[:500], "status": "pending"})
        return {
            "id": "n" + uuid.uuid4().hex[:8], "type": typ, "date": str(it.get("date") or datetime.now().date().isoformat())[:10],
            "session_id": it.get("session_id"), "question_id": it.get("question_id"),
            "title": str(it.get("title") or "")[:200], "body": str(it["body"])[:8000], "proposals": props,
            "created_at": str(it.get("created_at") or datetime.now().isoformat(timespec="minutes")), "source": stem, "read": False,
        }

    def notes(self) -> list[dict]:
        self.ingest()
        return self._read(self.notes_path, [])

    def set_proposal_status(self, nid: str, pid: str, status: str) -> dict | None:
        with self.lock:
            notes = self._read(self.notes_path, [])
            for n in notes:
                if n["id"] == nid:
                    for p in n.get("proposals", []):
                        if p["pid"] == pid:
                            p["status"] = status
                            self._write(self.notes_path, notes)
                            return p
        return None

    def get_proposal(self, nid: str, pid: str) -> dict | None:
        for n in self._read(self.notes_path, []):
            if n["id"] == nid:
                return next((p for p in n.get("proposals", []) if p["pid"] == pid), None)
        return None

    def mark_read(self, ids: list[str]) -> None:
        with self.lock:
            notes = self._read(self.notes_path, [])
            for n in notes:
                if n["id"] in ids:
                    n["read"] = True
            self._write(self.notes_path, notes)

    # ---------------------------------------------------------------- contexte
    def write_context(self, ctx: dict) -> None:
        self._write(self.context_path, ctx)

    def context_age_min(self) -> float | None:
        if not self.context_path.exists():
            return None
        return (datetime.now().timestamp() - self.context_path.stat().st_mtime) / 60


def compact_review(rv: dict | None) -> dict | None:
    if not rv:
        return None
    keep = {k: rv.get(k) for k in ("score", "verdict", "km_done", "km_planned", "time_done", "avg_hr", "drift", "comments", "tip", "mode")}
    keep["intervals"] = rv.get("intervals")
    keep["segments"] = [{k: s.get(k) for k in ("label", "target", "pace", "hr", "status", "delta", "approx")}
                        for s in rv.get("segments", []) if s.get("kind") not in ("recovery", "rest")][:30]
    return keep


def build_context(*, plan: dict, sessions: list[dict], reviews: dict, trends: list[dict], today: dict, light: dict,
                  weekly: list[dict], race_summary: dict, questions: list[dict], notes: list[dict], today_iso: str,
                  athlete_extra: dict | None = None) -> dict:
    past = [s for s in sessions if s["date"] <= today_iso][-21:]
    future = [s for s in sessions if s["date"] > today_iso][:21]

    def sess(s, with_steps=False):
        d = {k: s.get(k) for k in ("id", "date", "type", "title", "description", "summary", "planned_km", "planned_s",
                                     "status", "done_km", "feedback", "adjusted_reason")}
        d["on_watch"] = bool(s.get("garmin_workout_id"))
        d["activities"] = [{k: a.get(k) for k in ("id", "name", "km", "pace_s", "avg_hr", "date")} for a in s.get("activities", [])]
        if with_steps:
            d["steps"] = s.get("steps")
        r = reviews.get(s["id"], {}).get("review") if reviews.get(s["id"]) else None
        if r and s.get("activities"):
            d["review"] = compact_review(r)
        return d

    commented = sorted({n["session_id"] for n in notes if n.get("type") == "session" and n.get("session_id")})
    return {
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "today": today_iso,
        "athlete": {**(plan.get("athlete") or {}), **(athlete_extra or {})},
        "race": race_summary,
        "paces": plan.get("paces"), "pace_labels": plan.get("pace_labels"),
        "hr_zones": plan.get("hr_zones"), "coach_rules": plan.get("rules"),
        "morning_light": light,
        "garmin_today": {k: today.get(k) for k in ("readiness", "status", "predictions", "endurance_score")} if today else None,
        "wellness_last_days": trends,
        "weekly_volume": weekly,
        "past_sessions": [sess(s) for s in past],
        "next_sessions": [sess(s, True) for s in future],
        "open_questions": [q for q in questions if not q.get("answered")],
        "already_commented_session_ids": commented,
        "recent_coach_notes": [{k: n.get(k) for k in ("type", "date", "session_id", "title", "body")} for n in notes[-8:]],
    }
