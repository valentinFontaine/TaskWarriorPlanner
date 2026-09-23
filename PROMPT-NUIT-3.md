# Run de nuit n°3 — E3 + E4 : ajuster le plan, puis valider pour écrire

Tu travailles seul, sans personne pour répondre. Lis ce fichier en entier avant de
commencer. Tout ce qui pourrait te faire hésiter a un **défaut déclaré** ici : suis-le,
et note dans le rapport chaque fois que tu l'as appliqué.

Deux dépôts :

- **B** = `C:\Users\irpaui\Documents\Projets\perso\TaskWarriorPlanner` (Python,
  `venv/Scripts/python.exe`, branche `main`)
- **A** = `C:\Users\irpaui\Documents\Projets\perso\WebTaskManager` (FastAPI + JS,
  branche `master`)

Lis `B/AGENTS.md`, `A/AGENTS.md`, `B/RESTE-A-FAIRE.md` (sections E, G1bis, H2, H3) et
`B/openspec/changes/ordonnanceur-par-contraintes/design.md` §7 avant d'écrire.

---

## 0. Les règles qui ne se négocient pas

1. **Jamais de commande `task`, de Playwright ni de serveur sans `TASKRC` pointant sur
   la base de test** : `C:/Users/irpaui/taskwarrior-test/taskrc` (ou un `tmp_path` de
   pytest). La vraie base de l'utilisateur est synchronisée par Syncthing sur trois
   machines : une écriture involontaire n'y est pas rattrapable. Ne touche jamais
   `taskwarrior-dev`, `taskWarrior-copie`, ni `~/.task`. En PowerShell, positionne
   `$env:TASKRC` **dans la même commande** que ce qu'il protège.
2. **Aucun `git push`**, aucune PR, aucune issue. Un commit local par étape.
3. **Ne modifie jamais un test pour le faire passer**, ni le code pour contourner un
   test. Un test qui te semble faux : tu t'arrêtes sur ce point, tu l'écris dans le
   rapport, tu passes à l'étape suivante.
4. **Un contrat de test s'écrit d'abord et se voit rouge pour la bonne raison.** Un
   `ImportError` ou un 404 de route absente ne prouve rien : après l'implémentation,
   vérifie le mécanisme **par mutation** (neutralise la ligne qui compte, relance,
   regarde quel test tombe, restaure à l'identique en contrôlant le hash).
5. **Un mock doit avoir la forme de la vraie réponse.** Leçon du 23/09 : les mocks
   renvoyaient `{error: ...}`, le vrai serveur FastAPI rend `{"detail": ...}` ; tout
   était vert et le message ne s'affichait jamais. Pour chaque endpoint mocké, lis
   ce que le vrai code renvoie. Et **toute fonction qui écrit dans la base passe un
   essai de bout en bout sur la base de test**, vrai serveur et vrai Taskwarrior,
   vérifié ensuite par `task export`, avant son commit.
6. **Tu n'inventes aucune valeur de réglage** (grille horaire, marge, durée, coefficient
   d'urgence). Les seules sources sont `base.config` / `base.echeances` de
   `B/tests/base_realiste.py`. Si une valeur manque, crée un fichier `stub_...` dont
   l'en-tête dit où tu as cherché, et liste-le **en tête** du rapport.
7. **Délégation.** Tu peux confier l'écriture du code à des sous-agents
   `implementeur`. Leur brief rappelle les règles 1 à 3. Tu gardes pour toi le
   diagnostic, les contrats, la lecture des mesures et les commits.
8. Commentaires et messages de commit **en français sans accents** ; textes affichés
   à l'utilisateur **avec** accents ; messages de commit longs, qui expliquent le
   pourquoi et portent les mesures.

> Mieux vaut s'arrêter à l'étape 3 avec tout au vert que d'atteindre l'étape 6 avec
> des tests rouges.

---

## 1. Les décisions de l'utilisateur (23/09) — rien à trancher ici

| Sujet | Décision |
|---|---|
| **E3 — déplacer un bloc proposé** | l'ajustement est **écrit tout de suite** dans Taskwarrior : `+fige` et `scheduled` = nouveau début |
| **Après un déplacement** | un calcul **sans écriture** est relancé automatiquement (endpoint E1 existant), pour que le plan affiché intègre l'ajustement |
| **E4 — une tâche déplacée à la main** | reste `+fige` : le solveur ne la bouge plus. Les autres reçoivent `scheduled` **sans** `+fige` |
| **E4 — ce que Valider écrit** | **exactement le plan affiché** (`plan.json`), sans recalcul. Si la base a changé depuis le calcul, Valider **refuse** (409) et demande de recalculer |

Défauts déclarés pour ce que l'utilisateur n'a pas précisé :

- **Seul le premier bloc** (`indice` 0) d'une tâche non `+externe` est déplaçable.
  Raison mesurée : `+fige` n'impose que le début du bloc 0 (`planif/solveur.py:648-652`),
  et Taskwarrior n'a qu'un `scheduled` par tâche. Les autres blocs et les blocs
  `+externe` restent en lecture seule.
- **Un déplacement ne change pas la durée** (pas de redimensionnement en v1).
- **Valider demande une confirmation** avant d'écrire, avec le nombre de tâches concernées.
- **Valider est désactivé** tant qu'aucun plan n'est affiché ou qu'un calcul est en cours.
- **L'empreinte de la base** se calcule côté A : SHA-256 des lignes `uuid|modified`
  triées des tâches `status:pending`, prise **juste avant** de lancer le calcul, et
  gardée avec l'état du calcul. Valider la recalcule et la compare.

---

## 2. Ce qui existe déjà (vérifié le 23/09, relis-le quand même)

- A : les tâches réelles sont affichées depuis `task scheduled.not: export`
  (calendrier `scheduled`) ; les blocs proposés viennent de `/plan.json`, trois
  calendriers `CAL_PLAN_*`, construits dans `construireEvenementsPlan`
  (`calendar-planner.js:137-180`), **en lecture seule** (`isReadOnly: true`, l.152).
  Id d'un bloc : `plan-${uuid}-${indice}` (l.149). Le glisser d'une tâche réelle
  appelle `PUT /api/task/{id}/modify` (l.776-841).
- A : `PUT /api/task/{id}/modify` **efface les tags puis les réécrit**
  (`main_fastapi.py:659-666`). Ne l'utilise **pas** pour poser `+fige` : il faut un
  endpoint dédié qui n'ajoute que `+fige` et `scheduled`.
- A : le calcul (E1) : `POST /api/plan/calculer`, `GET /api/plan/etat`,
  `plan_runner.py` (thread, verrou, commande `[PYTHON, -m, planif, --sortie, ...]`).
  `test_plan_runner.py::test_la_commande_n_ecrit_jamais_dans_la_base` garantit que le
  calcul n'écrit pas. **Ce test doit rester vert et garder son sens.**
- B : `plan.json` (`planif/sortie.py`, design.md §7) : `taches` indexées par uuid,
  `blocs` avec `indice, debut, fin, externe, agrege, opportuniste, precision`.
  **Il ne contient pas les `due` calculées.**
- B : `ecrire_scheduled(plan, env, dry_run, taches_existantes)` (`sortie.py:164-226`)
  et `ecrire_due(plan, taches, env, dry_run, taches_existantes)` (`sortie.py:229-296`),
  idempotentes, rendent `{modifiees, inchangees, ignorees}`, testées sur
  `base_jetable`. Elles prennent un plan **en mémoire**, pas un fichier.
- B : `duePlanif` stocke la valeur écrite par le planificateur ; `est_calculee` =
  `due == duePlanif` (`planif/dues.py`). Une `due` humaine n'est jamais écrasée.
- B : le planificateur lit `config.json` et `echeances.json` à côté du paquet, et
  `reunions.json` dans le répertoire courant, **sans option** pour les désigner
  (`planif/__main__.py:300-301,337`, `planif/reunions.py:50`).
- B : `outils/recharger-base-test.py` recrée `C:/Users/irpaui/taskwarrior-test`
  (50 tâches, `config.json`, `echeances.json`).

---

## 3. Les étapes, dans l'ordre — un commit par étape

### Étape 0 — état et inventaire (aucun code)

- B est sur `main`, A sur `master`. Être en avance d'`origin` est normal (ce prompt
  lui-même est commité localement) ; tu ne pousses rien. L'arbre de travail doit être
  **propre** : dans A, seul `.claude/` est non suivi (un `launch.json` local), c'est
  normal, n'y touche pas et ne le commite pas. Tout autre fichier modifié ou non
  suivi : **arrête le run** et écris-le dans le rapport.
- Lance les suites et note les comptes : `venv/Scripts/python.exe -m pytest -q` dans
  B ; `pytest` dans A ; dans A, avec le `TASKRC` de test :
  `npx playwright test tests/graphe.spec.js tests/graphe-edition.spec.js tests/graphe-depends.spec.js tests/plan-calcul.spec.js`.
  Un rouge au départ : tu le notes, tu ne le corriges pas, tu continues.
- Écris `B/INVENTAIRE-NUIT-3.md` : ce que tu as trouvé à chaque point de la section 2,
  avec fichier et ligne, et tout écart avec ce qui est écrit ici.

### Étape 1 — le planificateur tourne sur la base de test (B, puis A)

Prérequis de tout le reste : sans lui, un calcul sur la base de test utilise la vraie
grille de l'utilisateur et ses vraies réunions Outlook.

- B : options `--config`, `--echeances`, `--reunions` (chemins). Sans option, le
  comportement actuel est **inchangé**.
- B : `outils/recharger-base-test.py` écrit aussi `reunions.json` vide (`[]` ou la
  forme vide que lit `planif/reunions.py`).
- A : `plan_runner.py` passe ces options si les variables d'environnement
  `PLANIFICATEUR_CONFIG`, `PLANIFICATEUR_ECHEANCES` et `PLANIFICATEUR_REUNIONS` sont
  positionnées, sur le modèle de `PLANIFICATEUR_RACINE`.
- **Contrôle de mécanisme :** avec les trois options, `plan.json` ne doit contenir que
  des uuid de la base de test, et aucun bloc ne doit tomber dans une réunion.

### Étape 2 — `plan.json` porte les `due` calculées (B)

- Chaque tâche de `plan.json` gagne `"due"` : la `due` que la passe 1 calcule pour elle,
  ou `null`. Mets à jour le contrat de design.md §7 **dans le même commit**.
- Vérifie que `A/calendar-planner.js` accepte le champ en plus (lecture tolérante).

### Étape 3 — appliquer un `plan.json` sans recalcul (B)

- Nouveau mode `python -m planif --appliquer <plan.json>` : lit le fichier, écrit
  `scheduled` (début du bloc 0 non externe) et `due` + `duePlanif`, **sans aucun
  calcul**, en réutilisant `ecrire_scheduled` / `ecrire_due` (adapte leur entrée si
  besoin, sans changer leur comportement actuel). Il imprime sur stdout un JSON
  `{modifiees, inchangees, ignorees}` pour chacune des deux écritures.
- Il ne pose **jamais** `+fige` (c'est E3 qui le fait).
- Contrats sur `base_jetable` : écrit ce qui est dans le fichier et rien d'autre ; une
  tâche absente de la base va dans `ignorees` ; une `due` humaine n'est pas écrasée ;
  **appliquer deux fois = zéro modifiée la seconde fois** ; `+externe` ignorées.

### Étape 4 — E4 : Valider (A)

- `POST /api/plan/valider` : refuse (409, message en français) si l'empreinte de la base
  a changé depuis le calcul, ou si aucun plan n'existe, ou si un calcul est en cours ;
  sinon lance `--appliquer` sur le `plan.json` affiché et rend le compte rendu.
- `test_la_commande_n_ecrit_jamais_dans_la_base` reste vert : le **calcul** n'écrit
  toujours pas. Ajoute le test symétrique : la commande de validation contient
  `--appliquer` et jamais `--ecrire-scheduled` / `--ecrire-due`.
- UI : bouton « Valider », confirmation, puis compte rendu affiché
  (modifiées / inchangées / ignorées).

### Étape 5 — E3 : déplacer un bloc proposé (A)

- Endpoint dédié, par exemple `POST /api/task/{uuid}/figer` avec `{scheduled}` :
  `task <uuid> modify +fige scheduled:<date>`, **rien d'autre** (les autres tags sont
  préservés). Uuid validé par `fullmatch` d'un uuid canonique avant toute commande
  (`run_task_command` passe par `shell=True` ; voir `test_depends.py`).
- UI : le bloc 0 des tâches non externes devient déplaçable ; au dépôt, appel de
  l'endpoint, puis relance automatique du calcul (E1), puis rechargement du plan.
- Contrats : un test vérifie que les tags existants (`pro`, `externe`, un tag d'acteur)
  **survivent** au figeage.

### Étape 6 — essai de bout en bout, et rapport

Sur `taskwarrior-test` fraîchement rechargée, avec le serveur lancé avec le `TASKRC` et
les trois variables `PLANIFICATEUR_*` pointant sur `taskwarrior-test` :

1. Calculer, puis Valider.
2. Valider une seconde fois sans rien changer.
3. Déplacer le bloc 0 de « Plan de detail carter » (`NPD.Orion.plans`) au lundi
   suivant à 14:00.
4. Vérifier la tâche, puis Valider.

---

## 4. Ce que tu dois observer — lis-le comme un détecteur d'erreur

Ces attentes servent à **détecter une erreur**, pas à valider un résultat. Un écart est
une information : **ne change aucun réglage pour rentrer dedans.**

| Mesure | Attendu | Si ce n'est pas le cas |
|---|---|---|
| 1er Valider | `modifiees + inchangees + ignorees` = nombre de tâches de `plan.json`, et `ignorees` ≥ nombre de tâches `+externe` du plan | une tâche est écrite deux fois ou oubliée |
| 2e Valider, sans changement | **`modifiees` = 0** pour `scheduled` comme pour `due` | l'écriture n'est pas idempotente, ou l'empreinte ne voit pas ses propres écritures |
| 2e Valider après le 1er, sans recalcul | **409** : le 1er Valider a modifié la base | **l'empreinte ne détecte rien** : c'est le contrôle qui compte le plus. Défaut déclaré : après un Valider réussi, l'interface relance un calcul, comme après E3 |
| Déplacement de « Plan de detail carter » | dans `task export` : `+fige` présent, `scheduled` = lundi 14:00, les autres tags **inchangés** | l'endpoint efface des tags |
| Plan recalculé après le déplacement | bloc 0 de « Plan de detail carter » à **exactement** lundi 14:00 ; « Devis fournisseur usinage carter », qui en dépend, commence **après** sa fin | le solveur ne lit pas `+fige`, ou la relance n'a pas eu lieu |
| Calcul (E1) | aucune tâche de la base modifiée (`modified` inchangé partout) | le calcul écrit : régression de la garantie E1 |

Note sur la ligne 3 du tableau. Si le 1er Valider modifie la base, l'empreinte change,
et un 2e Valider sans recalcul **doit** être refusé. Pour obtenir le « `modifiees` = 0 »
de la ligne 2, recalcule entre les deux Valider. **Mesure et rapporte les deux cas.**

---

## 5. Hors périmètre — tu ne fais pas

- Pas de redimensionnement de bloc, pas de déplacement des blocs `indice` > 0 ni des
  `+externe`.
- Pas de « défiger » depuis le calendrier (le tag reste modifiable par l'éditeur).
- Aucun changement du calcul d'urgence ni des réglages du solveur (`TEMPS_DETERMINISTE_MAX`,
  marges, poids).
- Pas de Nextcloud, pas d'import des réunions en `+meeting`, pas de régimes de période.
- Pas de refonte de `calendar-planner.js` au-delà de ce qu'exigent E3 et E4.
- Ne corrige pas un défaut aperçu en route : note-le dans le rapport.

---

## 6. Le rapport — `B/RAPPORT-NUIT-3.md`, commité à la fin (et mis à jour à chaque étape)

Dans cet ordre :

1. **Bouchons `stub_`** et toute valeur que tu as dû supposer (sinon : « aucun »).
2. **Interprétations** : tout ce qui n'était ni écrit ici ni une transcription directe
   du code, même petit.
3. **Mesures** : comptes de tests au départ et à l'arrivée, par suite ; tableau de la
   section 4 rempli avec les valeurs **observées** ; tableaux des mutations.
4. **Frictions** : tests jugés faux (non modifiés), écarts avec la section 2, défauts
   aperçus hors périmètre.
5. **État d'arrivée** : étapes faites, commits (hash + titre), ce qui reste.
