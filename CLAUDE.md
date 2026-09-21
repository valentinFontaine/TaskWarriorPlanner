# CLAUDE.md

Les instructions de ce dépôt sont dans **[AGENTS.md](AGENTS.md)**. Lis-le avant toute
modification.

Aucune instruction spécifique à Claude Code ne s'ajoute à ce fichier : tout est dans AGENTS.md,
afin qu'il n'y ait qu'une seule source à maintenir.

Trois points à ne pas découvrir en cours de route :

- **N'exécute jamais de commande Taskwarrior sans `TASKRC` ou `TASKDATA` positionné sur une
  base jetable.** La vraie base de l'utilisateur est synchronisée par Syncthing sur trois
  machines. Voir AGENTS.md §2.
- **Le cahier des charges fait foi** : `openspec/changes/ordonnanceur-par-contraintes/`.
  Si le code et le cahier des charges divergent, c'est le cahier des charges qui a raison —
  ou alors il faut le modifier explicitement et dire pourquoi.
- **Ne publie jamais sur GitHub au nom de l'utilisateur** : pas de `push` non demandé, pas de
  *pull request*, pas d'*issue*.
