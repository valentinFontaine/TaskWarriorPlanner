"""Comment une echeance de PROJET descend sur les taches.

**C'est le seul endroit du depot ou cette regle est ecrite.** Elle tient en une
fonction, volontairement, parce que c'est une **question ouverte** et qu'elle
doit pouvoir changer d'une ligne le jour ou l'utilisateur tranche.

## L'etat de la question

`design.md` §2 donne la *forme* d'une echeance de projet :

    [projets."NPD.helisides"]
    echeance = "2026-12-15"

mais il ne dit **nulle part** comment elle devient une contrainte sur des
taches. Le choix fait ici, et repris du run precedent :

> L'echeance d'un projet se pose comme `due` sur les taches **terminales** de ce
> projet — celles qui n'ont aucun successeur *a l'interieur du projet*.

Pourquoi celle-la : c'est la lecture la plus economique. Finir le projet avant
le X, c'est finir son dernier maillon avant le X ; les maillons anterieurs
heritent de la contrainte par les precedences, que le solveur propage deja, et
sans re-tamponner (design.md §4). Poser l'echeance sur *toutes* les taches du
projet donnerait le meme resultat sur une chaine simple, mais serait faux des
qu'une branche courte cotoie une branche longue : la branche courte se
retrouverait contrainte sans raison.

**Ce n'est pas tranche.** C'est la question n° 1 laissee a l'utilisateur par
RAPPORT-NUIT.md, et elle l'est toujours. Variante plausible : toutes les taches
du projet. Pour en changer, il suffit de reecrire `taches_terminales`.
"""
from dataclasses import replace

__all__ = ["taches_terminales", "appliquer_echeances_projet"]


def taches_terminales(taches, projet):
    """Les uuids des taches de `projet` sans successeur dans ce meme projet.

    `tache.depends` porte les **predecesseurs** (convention Taskwarrior) : le
    graphe des successeurs est donc son inverse.
    """
    du_projet = [t for t in taches if t.projet == projet]
    uuids = {t.uuid for t in du_projet}
    avec_successeur = set()
    for tache in du_projet:
        for predecesseur in tache.depends:
            if predecesseur in uuids:
                avec_successeur.add(predecesseur)
    return {t.uuid for t in du_projet if t.uuid not in avec_successeur}


def appliquer_echeances_projet(taches, echeances_projet):
    """Rend une nouvelle liste de taches, avec les echeances de projet posees.

    `echeances_projet` : dict nom_projet -> datetime (naif local, design.md §2).
    A defaut de source reelle, l'appelant passe le bouchon
    `planif.stub_echeances.ECHEANCES_PROJET` — aucune echeance de projet
    n'existe dans les donnees de production.

    Une tache qui porte **deja** un `due` propre le garde : un engagement
    explicite prime sur une echeance heritee du projet.
    """
    if not echeances_projet:
        return list(taches)

    cibles = {}
    for projet, echeance in echeances_projet.items():
        for uuid in taches_terminales(taches, projet):
            cibles[uuid] = echeance

    return [replace(t, due=cibles[t.uuid])
            if t.uuid in cibles and t.due is None else t
            for t in taches]
