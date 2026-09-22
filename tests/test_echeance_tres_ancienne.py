"""Une echeance tres ancienne ne doit pas rendre le modele infaisable.

Trouve a la premiere execution sur une copie des donnees reelles de
l'utilisateur, pas par relecture. La passe 1 rendait `INFEASIBLE` en 0,04 s sur
278 taches, et une dichotomie a montre qu'**une seule tache suffisait** :

    coupable : « aller chercher veste Christina pressing »
    estimated=0:20:00  due=2026-05-13 12:00:00
    limite effective (tampon applique) : 2026-05-11 19:30:00

Le mecanisme, confirme en elargissant l'horizon et rien d'autre :

    borne en creneaux depuis t0 : -6393  (negative = dans le passe)
    horizon  90 j =  4320 creneaux | statut INFEASIBLE | blocs 0
    horizon 150 j =  7200 creneaux | statut OPTIMAL    | blocs 1
    horizon 200 j =  9600 creneaux | statut OPTIMAL    | blocs 1

`retard` etait declare sur le domaine `[0, horizon]`. Or `retard = fin - borne`,
et quand `borne` est negative -- une echeance anterieure a `t0` -- le retard
reellement necessaire vaut `fin + |borne|`, qui depasse `horizon` des que la
tache est en retard de plus que la longueur de l'horizon. Le domaine ne pouvait
pas porter la valeur, et CP-SAT declarait le modele infaisable.

C'est le pire cas de figure pour cet outil : **l'echeance souple redevenait
dure**, silencieusement, et une seule vieille tache annulait la planification de
toutes les autres. C'est exactement ce que le lot 4 voulait empecher :

    « une echeance intenable est signalee sans empecher les autres d'etre
      planifiees » -- tasks.md, lot 4

L'utilisateur a 53 taches dont la `due` est depassee. Avec un horizon de 90
jours, il suffit qu'UNE d'entre elles le soit de plus de 90 jours.
"""
from datetime import datetime, timedelta

import pytest

from planif.modele import Contexte, Creneau, Tache
from planif.solveur import resoudre

MAINTENANT = datetime(2026, 9, 22, 8, 0)     # mardi
T0 = datetime(2026, 9, 22, 0, 0)
GRANULARITE = timedelta(minutes=30)
HORIZON_FIN = T0 + timedelta(days=90)

_MATIN = Creneau(9 * 60, 12 * 60)
_APRES_MIDI = Creneau(14 * 60, 17 * 60)
CONTEXTE = Contexte(nom="perso", contexte_tw="perso",
                    bloc_min=timedelta(minutes=30), marge_jour=timedelta(0),
                    grille={i: ((_MATIN, _APRES_MIDI) if i < 5 else ())
                            for i in range(7)})
CONTEXTES = {"perso": CONTEXTE}

UUID_VIEILLE = "11111111-0000-0000-0000-000000000001"
UUID_SAINE = "22222222-0000-0000-0000-000000000002"


def _vieille(jours_de_retard):
    return Tache(uuid=UUID_VIEILLE, description="aller chercher la veste",
                 estimated=timedelta(minutes=30),
                 due=MAINTENANT - timedelta(days=jours_de_retard),
                 tags=("perso",), contexte="perso")


@pytest.mark.parametrize("jours_de_retard", [1, 30, 89, 134, 400])
def test_une_echeance_ancienne_reste_planifiable(jours_de_retard):
    """Peu importe l'anciennete : la tache est placee, avec du retard.

    134 jours est le retard reel de la tache qui a fait tomber la passe 1 ;
    400 jours verifie qu'on n'a pas seulement repousse le seuil.
    """
    plan = resoudre([_vieille(jours_de_retard)], CONTEXTES, T0, MAINTENANT,
                    HORIZON_FIN, GRANULARITE)

    assert plan.statut != "INFEASIBLE", (
        "une echeance vieille de {} jours rend le modele infaisable ; "
        "l'echeance est censee etre SOUPLE".format(jours_de_retard))
    assert plan.blocs, "la tache n'est pas placee"
    assert UUID_VIEILLE in plan.en_retard
    assert plan.retard_total > 0


def test_une_vieille_tache_n_empeche_pas_les_autres_d_etre_planifiees():
    """L'exigence du lot 4, mise a l'epreuve par le cas reel.

    C'est la vraie consequence du defaut : ce n'est pas la vieille tache qui
    importe, c'est que son domaine trop etroit annulait le plan ENTIER.
    """
    saine = Tache(uuid=UUID_SAINE, description="preparer la reunion",
                  estimated=timedelta(hours=1),
                  due=MAINTENANT + timedelta(days=10),
                  tags=("perso",), contexte="perso")

    plan = resoudre([_vieille(134), saine], CONTEXTES, T0, MAINTENANT,
                    HORIZON_FIN, GRANULARITE)

    assert plan.statut != "INFEASIBLE"
    assert plan.blocs_de(UUID_SAINE), "la tache saine n'est pas planifiee"
    assert UUID_SAINE not in plan.en_retard
    assert UUID_VIEILLE in plan.en_retard
