"""La regle « echeance de projet -> taches » vit en UN SEUL endroit.

C'est la question n° 1 laissee ouverte par RAPPORT-NUIT.md. Tant qu'elle n'est
pas tranchee par l'utilisateur, ce qui compte est qu'elle soit **isolee** : un
seul point du code a changer le jour ou la reponse arrive.

Ces tests verifient la regle actuelle ET son isolation.
"""
from datetime import datetime, timedelta

from planif.echeances import appliquer_echeances_projet, taches_terminales
from planif.modele import Tache
from tests.cas_reference import ECHEANCE_PROJET, PROJET, UUID_D, chaine

AUTRE = datetime(2026, 10, 30, 17, 0)


def test_la_chaine_de_reference_n_a_qu_une_tache_terminale():
    """A -> B -> C -> D : seule D n'a pas de successeur dans le projet."""
    assert taches_terminales(chaine(), PROJET) == {UUID_D}


def test_l_echeance_se_pose_sur_la_terminale_et_elle_seule():
    """La regle actuelle : l'echeance du projet descend sur les terminales."""
    avec = appliquer_echeances_projet(chaine(), {PROJET: ECHEANCE_PROJET})
    par_uuid = {t.uuid: t for t in avec}
    assert par_uuid[UUID_D].due == ECHEANCE_PROJET
    for tache in avec:
        if tache.uuid != UUID_D:
            assert tache.due is None, \
                "{} a recu une echeance qu'elle ne devrait pas avoir".format(
                    tache.description)


def test_une_branche_courte_n_est_pas_contrainte_sans_raison():
    """Deux branches de longueurs differentes : seules les FEUILLES sont datees.

    C'est l'argument contre la variante « poser l'echeance sur toutes les
    taches du projet » : la branche courte se retrouverait contrainte comme la
    longue, sans raison.
    """
    racine = Tache(uuid="r", description="Racine", projet=PROJET,
                   estimated=timedelta(hours=1), tags=("pro",), contexte="pro")
    courte = Tache(uuid="c", description="Courte", projet=PROJET,
                   estimated=timedelta(hours=1), depends=("r",),
                   tags=("pro",), contexte="pro")
    longue1 = Tache(uuid="l1", description="Longue 1", projet=PROJET,
                    estimated=timedelta(hours=1), depends=("r",),
                    tags=("pro",), contexte="pro")
    longue2 = Tache(uuid="l2", description="Longue 2", projet=PROJET,
                    estimated=timedelta(hours=1), depends=("l1",),
                    tags=("pro",), contexte="pro")

    taches = [racine, courte, longue1, longue2]
    assert taches_terminales(taches, PROJET) == {"c", "l2"}

    avec = appliquer_echeances_projet(taches, {PROJET: ECHEANCE_PROJET})
    par_uuid = {t.uuid: t for t in avec}
    assert par_uuid["r"].due is None
    assert par_uuid["l1"].due is None
    assert par_uuid["c"].due == ECHEANCE_PROJET
    assert par_uuid["l2"].due == ECHEANCE_PROJET


def test_un_due_propre_prime_sur_l_echeance_du_projet():
    """Un engagement explicite n'est jamais ecrase par une echeance heritee."""
    from dataclasses import replace
    taches = [replace(t, due=AUTRE) if t.uuid == UUID_D else t for t in chaine()]
    avec = appliquer_echeances_projet(taches, {PROJET: ECHEANCE_PROJET})
    par_uuid = {t.uuid: t for t in avec}
    assert par_uuid[UUID_D].due == AUTRE


def test_sans_echeance_de_projet_rien_ne_change():
    """Aucun projet reel n'a d'echeance : ce chemin doit etre neutre."""
    avant = chaine()
    apres = appliquer_echeances_projet(avant, {})
    assert [t.due for t in apres] == [t.due for t in avant]


def test_un_projet_inconnu_ne_casse_rien():
    """Une echeance sur un projet absent des taches n'a simplement aucun effet."""
    avec = appliquer_echeances_projet(chaine(), {"projet.inexistant": AUTRE})
    assert all(t.due is None for t in avec)


def test_la_regle_n_est_ecrite_qu_a_un_seul_endroit():
    """Isolation : aucun autre module de planif/ ne reimplemente la regle.

    On cherche la notion de « terminale » ailleurs que dans planif/echeances.py.
    Si un jour un autre module se met a deduire lui-meme ou poser une echeance
    de projet, ce test doit le signaler — c'est precisement ce qu'on veut
    eviter tant que la question n'est pas tranchee.
    """
    from pathlib import Path
    racine = Path(__file__).resolve().parent.parent / "planif"
    coupables = []
    for fichier in racine.glob("*.py"):
        if fichier.name == "echeances.py":
            continue
        texte = fichier.read_text(encoding="utf-8")
        if "taches_terminales" in texte or "appliquer_echeances_projet" in texte:
            coupables.append(fichier.name)
    assert coupables == [], \
        "la regle fuit hors de planif/echeances.py : {}".format(coupables)
