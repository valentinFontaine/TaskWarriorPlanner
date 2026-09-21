# INVENTAIRE — étape 0

Établi avant toute ligne de code, le 2026-09-21 (soir).

## 1. État du dépôt — confirmé

| Vérifié | Attendu par le prompt | Constaté |
|---|---|---|
| branche | `main` | `main` |
| HEAD | `1b06e9c` | `1b06e9c` |
| arbre | propre | propre |
| `venv` | absent | absent → **créé** |

Aucun écart.

## 2. Socle technique — vérifié en l'exécutant

- `python -m venv venv` puis `pip install -r requirements.txt -r requirements-dev.txt` : OK.
- **`ortools` 9.15.6755** s'importe et résout un modèle trivial
  (`x+y=7, x−y=1, max x` → `OPTIMAL x=4 y=3`). Également installés : `protobuf 6.33.6`,
  `numpy 2.5.3`, `pytest 9.1.1`.
- `task --version` → **3.5.0**.

## 3. Isolation des données — vérifiée avant toute écriture

Base jetable créée **sous le répertoire temporaire de session**, pas dans
`~/taskwarrior-dev` (qui existe et appartient à l'utilisateur) :

```
TASKRC=<scratchpad>/twdev/taskrc
data.location=<scratchpad>/twdev/data
```

`task _show | grep data.location` confirme la cible **avant** la première commande
d'écriture. `confirmation=off` **et** `bulk=0` sont posés dans ce `taskrc`
(AGENTS.md §5 : `confirmation=off` seul ne couvre pas la confirmation de lot).

Aller-retour d'accents vérifié : `task import <fichier UTF-8>` puis `task export` rend
`platine élargie` et `pièce reçue` intacts. L'UDA `estTime` accepte `PT4H`, `PT30M`, `P28D`.

**Lapsus à signaler** : un `task --version` a été lancé sans `TASKRC` posé, avant la création
de la base jetable. C'est une lecture de version qui ne touche à aucune donnée, mais la règle
dit « y compris une simple lecture ». Aucune autre commande `task` n'a été lancée sans
isolation.

## 4. Ce que `config.json` fournit — et ce que j'en reprends

| Clé | Valeur réelle (mars 2025) | Usage |
|---|---|---|
| `timeSlots.pro` | lun–ven `08:30-12:00` + `14:00-18:30`, WE vide | **grille de production par défaut** |
| `timeSlots.perso` | lun–ven `7:00-8:00` + `18:40-19:30`, sam `7:00-12:00`+`16:00-18:00`, dim `7:00-12:00` | grille `perso` par défaut |
| `timeSlots.sleep`, `timeSlots.asso` | — | **non repris** : `sleep` n'est pas un contexte de travail, `asso` n'apparaît dans aucun lot du cahier des charges |
| `freeTimeHours` | `2` | marge quotidienne `pro` = 2 h (concorde avec `design.md` §2 et décision 11) |
| `deepWorkLimit` | `4` | **≠ bloc minimum.** `proposal.md` décision 3 dit bloc min **2 h** en `pro`. Le `4` de `config.json` est un plafond de travail profond, pas un bloc minimum — c'est la décision 3 qui fait foi. Voir §6. |
| `commuteTime`, `plannedDurationDays`, `timezone` | `10m`, `7`, `UTC` | **non repris** ce soir : aucun lot 0–5 ne les utilise |

La marge `perso` (30 min, décision 11) **n'est pas dans `config.json`** : elle vient de
`proposal.md` décision 11, transcrite telle quelle.

## 5. Ce qui manque et sera bouchonné

| Donnée | Recherchée dans | Constat |
|---|---|---|
| **échéances de projet** | `config.json`, `openspec/`, base Taskwarrior | **n'existe nulle part** → `planif/stub_echeances.py` |
| **réunions / iCal** | `TWsched_task_to_caldav.py` (écrit vers CalDAV, ne lit pas), `config.json` | **non branché** → `planif/stub_reunions.py`, liste vide |
| **calendrier de jours fériés** | tout le dépôt | inexistant → ignoré, « jour ouvré » = jour dont la grille du contexte est non vide |

## 6. Divergences relevées entre les sources

1. **`deepWorkLimit=4` vs bloc minimum 2 h.** Deux notions différentes portant des chiffres
   proches. Le cahier des charges (décision 3) fait foi : bloc min `pro` = 2 h.
2. **Grille du cas de référence ≠ grille réelle.** Le cas de référence impose
   `09:00-12:00` / `14:00-17:00` ; `config.json` porte `08:30-12:00` / `14:00-18:30`.
   Les deux coexistent : la grille du cas de référence vit dans les tests, la grille réelle
   dans la configuration par défaut. Rien n'est recalibré.
3. **`design.md` §4** illustre le tampon avec des fins de journée à 18 h 30 (grille réelle) ;
   le cas de référence attend 17 h 00 (sa propre grille). Même règle, grilles différentes.

## 7. Ce qui n'est pas fait ce soir

Lots 6 à 9 et lot Z, par consigne. `../WebTaskManager` n'est pas touché.
