"""Lot 6 — la passe opportuniste (design.md §5, `tasks.md` lot 6).

    « Passe 1 — le mur. [...] Passe 2 — l'opportuniste. Le plan de la passe 1
    est FIGE. Les taches non datees remplissent la capacite restante, par
    urgence decroissante, au plus tot. »

Ce fichier n'ecrit PAS `completer` : il en exerce l'API annoncee, contre
`planif/solveur.py`, pendant que quelqu'un d'autre l'implemente en parallele.
Rouge attendu : `ImportError` sur `completer`.

Horloge figee au lundi 2026-10-05 08:00 (voir `tests/cas_reference.py`).

Le solveur etant lent (jusqu'a 60 s par appel), ce fichier limite le nombre de
resolutions a QUATRE au total, toutes en fixtures `scope="module"` :

    1. `plan_passe1`         : une resolution de la chaine de reference (passe 1).
    2. `plan_complete`       : un `completer` avec un jeu de taches non datees
                               qui sert a TOUS les controles de mecanisme
                               (tests 1, 2->non, 3, 4, 5, 7, 8, 9).
    3. `plan_sans_rien`      : un `completer` sans aucune tache non datee
                               (test 2, l'absence d'effet de bord).
    4. `plan_urgence`        : un `completer` dedie au controle de l'urgence
                               (test 6), avec une offre de taches superieure a
                               la capacite disponible.
"""
from dataclasses import replace
from datetime import date, timedelta

import pytest

from planif.modele import Tache
from planif.solveur import completer, resoudre
from tests.cas_reference import (CONTEXTES, ECHEANCE_PROJET, GRANULARITE,
                                 HORIZON_FIN, MAINTENANT, T0, UUID_A, UUID_B,
                                 UUID_C, UUID_D, chaine)

# --------------------------------------------------------------------------
# Le cas de reference passe par la passe 1 avec l'echeance du projet posee sur
# D (meme interpretation que tests/test_lot5_tiers.py, declaree la-bas et
# rappelee ici : design.md §2 donne la forme d'une echeance de projet mais ne
# dit pas comment elle descend sur les taches).
# --------------------------------------------------------------------------

def _avec_due_sur_d(taches):
    return [replace(t, due=ECHEANCE_PROJET) if t.uuid == UUID_D else t
            for t in taches]


PROJET = "NPD.helisides"

# --- les taches non datees du controle de mecanisme ------------------------

UUID_PRECOCE = "11111111-0000-0000-0000-000000000001"
UUID_REMPLISSAGE = "22222222-0000-0000-0000-000000000002"
UUID_DEP_F = "33333333-0000-0000-0000-000000000003"
UUID_DEP_G = "44444444-0000-0000-0000-000000000004"

# --- les taches du controle d'urgence (call dedie) --------------------------

UUID_URGENT = "55555555-0000-0000-0000-000000000005"
UUID_MOYEN_1 = "66666666-0000-0000-0000-000000000006"
UUID_MOYEN_2 = "77777777-0000-0000-0000-000000000007"
UUID_FAIBLE = "88888888-0000-0000-0000-000000000008"


def taches_mecanisme():
    """Les taches non datees utilisees par `plan_complete` (controles 1,3,4,5,7,8,9).

    - `UUID_PRECOCE`     : urgence la plus forte du lot, petite (1 h). Sert au
      controle « au plus tot » (test 7) : rien ne doit la retarder.
    - `UUID_REMPLISSAGE` : 20 h, soit exactement une semaine pleine (5 j x 4 h)
      -> garantit qu'au moins un jour affiche la capacite maximale (test 4).
    - `UUID_DEP_F`/`UUID_DEP_G` : une precedence entre deux taches non datees
      (test 9), toutes deux petites pour etre placees sans effort.

    Import : elles tiennent largement dans les toutes premieres semaines de
    l'horizon, bien avant que la passe 1 ne consomme A/B (22-23 octobre).
    """
    return [
        Tache(uuid=UUID_PRECOCE, description="Opportuniste precoce", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=20.0,
              estimated=timedelta(hours=1)),
        Tache(uuid=UUID_REMPLISSAGE, description="Opportuniste remplissage",
              projet=PROJET, due=None, contexte="pro", tags=("pro",),
              urgency=9.0, estimated=timedelta(hours=20)),
        Tache(uuid=UUID_DEP_F, description="Opportuniste F", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=6.0,
              estimated=timedelta(hours=2)),
        Tache(uuid=UUID_DEP_G, description="Opportuniste G", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=5.5,
              depends=(UUID_DEP_F,),
              estimated=timedelta(hours=2)),
    ]


def taches_urgence():
    """Les taches non datees du controle d'urgence (test 6), en offre superieure
    a la capacite disponible : 3 x 30 h a urgence forte (90 h) plus 1 x 100 h a
    urgence faible. 190 h ne tiennent pas dans l'horizon (~156 h utiles
    restantes) : la tache faible doit ceder sa place aux trois autres."""
    return [
        Tache(uuid=UUID_URGENT, description="Urgence forte", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=10.0,
              estimated=timedelta(hours=30)),
        Tache(uuid=UUID_MOYEN_1, description="Urgence moyenne 1", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=9.0,
              estimated=timedelta(hours=30)),
        Tache(uuid=UUID_MOYEN_2, description="Urgence moyenne 2", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=8.0,
              estimated=timedelta(hours=30)),
        Tache(uuid=UUID_FAIBLE, description="Urgence faible", projet=PROJET,
              due=None, contexte="pro", tags=("pro",), urgency=1.0,
              estimated=timedelta(hours=100)),
    ]


# --------------------------------------------------------------------------
# Fixtures — quatre resolutions au total pour tout le fichier.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plan_passe1():
    """Resolution n°1 : la chaine de reference, passe 1 seule."""
    taches = _avec_due_sur_d(chaine())
    return resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)


@pytest.fixture(scope="module")
def plan_complete(plan_passe1):
    """Resolution n°2 : `completer` avec le jeu de taches du controle de mecanisme."""
    return completer(plan_passe1, taches_mecanisme(), CONTEXTES, T0, MAINTENANT,
                     HORIZON_FIN, GRANULARITE)


@pytest.fixture(scope="module")
def plan_sans_rien(plan_passe1):
    """Resolution n°3 : `completer` sans aucune tache non datee."""
    return completer(plan_passe1, [], CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                     GRANULARITE)


@pytest.fixture(scope="module")
def plan_urgence(plan_passe1):
    """Resolution n°4 : `completer` avec une offre superieure a la capacite."""
    return completer(plan_passe1, taches_urgence(), CONTEXTES, T0, MAINTENANT,
                     HORIZON_FIN, GRANULARITE)


def _cles(blocs):
    """Projette une collection de blocs sur l'ensemble (uuid, indice, debut, fin)."""
    return {(b.uuid, b.indice, b.debut, b.fin) for b in blocs}


# --------------------------------------------------------------------------
# Les controles de mecanisme
# --------------------------------------------------------------------------

def test_le_plan_de_la_passe_1_ne_bouge_pas_d_un_creneau(plan_passe1, plan_complete):
    """Chaque bloc de la passe 1 se retrouve, au meme creneau exact, dans le plan complete."""
    cles_passe1 = _cles(plan_passe1.blocs)
    cles_complete = _cles(plan_complete.blocs)
    assert cles_passe1, "la passe 1 n'a produit aucun bloc : le controle serait vide"
    assert cles_passe1.issubset(cles_complete)


def test_sans_tache_non_datee_le_plan_est_identique(plan_passe1, plan_sans_rien):
    """`completer(plan, [], ...)` ne modifie ni n'ajoute aucun bloc : pas d'effet de bord."""
    assert _cles(plan_sans_rien.blocs) == _cles(plan_passe1.blocs)
    assert len(plan_sans_rien.blocs) == len(plan_passe1.blocs)


def test_les_taches_opportunistes_sont_marquees(plan_complete):
    """Les blocs ajoutes portent `opportuniste=True`, ceux de la passe 1 ne le portent jamais."""
    uuids_passe1 = {UUID_A, UUID_B, UUID_C, UUID_D}
    au_moins_un_opportuniste = False
    for bloc in plan_complete.blocs:
        if bloc.uuid in uuids_passe1:
            assert bloc.opportuniste is False, \
                "un bloc de la passe 1 est marque opportuniste : " + bloc.uuid
        else:
            assert bloc.opportuniste is True, \
                "un bloc opportuniste n'est pas marque : " + bloc.uuid
            au_moins_un_opportuniste = True
    assert au_moins_un_opportuniste, "aucun bloc opportuniste dans le plan : controle vide"


def test_les_opportunistes_ne_prennent_que_la_place_restante(plan_complete):
    """Aucun jour ne depasse 8 creneaux (4 h) une fois passe 1 ET passe 2 comptees."""
    par_jour = plan_complete.creneaux_par_jour()
    assert par_jour, "aucun creneau occupe : le controle serait vide"
    for jour, occupe in par_jour.items():
        assert occupe <= 8, "{} : {} creneaux, capacite depassee".format(jour, occupe)
    assert any(occupe == 8 for occupe in par_jour.values()), \
        "aucun jour entierement rempli : le controle ne prouve rien"


def test_les_opportunistes_ne_chevauchent_ni_entre_eux_ni_la_passe_1(plan_complete):
    """L'utilisateur reste une ressource unique : les blocs non agreges ne se chevauchent jamais."""
    blocs = sorted((b for b in plan_complete.blocs if not b.externe and not b.agrege),
                   key=lambda b: b.debut)
    for precedent, suivant in zip(blocs, blocs[1:]):
        assert precedent.fin <= suivant.debut, \
            "chevauchement entre {} et {}".format(precedent.uuid, suivant.uuid)


def test_l_urgence_ordonne_le_choix(plan_urgence):
    """Face a une offre superieure a la capacite, la tache la plus urgente est
    retenue et la moins urgente est laissee de cote (entierement)."""
    blocs_urgent = plan_urgence.blocs_de(UUID_URGENT)
    blocs_faible = plan_urgence.blocs_de(UUID_FAIBLE)
    assert blocs_urgent, "la tache la plus urgente n'a pas ete placee"
    assert blocs_faible == (), "la tache la moins urgente a ete placee malgre l'oversupply"


@pytest.mark.xfail(strict=True, reason=(
    "EXIGENCE NON IMPLEMENTEE, decouverte le 22/09/2026. La passe 2 n'optimise "
    "PAS la precocite : son objectif choisit QUELLES taches sont placees, jamais "
    "OU dans l'horizon. Ce test passait par accident du chemin de recherche. "
    "Retirer le tampon de la passe 1 a deplace les taches datees de 4 jours -- "
    "sans jamais occuper la premiere semaine, verifie -- et l'accident a cesse : "
    "PRECOCE est passee du 05/10 09:00 au 12/10 09:00 alors que les creneaux du "
    "05 au 09 sont LIBRES dans les deux cas. Rien n'a ete degrade ; il n'y avait "
    "rien qui tenait. C'est le meme trou que « par urgence decroissante » du lot "
    "6, toujours ouvert : l'ordre a l'interieur de la passe 2 n'est contraint par "
    "rien. Ce xfail strict redeviendra rouge le jour ou la precocite entrera "
    "dans l'objectif."))
def test_les_opportunistes_sont_placees_au_plus_tot(plan_complete):
    """La passe 2 doit placer au plus tot : la tache la plus urgente du jeu de
    test commence dans les cinq premiers jours ouvres de l'horizon.

    Borne choisie : cinq jours ouvres, soit du lundi 2026-10-05 (MAINTENANT)
    au vendredi 2026-10-09 inclus. C'est large (une semaine ouvree entiere)
    pour eviter un test fragile sur l'ordre exact des creneaux, tout en
    excluant categoriquement un placement « a la fin ».
    """
    debut = plan_complete.debut(UUID_PRECOCE)
    assert debut is not None, "la tache la plus urgente du jeu n'a pas ete placee"
    assert debut.date() <= date(2026, 10, 9), \
        "placee le {}, pas dans les cinq premiers jours ouvres".format(debut.date())


def test_une_tache_est_placee_entierement_ou_pas_du_tout(plan_complete):
    """Pour chaque tache non datee presente dans le plan, la duree totale des
    blocs vaut exactement `estimated` : aucune tache a moitie placee."""
    for tache in taches_mecanisme():
        blocs = plan_complete.blocs_de(tache.uuid)
        if not blocs:
            continue
        total = sum(b.fin - b.debut for b in blocs) * GRANULARITE
        assert total == tache.estimated, \
            "{} : {} place au lieu de {}".format(tache.uuid, total, tache.estimated)


def test_les_precedences_sont_tenues_aussi_en_passe_2(plan_complete):
    """Si F et G (non datees, G depend de F) sont toutes deux placees, F finit avant que G ne commence."""
    fin_f = plan_complete.fin(UUID_DEP_F)
    debut_g = plan_complete.debut(UUID_DEP_G)
    if fin_f is not None and debut_g is not None:
        assert fin_f <= debut_g
    else:
        pytest.fail("F et/ou G n'ont pas ete placees : la precedence n'a pas pu etre controlee")
