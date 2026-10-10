"""Module Finances : comptes, transactions, catégories & budgets, abonnements, objectifs d'épargne, import bancaire, analyses.

Conventions
- Chaque transaction a un montant SIGNÉ du point de vue du compte : négatif = sortie, positif = entrée.
- Un virement entre deux de tes comptes est une transaction avec `to_account` (montant positif = somme déplacée).
  Un virement vers un compte d'épargne / placement compte comme « épargne » du mois, pas comme une dépense.
- Les catégories ont un genre : income (revenus), bill (charges fixes), expense (dépenses variables).
- Un remboursement = montant positif dans une catégorie de dépense : il réduit la dépense de la catégorie.
- Le « mois budgétaire » peut commencer un autre jour que le 1er (ex. le jour de la paie).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import threading
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

ACCOUNT_TYPES = {
    "courant": "Compte courant", "epargne": "Épargne", "placement": "Placement (PEA, CTO…)",
    "crypto": "Crypto", "retraite": "Épargne salariale / retraite", "especes": "Espèces / titres-resto",
}
SAVING_TYPES = {"epargne", "placement", "crypto", "retraite"}
KINDS = {"income": "Revenus", "bill": "Charges fixes", "expense": "Dépenses"}

PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316", "#84cc16",
           "#06b6d4", "#a855f7", "#e11d48", "#64748b", "#d946ef", "#22c55e"]

DEFAULT_ACCOUNTS = [
    ("Compte courant", "courant"), ("Livret A", "epargne"), ("PEA", "placement"), ("CTO", "placement"),
    ("Wallet crypto", "crypto"), ("Épargne salariale", "retraite"), ("Titres-resto", "especes"),
]
DEFAULT_CATEGORIES = [
    ("Salaire", "income", 0), ("Primes & remboursements", "income", 0), ("Autres revenus", "income", 0),
    ("Loyer", "bill", 0), ("Énergie (Engie)", "bill", 0), ("Mobile & internet", "bill", 0), ("Abonnements", "bill", 0),
    ("Salle de sport", "bill", 0), ("Assurances", "bill", 0), ("Banque & frais", "bill", 0),
    ("Courses", "expense", 0), ("Restos & sorties", "expense", 0), ("Livraison (Uber Eats…)", "expense", 0),
    ("Transport & déplacements", "expense", 0), ("Sport & running", "expense", 0), ("Vêtements", "expense", 0),
    ("Santé & soins", "expense", 0), ("Loisirs & culture", "expense", 0), ("Tech & jeux", "expense", 0),
    ("Voyages", "expense", 0), ("Cadeaux", "expense", 0), ("Maison", "expense", 0), ("Impôts", "expense", 0),
    ("Divers", "expense", 0),
]
# mots-clés de libellés bancaires → catégorie (import CSV)
KEYWORDS = [
    (r"carrefour|leclerc|lidl|auchan|intermarch|monoprix|franprix|super u|hyper u|casino|aldi|picard|biocoop|netto|cora|grand frais|naturalia", "Courses"),
    (r"uber ?eats|deliveroo|just ?eat", "Livraison (Uber Eats…)"),
    (r"restau|brasserie|burger|mcdo|mc donald|kfc|sushi|pizza|bar |cafe|café|starbucks|boulang", "Restos & sorties"),
    (r"ouigo|tgv|ratp|bla ?bla|uber(?! ?eats)|bolt|total ?energies|esso|shell|bp |avia|station|peage|péage|parking|lime|air ?france|easyjet|ryanair|transavia|vinci", "Transport & déplacements"),
    (r"decathlon|i-?run|alltricks|running|intersport|go sport|sport ?2000|nike|asics|garmin|strava|klikego|njuko|chronostart|protiming|ta energy", "Sport & running"),
    (r"basic ?fit|fitness|on air|keep cool", "Salle de sport"),
    (r"spotify|netflix|disney|prime video|amazon prime|deezer|canal|apple\.com|icloud|google \*|youtube|chatgpt|openai|anthropic|claude", "Abonnements"),
    (r"free mobile|bouygues|sfr|orange|sosh|red by|b&you", "Mobile & internet"),
    (r"engie|edf|total ?energ.*electr|ekwateur|gaz", "Énergie (Engie)"),
    (r"loyer|foncia|nexity|citya", "Loyer"),
    (r"assur|maif|macif|matmut|axa|allianz|groupama|alan|mutuelle", "Assurances"),
    (r"pharma|docteur|medecin|médecin|dentist|kine|kiné|ophtal|doctolib|osteo|ostéo", "Santé & soins"),
    (r"zara|h&m|uniqlo|kiabi|celio|jules|vinted|zalando|primark|lacoste", "Vêtements"),
    (r"fnac|cultura|cinema|cinéma|ugc|pathe|pathé|kinepolis|ticketmaster|livre|librairie", "Loisirs & culture"),
    (r"steam|playstation|nintendo|xbox|epic games|riot|ldlc|boulanger|darty|apple store|amazon", "Tech & jeux"),
    (r"airbnb|booking|hotel|hôtel|accor|ibis", "Voyages"),
    (r"impot|impôt|dgfip|tresor public|trésor public", "Impôts"),
    (r"frais|cotisation|commission|agios", "Banque & frais"),
    (r"ikea|leroy|castorama|brico|action |maisons du monde", "Maison"),
    (r"salaire|paie|payroll", "Salaire"),
]


def _id() -> str:
    return uuid.uuid4().hex[:10]


def _num(x, default=None):
    if x is None or x == "":
        return default
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(" ", "").replace("\xa0", "").replace(" ", "").replace("€", "")
    if s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def _date(s) -> str | None:
    if not s:
        return None
    s = str(s).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------ mois budgétaires
def month_bounds(ym: str, start_day: int) -> tuple[date, date]:
    """Mois budgétaire « ym » : du jour start_day du mois précédent (si start_day > 1) au jour d'avant le suivant.
    Ex. start_day = 28 : « 2026-11 » = du 28 oct. au 27 nov. (le salaire de fin octobre finance novembre)."""
    y, m = int(ym[:4]), int(ym[5:7])
    if start_day <= 1:
        a = date(y, m, 1)
        b = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        return a, b
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    a = _safe_day(py, pm, start_day)
    b = _safe_day(y, m, start_day) - timedelta(days=1)
    return a, b


def _safe_day(y, m, d):
    while True:
        try:
            return date(y, m, d)
        except ValueError:
            d -= 1


def month_of(d: str, start_day: int) -> str:
    dt = date.fromisoformat(d)
    if start_day <= 1 or dt.day < start_day:
        return f"{dt.year}-{dt.month:02d}"
    ny, nm = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    return f"{ny}-{nm:02d}"


def shift_month(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    y += m // 12
    return f"{y}-{m % 12 + 1:02d}"


# ------------------------------------------------------------------ stockage
class FinanceStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "finance.json"
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except Exception:
            d = self.default()
            self.save(d)
        for k in ("accounts", "categories", "transactions", "recurring", "goals", "valuations", "rules"):
            d.setdefault(k, [])
        d.setdefault("settings", {})
        d["settings"] = {"month_start_day": 1, "currency": "EUR", "setup": False, **d["settings"]}
        return d

    @staticmethod
    def default() -> dict:
        today = date.today().isoformat()
        return {
            "settings": {"month_start_day": 1, "currency": "EUR", "setup": False},
            "accounts": [{"id": _id(), "name": n, "type": t, "initial": 0.0, "initial_date": today, "color": PALETTE[i % len(PALETTE)],
                          "archived": False} for i, (n, t) in enumerate(DEFAULT_ACCOUNTS)],
            "categories": [{"id": _id(), "name": n, "kind": k, "budget": b, "color": PALETTE[i % len(PALETTE)]}
                           for i, (n, k, b) in enumerate(DEFAULT_CATEGORIES)],
            "transactions": [], "recurring": [], "goals": [], "valuations": [], "rules": [],
        }

    def save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    # ---------------------------------------------------------------- CRUD générique
    FIELDS = {
        "accounts": {"name": str, "type": str, "initial": float, "initial_date": "date", "color": str, "archived": bool},
        "categories": {"name": str, "kind": str, "budget": float, "color": str},
        "transactions": {"date": "date", "amount": float, "account": str, "to_account": str, "category": str, "label": str,
                         "note": str, "tags": list},
        "recurring": {"label": str, "amount": float, "account": str, "to_account": str, "category": str, "day": int,
                      "active": bool, "start": "date", "end": "date", "freq": str},
        "goals": {"name": str, "target": float, "account": str, "saved": float, "deadline": "date", "color": str},
        "valuations": {"account": str, "date": "date", "value": float},
        "rules": {"pattern": str, "category": str},
    }

    def upsert(self, coll: str, body: dict) -> dict:
        spec = self.FIELDS.get(coll)
        if not spec:
            raise ValueError("Collection inconnue")
        with self.lock:
            d = self.load()
            items = d[coll]
            cur = next((x for x in items if x["id"] == body.get("id")), None) if body.get("id") else None
            new = cur is None
            if new:
                cur = {"id": _id()}
            for k, t in spec.items():
                if k not in body:
                    continue
                v = body[k]
                if t is float:
                    cur[k] = _num(v, 0.0)
                elif t is int:
                    cur[k] = int(_num(v, 1) or 1)
                elif t is bool:
                    cur[k] = bool(v)
                elif t == "date":
                    cur[k] = _date(v) if v else None
                elif t is list:
                    cur[k] = [str(x)[:30] for x in (v or [])][:8]
                else:
                    cur[k] = (str(v)[:300] if v is not None else None) or None
            if coll == "transactions":
                if not cur.get("date"):
                    raise ValueError("Date obligatoire")
                if not cur.get("account"):
                    raise ValueError("Compte obligatoire")
                if cur.get("to_account") == cur.get("account"):
                    cur["to_account"] = None
            if coll == "categories" and cur.get("kind") not in KINDS:
                cur["kind"] = "expense"
            if coll == "accounts" and cur.get("type") not in ACCOUNT_TYPES:
                cur["type"] = "courant"
            if new:
                items.append(cur)
            self.save(d)
            return cur

    def delete(self, coll: str, iid: str) -> None:
        with self.lock:
            d = self.load()
            if coll not in d:
                raise ValueError("Collection inconnue")
            d[coll] = [x for x in d[coll] if x["id"] != iid]
            self.save(d)

    def set_settings(self, body: dict) -> dict:
        with self.lock:
            d = self.load()
            s = d["settings"]
            if "month_start_day" in body:
                s["month_start_day"] = max(1, min(28, int(_num(body["month_start_day"], 1) or 1)))
            if "setup" in body:
                s["setup"] = bool(body["setup"])
            self.save(d)
            return s

    # ---------------------------------------------------------------- abonnements → transactions
    def apply_recurring(self, today: date | None = None) -> int:
        """Crée les transactions des abonnements / charges fixes échues (une fois par mois)."""
        today = today or date.today()
        n = 0
        with self.lock:
            d = self.load()
            done = {(t.get("recurring_id"), t["date"][:7]) for t in d["transactions"] if t.get("recurring_id")}
            for r in d["recurring"]:
                if not r.get("active", True) or not r.get("account") or not r.get("amount"):
                    continue
                start = date.fromisoformat(r.get("start") or today.isoformat())
                cur = date(start.year, start.month, 1)
                while cur <= today:
                    when = _safe_day(cur.year, cur.month, int(r.get("day") or 1))
                    yearly = r.get("freq") == "year"
                    if when >= start and when <= today and (not r.get("end") or when.isoformat() <= r["end"]) \
                            and (not yearly or when.month == start.month) and (r["id"], when.isoformat()[:7]) not in done:
                        d["transactions"].append({"id": _id(), "date": when.isoformat(), "amount": r["amount"], "account": r["account"],
                                                  "to_account": r.get("to_account"), "category": r.get("category"), "label": r["label"],
                                                  "recurring_id": r["id"]})
                        done.add((r["id"], when.isoformat()[:7]))
                        n += 1
                    cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
            if n:
                self.save(d)
        return n

    # ---------------------------------------------------------------- import bancaire
    def guess_category(self, d: dict, label: str, amount: float) -> str | None:
        lab = (label or "").lower()
        cats = {c["name"]: c["id"] for c in d["categories"]}
        for r in d["rules"]:
            try:
                if r.get("pattern") and re.search(r["pattern"], lab, re.I):
                    return r["category"]
            except re.error:
                if r["pattern"].lower() in lab:
                    return r["category"]
        # même libellé déjà catégorisé
        key = _label_key(label)
        for t in reversed(d["transactions"]):
            if t.get("category") and _label_key(t.get("label")) == key:
                return t["category"]
        for pat, name in KEYWORDS:
            if re.search(pat, lab, re.I) and name in cats:
                return cats[name]
        if amount > 0:
            return cats.get("Autres revenus")
        return None

    def parse_csv(self, text: str, account: str) -> dict:
        d = self.load()
        sample = text[:4000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            delim = dialect.delimiter
        except Exception:
            delim = ";" if sample.count(";") > sample.count(",") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        rows = [r for r in rows if any(c.strip() for c in r)]
        # ligne d'en-tête = la première qui contient « date »
        hi = next((i for i, r in enumerate(rows[:30]) if any("date" in c.lower() for c in r)), 0)
        head = [c.strip().lower() for c in rows[hi]]

        def col(*names):
            for n in names:
                for i, h in enumerate(head):
                    if n in h:
                        return i
            return None
        ci_date = col("date op", "date d'op", "date")
        ci_lab = col("libellé", "libelle", "label", "description", "détail", "detail", "opération", "operation", "nom")
        ci_amt = col("montant", "amount", "valeur")
        ci_deb = col("débit", "debit")
        ci_cred = col("crédit", "credit")
        if ci_date is None or (ci_amt is None and ci_deb is None):
            raise ValueError("Je ne reconnais pas ce fichier : il faut au moins des colonnes Date et Montant (ou Débit / Crédit).")
        existing = {t.get("hash") for t in d["transactions"] if t.get("hash")}
        out = []
        for r in rows[hi + 1:]:
            g = lambda i: r[i].strip() if i is not None and i < len(r) else ""
            ds = _date(g(ci_date))
            if not ds:
                continue
            if ci_amt is not None and g(ci_amt):
                amt = _num(g(ci_amt))
            else:
                deb, cred = _num(g(ci_deb), 0.0), _num(g(ci_cred), 0.0)
                amt = (cred or 0) - abs(deb or 0)
            if amt is None:
                continue
            label = re.sub(r"\s+", " ", g(ci_lab)) or "Opération"
            h = hashlib.sha1(f"{account}|{ds}|{amt:.2f}|{label.lower()}".encode()).hexdigest()[:16]
            out.append({"date": ds, "amount": round(amt, 2), "label": label[:140], "hash": h, "duplicate": h in existing,
                        "category": self.guess_category(d, label, amt)})
        return {"rows": out, "columns": head, "delimiter": delim}

    def commit_import(self, account: str, rows: list[dict]) -> int:
        with self.lock:
            d = self.load()
            existing = {t.get("hash") for t in d["transactions"] if t.get("hash")}
            n = 0
            for r in rows:
                if r.get("skip") or r.get("hash") in existing:
                    continue
                d["transactions"].append({"id": _id(), "date": r["date"], "amount": float(r["amount"]), "account": account,
                                          "category": r.get("category") or None, "label": r.get("label") or "", "hash": r.get("hash"),
                                          "to_account": r.get("to_account") or None, "imported": True})
                n += 1
            self.save(d)
            return n


def _label_key(s) -> str:
    s = re.sub(r"\d+", "", (s or "").lower())
    s = re.sub(r"\b(cb|carte|prlv|prelevement|prélèvement|vir|virement|sepa|facture|paiement|achat|du|le|la|de|des)\b|[*/.]", " ", s)
    return " ".join(s.split()[:3])


# ------------------------------------------------------------------ calculs
def balances(d: dict, at: date | None = None) -> dict[str, float]:
    """Solde de chaque compte à une date (initial + flux), recalé sur la dernière valorisation saisie."""
    at = at or date.today()
    atx = at.isoformat()
    out = {}
    for a in d["accounts"]:
        vals = sorted([v for v in d["valuations"] if v["account"] == a["id"] and v["date"] <= atx], key=lambda v: v["date"])
        if vals:
            base, since = vals[-1]["value"], vals[-1]["date"]
            strict = True
        else:
            base, since = a.get("initial") or 0.0, a.get("initial_date") or "0000-00-00"
            strict = False
        s = base
        for t in d["transactions"]:
            if (t["date"] > since if strict else t["date"] >= since) and t["date"] <= atx:
                if t["account"] == a["id"]:
                    s += -abs(t["amount"]) if t.get("to_account") else t["amount"]
                if t.get("to_account") == a["id"]:
                    s += abs(t["amount"])
        out[a["id"]] = round(s, 2)
    return out


def month_summary(d: dict, ym: str) -> dict:
    sd = d["settings"]["month_start_day"]
    a, b = month_bounds(ym, sd)
    cats = {c["id"]: c for c in d["categories"]}
    accs = {x["id"]: x for x in d["accounts"]}
    txs = [t for t in d["transactions"] if a.isoformat() <= t["date"] <= b.isoformat()]
    inc = bills = exp = sav = 0.0
    by_cat = defaultdict(float)
    for t in txs:
        if t.get("to_account"):
            src, dst = accs.get(t["account"], {}), accs.get(t["to_account"], {})
            amt = abs(t["amount"])
            if dst.get("type") in SAVING_TYPES and src.get("type") not in SAVING_TYPES:
                sav += amt
            elif src.get("type") in SAVING_TYPES and dst.get("type") not in SAVING_TYPES:
                sav -= amt
            continue
        c = cats.get(t.get("category"))
        kind = c["kind"] if c else ("income" if t["amount"] > 0 else "expense")
        if kind == "income":
            inc += t["amount"]
        else:
            if kind == "bill":
                bills += -t["amount"]
            else:
                exp += -t["amount"]
            by_cat[t.get("category") or "_none"] += -t["amount"]
    spent = bills + exp
    days = (b - a).days + 1
    today = date.today()
    elapsed = max(1, min(days, (today - a).days + 1)) if a <= today else 0
    budgets = []
    for c in d["categories"]:
        if c["kind"] == "income":
            continue
        s = round(by_cat.get(c["id"], 0.0), 2)
        if s or c.get("budget"):
            proj = s if (today > b or not elapsed or c["kind"] == "bill") else s / elapsed * days
            budgets.append({"id": c["id"], "name": c["name"], "kind": c["kind"], "color": c.get("color"), "spent": s,
                            "budget": c.get("budget") or 0, "projected": round(proj, 2),
                            "pct": round(s / c["budget"] * 100) if c.get("budget") else None})
    budgets.sort(key=lambda x: -x["spent"])
    if by_cat.get("_none"):
        budgets.append({"id": None, "name": "Sans catégorie", "kind": "expense", "color": "#94a3b8", "spent": round(by_cat["_none"], 2),
                        "budget": 0, "projected": round(by_cat["_none"], 2), "pct": None})
    total_budget = sum(c.get("budget") or 0 for c in d["categories"] if c["kind"] != "income")
    left_days = max(0, (b - today).days + 1) if a <= today <= b else 0
    var_budget = sum(c.get("budget") or 0 for c in d["categories"] if c["kind"] == "expense")
    return {
        "month": ym, "from": a.isoformat(), "to": b.isoformat(), "income": round(inc, 2), "bills": round(bills, 2),
        "expenses": round(exp, 2), "spent": round(spent, 2), "saved": round(sav, 2), "net": round(inc - spent, 2),
        "savings_rate": round((inc - spent) / inc * 100) if inc > 0 else None, "budgets": budgets, "n": len(txs),
        "total_budget": round(total_budget, 2), "left_days": left_days,
        "var_left": round(var_budget - exp, 2) if var_budget else None,
        "per_day_left": round((var_budget - exp) / left_days, 2) if var_budget and left_days else None,
        "uncategorized": sum(1 for t in txs if not t.get("category") and not t.get("to_account")),
    }


def overview(d: dict, ym: str, run_km_year: float | None = None) -> dict:
    sd = d["settings"]["month_start_day"]
    bal = balances(d)
    accs = [{**a, "balance": bal.get(a["id"], 0.0), "type_label": ACCOUNT_TYPES.get(a["type"], a["type"])} for a in d["accounts"] if not a.get("archived")]
    net = round(sum(a["balance"] for a in accs), 2)
    liquid = round(sum(a["balance"] for a in accs if a["type"] in ("courant", "epargne", "especes")), 2)
    cur = month_summary(d, ym)
    prev = month_summary(d, shift_month(ym, -1))
    hist = [month_summary(d, shift_month(ym, -k)) for k in range(11, -1, -1)]
    # patrimoine fin de chaque mois
    nw = []
    first = min([a.get("initial_date") or "9999" for a in d["accounts"]] + [t["date"] for t in d["transactions"]] or ["9999"])
    for h in hist:
        end = min(date.fromisoformat(h["to"]), date.today())
        if end.isoformat() < first:
            continue
        b = balances(d, end)
        nw.append({"month": h["month"], "value": round(sum(v for k, v in b.items() if not next((a for a in d["accounts"] if a["id"] == k), {}).get("archived")), 2)})
    past = [h for h in hist[:-1] if h["n"]]
    avg_spent = round(mean([h["spent"] for h in past]), 2) if past else None
    avg_income = round(mean([h["income"] for h in past]), 2) if past else None
    emergency = sum(a["balance"] for a in accs if a["type"] in ("epargne",))
    months_cover = round(emergency / avg_spent, 1) if avg_spent else None
    # abonnements / charges fixes à venir ce mois
    a, b = month_bounds(ym, sd)
    upcoming = []
    for r in d["recurring"]:
        if not r.get("active", True):
            continue
        for m in {a.month, b.month}:
            y = a.year if m == a.month else b.year
            when = _safe_day(y, m, int(r.get("day") or 1))
            if a <= when <= b and when >= date.today():
                if r.get("freq") == "year" and r.get("start") and date.fromisoformat(r["start"]).month != when.month:
                    continue
                upcoming.append({"label": r["label"], "date": when.isoformat(), "amount": r["amount"]})
    upcoming.sort(key=lambda x: x["date"])
    monthly_fixed = sum(abs(r["amount"]) / (12 if r.get("freq") == "year" else 1) for r in d["recurring"]
                        if r.get("active", True) and r.get("amount", 0) < 0 and not r.get("to_account"))
    # insights
    cats = {c["id"]: c for c in d["categories"]}
    insights = []
    if cur["uncategorized"]:
        insights.append({"level": "info", "text": f"{cur['uncategorized']} transaction(s) sans catégorie ce mois-ci."})
    for bgt in cur["budgets"]:
        if bgt["budget"] and bgt["projected"] > bgt["budget"] * 1.05 and bgt["kind"] == "expense":
            insights.append({"level": "warn", "text": f"{bgt['name']} : {fmt_eur(bgt['spent'])} dépensés, en route pour {fmt_eur(bgt['projected'])} (budget {fmt_eur(bgt['budget'])})."})
    if past:
        for c in d["categories"]:
            if c["kind"] != "expense":
                continue
            avg3 = mean([next((x["spent"] for x in h["budgets"] if x["id"] == c["id"]), 0) for h in past[-3:]])
            now = next((x["spent"] for x in cur["budgets"] if x["id"] == c["id"]), 0)
            if avg3 > 30 and now > avg3 * 1.4 and now - avg3 > 40:
                insights.append({"level": "info", "text": f"{c['name']} : {fmt_eur(now)} ce mois-ci contre {fmt_eur(avg3)} en moyenne."})
    if months_cover is not None:
        insights.append({"level": "good" if months_cover >= 3 else "warn",
                         "text": f"Épargne de précaution : {str(months_cover).replace('.', ',')} mois de dépenses couverts" + (" (objectif 3 à 6 mois)." if months_cover < 3 else ".")})
    sport = next((c for c in d["categories"] if c["name"].lower().startswith("sport")), None)
    sport_year = None
    if sport:
        y = str(date.today().year)
        sport_year = round(-sum(t["amount"] for t in d["transactions"] if t.get("category") == sport["id"] and t["date"][:4] == y), 2)
    top = sorted([t for t in d["transactions"] if cur["from"] <= t["date"] <= cur["to"] and t["amount"] < 0 and not t.get("to_account")],
                 key=lambda t: t["amount"])[:5]
    return {
        "settings": d["settings"], "month": ym, "accounts": accs, "net_worth": net, "liquid": liquid,
        "current": cur, "previous": prev, "history": [{k: h[k] for k in ("month", "income", "spent", "saved", "net", "savings_rate")} for h in hist],
        "net_worth_history": nw, "avg_spent": avg_spent, "avg_income": avg_income, "months_cover": months_cover,
        "upcoming": upcoming[:8], "monthly_fixed": round(monthly_fixed, 2), "insights": insights,
        "sport_year": sport_year, "run_km_year": run_km_year,
        "eur_per_km": round(sport_year / run_km_year, 2) if sport_year and run_km_year else None,
        "top": [{"date": t["date"], "label": t.get("label"), "amount": t["amount"], "category": cats.get(t.get("category"), {}).get("name")} for t in top],
        "goals": goals_status(d, bal, avg_spent),
    }


def goals_status(d: dict, bal: dict, avg_spent) -> list[dict]:
    out = []
    for g in d["goals"]:
        saved = bal.get(g["account"]) if g.get("account") else (g.get("saved") or 0)
        target = g.get("target") or 0
        pct = round(min(100, saved / target * 100)) if target else None
        monthly = None
        if g.get("deadline") and target and saved < target:
            months = max(1, (date.fromisoformat(g["deadline"]) - date.today()).days / 30.4)
            monthly = round((target - saved) / months, 2)
        out.append({**g, "current": round(saved or 0, 2), "pct": pct, "monthly_needed": monthly})
    return out


def analysis(d: dict, year: int) -> dict:
    sd = d["settings"]["month_start_day"]
    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    sums = [month_summary(d, m) for m in months]
    cats = [c for c in d["categories"] if c["kind"] != "income"]
    grid = []
    for c in cats:
        vals = [next((x["spent"] for x in s["budgets"] if x["id"] == c["id"]), 0.0) for s in sums]
        if any(vals):
            grid.append({"id": c["id"], "name": c["name"], "kind": c["kind"], "color": c.get("color"), "values": vals,
                         "total": round(sum(vals), 2), "avg": round(sum(vals) / max(1, sum(1 for s in sums if s["n"])), 2)})
    grid.sort(key=lambda x: -x["total"])
    merchants = defaultdict(lambda: [0.0, 0])
    for t in d["transactions"]:
        if t["date"][:4] == str(year) and t["amount"] < 0 and not t.get("to_account"):
            k = _label_key(t.get("label")) or "?"
            merchants[k][0] += -t["amount"]
            merchants[k][1] += 1
    topm = sorted(([k, round(v[0], 2), v[1]] for k, v in merchants.items()), key=lambda x: -x[1])[:12]
    inc = sum(s["income"] for s in sums)
    spent = sum(s["spent"] for s in sums)
    return {"year": year, "months": months, "summaries": [{k: s[k] for k in ("month", "income", "bills", "expenses", "spent", "saved", "net", "savings_rate", "n")} for s in sums],
            "grid": grid, "merchants": topm, "income": round(inc, 2), "spent": round(spent, 2), "saved": round(sum(s["saved"] for s in sums), 2),
            "savings_rate": round((inc - spent) / inc * 100) if inc > 0 else None}


def fmt_eur(x: float) -> str:
    s = f"{abs(x):,.0f}".replace(",", " ")
    return ("−" if x < 0 else "") + s + " €"


def export_csv(d: dict) -> str:
    cats = {c["id"]: c["name"] for c in d["categories"]}
    accs = {a["id"]: a["name"] for a in d["accounts"]}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Date", "Libellé", "Montant", "Compte", "Vers le compte", "Catégorie", "Note"])
    for t in sorted(d["transactions"], key=lambda t: t["date"]):
        w.writerow([t["date"], t.get("label", ""), f"{t['amount']:.2f}".replace(".", ","), accs.get(t["account"], ""),
                    accs.get(t.get("to_account"), ""), cats.get(t.get("category"), ""), t.get("note", "")])
    return buf.getvalue()
