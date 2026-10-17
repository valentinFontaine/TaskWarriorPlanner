"""Une tache dont la limite tombe AU-DELA de la frontiere detaillee peut quand
meme etre placee AVANT elle.

Defaut trouve en lancant l'outil le 17/10/2026 (copie de la base reelle) : une
periode de vacances (perso 09:00-19:00 du 24/10 au 01/11) etait presque vide
dans le plan, et le projet maisonChristina, dont l'unique echeance est le 02/11,
ne demarrait que le 31/10 au soir -- en retard, alors que ses premieres taches
n'avaient aucun predecesseur.

Mecanisme : le regime d'une tache se choisissait sur sa SEULE limite. Limite
au-dela de la frontiere (31/10 avec 14 jours d'horizon detaille) -> tache
« agregee », dont les blocs n'avaient pour candidates QUE les journees agregees,
toutes posterieures a la frontiere. Les 46 taches du projet heritant toutes de
la limite du 02/11, aucune ne pouvait toucher aux 82 h disponibles avant la
frontiere, et 72 h de travail devaient tenir apres elle : retard garanti.

Or design.md §1 n'agrege que la CAPACITE au-dela de l'horizon detaille ; rien
n'y interdit a une tache lointaine d'utiliser la capacite proche. Un bloc
place avant la frontiere entre dans la ressource unique comme n'importe quel
bloc detaille.

Construction minimale : une grille d'une heure par jour, une periode de
10 h/jour entierement avant la frontiere, une chaine de 20 h datee apres
elle. Le parametre deplace la date : le temoin (limite AVANT la frontiere)
passait deja, les deux autres non.
"""
from datetime import date, datetime, timedelta

import pytest

from planif.calendrier import indice_creneau
from planif.modele import Contexte, Creneau, Tache
from planif.solveur import resoudre

T0 = datetime(2026, 10, 17, 0, 0)              # samedi
MAINTENANT = datetime(2026, 10, 17, 8, 0)
GRANULARITE = timedelta(hours=1)
FRONTIERE = T0 + timedelta(days=14)            # samedi 31/10, minuit
HORIZON_FIN = T0 + timedelta(days=60)

_SOIR = (Creneau(18 * 60, 19 * 60),)           # 1 h par jour hors periode
VACANCES = (date(2026, 10, 24), date(2026, 10, 30),
            (Creneau(9 * 60, 19 * 60),))       # 7 x 10 h, avant la frontiere

PERSO = Contexte(nom="perso", contexte_tw="perso",
                 bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
                 grille={j: _SOIR for j in range(7)}, periodes=(VACANCES,))
CONTEXTES = {"perso": PERSO}


def _chaine(due):
    """Quatre taches de 5 h, sans predecesseur pour la premiere ; la derniere datee."""
    taches = []
    for i in range(4):
        taches.append(Tache(
            uuid="c{:07d}-0000-0000-0000-000000000000".format(i),
            description="etape {}".format(i), estimated=timedelta(hours=5),
            depends=(taches[-1].uuid,) if taches else (),
            due=due if i == 3 else None, tags=("perso",), contexte="perso"))
    return taches


@pytest.mark.parametrize("due", [
    datetime(2026, 10, 30, 19, 0),   # temoin : limite avant la frontiere
    datetime(2026, 11, 2, 9, 0),     # le cas reel : 2 jours apres
    datetime(2026, 11, 10, 9, 0),    # 10 jours apres
], ids=["avant-frontiere", "frontiere+2j", "frontiere+10j"])
def test_la_capacite_avant_frontiere_sert_aux_limites_lointaines(due):
    taches = _chaine(due)
    plan = resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
                    horizon_detaille_fin=FRONTIERE)

    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert sum(b.longueur for b in plan.blocs) == 20
    # 70 h libres pendant la periode, 20 h de travail : aucun retard possible
    # si la periode est utilisable. Apres la frontiere, 1 h par jour : 20 h
    # demanderaient 20 jours, et l'echeance tomberait.
    assert plan.en_retard == (), (
        "en retard : {} -- la periode avant la frontiere n'a pas servi "
        "(premier bloc le {})".format(plan.en_retard, plan.debut(taches[0].uuid)))
    assert plan.fin(taches[-1].uuid) <= due
    frontiere = indice_creneau(T0, FRONTIERE, GRANULARITE)
    for bloc in plan.blocs:
        assert bloc.agrege == (bloc.debut >= frontiere)
    tries = sorted(plan.blocs, key=lambda b: b.debut)
    assert all(a.fin <= b.debut for a, b in zip(tries, tries[1:])), (
        "deux blocs detailles se chevauchent")
