# Rapport de nuit — ordonnanceur par contraintes

Run autonome du 2026-09-21 au soir. Branche `main`, rien n'a été poussé.

Tout ce qui est écrit ici a été **exécuté**, sauf mention explicite du contraire.
Ce que je suppose sans l'avoir lancé est marqué « *supposé* ».

---

## 1. Données bouchonnées ou interprétées

C'est la section à lire en premier : elle dit ce qui, dans le résultat, ne repose
pas sur une donnée réelle.

### 1.1 Les deux bouchons, repérables au `grep stub_`

| Fichier | Ce qui manque | Où j'ai cherché | Effet sur le résultat |
|---|---|---|---|
| `planif/stub_echeances.py` | **échéances de projet** | `config.json` (n'a que `timeSlots`, `commuteTime`, `plannedDurationDays`, `deepWorkLimit`, `freeTimeHours`) ; `design.md` §2 qui n'en donne que le *format* ; `tasks.md` qui écrit noir sur blanc « Aucune n'existe dans les données réelles » | La valeur bouchonnée est celle du cas de référence (**2026-11-24 17:00**), entièrement spécifiée par l'utilisateur dans le prompt du run. Le mécanisme est donc éprouvé sur une vraie valeur ; mais **aucun projet réel n'a d'échéance**, donc la passe arrière n'a encore rien à dire sur les données de production. |
| `planif/stub_reunions.py` | **réunions (flux iCal)** | `TWsched_task_to_caldav.py` (écrit *vers* CalDAV, ne lit rien) ; `config.json` (aucune URL, aucun identifiant de calendrier) ; `requirements.txt` (aucune bibliothèque iCal déclarée, donc rien n'a jamais lu de calendrier ici) ; `tasks.md` « le flux iCal n'est branché nulle part » | Rend **toujours une liste vide**. Conséquence : sur un agenda réel chargé, **le plan sera trop optimiste**. Le cas de référence stipule « aucune réunion », donc le bouchon y est exact et ne fausse rien — mais il fausserait la production. |

Le code de gestion des réunions, lui, **existe et est testé** : `planif/calendrier.py`
soustrait correctement une réunion à cheval sur deux créneaux et coupe une plage en
deux, et `planif/solveur.py` place les réunions dans `AddNoOverlap`. C'est
uniquement la **source** qui est bouchonnée.

### 1.2 Les interprétations — là où j'ai dû choisir plutôt que transcrire

Chacune est commentée à l'endroit du code concerné.

1. **L'échéance de projet descend sur les tâches terminales du projet.**
   `design.md` §2 donne la forme `[projets."X"] echeance = "..."` mais **ne dit pas**
   comment elle devient une contrainte sur des tâches. J'ai choisi : elle se pose
   comme `due` sur les tâches du projet qui n'ont aucun successeur dans le projet
   (ici, D). C'est le choix le plus lisible, et il rend le cas de référence exact.
   *À trancher avec l'utilisateur* — c'est une décision de modèle, pas un détail.

2. **Les trois tâches de 30 h du contrôle 2 ont reçu une échéance.**
   Le prompt les décrit « sans échéance ». Le régime des tâches non datées est la
   **passe 2 (lot 6), qui n'est pas écrite**. Je leur ai donc donné l'échéance du
   projet pour qu'elles entrent dans la passe 1. **Cela ne change rien à ce que le
   contrôle mesure** : la question est de savoir si la fabrication `+externe` mange
   de la capacité, pas par quel régime ces tâches sont placées. C'est signalé dans
   la docstring de `tests/cas_reference.py`.

3. **Les tailles de blocs sont des constantes, pas des variables.**
   `design.md` §5 pose une contrainte de conservation `Σ size = estimated` sur des
   `size` variables — mais il fixe lui-même les tailles trois lignes plus haut
   (« chacun de durée `bloc_min` sauf le dernier (le reste) »). La conservation
   devient donc vraie par construction et la contrainte redondante. J'ai pris la
   forme constante, plus lisible. **Un test vérifie quand même la conservation**,
   pour que la propriété reste assénée et pas seulement supposée.

4. **Un jour ouvré est un jour dont la grille du contexte est non vide.**
   Aucun calendrier de jours fériés n'existe dans le dépôt. Les fériés sont donc
   **ignorés** : un 11 novembre tombant dans une chaîne sera traité comme un jour
   travaillé. C'était le défaut annoncé ; je le confirme et je le signale.

5. **Alignement sur la granularité : on rétrécit vers l'intérieur.**
   Un créneau de grille non aligné (`18:40-19:30` en `perso`, granularité 30 min)
   devient `19:00-19:30`, soit 1 créneau et non 2. On n'invente jamais de
   disponibilité. Symétriquement, un créneau **partiellement** couvert par une
   réunion est compté **occupé en entier**. Les deux règles vont dans le sens
   prudent.

6. **`deepWorkLimit = 4` de `config.json` n'est pas le bloc minimum.**
   Deux notions différentes portant des chiffres proches. `proposal.md` décision 3
   dit bloc minimum **2 h** en `pro`, et c'est le cahier des charges qui fait foi.
   `deepWorkLimit` n'est utilisé nulle part ce soir.

7. **La grille du cas de référence n'est pas celle de l'utilisateur.**
   Le cas de référence impose `09:00-12:00` / `14:00-17:00` ; `config.json` porte
   `08:30-12:00` / `14:00-18:30`. Les deux coexistent : la grille réelle vit dans
   `planif/config.py`, celle du cas de référence dans `tests/cas_reference.py`.
   **Aucune règle n'a été recalibrée** pour tomber sur les valeurs attendues.

8. **Divergence de convention sur les `datetime` naïfs, entre deux modules.**
   `planif/tampon.py` traite un `datetime` naïf comme **local** ; `planif/verifications.py`
   le traite comme **UTC** pour rendre une comparaison possible. Les deux sont
   documentés à leur endroit, et le cas de référence n'est pas affecté (tout y est
   naïf des deux côtés). **C'est une incohérence réelle à réconcilier** avant de
   brancher sur des données Taskwarrior, qui exporte de l'UTC *aware*.

9. **`planif/tampon.py` retombe silencieusement sur le contexte `pro`** quand une
   tâche n'a pas de contexte attribuable. Ce chemin n'est exercé par aucun test.
   Les pré-vérifications du lot 3 sortent normalement ces tâches du modèle avant
   d'en arriver là, mais ce repli silencieux mériterait d'être remplacé par une
   erreur bruyante.

### 1.3 Ce que je n'ai pas bouchonné parce que je l'ai vérifié

- Les grilles horaires : lues dans `config.json`, pas inventées.
- La marge `pro` de 2 h : `freeTimeHours` de `config.json`, qui concorde avec
  `design.md` §2 et la décision 11.
- Le comportement de Taskwarrior : **exécuté** sur base jetable, pas supposé
  (voir §5.1).

---

## 2. Les mesures

### 2.1 Le cas de référence, en face des attendus

Sortie brute de `./venv/Scripts/python.exe -m tests.mesures_cas_reference` :

```
-- statut du solveur --
  statut        : OPTIMAL
  retard total  : 0 creneaux
  en retard     : (aucune)

-- plan obtenu, bloc par bloc --
  A - Faire le plan (4 h)   bloc 0 : jeudi 2026-10-22 a 15:00 -> jeudi 2026-10-22 a 17:00
  A - Faire le plan (4 h)   bloc 1 : vendredi 2026-10-23 a 09:30 -> vendredi 2026-10-23 a 11:30
  B - Commander (30 min)    bloc 0 : vendredi 2026-10-23 a 11:30 -> vendredi 2026-10-23 a 12:00
  C - Fabrication (+externe) bloc 0 : vendredi 2026-10-23 a 14:00 -> vendredi 2026-11-20 a 14:00
  D - Tester (3 h)          bloc 0 : vendredi 2026-11-20 a 14:00 -> vendredi 2026-11-20 a 16:00
  D - Tester (3 h)          bloc 1 : vendredi 2026-11-20 a 16:00 -> vendredi 2026-11-20 a 17:00
```

| Grandeur | Attendu | **Obtenu** | |
|---|---|---|---|
| fin de D | vendredi 2026-11-20 à 17:00 | **vendredi 2026-11-20 à 17:00** | conforme |
| durée de C | 28 jours calendaires, finissant quand D commence | **28 days, 0:00:00**, et `fin(C) == debut(D)` | conforme |
| B | vendredi 2026-10-23, avant 14:00 | **vendredi 2026-10-23 à 11:30 → 12:00** | conforme |
| A | réparti sur les 22 et 23 octobre | **jeudi 22/10 15:00-17:00 et vendredi 23/10 09:30-11:30** | conforme |

**Aucun écart.** Je le dis avec la réserve qui s'impose : ces quatre valeurs
étaient données dans le prompt, et le fait qu'elles tombent juste prouve que le
mécanisme se comporte comme attendu **sur ce cas**, pas qu'il est correct en
général. Ce sont les trois contrôles ci-dessous qui testent le mécanisme.

### 2.2 Les trois contrôles de mécanisme

#### Contrôle 1 — la chaîne est gouvernée par le délai, pas par la capacité — **PASSÉ**

Deux assertions séparées, chacune dirigée contre un mode de panne précis :

- `plan.debut(B) < 2026-11-01` — **obtenu 2026-10-23**. Si B tombait en novembre,
  le délai de 4 semaines ne se propagerait pas en arrière.
- `plan.debut(D) >= 2026-11-01` — **obtenu 2026-11-20**. Si D tombait en octobre,
  l'intervalle externe ne bloquerait pas ses successeurs.

La chaîne recule bien de 28 jours pleins depuis l'échéance, et pas d'un nombre de
jours dicté par la charge de travail (7 h 30 au total, soit moins de deux journées).

#### Contrôle 2 — la capacité reste intégralement disponible pendant les 28 jours — **PASSÉ**

Trois tâches de 30 h ajoutées. Sortie brute :

```
  statut : FEASIBLE | retard : 0 | en retard : (aucune)
  Remplissage 1 : 15 blocs, 1 day, 6:00:00 au total (attendu 30:00:00)
  Remplissage 2 : 15 blocs, 1 day, 6:00:00 au total (attendu 30:00:00)
  Remplissage 3 : 15 blocs, 1 day, 6:00:00 au total (attendu 30:00:00)

  fabrication : vendredi 2026-10-23 a 14:00 -> vendredi 2026-11-20 a 14:00
    lun 2026-10-26 : 8 creneaux  PLEIN
    ... (19 lignes, toutes a 8 creneaux)
    jeu 2026-11-19 : 8 creneaux  PLEIN

  -> 19 jours pleins, 0 partiels, 0 vides
  jours depassant la capacite de 4 h : (aucun)
```

(`1 day, 6:00:00` est la représentation d'un `timedelta` de **30 h**.)

**Les 19 jours ouvrés entièrement contenus dans l'intervalle de fabrication sont
tous chargés à 8 créneaux, c'est-à-dire 4 h pleines — la journée utile entière.**
Zéro jour partiel, zéro jour vide, et aucun jour ne dépasse la capacité : la marge
de 2 h est bien réservée partout.

Si C était entré dans `AddNoOverlap`, ces 19 jours seraient tous vides et les 90 h
ne tiendraient nulle part. **C'est le bug que ce projet existe pour éviter, et il
n'est pas là.**

Un quatrième test l'assène par un autre angle : il compte les blocs non externes
dont l'intervalle **chevauche** celui de C, et vérifie qu'ils représentent au moins
60 h. Avec un `AddNoOverlap` incluant C, ce nombre serait exactement zéro.

#### Contrôle 3 — le tampon distingue bien trois cas — **PASSÉ**

Trois assertions distinctes sur la même valeur :

- `!= 2026-11-24 17:00` → le tampon **est** appliqué ;
- `> 2026-11-19 23:59` → il n'est **pas** appliqué deux fois ni cumulé ;
- `== 2026-11-20 17:00` → seule la bonne valeur passe.

Et le non-cumul le long de la chaîne est vérifié séparément : A, B et C héritent
**exactement** de la limite de D (`vendredi 2026-11-20 à 17:00`), sans re-tamponner.
Un test du lot 2 le prouve en plus sur une chaîne de **cinq** tâches.

---

## 3. Les lots terminés

Les lots 0 à 4 ont été **vus rouges avant d'être verts**, et le rouge est reproduit
ci-dessous pour chacun, parce qu'un test qui n'a jamais rougi ne prouve rien.
**Le lot 5 fait exception** : ses tests ont été écrits après le code. Je ne le
maquille pas — voir §3.1, où je dis ce que j'ai fait à la place.

| Lot | Tests | Vu rouge — comment | État |
|---|---|---|---|
| **0** — socle, modèle, lecture Taskwarrior | 23 | `ModuleNotFoundError: No module named 'planif.config'` à la collecte, avant d'écrire une ligne de `planif/` | vert |
| **1** — calendrier disponible | 13 | `ModuleNotFoundError: No module named 'planif.calendrier'` | vert |
| **2** — tampon et dérivation des échéances | 9 | `ModuleNotFoundError: No module named 'planif.tampon'` | vert |
| **3** — pré-vérifications | 12 | 12 échecs, tous `ModuleNotFoundError: No module named 'planif.verifications'` | vert |
| **4** — modèle CP, passe 1 | 12 | `ModuleNotFoundError: No module named 'planif.solveur'` à la collecte | vert |
| **5** — tiers et précédences | 18 | **non, écrit après le code** — remplacé par un test de mutation, §3.1 | vert |

Les lots **6 à 9** et le lot **Z** n'ont pas été abordés, par consigne.

### Ce que chaque lot vérifie vraiment

- **Lot 0** — 23 tests. Les accents survivent à l'aller-retour `task import` /
  `task export` (le test échoue si on oublie `encoding='utf-8'`). Les tags sont
  traduits en marqueurs. `parse_duree` accepte `PT1H30M`, `90min`, `1.5h`, `P28D`
  et **refuse `1h30`**, que Taskwarrior rejette lui-même.
- **Lot 1** — 13 tests. Journée pleine, réunion à cheval sur deux créneaux, réunion
  coupant une plage en deux, week-end vide, **marge supérieure à la grille rendant
  zéro et pas un négatif**, granularité passée à 15 min sans rien casser,
  alignement qui rétrécit.
- **Lot 2** — 9 tests. Les deux exemples du cahier des charges (jeudi 14 h → mardi
  18 h 30 ; mardi 8 h → vendredi 18 h 30), avec une assertion sur `.weekday()` pour
  que le test prouve qu'il teste ce qu'il croit. Le cas `due` un lundi qui doit
  reculer jusqu'au vendredi — celui qui casse une implémentation naïve en `t − 1 jour`.
  Et la chaîne de cinq tâches à un seul tampon.
- **Lot 3** — 12 tests. Les cinq vérifications, **plus** le cas nominal qui ne doit
  rien produire, **plus** une tâche insécable qui *tient* et ne doit pas être
  signalée. Le module n'importe pas `ortools` et un test l'assène.
- **Lot 4** — 12 tests. Une tâche datée placée **à sa limite et pas avant** ; aucun
  chevauchement, vérifié par boucle sur les blocs triés ; aucun bloc hors des plages
  de la grille ; la marge quotidienne jamais dépassée **et atteinte au moins une
  fois** ; et le test qui compte le plus : **une échéance intenable est signalée
  sans empêcher les autres d'être planifiées**.
- **Lot 5** — le scénario de référence et les trois contrôles ci-dessus.

Le message de la tâche insécable propose bien les trois issues, et ses chiffres sont
calculés, pas écrits en dur :

> La tâche « Gros bloc indivisible » (8 h indivisible) ne tient dans aucune plage
> contiguë de vos journées en contexte « pro » (plus grande plage disponible :
> 4 h 30, pour 6 h utiles au maximum par jour) — découpez la tâche, déclarez une
> journée exceptionnelle, ou rognez la marge ce jour-là.

---

### 3.1 Lot 5 — 18 tests, et une preuve plus forte qu'un rouge de collecte

**Aveu d'abord** : j'ai écrit `tests/test_lot5_tiers.py` **après** `planif/solveur.py`,
et non l'inverse. Ces 18 tests n'ont donc jamais rougi de la façon attendue. C'est
un écart à la règle, et le dire vaut mieux que de le maquiller en renommant le
module pour provoquer un `ImportError` qui n'aurait rien prouvé d'autre qu'un
import cassé.

J'ai fait à la place quelque chose de plus probant : **injecter le bug exact que
tout ce projet existe pour éviter**, et vérifier que les tests le détectent. La
mutation ajoute la tâche `+externe` à `AddNoOverlap` — deux lignes :

```python
            intervalles_ressource.append(
                modele.NewIntervalVar(depart, taille, arrivee, "MUTANT"))
```

Résultat, sortie brute :

```
FAILED tests/test_lot5_tiers.py::test_controle_2_les_trois_taches_de_30h_sont_integralement_placees
FAILED tests/test_lot5_tiers.py::test_controle_2_la_capacite_reste_entiere_pendant_la_fabrication
FAILED tests/test_lot5_tiers.py::test_controle_2_du_travail_chevauche_bien_l_intervalle_externe
3 failed, 15 passed in 63.54s (0:01:03)

plan_avec_remplissage = Plan(blocs=(), ..., statut='INFEASIBLE', ...)
```

**Exactement les trois tests du contrôle 2 tombent, et le scénario devient
`INFEASIBLE`** : les 90 h de travail ne tiennent plus nulle part, parce que la
fabrication mange 28 jours de capacité. La mutation a ensuite été retirée et la
suite repassée au vert.

**Un enseignement au passage, qui vaut plus que le test lui-même :** sous la
mutation, les **15 autres tests passent toujours**, y compris toutes les dates du
cas de référence. La chaîne seule ne révèle pas le bug — il n'y a aucun travail
concurrent pour se faire évincer. **Sans le contrôle 2, on aurait vu un plan
parfaitement conforme aux quatre valeurs attendues, avec le bug dedans.** C'est
précisément pour ça que le contrôle 2 est écrit comme il est.

### 3.2 Le compte des tests

```
87 passed in 129.59s (0:02:09)
```

Et le compte se réconcilie, lot par lot : 23 + 13 + 9 + 12 + 12 + 18 = **87**.
Aucun test n'a été collecté sans tourner.

---

## 4. Les frictions

### 4.1 Ce qui a coûté du temps

**Le solveur est lent, et c'est mon choix de déterminisme qui le rend lent.**
J'ai posé `num_search_workers = 1` et `random_seed = 0` pour qu'un test d'égalité
de plans entre deux exécutions ait un sens. Conséquence mesurée : le lot 5 prend
**63 s**, le lot 4 aussi, et le scénario du contrôle 2 (environ 50 blocs pour
environ 80 fenêtres candidates chacun) **atteint le plafond de 60 s** et rend
`FEASIBLE` au lieu d'`OPTIMAL`.

Ce que cela veut dire, précisément — c'est important :

- Les **contraintes** sont dures, donc tout ce que le contrôle 2 mesure (capacité
  respectée, 90 h intégralement placées, aucun jour au-dessus de 4 h) **reste
  valide**. Un plan `FEASIBLE` est un plan correct.
- Ce qui n'est **pas** prouvé sur ce scénario, c'est l'**optimalité** du « au plus
  tard en sécurité ». Le plan pourrait être plaçable un peu plus tard.
- Le cas de référence seul, lui, rend bien **`OPTIMAL`**. Les quatre valeurs
  mesurées sont donc des optima prouvés, pas des solutions de repli.

La parade prévue par `proposal.md` (« horizon détaillé court, agrégation au-delà »)
n'a **pas** été mise en œuvre : j'ai modélisé les 57 jours d'horizon au créneau de
30 min. C'est assumé pour ce soir — le modèle reste petit en nombre de tâches — mais
**c'est le premier mur qu'on rencontrera sur les 277 tâches réelles**.

**Deuxième perte de temps, évitable** : mes fixtures `pytest` du lot 5 étaient au
départ de portée *fonction*, donc le solveur repartait à zéro à chaque test. Le
premier lancement a dû être interrompu. Passées en `scope="module"`, on est revenu
à 63 s. À retenir pour tous les lots qui appelleront le solveur.

### 4.2 Trois défauts que j'ai introduits et corrigés dans mon propre solveur

Je les liste parce qu'ils sont le genre de chose qui passe la revue et casse plus tard :

1. `statut=cp_model.OPTIMAL and s2.StatusName(etat)` — une expression parasite qui
   *marchait par accident* (`cp_model.OPTIMAL` vaut 4, donc vrai, donc l'expression
   rendait bien le nom du statut). Aucun test n'aurait attrapé ça.
2. La capacité quotidienne était indexée **par jour seulement**, pas par
   `(contexte, jour)`. Avec un seul contexte c'est correct ; avec `pro` **et**
   `perso` le même jour, les deux se seraient écrasés. Le cas de référence n'a
   qu'un contexte : **aucun test actuel n'aurait détecté ce bug.** Corrigé avant
   de le découvrir en production, mais il n'est toujours pas couvert par un test —
   il faudra un scénario à deux contextes.
3. Une branche « aucune fenêtre ne peut accueillir ce bloc » créait un littéral
   booléen mort inutile. Simplifiée en une borne qui vide le domaine.

### 4.3 Ce qui ne marche pas comme on pourrait le croire

- **Le contrôle « A réparti sur les 22 et 23 octobre » n'est pas une coïncidence
  de calendrier.** A fait 4 h, soit deux blocs de 2 h, et la capacité journalière
  est de 4 h : A tiendrait dans une seule journée. Ce qui la coupe en deux, c'est
  que la **matinée** du 23 ne fait que 3 h et que B doit passer avant 14 h. Le
  résultat attendu dépend donc de la **forme** des créneaux, pas seulement du
  volume — ce qui est exactement l'argument du cahier des charges contre un modèle
  en heures-par-jour. C'est rassurant : le cas de référence teste bien ce pour quoi
  il a été construit.
- **`P28D` n'est pas normalisé par Taskwarrior.** Vérifié sur base jetable :
  `PT4H`, `PT30M` et `P28D` traversent `task import` puis `task export` inchangés
  (`P28D` ressort `P28D`, pas `P4W` ni `PT672H`). Mon parseur accepte aussi `P4W`,
  mais **je ne l'ai jamais vu produire par Taskwarrior** — c'est une tolérance en
  lecture, pas un comportement observé.
- **`pytest` installé est en `9.1.1`** alors que `requirements-dev.txt` demande
  `pytest>=8.0`. Rien de cassé, mais la borne haute est ouverte.
- **L'outil `bash` de mon environnement a échoué plusieurs fois sur des
  *heredocs*** (dépassements de délai, puis une erreur de *quoting* qui a avorté
  une écriture de ce rapport). Sans conséquence sur le dépôt — l'écriture partielle
  n'a pas eu lieu — mais c'est ce qui a le plus ralenti la nuit après le solveur.

### 4.4 Sur l'isolation des données

**Un lapsus à signaler honnêtement** : un `task --version` a été lancé **sans
`TASKRC` posé**, avant la création de la base jetable. C'est une lecture de numéro
de version qui ne touche à aucune donnée, mais la consigne dit « y compris une
simple lecture ». **Aucune autre commande `task` n'a été lancée sans isolation**,
et aucune commande d'écriture, jamais.

Le reste a été fait dans les règles :

- base jetable créée **sous le répertoire temporaire de session**, pas dans
  `~/taskwarrior-dev` (qui existe et appartient à l'utilisateur) ;
- `task _show | grep data.location` vérifié **avant** la première écriture, et la
  fixture `tests/conftest.py` **refait ce contrôle et lève une assertion** si
  l'isolation ne pointe pas où elle croit ;
- `confirmation=off` **et** `bulk=0` posés dans le `taskrc` jetable (AGENTS.md §5 :
  `confirmation=off` seul ne couvre pas la confirmation de lot) ;
- chaque test qui touche Taskwarrior crée sa **propre** base dans son `tmp_path`.

La base réelle de l'utilisateur n'a jamais été ouverte, ni en lecture, ni en écriture.

---

## 5. Ce que le run a tranché, et ce qu'il soulève

### 5.1 Tranché — vérifié en l'exécutant

- **`ortools` s'installe et tourne sur cette machine.** 9.15.6755, `win_amd64`,
  modèle trivial résolu `OPTIMAL`. Tout le reste en dépendait.
- **L'approche par contraintes traite le cas qui a motivé le projet.** Un
  intervalle absent de `AddNoOverlap`, c'est bien *une ligne*, et ça suffit : la
  fabrication prend 28 jours calendaires sans consommer une minute de capacité, et
  les 19 jours ouvrés qu'elle recouvre restent chargés à 4 h pleines.
- **Le tampon appliqué une seule fois donne la bonne date, et ne se cumule pas**
  sur une chaîne de cinq tâches.
- **Une échéance intenable n'empoisonne pas le plan.** L'échéance est une
  contrainte *souple* : le dépassement remonte dans `retard_total` et `en_retard`,
  et les tâches saines restent toutes intégralement planifiées. C'est le défaut
  observé sur taskcheck, et il n'est pas reproduit ici.
- **Taskwarrior 3.5.0, sur base jetable** : les accents survivent à
  `task import <fichier UTF-8>` puis `task export`, avec `encoding='utf-8'`
  explicite. L'UDA `estTime` accepte `PT4H`, `PT30M`, `P28D`.

### 5.2 Soulevé — pour vous, par ordre d'importance

1. **Comment une échéance de projet descend-elle sur les tâches ?** J'ai posé
   « sur les tâches terminales du projet », et c'est ce qui fait tomber le cas de
   référence juste. Mais c'est **mon** choix, pas celui du cahier des charges.
   Variante plausible : sur *toutes* les tâches du projet. À trancher — c'est une
   décision de modèle, pas un détail d'implémentation.
2. **Le flux iCal reste à brancher, et c'est bloquant pour la production.** Sans
   lui, le plan ignore les réunions et sera trop optimiste. `tasks.md` le posait
   déjà comme « à trancher avant le lot 4 » ; le lot 4 est écrit, la question reste
   entière. Elle demande une dépendance nouvelle (aucune bibliothèque iCal n'est
   déclarée dans `requirements.txt`) — donc **votre accord**, je n'en ai ajouté aucune.
3. **Aucun projet réel n'a d'échéance.** Tant que ce sera vrai, la passe arrière
   n'aura rien à dire des 277 tâches de production. Il en faut **au moins une** pour
   que l'outil serve à quelque chose.
4. **La convention sur les `datetime` naïfs diverge entre deux modules**
   (§1.2 point 8). Taskwarrior exporte de l'UTC *aware* ; les grilles sont locales
   et naïves. Il faut une convention unique, écrite une fois, avant que ça morde.
5. **La performance du solveur est le prochain mur.** Environ 50 blocs sur 57 jours
   au créneau de 30 min atteint déjà le plafond de 60 s en mono-worker. Les 277
   tâches réelles ne passeront pas comme ça. Deux leviers, dans cet ordre :
   l'horizon détaillé court avec agrégation au-delà (déjà prévu, `proposal.md`
   risque n° 1), puis éventuellement le multi-worker — mais il faudra alors
   renoncer au test d'égalité de plans, ou le formuler autrement.
6. **`+asap` n'est pas implémenté.** `proposal.md` décision 7 le prévoit comme une
   échéance artificielle proche. Le marqueur est lu et exposé (`Tache.asap`), mais
   le solveur n'en fait rien. Ce n'était dans aucun lot de cette nuit ; je le
   signale pour qu'il ne soit pas cru fait.
7. **`+fige` est implémenté mais n'a aucun test.** Le code fixe le premier bloc sur
   le `scheduled` courant ; personne ne l'a vérifié. À traiter comme non éprouvé.

### 5.3 État du dépôt au matin

Branche `main`, **rien n'a été poussé**, conformément à la consigne. Le commit local
non poussé d'avant le run est resté tel quel. Commits ajoutés cette nuit :

```
Etape 0 : inventaire et socle technique
Lot 0 : socle, modele de donnees et lecture Taskwarrior
Lots 1 et 2 : calendrier disponible et tampon de securite
Lot 3 : pre-verifications, sans jamais appeler le solveur
Lots 4 et 5 : modele de contraintes et tiers hors non-chevauchement
```

`../WebTaskManager` n'a pas été touché. `README.md` n'a pas été réécrit. Aucun
défaut de taskcheck n'a été corrigé et rien n'a été ouvert chez lui (lot Z, différé).
Aucune dépendance n'a été ajoutée à `requirements.txt`. Le téléphone n'a pas été
touché.

### 5.4 Par où reprendre

Dans cet ordre, à mon avis :

1. Trancher le point 1 (échéance de projet → tâches) : tout le reste en dépend.
2. Lot 6, la passe opportuniste — c'est ce qui rendra l'outil utilisable sur les
   224 tâches non datées, et `proposal.md` prévient qu'il doit arriver **en même
   temps** que le régime « au plus tard », sinon l'outil paraîtra cassé.
3. Lot 7, la sortie JSON — c'est le contrat avec `../WebTaskManager`.
4. Un scénario de test à **deux contextes**, pour couvrir le bug de capacité
   décrit en §4.2 point 2, qui n'est aujourd'hui corrigé que par relecture.
