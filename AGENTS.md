# AGENTS.md — TaskWarriorPlanner

Instructions opérationnelles pour un agent travaillant sur ce dépôt.
**À lire avant toute modification.**

---

## 1. Ce qu'est ce projet

Un **ordonnanceur de projet** pour Taskwarrior, par programmation par contraintes.

Il ne cherche pas à remplir des journées. Il répond à trois questions :

1. Quel est l'ETA d'un projet qui contient des tâches que l'utilisateur ne réalise pas
   lui-même (fabrication chez un fournisseur, étude par un bureau d'études) ?
2. Dois-je agir aujourd'hui, ou la semaine prochaine suffit-elle ?
3. Quelle est la vraie date limite d'une tâche, sachant que le projet doit finir le X ?

**Le cahier des charges fait foi** : `openspec/changes/ordonnanceur-par-contraintes/`.
`proposal.md` porte les décisions, `design.md` le modèle formel, `tasks.md` le découpage.
Un agent doit pouvoir exécuter un lot en ne lisant que ces trois fichiers.

Le dépôt contenait une tentative précédente (`TWschedule_tasks.py`,
`TWsched_task_to_caldav.py`, `config.json`, mars 2025), non fonctionnelle. Elle est conservée
pour référence : `TWsched_task_to_caldav.py` est le point de départ de la lecture du calendrier,
et `config.json` porte les vraies grilles horaires de l'utilisateur. **Ne pas s'en inspirer
pour l'algorithme** — c'est ce qu'on remplace.

---

## 2. Règle absolue : isolation des données

**Ne jamais exécuter de commande Taskwarrior sans `TASKRC` ou `TASKDATA` explicitement
positionné sur une base jetable.**

```powershell
# PC de travail
$env:TASKRC = 'C:/Users/irpaui/taskwarrior-dev/taskrc'
```

La vraie base de l'utilisateur est synchronisée par **Syncthing sur trois machines**. Une
commande d'écriture lancée sans isolation abîme des données réelles, et il n'y a pas de retour
arrière.

Cela vaut aussi pour l'exploration : un `task export` de vérification se lance avec `TASKRC`
posé, comme le reste.

---

## 3. Règle : tout bug corrigé laisse un test derrière lui

**Aucune correction n'est complète sans un test qui échoue avant elle et passe après.**
Écrire le test *d'abord* : un test qui n'a jamais rougi ne prouve rien.

Quatre exigences, apprises en se faisant avoir sur chacune dans le dépôt voisin :

1. **Le test doit être déterministe.** Pour un bug de concurrence ou de date, ne pas espérer
   perdre la course : la faire perdre. Figer l'horloge plutôt que d'utiliser `now()`.
2. **Le test doit prouver qu'il exerce le chemin visé.** Compter les appels et l'asséner.
3. **Compter les tests exécutés, pas seulement les verts.** Un `10 passed` peut masquer quatre
   tests qui n'ont jamais tourné.
4. **Ce qui écrit dans une base réelle ne se parallélise pas.**

### Un bug trouvé sur des données réelles se reproduit dans `pytest`, toujours

Les données réelles servent à **trouver** des défauts, jamais à les **surveiller** : on ne les
a pas sous la main à chaque exécution, elles changent, et elles sont personnelles. Un bug
observé sur la base de l'utilisateur n'est donc pas corrigé tant qu'un test de la suite ne le
reproduit pas sur des données construites, réduites au minimum qui le déclenche.

Les trois défauts les plus graves du 22/09/2026 ont tous été trouvés en **lançant** l'outil,
aucun en relisant le code, et le dernier était strictement indétectable sans données
réelles — une échéance vieille de 134 jours rendait le modèle infaisable, alors que tous les
scénarios de test utilisaient des échéances futures ou à peine dépassées.

La démarche, à chaque fois :

1. réduire le cas réel jusqu'à la plus petite entrée qui reproduit (une dichotomie a désigné
   *une* tâche parmi 278) ;
2. écrire le test sur des données **construites**, paramétré autour du seuil trouvé, pour
   qu'on voie où il bascule ;
3. le voir rougir, puis corriger.

Le paramétrage compte : sur ce bug-là, `1` et `30` jours passaient et `89` cassait, ce qui a
montré le mécanisme — le seuil valait la longueur de l'horizon — avant même de lire le code.

---

## 4. Environnement

- Python, `venv` à la racine. **Ne rien installer en dehors.**
- `ortools` est un **binaire natif**, pas du Python : roues disponibles pour `win_amd64`,
  `manylinux aarch64`, macOS. **Pas de roue Termux** (Android utilise la Bionic, pas la glibc).
  Le solveur tourne donc sur le PC, jamais sur le téléphone.
- Les fins de ligne sont fixées par `.gitattributes` (`*.sh` et `*.py` en LF) : un script en
  CRLF échoue sous Termux avec « bad interpreter ».

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
pytest
```

---

## 5. Pièges Taskwarrior vérifiés

Constatés dans le dépôt voisin, tous reproductibles. Ne pas les redécouvrir.

- **`subprocess.run(..., text=True)` sans `encoding='utf-8'` corrompt les accents sous
  Windows.** Toujours passer l'encodage explicitement.
- **`task.exe` corrompt les accents passés dans ses *arguments* sous Windows** — vérifié avec
  `shell=True`, `shell=False`, PowerShell natif et `chcp 65001`. Seul `task import` depuis un
  fichier UTF-8 y survit. Sous Linux, `argv` gère l'UTF-8 et le problème n'existe pas.
- **`rc.confirmation=off` ne couvre pas la confirmation *de lot*.** Taskwarrior redemande alors
  tâche par tâche, ne lit rien sur une entrée non interactive, et annonce « Deleted 0 tasks »
  avec un **code de retour nul**. `rc.bulk=0` est obligatoire pour toute modification en masse.
- **`estTime` n'accepte pas `1h30`** (rejeté, code retour 2). Formats valides : `90min`,
  `1.5h`, `PT1H30M`.
- **Un filtre par motif (`/texte/`) ne matche pas toujours** : préférer l'UUID pour modifier
  une tâche précise.

---

## 6. Conventions

- Python : PEP 8, pas de linter configuré.
- Le français dans les commentaires et la documentation, comme dans le dépôt voisin.
- `openspec/changes/` documente les changements structurants.
- **Ne jamais publier sur GitHub au nom de l'utilisateur** : ni `push` non demandé, ni *pull
  request*, ni *issue*. Les textes se préparent, l'utilisateur publie.

---

## 7. Lien avec WebTaskManager

`../WebTaskManager` est l'interface web du même utilisateur, sur la même base Taskwarrior.

**Le contrat entre les deux est un fichier JSON de plan**, décrit au §7 de `design.md`.
L'interface web ne connaît ni `ortools`, ni le modèle de contraintes, ni la configuration des
grilles. Ce dépôt ne connaît pas l'interface web.

Ne pas introduire d'import croisé entre les deux projets.
