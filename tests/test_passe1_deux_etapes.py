"""La passe 1 resout deux fois : le retard, puis « au plus tard ». La seconde
resolution ne doit jamais perdre la solution que la premiere a trouvee.

Defaut trouve en LANCANT l'outil le 17/10/2026, sur une copie de la base reelle
(projet maisonChristina seul, 46 taches en passe 1) :

    budget | etape « retard »        | etape « au plus tard » | plan
       5   | UNKNOWN                 | -                      | VIDE
      15   | FEASIBLE (retard 20370) | UNKNOWN                | VIDE
      45   | FEASIBLE (retard 19652) | UNKNOWN                | VIDE

613 s de calcul pour un plan vide, alors qu'aux budgets 15 et 45 un plan
complet etait EN MAIN apres la premiere resolution. La seconde repartait de
zero -- aucun indice -- sous une contrainte de plus (`retard <= optimum`), et
quand elle ne retrouvait rien dans son budget, `_resoudre_une_fois` rendait le
plan vide au lieu de la solution deja trouvee.

Deux contrats, chacun vu rouge avant la correction :

1. la seconde resolution recoit la solution de la premiere comme indice
   COMPLET (une valeur par variable) ;
2. si elle ne trouve quand meme rien, le plan est celui de la premiere
   resolution : valide pour toutes les contraintes dures, seulement pas pousse
   « au plus tard ». Jamais un plan vide.

Le contrat 2 se teste sans instance difficile : on prive la seconde resolution
de tout budget (`max_deterministic_time = 0`), ce qui la fait rendre UNKNOWN a
coup sur -- meme avec un indice, verifie sur ortools 9.15.
"""
from dataclasses import replace

from ortools.sat.python import cp_model

from planif import solveur
from tests.cas_reference import (CONTEXTES, ECHEANCE_PROJET, GRANULARITE,
                                 HORIZON_FIN, MAINTENANT, T0, UUID_A, UUID_B,
                                 UUID_C, UUID_D, chaine)


def _taches():
    """La chaine A -> B -> C (+external) -> D, D datee : la passe 1 a deux etapes."""
    taches = chaine()
    taches[-1] = replace(taches[-1], due=ECHEANCE_PROJET)
    return taches


def _resoudre_une_fois():
    return solveur._resoudre_une_fois(
        _taches(), CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
        horizon_detaille_fin=T0 + __import__("datetime").timedelta(days=14))


def test_la_seconde_resolution_part_de_la_solution_de_la_premiere(monkeypatch):
    """Contrat 1 : un indice complet, egal a la solution de l'etape « retard »."""
    vus = []
    original = cp_model.CpSolver.Solve

    def espion(self, modele, *a, **kw):
        proto = modele.Proto()
        indice = dict(zip(proto.solution_hint.vars, proto.solution_hint.values))
        etat = original(self, modele, *a, **kw)
        vus.append((len(proto.variables), indice,
                    list(self.ResponseProto().solution)))
        return etat

    monkeypatch.setattr(cp_model.CpSolver, "Solve", espion)
    plan = _resoudre_une_fois()

    assert len(vus) == 2, "attendu deux resolutions (retard, puis au plus tard)"
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    nb_variables, _, solution1 = vus[0]
    nb_variables2, indice2, _ = vus[1]
    assert nb_variables2 == nb_variables
    assert len(indice2) == nb_variables, (
        "la seconde resolution doit recevoir une valeur pour CHAQUE variable : "
        "{} sur {}".format(len(indice2), nb_variables))
    assert all(indice2[i] == v for i, v in enumerate(solution1)), (
        "l'indice doit etre la solution de la premiere resolution")


def test_seconde_resolution_sans_solution_rend_la_premiere(monkeypatch):
    """Contrat 2 : jamais un plan vide quand un plan a ete trouve."""
    appels = []
    original = solveur._solveur

    def affame(budget=None):
        s = original(budget)
        appels.append(s)
        if len(appels) == 2:
            s.parameters.max_deterministic_time = 0.0
        return s

    monkeypatch.setattr(solveur, "_solveur", affame)
    plan = _resoudre_une_fois()

    assert len(appels) == 2, "le chemin vise est la seconde resolution"
    assert plan.statut == "FEASIBLE", (
        "statut {} : la solution de l'etape « retard » a ete perdue"
        .format(plan.statut))
    for uuid in (UUID_A, UUID_B, UUID_C, UUID_D):
        assert plan.blocs_de(uuid), "tache {} absente du plan".format(uuid)
    assert sum(b.longueur for b in plan.blocs_de(UUID_A)) == 8   # 4 h
    # les precedences de la premiere resolution tiennent toujours
    assert plan.debut(UUID_B) >= plan.fin(UUID_A)
    assert plan.debut(UUID_C) >= plan.fin(UUID_B)
    assert plan.debut(UUID_D) >= plan.fin(UUID_C)
