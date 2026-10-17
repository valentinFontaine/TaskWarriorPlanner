"""Contrat de test -- une tache +fixed deja commencee ne rend pas le plan infaisable.

Defaut trouve le 2026-10-17 sur la base reelle : depuis 09:00, tout le calcul
(base entiere comme Balise77 seul) etait INFAISABLE. « faire verif des postes
sur le terrain » (+fixed, scheduled 17/10 09:00, 5 h) avait son debut dans le
passe et n'etait pas terminee. Le bloc 0 d'une figee est une constante posee a
son `scheduled`, mais le debut et la fin de chaque TACHE etaient des variables
de domaine `[maintenant, horizon]` : contradiction immediate, meme pour une
figee seule et sans dependance.

Specification (decidee avec l'utilisateur le 2026-10-17) : on garde le FAIT.
Le bloc 0 reste a son `scheduled`, meme passe (en cours, ou suppose fait) ;
ses successeurs attendent sa fin ; un predecesseur encore en attente ne la
contraint plus (on ne peut pas finir avant un debut deja passe) et se place a
partir de maintenant.

Parametre autour du seuil : `maintenant` avant le debut (temoin), pendant, et
apres la fin du fait. Horloge figee : aucun `datetime.now()`.
"""
from datetime import datetime, timedelta

import pytest

from planif.modele import Contexte, Creneau, Tache
from planif.solveur import completer, resoudre

T0 = datetime(2026, 10, 5, 0, 0)          # lundi, minuit
GRANULARITE = timedelta(minutes=30)
HORIZON_FIN = T0 + timedelta(days=35)

_VIDE = ()
CONTEXTE_A = Contexte(
    nom="ctxA", contexte_tw="ctxA",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(9 * 60, 13 * 60),), 1: (Creneau(9 * 60, 13 * 60),),
        2: (Creneau(9 * 60, 13 * 60),), 3: (Creneau(9 * 60, 13 * 60),),
        4: (Creneau(9 * 60, 13 * 60),), 5: _VIDE, 6: _VIDE,
    },
)
CONTEXTES_A = {"ctxA": CONTEXTE_A}

UUID_F = "ffffffff-0000-0000-0000-000000000001"   # figee
UUID_S = "55555555-0000-0000-0000-000000000001"   # successeur de F
UUID_P = "99999999-0000-0000-0000-000000000001"   # predecesseur de F

DEBUT_F = datetime(2026, 10, 9, 9, 0)    # vendredi 09:00
FIN_F = DEBUT_F + timedelta(hours=1)

MAINTENANTS = {
    # temoin : le fait est a venir, avec une matinee libre pour P (jeudi)
    "avant": datetime(2026, 10, 8, 8, 0),
    "pendant": datetime(2026, 10, 9, 9, 30),  # commence, pas fini
    "apres": datetime(2026, 10, 12, 10, 0),   # lundi suivant, fin passee
}


def _f(depends=()):
    return Tache(uuid=UUID_F, description="figee", contexte="ctxA",
                 estimated=timedelta(hours=1), scheduled=DEBUT_F,
                 tags=("fixed",), depends=depends)


def _s():
    return Tache(uuid=UUID_S, description="apres la figee", contexte="ctxA",
                 estimated=timedelta(hours=1), depends=(UUID_F,))


def _p():
    return Tache(uuid=UUID_P, description="avant la figee", contexte="ctxA",
                 estimated=timedelta(hours=1))


def _resoudre(taches, maintenant):
    return resoudre(taches, CONTEXTES_A, T0, maintenant, HORIZON_FIN,
                    GRANULARITE)


@pytest.mark.parametrize("moment", list(MAINTENANTS))
def test_passe1_figee_seule_reste_a_son_debut(moment):
    plan = _resoudre([_f()], MAINTENANTS[moment])
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert plan.debut(UUID_F) == DEBUT_F


@pytest.mark.parametrize("moment", list(MAINTENANTS))
def test_passe1_successeur_attend_la_fin_et_maintenant(moment):
    maintenant = MAINTENANTS[moment]
    plan = _resoudre([_f(), _s()], maintenant)
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert plan.debut(UUID_F) == DEBUT_F
    assert plan.debut(UUID_S) >= max(FIN_F, maintenant)


@pytest.mark.parametrize("moment", list(MAINTENANTS))
def test_passe1_predecesseur_en_attente_ne_bloque_pas(moment):
    maintenant = MAINTENANTS[moment]
    plan = _resoudre([_p(), _f(depends=(UUID_P,))], maintenant)
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert plan.debut(UUID_F) == DEBUT_F
    # chemin exerce : le predecesseur est bien place, a partir de maintenant
    assert plan.debut(UUID_P) is not None
    assert plan.debut(UUID_P) >= maintenant
    if moment == "avant":
        # le fait est a venir : la precedence tient toujours
        assert plan.fin(UUID_P) <= DEBUT_F


@pytest.mark.parametrize("moment", list(MAINTENANTS))
def test_passe2_figee_non_datee_reste_a_son_debut(moment):
    maintenant = MAINTENANTS[moment]
    plan1 = _resoudre([], maintenant)
    plan2 = completer(plan1, [_f(), _s()], CONTEXTES_A, T0, maintenant,
                      HORIZON_FIN, GRANULARITE)
    assert plan2.debut(UUID_F) == DEBUT_F
    assert plan2.debut(UUID_S) is not None
    assert plan2.debut(UUID_S) >= max(FIN_F, maintenant)
