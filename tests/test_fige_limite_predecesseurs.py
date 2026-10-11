"""Contrat de test -- le debut d'une tache +fixed borne ses predecesseurs.

Defaut trouve le 2026-10-11 sur la base reelle (projet Balise77) : la passe 1
etait INFAISABLE a cause de « faire verif des postes sur le terrain », figee au
samedi 17/10 9:00, SANS `due`. Sa chaine amont (tracage -> verification ->
envoi -> controle externe) n'avait donc aucune limite :
`limites_effectives` ne lisait que les `due`. Une tache sans limite part en
regime AGREGE, place seulement au-dela de la frontiere de l'horizon detaille
(25/10) ; la precedence vers la figee du 17/10 devenait impossible a tenir, et
le modele entier INFAISABLE.

Specification : pour un predecesseur d'une tache `+fixed` qui porte un
`scheduled`, ce `scheduled` est une limite, au meme titre qu'un `due` (min des
deux s'il y a les deux). Il n'est PAS tamponne : c'est un fait, pas une
echeance (design.md §4, le tampon ne s'applique qu'aux `due` reelles).

Horloge figee : aucun `datetime.now()`.
"""
from datetime import datetime, timedelta

from planif.modele import Contexte, Creneau, Tache
from planif.solveur import resoudre
from planif.tampon import limites_effectives

T0 = datetime(2026, 10, 5, 0, 0)          # lundi, minuit
MAINTENANT = datetime(2026, 10, 5, 8, 0)  # lundi 08:00
GRANULARITE = timedelta(minutes=30)
HORIZON_FIN = T0 + timedelta(days=35)
HORIZON_DETAILLE_FIN = T0 + timedelta(days=14)   # frontiere : lundi 19/10

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

UUID_A = "aaaaaaaa-0000-0000-0000-000000000001"   # predecesseur de A2
UUID_A2 = "aaaaaaaa-0000-0000-0000-000000000002"  # predecesseur direct de F
UUID_F = "ffffffff-0000-0000-0000-000000000001"   # figee, sans due

DEBUT_F = datetime(2026, 10, 9, 9, 0)   # vendredi 9:00, avant la frontiere


def _taches(due_f=None):
    return [
        Tache(uuid=UUID_A, description="amont", contexte="ctxA",
              estimated=timedelta(hours=2)),
        Tache(uuid=UUID_A2, description="juste avant", contexte="ctxA",
              estimated=timedelta(hours=2), depends=(UUID_A,)),
        Tache(uuid=UUID_F, description="figee", contexte="ctxA",
              estimated=timedelta(hours=1), scheduled=DEBUT_F,
              due=due_f, tags=("fixed",), depends=(UUID_A2,)),
    ]


def test_debut_fige_est_la_limite_des_predecesseurs():
    limites = limites_effectives(_taches(), CONTEXTES_A)
    assert limites[UUID_A2] == DEBUT_F
    assert limites[UUID_A] == DEBUT_F      # transitif, sans tampon cumule


def test_due_de_la_figee_plus_tot_que_son_debut_reste_le_min():
    # cas tordu (due avant le debut) : on garde le plus contraignant
    due = datetime(2026, 10, 9, 8, 0)
    limites = limites_effectives(_taches(due_f=due), CONTEXTES_A)
    assert limites[UUID_A2] <= DEBUT_F


def test_tache_non_figee_avec_scheduled_ne_borne_rien():
    # `scheduled` sans +fixed n'est qu'une proposition, pas une limite
    taches = _taches()
    taches[2] = Tache(uuid=UUID_F, description="pas figee", contexte="ctxA",
                      estimated=timedelta(hours=1), scheduled=DEBUT_F,
                      depends=(UUID_A2,))
    limites = limites_effectives(taches, CONTEXTES_A)
    assert limites[UUID_A2] is None


def test_chaine_avant_une_figee_sans_due_est_placee_avant_elle():
    plan = resoudre(_taches(), CONTEXTES_A, T0, MAINTENANT, HORIZON_FIN,
                    GRANULARITE, horizon_detaille_fin=HORIZON_DETAILLE_FIN)
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    # le chemin vise est bien exerce : les deux predecesseurs sont places
    places = {b.uuid for b in plan.blocs}
    assert {UUID_A, UUID_A2, UUID_F} <= places
    assert plan.fin(UUID_A) <= plan.debut(UUID_A2)
    assert plan.fin(UUID_A2) <= DEBUT_F
