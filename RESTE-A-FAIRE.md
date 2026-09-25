# Reste à faire

**Ce fichier existe parce que la conversation n'est pas une mémoire.** Des points
décidés ensemble ont été perdus faute d'être écrits quelque part : l'acquisition
Outlook, l'ordre par urgence de la passe 2, le nettoyage de la casse des projets.
Tout point discuté et non fait s'écrit ici, le jour où il est discuté.

Il ne remplace pas `openspec/changes/ordonnanceur-par-contraintes/tasks.md`, qui
décrit les lots 0 à 8 tels qu'ils ont été spécifiés au départ. Il recense ce qui
est apparu **depuis**, ou ce que ces lots ont laissé ouvert.

Dernière mise à jour : 2026-09-23 (soir).

Ce carnet couvre **les deux dépôts** : `TaskWarriorPlanner` et
`WebTaskManager`. Une seule liste, pour ne pas la perdre en deux moitiés.

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

> **Mis de côté le 23/09** (décision utilisateur) : à revoir à l'usage.

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

### ~~A5.~~ FAIT — Consigner la décision `assignee`

> Déjà écrit dans `design.md` §1 (commit `8c51258`) : `+externe` dit si la
> tâche consomme ma capacité, un second tag nomme l'acteur si nécessaire.

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

> **Penchant du 23/09 : (a)**, accepter un plan non prouvé optimal. À confirmer
> par l'utilisateur après ses essais réels.

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

Avis **corrigé le 23/09** : **1**, et rien d'autre. CalDAV est un *protocole de
synchronisation*, pas une interface : le client serait Nextcloud, Thunderbird ou
un téléphone, et surtout **aucun d'eux ne sait renvoyer quoi que ce soit à
Taskwarrior**. On y perdrait la planification manuelle et l'ajustement, c'est-à-
dire exactement ce qu'on veut garder. L'option 3 n'est pas un horizon : c'est au
mieux un satellite en lecture seule pour le téléphone. Calendar-planner reste
l'endroit où l'on ajuste.

**Timewarrior fait repencher la balance vers les tâches Taskwarrior** (point
soulevé le 23/09). Le hook `on-modify` déclenche Timewarrior sur `task start`
avec les tags de la tâche : une réunion-tâche donne `task <réunion> start` et le
temps se range seul sous `+meeting`. Avec un fichier, il faut `timew start` à la
main, sans lien. Avec l'argument `depends` (préparer un dossier pour une
réunion, et que ça suive si elle se déplace), l'option A a désormais **deux
usages réels** que le fichier ne sert pas.

Si on y va, le chemin est : extraction → `reunions.json` → **import** vers
Taskwarrior en `+meeting +fige` avec `scheduled` + `estTime`. Le solveur les lit
alors comme des tâches figées, mécanisme qui existe déjà. Idempotence sur
`entryId + date de début`, **jamais sur `entryId` seul**. Et la passe de ménage
(`task +meeting scheduled.before:now status:pending done`) est à écrire en même
temps, pas plus tard.

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

### C1bis. Outlook — ce qui n'est pas fait

- **Aucune détection de changement.** L'extraction est un instantané complet ;
  si une réunion se déplace, rien ne le signale et rien n'en tire de
  conséquence sur le plan. Non prioritaire (décision du 23/09), mais à savoir.
- Un seul calendrier (le calendrier par défaut), une seule fenêtre glissante,
  et l'extraction est manuelle.

### C2. Nettoyage de la casse des projets

Les données portent `NPD.Heliside` / `NPD.heliside`, `NPD.Heliside.MRE` /
`NPD.heliside.MRE`, `NPD.Heliside.IOM` / `NPD.heliside.IOM`, `NPD.helisem` /
`Helisem` — des projets distincts pour Taskwarrior alors que ce sont les mêmes.
A1 rend la comparaison insensible à la casse, ce qui traite le symptôme ; le
nettoyage des données reste à faire.

Les commandes `task ... modify project:...` peuvent être préparées ici ;
**l'utilisateur les lance lui-même sur sa base.**

### ~~C3.~~ Poussé le 23/09 (autorisation explicite de l'utilisateur)

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


---

## E. La boucle d'usage — ce qui manque pour s'en servir vraiment

Demandé le 23/09, et c'est ce qui transforme le projet en outil :

> lancer le programme depuis l'interface, voir le dry-run dans le calendrier,
> faire mes ajustements dessus, et valider ensuite pour créer vraiment.

**Ce qui existe déjà**, et qui est plus que prévu :

- `python -m planif` produit `plan.json` ;
- `calendar-planner.js` **lit déjà `/plan.json`** (lot 9, commit `07fa503`) :
  le plan est donc affichable sans rien écrire dans la base ;
- `--ecrire-scheduled` et `--ecrire-due` écrivent, et seulement sur demande ;
- `dry_run` existe dans les deux fonctions d'écriture.

**Ce qui manque**, dans l'ordre où ça se construit :

1. **E1 — lancer le calcul depuis l'interface.** Un endpoint dans
   `main_fastapi.py` qui exécute le planificateur et régénère `plan.json`, plus
   un bouton. Sans écriture dans la base : c'est le dry-run.
2. **E2 — distinguer à l'écran le proposé du réel.** Le calendrier affiche
   aujourd'hui `task scheduled.not: export` (le réel) *et* `/plan.json` (le
   proposé). Tant qu'on ne les distingue pas visuellement, on ne sait pas ce
   qu'on regarde.
3. **E3 — ajuster.** Déplacer un bloc dans la vue et que l'ajustement tienne :
   soit en épinglant la tâche (`+fige` + `scheduled`), soit en posant un `due`
   humain — qui, lui, survit à la replanification (voir A2).
4. **E4 — valider.** Un bouton qui lance l'écriture réelle
   (`--ecrire-scheduled --ecrire-due`) et rend le compte rendu
   `modifiees / inchangees / ignorees` que les deux fonctions produisent déjà.

E1 et E2 suffisent pour commencer à s'en servir. E3 et E4 ferment la boucle.

**E1 et E2 sont faits** (`dde8a1a`, `2ec9f9c`). **Décisions pour E3 et E4 (23/09)** :

- E3 : déplacer un bloc proposé **écrit tout de suite** `+fige` et `scheduled`
  (choix de l'utilisateur, contre la recommandation de tout garder jusqu'à
  Valider), puis relance un calcul sans écriture pour que le plan affiché
  intègre l'ajustement ;
- E4 : une tâche déplacée à la main reste `+fige` ; Valider écrit **exactement
  le plan affiché**, sans recalcul, et refuse si la base a changé depuis le
  calcul (empreinte `uuid|modified`).

**Run de nuit n°3 (24/09)** : étapes 0 à 6 faites (B `6334ef6`..`f6193d1`,
A `be7fc84`..`f0715ce`), détail dans `RAPPORT-NUIT-3.md`. Quatre points trouvés,
**les quatre sont désormais résolus** :

1. **`+fige` ignoré en passe 2**, RÉSOLU : commit `2a6f091` du planificateur
   (bloc 0 d'une `+fige` = fait constant dans les deux passes ; suite
   optionnelle ; `--appliquer` ne réécrit jamais une `+fige`) et commit
   `d8d9221` de WebTaskManager (Valider refuse un plan INFEASIBLE/UNKNOWN/
   MODEL_INVALID, la page affiche le statut). Scénario de la nuit rejoué sur
   la base de test : FEASIBLE, les figées restent à leur `scheduled`.
2. **Précédence perdue** (défaut antérieur, grave), RÉSOLU : commit `b2c395e`
   du planificateur (« Précédence : les prédécesseurs d'une tâche datée
   entrent en passe 1 »). Deux défauts : les prédécesseurs transitifs d'une
   tâche datée étaient envoyés en passe 1 ; une tâche détaillée pouvait
   déborder au-delà de la frontière des 14 jours en régime agrégé (avant :
   INFEASIBLE et plan vide). Sur la base de test : 23/50 → 43/50 tâches
   planifiées, `+externe` 0/5 → 5/5, 0 violation de précédence ; coût passe 1
   1 s → 11 s, statut FEASIBLE (cohérent avec B4).
3. **Un `+fige` sur une tâche à précision « jour » rend la passe 1
   infaisable**, RÉSOLU dans le même commit `2a6f091` que le point 1.
4. **`modify -TAGS` ne fait rien** sur Taskwarrior 3.5 (code 0, mesuré le
   24/09), RÉSOLU : commit `59d0073` de WebTaskManager. Correction du
   diagnostic : de bout en bout le retrait de tag marchait déjà via
   `repair_text_fields` (réimport complet de la tâche) ; corrigé quand même
   (une commande `-t`/`+t`) et ajout d'une validation des tags avant le shell
   (injection possible avant). Vérification sur le téléphone : plus
   nécessaire pour `-TAGS` (on n'utilise plus que `-t`/`+t`, validés partout).

**Défaut révélé en chemin, RÉSOLU dans `2a6f091`** : en passe 2, une candidate
d'urgence nulle ou négative (une tâche bloquée prend -5) n'était jamais placée.

Aussi : test Playwright `task-manager.spec.js:1085` sensible à l'heure corrigé
(WebTaskManager `0944d37`).

Faits mesurés qui en découlent : `plan.json` ne porte pas les `due` (à
ajouter) ; `+fige` n'impose que le début du bloc 0, donc seul ce bloc est
déplaçable.

**Points ouverts qui en découlent :**

- une passe 1 surchargée **sans** `+fige` (deux tâches qui se disputent la
  seule fenêtre, ou charge datée > capacité de tout l'horizon) peut encore
  être INFEASIBLE : piste = rendre chaque bloc de passe 1 optionnel avec une
  forte pénalité d'absence ; à lier à la variante « infaisable » de la base
  de test.
- message de refus de Valider : dit « infaisable » même pour UNKNOWN (qui
  veut dire « pas de solution trouvée dans le budget ») — à reformuler.
- `PUT /api/task/{id}/modify` et d'autres routes de `main_fastapi.py` passent
  `task_id` brut à un shell (`shell=True`) sans validation d'uuid,
  contrairement à `/depends`.
- suite Playwright complète à relancer sur une base remplie
  (`TASKRC=C:/Users/irpaui/taskwarrior-dev/taskrc npm test`) : non revalidée
  cette session.
- WebTaskManager : TaskEditor.show() est un no-op silencieux tant que le
  template de sa modale (chargé par fetch dans createModal) n'est pas arrivé :
  un clic très rapide après le chargement d'une page peut ne rien ouvrir. Le
  bouton Add task de la nav l'attend (b6ca1e5), mais les autres appels à show()
  non.
- WebTaskManager, import CSV : la détection de cycles inclut les dépends des
  tâches deleted ; faux refus possible, jamais d'écriture fautive.


---

## F. Les deux calendriers, et les régimes de capacité

> **Tranché le 23/09** : Outlook = **pro**, Nextcloud = **perso**, les deux à
> brancher. Réunions importées en tâches `+meeting` (C1, Timewarrior). Les
> régimes de période (F2) restent **en suspens** : l'utilisateur a recensé les
> cas (semaine normale, vacances, week-end vacances, week-end sportif, trajet
> voiture, trajet train) et doit préciser chacun. Tout est dans `design.md` §3.

Ajouté le 23/09.

### F1. Deux sources, pas une

- **Outlook** — *hypothèse à confirmer : c'est le calendrier **pro***. Le compte
  lu (`…@miltonroy.com`) contenait bien des réunions de travail. L'utilisateur a
  écrit « Outlook est le calendrier perso », ce qui contredit la mesure : à
  trancher avant d'écrire quoi que ce soit.
- **Nextcloud** (sur le téléphone) — les informations personnelles. Accès par
  CalDAV, la bibliothèque `caldav` est déjà utilisée par
  `TWsched_task_to_caldav.py` : rien de nouveau à installer.

L'extraction actuelle ne connaît qu'Outlook et un seul calendrier.

### F2. Les périodes ne font pas qu'occuper : elles changent le régime

C'est un **manque de modèle**, pas un réglage. Aujourd'hui une période se
soustrait comme un intervalle, uniformément. Or ce que l'utilisateur décrit est
autre chose :

| Période | Effet voulu |
|---|---|
| vacances | contexte `pro` à **zéro**, les autres contextes intacts |
| week-end en vacances | `sport` plafonné à 30 min, pas supprimé |

Deux conséquences immédiates :

1. **Un défaut actuel.** L'absence de 5 jours lue dans Outlook vide *toutes* les
   journées, **tous contextes confondus** — donc aussi `perso`, `sport`,
   `couture`. En vacances, on peut faire du sport. Le comportement est faux,
   et il n'est faux que depuis qu'on lit vraiment l'agenda.
2. **Le modèle doit accepter une modulation par (période × contexte)** : mettre
   à zéro, plafonner, ou laisser tel quel. `Contexte.marge_jour` est global et
   ne sait pas faire ça.

Question ouverte : ces régimes se déduisent-ils des calendriers (un événement
« vacances » en journée entière) ou se déclarent-ils dans un fichier, comme
`echeances.json` ? La déduction est fragile (elle dépend de la façon dont
l'événement est nommé) ; la déclaration est fiable mais manuelle.

---

## G. Une base de test réaliste — et l'abandon de la base actuelle

Décision du 23/09 : **on arrête de se servir de la base réelle comme référence.**
Elle est trop périmée pour qu'on en tire une conclusion — `estTime` manquante sur
81 tâches, classement par projet incohérent (casse, doublons), 53 échéances déjà
dépassées. Toute mesure faite dessus mesure surtout sa dette.

### G1. Ce que la base de test doit contenir

Pas un jeu minimal : un jeu **qui ressemble au réel**, et dont chaque cas
correspond à une situation qui arrive vraiment.

- plusieurs projets portant **la même échéance**, mais des chaînes de
  dépendances différentes — c'est le cas qui met les contextes en concurrence ;
- des projets à **plusieurs niveaux** de dépendance ;
- des **dépendances multiples** : une tâche qui dépend de plusieurs, et une
  tâche dont plusieurs dépendent (convergence et divergence) ;
- le régime **sans aucune dépendance** — déjà couvert depuis le 23/09 ;
- des délais `+externe` intercalés dans les chaînes.

### G1bis. Comment une base reconstruite chaque jour donne des résultats stables

Décidé le 23/09 (après-midi), après une première proposition écartée.

**Écarté : un drapeau `--maintenant`** qui ferait croire au planificateur qu'on
est lundi. Taskwarrior, lui, ne se laisse pas injecter l'heure : il calcule
l'urgence (âge, proximité de `due`, `scheduled < now`) sur la vraie horloge
(`planif/taskwarrior.py:118` la lit telle quelle). Dissocier les deux horloges
créait le problème au lieu de le résoudre.

**Retenu :**

1. **Une seule horloge, la vraie**, pour le planificateur et pour Taskwarrior.
   Toute date de la base est relative à aujourd'hui, donc l'âge d'une tâche et
   la distance à son échéance sont les mêmes quel que soit le jour du lancement.
2. **Dates de création variées** : quelques tâches à plus d'un an (terme d'âge
   saturé), les autres récentes. C'est réaliste et stable, puisque l'âge est
   relatif.
3. **UUID dérivés du nom de la tâche** (`uuid5`). Nécessaires pour écrire les
   `depends` dans le JSON d'import ; ils suppriment en plus une source d'aléa
   possible dans le départage des égalités (non vérifiée).
4. **Échéances en « N-ième vendredi (ou lundi) à venir »**, pas en « dans N
   jours » : elles tombent toujours le même jour de la semaine. La distance
   varie alors de 0 à 6 jours selon le jour du lancement, d'où :
5. **Une règle de marge, vérifiée statiquement** (sans solveur, pour les 7 jours
   de lancement possibles) : aucun verdict ne doit tenir à une semaine de
   capacité près. Chaque scénario est largement faisable, ou franchement
   infaisable.
6. **Les tests vérifient des propriétés tirées de la spécification, jamais des
   dates.** Un ordre entre deux tâches n'est vérifié que si leur écart
   d'urgence dépasse ce que le terme `due` peut faire bouger en une semaine.
7. **Les tests commencent par effacer la base et recréer les tâches.** Hors
   pytest, l'effacement de la base de dev n'a lieu que si son dossier de données
   contient un fichier témoin `.jetable`.

Scénarios retenus (chacun correspond à une situation réelle) :

| # | Situation | Structure |
|---|---|---|
| S1 | deux livrables pour la même revue | 2 projets, même échéance ; chaîne longue avec `+externe` contre 6 tâches courtes indépendantes |
| S2 | projet façon Heliside.US | 3 niveaux (`.plans`, `.achats`, `.essais`), échéance sur la racine |
| S3 | montage prototype | convergence : dépend de plans + pièces (`+externe`) + moteur (`+externe`) |
| S4 | revue de conception validée | divergence : débloque 3 plans de détail + note de calcul |
| S5 | losange entre sous-projets | A → (B `.plans`, C `.achats`) → D |
| S6 | circuit d'achat | devis `+externe +serviceAchat` → commande → fabrication `+externe` → contrôle |
| S7 | travail non daté | pro, perso, sport, sans dépendance |
| S8 | échéance perso | autre contexte, ne doit pas manger la capacité pro |
| S9 | créneau imposé | une tâche `+fige` dans deux jours |

Le projet infaisable (échéance intenable) est une **variante à part**, hors de
la base principale.

**Fait (23/09)** : `tests/base_realiste.py` (générateur, 50 tâches) et son
contrat `tests/test_base_realiste.py` (42 tests, statiques sauf le semis),
vérifié par 12 mutations. Deux défauts trouvés en route : l'effacement visait
les `*.data` de Taskwarrior 2 et n'effaçait rien (masqué par les uuid fixes :
réimporter écrase les mêmes tâches) ; et le refus sans `.jetable` n'était
testé que sur une base vide, où un effacement prématuré est invisible.

**Reste ouvert :**

- **Les tests de comportement avec solveur** (propriétés par scénario :
  convergence, externe hors capacité, chaîne longue d'abord, propagation).
- ~~Le script de semis~~ **fait** (`bcb8437`) : `outils/recharger-base-test.py`
  recharge une base **dédiée**, `C:/Users/irpaui/taskwarrior-test`, distincte
  de `taskwarrior-dev` (entretenue à la main, non touchée). Pour s'en servir :
  `$env:TASKRC='C:\Users\irpaui\taskwarrior-test\taskrc'`.
- **Le planificateur ne sait pas encore tourner sur cette base** : il lit
  `config.json` et `echeances.json` à côté du paquet, et `reunions.json` dans
  le répertoire courant (`planif/__main__.py:300`, `planif/reunions.py:50`),
  sans option pour les désigner. Le script écrit déjà les deux premiers dans
  `taskwarrior-test/` ; il manque les options côté planificateur et côté
  `plan_runner.py`.
- **La base est détendue.** La règle de marge a forcé les échéances du 7e au 12e
  vendredi à venir : aucun scénario ne met le solveur sous tension, alors que la
  base réelle l'est. Une variante « tendue » est à prévoir à côté de la
  variante infaisable.

### G2. Le nettoyage de la vraie base

Séparé, et c'est du travail utilisateur : renommages de projets, `estTime`
manquantes, échéances dépassées, nouveaux projets. Les commandes `task` peuvent
être préparées ici ; **c'est lui qui les lance.**

---

## H. Voir les dépendances

Demandé le 23/09, avec la bonne question : *le Gantt est-il le bon outil, sachant
qu'il faut le planning d'abord ?*

**Non, pas en premier — et c'est une bonne nouvelle.** Trois représentations
répondent à trois questions différentes :

| Vue | Ce qu'elle montre | A-t-elle besoin du plan ? |
|---|---|---|
| **graphe (DAG)** | la structure : qui dépend de qui | **non** |
| **Gantt** | le temps : quand chaque chose tombe | oui |
| **chemin critique** | ce qui commande la date de fin | non, seulement les durées |

Le graphe ne dépend de rien : il se dessine tout de suite, et c'est justement
l'outil pour **vérifier** qu'une base — de test ou réelle — est bien construite,
avant même de planifier. Le Gantt vient après, quand il y a un plan à montrer.

**Fait (23/09, WebTaskManager `2efa2f8`)** : `GET /api/graphe?projet=X` et
`graphe.html` (Mermaid 10 par CDN, un cadre par sous-projet, externes / figées /
hors projet distinguées), projet choisi dans le filtre de `nav.js`. Endpoint
vérifié par 10 mutations ; la page, non. Vérifié à l'œil sur NPD.Orion de la
base de test : 16 nœuds, 13 flèches, 5 cadres, conformes.

**Lisibilité — tranchée le 23/09** : zoom et déplacement (boutons + molette +
glisser), cadres imbriqués par sous-projet, le projet demandé sans cadre propre,
même marge entre le cadre et la nav, le bas et les côtés.

> **H2 et H3 sont faits** (WebTaskManager `69cdd34`, `ee0eb9c`, `7c489f2`),
> vérifiés par mutation et par un essai de bout en bout sur la base de test.
> Leçon à retenir : un contrat Playwright qui simule le serveur peut se
> tromper de forme de réponse (`error` au lieu du `detail` de FastAPI) et
> rester vert pendant que l'interface échoue contre le vrai serveur. D'où
> l'essai réel avant chaque commit d'une fonction qui écrit dans la base.

### H2. Éditer les dépendances depuis le graphe (demandé le 23/09)

Le graphe devient **l'interface de création des dépendances**. Geste voulu : on
sélectionne une ou plusieurs tâches, on clique « → » (les sélectionnées
s'allument), puis on clique la tâche dépendante, qui porte le `depends`.

Mesuré sur Taskwarrior 3.5 (base temporaire) :

    depends:X          ajoute X (ne remplace pas la liste)
    depends:-X         retire X
    depends:X,-Y       ajout et retrait en une commande
    depends:+X         REFUSE ("Invalid dependency value")
    cycle direct ou indirect : refuse par Taskwarrior, code 2,
                       "Circular dependency detected and disallowed."

Décisions : pas de création de dépendance entre deux projets racine depuis le
graphe — il ne montre de toute façon que le projet choisi et ses voisins déjà
liés, donc la limite est naturelle. Retirer un lien : clic sur la flèche (elle
s'allume), puis bouton « Retirer le lien » ou touche Suppr. Annuler un geste
en cours : Échap, ou un second clic sur « → » (décisions utilisateur du 23/09).
Le retrait d'un lien existant vers un
voisin reste possible. `run_task_command` passe par `shell=True` : les uuid
reçus doivent être validés par expression régulière stricte avant d'entrer
dans la commande.

### H3. Éditer une tâche depuis le graphe (demandé le 23/09)

Un bouton « stylo » sur chaque nœud, comme sur les taskcards, ouvre la modale
d'édition existante (`task-editor.js`) ; à l'enregistrement, le graphe se
redessine. À faire **avant H2** : il pose l'infrastructure de clic sur un nœud
(distinguer un clic d'un glisser de `svg-pan-zoom`) dont H2 a besoin.

---

## Priorité proposée

1. **E1 + E2** — voir le plan à l'écran sans toucher la base. Le plus court
   chemin vers un usage réel, et `plan.json` est déjà lu par le calendrier.
2. **G1** — la base de test réaliste. Prérequis pour croire quoi que ce soit de
   ce qui suit, et l'utilisateur a explicitement retiré sa confiance à la base
   actuelle.
3. **H — le graphe de dépendances.** Ne dépend d'aucun plan, et sert
   immédiatement à valider G1.
4. **E3 + E4** — ajuster et valider : la boucle se ferme.
5. **I — les sous-tâches** (ci-dessous), qui a besoin de G1 pour être testée.
6. **F** — les deux calendriers et les régimes de capacité.
7. **G2** — le nettoyage de la vraie base, quand le reste est sûr.

---

## I. Les sous-tâches

Le besoin, dans les termes de l'utilisateur : en avant-projet il alloue du temps
à « faire les plans de détails » sans connaître les pièces. En exécution il veut
la découper en « faire plan APM-XX-00302 », « …00303 », etc. — **mais ses chefs
ne doivent voir que « Faire les plans de détails ».**

Taskwarrior n'a pas de hiérarchie de tâches. `depends` est un ordre, pas une
appartenance. Deux façons de la simuler :

**a. Un sous-projet** `NPD.Heliside.US.plansDetails`, avec un libellé attaché au
projet. Avantages : `task project:…plansDetails` marche nativement,
`task project:NPD.Heliside.US` les inclut, et **la propagation d'échéance (A1)
les couvre déjà**. Il manque seulement un libellé lisible pour le projet — ce
qui se range naturellement à côté de `echeances.json`, dans un `projets.json`
qui porterait libellé *et* échéance.

**b. Un UDA `parent`** pointant la tâche mère. Ça invente une hiérarchie que
Taskwarrior ignore : aucun rapport, aucun filtre, aucune vue existante ne la
comprendrait. Tout serait à réécrire.

**Avis : (a).** Elle ne crée aucune notion nouvelle et réutilise trois
mécanismes déjà en place.

**Une règle d'exploitation à ne pas oublier :** au moment de la découpe, la tâche
mère doit disparaître ou voir son `estTime` tomber à zéro. Sinon les 40 h de
l'avant-projet et les 8 × 5 h du détail **se comptent deux fois**, et toute la
capacité est fausse.

**Et le « replier pour les chefs » est une règle d'affichage**, pas de modèle :
agréger à une profondeur de projet donnée. Ça vaut pour le Gantt comme pour le
rapport — et ça marche tout seul avec des sous-projets, pas avec un UDA.
