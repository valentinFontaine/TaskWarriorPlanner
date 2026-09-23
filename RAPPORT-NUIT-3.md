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

### Étape 3 — mutations (`tests/test_nuit3_appliquer.py`, 17 tests, sur `base_jetable`)

| Mutation | Résultat |
|---|---|
| M22 `dues` du fichier ignorées (recalcul `dues_calculees`) | 2 failed (`due` nulle écrite) |
| M23 `due` humaine écrasée | 2 failed |
| M24 tâches de la base non lues (`taches = []`) | 2 failed |
| M25 `scheduled` en `dry_run` | 5 failed |
| M26 combinaison avec `--ecrire-*` permise | 2 failed |
| M27 version non contrôlée | 1 failed |
| M28 idempotence de la `due` cassée | 1 failed (`appliquer deux fois`) |
| M29 tâche absente de `dues` non ignorée | 12 errors (KeyError dans la fixture) |

### Étape 4 — mutations (A : `test_nuit3_valider.py` 14 tests, `tests/plan-valider.spec.js` 9 tests)

| Mutation | Résultat | Tests tombés |
|---|---|---|
| M11 empreinte sans `modified` | 3 failed | sha256, ordre/modified, « base a changé » |
| M12 Valider ne compare pas l'empreinte | 1 failed | `test_si_la_base_a_change_valider_refuse_sans_rien_ecrire` |
| M13 empreinte non prise au calcul | 5 failed | dont « prise au lancement », succès, 500 |
| M14 validation par `--ecrire-scheduled` | 1 failed | test symétrique `…applique_le_plan_sans_recalcul` |
| M15 statut `termine` non exigé | 1 failed | « après un calcul en échec » |
| M16 refus pendant calcul retiré | 1 failed | « pendant un calcul » |
| M17 plan absent non vérifié | 1 failed | « plan absent » |
| M18 JS confirmation court-circuitée | 1 failed | « la refuser n'envoie rien » |
| M19 JS pas de relance après succès | 1 failed | « un calcul est relancé » |
| M20 JS bouton actif sans plan / pendant calcul | 2 failed | les deux « désactivé » |
| M21 JS lit `error` au lieu de `detail` | 2 failed | 409 et 500 |

### Étapes 3 + 4 — essai réel (vrai serveur :8011, vrai Taskwarrior, `taskwarrior-test` rechargée, `PLANIFICATEUR_*` sur la base de test)

| Mesure | Valeur observée |
|---|---|
| calcul 1 : tâches dont `modified` a changé | 0 |
| `plan.json` : tâches / `+externe` / `due` non nulle | 23 / **0** / 16 |
| Valider 1 : `scheduled` | 23 modifiées, 0 inchangées, 0 ignorées (somme 23) |
| Valider 1 : `due` | 16 modifiées, 0 inchangées, 7 ignorées (somme 23 ; les 7 = `due` nulles, toutes de passe 2) |
| `task export` après Valider 1 | 23/23 `scheduled` = début du premier bloc ; 16/16 `due` = `duePlanif` = valeur du fichier ; 7/7 sans `due` ; 0 `+fige` posé |
| Valider 2 **sans** recalcul | **409** « La base a changé depuis le calcul : recalculez avant de valider. » ; 0 tâche modifiée |
| calcul 2 : tâches dont `modified` a changé | 0 |
| Valider 2 **après** recalcul | `scheduled` 0 modifiée / 23 inchangées ; `due` 0 modifiée / 16 inchangées / 7 ignorées ; 0 tâche modifiée en base |

## 4. Frictions

Voir `INVENTAIRE-NUIT-3.md`, « Écarts et faits notés ». En plus :

- **Tests jugés faux** : aucun.
- **Écart avec la section 2** : le prompt redoute que le calcul lise « ses vraies
  réunions Outlook » ; il n'existe pas de `reunions.json` dans B sur ce PC. Le
  risque était latent, il est maintenant couvert.
- **Défaut aperçu, hors périmètre, non corrigé** : dans le flux
  `--ecrire-due` existant, une tâche terminale qui hérite l'échéance de son projet
  est classée « engagement humain » (sa `due` est posée par
  `appliquer_echeances_projet`, sans `duePlanif`) et **ignorée** : sa `due`
  calculée n'est jamais écrite. `--appliquer` lit la base sans appliquer les
  échéances de projet, donc ne reproduit pas ce défaut : sur ces tâches, Valider
  écrit la `due` calculée, `--ecrire-due` non. À trancher par l'utilisateur.
- **Écart assumé** entre `--appliquer` et `--ecrire-due` sur les tâches de passe 2
  (voir interprétations, étape 2).
- **Défaut aperçu, grave, hors périmètre, non corrigé : les prédécesseurs non datés
  sortent de la passe 1, et la précédence avec eux.** `planif/__main__.py` ne donne à
  `resoudre` que `taches_datees` (`t.due is not None`). Une échéance de projet ne se
  pose que sur les terminales (`planif/echeances.py`) ; leurs prédécesseurs, sans
  `due`, partent en passe 2, et `resoudre` ne pose une précédence que si le
  prédécesseur est dans le modèle (`if predecesseur in fins`, `solveur.py`). Mesuré
  sur `taskwarrior-test` fraîche : « Plan de detail carter » et « Devis fournisseur
  usinage carter » sont **absents** de `plan.json` alors que leur successeur
  « Essai fonctionnel carter » y est ; **aucune des 5 tâches `+externe`** n'est
  dans le plan ; la tâche `+fige` du scénario S9 non plus. Le délai fournisseur et
  la chaîne, qui sont la raison d'être de l'ordonnanceur, ne contraignent donc pas
  le plan produit par la ligne de commande. Les tests du solveur passent parce
  qu'ils appellent `resoudre` avec toutes les tâches. À reproduire en test puis
  corriger dans un run dédié.
- **Défaut aperçu, hors périmètre** : dans ce même plan, « Essai fonctionnel
  carter » a son bloc `indice 1` (04/12) **avant** son bloc `indice 0` (11/12). Or
  `+fige` impose le début du bloc d'indice 0 (`solveur.py`, contrainte 8), alors
  qu'`ecrire_scheduled` écrit le début du bloc le plus tôt : sur une telle tâche,
  figer à la valeur de `scheduled` ne fige pas le bloc qu'on croit.
- `POST /api/plan/valider` est `async` et lance `--appliquer` de façon synchrone :
  le serveur ne répond à rien d'autre pendant l'écriture (≈ quelques secondes pour
  23 tâches). Acceptable en v1, à noter si la base grossit.

## 5. État d'arrivée

| Étape | État | Commit |
|---|---|---|
| 0 inventaire | fait | B `6334ef6` |
| 1 chemins | fait | B `88428d4`, A `be7fc84` |
| 2 due dans plan.json | fait | B `595773c` |
| 3 --appliquer | fait | B (ce commit) |
