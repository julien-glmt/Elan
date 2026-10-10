#!/bin/bash
# À lancer SUR LE MAC (double-clic) une fois le Pi prêt et branché sur la box.
# Copie Sub3 et toutes tes données vers le Pi, puis lance l'installation.
cd "$(dirname "$0")/../.." || exit 1
read -r -p "Adresse du Pi (ex. elan-pi.local) : " HOST
read -r -p "Utilisateur du Pi (ex. pi) : " PIUSER
echo "Copie des fichiers (le mot de passe du Pi va être demandé)…"
rsync -av --exclude ".venv" --exclude "__pycache__" --exclude "data_demo" --exclude "_debug_data.tgz" ./ "${PIUSER}@${HOST}:~/sub3/" || { echo "Échec de la copie"; read -n1; exit 1; }
echo "Installation sur le Pi…"
ssh -t "${PIUSER}@${HOST}" "cd ~/sub3 && bash deploy/pi/install.sh"
echo ""
echo "Terminé. IMPORTANT : ne relance plus Sub3 sur le Mac (deux serveurs enverraient les séances en double sur ta montre)."
read -n 1 -s -r -p "Appuie sur une touche pour fermer…"
