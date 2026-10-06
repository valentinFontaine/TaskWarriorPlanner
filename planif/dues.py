"""Les `due` que la passe 1 CALCULE, par opposition a celles qu'elle LIT.

Une echeance de projet (`planif/echeances.py`) est une **entree** : elle se pose
sur les taches terminales et devient une contrainte du modele. Ce que produit ce
module est une **sortie** : une fois le plan resolu « au plus tard », chaque
tache placee a une date apres laquelle il est trop tard pour elle, et c'est
cette date que l'utilisateur veut voir dans Taskwarrior.

    « Si le montage est du pour le 31/12/2026, et que la piece met 4 semaines a
    se fabriquer, la due date de "passer la commande" doit etre remplie au
    3/12/2026. »

La regle est celle-la, et rien de plus : **la `due` d'une tache est la fin de
son dernier bloc dans le plan.** Le solveur a deja fait tout le travail --
precedences, delais `+external`, capacite des contextes, conflits avec le reste
du portefeuille. Recalculer quoi que ce soit ici reviendrait a dupliquer le
modele, avec la certitude de diverger.

Ce module ne decide pas ce qu'on ECRIT dans Taskwarrior : il rend un dict.

La `due` produite ici ne porte AUCUN tampon, et c'est une decision, pas un
oubli : elle dit quand il est reellement trop tard, pas quand on aimerait avoir
fini. Le coussin, si on en veut un, se pose sur le placement de la passe 2. Un
coussin melange a une limite donne une limite fausse, et plus personne ne peut
dire de combien.

Comment une `due` calculee se distingue d'une `due` posee a la main -- sans quoi
le plan se fige sur sa propre sortie de la veille -- est tranche : voir
`est_calculee` plus bas.
"""
from dataclasses import replace

__all__ = ["dues_calculees", "est_calculee", "marquer_calculee",
           "oublier_dues_calculees", "UDA"]


def dues_calculees(plan, taches):
    """Rend {uuid: datetime} : pour chaque tache placee, sa date « au plus tard ».

    `taches` n'est pas lu pour l'instant ; il fait partie de la signature parce
    que la regle d'ecriture (quelles taches on date reellement) se decidera au
    vu des taches, pas du seul plan.
    """
    dues = {}
    for uuid in {b.uuid for b in plan.blocs}:
        dues[uuid] = max(fin for _, fin in plan.instants(uuid))
    return dues


#: Nom de l'UDA Taskwarrior qui porte la valeur. Type `date`, pas `string` :
#: c'est une date, et Taskwarrior doit pouvoir la comparer.
UDA = "duePlanif"


def est_calculee(tache):
    """Vrai si le `due` que porte `tache` est celui QUE NOUS AVONS ECRIT.

    Pourquoi une valeur et pas un drapeau : un drapeau (`duePlanif:1`, ou son
    inverse `dueOverriden:1`) ne survit pas a un `task X modify due:...` fait
    en ligne de commande, hors de l'outil. La date change, le drapeau reste, et
    on ecrase l'engagement de l'utilisateur au run suivant. En stockant la
    valeur, la divergence se voit toute seule : `due` a bouge, `due_planif` non.

    Angle mort assume : si l'utilisateur pose a la main exactement la date que
    le calcul aurait donnee, on la croit notre. La consequence est nulle -- on
    recalculerait la meme -- sauf s'il voulait l'epingler, ce qui demande un
    epinglage explicite et non une coincidence de date.
    """
    return tache.due is not None and tache.due == tache.due_planif


def marquer_calculee(tache, due):
    """Rend une copie de `tache` portant `due`, et la trace qu'on l'a ecrite."""
    return replace(tache, due=due, due_planif=due)


def oublier_dues_calculees(taches):
    """Rend les taches debarrassees des `due` QUE NOUS AVONS ECRITES.

    A appeler avant toute replanification, et c'est le geste qui empeche le plan
    de se figer sur sa sortie de la veille. Une `due` que nous avons posee n'est
    pas un engagement : c'est un resultat, et un resultat se recalcule.

    Sans ce geste, la regle « une tache qui porte deja un `due` propre le garde »
    (voir `planif.echeances`) preserverait nos propres dates, et reculer
    l'echeance d'un projet dans `echeances.json` ne relacherait rien du tout --
    sans qu'aucune erreur ne soit signalee nulle part.

    Ce qui vient de l'utilisateur n'est jamais touche : une date posee a la main
    n'a pas de `due_planif` correspondant, donc `est_calculee` la refuse.
    """
    return [replace(t, due=None, due_planif=None) if est_calculee(t) else t
            for t in taches]
