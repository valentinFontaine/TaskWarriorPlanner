"""BOUCHON — reunions (source iCal).

CE FICHIER NE CONTIENT PAS DE DONNEE REELLE. Il rend toujours une liste vide.
Nomme `stub_` pour etre trouve au `grep`, declare en tete de RAPPORT-NUIT.md.

Ou j'ai cherche, et ce que je n'ai pas trouve :

- `TWsched_task_to_caldav.py` a la racine : ecrit **vers** CalDAV (il pousse des
  taches planifiees dans un calendrier). Il ne lit aucun creneau occupe. design.md §2
  le dit : « le flux iCal existe deja cote utilisateur (cf. TWsched_task_to_caldav.py,
  qui n'ecrit que dans un sens) ».
- `config.json` : aucune cle de calendrier, aucune URL CalDAV, aucun identifiant.
- `requirements.txt` : `ortools` seul. Aucune bibliotheque iCal (`icalendar`,
  `caldav`, `vobject`) n'est declaree — donc rien n'a jamais lu de calendrier ici.
- `tasks.md`, section « A trancher avec l'utilisateur avant le lot 4 » :
  « **Source des reunions.** Le flux iCal n'est branche nulle part. »

Consequence sur le resultat, a lire avant d'utiliser un plan produit ce soir :
le calendrier disponible **ignore les reunions**. Sur un agenda reel charge, le plan
sera donc trop optimiste. Le cas de reference du run stipule « aucune reunion », donc
le bouchon y est exact et ne fausse rien.

Ce qu'il faudrait pour le remplacer : inverser le sens de `TWsched_task_to_caldav.py`
pour *lire* les creneaux occupes, et une dependance iCal declaree dans
`requirements.txt` (lot dedie, a trancher avec l'utilisateur).
"""

__all__ = ["reunions"]


def reunions(debut, fin, source=None):
    """Rend les `Reunion` chevauchant [debut, fin[.

    Bouchon : toujours vide, quelle que soit la fenetre demandee.
    """
    return ()
