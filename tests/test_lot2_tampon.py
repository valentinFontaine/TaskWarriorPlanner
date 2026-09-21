"""Tests du lot 2 : tampon de securite et derivation des echeances.

design.md §4 :
    echeance_effective(due) :
        t = due - 24 h
        reculer jusqu'a la fin du dernier jour ouvre strictement anterieur a t

Aucun appel a datetime.now() : toutes les dates sont figees en dur dans les tests.
Aucune commande Taskwarrior n'est utilisee ici (AGENTS.md §2 / consignes du lot).
"""
from datetime import date, datetime, timedelta

import pytest

from planif.config import charger_config
from planif.modele import Contexte, Creneau, Tache
from planif.tampon import CycleDependances, echeance_effective, limites_effectives


@pytest.fixture
def contexte_pro():
    """Grille `pro` reelle issue de config.json (lun-ven 08:30-12:00 + 14:00-18:30)."""
    config = charger_config()
    return config.contextes["pro"]


@pytest.fixture
def contexte_pro_17h():
    """Grille synthetique (PAS la grille reelle) : lun-ven 09:00-12:00 + 14:00-17:00,
    week-end vide. Sert uniquement a verifier le cas de reference du projet ou les
    journees finissent a 17:00.
    """
    grille = {
        0: (Creneau(9 * 60, 12 * 60), Creneau(14 * 60, 17 * 60)),
        1: (Creneau(9 * 60, 12 * 60), Creneau(14 * 60, 17 * 60)),
        2: (Creneau(9 * 60, 12 * 60), Creneau(14 * 60, 17 * 60)),
        3: (Creneau(9 * 60, 12 * 60), Creneau(14 * 60, 17 * 60)),
        4: (Creneau(9 * 60, 12 * 60), Creneau(14 * 60, 17 * 60)),
        5: (),
        6: (),
    }
    return Contexte(
        nom="pro_17h",
        contexte_tw="pro",
        bloc_min=timedelta(hours=2),
        marge_jour=timedelta(hours=2),
        grille=grille,
    )


def _tache(uuid, due=None, depends=(), description=None):
    return Tache(uuid=uuid, description=description or uuid, due=due, depends=depends)


# ---------------------------------------------------------------------------
# 1. Les deux exemples de reference du cahier des charges
# ---------------------------------------------------------------------------

def test_exemple_jeudi_14h_vers_mardi_18h30(contexte_pro):
    due = datetime(2026, 11, 12, 14, 0)
    assert due.weekday() == 3  # jeudi
    resultat = echeance_effective(due, contexte_pro)
    attendu = datetime(2026, 11, 10, 18, 30)
    assert attendu.weekday() == 1  # mardi
    assert resultat == attendu


def test_exemple_mardi_8h_vers_vendredi_18h30(contexte_pro):
    due = datetime(2026, 11, 10, 8, 0)
    assert due.weekday() == 1  # mardi
    resultat = echeance_effective(due, contexte_pro)
    attendu = datetime(2026, 11, 6, 18, 30)
    assert attendu.weekday() == 4  # vendredi
    assert resultat == attendu


# ---------------------------------------------------------------------------
# 2. Cas de reference du projet : grille finissant a 17h
# ---------------------------------------------------------------------------

def test_cas_reference_grille_17h(contexte_pro_17h):
    due = datetime(2026, 11, 24, 17, 0)
    assert due.weekday() == 1  # mardi
    resultat = echeance_effective(due, contexte_pro_17h)
    attendu = datetime(2026, 11, 20, 17, 0)
    assert attendu.weekday() == 4  # vendredi
    assert resultat == attendu
    # ni le 24/11 (tampon non applique)
    assert resultat != datetime(2026, 11, 24, 17, 0)
    # ni le 19/11 ou avant (tampon applique deux fois)
    assert resultat > datetime(2026, 11, 19, 23, 59)


# ---------------------------------------------------------------------------
# 3. Le tampon ne s'accumule pas sur une chaine A->B->C->D->E
# ---------------------------------------------------------------------------

def test_tampon_ne_s_accumule_pas_sur_une_chaine(contexte_pro):
    a = _tache("A", depends=())
    b = _tache("B", depends=("A",))
    c = _tache("C", depends=("B",))
    d = _tache("D", depends=("C",))
    e = _tache("E", due=datetime(2026, 11, 12, 14, 0), depends=("D",))

    taches = [a, b, c, d, e]
    contextes = {"pro": contexte_pro}
    # noter : a.depends=() signifie que A n'a pas de predecesseur ; mais le
    # graphe des successeurs est construit a partir de depends de B,C,D,E qui
    # pointent chacun vers le precedent -> A precede B precede C ... precede E.
    limites = limites_effectives(taches, contextes)

    limite_e = echeance_effective(e.due, contexte_pro)
    assert limites["E"] == limite_e
    assert limites["D"] == limite_e
    assert limites["C"] == limite_e
    assert limites["B"] == limite_e
    assert limites["A"] == limite_e


# ---------------------------------------------------------------------------
# 4. Deux due concurrents : le min des deux
# ---------------------------------------------------------------------------

def test_min_de_deux_successeurs_dates(contexte_pro):
    a = _tache("A", depends=())
    b1 = _tache("B1", due=datetime(2026, 11, 12, 14, 0), depends=("A",))
    b2 = _tache("B2", due=datetime(2026, 11, 10, 8, 0), depends=("A",))

    taches = [a, b1, b2]
    contextes = {"pro": contexte_pro}
    limites = limites_effectives(taches, contextes)

    limite_b1 = echeance_effective(b1.due, contexte_pro)
    limite_b2 = echeance_effective(b2.due, contexte_pro)
    assert limites["B1"] == limite_b1
    assert limites["B2"] == limite_b2
    assert limites["A"] == min(limite_b1, limite_b2)
    assert limites["A"] == limite_b2  # b2 est la plus contraignante


# ---------------------------------------------------------------------------
# 5. Une tache avec due ET successeur date plus tot -> min
# ---------------------------------------------------------------------------

def test_min_entre_due_propre_et_successeur(contexte_pro):
    # A a un due propre plus tardif que la limite de son successeur B.
    a = _tache("A", due=datetime(2026, 11, 24, 17, 0), depends=())
    b = _tache("B", due=datetime(2026, 11, 10, 8, 0), depends=("A",))

    taches = [a, b]
    contextes = {"pro": contexte_pro}
    limites = limites_effectives(taches, contextes)

    limite_a_propre = echeance_effective(a.due, contexte_pro)
    limite_b = echeance_effective(b.due, contexte_pro)
    assert limites["B"] == limite_b
    assert limites["A"] == min(limite_a_propre, limite_b)
    assert limites["A"] == limite_b  # b est plus contraignant


# ---------------------------------------------------------------------------
# 6. Sans due et sans successeur date -> None
# ---------------------------------------------------------------------------

def test_sans_due_et_sans_successeur_date(contexte_pro):
    a = _tache("A", depends=())
    b = _tache("B", depends=("A",))  # B n'a pas non plus de due

    taches = [a, b]
    contextes = {"pro": contexte_pro}
    limites = limites_effectives(taches, contextes)

    assert limites["A"] is None
    assert limites["B"] is None


# ---------------------------------------------------------------------------
# 7. Cycle A->B->A leve CycleDependances sans boucler
# ---------------------------------------------------------------------------

def test_cycle_leve_exception(contexte_pro):
    a = _tache("A", depends=("B",))
    b = _tache("B", depends=("A",))

    taches = [a, b]
    contextes = {"pro": contexte_pro}
    with pytest.raises(CycleDependances):
        limites_effectives(taches, contextes)


# ---------------------------------------------------------------------------
# 8. due un lundi -> recul jusqu'au vendredi (pas juste t - 1 jour)
# ---------------------------------------------------------------------------

def test_due_lundi_recule_jusqu_au_vendredi(contexte_pro):
    due = datetime(2026, 11, 9, 10, 0)
    assert due.weekday() == 0  # lundi
    t = due - timedelta(hours=24)
    assert t.weekday() == 6  # dimanche : le jour ouvre precedent n'est pas t - 1 jour
    resultat = echeance_effective(due, contexte_pro)
    attendu = datetime(2026, 11, 6, 18, 30)
    assert attendu.weekday() == 4  # vendredi
    assert resultat == attendu
