#!/bin/bash
# Installation de Sub3 sur un Raspberry Pi (Raspberry Pi OS Lite 64 bits).
# À lancer SUR le Pi, depuis le dossier sub3 :  bash deploy/pi/install.sh
set -e
cd "$(dirname "$0")/../.."
SUB3_DIR="$(pwd)"
USER_NAME="$(whoami)"

echo "== 1/5 Paquets système"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip rsync curl

echo "== 2/5 Fuseau horaire (indispensable pour les dates et l'envoi auto à 18h)"
sudo timedatectl set-timezone Europe/Paris

echo "== 3/5 Environnement Python"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "== 4/5 Service Sub3 (démarre tout seul, redémarre en cas de souci)"
sed -e "s#__USER__#${USER_NAME}#g" -e "s#__DIR__#${SUB3_DIR}#g" deploy/pi/sub3.service | sudo tee /etc/systemd/system/sub3.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now sub3
sleep 3
systemctl --no-pager --lines=0 status sub3 || true

echo "== 5/5 Tailscale (accès depuis ton téléphone, partout)"
if ! command -v tailscale >/dev/null; then curl -fsSL https://tailscale.com/install.sh | sh; fi
sudo tailscale up || true

IP_LAN=$(hostname -I | awk '{print $1}')
IP_TS=$(tailscale ip -4 2>/dev/null | head -1)
echo ""
echo "============================================================"
echo " Sub3 tourne sur le Pi."
echo "  À la maison : http://${IP_LAN}:8742"
[ -n "$IP_TS" ] && echo "  Partout (Tailscale) : http://${IP_TS}:8742   ou   http://$(hostname):8742"
echo "  Code PIN : $(python3 -c "import json;print(json.load(open('data/config.json'))['pin'])" 2>/dev/null)"
echo "  Logs : journalctl -u sub3 -f"
echo "============================================================"
