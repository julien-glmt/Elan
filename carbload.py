"""Recharge glucidique avant course : plan jour par jour, menus et suivi des repas.

Repères utilisés (recommandations courantes en nutrition du sport) :
- effort de plus de ~2 h 30 (marathon) : 36-48 h à ~10 g de glucides / kg / jour (J-2 et J-1), J-3 en transition ;
- effort de 1 h 30 à 2 h 30 : la veille à ~8 g/kg ;
- jour J : petit-déjeuner 3 h avant le départ (~2,5 g/kg), puis 20-30 g dans le quart d'heure avant ;
- pendant ces jours : peu de fibres, peu de graisses, protéines modérées, bien s'hydrater ;
- +1 à 2 kg sur la balance est normal (glycogène + eau) : ce n'est pas de la graisse.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

# glucides approximatifs par portion (aliments faciles à trouver en supermarché)
FOODS = [
    ("Pâtes cuites", "200 g (une assiette)", 60), ("Riz blanc cuit", "200 g", 56), ("Semoule cuite", "200 g", 46),
    ("Pain blanc / baguette", "1/2 baguette (125 g)", 65), ("Pain de mie", "2 tranches", 25), ("Corn flakes / céréales sans son", "50 g", 42),
    ("Banane", "1 moyenne", 25), ("Compote (gourde)", "90 g", 15), ("Jus de fruit / d'orange", "25 cl", 25),
    ("Miel ou confiture", "1 c. à soupe", 15), ("Sirop dilué", "25 cl", 25), ("Gâteau de riz / semoule", "1 pot", 30),
    ("Barre de céréales", "1 barre", 20), ("Pomme de terre cuite (sans peau)", "200 g", 34), ("Pain d'épices", "2 tranches (50 g)", 37),
    ("Boisson sucrée / soda", "33 cl", 35),
]

AVOID = ["légumes crus, salades et légumineuses (fibres)", "fritures, sauces grasses, fromages en quantité", "plats très épicés ou inconnus",
         "alcool", "trop de lait si tu le digères mal", "aliments complets (pain complet, riz complet) : passe au blanc"]


def _meals(carbs: int, kind: str) -> list[dict]:
    """Répartition des glucides sur la journée, avec un exemple concret pour chaque repas."""
    if kind == "load":
        parts = [("Petit-déjeuner", .22, "Corn flakes + lait, 2 tartines miel/confiture, jus d'orange, banane"),
                 ("Collation", .12, "Gâteau de riz + compote, ou pain d'épices + jus"),
                 ("Déjeuner", .28, "Grosse assiette de pâtes ou riz blanc, sauce tomate, un peu de jambon/poulet, pain blanc, compote"),
                 ("Goûter", .13, "Barres de céréales + banane + sirop"),
                 ("Dîner", .25, "Riz ou semoule + poisson/œuf, pain blanc, gâteau de riz ou compote")]
    elif kind == "eve":  # veille : gros midi, dîner tôt et digeste
        parts = [("Petit-déjeuner", .22, "Corn flakes + lait, tartines miel/confiture, jus d'orange"),
                 ("Collation", .12, "Banane + compote"),
                 ("Déjeuner (le plus gros repas)", .32, "Pâtes ou riz blanc à volonté, peu de sauce, pain blanc, dessert sucré"),
                 ("Goûter", .12, "Gâteau de riz, pain d'épices, sirop"),
                 ("Dîner tôt (avant 20 h)", .22, "Riz/pâtes ou purée, un peu de protéine maigre, pas de crudités")]
    elif kind == "transition":
        parts = [("Petit-déjeuner", .25, "Ton petit-déj habituel + un jus de fruit"),
                 ("Déjeuner", .35, "Féculents en plus grande quantité (pâtes, riz), légumes cuits"),
                 ("Collation", .12, "Banane, compote"),
                 ("Dîner", .28, "Féculents + protéine maigre, légumes cuits")]
    else:
        return []
    return [{"name": n, "carbs": int(round(carbs * f / 5) * 5), "example": ex} for n, f, ex in parts]


def _effort(session: dict, race: dict, is_main: bool, paces: dict | None = None) -> dict:
    """Durée prévue et km-effort (km + D+/100)."""
    km = None
    for st in session.get("steps") or []:
        d = (st.get("dur") or {})
        if d.get("type") == "distance":
            km = (km or 0) + d.get("value", 0) / 1000
    km = km or session.get("planned_km") or float(race.get("distance_km") or 42.195)
    m = re.search(r"(\d{3,4})\s*m\s*D\+", session.get("title") or "")
    dplus = int(m.group(1)) if m else 0
    if is_main and race.get("goal"):
        h, mi, s = (list(map(int, race["goal"].split(":"))) + [0, 0])[:3]
        secs = h * 3600 + mi * 60 + s
    else:
        secs = session.get("planned_s") or (km + dplus / 100) * 315  # ~5:15/km-effort par défaut
    return {"km": round(km, 1), "dplus": dplus, "seconds": round(secs)}


def plan_for(session: dict, race: dict, is_main: bool, weight: float, start_time: str = "08:00") -> dict:
    eff = _effort(session, race, is_main)
    secs = eff["seconds"]
    level = "full" if secs >= 2.5 * 3600 else ("light" if secs >= 1.5 * 3600 else "none")
    rd = date.fromisoformat(session["date"])
    w = weight
    days = []

    def day(offset: int, gkg: float, kind: str, title: str, tips: list[str]):
        carbs = int(round(gkg * w / 10) * 10)
        prot = round(1.3 * w)
        fat = round(0.8 * w)
        days.append({"date": (rd + timedelta(days=offset)).isoformat(), "offset": offset, "title": title, "g_per_kg": gkg,
                     "carbs": carbs, "protein": prot, "fat": fat, "kcal": int(round((carbs * 4 + prot * 4 + fat * 9) / 10) * 10),
                     "water_l": round(w * 0.04, 1), "kind": kind, "meals": _meals(carbs, kind), "tips": tips})

    if level == "full":
        day(-3, 6, "transition", "J-3 · on augmente doucement",
            ["Garde des repas normaux, mais avec plus de féculents à chaque repas.", "Commence à réduire les crudités et le complet.", "Pas de déficit calorique à partir d'aujourd'hui."])
        day(-2, 10, "load", "J-2 · recharge",
            ["Mange souvent : 5 prises dans la journée, c'est plus facile qu'en 3 gros repas.", "Pain blanc, riz blanc, pâtes, sucre : on évite les fibres.",
             "Les boissons sucrées (jus, sirop) aident à atteindre le total sans se gaver.", "Bois régulièrement : urines claires."])
        day(-1, 10, "eve", "J-1 · veille de course",
            ["Le gros repas, c'est le midi. Le soir : dîner tôt et digeste.", "Rien de nouveau : seulement des aliments que tu connais.",
             "Prépare tes gels, ton dossard et ton petit-déj ce soir.", "La balance peut afficher +1 à 2 kg : c'est du glycogène et de l'eau, c'est voulu."])
    elif level == "light":
        day(-1, 8, "eve", "J-1 · veille de course",
            ["Plus de féculents à chaque repas, peu de fibres et de graisses.", "Dîner tôt, digeste, avec des aliments que tu connais.", "Pas de déficit calorique."])
    hh, mm = map(int, (start_time or "08:00").split(":"))
    start = datetime.combine(rd, datetime.min.time()).replace(hour=hh, minute=mm)
    bk = start - timedelta(hours=3)
    bk_carbs = int(round(2.5 * w / 5) * 5) if level != "none" else int(round(1.5 * w / 5) * 5)
    race_day = {"date": rd.isoformat(), "start": start.strftime("%H:%M"), "breakfast_at": bk.strftime("%H:%M"), "breakfast_carbs": bk_carbs,
                "breakfast_example": f"Exemple (~{bk_carbs} g) : pain blanc + confiture/miel, une banane, un jus d'orange, un gâteau de riz. Café si tu en as l'habitude, rien de nouveau.",
                "pre_start": "15 min avant le départ : un gel ou 25 cl de boisson d'effort (~25 g).",
                "during": "Pendant : suis ton plan de ravitaillement (page Ravito).",
                "after": f"Après : dans l'heure, ~{round(w)} g de glucides + 20-25 g de protéines (boisson de récup, ou sandwich + jus + yaourt), et bois.",
                "wake": (bk - timedelta(minutes=20)).strftime("%H:%M")}
    return {"race": session.get("title"), "date": rd.isoformat(), "is_main": is_main, "level": level, "effort": eff, "weight": round(w, 1),
            "days": days, "race_day": race_day, "foods": [{"name": n, "portion": p, "carbs": c} for n, p, c in FOODS], "avoid": AVOID,
            "window": [(rd - timedelta(days=3)).isoformat(), (rd + timedelta(days=1)).isoformat()]}


class CarbStore:
    """Repas cochés pendant la recharge : {date: [index des repas faits]}."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "carbload.json"
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {"done": {}}

    def toggle(self, day: str, idx: int, on: bool) -> dict:
        with self.lock:
            d = self.load()
            cur = set(d["done"].get(day, []))
            (cur.add if on else cur.discard)(idx)
            d["done"][day] = sorted(cur)
            self.path.write_text(json.dumps(d))
            return d


def plans(sessions: list[dict], race: dict, weight: float, start_time: str, today: date | None = None, done: dict | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for s in sessions:
        if s.get("type") != "COURSE" or s["date"] < today.isoformat():
            continue
        p = plan_for(s, race, s["date"] == race.get("date"), weight, start_time if s["date"] == race.get("date") else "09:00")
        for dd in p["days"]:
            ids = set((done or {}).get(dd["date"], []))
            for i, m in enumerate(dd["meals"]):
                m["done"] = i in ids
            dd["eaten"] = sum(m["carbs"] for m in dd["meals"] if m["done"])
        p["days_to"] = (date.fromisoformat(p["date"]) - today).days
        out.append(p)
    return out


def active_day(all_plans: list[dict], day: str) -> dict | None:
    """Le jour de recharge correspondant à `day`, s'il y en a un."""
    for p in all_plans:
        for d in p["days"]:
            if d["date"] == day:
                return {**d, "race": p["race"], "race_date": p["date"]}
    return None
