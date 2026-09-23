# Rapport — run de nuit n°3 (E3 + E4)

Mis à jour à chaque étape (consigne de reprise : une coupure ne doit rien perdre).

## 1. Bouchons `stub_` et valeurs supposées

Aucun à ce stade.

## 2. Interprétations

- **Reprise après coupure (batterie).** La session a été coupée après le commit de
  l'étape 0 (`6334ef6`) et l'écriture de `tests/test_nuit3_chemins.py` (non suivi).
  Relu en entier à la reprise : complet (290 lignes, dernier test terminé), aucune
  troncature. Aucun sous-agent n'avait été lancé avant la coupure. A était propre
  (seul `.claude/` non suivi).
- Étape 1 : un chemin passé **explicitement** (`--config`, `--echeances`,
  `--reunions`) qui n'existe pas est une **erreur** (code non nul, chemin nommé,
  aucun plan écrit), alors que sans option les fichiers restent optionnels comme
  avant. Raison : sur la base de test, une faute de frappe dans un chemin ferait
  sinon retomber en silence sur un agenda vide ou aucune échéance.

- Étape 1 : les contrats « chemin absent » passaient **avant** l'implémentation,
  pour une mauvaise raison (argparse rejette l'option inconnue en citant sa
  valeur). Ajout, avant implémentation, de `"unrecognized arguments" not in stderr`
  (même correction pour deux refus de l'étape 3). C'est une correction de mon
  propre contrat en phase rouge, pas une retouche pour faire passer du code.
- Étape 1, contrôle de mécanisme « aucun bloc dans une réunion » : avec le
  `reunions.json` vide de la base de test, la condition est triviale. Contrôle
  refait avec un agenda construit : réunion de 06:00 à 22:00 posée sur le jour où
  le témoin (agenda vide) place le plus de blocs.

- Étape 2 : « la `due` que la passe 1 calcule pour elle, ou `null` » est lu
  ainsi : tâche ayant au moins un bloc non opportuniste → `dues_calculees`
  (fin du dernier bloc, ce que `--ecrire-due` écrit) ; tâche de passe 2 → `null`.
  Écart assumé avec `--ecrire-due` existant, qui écrit aussi une `due` sur les
  tâches de passe 2 : la fin d'un placement « au plus tôt » n'est pas une date
  limite. Les `+externe` portent leur valeur (information) ; c'est l'écriture qui
  les ignore. `version` reste 1 (champ ajouté, compatible).
- Étape 2 : la lecture tolérante de `calendar-planner.js` est vérifiée par un test
  Playwright (`tests/plan-valider.spec.js`, bloc « Étape 2 ») : un plan dont les
  tâches portent `due` s'affiche. Vert avant toute modification d'A
  (`planEstValide` ne contrôle que `version` et `taches`).

## 3. Mesures

| Suite | Départ | Arrivée |
|---|---|---|
| B pytest | 273 passed, 1 xfailed | — |
| A pytest | 128 passed | — |
| A Playwright (4 fichiers) | 61 passed | — |

Tableau de la section 4 : à remplir à l'étape 6.

### Étape 1 — mutations

| Mutation | Résultat | Tests tombés |
|---|---|---|
| M1 `--config` ignoré (`chemin=None`) | 1 failed | `test_config_mercredi_seul_…` |
| M2 `--echeances` ignoré | 1 failed | `test_echeances_est_lu_…` |
| M3 `--reunions` ignoré | 1 failed | `test_reunions_est_lu_…` |
| M4 contrôle d'existence retiré | 2 failed | `test_echeances_absent_echoue`, `test_reunions_absent_echoue` (`--config` absent échoue de toute façon : `charger_config` lève en nommant le fichier) |
| M5 recharger n'écrit pas `reunions.json` | 1 failed | `test_recharger_ecrit_un_reunions_json_vide` |
| M6 A : option jamais ajoutée | 4 failed | les trois paramétrés + le test « trois variables » |
| M7 A : `PLANIFICATEUR_REUNIONS` non lue | 2 failed | « trois variables », `[PLANIFICATEUR_REUNIONS]` |

Restauration contrôlée par SHA-256 à chaque mutation : identique.

### Étape 1 — contrôle de mécanisme sur `taskwarrior-test` rechargée (50 tâches)

| Mesure | Valeur |
|---|---|
| tâches dans `plan.json` | 23 |
| uuid hors de la base de test | **0** |
| témoin (agenda vide) : blocs à l'heure le 26/09 | 6 |
| avec réunion 06:00-22:00 le 26/09 : blocs à l'heure dedans | **0** (15 blocs à l'heure au total) |
| tâches dont `modified` a changé pendant le calcul | **0** |

### Étape 2 — mutations (`tests/test_nuit3_plan_due.py`, 7 tests)

| Mutation | Résultat |
|---|---|
| M8 `due` toujours `null` | 5 failed |
| M9 passe 2 non distinguée (`due` partout) | 3 failed |
| M10 `due` = début du premier bloc | 5 failed |

Hash restauré identique à chaque fois.

## 4. Frictions

Voir `INVENTAIRE-NUIT-3.md`, « Écarts et faits notés ».

## 5. État d'arrivée

| Étape | État | Commit |
|---|---|---|
| 0 inventaire | fait | B `6334ef6` |
| 1 chemins | fait | B `88428d4`, A `be7fc84` |
| 2 due dans plan.json | fait | B (ce commit) |
