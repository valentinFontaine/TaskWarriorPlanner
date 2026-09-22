"""Performance et deux horizons — design.md §1, proposal.md risque n° 1.

    « Deux horizons. Un horizon *detaille* (2 semaines par defaut, reglable) qui
    produit les heures ; un horizon de *faisabilite* couvrant le projet, en
    capacite agregee, qui produit les dates au plus tard. »

Cible mesurable de ce lot, fixee avant de coder :

    100 taches sur un horizon detaille de 2 semaines doivent se resoudre en
    MOINS DE 30 SECONDES, et le cas de reference doit rester OPTIMAL.

Le chiffre obtenu est reporte dans RAPPORT-NUIT-2.md, bon ou mauvais. La regle
est explicite : si la cible n'est pas atteinte, on dit de combien on est loin,
**on ne degrade pas le modele pour y arriver**.

Les 100 taches de ce fichier sont un **banc d'essai synthetique**, pas des
donnees metier : durees et echeances sont engendrees par une formule lisible,
commentee comme telle, et ne pretendent representer aucun projet reel.
"""
import time
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from planif.echeances import appliquer_echeances_projet
from planif.solveur import resoudre
from tests.cas_reference import (CONTEXTES, ECHEANCE_PROJET, GRANULARITE, PROJET,
                                 HORIZON_FIN, MAINTENANT, T0, UUID_C, UUID_D,
                                 chaine)

# La cible, en secondes. Elle est ecrite ici une seule fois.
CIBLE_SECONDES = 30.0
NOMBRE_DE_TACHES = 100

# Horizon detaille : 2 semaines a partir de l'instant courant (design.md §1).
HORIZON_DETAILLE_FIN = MAINTENANT.replace(hour=0, minute=0) + timedelta(weeks=2)


def banc_de_taches(nombre=NOMBRE_DE_TACHES):
    """Engendre `nombre` taches synthetiques en contexte `pro`.

    Le banc doit exercer LES DEUX regimes, sinon il ne mesure rien : un banc
    entierement agrege se resoudrait vite en ne prouvant rien du regime
    detaille, et inversement. Repartition, sans aleatoire (donnees et horloge
    figees, donc mesure reproductible) :

    - **20 taches datees dans l'horizon detaille** -> regime DETAILLE. Elles
      totalisent 30 h pour 40 h utiles sur les 10 jours ouvres des deux
      semaines : ca tient, donc on mesure une resolution reelle et pas une
      infaisabilite.
    - **40 taches portant l'echeance du projet** (bien au-dela) -> regime AGREGE.
    - **40 taches sans echeance** -> regime AGREGE aussi (aucune pression de
      date : elles n'ont pas besoin de l'heure exacte en passe 1).

    Durees : 1 h ou 2 h, de part et d'autre du bloc minimum de 2 h, pour
    exercer les deux branches du decoupage en blocs.

    Ce n'est PAS un jeu de donnees realiste et ca ne pretend pas l'etre.
    """
    from planif.modele import Tache
    # Une echeance dans l'horizon detaille : le vendredi de la premiere
    # semaine, soit le 2026-10-09 a 17:00. Apres tampon, la limite effective
    # tombe plus tot encore, ce qui force bien le regime detaille.
    due_proche = datetime(2026, 10, 16, 17, 0)

    taches = []
    for i in range(nombre):
        heures = 1 if i % 2 else 2
        if i < 20:
            due = due_proche               # -> detaille
        elif i < 60:
            due = ECHEANCE_PROJET          # -> agrege (echeance lointaine)
        else:
            due = None                     # -> agrege (aucune echeance)
        taches.append(Tache(
            uuid="eeeeeeee-0000-0000-0000-{:012d}".format(i),
            description="Banc {}".format(i),
            projet="banc",
            estimated=timedelta(hours=heures),
            due=due,
            tags=("pro",),
            contexte="pro",
        ))
    return taches


def _avec_due_sur_d(taches):
    """Pose l'echeance du projet, via l'UNIQUE point du depot qui porte la regle.

    Voir `planif/echeances.py` : comment une echeance de projet descend sur les
    taches est une question encore ouverte, donc elle est isolee la et nulle
    part ailleurs.
    """
    return appliquer_echeances_projet(taches, {PROJET: ECHEANCE_PROJET})


# --------------------------------------------------------------------------
# La mesure
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mesure_100_taches():
    """Resout le banc de 100 taches et rend (plan, secondes)."""
    taches = banc_de_taches()
    depart = time.perf_counter()
    plan = resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
                    horizon_detaille_fin=HORIZON_DETAILLE_FIN)
    return plan, time.perf_counter() - depart


@pytest.mark.xfail(
    strict=True,
    reason="CIBLE NON ATTEINTE : mesure 60,8 s pour une cible de 30 s. Ce n'est "
           "pas la construction du modele qui coute, c'est la PREUVE "
           "d'optimalite de la passe 2. Diagnostic chiffre : passe 1 "
           "(minimiser le retard) 0,7 s OPTIMAL ; passe 2 (maximiser la somme "
           "des debuts) 60,0 s sans jamais prouver l'optimum, donc FEASIBLE. "
           "Trois pistes essayees, aucune n'a bouge le chiffre : reduction des "
           "domaines a l'union exacte des fenetres, objectif au jour plutot "
           "qu'au creneau pour les blocs agreges, et 8 workers (60,1 s, et le "
           "plan cesse d'etre reproductible). Le modele n'a PAS ete degrade "
           "pour faire passer ce test, et le plafond de 60 s n'a PAS ete "
           "abaisse sous la cible : ce `xfail` strict redeviendra rouge le "
           "jour ou la cible sera reellement atteinte. Voir RAPPORT-NUIT-2.md.")
def test_cent_taches_se_resolvent_sous_la_cible(mesure_100_taches):
    """La cible du lot : 100 taches, horizon detaille 2 semaines, < 30 s.

    Marque `xfail(strict=True)` : la cible n'est pas atteinte, et on refuse de
    l'atteindre en trichant. Le chiffre reel est imprime a chaque execution.
    """
    plan, secondes = mesure_100_taches
    print("\n[MESURE] {} taches, horizon detaille 2 semaines : "
          "{:.1f} s, statut {}".format(NOMBRE_DE_TACHES, secondes, plan.statut))
    assert plan.statut != "INFEASIBLE"
    assert secondes < CIBLE_SECONDES, (
        "{:.1f} s pour {} taches, cible {:.0f} s — depassement de {:.1f} s".format(
            secondes, NOMBRE_DE_TACHES, CIBLE_SECONDES,
            secondes - CIBLE_SECONDES))


def test_cent_taches_sont_toutes_placees(mesure_100_taches):
    """Une resolution rapide qui ne place rien ne prouverait rien."""
    plan, _ = mesure_100_taches
    attendues = banc_de_taches()
    manquantes = [t.description for t in attendues if not plan.blocs_de(t.uuid)]
    assert not manquantes, "taches non planifiees : {}".format(manquantes[:5])
    # conservation de la duree, tache par tache
    for tache in attendues:
        total = sum(b.fin - b.debut
                    for b in plan.blocs_de(tache.uuid)) * GRANULARITE
        assert total == tache.estimated, tache.description


def test_la_capacite_quotidienne_tient_aussi_en_regime_agrege(mesure_100_taches):
    """L'agregation relache les heures, JAMAIS le volume disponible par jour.

    C'est la propriete qui fait qu'un plan agrege reste un plan honnete : on
    perd l'heure exacte, on ne gagne pas de capacite.
    """
    plan, _ = mesure_100_taches
    contexte = CONTEXTES["pro"]
    for jour, occupe in plan.creneaux_par_jour().items():
        assert contexte.est_ouvre(jour), "travail place un jour non ouvre : {}".format(jour)
        assert occupe <= 8, "{} : {} creneaux pour 8 utiles".format(jour, occupe)


# --------------------------------------------------------------------------
# Le cas de reference ne doit pas avoir bouge
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plan_reference_detaille():
    """Cas de reference, horizon detaille non borne : tout est place a l'heure."""
    return resoudre(_avec_due_sur_d(chaine()), CONTEXTES, T0, MAINTENANT,
                    HORIZON_FIN, GRANULARITE)


def test_le_cas_de_reference_reste_optimal(plan_reference_detaille):
    """Sans horizon detaille borne, rien ne change : OPTIMAL et dates exactes."""
    plan = plan_reference_detaille
    assert plan.statut == "OPTIMAL"
    assert plan.retard_total == 0
    assert plan.fin(UUID_D) == datetime(2026, 11, 20, 17, 0)


# --------------------------------------------------------------------------
# Ce que l'agregation garde, et ce qu'elle lache
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plan_reference_agrege():
    """Le meme cas, mais avec un horizon detaille de 2 semaines.

    D tombe alors bien au-dela de l'horizon detaille : il passe en regime
    agrege. On mesure ce qu'on perd et ce qu'on garde.
    """
    return resoudre(_avec_due_sur_d(chaine()), CONTEXTES, T0, MAINTENANT,
                    HORIZON_FIN, GRANULARITE,
                    horizon_detaille_fin=HORIZON_DETAILLE_FIN)


def test_l_agregation_garde_le_bon_JOUR_pour_d(plan_reference_agrege):
    """Les deux horizons s'accordent sur le jour, meme s'ils divergent sur l'heure.

    C'est la promesse du design.md §1 : au-dela de l'horizon detaille on
    repond en dates, pas en heures. Le jour doit rester juste.
    """
    plan = plan_reference_agrege
    assert plan.statut != "INFEASIBLE"
    assert plan.fin(UUID_D).date() == datetime(2026, 11, 20).date()


def test_l_agregation_respecte_encore_le_delai_fournisseur(plan_reference_agrege):
    """Le controle qui compte, meme en agrege : C dure 28 jours calendaires."""
    plan = plan_reference_agrege
    assert plan.fin(UUID_C) - plan.debut(UUID_C) == timedelta(days=28)


def test_l_agregation_ne_cree_pas_de_capacite(plan_reference_agrege):
    """Jamais plus de 4 h utiles par jour, y compris au-dela de l'horizon detaille."""
    for jour, occupe in plan_reference_agrege.creneaux_par_jour().items():
        assert occupe <= 8, "{} : {} creneaux".format(jour, occupe)
