"""BOUCHON — echeances de projet.

CE FICHIER NE CONTIENT PAS DE DONNEE REELLE. Il est nomme `stub_` pour etre trouve
au `grep`, et il est declare en tete de RAPPORT-NUIT.md.

Ou j'ai cherche, et ce que je n'ai pas trouve :

- `config.json` a la racine : porte `timeSlots`, `commuteTime`, `plannedDurationDays`,
  `deepWorkLimit`, `freeTimeHours`. **Aucune echeance de projet.**
- `openspec/changes/ordonnanceur-par-contraintes/design.md` §2 : decrit la *forme*
  attendue (`[projets."NPD.helisides"] echeance = "2026-12-15"`) mais precise que
  c'est un exemple de format, pas une donnee.
- `openspec/changes/ordonnanceur-par-contraintes/tasks.md`, section « A trancher avec
  l'utilisateur avant le lot 4 » : « **Echeances de projet.** Aucune n'existe dans les
  donnees reelles. »
- La base Taskwarrior : non consultee, par isolation — et de toute facon Taskwarrior
  ne porte pas d'echeance *de projet*, seulement des `due` par tache.

Valeur bouchonnee : celle du cas de reference du run, entierement specifiee par
l'utilisateur dans le prompt du run (mardi 2026-11-24 a 17:00). Elle est utilisable
pour eprouver le mecanisme ; elle n'engage aucun projet reel.

Ce qu'il faudrait pour la remplacer : un fichier de configuration de projets, decide
avec l'utilisateur (design.md §7 dit « fichier de configuration du depot »).
"""
from datetime import datetime

__all__ = ["ECHEANCES_PROJET"]

#: nom de projet Taskwarrior -> echeance (datetime naif, heure locale)
ECHEANCES_PROJET = {
    "NPD.helisides": datetime(2026, 11, 24, 17, 0),
}
