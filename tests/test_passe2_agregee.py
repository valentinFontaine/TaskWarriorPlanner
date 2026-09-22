"""La passe 2 sous regime agrege — defaut trouve en branchant l'interface.

Le symptome, constate en ouvrant le calendrier sur un vrai plan : avec un
horizon detaille de deux semaines, `completer` ne placait **aucune** tache non
datee, rendait le plan de la passe 1 a l'identique, et n'en disait rien.

    passe 1 SANS agregation -> 4 blocs opportunistes
    passe 1 AVEC agregation -> 1 paire de blocs qui se chevauchent
                            -> 0 blocs opportunistes
                            -> plan rendu a l'identique : True

Le mecanisme : au-dela de la frontiere, deux blocs d'une meme journee **peuvent
se chevaucher** — c'est documente et voulu (design.md §1, le regime agrege
repond a la journee, pas a l'heure). Mais `completer` versait tous les blocs de
la passe 1 dans `AddNoOverlap` comme constantes. Le modele etait donc
**infaisable des sa construction**, et la fonction retombait sur son
`return plan` de secours : plan inchange, statut inchange, aucun message.

Ce fichier verifie les deux moities de la correction :

1. les blocs **agreges** de la passe 1 ne vont plus dans `AddNoOverlap` — leur
   capacite reste comptee par `charge_figee`, qui travaille en **volume** par
   journee, ce qui est exactement la garantie que le regime agrege promet ;
2. `completer` **dit** combien de candidates il a placees. C'est ce qui
   manquait le plus : un plan qui perd la moitie de son contenu en rendant
   `OPTIMAL` est le pire mode de panne de cet outil.

Horloge figee au lundi 2026-10-05 08:00 (voir `tests/cas_reference.py`).
Trois resolutions au total, en fixtures `scope="module"`.
"""
import logging
from dataclasses import replace
from datetime import timedelta

import pytest

from planif.calendrier import instant_creneau
from planif.modele import Tache
from planif.solveur import completer, resoudre
from tests.cas_reference import (CONTEXTE_PRO, CONTEXTES, ECHEANCE_PROJET,
                                 GRANULARITE, HORIZON_FIN, MAINTENANT, T0,
                                 UUID_D, chaine)

# Frontiere du regime detaille : deux semaines, la valeur par defaut de
# `planif.config.Config.horizon_detaille`. C'est elle qui declenchait le defaut
# des la premiere execution reelle.
HORIZON_DETAILLE_FIN = T0 + timedelta(weeks=2)

# Capacite utile d'une journee ouvree du contexte `pro` du cas de reference :
# grille de 6 h moins 2 h de marge, au creneau de 30 min.
CRENEAUX_PAR_JOUR = 8

UUID_LIBRE_1 = "aaaa1111-0000-0000-0000-000000000001"
UUID_LIBRE_2 = "aaaa2222-0000-0000-0000-000000000002"


def _avec_due_sur_d(taches):
    return [replace(t, due=ECHEANCE_PROJET) if t.uuid == UUID_D else t
            for t in taches]


def _libres():
    """Deux taches sans `due` : elles n'ont leur place qu'en passe 2."""
    return [
        Tache(uuid=UUID_LIBRE_1, description="Relire la doc qualite",
              projet="NPD.divers", estimated=timedelta(hours=2), urgency=9.0,
              tags=("pro",), contexte="pro"),
        Tache(uuid=UUID_LIBRE_2, description="Ranger le labo",
              projet="NPD.divers", estimated=timedelta(hours=2), urgency=1.0,
              tags=("pro",), contexte="pro"),
    ]


@pytest.fixture(scope="module")
def plan_passe1():
    return resoudre(_avec_due_sur_d(chaine()), CONTEXTES, T0, MAINTENANT,
                    HORIZON_FIN, GRANULARITE,
                    horizon_detaille_fin=HORIZON_DETAILLE_FIN)


@pytest.fixture(scope="module")
def plan_complete(plan_passe1):
    return completer(plan_passe1, _libres(), CONTEXTES, T0, MAINTENANT,
                     HORIZON_FIN, GRANULARITE,
                     horizon_detaille_fin=HORIZON_DETAILLE_FIN)


# --------------------------------------------------------------------------
# Le test ne vaut que si la passe 1 produit reellement la situation en cause.
# Sans ce controle, la correction pourrait etre validee par un plan sans aucun
# bloc agrege, c'est-a-dire par un scenario qui n'exerce rien.
# --------------------------------------------------------------------------

def test_la_passe1_produit_bien_des_blocs_agreges_qui_se_chevauchent(plan_passe1):
    agreges = [b for b in plan_passe1.blocs if b.agrege]
    assert agreges, ("le scenario n'exerce rien : la passe 1 n'a produit aucun "
                     "bloc agrege")

    ordonnes = sorted((b for b in plan_passe1.blocs if not b.externe),
                      key=lambda b: b.debut)
    chevauchements = [(a, b) for a, b in zip(ordonnes, ordonnes[1:])
                      if b.debut < a.fin]
    assert chevauchements, ("le scenario n'exerce rien : aucun bloc de la passe 1 "
                            "ne se chevauche, or c'est ce chevauchement qui "
                            "rendait le modele de la passe 2 infaisable")


def test_les_taches_non_datees_sont_placees_malgre_l_agregation(plan_complete):
    """Le defaut lui-meme : zero bloc opportuniste, en silence."""
    opportunistes = [b for b in plan_complete.blocs if b.opportuniste]
    assert opportunistes, ("aucune tache non datee placee : c'est le defaut que "
                           "l'agregation provoquait")

    places = {b.uuid for b in opportunistes}
    assert places == {UUID_LIBRE_1, UUID_LIBRE_2}


def test_la_capacite_quotidienne_reste_respectee(plan_complete):
    """La correction retire une contrainte : elle ne doit pas creer de capacite.

    `AddNoOverlap` ne garde plus les blocs agreges, mais la contrainte de
    **volume** par journee, elle, reste — et c'est exactement la garantie que
    le regime agrege promet. Un jour a plus de huit creneaux signifierait que
    la correction a ouvert une porte au lieu d'en fermer une.
    """
    for jour, creneaux in plan_complete.creneaux_par_jour().items():
        assert creneaux <= CRENEAUX_PAR_JOUR, (
            "le {} porte {} creneaux, soit plus que la journee utile ({})"
            .format(jour, creneaux, CRENEAUX_PAR_JOUR))


def test_la_passe1_ne_bouge_pas_d_un_creneau(plan_passe1, plan_complete):
    """Figee veut dire figee, y compris sous regime agrege."""
    avant = sorted((b.uuid, b.indice, b.debut, b.fin) for b in plan_passe1.blocs)
    apres = sorted((b.uuid, b.indice, b.debut, b.fin)
                   for b in plan_complete.blocs if not b.opportuniste)
    assert apres == avant


def test_completer_dit_combien_de_candidates_il_a_placees(plan_passe1, caplog):
    """Le vrai correctif : que le silence cesse.

    Avec le defaut, `completer` rendait le plan intact sans un mot. Le journal
    doit porter les deux nombres — placees et soumises — pour qu'un plan ampute
    se voie dans la sortie au lieu de passer pour un plan complet.
    """
    with caplog.at_level(logging.INFO, logger="planif.solveur"):
        completer(plan_passe1, _libres(), CONTEXTES, T0, MAINTENANT,
                  HORIZON_FIN, GRANULARITE,
                  horizon_detaille_fin=HORIZON_DETAILLE_FIN)

    messages = [enr.getMessage() for enr in caplog.records]
    assert any("2" in m and "passe 2" in m.lower() for m in messages), (
        "le journal ne dit pas combien de taches la passe 2 a placees : "
        "{}".format(messages))
