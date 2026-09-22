"""Selection des candidates de la passe 2, a hauteur de la capacite reelle.

Constate sur les donnees reelles : la passe 2 soumettait **184 candidates** pour
une capacite de deux semaines, soit une quarantaine d'heures utiles. Le solveur
n'a trouve AUCUNE solution en 60 s (`UNKNOWN`, pas `INFEASIBLE` : « ne rien
placer » est pourtant toujours faisable — le modele etait trop gros pour etre
seulement demarre).

L'algorithme retenu, specifie par l'utilisateur :

    capacite disponible = grille - marge - reunions - ce que la passe 1 a pris
    puis, CONTEXTE PAR CONTEXTE, file d'attente par urgence decroissante,
    cumul des durees jusqu'a saturation.

Le detail des mesures, et les deux hypotheses successives qu'elles ont
departagees, vivent dans `planif/selection.py`. Ce qu'il faut en retenir ici :
la selection par capacite est necessaire mais ne suffisait pas — c'est
**l'horizon de la passe 2** qui a debloque le solveur, et ce module travaille
donc sur cet horizon-la, jamais sur l'horizon total.

Le choix a justifier, lui, tient toujours :

- **par contexte et non globalement** : une tache `perso` urgente ne doit pas
  etre ecartee parce que le `pro` deborde. Ce sont deux budgets separes, c'est
  tout le modele.
"""
from datetime import datetime, timedelta

import pytest

from planif.modele import Contexte, Creneau, Tache

MAINTENANT = datetime(2026, 9, 22, 8, 0)      # mardi
T0 = datetime(2026, 9, 22, 0, 0)
GRANULARITE = timedelta(minutes=30)

_MATIN = Creneau(9 * 60, 12 * 60)             # 3 h
_APRES_MIDI = Creneau(14 * 60, 17 * 60)       # 3 h

PRO = Contexte(nom="pro", contexte_tw="pro", bloc_min=timedelta(hours=2),
               marge_jour=timedelta(hours=2),     # -> 4 h utiles par jour ouvre
               grille={i: ((_MATIN, _APRES_MIDI) if i < 5 else ())
                       for i in range(7)})
PERSO = Contexte(nom="perso", contexte_tw="perso", bloc_min=timedelta(hours=1),
                 marge_jour=timedelta(minutes=30),  # -> 1 h 30 utile par jour
                 grille={i: ((Creneau(19 * 60, 21 * 60),) if i < 5 else ())
                         for i in range(7)})
CONTEXTES = {"pro": PRO, "perso": PERSO}


def _tache(n, contexte, heures, urgence):
    return Tache(uuid="{}-{:04d}".format(contexte, n),
                 description="{} {}".format(contexte, n),
                 estimated=timedelta(hours=heures), urgency=urgence,
                 tags=(contexte,), contexte=contexte)


def test_capacite_restante_retire_ce_que_la_passe_1_a_pris():
    from planif.selection import capacite_restante

    fin = T0 + timedelta(days=7)          # une semaine : 5 jours ouvres
    libre = capacite_restante(CONTEXTES, T0, MAINTENANT, fin, GRANULARITE,
                              deja_pris={})
    # 5 jours ouvres x 4 h pour `pro`. Le mardi courant est entame a 08:00,
    # donc il compte encore entier : la grille commence a 09:00.
    assert libre["pro"] == timedelta(hours=20)
    assert libre["perso"] == timedelta(hours=7, minutes=30)

    # La passe 1 a pris 6 h de `pro` : il doit en rester 14.
    avec_charge = capacite_restante(CONTEXTES, T0, MAINTENANT, fin, GRANULARITE,
                                    deja_pris={"pro": timedelta(hours=6)})
    assert avec_charge["pro"] == timedelta(hours=14)
    assert avec_charge["perso"] == timedelta(hours=7, minutes=30)


def test_une_charge_superieure_a_la_capacite_ne_rend_jamais_un_negatif():
    from planif.selection import capacite_restante

    fin = T0 + timedelta(days=7)
    libre = capacite_restante(CONTEXTES, T0, MAINTENANT, fin, GRANULARITE,
                              deja_pris={"pro": timedelta(hours=999)})
    assert libre["pro"] == timedelta(0)


def test_la_selection_coupe_par_urgence_decroissante():
    from planif.selection import selectionner_candidates

    # 20 taches `pro` de 2 h = 40 h offertes pour 20 h de capacite.
    taches = [_tache(i, "pro", 2, urgence=float(i)) for i in range(20)]
    libre = {"pro": timedelta(hours=20)}

    retenues, ecartees = selectionner_candidates(taches, libre, facteur=2)

    # Facteur 2 : on offre 40 h au solveur pour 20 h de capacite, soit 20 taches
    # de 2 h. Ici tout rentre donc, mais l'ORDRE doit etre le bon.
    assert len(retenues) + len(ecartees) == 20
    if ecartees:
        urgence_min_retenue = min(t.urgency for t in retenues)
        urgence_max_ecartee = max(t.urgency for t in ecartees)
        assert urgence_min_retenue >= urgence_max_ecartee


def test_une_offre_trop_grande_est_bien_coupee():
    from planif.selection import selectionner_candidates

    # 60 taches de 2 h = 120 h offertes, pour 10 h de capacite -> 20 h retenues.
    taches = [_tache(i, "pro", 2, urgence=float(i)) for i in range(60)]
    retenues, ecartees = selectionner_candidates(
        taches, {"pro": timedelta(hours=10)}, facteur=2)

    assert len(retenues) == 10           # 20 h / 2 h
    assert len(ecartees) == 50
    # Les dix plus urgentes, et elles seules.
    assert {t.urgency for t in retenues} == {float(i) for i in range(50, 60)}


def test_le_facteur_par_defaut_vaut_un():
    """Le defaut est une MESURE, pas une intuition -- voir planif/selection.py.

    Je pensais qu'il fallait offrir plus que la capacite pour laisser au solveur
    de quoi arbitrer. Les chiffres ont dit le contraire : a nombre de candidates
    egal, c'est l'horizon de placement qui decide, pas la taille de la file.
    """
    from planif.selection import FACTEUR_OFFRE, selectionner_candidates

    assert FACTEUR_OFFRE == 1

    taches = [_tache(i, "pro", 2, urgence=float(i)) for i in range(60)]
    retenues, _ = selectionner_candidates(taches, {"pro": timedelta(hours=10)})
    assert len(retenues) == 5            # 10 h / 2 h


def test_les_contextes_ont_des_budgets_separes():
    """Le point que l'utilisateur a explicitement demande.

    Une tache `perso` urgente ne doit pas etre ecartee parce que le budget
    `pro` deborde : ce sont deux files d'attente independantes.
    """
    from planif.selection import selectionner_candidates

    taches = ([_tache(i, "pro", 2, urgence=100.0) for i in range(60)]
              + [_tache(i, "perso", 1, urgence=1.0) for i in range(3)])
    libre = {"pro": timedelta(hours=10), "perso": timedelta(hours=5)}

    retenues, _ = selectionner_candidates(taches, libre)
    perso_retenues = [t for t in retenues if t.contexte == "perso"]

    assert len(perso_retenues) == 3, (
        "les taches perso, peu urgentes, ont ete ecartees par le debordement "
        "du contexte pro : les budgets ne sont pas separes")


def test_une_tache_sans_duree_ou_sans_contexte_n_est_pas_retenue():
    """Elles sont deja signalees par les pre-verifications ; ici on ne les
    compte simplement pas dans le budget, et on ne les fait pas passer pour
    ecartees faute de place -- ce serait un message faux."""
    from planif.selection import selectionner_candidates

    sans_duree = Tache(uuid="x1", description="sans duree", estimated=None,
                       tags=("pro",), contexte="pro")
    sans_ctx = Tache(uuid="x2", description="sans contexte",
                     estimated=timedelta(hours=1), tags=(), contexte=None)

    retenues, ecartees = selectionner_candidates(
        [sans_duree, sans_ctx], {"pro": timedelta(hours=10)})

    assert retenues == []
    assert ecartees == []


def test_la_selection_est_deterministe():
    """Deux taches de meme urgence ne doivent pas changer d'ordre d'un run a
    l'autre, sinon le plan cesse d'etre reproductible."""
    from planif.selection import selectionner_candidates

    taches = [_tache(i, "pro", 2, urgence=5.0) for i in range(30)]
    libre = {"pro": timedelta(hours=10)}

    a, _ = selectionner_candidates(taches, libre)
    b, _ = selectionner_candidates(list(reversed(taches)), libre)
    assert [t.uuid for t in a] == [t.uuid for t in b]
