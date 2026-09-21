# Lots de travail

Chaque lot est **exécutable isolément**. Un agent qui reprend un lot doit pouvoir travailler en
ne lisant que `proposal.md`, `design.md`, ce fichier et `AGENTS.md` — il n'a pas le contexte de
la discussion qui les a produits.

Le lot 9 (affichage du plan dans le calendrier web) vit dans l'autre dépôt,
`../WebTaskManager`, et n'est pas traité ici.

## Règles valables pour tous les lots

Détail dans `AGENTS.md`. En résumé :

1. **Jamais de commande Taskwarrior sans `TASKRC` ou `TASKDATA` sur une base jetable.**
   Sur le PC : `TASKRC=C:/Users/irpaui/taskwarrior-dev/taskrc`.
2. **Le test s'écrit d'abord et doit être vu rouge.** Compter les tests exécutés, pas seulement
   les verts.
3. **Ne rien installer hors du `venv` du projet.**
4. **Ne jamais publier sur GitHub au nom de l'utilisateur.**
5. `pytest` doit être vert à la fin de chaque lot.
6. Toute lecture de `task export` passe par `encoding='utf-8'` explicite, et toute modification
   en masse par `rc.bulk=0` — voir les pièges du §5 d'`AGENTS.md`.

---

## Lot 0 — Socle, sans solveur

**But** : lire Taskwarrior et construire le modèle de données, rien de plus.

- Paquet `planif/`. `venv` créé, `requirements.txt` installé.
- Lecture par `task export`, **avec `encoding='utf-8'` explicite**.
- Objets : `Tache`, `Contexte`, `Projet`, `Reunion`, selon `design.md` §2.
- Marqueurs par **tags** : `+externe`, `+insecable`, `+fige`, `+asap`. Aucun UDA nouveau.
- Chargement de la configuration (contextes, grilles, marges, blocs, horizons, échéances).
  Les vraies grilles de l'utilisateur sont dans `config.json` à la racine — les reprendre comme
  valeurs de départ, en les convertissant au format de `design.md` §2.

**Vert quand** : sur une base jetable semée, le chargement rend le bon nombre de tâches, les
tags sont traduits en marqueurs, et une description accentuée survit à l'aller-retour.

---

## Lot 1 — Calendrier disponible

**But** : la fonction pure `disponibilite(contexte, jour)` de `design.md` §3.

Grille du contexte, moins les réunions, moins la marge quotidienne — la marge est un **volume**
réservé, pas une plage figée. Sortie en indices de créneaux, granularité **paramétrée**.

**Vert quand** : tests sans Taskwarrior ni réseau — journée pleine, réunion à cheval sur deux
créneaux, week-end vide, marge supérieure à la grille (doit rendre zéro, pas un négatif),
granularité passée à 15 min sans rien casser.

---

## Lot 2 — Tampon et dérivation des échéances

**But** : `echeance_effective(due)` de `design.md` §4, et la remontée le long du graphe.

`due − 24 h`, puis reculer jusqu'à la fin du dernier jour ouvré strictement antérieur.
**Tampon appliqué une seule fois**, sur les `due` réelles uniquement.

**Vert quand** : les deux exemples de référence tombent juste (jeudi 14 h → mardi 18 h 30 ;
mardi 8 h → vendredi 18 h 30), **et** un test prouve qu'une chaîne de cinq tâches n'accumule
qu'un seul tampon.

---

## Lot 3 — Pré-vérifications

**But** : tout le tableau de `design.md` §6, **sans jamais appeler le solveur**.

Tâche indivisible trop longue pour la plus grande journée, cycle de dépendances, `due` dépassée,
`+externe` sans `estimated`, tâche sans contexte attribuable.

**Vert quand** : chaque cas produit un message nommant les tâches concernées, le cas nominal
n'en produit aucun, et le message de la tâche indivisible propose les trois issues (découper /
journée exceptionnelle / rogner la marge).

> **Lots 0 à 3 : aucun solveur, tout est pur et testable hors ligne.**

---

## Lot 4 — Modèle CP, passe 1 (le mur)

**But** : `design.md` §5, tâches datées uniquement.

Intervalles, conservation de la durée, fenêtres, bloc minimum, `AddNoOverlap` sur la ressource
unique + réunions + tâches figées, précédences, échéances. Objectif lexicographique : minimiser
le retard, puis **maximiser** la somme des débuts.

**Vert quand** : une tâche datée est placée à sa limite et pas avant ; deux tâches ne se
chevauchent jamais ; **une échéance intenable est signalée sans empêcher les autres d'être
planifiées** (constaté sur taskcheck : une seule tâche impossible monopolisait sept journées).

---

## Lot 5 — Tiers et précédences

**But** : la décision 10 du `proposal.md`. C'est **le lot qui compte le plus** : c'est le
scénario qui a motivé tout ce travail.

Une tâche `+externe` a un intervalle de durée `estimated`, soumis aux précédences, **absent de
la contrainte de non-chevauchement**.

**Vert quand** : le scénario de référence tombe juste —
`plan (4 h) → commander (30 min) → fabrication (4 semaines, +externe) → tester (3 h)`.
Le test doit démarrer **après** les quatre semaines, et la capacité de l'utilisateur sur la
période doit être **intégralement disponible pour autre chose**.

---

## Lot 6 — Passe 2, opportuniste

**But** : remplir la capacité restante avec les tâches non datées, par urgence, au plus tôt, le
plan de la passe 1 étant **figé**.

**Vert quand** : les tâches de la passe 1 ne bougent pas d'un créneau ; les non datées ne
prennent que la place restante ; elles sont marquées comme opportunistes dans la sortie.

---

## Lot 7 — Sortie

**But** : le plan en JSON, et `scheduled:` écrit dans Taskwarrior.

Les deux régimes distingués dans le JSON. Écriture idempotente. `--dry-run` n'écrit rien.
Le format JSON est le **contrat avec `../WebTaskManager`** : le documenter dans `design.md` §7
s'il s'en écarte.

**Vert quand** : deux exécutions successives sans changement d'entrée produisent le même plan
et n'écrivent rien la seconde fois.

---

## Lot 8 — Noyau d'insatisfiabilité

**But** : `design.md` §6, partie infaisabilité.

Chaque contrainte d'échéance et chaque tâche figée posée en hypothèse étiquetée, pour que le
noyau se retraduise en langage courant.

**Vert quand** : un conflit construit à la main rend exactement les éléments en cause, et rien
d'autre.

---

## Lot Z — Remontées amont taskcheck (différé, décision utilisateur)

Six défauts établis et reproductibles, listés en annexe de `design.md`.
**Rien n'est publié sans accord explicite de l'utilisateur, et jamais en son nom.**

- **PR 1** — sections de configuration optionnelles lues sans défaut (`[report]`,
  `[calendars]`). Trivialement correct, aucun débat.
- **PR 2** — support Windows : `encoding='utf-8'` manquant + `import termios` conditionnel.
- **Issue** — budget journalier en `max` au lieu de somme. **C'est la question qui gouverne les
  autres.** Formuler en question, avec la reproduction en deux tâches.
- **Issue** — durées non normalisées, `[[0, 24]]` qui plante, seuil des 3 minutes.

Le projet amont n'a **ni `CONTRIBUTING`, ni gabarit d'issue**.

---

## À trancher avec l'utilisateur avant le lot 4

- **Source des réunions.** Le flux iCal n'est branché nulle part. Sans lui, le calendrier
  disponible ignore les réunions et le plan sera faux. `TWsched_task_to_caldav.py` écrit vers le
  calendrier ; il faut l'inverser pour en **lire** les créneaux occupés. Lot dédié ?
- **Échéances de projet.** Aucune n'existe dans les données réelles. Il en faut au moins une
  pour que la passe arrière ait un sens ; à défaut, les lots 4 et 5 ne seront testables que sur
  des scénarios inventés.
- **Pénalité de stabilité** (écart au plan précédent) : prévue tardivement, mais remonte en
  priorité si le plan s'avère trop instable dès le lot 4.
