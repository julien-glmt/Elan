"""Sauvegarde automatique d'Élan (code + données) dans iCloud Drive, une fois par jour.

Si le Mac disparaît, il suffit de dézipper la dernière sauvegarde sur un autre Mac (ou le Raspberry Pi)
et de relancer « Lancer Élan.command ». Seule la connexion Garmin est à refaire (les jetons ne sont pas copiés).
"""
from __future__ import annotations

import json
import os
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

ICLOUD = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
SKIP_DIRS = {".venv", "venv", "__pycache__", "cache", ".git", "node_modules", "data_demo"}
SKIP_FILES = {"garmin_tokens.json", ".DS_Store"}
KEEP_DAILY = 14  # + la première sauvegarde de chaque mois, gardée un an


def target_dir(cfg: dict) -> Path | None:
    if cfg.get("backup_dir"):
        return Path(cfg["backup_dir"]).expanduser()
    if ICLOUD.exists():
        return ICLOUD / "Élan – sauvegardes"
    return None


def _files(root: Path):
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f in SKIP_FILES or f.endswith((".tmp", ".log", ".zip", ".partial")) or "garmin_tokens" in f:
                continue
            p = Path(cur) / f
            yield p, p.relative_to(root)


def run(root: Path, cfg: dict, force: bool = False) -> dict:
    dest = target_dir(cfg)
    if dest is None:
        return {"ok": False, "error": "iCloud Drive introuvable sur cet ordinateur : indique un dossier de sauvegarde dans data/config.json (« backup_dir »)."}
    dest.mkdir(parents=True, exist_ok=True)
    name = f"elan-{date.today().isoformat()}.zip"
    out = dest / name
    if out.exists() and not force:
        return status(cfg)
    tmp = dest / (name + ".partial")
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in _files(root):
            try:
                z.write(p, Path("Elan") / rel)
                n += 1
            except OSError:
                pass
        z.writestr("Elan/RESTAURER.txt",
                   "Pour restaurer Élan : dézippe ce dossier (par exemple dans Documents/programme/sub3), "
                   "puis double-clique sur « Lancer Élan.command ». Reconnecte ensuite ton compte Garmin dans Réglages.\n")
    tmp.replace(out)
    _prune(dest)
    return status(cfg)


def _prune(dest: Path) -> None:
    zips = sorted(dest.glob("elan-*.zip"))
    keep = set(zips[-KEEP_DAILY:])
    months = {}
    for z in zips:
        d = z.stem[5:15]
        months.setdefault(d[:7], z)
    cutoff = (date.today() - timedelta(days=365)).isoformat()[:7]
    keep |= {z for m, z in months.items() if m >= cutoff}
    for z in zips:
        if z not in keep:
            try:
                z.unlink()
            except OSError:
                pass


def status(cfg: dict, root: Path | None = None) -> dict:
    dest = target_dir(cfg)
    zips = sorted(dest.glob("elan-*.zip")) if dest and dest.exists() else []
    last = zips[-1] if zips else None
    return {"ok": dest is not None, "dir": str(dest) if dest else None, "count": len(zips),
            "last": datetime.fromtimestamp(last.stat().st_mtime).isoformat(timespec="minutes") if last else None,
            "last_file": last.name if last else None, "size_mb": round(last.stat().st_size / 1e6, 1) if last else None,
            "error": None if dest else "iCloud Drive introuvable : indique un dossier « backup_dir » dans data/config.json."}
