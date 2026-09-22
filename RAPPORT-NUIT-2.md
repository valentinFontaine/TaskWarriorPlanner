# Rapport de nuit 2 — dette, performance, lots 6 à 9

Run autonome du 2026-09-21 au soir (suite de `RAPPORT-NUIT.md`).
Branche `main`, **rien n'a été poussé**.

Tout ce qui est écrit ici a été **exécuté**, sauf mention explicite du contraire.
Ce que je suppose sans l'avoir lancé est marqué « *supposé* ».

État de départ confirmé au lancement : branche `main`, 7 commits d'avance sur
`origin`, arbre propre, `venv` présent, `ortools` 9.15.6755, **87 tests verts en
129,5 s**. Aucun écart avec ce qu'annonçait le prompt.

---

## 1. Données bouchonnées ou interprétées

### 1.1 Les deux bouchons — inchangés, et toujours vrais

Ni `planif/stub_echeances.py` ni `planif/stub_reunions.py` n'ont été remplacés par
des valeurs inventées. Ils restent exactement ce qu'ils étaient :

| Fichier | Ce qui manque | Effet sur le résultat |
|---|---|---|
| `planif/stub_echeances.py` | **échéances de projet** — n'existent nulle part dans les données réelles | La seule valeur est celle du cas de référence (`2026-11-24 17:00`), spécifiée par l'utilisateur. Aucun projet réel n'a d'échéance, donc la passe arrière n'a toujours rien à dire de la production. |
| `planif/stub_reunions.py` | **réunions (flux iCal)** — non branché | Rend toujours une liste vide. Sur un agenda réel chargé, **le plan reste trop optimiste**. |

**Ils ne m'ont pas gêné cette nuit**, et c'est une information en soi : tout ce qui
a été écrit (deux horizons, passe 2, sortie, noyau) se teste sans eux. Le premier
lot qui butera dessus est celui qui voudra un plan *juste* sur des données réelles,
pas un plan *correct* sur un cas construit.

**Aucune dépendance n'a été ajoutée** à `requirements.txt` — en particulier aucune
bibliothèque iCal, conformément à la consigne.

### 1.2 Les interprétations de ce run

1. **L'échéance de projet descend sur les tâches terminales — et c'est désormais
   écrit à UN SEUL endroit.** Le prompt demandait de garder le choix du run
   précédent mais de l'isoler. C'est fait : `planif/echeances.py`, fonctions
   `taches_terminales` et `appliquer_echeances_projet`. Les trois fichiers de test
   qui dupliquaient la règle (`test_lot5_tiers.py`, `test_perf_horizon.py`,
   `test_lot8_noyau.py`) l'appellent maintenant. **Un test vérifie l'isolation
   elle-même** : il parcourt `planif/*.py` et échoue si un autre module se met à
   réimplémenter la règle. Pour changer de convention, il y a une fonction à
   réécrire.
   L'argument retenu, écrit dans le module : poser l'échéance sur *toutes* les
   tâches du projet donnerait le même résultat sur une chaîne simple, mais serait
   faux dès qu'une branche courte côtoie une branche longue — la courte serait
   contrainte sans raison. Un test construit ce cas.
   **La question reste ouverte pour vous.**

2. **Convention de dates : tout est naïf local à l'intérieur, converti aux
   frontières.** C'est le défaut que le prompt imposait, appliqué. Écrit une seule
   fois dans `design.md` §2. **Conséquence assumée** : `Tache.due` n'est plus de
   l'UTC *aware*. Une assertion du lot 0 en dépendait ; elle est corrigée, avec un
   attendu **calculé depuis le fuseau de la machine**, jamais écrit en dur.

3. **Une tâche est modélisée finement si elle porte une limite tombant dans
   l'horizon détaillé ; sinon elle est agrégée.** `design.md` §1 dit qu'au-delà de
   `H_d` la capacité est agrégée par jour, mais ne dit pas *quelles tâches* passent
   dans quel régime. J'ai transcrit la parade annoncée par `proposal.md` (« ne
   modéliser finement que ce qui porte une échéance »). Une tâche sans limite n'a
   aucune pression de date : elle n'a pas besoin de l'heure exacte en passe 1.

4. **Ce que l'agrégation lâche, explicitement.** Au-delà de la frontière, **deux
   blocs d'une même journée peuvent se chevaucher dans la sortie**. Ce ne sont plus
   des placements horaires, ce sont des affectations à une journée. Le volume
   quotidien, lui, reste garanti. C'est pour ça que le JSON porte une `precision`
   (`"heure"` / `"jour"`) et pas seulement le drapeau `agrege` : le drapeau dit
   *d'où vient* le bloc, la précision dit *ce qu'on peut en faire*.

5. **Les deux régimes vivent dans des plages de temps disjointes.** Un bloc agrégé
   ne peut jamais commencer avant la frontière. Sans ça, un bloc agrégé (absent de
   `AddNoOverlap`) pourrait se superposer à un bloc détaillé. C'est conservateur :
   la journée à cheval sur la frontière perd sa partie d'avant-frontière plutôt que
   de risquer un double placement.

6. **Une tâche opportuniste est placée entièrement ou pas du tout.** `design.md`
   écrit `Σ urgence_i × planifiée_i` sans dire si « planifiée » est partiel. Une
   seule variable de présence par tâche : un demi-travail planifié ne rend service
   à personne.

7. **Jours fériés toujours ignorés.** Aucun calendrier n'existe dans le dépôt. Un
   11 novembre tombant dans une chaîne est traité comme un jour travaillé. Je le
   redis parce que la consigne demandait de le redire.

8. **`planif/diagnostic.py` duplique une quarantaine de lignes de
   `planif/solveur.py`** (pose des blocs, fenêtres, capacité, non-chevauchement).
   Factoriser aurait signifié toucher `resoudre`, donc les lots 4, 5 et 6 et leurs
   tests, pour économiser 40 lignes. Je ne l'ai pas fait. **C'est une dette, pas un
   choix définitif**, et elle est écrite en tête du module.

---

## 2. Les mesures

### 2.1 Performance — **CIBLE NON ATTEINTE, et rien n'a été dégradé pour la faire passer**

| | Cible | **Mesuré** |
|---|---|---|
| 100 tâches, horizon détaillé 2 semaines | **< 30 s** | **60,8 s** |
| statut obtenu | `OPTIMAL` | **`FEASIBLE`** |
| cas de référence conservé | `OPTIMAL` | **`OPTIMAL`** ✓ |

Dépassement : **+30,8 s, soit le double de la cible.**

**Le diagnostic chiffré, qui est le vrai résultat de cette étape** — modèle de
**3 420 variables et 6 443 contraintes** :

```
--- num_search_workers = 1 ---
  essai 1 : total  60.8 s | passe 1 :   0.7 s OPTIMAL  passe 2 :  60.0 s FEASIBLE
  essai 2 : total  60.8 s | passe 1 :   0.7 s OPTIMAL  passe 2 :  60.0 s FEASIBLE
  -> plans identiques entre les deux essais : OUI

--- num_search_workers = 8 ---
  essai 1 : total  60.9 s | passe 1 :   0.7 s OPTIMAL  passe 2 :  60.1 s FEASIBLE
  essai 2 : total  60.9 s | passe 1 :   0.7 s OPTIMAL  passe 2 :  60.1 s FEASIBLE
  -> plans identiques entre les deux essais : NON
```

Ce que ça dit, et c'est plus utile que le chiffre brut :

- **Ce n'est pas la construction du modèle qui coûte.** La passe 1 (minimiser le
  retard) prend **0,7 s** et **prouve l'optimum**.
- **C'est la PREUVE d'optimalité de la passe 2 qui brûle les 60 s.** Maximiser la
  somme des débuts sur 100 tâches tassées contre la capacité produit une quantité
  énorme de solutions quasi équivalentes. Le solveur trouve vite un bon plan et
  passe le reste du temps à ne pas réussir à démontrer qu'il est optimal.
- **Un plan `FEASIBLE` est un plan correct** : les contraintes sont dures. Ce qui
  n'est pas prouvé, c'est qu'il soit *le plus tard possible*, pas qu'il soit valide.

**Les trois pistes essayées, toutes mesurées, aucune n'a bougé le chiffre :**

| Piste | Résultat | Retenue ? |
|---|---|---|
| Réduire les domaines à l'union exacte des fenêtres | 60,8 s → **60,8 s** | **Gardée** — renforcement pur, ensemble des solutions identique, et le modèle documente où les blocs peuvent aller. N'a rien rapporté et je le dis. |
| Objectif au **jour** (et non au créneau) pour les blocs agrégés | **60,8 s** | **Annulée.** Défendable sémantiquement — optimiser une heure dans un régime où l'heure n'a pas de sens, c'est optimiser du bruit — mais c'était une hypothèse de performance, elle est réfutée, et la garder laissait une différence de comportement injustifiée. Question posée en §5.2. |
| 8 workers au lieu de 1 | **60,1 s**, et **le plan cesse d'être reproductible** | **Refusée.** Résultat négatif utile : le bridage à 1 worker, qu'on croyait coûteux, **ne coûte rien**. Il n'y a pas d'arbitrage déterminisme/vitesse à faire. |

**Ce que je n'ai pas fait, et c'est délibéré** : abaisser `SECONDES_MAX` sous 30 s
ferait passer le test instantanément, sans changer une seule contrainte. C'est
exactement la triche que la consigne interdit. Le plafond reste à 60 s, et l'échec
est consigné en **`xfail(strict=True)`** — donc la suite est verte, le chiffre réel
est imprimé à chaque exécution, et **le test redeviendra rouge le jour où la cible
sera réellement atteinte**.

### 2.2 Le cas de référence n'a pas bougé

`OPTIMAL`, retard nul, et `fin(D) == 2026-11-20 17:00`. Vérifié par le test dédié
du lot perf **et** par les tests du lot 5, inchangés.

Vérifié en plus : avec un horizon détaillé de 2 semaines, D passe en régime agrégé
et **le JOUR reste juste** (`fin(D).date() == 2026-11-20`), la fabrication dure
toujours **28 jours calendaires exactement**, et aucun jour ne dépasse 4 h utiles.
Les deux horizons s'accordent sur la date même quand ils divergent sur l'heure —
c'est précisément la promesse de `design.md` §1.

### 2.3 Les contrôles de mécanisme, lot par lot

| Contrôle | Résultat |
|---|---|
| **Dette 1.2** — chaque contexte garde sa capacité propre | **passé**, et vérifié par mutation |
| **Dette 1.3** — `+fige` tient à sa date sous la pression du « au plus tard » | **passé** |
| **Lot 6** — le plan de la passe 1 ne bouge pas d'un seul créneau | **passé**, comparé bloc à bloc |
| **Lot 6** — sans tâche non datée, le plan est identique | **passé** |
| **Lot 6** — les opportunistes sont marquées, les autres non | **passé**, les deux moitiés |
| **Lot 7** — deux exécutions n'écrivent rien la seconde fois | **passé**, prouvé sur le `mtime` du fichier et sur le champ `modified` de Taskwarrior |
| **Lot 7** — `--dry-run` n'écrit rien | **passé**, prouvé en comparant l'export Taskwarrior complet avant/après, pas en lisant le code |
| **Lot 8** — un conflit rend exactement les éléments en cause | **passé** : la tâche saine voisine n'est pas nommée |
| **Lot 8** — un modèle faisable ne rend aucun noyau | **passé** |

---

## 3. Les lots terminés

| Étape | Tests | Vu rouge ? | Commit |
|---|---|---|---|
| **1.1** convention de dates | 4 | oui — `ImportError: cannot import name 'vers_local_naif'` | `7c14bfd` |
| **1.2 + 1.3** contextes et `+fige` | 7 | **non** — voir ci-dessous | `7c14bfd` |
| **2** deux horizons | 7 (6 + 1 `xfail`) | oui — `TypeError: unexpected keyword argument 'horizon_detaille_fin'` | `b88e0f8` |
| **3** lot 6, passe opportuniste | 9 | oui — `cannot import name 'completer'` | `e8f83f2` |
| **4** lot 7, sortie | 11 | oui — `ImportError` à la collecte, `planif/sortie.py` absent | `0b16a99` |
| **5** lot 8, noyau | 8 | oui — 7 à la collecte, **et 1 vraiment rouge** | `fb1e625` |
| — échéances de projet isolées | 7 | oui — module absent | *(à committer)* |

### Les deux endroits où le rouge mérite une explication

**1.2 et 1.3 n'ont pas pu être vus rouges**, et c'est normal : ils testent du code
**déjà écrit**. Un `ImportError` n'aurait rien prouvé. La compensation exigée a été
faite — **un test de mutation** : en forçant la capacité d'un seul contexte, **les
deux tests qui mesurent le volume par jour tombent**, le troisième (ordre temporel)
reste vert parce qu'il ne mesure pas ça. `planif/solveur.py` a été restauré et
`git diff` confirme qu'il est identique au commit.

**Une trouvaille qui vaut plus que le test lui-même** : il a fallu rendre les deux
contextes de test **asymétriques** (3 h et 2 h). Avec deux capacités **égales**, la
mutation est **indétectable** — forcer « la capacité du premier contexte » rend la
même valeur, et les tests restent verts sur un code faux. Un test à deux contextes
symétriques aurait donné une fausse assurance.

**Le huitième test du lot 8 a réellement échoué**, et c'est comme ça que le piège
CP-SAT du §4.1 a été trouvé.

### Compte des tests

Suite complète finale, sortie brute :

```
139 passed, 1 xfailed in 385.27s (0:06:25)
```

**140 tests**, et le compte se réconcilie exactement, lot par lot :

    87 (état de départ)
  + 11 (dette 1.1, 1.2, 1.3)
  +  7 (deux horizons, dont 1 xfail)
  +  9 (lot 6)
  + 11 (lot 7)
  +  8 (lot 8)
  +  7 (échéances de projet isolées)
  ----
   140

Aucun test n'a été collecté sans tourner. Le seul `xfail` est la cible de
performance non atteinte du §2.1, et il est `strict` : il redeviendra rouge le
jour où la cible sera réellement atteinte.

---

## 4. Les frictions

### 4.1 Un piège CP-SAT, trouvé en se cognant dedans

**`SufficientAssumptionsForInfeasibility()` rend une liste VIDE quand le presolve
tranche avant les hypothèses.**

Le cas : une tâche `+insecable` de 4 h alors que la plus grande plage contiguë fait
3 h. Posée en hypothèse étiquetée comme le prescrit `design.md` §6, elle *devrait*
apparaître dans le noyau. Elle n'apparaît pas : le presolve de CP-SAT fixe le
littéral avant que le mécanisme d'hypothèses n'entre en jeu, l'infaisabilité est
prouvée en amont, et le noyau ressort vide. Le diagnostic annonçait alors « la
capacité elle-même ne suffit pas », ce qui est **faux et trompeur**.

Le correctif est aussi la bonne architecture, et `design.md` §6 le disait déjà :
les **pré-vérifications passent avant tout appel au solveur**. `diagnostiquer`
commence donc par appeler `verifier_insecables` (lot 3) et nomme le cas lui-même.
Ce n'est pas une économie, c'est le **seul moyen** de le nommer.

### 4.2 Deux sous-agents perdus en vol

Les deux sous-agents des lots 6 et 7 ont été **interrompus par la limite de session**
en pleine tâche. Les dégâts et ce qui a été récupéré :

- **Lot 6** : le fichier de tests était écrit et **les 9 tests passaient déjà**
  (182 s). L'agent est mort pendant le nettoyage cosmétique. Restaient des artefacts
  d'encodage `{deg}` dans quatre docstrings (une tentative de `n°`), corrigés à la
  main. **Aucune perte.**
- **Lot 7** : les 11 tests étaient écrits et vus rouges, mais `planif/sortie.py`
  **n'a jamais été écrit**. Je l'ai écrit moi-même. **Une heure de délégation
  perdue**, récupérée en écrivant le module directement.

Le lot 8 a donc été fait sans délégation, pour ne pas rejouer le même risque.

### 4.3 Ce qui ne marche pas comme on pourrait le croire

- **Le bridage à un seul worker ne coûte rien.** C'était présenté comme le grand
  arbitrage vitesse/déterminisme par le rapport précédent. Mesuré : 8 workers font
  **60,1 s contre 60,8 s** — dans le bruit — **et** rendent le plan non
  reproductible. Il n'y a pas d'arbitrage : le mono-worker est gratuit.
- **Réduire les domaines n'a rien apporté.** Donner à chaque bloc l'union exacte
  de ses positions possibles au lieu de tout l'horizon est un renforcement propre…
  qui n'a pas changé une seconde. La difficulté n'était pas là.
- **Taskwarrior accepte les deux formats de date pour `scheduled`.** Vérifié sur
  base jetable, pas supposé : `scheduled:2026-11-20T14:00:00` et
  `scheduled:20261120T130000Z` sont tous deux acceptés et ressortent identiques à
  `20261120T130000Z`. On retient l'UTC explicite, qui ne dépend pas de la façon dont
  Taskwarrior interprète une date sans fuseau.
- **La suite est passée de 130 s à plus de 380 s.** Presque tout est du temps
  solveur. C'est vivable mais ça ne le restera pas : chaque lot qui appelle
  `resoudre` ajoute des dizaines de secondes. Les fixtures sont en `scope="module"`
  partout, comme le prompt le demandait.

### 4.4 Sur l'isolation des données

**Aucune commande `task` n'a été lancée sans isolation cette nuit**, `task --version`
compris — c'est le lapsus du run précédent, il n'a pas été répété. Toutes les
commandes Taskwarrior de ce run ont tourné soit sous la fixture `base_jetable`
(qui vérifie `data.location` et lève si l'isolation ne pointe pas où elle croit),
soit sous un `TASKRC` pointant une base jetable du répertoire temporaire de session,
vérifiée avant usage.

La base réelle de l'utilisateur n'a jamais été ouverte, ni en lecture, ni en écriture.

---

## 5. Ce que le run a tranché, et ce qu'il soulève

### 5.1 Tranché — vérifié en l'exécutant

- **La convention de dates est unifiée** et écrite une seule fois. Le risque de
  décalages d'heures silencieux sur données réelles est levé.
- **La capacité par contexte est maintenant couverte**, et le test mord : vérifié
  par mutation.
- **`+fige` fonctionne.** Il était implémenté sans aucun test ; quatre tests
  l'éprouvent, aucun `xfail` n'a été nécessaire.
- **Les deux horizons fonctionnent et sont honnêtes** : ils gardent le bon jour,
  le délai fournisseur exact, et ne créent jamais de capacité.
- **La passe 2 fige réellement la passe 1** — comparé bloc à bloc, pas « à peu près ».
- **La sortie est idempotente**, prouvé par le `mtime` du fichier et par le champ
  `modified` de Taskwarrior, et `--dry-run` n'écrit rien, prouvé par l'export.
- **Le noyau d'insatisfiabilité nomme juste**, et ne nomme pas la tâche saine
  voisine.
- **Le mono-worker est gratuit** (§4.3). Un faux arbitrage en moins.

### 5.2 Soulevé — pour vous, par ordre d'importance

1. **La cible de performance n'est pas atteinte, et le mur est identifié :** c'est
   la *preuve* d'optimalité de la passe 2, pas le modèle. Trois directions
   possibles, et **c'est un arbitrage produit, pas technique** :
   (a) accepter `FEASIBLE` et afficher un plan non prouvé optimal — c'est déjà un
   plan correct ; (b) réduire l'horizon détaillé sous 2 semaines ; (c) accepter une
   optimalité approchée en bornant l'écart. Je n'ai pas tranché parce que ça change
   ce que l'outil *promet*, pas seulement ce qu'il calcule.
2. **Comment une échéance de projet descend-elle sur les tâches ?** Toujours ouverte,
   mais elle ne coûte plus rien à changer : une fonction dans `planif/echeances.py`,
   et un test qui garantit qu'elle ne fuit pas ailleurs.
3. **L'objectif du régime agrégé doit-il porter sur le jour ou sur le créneau ?**
   J'ai essayé le jour (plus cohérent : optimiser une heure là où l'heure n'est pas
   garantie, c'est optimiser du bruit), mesuré aucun gain, et **annulé** pour ne pas
   laisser une différence de comportement injustifiée. À reprendre si la question
   revient par la sémantique plutôt que par la performance.
4. **Le flux iCal reste à brancher**, et reste bloquant pour la production. Aucune
   dépendance ajoutée : c'est votre décision.
5. **`planif/diagnostic.py` duplique ~40 lignes du solveur** (§1.2 point 8). À
   factoriser quand les lots 4 à 6 seront stabilisés.
6. **`+asap` n'est toujours pas implémenté**, par consigne. Le marqueur est lu et
   exposé, le solveur n'en fait rien. Qu'il ne soit pas cru fait.
7. **Le repli silencieux de `planif/tampon.py` sur le contexte `pro`** quand une
   tâche n'a pas de contexte attribuable est toujours là, toujours non exercé par
   les tests. Signalé au run précédent, toujours vrai.

### 5.3 État du dépôt au matin

Branche `main`, **rien n'a été poussé**. `../WebTaskManager` n'a pas été touché
(lot 9 non abordé — voir ci-dessous). `README.md` n'a pas été réécrit. Aucun défaut
de taskcheck n'a été corrigé (lot Z, différé). Aucune dépendance ajoutée.

Commits de cette nuit :

```
7c14bfd Dette : convention de dates, capacite par contexte, taches figees
b88e0f8 Horizon detaille et agregation au-dela
e8f83f2 Lot 6 : passe 2, le regime opportuniste
0b16a99 Lot 7 : sortie JSON et ecriture de scheduled
fb1e625 Lot 8 : noyau d'insatisfiabilite
```

### 5.4 Le lot 9 — fait, dans l'autre dépôt

La consigne le conditionnait à ce que les étapes 1 à 5 soient vertes et commitées.
Ça l'est devenu en fin de run, et son prérequis réel — le lot 7, qui produit le
fichier de plan — venait d'atterrir. Il a donc été fait.

`../WebTaskManager`, trois fichiers touchés (`calendar-planner.js`,
`calendar-planner.css`, et le bloc `Filtres partages` de `tests/task-manager.spec.js`),
**commit local `07fa503`, rien de poussé**. `main_fastapi.py` n'a pas été touché.

**Ce que j'ai vérifié moi-même, et ce que je n'ai pas pu vérifier.** Le sous-agent
annonce `26 passed`. Je ne reproduis pas ce chiffre, et la raison est intéressante :
j'ai lancé la suite sur une base jetable **vide**, alors que deux blocs
(`Task Manager`, `Parcours sur la base de dev`) ont besoin d'une base **peuplée**.
J'obtiens donc 2 échecs. Plutôt que de supposer qu'ils sont sans rapport, je l'ai
**mesuré** : en remisant les trois fichiers du lot 9 et en relançant ces deux tests
seuls, **ils échouent exactement pareil**. Ce sont des échecs préexistants dus à ma
base vide, pas une régression du lot 9.

Ce que j'affirme donc, parce que je l'ai exécuté : **le bloc `Filtres partages`
passe 16/16 sur base vide** (12,3 s), les 4 nouveaux tests compris. C'est cohérent
avec le fait qu'il soit entièrement bouchonné, ce qui est précisément pourquoi le
cahier des charges le désigne.

Les trois contrôles exigés passent :

1. **les deux régimes sont distinguables par un sélecteur**, pas seulement à l'œil :
   `.bloc--contraint` / `.bloc--opportuniste`. Et la distinction n'est pas une nuance
   de gris — bordure pleine contre pointillée, trame diagonale, italique, icône
   différente : quatre signaux **indépendants de la couleur**, dont un est assené par
   une assertion sur `getComputedStyle().borderStyle` ;
2. **un plan absent ne produit ni bandeau ni calendrier vide** ;
3. **un plan malformé ne casse pas davantage qu'un plan absent** — et le cas
   « `version` inattendue » est traité comme malformé, ce à quoi sert ce champ.

Décisions prises là-bas, qui méritent votre œil :

- **les blocs `precision: "jour"` sont rendus en évènements *jour entier***, jamais
  en créneau horaire. C'était le piège principal : deux blocs agrégés d'une même
  journée peuvent se chevaucher dans le JSON, et les afficher à l'heure près
  mentirait sur la précision réelle ;
- **les blocs `externe` sont un marqueur en retrait, pas un créneau de travail** :
  ils ne consomment pas la capacité de l'utilisateur, donc les montrer comme un
  rendez-vous donnerait l'illusion d'un agenda chargé à tort ;
- **« plan périmé » = tous les blocs dans le passé.** Le contrat ne porte aucune date
  de génération ; c'est le seul critère honnête disponible sans inventer un champ.
  **Si vous voulez mieux, il faut ajouter le champ au contrat** — c'est une question
  pour vous.

**Une friction qui vaut d'être lue** : `calendar-planner.html` ne contient **aucun**
`#error-message`, contrairement à `index.html` — cette page-là fait un simple
`alert()`. Le contrôle 2 du cahier des charges (« ni `#error-message` visible »)
serait donc passé **trivialement**, sur un élément inexistant, y compris avec une
page entièrement cassée. C'est exactement le faux positif que le cahier des charges
redoutait en écrivant « une page entièrement cassée peut laisser la console vide ».
Les tests ont été renforcés en conséquence : écoute des `dialog` pour prouver
qu'aucune `alert()` de secours ne sort, **et** assertion que `/plan.json` a bien été
appelé, pour prouver que le chemin de code est exercé et que le test ne passe pas
par vacuité.

**Le dépôt web a un garde-fou que celui-ci n'a pas**, et il mérite d'être copié :
`playwright.config.js` **refuse de lancer les tests si `TASKRC` n'est pas défini**.
Je m'y suis cogné en lançant `npm test` sans isolation — le refus est net et le
message dit quoi faire. C'est la bonne façon de rendre la règle d'isolation
inviolable plutôt que seulement écrite.
