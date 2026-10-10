#!/bin/bash
# Double-clique sur ce fichier pour lancer Élan.
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "Il faut Python 3.10 ou plus récent."
  echo "Installe-le depuis https://www.python.org/downloads/ (bouton « Download Python »),"
  echo "puis double-clique à nouveau sur « Lancer Élan »."
  open "https://www.python.org/downloads/"
  read -n 1 -s -r -p "Appuie sur une touche pour fermer…"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Première installation (une minute)…"
  "$PY" -m venv .venv || exit 1
fi
REQ_HASH=$(shasum requirements.txt | cut -d' ' -f1)
if [ ! -f .venv/.req_hash ] || [ "$(cat .venv/.req_hash)" != "$REQ_HASH" ]; then
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt || { read -n 1 -s -r -p "Erreur d'installation. Touche pour fermer…"; exit 1; }
  echo "$REQ_HASH" > .venv/.req_hash
fi

# Arrête une ancienne version d’Élan restée allumée en arrière-plan
OLD=$(lsof -ti tcp:8742 -sTCP:LISTEN 2>/dev/null)
if [ -n "$OLD" ]; then
  echo "Arrêt de l'ancienne version d’Élan…"
  kill $OLD 2>/dev/null; sleep 2
  OLD=$(lsof -ti tcp:8742 -sTCP:LISTEN 2>/dev/null); [ -n "$OLD" ] && kill -9 $OLD 2>/dev/null; sleep 1
fi

(sleep 2; open "http://localhost:8742") &
# caffeinate empêche le Mac de se mettre en veille tant qu’Élan tourne
# (indispensable pour l'envoi auto sur la montre et les passages du coach à 7h20 / 21h40)
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i .venv/bin/python server.py
else
  exec .venv/bin/python server.py
fi
