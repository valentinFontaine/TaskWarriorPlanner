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

## 4. Frictions

Voir `INVENTAIRE-NUIT-3.md`, « Écarts et faits notés ».

## 5. État d'arrivée

| Étape | État | Commit |
|---|---|---|
| 0 inventaire | fait | B `6334ef6` |
| 1 chemins | fait | voir ci-dessous |
