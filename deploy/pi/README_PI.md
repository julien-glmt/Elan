# Héberger Sub3 sur un Raspberry Pi

Objectif : Sub3 tourne 24 h/24 sans ton Mac (synchro Garmin, envoi auto des séances sur la montre, accès depuis le téléphone partout).

## 1. Le matériel (une seule fois)
- **Raspberry Pi 4 (2 Go suffisent) ou Pi 5**, avec son **alimentation officielle**
- **Carte microSD 32 Go** (classe A1/A2) et un **boîtier** (idéalement avec ventilation passive)
- Un câble Ethernet vers la box (plus fiable que le wifi), sinon le wifi marche aussi

## 2. Préparer la carte SD (sur le Mac, 10 min)
1. Installe **Raspberry Pi Imager** (raspberrypi.com/software).
2. Choisis *Raspberry Pi OS Lite (64-bit)*.
3. Dans les réglages (roue dentée) : nom d'hôte `elan-pi`, active **SSH**, crée ton utilisateur (ex. `pi`) et mot de passe, renseigne le wifi si besoin, fuseau Europe/Paris.
4. Écris la carte, mets-la dans le Pi, branche-le sur la box. Attends 2 minutes.

## 3. Installer Sub3 (5 min)
Sur le Mac, double-clique sur `deploy/pi/migrer-vers-le-pi.command` :
- adresse : `elan-pi.local`, utilisateur : celui choisi à l'étape 2 ;
- le script copie Sub3 **avec toutes tes données** (plan, bilans, jetons Garmin : pas besoin de te reconnecter), installe tout et lance le service ;
- à la fin, il te demande de te connecter à **Tailscale** (lien à ouvrir) : utilise le même compte que sur ton téléphone.

Ensuite :
- **Ne relance plus Sub3 sur le Mac.**
- Sur le téléphone : installe Tailscale (gratuit), connecte-toi, ouvre `http://elan-pi:8742`, entre le PIN, « Sur l'écran d'accueil ».

## 4. Le coach IA
Les passages du coach (7h20 / 21h40) lisent et écrivent les fichiers de Sub3 **via ton Mac**. Deux possibilités :
- **Étape 1 (simple)** : installer **Syncthing** sur le Pi et le Mac pour synchroniser `sub3/data/coach` dans ton dossier « programme ». Le coach marche quand le Mac est allumé au moment du passage ; l'app, elle, marche tout le temps.
- **Étape 2 (sans Mac du tout)** : faire passer l'échange coach ↔ Sub3 par Google Drive (le Pi synchronise un dossier Drive, la tâche Claude lit/écrit dans Drive). À mettre en place ensemble une fois le Pi installé.

## Au quotidien
- Mettre à jour Sub3 : je pousse les fichiers sur ton Mac, puis double-clic sur `migrer-vers-le-pi.command` (il ne recopie que ce qui a changé ; tes données sur le Pi sont conservées si tu ne les modifies pas sur le Mac — voir ci-dessous).
- Voir ce qui se passe : `ssh pi@elan-pi.local` puis `journalctl -u sub3 -f`.
- Redémarrer : `sudo systemctl restart sub3`.

> Attention : après la migration, les données « vivantes » sont sur le Pi. Le script de migration ne doit plus recopier `data/` depuis le Mac (ça écraserait les nouvelles). Je te fournirai un script de mise à jour qui exclut `data/` quand on en sera là.
