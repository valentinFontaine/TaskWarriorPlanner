"""Selection des candidates de la passe 2, a hauteur de la capacite reelle.

## Pourquoi ce module existe

A la premiere execution sur les donnees reelles, la passe 2 soumettait **184
candidates** au solveur pour une capacite de deux semaines — une quarantaine
d'heures utiles. Resultat mesure : aucune solution trouvee en 60 s, statut
`UNKNOWN`. Pas `INFEASIBLE` : « ne rien placer » est toujours une solution
valide. Le modele etait simplement trop gros pour etre seulement demarre.

La mesure a corrige deux fois de suite l'explication qu'on en donnait, et les
deux etapes valent d'etre gardees.

**Premiere hypothese, refutee** : reduire l'horizon TOTAL des deux passes.

    horizon total 90 j : passe 2 =  60,99 s ->  0 bloc opportuniste
    horizon total 30 j : passe 2 = 120,59 s ->  9 blocs opportunistes

Deux fois plus lent pour 9 taches sur 184. Le probleme semblait donc etre le
**nombre de candidates**.

**Deuxieme hypothese, la bonne** : c'est l'horizon de la seule PASSE 2.

    horizon passe 2 | candidates | placees | temps
             90 j   |    184     |    0    | 61 s
             14 j   |    147     |   84    | 65 s
             21 j   |    147     |  135    | 68 s

A 147 candidates dans les deux derniers cas, on en place 84 puis 135 : ce n'est
pas la taille de la file qui decide, c'est **l'horizon sur lequel le solveur
doit placer**. Chaque bloc porte un litteral par fenetre possible ; passer de 90
a 21 jours divise cette combinatoire par quatre.

Et c'est juste sur le fond : **le remplissage opportuniste n'a rien a faire a
planifier trois mois a l'avance.** Une tache non datee placee au jour 80 ne veut
rien dire — tout aura change. La selection par capacite reste utile, mais elle
travaille desormais sur l'horizon de la passe 2, pas sur l'horizon total.

## L'algorithme

    capacite disponible = grille - marge - reunions - ce que la passe 1 a pris
    puis, CONTEXTE PAR CONTEXTE, file d'attente par urgence decroissante,
    cumul des durees jusqu'a saturation.

**Ce n'est pas une degradation du modele** : les taches ecartees sont celles que
le solveur n'aurait pas pu placer. Ce qui change, c'est ce que l'outil *promet* —
il ne dit plus « j'ai considere toutes tes taches » mais « j'ai considere celles
qui pouvaient tenir », et il dit combien il en a ecarte.

## Les deux choix qui gouvernent

**Par contexte, jamais globalement.** Une tache `perso` urgente ne doit pas etre
ecartee parce que le budget `pro` deborde : ce sont deux budgets separes, c'est
tout le modele de ce projet.

**Un facteur d'offre mesure, pas suppose** (`FACTEUR_OFFRE`). J'ai d'abord
argumente qu'il fallait offrir plus que la capacite, pour laisser au solveur de
quoi arbitrer plutot que d'executer betement le tri par urgence. La mesure a dit
le contraire : a nombre de candidates egal, c'est l'horizon qui decide. Le
facteur vaut donc 1, et le detail des chiffres est en face de la constante.
"""
from datetime import timedelta

from planif.calendrier import disponibilite

__all__ = ["FACTEUR_OFFRE", "capacite_restante", "selectionner_candidates"]

#: Combien de fois la capacite restante on soumet au solveur.
#:
#: Mesure sur les donnees reelles (278 taches), qui a tranche contre mon
#: intuition de depart -- je pensais qu'il fallait de la marge pour laisser le
#: solveur arbitrer :
#:
#:     horizon passe 2 | facteur | candidates | placees | temps
#:              90 j   |    2    |    184     |    0    | 61 s
#:              14 j   |    2    |    147     |   84    | 65 s
#:              14 j   |    1    |     90     |   78    | 63 s
#:              21 j   |    1    |    147     |  135    | 68 s
#:
#: A 14 j facteur 2 et a 21 j facteur 1, on soumet le MEME nombre de candidates
#: (147) et on en place 84 contre 135 : la variable decisive est l'horizon de
#: placement, pas la taille de la file. Le facteur reste donc a 1, et c'est
#: l'horizon de la passe 2 qui porte le reglage.
FACTEUR_OFFRE = 1


def capacite_restante(contextes, t0, maintenant, horizon_fin, granularite,
                      deja_pris=None):
    """Capacite encore libre par contexte, sur [maintenant, horizon_fin].

    `deja_pris` : dict nom_contexte -> timedelta consomme par la passe 1.

    La capacite d'une journee vient de `planif.calendrier.disponibilite`, donc
    marge quotidienne et reunions deja deduites — on ne reimplemente pas la
    regle ici, on l'appelle. Le resultat est borne a zero : une passe 1 qui
    deborde rend une capacite nulle, jamais negative.
    """
    deja_pris = deja_pris or {}
    restantes = {}

    for nom, contexte in contextes.items():
        total = timedelta(0)
        jour = maintenant.date()
        while jour < horizon_fin.date():
            dispo = disponibilite(contexte, jour, t0, granularite)
            total += dispo.capacite * granularite
            jour += timedelta(days=1)

        libre = total - deja_pris.get(nom, timedelta(0))
        restantes[nom] = max(libre, timedelta(0))

    return restantes


def selectionner_candidates(taches, capacites, facteur=FACTEUR_OFFRE):
    """Rend `(retenues, ecartees)` — deux listes de `Tache`.

    Une tache sans `estimated` ou sans contexte connu n'est **ni** retenue
    **ni** ecartee : elle est deja signalee par les pre-verifications, et la
    faire figurer parmi les ecartees laisserait croire qu'elle a manque de
    place, ce qui serait faux.

    Le tri est `(-urgence, uuid)` : l'uuid departage, sans quoi deux taches de
    meme urgence pourraient changer d'ordre d'une execution a l'autre et le
    plan cesserait d'etre reproductible.
    """
    par_contexte = {}
    for tache in taches:
        if tache.estimated is None or tache.contexte not in capacites:
            continue
        par_contexte.setdefault(tache.contexte, []).append(tache)

    retenues, ecartees = [], []
    for nom, candidates in par_contexte.items():
        budget = capacites[nom] * facteur
        cumul = timedelta(0)
        sature = False
        for tache in sorted(candidates, key=lambda t: (-t.urgency, t.uuid)):
            if sature or cumul + tache.estimated > budget:
                # On ne « saute » pas une grosse tache pour en caser une plus
                # petite derriere : la file est une file. Sinon l'ordre annonce
                # (urgence decroissante) ne serait plus celui applique.
                sature = True
                ecartees.append(tache)
            else:
                cumul += tache.estimated
                retenues.append(tache)

    return retenues, ecartees
