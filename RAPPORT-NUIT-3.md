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
- Étape 4 : l'empreinte est prise dans `POST /api/plan/calculer` par
  `run_task_command` (donc neutralisée par `DEVELOPER_MODE` sous pytest) plutôt
  que dans `plan_runner`, qui aurait lancé un vrai `task` sans `TASKRC` pendant
  la suite pytest d'A. Une empreinte illisible → Valider refuse (409). Les refus
  suivent la forme `HTTPException` / `{"detail"}` (H2), pas le
  `success:false` en HTTP 200 d'E1.
- Étape 4 : après un Valider, l'état du calcul reste « terminé » et son empreinte
  inchangée : c'est ce qui rend le 409 d'un second Valider mesurable. Pendant
  l'écriture, l'état passe à « validation » (calcul refusé).
- Étape 5 : les blocs **agrégés** (`precision: "jour"`) restent en lecture seule
  même s'ils sont d'indice 0 : leur heure n'est pas garantie et un dépôt en
  journée entière donnerait minuit. Mesure a posteriori : figer une telle tâche
  (par l'endpoint) rend la passe 1 infaisable, ce qui conforte la restriction.
- Étape 5 : l'endpoint prend la date en UTC compacte (`YYYYMMDDTHHMMSSZ`), la
  forme qu'écrit l'ordonnanceur, sans ambiguïté de fuseau et validable par
  `fullmatch`.
- Étape 6 : carter n'ayant aucun bloc dans le plan, son déplacement a été fait
  par l'endpoint réel suivi d'une relance du calcul (la séquence exacte de
  l'interface) ; le vrai glisser a été fait sur une tâche qui avait un bloc 0
  déplaçable.

## 3. Mesures

| Suite | Départ | Arrivée |
|---|---|---|
| B pytest | 273 passed, 1 xfailed | **306 passed, 1 xfailed** (+33 : 9 + 7 + 17) |
| A pytest | 128 passed | **164 passed** (+36 : 6 + 14 + 16) |
| A Playwright (graphe ×3, plan-calcul) | 61 passed | 61 passed |
| A Playwright + plan-valider + plan-figer | — | **76 passed** (+15 : 9 + 6) |

### Tableau de la section 4 — valeurs observées (étape 6, `taskwarrior-test` rechargée, serveur :8011)

| Mesure | Attendu | Observé | Verdict |
|---|---|---|---|
| 1er Valider | somme = nb de tâches du plan ; `ignorees` ≥ nb `+externe` du plan | `scheduled` 23 + 0 + 0 = 23 ; `due` 16 + 0 + 7 = 23 ; 0 `+externe` dans le plan (0 ≥ 0) | conforme, mais **la seconde condition est vide** : aucune des 5 tâches `+externe` de la base n'est dans le plan (défaut « prédécesseurs non datés », Frictions) |
| 2e Valider sans changement (après recalcul) | `modifiees` = 0 pour `scheduled` et `due` | `scheduled` 0 / 23 inchangées ; `due` 0 / 16 inchangées / 7 ignorées ; 0 tâche modifiée en base | **conforme** |
| 2e Valider après le 1er, sans recalcul | **409** | **409** « La base a changé depuis le calcul : recalculez avant de valider. », 0 tâche modifiée | **conforme** |
| Déplacement de « Plan de detail carter » | `+fige`, `scheduled` = lundi 14:00, autres tags inchangés | tags `["pro"]` → `["fige","pro"]` ; `scheduled` = `20260928T120000Z` (lundi 28/09 14:00 local) ; aucune autre tâche modifiée | **conforme**, mais par l'endpoint réel et non par un glisser : carter **n'a aucun bloc dans le plan** (voir ligne suivante). Le vrai glisser à la souris a été fait sur une autre tâche (ci-dessous) |
| Plan recalculé après le déplacement | bloc 0 de carter à lundi 14:00 ; « Devis… carter » après sa fin | carter **absent** du plan recalculé ; « Devis fournisseur usinage carter » **absent** aussi | **écart**. Cause mesurée : ni carter ni devis n'ont de `due` (seule la terminale « Essai fonctionnel carter » hérite l'échéance du projet), ils partent en passe 2, qui les écarte faute de capacité et **ignore `+fige`**. Aucun réglage n'a été touché |
| Calcul (E1) | aucune tâche modifiée | 0 tâche au `modified` changé, sur 4 calculs mesurés | **conforme** |

Mesures complémentaires, faites pour attribuer l'écart de la ligne 5 (même base, même serveur) :

| Essai | Observé |
|---|---|
| vrai glisser à la souris (Playwright hors suite, vrai serveur) du bloc 0 de « Trouver logement » (passe 2, perso) | `POST /figer` émis par le calendrier ; `task export` : `["fige","perso"]`, rien d'autre modifié ; calcul relancé. L'heure de dépôt obtenue (22:30 au lieu de 16:00 visé) vient de mon calcul de coordonnées, pas de l'application |
| plan recalculé après ce glisser | bloc 0 **resté à 07:00** : la passe 2 ignore `+fige` |
| `+fige` d'une tâche de passe 2 sur un créneau de sa grille (« Signer bail location », sam. 09:00) | plan : bloc 0 resté à 10:00 |
| `+fige` d'une tâche de passe 1 en régime agrégé sur un créneau de sa grille (« Relire note de calcul préliminaire », mar. 29/09 14:00) | la passe 1 devient **INFEASIBLE, 0 tâche placée** ; le calcul est rapporté « terminé » à l'interface. Même base sans ce seul `+fige` : OPTIMAL, 16 tâches |
| Valider sur ce plan INFEASIBLE | accepté (HTTP 200) : 2 `scheduled` modifiés — **les deux tâches de passe 2 figées à la main ont été ramenées au plan** (22:30 → 07:00, 09:00 → 10:00), `+fige` conservé |
| blocs déplaçables dans ce plan | seuls les 7 blocs de passe 2 (perso) sont « à l'heure » ; les 16 tâches de passe 1 sont toutes en régime agrégé (échéances à 7-12 semaines, base « détendue ») |

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

### Étape 5 — mutations (A : `test_nuit3_figer.py` 16 tests, `tests/plan-figer.spec.js` 6 tests ; un seul lanceur, hash contrôlé)

| Mutation | Résultat | Tests tombés |
|---|---|---|
| M30 uuid non validé | 4 failed | les 4 uuid non canoniques |
| M31 date non validée | 6 failed | les 6 dates hors format |
| M32 `-TAGS` dans la commande de figeage | 2 failed | commande exacte, « aucun tag effacé » |
| M32b `modify -TAGS` séparé avant le figeage | **survit** | mutation équivalente sur ce binaire : `-TAGS` n'efface rien (mesuré, voir Frictions) |
| M33 JS tout en lecture seule | 1 failed | « seul le bloc 0 … est déplaçable » |
| M34 JS pas de relance | 1 failed | « le calcul est relancé puis le plan relu » |
| M35 JS bloc de plan vers `PUT /modify` | 5 failed | |
| M36 JS garde « redimensionnement » retirée | **survit** | garde redondante : `extractDateFromToastChange(undefined)` rend déjà `null` |
| M36b JS redimensionnement pris pour un déplacement | 1 failed | « un redimensionnement n'écrit rien » |
| M37 JS garde indice/externe retirée | 1 failed | « bloc d'indice 1 ou externe » |
| M38 JS lit `error` au lieu de `detail` | 1 failed | « refus du serveur » |

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
- **Incident d'instrument (étape 5), corrigé** : j'ai arrêté un lanceur de
  mutations en cours (motifs `\r\n` alors que l'implémenteur avait réécrit
  `calendar-planner.js` en LF). L'arrêt n'a tué que l'enveloppe bash, pas le
  processus Python : deux lanceurs ont tourné en même temps et deux mutations sont
  restées en place (`-TAGS` dans `/figer`, `isReadOnly = true`). Repéré par
  relecture des lignes clés, restauré à la main, contrôlé : le diff revient à
  121 lignes changées, identique à la remise de l'implémenteur. Les mutations
  concernées ont été relancées avec un seul lanceur, et les suites complètes ont
  été rejouées après. Les résultats de mutation de ce double passage n'ont servi
  que pour les lignes à hash contrôlé.
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
- **Écart avec la section 2, mesuré : `modify -TAGS` n'efface rien sur ce
  binaire.** Sur une base jetable (Taskwarrior 3.5.0, fork wilt00), `task <uuid>
  modify -TAGS` rend 0 et laisse `["acteurDupont","externe","pro"]` intacts, par
  `shell=True`/cmd.exe comme en direct ; `modify -pro` retire bien `pro`. Donc
  `PUT /api/task/{id}/modify` n'efface pas les tags ici — mais, symétriquement, il
  ne peut **jamais retirer** un tag décoché dans l'éditeur (il ne fait que
  réajouter la liste). Défaut probable hors périmètre, non vérifié côté
  interface, non vérifié sur le binaire amont du téléphone. Conséquence pour E3 :
  la mutation « `-TAGS` dans une commande séparée » est équivalente sur ce binaire
  et survit ; la mutation « `-TAGS` dans la commande de figeage » est détectée par
  le test de la ligne de commande.
- `POST /api/plan/valider` est `async` et lance `--appliquer` de façon synchrone :
  le serveur ne répond à rien d'autre pendant l'écriture (≈ quelques secondes pour
  23 tâches). Acceptable en v1, à noter si la base grossit.
- **Conflit entre deux décisions, révélé par l'étape 6 — à trancher par
  l'utilisateur, non tranché ici.** « Valider écrit exactement le plan affiché » et
  « une tâche déplacée à la main reste `+fige`, le solveur ne la bouge plus »
  ne tiennent ensemble que si le solveur respecte `+fige`. Or la **passe 2 ignore
  `+fige`** (la contrainte 8 n'existe que dans `resoudre`, `solveur.py:648-652` ;
  `completer` ne la lit pas). Mesuré : deux tâches de passe 2 figées à la main ont
  été **ramenées au plan par Valider** (`+fige` conservé, `scheduled` écrasé). Trois
  issues possibles : (a) `completer` applique `+fige` (le vrai correctif, dans le
  solveur) ; (b) `--appliquer` n'écrit jamais le `scheduled` d'une tâche `+fige`
  (garde simple, mais le plan affiché et la base divergent alors) ; (c) Valider
  refuse tant qu'une tâche figée n'est pas au créneau où elle est figée.
- **Un `+fige` sur une tâche de passe 1 en régime agrégé rend toute la passe 1
  infaisable** (mesuré, une seule variable changée : OPTIMAL 16 tâches →
  INFEASIBLE 0 tâche). Deux défauts se cumulent : le calcul est rapporté
  « terminé » à l'interface, alors que le plan ne contient plus aucun travail daté
  (`plan_runner` ne regarde que le code de retour ; `statut` n'est pas affiché) ;
  et le message « Le diagnostic (planif/diagnostic.py) nomme les responsables »
  n'est suivi d'aucun nom. L'interface ne permet pas ce figeage (blocs agrégés en
  lecture seule) ; l'endpoint, la ligne de commande et un changement de régime
  entre deux calculs, si.
- **Valider accepte un plan `INFEASIBLE`.** Rien ne l'interdisait dans le prompt ;
  à décider (refus 409, ou confirmation renforcée).
- **Blocs d'une tâche hors ordre** : voir plus haut (bloc `indice 1` avant
  `indice 0`) ; il pèse directement sur E3, qui ne rend déplaçable que l'indice 0.
- La base de test « détendue » (échéances à 7-12 semaines) met toute la passe 1
  en régime agrégé : **aucun bloc de passe 1 n'est déplaçable** dans l'interface
  sur cette base. E3 n'y est exerçable que sur des tâches de passe 2, précisément
  celles dont le figeage est ignoré.
- La base `taskwarrior-test` est laissée dans l'état de l'étape 6 (cinq tâches
  `+fige`, dont carter) ; `outils/recharger-base-test.py` la remet à neuf.

## 5. État d'arrivée

| Étape | État | Commit |
|---|---|---|
| 0 inventaire | fait | B `6334ef6` |
| 1 chemins | fait | B `88428d4`, A `be7fc84` |
| 2 due dans plan.json | fait | B `595773c` |
| 3 --appliquer | fait | B `dad0ecd` |
| 4 Valider (E4) | fait | A `dbdf827` |
| 5 figer (E3) | fait | A `f0715ce` |
| 6 essai de bout en bout + rapport | fait, avec un écart (ligne 5 du tableau) | B (ce commit) |

**Aucun git push.** Suites vertes à l'arrivée dans les deux dépôts.

**Ce qui demande l'utilisateur**, par ordre d'importance :

1. Trancher le conflit « plan affiché » / « `+fige` respecté » (a, b ou c ci-dessus)
   — tant qu'il ne l'est pas, Valider peut défaire un déplacement manuel d'une
   tâche de passe 2.
2. Lancer un run sur le défaut « prédécesseurs non datés hors de la passe 1 » : il
   sort du plan les délais `+externe` et les chaînes, et c'est lui qui empêche la
   ligne 5 du tableau d'être mesurée.
3. `+fige` en régime agrégé → passe 1 infaisable, et un calcul infaisable qui se dit
   « terminé » ; décider aussi si Valider doit refuser un plan `INFEASIBLE`.
4. `PUT /api/task/{id}/modify` ne retire jamais un tag (`-TAGS` inopérant sur
   3.5.0) : à confirmer sur le binaire amont du téléphone.
5. Le cas `--ecrire-due` / terminale héritant l'échéance du projet (ignorée).
