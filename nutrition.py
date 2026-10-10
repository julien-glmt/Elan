"""Nutrition d'effort : produits (gels, boissons…), stock, classement S-A-B-C-D et carnet de ravitaillement.

Repères (consensus nutrition d'endurance) :
- < 75 min : rien d'obligatoire ;
- 75 min à 2h30 : 30 à 60 g de glucides / h ;
- > 2h30 et marathon : 60 à 90 g / h (60 g/h si l'estomac n'est pas encore entraîné) ;
- boisson : 400 à 800 ml / h selon la chaleur.
"""
from __future__ import annotations

import copy
import json
import math
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

DEFAULT_PRODUCTS = [
    {"id": "dec-gelplus", "name": "Energy Gel+", "brand": "Decathlon", "kind": "gel", "carbs_g": 30, "caffeine_mg": 0, "sodium_mg": 0,
     "price_eur": 1.83, "stock": 0, "ratings": {}, "tier_override": None, "notes": "Pas cher. Entraîne-toi à l'ouvrir en courant."},
    {"id": "ta-jelly", "name": "Jelly Gel", "brand": "Tā Energy", "kind": "gel", "carbs_g": 35, "caffeine_mg": 0, "sodium_mg": 200,
     "price_eur": 3.50, "stock": 0, "ratings": {}, "tier_override": None, "notes": "Texture gélifiée, version neutre bien tolérée en fin de course."},
    {"id": "compote", "name": "Compote à boire", "brand": "", "kind": "solide", "carbs_g": 13, "caffeine_mg": 0, "sodium_mg": 0,
     "price_eur": 0.40, "stock": 0, "ratings": {}, "tier_override": None, "notes": "Lourde pour peu de glucides."},
    {"id": "boisson-maison", "name": "Boisson maison 500 ml", "brand": "", "kind": "boisson", "carbs_g": 35, "caffeine_mg": 0, "sodium_mg": 250,
     "price_eur": 0.15, "stock": 0, "ratings": {}, "tier_override": None, "notes": "500 ml d'eau + 35 g de sucre ou sirop + une pincée de sel."},
]

CRITERIA = {"ventre": ("Ventre", 0.40), "gout": ("Goût", 0.25), "pratique": ("Ouverture / prise en courant", 0.20), "texture": ("Texture", 0.15)}
TIERS = ["S", "A", "B", "C", "D"]


def tier_of(p: dict) -> dict:
    r = {k: v for k, v in (p.get("ratings") or {}).items() if k in CRITERIA and isinstance(v, (int, float)) and v > 0}
    score = None
    if r:
        w = sum(CRITERIA[k][1] for k in r)
        score = round(sum(r[k] * CRITERIA[k][1] for k in r) / w, 2)
    if p.get("tier_override") in TIERS:
        return {"tier": p["tier_override"], "score": score, "manual": True}
    if score is None:
        return {"tier": None, "score": None, "manual": False}
    t = "S" if score >= 4.5 else "A" if score >= 3.8 else "B" if score >= 3.0 else "C" if score >= 2.2 else "D"
    if r.get("ventre", 5) <= 2:  # un produit qui retourne le ventre ne peut pas être bien classé
        t = max(t, "C", key=TIERS.index)
    return {"tier": t, "score": score, "manual": False}


def target_gph(duration_s: float) -> tuple[int, int]:
    h = duration_s / 3600
    if h < 1.25:
        return (0, 30)
    if h < 2.5:
        return (30, 60)
    return (60, 90)


def analyse_log(log: dict, duration_s: float | None, products: dict) -> dict:
    carbs = 0.0
    caffeine = 0.0
    sodium = 0.0
    for it in log.get("items", []):
        p = products.get(it.get("product_id")) or {}
        q = float(it.get("qty") or 0)
        carbs += q * float(it.get("carbs_g") if it.get("carbs_g") is not None else p.get("carbs_g", 0))
        caffeine += q * float(p.get("caffeine_mg") or 0)
        sodium += q * float(p.get("sodium_mg") or 0)
    water = float(log.get("water_ml") or 0)
    res = {"carbs_g": round(carbs), "water_ml": round(water), "caffeine_mg": round(caffeine), "sodium_mg": round(sodium)}
    if duration_s:
        h = duration_s / 3600
        lo, hi = target_gph(duration_s)
        gph = carbs / h
        mlh = water / h
        res.update(duration_s=round(duration_s), carbs_per_h=round(gph), water_per_h=round(mlh), target=[lo, hi])
        if lo == 0:
            res["verdict"], res["level"] = "Sortie courte : pas besoin de manger pendant.", "good"
        elif gph >= lo:
            res["verdict"], res["level"] = f"Bon apport : {round(gph)} g/h (objectif {lo}-{hi} g/h).", "good"
        elif gph >= lo * 0.6:
            res["verdict"], res["level"] = f"Un peu juste : {round(gph)} g/h pour un objectif de {lo}-{hi} g/h.", "warn"
        else:
            res["verdict"], res["level"] = f"Trop peu : {round(gph)} g/h pour un objectif de {lo}-{hi} g/h. Les jambes risquent de lâcher en fin de sortie.", "bad"
        if h >= 1.25:
            res["water_verdict"] = "Hydratation correcte." if mlh >= 400 else f"Boisson insuffisante : {round(mlh)} ml/h (vise 400-600 ml/h)."
    return res


class NutritionStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "nutrition.json"
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except Exception:
            d = {"products": copy.deepcopy(DEFAULT_PRODUCTS), "logs": {}}
            self.save(d)
        d.setdefault("products", [])
        d.setdefault("logs", {})
        return d

    def save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    # ---------------------------------------------------------------- produits
    def upsert_product(self, body: dict) -> dict:
        with self.lock:
            d = self.load()
            pid = body.get("id")
            p = next((x for x in d["products"] if x["id"] == pid), None) if pid else None
            if not p:
                p = {"id": "p" + uuid.uuid4().hex[:6], "ratings": {}, "tier_override": None, "stock": 0}
                d["products"].append(p)
            for k in ("name", "brand", "kind", "notes"):
                if k in body:
                    p[k] = str(body[k] or "")[:120]
            for k in ("carbs_g", "caffeine_mg", "sodium_mg", "price_eur", "stock"):
                if k in body and body[k] not in (None, ""):
                    p[k] = max(0, float(body[k])) if k == "price_eur" else max(0, int(float(body[k])))
            if "ratings" in body and isinstance(body["ratings"], dict):
                p["ratings"] = {k: int(v) for k, v in body["ratings"].items() if k in CRITERIA and v not in (None, "", 0)}
            if "tier_override" in body:
                p["tier_override"] = body["tier_override"] if body["tier_override"] in TIERS else None
            self.save(d)
            return p

    def delete_product(self, pid: str) -> None:
        with self.lock:
            d = self.load()
            d["products"] = [p for p in d["products"] if p["id"] != pid]
            self.save(d)

    # ---------------------------------------------------------------- carnet
    def save_log(self, sid: str, body: dict) -> dict:
        """Enregistre le ravitaillement d'une séance et ajuste le stock (différence avec l'ancienne saisie)."""
        with self.lock:
            d = self.load()
            prods = {p["id"]: p for p in d["products"]}
            old = d["logs"].get(sid, {"items": []})
            items = []
            for it in body.get("items", []):
                q = float(it.get("qty") or 0)
                if q <= 0:
                    continue
                e = {"product_id": it.get("product_id"), "qty": q}
                if not it.get("product_id"):
                    e["label"] = str(it.get("label") or "Autre")[:60]
                    e["carbs_g"] = float(it.get("carbs_g") or 0)
                items.append(e)
            delta: dict[str, float] = {}
            for it in old.get("items", []):
                if it.get("product_id"):
                    delta[it["product_id"]] = delta.get(it["product_id"], 0) + it["qty"]
            for it in items:
                if it.get("product_id"):
                    delta[it["product_id"]] = delta.get(it["product_id"], 0) - it["qty"]
            for pid, dq in delta.items():
                if pid in prods and prods[pid].get("kind") in ("gel", "solide") and dq:
                    prods[pid]["stock"] = max(0, int(round(prods[pid].get("stock", 0) + dq)))
            log = {"items": items, "water_ml": float(body.get("water_ml") or 0), "notes": str(body.get("notes") or "")[:500],
                   "at": datetime.now().isoformat(timespec="minutes")}
            d["logs"][sid] = log
            self.save(d)
            return log

    # ---------------------------------------------------------------- synthèse
    def summary(self, sessions: list[dict], race_gels: int | None, today: str | None = None) -> dict:
        d = self.load()
        today = today or date.today().isoformat()
        prods = d["products"]
        for p in prods:
            p.update(tier_of(p))
        gels = [p for p in prods if p.get("kind") == "gel"]
        ranked = sorted([p for p in gels if p.get("tier")], key=lambda p: (TIERS.index(p["tier"]), -(p.get("score") or 0)))
        favorite = ranked[0] if ranked else (max(gels, key=lambda p: p.get("carbs_g", 0)) if gels else None)
        fav_carbs = (favorite or {}).get("carbs_g") or 30

        # besoins en gels d'ici la course : sorties ≥ 75 min à venir
        need = 0
        plan_need = []
        for s in sessions:
            if s["date"] < today or s.get("activities") or not s.get("planned_s") or s["planned_s"] < 75 * 60 or s.get("type") == "COURSE":
                continue
            lo, hi = target_gph(s["planned_s"])
            g = math.ceil(((lo + hi) / 2 if lo else 0) * s["planned_s"] / 3600 / fav_carbs * 0.8)  # une partie peut venir de la boisson
            if g:
                need += g
                plan_need.append({"date": s["date"], "title": s["title"], "gels": g})
        if race_gels:
            need += race_gels + 1
            plan_need.append({"date": "course", "title": "Marathon (+1 de secours)", "gels": race_gels + 1})
        stock = sum(int(p.get("stock") or 0) for p in gels)
        cost = round(max(0, need - stock) * ((favorite or {}).get("price_eur") or 2), 2)
        board = {t: [p for p in prods if p.get("tier") == t] for t in TIERS}
        board["?"] = [p for p in prods if not p.get("tier")]
        return {"products": prods, "board": board, "favorite": favorite, "gel_stock": stock, "gels_needed": need,
                "gels_missing": max(0, need - stock), "restock_cost": cost, "needs": plan_need,
                "criteria": {k: v[0] for k, v in CRITERIA.items()}, "logs": d["logs"]}


def prep_card(session: dict, favorite: dict | None, paces: dict | None = None) -> dict | None:
    """Fiche « veille de sortie longue » : quoi emporter et quand le prendre."""
    dur = session.get("planned_s") or 0
    if dur < 75 * 60:
        return None
    lo, hi = target_gph(dur)
    target = 60 if lo >= 60 else 45
    gel_c = (favorite or {}).get("carbs_g") or 30
    total = target * dur / 3600
    n_gels = max(1, math.floor((total - 0) / gel_c + 0.5))
    first = 30
    interval = max(20, int((dur / 60 - first - 15) / max(1, n_gels - 1))) if n_gels > 1 else 0
    times = [first + i * interval for i in range(n_gels)]
    water = round(500 * dur / 3600 / 50) * 50
    return {
        "session_id": session["id"], "date": session["date"], "title": session["title"], "duration_s": dur,
        "target_gph": target, "gel": favorite["brand"] + " " + favorite["name"] if favorite else "gel",
        "gels": n_gels, "gel_times_min": times, "water_ml": water,
        "carry": "Ceinture ou short à poches pour les gels, flasque souple ou gilet pour la boisson" if water > 400 else "Short à poches ou ceinture",
        "meal_morning": "Sortie le matin : petit-déj riche en glucides 2 à 3 h avant (pain, confiture, banane, boisson), ou une collation 45 min avant si tu pars tôt.",
        "meal_evening": "Sortie le soir : vrai repas avec des féculents le midi, puis une collation 1 h avant (banane, barre, pain + miel). Ne pars pas le ventre vide après la journée.",
        "evening_before": "La veille : dîner avec des féculents, 500 ml d'eau en plus, au lit à l'heure conseillée.",
    }
