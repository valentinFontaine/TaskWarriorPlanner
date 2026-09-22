"""Le plan ne doit pas se figer sur sa propre sortie de la veille.

Des que la passe 1 ecrit ses `due` dans Taskwarrior, elle les relit au run
suivant. Sans precaution, ce qu'elle a calcule hier devient une contrainte
d'entree aujourd'hui, et deux choses se cassent :

1. **la stabilite** -- rien ne garantit que la boucle
   `due -> urgency -> placement -> due` converge ;
2. **la reactivite**, et c'est la vraie casse -- la regle en vigueur est qu'une
   tache portant deja un `due` propre le garde. Si nos propres `due` sont
   indiscernables des siennes, alors reculer l'echeance d'un projet dans
   `echeances.json` ne relacherait RIEN : chaque terminale resterait collee a la
   date d'hier, et l'utilisateur ne verrait aucun effet a sa modification.

Le deuxieme test de ce fichier est donc plus important que le premier. Le
premier constate une propriete ; le second verifie que le mecanisme
`duePlanif` sert reellement a quelque chose.

## Verifie par MUTATION, pas suppose

Ces tests n'ont d'abord ete rouges que par `ImportError`, ce qui ne prouve rien.
On a donc neutralise `oublier_dues_calculees` (rendue identite) et relance :

    test_deux_executions_successives_rendent_le_meme_plan   PASSE malgre tout
    test_une_troisieme_execution_ne_derive_pas_davantage    PASSE malgre tout
    test_reculer_l_echeance_relache_le_plan                 MORD
    test_une_due_posee_a_la_main_survit_a_la_replanification PASSE malgre tout

La boucle converge donc d'elle-meme : reecrire une `due` egale a la sortie du
plan ne deplace pas ce plan. Les deux tests de stabilite gardent leur utilite --
ils attraperaient une divergence franche, d'une autre nature -- mais ils ne
testent PAS le mecanisme `duePlanif`. Un seul le fait, et son message le dit
mot pour mot : « le plan n'a pas suivi l'echeance reculee : il est reste au
2026-12-31 alors que l'echeance est passee au 2027-02-26 ».

`est_calculee` (voir `planif/dues.py`) reconnait nos ecritures en comparant la
VALEUR : `due == due_planif`. Un `task X modify due:...` fait a la main change
`due` sans toucher `due_planif`, les deux divergent, et l'engagement humain est
respecte -- ce qu'un simple drapeau ne saurait pas faire.
"""
from datetime import datetime, timedelta

import pytest

from planif.dues import dues_calculees, marquer_calculee, oublier_dues_calculees
from planif.echeances import appliquer_echeances_projet
from planif.modele import Tache
from planif.solveur import resoudre
from tests.cas_reference import CONTEXTES, GRANULARITE

T0 = datetime(2026, 10, 5, 8, 0)
HORIZON_FIN = datetime(2027, 3, 1, 0, 0)

PROJET = "NPD.exemple.piece"
ECHEANCE = datetime(2026, 12, 31, 17, 0)
ECHEANCE_RECULEE = datetime(2027, 2, 26, 17, 0)

U_PLANS = "11111111-0000-0000-0000-000000000001"
U_COMMANDE = "22222222-0000-0000-0000-000000000002"
U_MONTAGE = "33333333-0000-0000-0000-000000000003"


def chaine():
    """Trois maillons, aucune `due` posee a la main : tout vient du projet."""
    return [
        Tache(uuid=U_PLANS, description="Plans", projet=PROJET,
              estimated=timedelta(hours=4), tags=("pro",), contexte="pro"),
        Tache(uuid=U_COMMANDE, description="Commande", projet=PROJET,
              estimated=timedelta(hours=2), depends=(U_PLANS,),
              tags=("pro",), contexte="pro"),
        Tache(uuid=U_MONTAGE, description="Montage", projet=PROJET,
              estimated=timedelta(hours=3), depends=(U_COMMANDE,),
              tags=("pro",), contexte="pro"),
    ]


def _planifier(taches, echeance):
    """Une execution complete : echeance de projet, puis passe 1."""
    avec = appliquer_echeances_projet(oublier_dues_calculees(taches),
                                      {PROJET: echeance})
    plan = resoudre(avec, CONTEXTES, T0, T0, HORIZON_FIN, GRANULARITE)
    assert plan.blocs, "plan vide ({}) : rien a comparer".format(plan.statut)
    return plan


def _reecrire(taches, plan):
    """Ce que fera `--ecrire-due` : poser les dates calculees ET leur trace."""
    calculees = dues_calculees(plan, taches)
    return [marquer_calculee(t, calculees[t.uuid])
            if t.uuid in calculees else t for t in taches]


def _empreinte(plan):
    return tuple(sorted((b.uuid, b.debut, b.fin) for b in plan.blocs))


def test_deux_executions_successives_rendent_le_meme_plan():
    """Stabilite : replanifier apres avoir ecrit ne deplace rien."""
    plan1 = _planifier(chaine(), ECHEANCE)
    plan2 = _planifier(_reecrire(chaine(), plan1), ECHEANCE)
    assert _empreinte(plan2) == _empreinte(plan1)


def test_une_troisieme_execution_ne_derive_pas_davantage():
    """Une derive lente ne se voit pas sur deux runs. On en fait trois."""
    plan1 = _planifier(chaine(), ECHEANCE)
    taches2 = _reecrire(chaine(), plan1)
    plan2 = _planifier(taches2, ECHEANCE)
    plan3 = _planifier(_reecrire(taches2, plan2), ECHEANCE)
    assert _empreinte(plan3) == _empreinte(plan1)


def test_reculer_l_echeance_relache_le_plan():
    """LE test qui justifie tout le mecanisme.

    L'utilisateur recule l'echeance du projet de deux mois dans
    `echeances.json`. Le plan doit suivre. Sans `duePlanif`, les `due` ecrites
    au run precedent seraient prises pour des engagements humains, la regle
    « un due propre prime » les preserverait, et le plan resterait colle a
    decembre -- sans qu'aucune erreur ne soit signalee nulle part.
    """
    plan1 = _planifier(chaine(), ECHEANCE)
    apres_ecriture = _reecrire(chaine(), plan1)

    plan2 = _planifier(apres_ecriture, ECHEANCE_RECULEE)

    fin1 = max(f for _, f in plan1.instants(U_MONTAGE))
    fin2 = max(f for _, f in plan2.instants(U_MONTAGE))
    assert fin2 > fin1, (
        "le plan n'a pas suivi l'echeance reculee : il est reste au {} "
        "alors que l'echeance est passee au {}".format(fin1, ECHEANCE_RECULEE))
    assert fin2.date() >= datetime(2027, 2, 1).date()


def test_une_due_posee_a_la_main_survit_a_la_replanification():
    """Le revers : ce qui vient de l'utilisateur ne doit JAMAIS etre efface.

    Une date posee a la main n'a pas de `due_planif` correspondant ; elle n'est
    donc pas reconnue comme notre sortie, et l'oubli ne la touche pas.
    """
    engagement = datetime(2026, 11, 20, 17, 0)
    taches = [t if t.uuid != U_COMMANDE else
              Tache(uuid=t.uuid, description=t.description, projet=t.projet,
                    estimated=t.estimated, depends=t.depends, tags=t.tags,
                    contexte=t.contexte, due=engagement)
              for t in chaine()]

    survivantes = oublier_dues_calculees(taches)
    par_uuid = {t.uuid: t for t in survivantes}
    assert par_uuid[U_COMMANDE].due == engagement

    plan = _planifier(taches, ECHEANCE)
    assert max(f for _, f in plan.instants(U_COMMANDE)) <= engagement
