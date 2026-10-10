# Élan — ton coach perso (running + nutrition)

App perso qui tourne sur ton Mac et s'ouvre dans le navigateur (Mac ou téléphone).

## Lancer
1. Double-clique sur **Lancer Élan.command** (la 1re fois : clic droit → Ouvrir si macOS bloque).
   - Il faut Python 3.10+ ; si absent, le script ouvre python.org.
2. Le navigateur s'ouvre sur `http://localhost:8742`. Connecte ton compte Garmin (e-mail, mot de passe, puis code de vérification si Garmin en demande un).
3. Laisse la fenêtre du Terminal ouverte tant que tu utilises l'app.

### Sur Windows
1. Installe **Python 3.10+** depuis python.org en cochant **« Add python.exe to PATH »**.
2. Double-clique sur **Lancer Elan (Windows).bat** (si Windows affiche « Windows a protégé votre ordinateur » : Informations complémentaires → Exécuter quand même).
3. Le navigateur s'ouvre sur `http://localhost:8742`. Laisse la fenêtre noire ouverte tant que tu utilises l'app.
- La sauvegarde automatique vise iCloud Drive (Mac) : sur Windows, indique un dossier dans `data/config.json` → `"backup_dir": "C:/Users/toi/OneDrive/Elan-sauvegardes"`.

## Sur le téléphone
- Même wifi que le Mac : ouvre l'adresse affichée dans le Terminal (ex. `http://192.168.1.20:8742`), entre le **code PIN** affiché, puis Partager → **Sur l'écran d'accueil**.
- Hors de chez toi : installe **Tailscale** (gratuit) sur le Mac et le téléphone, puis utilise l'adresse Tailscale du Mac (`http://100.x.y.z:8742`).
- Le Mac doit être allumé et Élan lancé.

## Ce que fait l'app
- **Accueil** : J-xx, prédiction Garmin vs objectif, séance du jour, semaine en cours, forme du jour (disponibilité, VFC, sommeil, Body Battery, FC repos, statut, VO2max, charge).
- **Plan** : les semaines jusqu'au marathon, prévu vs réalisé (rapproché automatiquement de tes activités Garmin), édition des séances, envoi d'une séance ou d'une semaine entière sur la montre.
- **Séance** : constructeur (échauffement, blocs répétés, allures cibles par zone ou perso, FC), modèles prêts à l'emploi, envoi + planification Garmin.
- **Analyse** : volume hebdo prévu/réalisé, VFC, FC repos, sommeil, charge, efficacité aérobie, allure vs FC.
- **Activités** : détail de chaque sortie (tours, zones cardio, dynamique de course).

## Le coach intégré
- **Feu du matin** (Accueil) : VFC, FC repos vs ta moyenne 7 j, sommeil, Body Battery, disponibilité Garmin et ratio de charge donnent un feu vert / orange / rouge. En orange ou rouge, un bouton adapte la séance du jour (alléger, raccourcir, footing facile, décaler à demain, repos) et met la montre à jour. « Annuler l'ajustement » remet tout comme avant.
- **Bilan de séance** : dès que la sortie remonte de Garmin, l'app la compare au plan (allure de chaque étape, répétitions dans la cible, FC en endurance, dérive cardiaque, volume) et donne une note sur 100 + des commentaires.
  - Pour un bilan précis des fractionnés, lance la séance depuis la montre (Entraînement → Mes entraînements) : la montre crée un tour par étape.
  - Sans ça (tours auto au km), seuls les blocs de 2 km et plus sont analysés.
- **Séance décalée ?** Dans la séance → « Associer une sortie » pour la rattacher à la bonne sortie (±3 jours).
- **Ressenti** : note d'effort 1-10 + commentaire dans chaque séance.

## Jour J (onglet dédié)
- **Plan d'allure** km par km et par 5 km : passages, heure de passage, stratégie (régulière, léger negative split, départ prudent), correction chaleur (au-delà de 12 °C) et dénivelé si tu importes le GPX du parcours.
- **Bracelet d'allure** à imprimer (3 colonnes à découper) et **séance course** envoyée sur la montre (9 blocs de 5 km, gels notés).
- **Nutrition** : charge glucidique J-3 → J-1 calculée sur ton poids, petit-déj (heure + quantité), gels km par km (avec caféine), boisson et sodium.
- **Météo** : prévision Open-Meteo à l'heure du départ, disponible à J-15 (renseigne la ville).
- **Checklist** du sac, cochée et sauvegardée.

## Coach IA (bouton 💬 en haut)
- Une tâche Claude programmée passe **à 7h20 et 21h40** : message du matin, analyse de chaque séance, réponses à tes questions, et **le dimanche soir** bilan de la semaine avec des ajustements que tu acceptes ou refuses en un clic.
- Élan doit tourner sur le Mac (il prépare `data/coach/context.json` toutes les 5 min) et l'app Claude doit être ouverte et liée au Mac au moment du passage.
- Les messages arrivent dans `data/coach/out/` et s'affichent dans l'onglet Coach. Les consignes du coach sont à écrire dans un fichier `COACH_INSTRUCTIONS.md` (non fourni).

## Nutrition, prédiction, carte, calendrier
- **Onglet Nutrition** : classement S-A-B-C-D de tes gels (notes ventre / goût / praticité / texture, le ventre compte le plus), stock restant, gels à racheter pour la prépa et le jour J.
- **Ravitaillement** : dans le détail d'une séance (sortie de 75 min et plus), note ce que tu as pris ; l'app calcule tes g/h et ml/h et décompte le stock.
- **Fiche veille de sortie longue** sur l'accueil (gels, horaires, eau, repas) ; le coach du soir te l'envoie aussi.
- **Prédiction marathon maison** (Jour J > Course) : Riegel, semi × 2,11, Tanda, tes blocs à allure marathon, Garmin, avec l'historique.
- **Carte du parcours** dans le détail d'une sortie, colorée par allure ou FC.
- **Plan > Mois** : vue calendrier.
- Les sorties apparaissent dans l'app environ 5 min après la synchro Garmin.

## Accueil et modules
- À l'ouverture, l'accueil animé propose **Running** (tout le suivi de prépa) ou **Nutrition**. Le logo Élan (en haut à gauche) ou le bouton Élan de la barre du bas ramène à l'accueil ; le sélecteur Running / Nutrition de la barre latérale passe d'un module à l'autre.
- **Nutrition** : chaque jour, la dépense vient de ta montre (calories totales Garmin, projetée jusqu'au soir pour aujourd'hui), tu notes ce que tu as mangé (ajout rapide par repas) et ton poids si tu t'es pesé. L'app calcule le bilan, le déficit cumulé, la perte estimée, le poids moyen sur 7 jours, la tendance et la date d'arrivée estimée. Elle limite le déficit conseillé les jours de sortie longue, de séance clé et avant une course.
- Les données sont dans `data/body.json`. L'ancien onglet « Nutrition » du running s'appelle maintenant **Ravito** (gels, stock, ravitaillement).

## Finances
- **Vue d'ensemble** du mois (reste à dépenser, revenus, dépenses, épargne, taux d'épargne), patrimoine, où part l'argent, prélèvements à venir, objectifs, alertes de budget.
- **Opérations** : saisie rapide, recherche et filtres, import du relevé CSV de ta banque (doublons détectés, catégories proposées et apprises), export CSV.
- **Budget** par catégorie (dépenses variables et charges fixes), avec projection de fin de mois. **Abonnements** : loyer, énergie, mobile, salaire, virements d'épargne… ajoutés automatiquement chaque mois.
- **Patrimoine** : comptes (courant, livrets, PEA, CTO, crypto, épargne salariale, titres-resto), mise à jour des valeurs, objectifs d'épargne. **Analyse** annuelle par catégorie et par marchand.
- « Mode discret » floute les montants (pratique en public). Données dans `data/finance.json`.

## Vu & Lu
- Séries, films, animés, mangas et livres, sans compte externe : tape un titre, l'app trouve l'affiche, le nombre d'épisodes, de chapitres ou de pages (catalogues gratuits : TVmaze, iTunes, AniList, Google Books / Open Library). Si rien ne sort, « Ajouter à la main ».
- **En cours** : bouton « +1 épisode / chapitre », page en cours pour les livres, épisode suivant (S2 · E5), épisodes à rattraper et sorties à venir (mis à jour toutes les 12 h).
- **Bibliothèque** filtrable (type, statut, recherche), fiche avec note sur 5, dates et avis. **Bilan** : heures par mois, genres, top de l'année.
- Données dans `data/media.json`.

## Saison : bilans de course et prochaine prépa
- **Saison → Bilans de course** : pour chaque course (celles du plan + celles marquées « Course » dans Garmin), allure km par km comparée au plan de course, avance/retard cumulé, passages tous les 5 km, décrochage, dérive cardiaque, ravitaillement réel, la prépa en chiffres, quelle prédiction était la plus juste, et les leçons à garder. Ajoute ton temps officiel et ton ressenti.
- **Saison → Prochaine prépa** : choisis ta course, ta date, ton objectif et ton organisation. Le plan est calculé avec le modèle VDOT de Jack Daniels (allures), une périodisation foncier → développement → spécifique → affûtage, une semaine allégée toutes les 4 semaines et +10 % de volume maximum par semaine. Tes leçons de bilan sont ajoutées aux règles du plan.
- Le plan reste un **brouillon** tant que tu ne l'actives pas. À l'activation, l'ancien plan est archivé dans `data/archive/`, l'historique est conservé, et la page Jour J passe sur la nouvelle course.

## Raspberry Pi
Voir `deploy/pi/README_PI.md` (matériel, installation, migration depuis le Mac).

## Données
- Tout reste sur ton Mac, dans `data/` : `plan.json` (ton plan), `garmin_tokens.json` (session Garmin), `cache/`.
- Les allures (EF, AM, SEUIL…) se règlent dans ⚙️ Réglages et s'appliquent à toutes les séances. Après un changement, renvoie les séances déjà sur la montre.
- Mode démo sans compte : `SUB3_DEMO=1 .venv/bin/python server.py`.

## À savoir
Garmin n'a pas d'API publique pour les particuliers : l'app utilise la librairie non officielle `garminconnect`. Si Garmin change quelque chose, une mise à jour de la librairie peut être nécessaire (`.venv/bin/pip install -U garminconnect`).
