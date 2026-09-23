# Inventaire — run de nuit n°3 (étape 0)

Relevé le 23/09/2026, avant toute écriture de code. Chaque point de la section 2 de
`PROMPT-NUIT-3.md`, avec fichier et ligne, puis les écarts.

## État de départ

| Dépôt | Branche | Arbre | Dernier commit |
|---|---|---|---|
| B (TaskWarriorPlanner) | `main` | propre | `1ae66d5 Run de nuit n3 prepare : E3 + E4` |
| A (WebTaskManager) | `master` | propre sauf `.claude/` (non suivi, normal) | `7c489f2 H2 : creer et retirer des dependances depuis le graphe` |

| Suite | Résultat de départ |
|---|---|
| B `venv/Scripts/python.exe -m pytest -q` | **273 passed, 1 xfailed** (452 s) |
| A `venv/Scripts/python.exe -m pytest -q` | **128 passed** |
| A Playwright (4 fichiers : graphe, graphe-edition, graphe-depends, plan-calcul), `TASKRC=taskwarrior-test` | **61 passed** (2,4 min) |

Aucun rouge au départ.

## Section 2, point par point

### A — affichage du plan (`calendar-planner.js`)

- Tâches réelles : `GET /api/tasks/planned` → `task scheduled.not: export`
  (`main_fastapi.py:294-297`). Conforme.
- `construireEvenementsPlan` : `calendar-planner.js:137-180`. Conforme.
  Id d'un bloc `plan-${uuid}-${bloc.indice}` l.149, `isReadOnly: true` l.152. Conforme.
  `raw` porte `{uuid, regime, agrege, projet}` (l.153) : **ni `indice` ni `externe`
  explicite** (le régime `externe` se lit dans `raw.regime`).
- Glisser d'une tâche réelle : `handleBeforeUpdateEvent`, l.776-842, appelle
  `modifyTaskInBackend` → `PUT /api/task/{id}/modify`. Conforme. Remarque : ce
  gestionnaire envoie aussi un `estTime` recalculé depuis la durée du créneau
  (l.808-820). Un événement `plan-…` qui deviendrait déplaçable passerait par ce
  chemin avec l'id `plan-<uuid>-0` : il faut une branche dédiée **avant**.
- Lecture du plan : `planEstValide` (l.89-96) ne contrôle que `version === 1` et
  `taches` objet. Un champ en plus dans une tâche est ignoré sans erreur.

### A — `PUT /api/task/{id}/modify` efface les tags

`main_fastapi.py:659-666` : `task rc.confirmation=off {id} modify -TAGS`, puis
réécriture des tags reçus. Conforme : inutilisable pour poser `+fige`.

### A — le calcul (E1)

- `POST /api/plan/calculer` (`main_fastapi.py:267-281`), `GET /api/plan/etat`
  (l.284-291). Conforme.
- `plan_runner.py` : thread + verrou (l.51, 122-141), commande
  `[PYTHON, "-m", "planif", "--sortie", abspath(sortie)]` (l.72-78), exécutée avec
  `cwd=RACINE` (l.83). Conforme.
- `test_plan_runner.py::test_la_commande_n_ecrit_jamais_dans_la_base` (l.69-80) :
  vérifie l'absence de `--ecrire-scheduled`, `--ecrire-due` et `modify` dans la
  ligne jointe. Conforme.
- **Forme des refus d'E1** : `ResponseModel(success=False, error=...)` avec un
  **HTTP 200** (l.279-280), et non une `HTTPException`. Les endpoints H2
  (`/depends`, l.825-856) utilisent `HTTPException` → `{"detail": ...}`. Valider
  (409 demandé) suivra la forme `HTTPException`, donc `{"detail": ...}`.
- Validation d'uuid : `UUID_CANONIQUE_RE` + `_est_uuid_canonique` (`fullmatch`),
  l.810-816, réutilisable pour E3.

### B — `plan.json`

- `planif/sortie.py::plan_en_dict` (l.75-132) : `taches` indexées par uuid, `blocs`
  avec `indice, debut, fin, externe, agrege, opportuniste, precision`, plus `debut`,
  `fin`, `description`, `projet` par tâche. **Pas de `due`.** Conforme.
- Blocs triés par `(debut, indice)` (l.114) ; `debut` de la tâche = début du premier
  bloc dans ce tri.

### B — les deux écritures

- `ecrire_scheduled(plan, env, dry_run, taches_existantes)` : `sortie.py:164-226`.
  Conforme. `scheduled` = **plus petit début de bloc** (l.190-197), pas
  littéralement « le bloc d'indice 0 » ; les deux coïncident si le bloc 0 est le
  premier dans le temps.
- `ecrire_due(plan, taches, env, dry_run, taches_existantes)` : `sortie.py:229-295`.
  Conforme. La valeur vient de `dues_calculees(plan, taches)` (`planif/dues.py:37-47`)
  = fin du dernier bloc, **pour toute tâche placée, passe 2 comprise**.
- Les deux prennent un `Plan` en mémoire (`plan.blocs`, `plan.t0`,
  `plan.granularite`, `plan.instants`). Conforme.

### B — `duePlanif`

`planif/dues.py:55-69` : `est_calculee(t) = t.due is not None and t.due == t.due_planif`.
Conforme.

### B — chemins de configuration

- `planif/__main__.py:300-301` : `charger_echeances()` et `charger_config(...)` sans
  chemin → `config.json` / `echeances.json` à la racine de B (`planif/config.py:17,23`).
- `planif/__main__.py:337` : `charger_reunions(t0, horizon_fin)` sans source →
  `reunions.json` du **répertoire courant** (`planif/reunions.py:50,81`).
- Les deux chargeurs acceptent **déjà** un chemin (`charger_config(chemin)`,
  `charger_echeances(chemin)`, `reunions(debut, fin, source)`) : seules les options
  de ligne de commande manquent. Conforme.

### B — `outils/recharger-base-test.py`

Recrée `C:/Users/irpaui/taskwarrior-test` (taskrc, `data/.jetable`, 50 tâches,
`config.json`, `echeances.json`), l.81-98. N'écrit pas de `reunions.json`. Conforme.

## Écarts et faits notés

1. **Il n'y a pas de `reunions.json` dans B aujourd'hui** (`ls` à la racine) : un
   calcul lancé depuis A (cwd = B) ne lit donc *aucune* réunion sur ce PC, avec un
   avertissement. Le risque « ses vraies réunions Outlook » du prompt est latent
   (dès qu'une extraction Outlook aura tourné), pas actuel. En revanche la **vraie
   grille** (`B/config.json`) et les **vraies échéances** (`B/echeances.json`) sont
   bien lues aujourd'hui par un calcul sur la base de test.
2. **Écart de comportement dans le flux `--ecrire-due` existant** (hors périmètre,
   non corrigé) : `ecrire_due` reçoit les tâches **après**
   `appliquer_echeances_projet` (`__main__.py:314,396`). Une tâche terminale qui a
   hérité l'échéance de son projet a `due` posé et `due_planif` vide :
   `est_calculee` est faux, elle est donc classée « engagement humain » et
   **ignorée** — sa `due` calculée n'est jamais écrite. Voir l'interprétation de
   l'étape 2 dans le rapport : `plan.json` reproduit ce comportement plutôt que de
   le changer.
3. `test_plan_runner.py` appelle `POST /api/plan/calculer` sous pytest, où
   `DEVELOPER_MODE=True` fait rendre à `run_task_command` un texte non JSON : une
   empreinte prise dans cet endpoint doit tolérer une sortie illisible (sans quoi
   des tests existants tomberaient).
