# Conception — ordonnanceur de projet par contraintes

Document de référence. Il doit se suffire à lui-même : un agent qui n'a pas suivi la
discussion doit pouvoir implémenter un lot de `tasks.md` en ne lisant que ce fichier et
`proposal.md`.

---

## 1. Modèle du temps

- **Granularité** `g` = 30 min, **paramétrable**. Toutes les durées et positions sont des
  entiers en nombre de créneaux. Jamais de flottant d'heures dans le modèle.
- **Origine** `t0` = début du jour courant, minuit local.
- **Horizon détaillé** `H_d` = 2 semaines par défaut, paramétrable. C'est la fenêtre où l'on
  produit des heures.
- **Horizon de faisabilité** `H_f` ≥ `H_d`, couvrant la plus lointaine échéance de projet.
  Au-delà de `H_d`, la capacité est agrégée par jour au lieu d'être posée au créneau.

> Pourquoi deux horizons : une fenêtre de deux semaines ne peut pas dire si un projet à trois
> mois est faisable. Mais modéliser trois mois au créneau de 30 min ferait exploser le modèle.

---

## 2. Entités

### Tâche (lue depuis Taskwarrior)

| Champ | Source | Rôle |
|---|---|---|
| `uuid`, `description`, `project` | Taskwarrior | identité |
| `estimated` | UDA `estTime` | durée de travail, ou **délai** si `+externe` |
| `due` | Taskwarrior | échéance **réelle** (un engagement) |
| `depends[]` | Taskwarrior | précédence |
| `tags[]` | Taskwarrior | contexte + marqueurs |
| `urgency` | Taskwarrior | ordre du régime opportuniste |

**Marqueurs, par tags — aucun UDA nouveau :**

| Tag | Effet |
|---|---|
| `+externe` | la tâche n'est pas réalisée par l'utilisateur : intervalle **hors** de la contrainte de non-chevauchement. `estimated` est un **délai calendaire**, pas du travail. |
| `+insecable` | un seul bloc, pas de fractionnement |
| `+fige` | début imposé : on conserve le `scheduled` courant |
| `+asap` | exception au « au plus tard » — traité par une échéance artificielle proche |

### Qui fait la tâche : pas de champ, un tag

**Décision utilisateur du 22/09/2026.** Il n'y a pas et il n'y aura pas de champ
`assignee`. Le solveur n'a besoin que d'une chose : est-ce que cette tâche
consomme *ma* capacité, oui ou non — et `+externe` y répond déjà entièrement.

L'acteur, quand il faut le connaître, se note **en tag** :

    +externe +serviceAchat      la demande est chez les achats
    +externe +Ludovic           c'est Ludovic qui doit répondre

Le gain est immédiat et ne coûte rien au modèle : `task +externe +serviceAchat`
donne la liste de ce qu'un tiers a à faire, `task +externe +Ludovic` prépare un
point avec lui. Un champ dédié n'aurait rien apporté de plus, puisqu'il n'entre
dans aucune contrainte.

**Ce qui est écarté, et qu'il ne faut pas confondre avec ça :** une capacité
limitée *par acteur* — le service achat ne traitant pas trois demandes de front.
Ce serait une ressource supplémentaire dans le modèle, donc une autre
fonctionnalité, autrement plus lourde. Elle n'est pas au programme.

### Convention sur les `datetime`

À l'intérieur du modèle (grilles horaires, tampon, vérifications), tout `datetime`
naïf est en **heure locale** — jamais en UTC. Taskwarrior, lui, exporte ses dates en
UTC *aware*. La conversion se fait **une seule fois, à la frontière** :
`planif/taskwarrior.py::vers_local_naif`, appelée par `_parse_date` au moment de la
lecture. Aucun autre endroit du dépôt ne doit reconvertir ni resupposer un fuseau ;
`planif/tampon.py` et `planif/verifications.py` importent cette même fonction plutôt
que d'en tenir chacun une version.

### Contexte

Un contexte Taskwarrior (`context.<nom>.read`) fournit **l'éligibilité** : quelles tâches
peuvent occuper ses créneaux. **Le filtre n'est jamais réinterprété** — on demande les UUID à
Taskwarrior (`task <filtre> _uuids`) et on s'en tient à la réponse.

Configuration associée à chaque contexte :

```toml
[contextes.pro]
contexte_tw = "pro"          # nom du contexte TaskWarrior
bloc_min    = "2h"
marge_jour  = "2h"           # capacité réservée, jamais planifiée
grille      = { lun = ["08:30-12:00", "14:00-18:30"], ... }

[contextes.perso]
contexte_tw = "perso"
bloc_min    = "1h"
marge_jour  = "30min"
grille      = { lun = ["07:00-08:00", "18:40-19:30"], sam = ["07:00-12:00"], ... }
```

> La **forme** des créneaux compte ici, contrairement à taskcheck : on place à l'heure.

### Réunion

Intervalle fixe, issu d'iCal. Entre dans la contrainte de non-chevauchement au même titre
qu'une tâche `+fige`. **Source à brancher** : le flux iCal existe déjà côté utilisateur
(cf. `TWsched_task_to_caldav.py` du dépôt TaskWarriorPlanner, qui n'écrit que dans un sens).

### Projet

```toml
[projets."NPD.helisides"]
echeance = "2026-12-15"
```

---

## 3. Calendrier disponible

Fonction pure, testable sans solveur ni réseau :

```
disponibilite(contexte, jour) = grille(contexte, jour)
                              − réunions(jour)
                              − marge_jour(contexte)
```

Elle produit, par contexte et par jour, la liste des créneaux libres en indices de créneaux.

**Règle de la marge** : la marge est un *volume* réservé, pas une plage. On retire
`marge_jour` du total disponible du jour ; on ne fige pas *quand*.

### Deux calendriers (décision du 23/09/2026)

| Source | Contenu | Accès |
|---|---|---|
| **Outlook** | calendrier **pro** | PowerShell + Outlook COM, sur le PC pro (`outils/extraire-outlook.ps1`) |
| **Nextcloud** | calendrier **perso** | CalDAV (bibliothèque `caldav`, déjà utilisée par `TWsched_task_to_caldav.py`) |

Les deux sont à brancher. Aujourd'hui, seul Outlook est lu, et un seul de ses
calendriers.

### Les réunions deviennent des tâches `+meeting` (décision du 23/09/2026)

L'import se fait en tâches Taskwarrior `+meeting +fige`, avec `scheduled` et
`estTime`. Le solveur les lit alors comme des tâches figées, un mécanisme qui
existe déjà. **L'argument décisif est Timewarrior** : le hook `on-modify`
déclenche Timewarrior sur `task start` avec les tags de la tâche, donc le temps
d'une réunion se range seul sous `+meeting`. Avec un fichier `reunions.json`
lu directement, il faudrait lancer `timew start` à la main, sans lien avec la
tâche. Second usage : poser un `depends` sur une réunion (préparer un dossier
pour une réunion, et que ça suive si elle se déplace).

Règles arrêtées :

- **idempotence sur `entryId` + date de début de l'occurrence, jamais sur
  `entryId` seul** : mesuré, l'`entryId` d'Outlook appartient à la *série*
  (18 occurrences, 6 identifiants) ;
- un événement `Free` n'occupe pas : mesuré, 6 sur 18 le sont ;
- la passe de ménage des réunions passées
  (`task +meeting scheduled.before:now status:pending done`) s'écrit **en même
  temps** que l'import, pas plus tard ;
- **tout import réel est lancé par l'utilisateur lui-même.**

Reste à trancher : la pollution des vues de tâches normales par des dizaines de
réunions (un filtre `-meeting` dans les rapports par défaut ?).

### Régimes de période — en suspens

Une période ne fait pas qu'occuper : elle change le régime de chaque contexte.
Cas recensés par l'utilisateur (23/09), à préciser par lui avant toute
conception :

| Régime | Ce qui est planifiable |
|---|---|
| semaine normale | tout, selon les grilles |
| vacances (semaine) | pas de pro ; le reste : à valider |
| week-end « vacances » | pas comme d'habitude : pas de projet perso, sport éventuellement |
| week-end sportif | pas de projet perso, sport oui |
| trajet en voiture | **rien** (il conduit) |
| trajet en train | certaines choses seulement |

Défaut connu en attendant : une absence lue dans Outlook vide *tous* les
contextes, sport et perso compris.

---

## 4. Le tampon de sécurité

```
echeance_effective(due) :
    t = due − 24 h
    reculer jusqu'à la fin du dernier jour ouvré strictement antérieur à t
```

Vérifié sur les deux exemples de référence :

| `due` | − 24 h | fin du dernier jour ouvré antérieur | résultat |
|---|---|---|---|
| jeudi 14 h 00 | mercredi 14 h 00 | mardi 18 h 30 | **mardi 18 h 30** |
| mardi 8 h 00 | lundi 8 h 00 | vendredi 18 h 30 | **vendredi 18 h 30** |

**Appliqué une seule fois, aux `due` réelles.** Les dates dérivées le long du graphe de
dépendances ne sont pas tamponnées : sinon le tampon se cumule et une chaîne de cinq tâches
accumulerait une dizaine de jours ouvrés de rembourrage invisible.

---

## 5. Le modèle de contraintes

### Variables

Pour chaque tâche `i` retenue dans l'horizon détaillé :

- si `+insecable` ou `estimated ≤ bloc_min` : **un** intervalle `I_i`
- sinon : `k_i` intervalles `I_{i,1..k}`, où `k_i = ceil(estimated / bloc_min)`,
  chacun de durée `bloc_min` sauf le dernier (le reste)

Chaque intervalle porte `start`, `size`, `end` et, pour les blocs optionnels du reste, une
variable de présence.

### Contraintes

1. **Conservation** : `Σ size(I_{i,*}) = estimated(i)`
2. **Fenêtres** : chaque intervalle est inclus dans un créneau disponible du contexte de `i`
3. **Bloc minimum** : `size ≥ bloc_min(contexte(i))`, sauf l'intervalle de reste
4. **Ressource unique** : `AddNoOverlap` sur **tous** les intervalles des tâches non `+externe`,
   **plus** les réunions, **plus** les tâches `+fige`
5. **Tiers** : une tâche `+externe` a un intervalle de durée `estimated`, soumis aux précédences
   mais **absent** de la contrainte 4 — c'est toute la différence, et c'est une ligne
6. **Précédence** : pour `i → j`, `start(premier bloc de j) ≥ end(dernier bloc de i)`
7. **Échéance** : `end(dernier bloc de i) ≤ echeance_effective(i)`
8. **Figées** : `start(I_i)` fixé à la valeur courante de `scheduled`

### Objectif — deux résolutions, pas deux objectifs

Les deux régimes ne se mélangent pas dans une seule optimisation : ils s'enchaînent.

**Passe 1 — le mur.** On ne retient que les tâches datées (directement, ou par dépendance vers
une tâche datée).

```
minimiser   Σ retard_i            (lexicographiquement prioritaire)
puis
maximiser   Σ start_i             ← « au plus tard en sécurité »
```

Le résultat : chaque tâche datée est à sa date limite. **Sa date planifiée *est* sa marge.**
La question « puis-je décaler cette commande ? » se lit dans le plan, sans seconde requête.

**Passe 2 — l'opportuniste.** Le plan de la passe 1 est **figé**. Les tâches non datées
remplissent la capacité restante, par urgence décroissante, au plus tôt.

```
maximiser   Σ urgence_i × planifiée_i
départager  par start croissant
```

> Pourquoi figer la passe 1 : pour que la marge annoncée soit **actionnable**. Une marge
> obtenue en réorganisant tout le reste est vraie mais inutilisable — on ne la suivra pas, et
> on cessera de faire confiance au chiffre.

---

## 6. Diagnostics

### Pré-vérifications, avant tout appel au solveur

Elles sont bêtes, rapides, et évitent un `INFEASIBLE` sans explication :

| Vérification | Message attendu |
|---|---|
| tâche `+insecable` plus longue que le plus grand créneau disponible | « 8 h indivisibles ne tiennent dans aucune de vos journées (max 6 h utiles) — découpez, ou déclarez une journée exceptionnelle, ou rognez la marge ce jour-là » |
| cycle de dépendances | nommer le cycle |
| `due` déjà passée | lister |
| tâche `+externe` sans `estimated` | « délai fournisseur non renseigné » |
| tâche sans contexte attribuable | lister |

### En cas d'infaisabilité

CP-SAT rend un **noyau d'insatisfiabilité** via des hypothèses (`AddAssumption`). Chaque
contrainte d'échéance et chaque tâche figée est posée comme une hypothèse étiquetée, de sorte
que le noyau se retraduise en langage courant :

> « Ces trois éléments s'opposent : l'échéance du 15/12 sur *Finaliser IOM US*, la tâche figée
> *Réunion revue de projet* du 12/12, et les 8 h indivisibles de *Test de qualification*. »

**On diagnostique, on ne tranche pas.** Les règles d'arbitrage viendront de l'usage observé.

### Rapport, en sortie nominale

- par échéance : la marge restante, en temps ouvré
- la **chaîne critique** : les tâches dont tout report décale la fin de projet
- la part de la semaine qui est contrainte, contre la part opportuniste
- ce qui n'a pas pu être placé, et pourquoi

---

## 7. Où vivent les données

| Donnée | Emplacement | Raison |
|---|---|---|
| tâches, durées, échéances, dépendances, tags | **Taskwarrior** | source de vérité unique |
| grilles, marges, blocs, horizons, échéances de projet | fichier de configuration du dépôt | pas la place de Taskwarrior |
| réunions | iCal | déjà ailleurs, ne pas dupliquer |
| plan calculé | fichier JSON + `scheduled:` dans Taskwarrior | l'un pour l'interface, l'autre pour la ligne de commande |

Le plan JSON est le contrat avec l'interface web. Elle ne connaît pas le solveur.

### Le format JSON — contrat avec `../WebTaskManager`

Produit par `planif/sortie.py`. L'interface web lit **ce fichier et rien d'autre** :
elle ne connaît ni `ortools`, ni les grilles, ni `t0`, ni la notion de créneau.

```json
{
  "version": 1,
  "statut": "OPTIMAL",
  "retard_total": 0,
  "en_retard": [],
  "t0": "2026-10-05T00:00:00",
  "granularite_minutes": 30,
  "taches": {
    "dddddddd-…-0004": {
      "description": "Tester",
      "projet": "NPD.helisides",
      "debut": "2026-11-20T14:00:00",
      "fin": "2026-11-20T17:00:00",
      "blocs": [
        {"indice": 0, "debut": "2026-11-20T14:00:00", "fin": "2026-11-20T16:00:00",
         "externe": false, "agrege": false, "opportuniste": false, "precision": "heure"},
        {"indice": 1, "debut": "2026-11-20T16:00:00", "fin": "2026-11-20T17:00:00",
         "externe": false, "agrege": false, "opportuniste": false, "precision": "heure"}
      ]
    }
  }
}
```

Les règles, dans l'ordre d'importance :

1. **`precision` gouverne l'affichage.** `"heure"` : le créneau est un engagement.
   `"jour"` : le bloc vient du régime agrégé (au-delà de l'horizon détaillé, §1) et
   **seule la journée est garantie** — deux blocs agrégés d'une même journée peuvent
   même se chevaucher dans cette sortie. L'interface ne doit pas les afficher comme
   des rendez-vous à l'heure près. `precision` est redondante avec `agrege`, et c'est
   voulu : le drapeau dit *d'où vient* le bloc, la précision dit *ce qu'on peut en
   faire*, et c'est la seconde qui intéresse un afficheur.
2. **Les trois régimes sont lus, jamais déduits.** Chaque bloc porte `externe`,
   `agrege` et `opportuniste`. Un consommateur ne recalcule rien. `opportuniste`
   distingue le travail de la passe 2 (§5) de celui de la passe 1 : les deux
   **doivent être visuellement distincts** (`proposal.md` décision 9).
3. **Aucun indice de créneau ne sort.** Les instants sont des chaînes ISO-8601 en
   **heure locale naïve**, conformément à la convention du §2. `t0` et
   `granularite_minutes` ne sont là que pour le diagnostic.
4. **`statut`, `retard_total` et `en_retard` remontent un plan dégradé.** `statut`
   vaut `OPTIMAL`, `FEASIBLE` ou `INFEASIBLE` ; `FEASIBLE` signifie « plan valide,
   optimalité non prouvée ». `en_retard` liste les tâches dont l'échéance n'est pas
   tenue — l'échéance est une contrainte *souple*, une tâche intenable ne bloque pas
   les autres.
5. **Le fichier est stable octet pour octet** pour une même entrée (`sort_keys`,
   indentation fixe), et l'écriture est **idempotente** : si le contenu n'a pas
   changé, le fichier n'est pas rouvert en écriture et son `mtime` ne bouge pas.
6. **`version` est un entier**, à incrémenter dès que le format change de façon
   incompatible, pour que l'interface puisse refuser ce qu'elle ne sait pas lire
   plutôt que de l'interpréter de travers.

### L'écriture de `scheduled:` dans Taskwarrior

`scheduled` reçoit le **début du premier bloc** de la tâche. Deux règles :

- les tâches **`+externe` sont ignorées** — un délai fournisseur n'est pas du travail
  de l'utilisateur et n'a pas à apparaître dans son agenda ;
- l'écriture est **idempotente** : on relit l'état courant et on ne réécrit que ce qui
  diffère. Sans ça, chaque exécution toucherait toute la base et Syncthing
  répliquerait le bruit sur trois machines.

`planif/sortie.py` est la **frontière en écriture** des dates, symétrique de
`planif/taskwarrior.py` en lecture : il reconvertit le local naïf du §2 vers l'UTC
compact `%Y%m%dT%H%M%SZ`. Vérifié sur base jetable (Taskwarrior 3.5.0) : les deux
formes `2026-11-20T14:00:00` et `20261120T130000Z` sont acceptées et ressortent
identiques ; on retient l'UTC explicite, qui ne dépend pas de la façon dont
Taskwarrior interprète une date sans fuseau.

---

## 8. Interfaces

```
plan            résout et écrit le plan
plan --check    pré-vérifications seules, aucun solveur
plan --dry-run  résout sans rien écrire
why <tâche>     marge, chaîne critique, ce qui la contraint
```

---

## Annexe — constats taskcheck (2026-09-21)

Établis en exécutant l'outil, sur base jetable. Conservés parce qu'ils documentent les
pièges du domaine, et parce qu'ils sont à remonter en amont.

1. `subprocess.run(["task","export"], text=True)` sans `encoding='utf-8'` → accents corrompus
   sous Windows (`common.py:32`). Défaut identique à celui corrigé dans ce dépôt le 2026-09-18.
2. `config["report"]` (`report.py:285`) et `config["calendars"]` (`common.py:213`) lus sans
   défaut → plantage si la section documentée comme optionnelle est absente.
3. `import termios` inconditionnel (`theme.py:4`) → `--report` et `--timeline` inutilisables
   sous Windows. Correctif de 11 lignes écrit et vérifié.
4. Durées non normalisées : `PT1H60M` au lieu de `PT2H`.
5. `[[0, 24]]` dans une grille fait planter : `hours_to_time(24)` produit `"24:0"`.
6. `allocation <= 0.05` (≈ 3 min) dans `allocate_time_to_task` → une tâche plus courte n'est
   **jamais** planifiée, donc jamais terminée, et **bloque ses dépendants en silence**.
7. Limite structurelle : `compute_total_available_hours` prend le **max** des grilles, pas leur
   somme, et le budget journalier est partagé. Deux contextes ne donnent pas deux capacités.
   Contournement trouvé : une tâche sentinelle sur une grille large. Reproduction en deux
   tâches disponible.
