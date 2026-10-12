# Mes Finances

Application **locale** de suivi des dépenses : import de relevés CSV, catégorisation (manuelle ou par règles),
dépenses récurrentes / ponctuelles et graphiques mensuels. Les données restent sur votre machine
dans le fichier `finance.db` (SQLite).

## Télécharger

Les versions prêtes à l'emploi (macOS Apple Silicon et Windows) sont sur la page
[Releases](https://github.com/IvanMoz98/personal_finance_app/releases/latest).
Les instructions de premier lancement y sont détaillées (l'application n'est pas signée).

Les données sont stockées dans `~/Library/Application Support/Mes Finances/finance.db` (macOS)
ou `%APPDATA%\Mes Finances\finance.db` (Windows).

## Lancer depuis le code source

Double-cliquez sur `lancer.command` (macOS), ou dans un terminal :

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python app.py
```

Le navigateur s'ouvre sur http://127.0.0.1:5050. Seul votre ordinateur peut accéder au serveur.
En mode source, la base `finance.db` est créée à côté du code.

Pour la version « fenêtre native » (celle des exécutables) :

```bash
.venv/bin/pip install -r requirements-build.txt
```

```bash
.venv/bin/python desktop.py
```

## Utilisation

1. **Comptes** : créez un compte par compte bancaire / carte.
2. **Import CSV** : choisissez le compte, déposez le fichier exporté par votre banque.
   Le séparateur, l'encodage, les lignes d'en-tête de la banque et les colonnes sont détectés automatiquement ;
   vérifiez les colonnes proposées puis importez. Réimporter un relevé qui chevauche le précédent ne crée pas de doublons.
3. **Opérations** : catégorisez (une par une ou par lot en cochant plusieurs lignes), marquez récurrent/ponctuel,
   ajoutez des notes. Le bouton ⚡ crée une règle à partir du libellé.
4. **Catégories & règles** : une règle « le libellé contient X → catégorie Y » s'applique automatiquement
   aux imports suivants. « Détecter les dépenses récurrentes » repère les opérations qui reviennent chaque mois
   avec un montant proche (abonnements, loyer, factures…).
5. **Tableau de bord** : dépenses par catégorie sur 6 à 36 mois, répartition du mois (cliquez sur une barre
   pour changer de mois, sur une catégorie pour voir ses opérations), revenus et dépenses, récurrent et ponctuel.

La catégorie de type **Virement interne** est exclue des statistiques : utilisez-la pour les virements
entre vos propres comptes (sinon ils compteraient comme dépense d'un côté et revenu de l'autre).

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | Serveur Flask : API JSON et calcul des statistiques |
| `desktop.py` | Point d'entrée de l'application de bureau (fenêtre native pywebview) |
| `mes_finances.spec` | Configuration PyInstaller (.app / .exe) |
| `.github/workflows/build.yml` | Compilation automatique et publication des Releases |
| `importer.py` | Lecture des CSV (encodage, séparateur, montants « 1 234,56 », dates, doublons) |
| `db.py` | Schéma SQLite et catégories par défaut |
| `static/` | Interface (HTML / CSS / JavaScript, graphiques Chart.js embarqué dans `static/vendor/`) |
| `exemples/` | Générateur de deux relevés fictifs pour tester |

Sauvegarde : copiez simplement `finance.db`. Pour tester sans toucher à vos données :
`FINANCE_DB=/chemin/demo.db .venv/bin/python app.py`.

## Publier une nouvelle version

Créez un tag commençant par `v` puis poussez-le : GitHub Actions compile les versions macOS et Windows
et crée la Release automatiquement (environ 5 minutes).

```bash
git tag v1.1.0 && git push origin v1.1.0
```

Pour compiler sans publier : onglet **Actions** → **Build** → **Run workflow** (les fichiers sont dans *Artifacts*).
Pour compiler la version Mac en local : `.venv/bin/pyinstaller --noconfirm mes_finances.spec`.
