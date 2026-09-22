# Reste à faire

**Ce fichier existe parce que la conversation n'est pas une mémoire.** Des points
décidés ensemble ont été perdus faute d'être écrits quelque part : l'acquisition
Outlook, l'ordre par urgence de la passe 2, le nettoyage de la casse des projets.
Tout point discuté et non fait s'écrit ici, le jour où il est discuté.

Il ne remplace pas `openspec/changes/ordonnanceur-par-contraintes/tasks.md`, qui
décrit les lots 0 à 8 tels qu'ils ont été spécifiés au départ. Il recense ce qui
est apparu **depuis**, ou ce que ces lots ont laissé ouvert.

Dernière mise à jour : 2026-09-22, après le run de nuit.

---

## A. Décidé, spécifié, pas encore fait

Rien à trancher ici : la décision est prise, il reste à l'écrire en code.

> **A1, A2 et A3 sont faits** (run de nuit du 22/09/2026, commits `3919ac8`,
> `d43da05`, `68c2d09`). Leurs sections sont conservées telles quelles : elles
> portent les mesures et les raisons, qui restent utiles. Ce qui reste ouvert
> est **A5**, plus le lot Outlook dont la partie affichage n'est pas tranchée.

### ~~A1.~~ FAIT — Propagation d'une échéance aux sous-projets

Aujourd'hui `planif/echeances.py` compare les noms de projet à l'identique. Une
échéance sur `NPD.Heliside.US` ne touche donc pas `NPD.Heliside.US.plans`, alors
que Taskwarrior y voit une hiérarchie.

Règles arrêtées :

- préfixe sur **frontière de point** : `NPD.Heliside.US` couvre
  `NPD.Heliside.US.plans`, **pas** `NPD.Heliside.USA` ;
- **le préfixe le plus long gagne** : si `NPD.Heliside` et `NPD.Heliside.US`
  portent tous deux une échéance, les plans prennent celle de `US` ;
- **insensible à la casse**, parce que les données réelles portent
  `NPD.Heliside.MRE` et `NPD.heliside.MRE` comme deux projets distincts alors
  que c'est le même.

**Conséquence à ne pas manquer :** dès qu'une échéance couvre un sous-arbre, les
tâches terminales doivent se calculer **sur l'arbre entier**, pas sous-projet par
sous-projet. Sinon `NPD.Heliside.US.plans` a ses propres terminales, qui
reçoivent l'échéance finale alors qu'elles alimentent le montage. C'est
exactement la panne que la règle des terminales existe pour éviter.

C'est ce point qui rendra opérantes les deux dates de `echeances.json`, et qui
donnera une échéance aux **149 tâches** de `NPD.Heliside.US` et
`NPD.Heliside.MRIS` qui n'en ont aucune aujourd'hui.

### ~~A2.~~ FAIT — Écriture de `due` et `duePlanif` dans Taskwarrior

`planif/dues.py` calcule les dates ; rien ne les écrit. L'écriture va derrière un
drapeau de ligne de commande, sur le modèle de `--ecrire-scheduled`.

**Précédée du test qui manque, et il doit être vu rouge :** deux exécutions
successives avec écriture doivent rendre le même plan. `duePlanif` empêche le
tampon de se cumuler d'un run à l'autre, mais rien ne garantit encore que la
boucle `due → urgency → placement → due` converge.

L'UDA à déclarer dans le `taskrc` : `uda.duePlanif.type=date`.

### ~~A3.~~ FAIT — Précocité et ordre dans la passe 2

**Le diagnostic initial était faux, et la correction vaut d'être lue.** On avait
écrit « la passe 2 n'optimise pas la précocité ». La lecture du code montre le
contraire : elle maximise `Σ urgence × présence`, puis, à urgence figée,
minimise `Σ débuts`. Ce qui manquait n'était pas l'objectif mais sa
**pondération** — une somme de débuts non pondérée est indifférente à qui passe
devant. Mesuré : la tâche la plus urgente du jeu de
test est passée du 05/10 au 12/10 alors que les créneaux du 05 au 09 sont libres
dans les deux cas — rien ne l'y forçait.

`tests/test_lot6_opportuniste.py::test_les_opportunistes_sont_placees_au_plus_tot`
est en `xfail(strict=True)` : il redeviendra rouge tout seul le jour où la
précocité entrera dans l'objectif. C'est le critère d'acceptation.

C'est le même trou que « par urgence décroissante » du lot 6
(`tasks.md`), jamais implémenté. La passe 2 étant celle qui produira le planning
réellement exécuté, ce point prime sur le reste.

### A4. Réserve de capacité pour le travail non daté

Sans elle, une tâche sans échéance a une urgence faible et se fait repousser
indéfiniment. **Le calcul d'urgence de Taskwarrior ne doit pas être touché** :
c'est un empilement de coefficients, le régler à tâtons pour corriger un problème
d'ordonnancement ne peut donner aucun test rouge pour la bonne raison, et ça
casserait les vues normales.

Le problème n'est pas « ces tâches marquent trop peu », c'est qu'**aucune
capacité ne leur est réservée**. La correction est une contrainte dans la passe 2
— un plancher d'heures par semaine pour le non-daté.

Le mécanisme de planification sans date reste tel quel en attendant (décision
utilisateur du 22/09).

### A5. Consigner la décision `assignee`

Pas de champ `assignee` : le solveur n'a besoin que de savoir si une tâche
consomme de la capacité, et `+externe` y répond. L'acteur se note **en tag** :
`+externe +serviceAchat`, `+externe +Ludovic`, ce qui permet de filtrer
`task +externe +serviceAchat` pour voir ce qu'un tiers a à faire.

Une capacité limitée **par acteur** (le service achat ne traite pas trois
demandes en parallèle) serait une tout autre fonctionnalité. Écartée pour
l'instant.

À écrire dans `design.md`, sinon ça se perdra comme le reste.

---

## B. À trancher, ou à régler à l'usage

### B1. `marge_jour` du contexte pro

`disponibilite = grille − réunions − marge_jour` (`planif/calendrier.py`). La
grille pro fait 6 h ; avec `marge_jour = 3h` on obtient la pratique réelle de la
revue hebdo : 3 h planifiées par jour, le reste laissé à l'imprévu. C'est un
réglage, pas une fonctionnalité. **À ajuster à l'usage**, après le premier vrai
plan.

### B2. Budget du solveur

`TEMPS_DETERMINISTE_MAX = 5.0`. Prouvé sans perte sur la base actuelle (54 tâches
datées) ; coûte 0,062 % de marge sur un banc à 100 tâches. **À remonter si la
base grossit** — et elle va grossir de 149 tâches dès que A1 sera fait. À
re-mesurer à ce moment-là, pas avant.

### B3. Un coussin sur le placement de la passe 2 ?

Le tampon de 24 h a été retiré de la passe 1 : une `due` calculée dit quand il
est réellement trop tard. La question reste ouverte de savoir si le *placement*
de la passe 2 doit, lui, garder une marge — et laquelle. Deux objets différents,
à ne pas re-mélanger.

### B4. La cible de performance : un arbitrage produit, pas technique

100 tâches en moins de 30 s : mesuré 60,8 s, statut `FEASIBLE` au lieu
d'`OPTIMAL`. Le mur est identifié — c'est la preuve d'optimalité de la passe 2,
pas la construction du modèle. Trois directions, et le choix t'appartient :

- **(a)** accepter `FEASIBLE` et afficher un plan non prouvé optimal ;
- **(b)** réduire l'horizon détaillé sous 2 semaines ;
- **(c)** accepter une optimalité approchée en bornant l'écart.

Jamais tranché. Signalé dans `RAPPORT-NUIT-2.md` et jamais remonté depuis.

**Mesure du 22/09/2026, qui pèse sur cet arbitrage.** La suppression du tampon
de la passe 1 (B3, décision du 22/09) coûte du temps de résolution sur ce banc.
Mesuré dans un même processus, même machine, budget figé à 30 :

    sans tampon (HEAD)            139,6 s   FEASIBLE
    avec tampon (avant a882452)   111,2 s   FEASIBLE

**+28 s, soit +26 %.** C'est le prix d'une `due` qui dit la vérité, et il est
assumé. En revanche, aucun écart mesuré dans deux exécutions différentes ne doit
être invoqué ici : le budget déterministe fige le TRAVAIL, pas le temps mural,
qui dépend de la charge de la machine. Les 60,8 s citées par
`RAPPORT-NUIT-2.md` viennent d'un autre run et ne se comparent pas à celles-ci.

### B5. La grille du cas de référence n'est pas ta vraie grille

Les tests imposent `09:00-12:00` / `14:00-17:00`, soit 6 h. Ton `config.json`
porte `08:30-12:00` / `14:00-18:30`, soit **8,5 h**. Les deux coexistent
volontairement — aucune règle n'a été recalibrée pour tomber sur les valeurs
attendues — mais toute discussion sur `marge_jour` (B1) doit se faire sur la
vraie grille, pas sur celle des tests.

### B6. L'objectif du régime agrégé : au jour ou au créneau ?

Essayé au jour, aucun gain de performance mesuré, annulé. À reprendre si la
question revient **par la sémantique** plutôt que par la performance.

### B7. Les 53 tâches dont l'échéance est déjà dépassée

`--ignorer-due-depassee` existe. Le ménage est une décision utilisateur, pas un
blocage.

### B8. Les 81 tâches sans `estTime`

Sur 278. Une tâche sans durée est **invisible au solveur**. Une échéance posée
sur un projet dont les tâches n'ont pas de durée ne produit rien.

---

## C. Hors de cette machine

### C1. Réunions Outlook — la lecture est faite, l'affichage non

**Fait** (commit `ade923f`) : `outils/extraire-outlook.ps1` extrait l'agenda en
lecture seule, `planif/reunions.py` filtre et alimente le solveur. Le plan ne
ignore plus les réunions. Deux choses mesurées sur l'export réel ont corrigé la
conception : l'`entryId` appartient à la **série** et non à l'occurrence (18
occurrences, 6 identifiants), et **6 événements sur 18 sont `Free`**, donc la
présence d'un événement ne vaut pas occupation.

**Reste ouvert : où les réunions s'affichent.** Calendar-planner lit
`task scheduled.not: export`, donc il ne voit que Taskwarrior. Trois formes
possibles, discutées le 22/09 :

1. calendar-planner reste, CalDAV s'ajoute — coût nul, c'est l'existant ;
2. calendar-planner devient un éditeur CalDAV — **à éviter** : on relit ses
   propres écritures, le piège que la séparation Outlook/CalDAV évitait ;
3. calendar-planner est abandonné, CalDAV affiche tout — le moins cher en
   maintenance, mais on perd le kanban et l'édition rapide.

Avis donné : **1 maintenant, 3 comme horizon, jamais 2.**

L'ancienne conception « une réunion = une tâche Taskwarrior `+meeting` » n'est
plus nécessaire pour le calcul. Si elle revient, ce sera pour l'affichage ou
pour pouvoir poser un `depends` sur une réunion — et l'idempotence devra alors
se faire sur `entryId + date de début`, jamais sur `entryId` seul :

- une réunion est une tâche Taskwarrior `+meeting`, avec `scheduled` et
  `estTime`, ce qui implique le marqueur `+fige` existant ;
- acquisition par PowerShell + Outlook COM, **sur le PC professionnel**.

Deux décisions restent ouvertes : l'idempotence (un UDA `outlookId` pour ne pas
réimporter deux fois la même réunion) et la pollution des vues de tâches
normales par des dizaines de réunions.

**Tout import réel est lancé par l'utilisateur lui-même.**

### C2. Nettoyage de la casse des projets

Les données portent `NPD.Heliside` / `NPD.heliside`, `NPD.Heliside.MRE` /
`NPD.heliside.MRE`, `NPD.Heliside.IOM` / `NPD.heliside.IOM`, `NPD.helisem` /
`Helisem` — des projets distincts pour Taskwarrior alors que ce sont les mêmes.
A1 rend la comparaison insensible à la casse, ce qui traite le symptôme ; le
nettoyage des données reste à faire.

Les commandes `task ... modify project:...` peuvent être préparées ici ;
**l'utilisateur les lance lui-même sur sa base.**

### C3. Rien n'est poussé

Le dépôt est en avance sur `origin/main` et rien n'a jamais été poussé. C'est une
décision utilisateur, jamais prise à sa place.

---

## D. Limites connues et assumées

- **Jours fériés ignorés.** Aucun calendrier de jours fériés n'existe dans le
  dépôt ; `Contexte.est_ouvre` ne connaît que les jours de la semaine.
- **`planif/diagnostic.py` duplique une quarantaine de lignes de
  `planif/solveur.py`.** Deux copies qui peuvent diverger.
- **`+asap` n'est pas implémenté.**
- **`planif/tampon.py::_contexte_de` retombe silencieusement sur le contexte
  `pro`** quand celui d'une tâche est inconnu ou absent. Interprétation déclarée
  dans le code, jamais confirmée.
- **La cible de performance à 100 tâches n'est pas atteinte**
  (`tests/test_perf_horizon.py`, `xfail(strict=True)`). Ce n'est pas la
  construction du modèle qui coûte, c'est la preuve d'optimalité de la passe 2.
- **Lot Z — remontées amont vers taskcheck** : différé, décision utilisateur.
- **En régime agrégé, deux blocs d'une même journée peuvent se chevaucher dans
  la sortie.** Ce ne sont plus des placements horaires mais des affectations à
  une journée — conséquence assumée du design.md §1, pas un défaut.
- **`SufficientAssumptionsForInfeasibility()` peut rendre une liste vide** quand
  le presolve tranche avant que le mécanisme d'hypothèses n'entre en jeu. Le
  diagnostic annonçait alors quelque chose de faux ; contourné par des
  pré-vérifications en amont, mais la limite d'OR-Tools reste.
- **`deepWorkLimit = 4` de `config.json` n'est utilisé nulle part**, et ce n'est
  pas le bloc minimum.
- **Clés de `config.json` non reprises** : `timeSlots.sleep`, `timeSlots.asso`,
  `commuteTime`, `plannedDurationDays`, `timezone`.
- **`P4W` est toléré en lecture mais n'a jamais été observé produit par
  Taskwarrior.** Tolérance, pas comportement constaté.
- **`README.md` n'a jamais été réécrit** (2 lignes).
- **La suite de tests dure ~4 min**, presque entièrement du temps solveur. Chaque
  lot qui appelle `resoudre` en rajoute.
- **`pytest` installé est en 9.1.1** alors que `requirements-dev.txt` demande
  `>=8.0` : la borne haute est ouverte.
- **Le régime « au plus tard » n'a jamais tourné de bout en bout sur les données
  réelles.** `echeances.json` porte enfin deux dates ; tant que A1 n'est pas
  fait, elles ne touchent presque rien.
