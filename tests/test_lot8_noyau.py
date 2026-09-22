"""Lot 8 — noyau d'insatisfiabilite (design.md §6).

Exigence du cahier des charges : « un conflit construit a la main rend
**exactement** les elements en cause, et rien d'autre » ; un modele faisable ne
rend **aucun** noyau.

Le mot qui compte est *exactement*. Un diagnostic qui nomme tout ne diagnostique
rien : il faut donc verifier les deux moitiés — ce qui est dans le noyau, et ce
qui n'y est pas.

Horloge FIGEE partout (voir `tests/cas_reference.py`).
"""
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from planif.diagnostic import diagnostiquer
from planif.echeances import appliquer_echeances_projet
from planif.modele import Tache
from tests.cas_reference import (CONTEXTE_PRO, CONTEXTES, ECHEANCE_PROJET, PROJET,
                                 GRANULARITE, HORIZON_FIN, MAINTENANT, T0,
                                 UUID_D, chaine)

# Grille du cas de reference : lun-ven 09:00-12:00 et 14:00-17:00, marge 2 h,
# bloc min 2 h. Donc 4 h utiles par jour, et la plus grande plage contigue
# fait 3 h.


def _tache(suffixe, heures, due=None, tags=("pro",), scheduled=None, depends=()):
    return Tache(uuid="88888888-0000-0000-0000-{:012d}".format(suffixe),
                 description="Tache {}".format(suffixe),
                 estimated=timedelta(hours=heures),
                 due=due, scheduled=scheduled, depends=depends,
                 tags=tags, contexte="pro")


# --------------------------------------------------------------------------
# Le cas nominal : rien a signaler
# --------------------------------------------------------------------------

def test_un_modele_faisable_ne_rend_aucun_noyau():
    """Exigence explicite : un modele faisable ne rend AUCUN noyau."""
    taches = appliquer_echeances_projet(chaine(), {PROJET: ECHEANCE_PROJET})
    diag = diagnostiquer(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                         GRANULARITE)
    assert diag.faisable is True
    assert diag.noyau == ()
    assert diag.message == ""
    assert bool(diag) is True


def test_une_charge_qui_tient_largement_est_faisable():
    """Deux taches de 2 h avec une echeance lointaine : aucun conflit."""
    taches = [_tache(1, 2, due=ECHEANCE_PROJET),
              _tache(2, 2, due=ECHEANCE_PROJET)]
    diag = diagnostiquer(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                         GRANULARITE)
    assert diag.faisable is True
    assert diag.noyau == ()


# --------------------------------------------------------------------------
# Un conflit construit a la main
# --------------------------------------------------------------------------

def test_une_echeance_intenable_est_nommee_et_elle_seule():
    """40 h de travail a tenir en deux jours : l'echeance est nommee, et le
    noyau ne contient QUE cette echeance."""
    # 40 h a faire pour mercredi, alors qu'il n'y a que 4 h utiles par jour.
    intenable = _tache(1, 40, due=datetime(2026, 10, 9, 17, 0))
    # ... et une tache saine, avec une echeance lointaine, qui ne doit PAS
    # apparaitre dans le noyau.
    saine = _tache(2, 2, due=ECHEANCE_PROJET)

    diag = diagnostiquer([intenable, saine], CONTEXTES, T0, MAINTENANT,
                         HORIZON_FIN, GRANULARITE)

    assert diag.faisable is False
    genres = {e.genre for e in diag.noyau}
    uuids = {e.uuid for e in diag.noyau}
    assert genres == {"echeance"}
    assert intenable.uuid in uuids
    assert saine.uuid not in uuids, \
        "la tache saine est nommee a tort : le diagnostic accuse trop large"
    assert "Tache 1" in diag.message


def test_le_noyau_nomme_la_tache_figee_qui_bloque():
    """Une tache figee qui occupe la seule place disponible avant l'echeance
    d'une autre : les DEUX elements sont nommes, et rien d'autre."""
    # Le lundi 05/10 : 4 h utiles. Une tache figee de 4 h le prend en entier.
    figee = _tache(1, 4, tags=("pro", "fige"),
                   scheduled=datetime(2026, 10, 5, 9, 0))
    # Une tache de 4 h qui doit finir avant mardi 06/10 : apres tampon, sa
    # limite tombe avant que la figee ne libere quoi que ce soit.
    contrainte = _tache(2, 4, due=datetime(2026, 10, 7, 9, 0))

    diag = diagnostiquer([figee, contrainte], CONTEXTES, T0, MAINTENANT,
                         HORIZON_FIN, GRANULARITE)

    assert diag.faisable is False, "ce conflit devrait etre infaisable"
    genres = {e.genre for e in diag.noyau}
    assert "figee" in genres, \
        "la tache figee n'est pas nommee : noyau = {}".format(diag.message)
    assert "echeance" in genres


def test_le_noyau_nomme_une_tache_insecable_trop_longue():
    """Une tache +insecable de 4 h ne tient dans aucune plage (3 h au plus) :
    c'est elle que le noyau doit nommer."""
    insecable = _tache(1, 4, tags=("pro", "insecable"), due=ECHEANCE_PROJET)

    diag = diagnostiquer([insecable], CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                         GRANULARITE)

    assert diag.faisable is False
    genres = {e.genre for e in diag.noyau}
    assert "insecable" in genres, \
        "le noyau ne nomme pas l'insecable : {}".format(diag.message)
    assert "4 h" in diag.message


# --------------------------------------------------------------------------
# La forme du diagnostic
# --------------------------------------------------------------------------

def test_le_message_est_en_langage_courant():
    """Le noyau se retraduit en une phrase lisible, pas en noms de variables."""
    intenable = _tache(1, 40, due=datetime(2026, 10, 9, 17, 0))
    diag = diagnostiquer([intenable], CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                         GRANULARITE)
    assert diag.faisable is False
    assert diag.message
    # aucun nom de variable interne ne doit fuir dans le message
    for interdit in ("h_ech_", "h_fige_", "BoolVar", "uuid", "88888888"):
        assert interdit not in diag.message, \
            "nom interne dans le message : {}".format(diag.message)


def test_le_diagnostic_est_deterministe():
    """Deux appels sur la meme entree rendent exactement le meme noyau."""
    taches = [_tache(1, 40, due=datetime(2026, 10, 9, 17, 0)),
              _tache(2, 2, due=ECHEANCE_PROJET)]
    a = diagnostiquer(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    b = diagnostiquer(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    assert a.noyau == b.noyau
    assert a.message == b.message


def test_le_diagnostic_n_appelle_pas_le_solveur_de_plan():
    """Le diagnostic est un modele a part : les echeances y sont DURES, alors
    qu'elles sont souples dans planif/solveur.py. C'est ce qui fait qu'il rend
    INFEASIBLE la ou `resoudre` rendrait un plan en retard."""
    from planif.solveur import resoudre
    intenable = _tache(1, 40, due=datetime(2026, 10, 9, 17, 0))

    plan = resoudre([intenable], CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                    GRANULARITE)
    diag = diagnostiquer([intenable], CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                         GRANULARITE)

    # resoudre place quand meme la tache, en retard
    assert plan.statut != "INFEASIBLE"
    assert plan.retard_total > 0
    assert intenable.uuid in plan.en_retard
    # le diagnostic, lui, dit pourquoi ca ne tient pas
    assert diag.faisable is False
    assert diag.noyau
