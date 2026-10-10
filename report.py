"""Résumé hebdomadaire par mail (HTML compatible clients mail : tableaux + styles en ligne)."""
from __future__ import annotations

import html
from datetime import date, timedelta
from statistics import mean

COACH_MARK = "<!--COACH_BILAN-->"
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
ACCENT = "#fc5200"


def _d(s: str) -> str:
    d = date.fromisoformat(s)
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"


def _pace(s):
    if not s:
        return "—"
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def _dur(s):
    if not s:
        return "—"
    s = int(round(s))
    h, m = divmod(s // 60, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def _fr(x, d=1):
    return "—" if x is None else f"{x:.{d}f}".replace(".", ",")


def report_week(today: date) -> date:
    """Le dimanche on résume la semaine en cours, sinon la semaine précédente."""
    mon = today - timedelta(days=today.weekday())
    return mon if today.weekday() == 6 else mon - timedelta(days=7)


def build_weekly_email(*, week_start: date, plan: dict, acts: list[dict], reviews: dict, trends: list[dict],
                       weekly: list[dict], race: dict, coach_note: dict | None = None) -> dict:
    ws, we = week_start, week_start + timedelta(days=6)
    wsi, wei = ws.isoformat(), we.isoformat()
    sessions = [s for s in plan["sessions"] if wsi <= s["date"] <= wei]
    nxt = [s for s in plan["sessions"] if (we + timedelta(days=1)).isoformat() <= s["date"] <= (we + timedelta(days=7)).isoformat()]
    runs = [a for a in acts if a.get("is_run") and wsi <= a["date"] <= wei]
    km = sum(a["distance_km"] for a in runs)
    secs = sum(a["duration_s"] or 0 for a in runs)
    elev = sum(a.get("elev_gain") or 0 for a in runs)
    planned_km = sum(s.get("planned_km") or 0 for s in sessions)
    to_do = [s for s in sessions if s["type"] not in ("REPOS", "RENFO")]
    done = [s for s in to_do if s.get("status") in ("done", "partial")]
    scores = [reviews[s["id"]]["review"]["score"] for s in sessions
              if reviews.get(s["id"]) and reviews[s["id"]]["review"].get("score") is not None and s.get("activities")]
    rpes = [s["feedback"]["rpe"] for s in sessions if (s.get("feedback") or {}).get("rpe")]

    def wavg(lo, hi, key):
        v = [t[key] for t in trends if lo <= t["date"] <= hi and t.get(key)]
        return mean(v) if v else None

    prev_s, prev_e = (ws - timedelta(days=7)).isoformat(), (ws - timedelta(days=1)).isoformat()
    hrv, hrv_p = wavg(wsi, wei, "hrv"), wavg(prev_s, prev_e, "hrv")
    rhr, rhr_p = wavg(wsi, wei, "rhr"), wavg(prev_s, prev_e, "rhr")
    sl, sl_p = wavg(wsi, wei, "sleep_s"), wavg(prev_s, prev_e, "sleep_s")
    sc = wavg(wsi, wei, "sleep_score")
    short_nights = sum(1 for t in trends if wsi <= t["date"] <= wei and t.get("sleep_s") and t["sleep_s"] < 6 * 3600)

    def delta(a, b, unit, d=0, invert=False):
        if a is None or b is None:
            return ""
        x = a - b
        if round(abs(x), d) == 0:
            return ""
        good = (x < 0) if invert else (x > 0)
        col = "#16a34a" if good else ("#dc2626" if abs(x) > 0 else "#6b7280")
        return f' <span style="color:{col};font-size:12px">({"+" if x >= 0 else "−"}{_fr(abs(x), d)}{unit})</span>'

    days_to = (date.fromisoformat(race["date"]) - date.today()).days
    week_idx = next((i for i, w in enumerate(sorted({(date.fromisoformat(s["date"]) - timedelta(days=date.fromisoformat(s["date"]).weekday())).isoformat() for s in plan["sessions"]})) if w == wsi), None)
    title = f"Semaine du {ws.day} au {we.day} {MOIS[we.month - 1]}" + (f" · S{week_idx}" if week_idx is not None else "")
    subject = f"Élan · {title} · {_fr(km)} km · J-{days_to} {race['name']}"

    # --- lignes séances
    rows = []
    for s in sessions:
        acts_s = s.get("activities") or []
        rv = (reviews.get(s["id"]) or {}).get("review") if acts_s else None
        score = rv.get("score") if rv else None
        sc_col = "#16a34a" if score is not None and score >= 70 else ("#d97706" if score is not None and score >= 50 else "#dc2626")
        real = " + ".join(f"{_fr(a['km'])} km · {_pace(a.get('pace_s'))}/km" + (f" · {int(a['avg_hr'])} bpm" if a.get("avg_hr") else "") for a in acts_s) \
            or ("—" if s["type"] in ("REPOS", "RENFO") else '<span style="color:#dc2626">non réalisée</span>' if s["date"] < date.today().isoformat() else "à venir")
        rows.append(f"""<tr>
<td style="padding:8px 6px;border-bottom:1px solid #eee;white-space:nowrap;color:#6b7280;font-size:13px">{_d(s['date'])}</td>
<td style="padding:8px 6px;border-bottom:1px solid #eee;font-size:14px"><b>{html.escape(s['title'])}</b><br><span style="color:#6b7280;font-size:12px">{html.escape(s.get('summary') or '')}</span></td>
<td style="padding:8px 6px;border-bottom:1px solid #eee;font-size:13px">{real}</td>
<td style="padding:8px 6px;border-bottom:1px solid #eee;text-align:center">{f'<span style="background:{sc_col};color:#fff;border-radius:6px;padding:2px 7px;font-weight:700;font-size:12px">{score}</span>' if score is not None else ''}</td></tr>""")

    # --- histogramme volume 8 semaines
    hist = []
    wk = [w for w in weekly if not w.get("future") or w["start"] <= wsi][-8:]
    mx = max([max(w["km"] or 0, w.get("planned_km") or 0) for w in wk] + [1])
    for w in wk:
        p = w.get("planned_km") or 0
        cur = w["start"] == wsi
        hist.append(f"""<tr><td style="font-size:12px;color:#6b7280;padding:2px 6px;white-space:nowrap">{date.fromisoformat(w['start']).day}/{date.fromisoformat(w['start']).month}</td>
<td style="width:100%;padding:2px 0"><div style="background:{ACCENT if cur else '#fdba8c'};height:12px;border-radius:3px;width:{max(1, round((w['km'] or 0) / mx * 100))}%"></div>{f'<div style="border-top:2px dashed #9ca3af;width:{round(p / mx * 100)}%;margin-top:2px"></div>' if p else ''}</td>
<td style="font-size:12px;padding:2px 6px;white-space:nowrap;text-align:right"><b>{_fr(w['km'], 0)}</b>{f' / {_fr(p, 0)}' if p else ''} km</td></tr>""")

    nxt_rows = "".join(f'<tr><td style="padding:5px 6px;color:#6b7280;font-size:13px;white-space:nowrap">{_d(s["date"])}</td><td style="padding:5px 6px;font-size:14px"><b>{html.escape(s["title"])}</b>{" · " + _fr(s.get("planned_km")) + " km" if s.get("planned_km") else ""}</td></tr>' for s in nxt)
    nxt_km = sum(s.get("planned_km") or 0 for s in nxt)

    coach_html = COACH_MARK + '<p style="margin:6px 0;font-size:14px;color:#6b7280">Le bilan du coach arrive le dimanche soir.</p><!--/COACH_BILAN-->'
    if coach_note:
        coach_html = _note_html(coach_note)

    kpi = lambda label, val, sub="": f'<td style="padding:10px;background:#f6f7f9;border-radius:10px;text-align:center;width:25%"><div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em">{label}</div><div style="font-size:22px;font-weight:800;margin-top:2px">{val}</div><div style="font-size:12px;color:#6b7280">{sub}</div></td>'
    body = f"""<!doctype html><html><body style="margin:0;background:#f4f5f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#14161a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:#fff;border-radius:16px;overflow:hidden">
<tr><td style="background:{ACCENT};color:#fff;padding:20px 22px">
  <div style="font-size:13px;opacity:.9">Élan · résumé de la semaine</div>
  <div style="font-size:22px;font-weight:800;margin-top:4px">{title}</div>
  <div style="font-size:14px;margin-top:6px">J-{days_to} · {html.escape(race['name'])} · objectif {html.escape(race['goal'])}</div>
</td></tr>
<tr><td style="padding:18px 16px 4px"><table role="presentation" width="100%" cellspacing="6"><tr>
  {kpi("Volume", f"{_fr(km)} km", f"prévu {_fr(planned_km, 0)} km")}
  {kpi("Séances", f"{len(done)}/{len(to_do)}", f"{_dur(secs)} de course")}
  {kpi("Bilan moyen", f"{round(mean(scores))}" if scores else "—", f"ressenti moy. {_fr(mean(rpes))}/10" if rpes else "sur 100")}
  {kpi("D+", f"{round(elev)} m", "")}
</tr></table></td></tr>
<tr><td style="padding:10px 22px 0"><div style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em">Le mot du coach</div>{coach_html}</td></tr>
<tr><td style="padding:16px 22px 0"><div style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Séances</div>
<table role="presentation" width="100%" cellspacing="0">{''.join(rows)}</table></td></tr>
<tr><td style="padding:16px 22px 0"><div style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Forme (moyennes de la semaine)</div>
<table role="presentation" width="100%" cellspacing="0" style="font-size:14px">
<tr><td style="padding:4px 0">VFC nocturne</td><td style="text-align:right"><b>{_fr(hrv, 0)} ms</b>{delta(hrv, hrv_p, " ms")}</td></tr>
<tr><td style="padding:4px 0">FC de repos</td><td style="text-align:right"><b>{_fr(rhr, 0)} bpm</b>{delta(rhr, rhr_p, " bpm", invert=True)}</td></tr>
<tr><td style="padding:4px 0">Sommeil</td><td style="text-align:right"><b>{_dur(sl)}</b>{delta((sl or 0) / 3600 if sl else None, (sl_p or 0) / 3600 if sl_p else None, " h", 1)} · score {_fr(sc, 0)}</td></tr>
<tr><td style="padding:4px 0">Nuits de moins de 6 h</td><td style="text-align:right"><b style="color:{'#dc2626' if short_nights >= 3 else '#14161a'}">{short_nights}</b></td></tr>
</table></td></tr>
<tr><td style="padding:16px 22px 0"><div style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Volume des 8 dernières semaines <span style="font-weight:400;text-transform:none">(pointillés = prévu)</span></div>
<table role="presentation" width="100%" cellspacing="0">{''.join(hist)}</table></td></tr>
<tr><td style="padding:16px 22px 0"><div style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">La semaine prochaine · {_fr(nxt_km, 0)} km prévus</div>
<table role="presentation" width="100%" cellspacing="0">{nxt_rows or '<tr><td style="color:#6b7280">Rien de prévu.</td></tr>'}</table></td></tr>
<tr><td style="padding:20px 22px;font-size:12px;color:#9ca3af">Envoyé par ton coach Élan. Détails, bilans et ajustements : ouvre Élan sur ton Mac (http://localhost:8742).</td></tr>
</table></td></tr></table></body></html>"""
    return {"subject": subject, "html": body, "week_start": wsi, "week_end": wei, "km": round(km, 1)}


def _note_html(n: dict) -> str:
    """Convertit le texte du coach (paragraphes, listes « - », **gras**) en HTML mail."""
    import re
    out = []
    if n.get("title"):
        out.append(f'<div style="font-size:16px;font-weight:700;margin:6px 0">{html.escape(n["title"])}</div>')
    for block in str(n.get("body") or "").split("\n\n"):
        lines = block.split("\n")
        fmt = lambda s: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(s))
        if all(l.strip().startswith(("- ", "• ")) for l in lines if l.strip()):
            out.append('<ul style="margin:6px 0;padding-left:20px;font-size:14px;line-height:1.5">' + "".join(f"<li>{fmt(l.strip()[2:])}</li>" for l in lines if l.strip()) + "</ul>")
        else:
            out.append(f'<p style="margin:6px 0;font-size:14px;line-height:1.5">{"<br>".join(fmt(l) for l in lines)}</p>')
    props = [p for p in n.get("proposals") or []]
    if props:
        out.append('<p style="margin:8px 0;font-size:13px;color:#6b7280">' + f"{len(props)} ajustement(s) proposé(s) : à valider dans l'onglet Coach de Sub3.</p>")
    return "".join(out)
