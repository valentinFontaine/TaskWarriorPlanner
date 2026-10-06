"""Le livrable de la passe 1 : une `due` sur CHAQUE tache placee, pas seulement
sur les terminales.

## Ce que l'utilisateur a demande, dans ses termes

> Le but aussi de la passe 1 est de remplir la due pour les taches
> intermediaires quand elle les a placees. Si le montage est du pour le
> 31/12/2026, et que la piece met 4 semaines a se fabriquer, la due date de
> « passer la commande » doit etre remplie au 3/12/2026 et la due date du plan
> doit etre remplie au 2/12/2026 ou plus tot si elle rentre en conflit avec
> d'autres choses.

L'echeance de PROJET, elle, continue de ne se poser que sur les terminales :
c'est une **entree** du solveur. Les `due` calculees ici sont une **sortie**.
Les deux ne se confondent pas, et le test le plus important de ce fichier est
celui qui verifie que la sortie ne remonte pas en entree.

## Pourquoi des donnees fabriquees et pas la vraie base

Sur 136 taches reelles on obtient un plan qu'on ne peut pas verifier : il n'y a
pas de reponse calculable a la main a comparer. Ici il y en a une. La chaine
est celle de l'utilisateur, a quatre maillons, et le delai de 4 semaines est
porte par le marqueur `+external`, dont `estTime` se lit comme un DELAI et non
comme du travail (solveur.py, « un seul intervalle, de duree `estimated` lue
comme un DELAI »). C'est ce qui permet a une fabrication de 4 semaines de ne
pas devorer 4 semaines de journees de travail.

## Ce que les tests verifient, et ce qu'ils ne verifient pas

On n'affirme **aucune date absolue calculee a la main** : la geometrie des
creneaux (09:00-12:00, 14:00-17:00, jours ouvres) deplacerait l'attendu d'une
demi-heure a chaque retouche du calendrier de test, et un test qui casse pour
cette raison-la ne dit rien. On verifie les **relations** qui portent la
demande :

1. toute tache placee ressort avec une `due` ;
2. la `due` d'un maillon ne depasse pas le debut du suivant ;
3. le delai de 4 semaines se voit dans l'ecart entre la commande et le
   montage -- c'est le controle de MECANISME : si `+external` etait traite comme
   du travail, ou simplement traverse, cet ecart s'effondrerait ;
4. l'echeance du montage n'est pas deplacee par le calcul ;
5. une `due` calculee ne se fait pas passer pour une `due` posee par
   l'utilisateur.
"""
from datetime import datetime, timedelta

import pytest

from planif.modele import Tache
from planif.solveur import resoudre
from tests.cas_reference import CONTEXTES, GRANULARITE

#: Le lundi ou demarre le plan. Assez tot pour que 4 semaines de delai tiennent
#: avant l'echeance sans coller au bord de l'horizon.
T0 = datetime(2026, 10, 5, 8, 0)
MAINTENANT = T0
HORIZON_FIN = datetime(2027, 1, 5, 0, 0)

#: L'echeance que l'utilisateur pose a la main sur le dernier maillon.
ECHEANCE_MONTAGE = datetime(2026, 12, 31, 17, 0)

DELAI_FABRICATION = timedelta(weeks=4)

UUID_PLANS = "11111111-0000-0000-0000-000000000001"
UUID_COMMANDE = "22222222-0000-0000-0000-000000000002"
UUID_FABRICATION = "33333333-0000-0000-0000-000000000003"
UUID_MONTAGE = "44444444-0000-0000-0000-000000000004"

PROJET = "NPD.exemple.piece"


def chaine_de_la_piece():
    """plans -> commande -> fabrication (+external, 4 semaines) -> montage.

    `depends` porte les PREDECESSEURS (convention Taskwarrior).
    """
    return [
        Tache(uuid=UUID_PLANS, description="Faire les plans", projet=PROJET,
              estimated=timedelta(hours=6), tags=("pro",), contexte="pro"),
        Tache(uuid=UUID_COMMANDE, description="Passer la commande",
              projet=PROJET, estimated=timedelta(hours=1),
              depends=(UUID_PLANS,), tags=("pro",), contexte="pro"),
        Tache(uuid=UUID_FABRICATION, description="Fabrication de la piece",
              projet=PROJET, estimated=DELAI_FABRICATION,
              depends=(UUID_COMMANDE,), tags=("pro", "external"),
              contexte="pro"),
        Tache(uuid=UUID_MONTAGE, description="Montage", projet=PROJET,
              estimated=timedelta(hours=2), depends=(UUID_FABRICATION,),
              due=ECHEANCE_MONTAGE, tags=("pro",), contexte="pro"),
    ]


@pytest.fixture(scope="module")
def plan():
    p = resoudre(chaine_de_la_piece(), CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                 GRANULARITE)
    assert p.blocs, (
        "le plan ressort VIDE ({}) : rien a mesurer, la chaine elle-meme est "
        "en cause avant la question des due".format(p.statut))
    return p


@pytest.fixture(scope="module")
def dues(plan):
    from planif.dues import dues_calculees
    return dues_calculees(plan, chaine_de_la_piece())


def test_le_delai_externe_ne_devore_pas_les_journees_de_travail(plan):
    """Garde-fou sur l'INSTRUMENT, avant toute question de due.

    Si `+external` etait lu comme du travail, la fabrication reclamerait 4
    semaines de creneaux ouvres -- soit bien plus que les 4 semaines de
    calendrier disponibles -- et tout le reste du fichier mesurerait autre
    chose que ce qu'il croit.
    """
    ouvres = [b for b in plan.blocs if not b.externe]
    travail = sum(b.longueur for b in ouvres) * GRANULARITE
    assert travail == timedelta(hours=9), (
        "seules les 9 h de plans + commande + montage sont du travail ; "
        "mesure {}".format(travail))


def test_chaque_tache_placee_ressort_avec_une_due(dues, plan):
    """Le livrable de la passe 1, dans les termes de l'utilisateur."""
    placees = {b.uuid for b in plan.blocs}
    assert placees == set(dues), (
        "taches placees sans due : {}".format(placees - set(dues)))


def test_la_due_d_un_maillon_ne_depasse_pas_le_debut_du_suivant(dues, plan):
    """La chaine se tient : chaque due est un « au plus tard » credible."""
    for amont, aval in ((UUID_PLANS, UUID_COMMANDE),
                        (UUID_COMMANDE, UUID_FABRICATION),
                        (UUID_FABRICATION, UUID_MONTAGE)):
        debut_aval = min(d for d, _ in plan.instants(aval))
        assert dues[amont] <= debut_aval, (
            "{} est due apres le debut de {}".format(amont, aval))


def test_les_quatre_semaines_de_delai_se_voient_dans_la_due_de_la_commande(dues):
    """LE controle de mecanisme.

    C'est l'assertion de l'utilisateur, litteralement : montage le 31/12,
    fabrication 4 semaines, donc la commande est due au plus tard 4 semaines
    avant. Un `+external` traite comme du travail, ou purement et simplement
    traverse, ferait s'effondrer cet ecart -- aucune autre assertion du fichier
    ne le verrait.
    """
    assert dues[UUID_COMMANDE] <= ECHEANCE_MONTAGE - DELAI_FABRICATION


def test_les_plans_sont_dus_avant_la_commande(dues):
    """« ou plus tot si elle rentre en conflit avec d'autres choses »."""
    assert dues[UUID_PLANS] <= dues[UUID_COMMANDE]


def test_le_calcul_ne_repousse_pas_l_echeance_posee_a_la_main(dues):
    """Une due calculee ne desserre jamais un engagement explicite."""
    assert dues[UUID_MONTAGE] <= ECHEANCE_MONTAGE


def test_une_due_calculee_se_distingue_d_une_due_posee_par_l_utilisateur(dues):
    """Sans cette distinction, le plan se fige sur sa propre sortie.

    La regle en vigueur (`appliquer_echeances_projet`) est qu'une tache portant
    deja un `due` propre le garde. Si la passe 1 ecrit une `due` indiscernable
    d'une due humaine, alors au run suivant chaque tache intermediaire porte un
    engagement qu'elle n'a jamais recu de l'utilisateur, et le plan ne peut
    plus se relacher : reculer l'echeance du montage laisserait la commande
    collee a sa date de la veille.
    """
    from planif.dues import est_calculee, marquer_calculee
    tache = marquer_calculee(chaine_de_la_piece()[1], dues[UUID_COMMANDE])
    assert tache.due == dues[UUID_COMMANDE]
    assert est_calculee(tache) is True
    assert est_calculee(chaine_de_la_piece()[3]) is False, \
        "l'echeance du montage est posee par l'utilisateur, pas calculee"


# ==========================================================================
# Le regime SANS AUCUNE DEPENDANCE, souleve par l'utilisateur le 23/09/2026
# ==========================================================================
#
# On avait ecrit qu'un projet dont aucune tache ne porte de `depends` serait
# « inexploitable », puisque TOUTES ses taches sont terminales et recoivent la
# meme `due`. C'est faux, et l'utilisateur l'a releve : cette date commune n'est
# qu'une ENTREE. La passe 1 empile ensuite les taches a rebours selon la
# capacite, et `dues_calculees` rend a chacune une date DIFFERENTE.
#
# C'est meme le regime le plus courant sur ses donnees : la plupart des projets
# n'ont pas de chaine interne.

PROJET_PLAT = "NPD.exemple.plat"
ECHEANCE_PLATE = datetime(2026, 12, 18, 17, 0)


def _taches_sans_dependance(nombre=6, heures=3):
    return [Tache(uuid="eeeeeeee-0000-0000-0000-{:012d}".format(i),
                  description="Tache plate {}".format(i), projet=PROJET_PLAT,
                  estimated=timedelta(hours=heures), due=ECHEANCE_PLATE,
                  tags=("pro",), contexte="pro")
            for i in range(1, nombre + 1)]


@pytest.fixture(scope="module")
def dues_plates():
    from planif.dues import dues_calculees
    taches = _taches_sans_dependance()
    plan = resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    assert plan.blocs, "plan vide ({})".format(plan.statut)
    return dues_calculees(plan, taches)


def test_une_echeance_commune_ressort_en_dates_etagees(dues_plates):
    """L'entree est une date unique ; la sortie ne l'est pas.

    C'est tout l'interet de la passe 1 dans ce regime : elle transforme « tout
    pour le 18 decembre » en un echeancier tenable, tache par tache.
    """
    distinctes = set(dues_plates.values())
    assert len(distinctes) > 1, (
        "les {} taches ressortent avec la meme date : la passe 1 n'a rien "
        "etage".format(len(dues_plates)))


def test_aucune_tache_ne_depasse_l_echeance_commune(dues_plates):
    assert max(dues_plates.values()) <= ECHEANCE_PLATE


def test_toutes_les_taches_sont_datees(dues_plates):
    """Aucune n'est oubliee : six taches, six echeances."""
    assert len(dues_plates) == 6
