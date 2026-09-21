"""Lot 1 — calendrier disponible : disponibilite(contexte, jour) = grille - reunions
- marge_jour (design.md §3).

Aucune commande Taskwarrior ici : ce lot ne travaille que sur des objets en memoire
(Contexte, Creneau, Reunion) et sur `config.json` via `charger_config()`.
"""
from datetime import date, datetime, timedelta

import pytest

from planif.calendrier import (
    Disponibilite,
    Plage,
    disponibilite,
    indice_creneau,
    instant_creneau,
    plus_grande_plage,
)
from planif.config import charger_config
from planif.modele import Contexte, Creneau, Reunion

# --------------------------------------------------------------------------
# contextes de reference
# --------------------------------------------------------------------------

CFG = charger_config()
PRO = CFG.contextes["pro"]        # grille reelle : 08:30-12:00, 14:00-18:30 ; marge 2h
PERSO = CFG.contextes["perso"]    # grille reelle : 07:00-08:00, 18:40-19:30 ; marge 30min

LUNDI = date(2026, 9, 21)   # un lundi (verifie ci-dessous)
SAMEDI = date(2026, 9, 26)
DIMANCHE = date(2026, 9, 27)

T0 = datetime(2026, 9, 21, 0, 0)  # minuit du lundi de reference
G30 = timedelta(minutes=30)
G15 = timedelta(minutes=15)


def test_jours_de_reference_sont_corrects():
    assert LUNDI.weekday() == 0
    assert SAMEDI.weekday() == 5
    assert DIMANCHE.weekday() == 6


# --------------------------------------------------------------------------
# 1. journee pleine
# --------------------------------------------------------------------------

def test_journee_pleine_pro():
    disp = disponibilite(PRO, LUNDI, T0, G30)
    assert len(disp.plages) == 2
    assert disp.plages[0].longueur == 7   # 08:30-12:00 = 3h30 = 7 creneaux de 30 min
    assert disp.plages[1].longueur == 9   # 14:00-18:30 = 4h30 = 9 creneaux de 30 min
    total = sum(p.longueur for p in disp.plages)
    assert total == 16
    assert disp.capacite == 16 - 4   # marge 2h = 4 creneaux de 30 min
    assert disp.capacite == 12


# --------------------------------------------------------------------------
# 2. reunion a cheval sur deux creneaux
# --------------------------------------------------------------------------

def test_reunion_a_cheval_sur_deux_creneaux():
    reunion = Reunion(
        titre="reunion test",
        debut=datetime(2026, 9, 21, 10, 15),
        fin=datetime(2026, 9, 21, 11, 15),
    )
    disp = disponibilite(PRO, LUNDI, T0, G30, reunions=(reunion,))

    # la plage du matin (08:30-12:00, 7 creneaux) est coupee en deux par
    # l'occupation des creneaux 10:00-10:30, 10:30-11:00, 11:00-11:30 (3 creneaux,
    # tous partiellement couverts donc entierement occupes).
    plages_matin = [p for p in disp.plages if p.debut < indice_creneau(T0, datetime(2026, 9, 21, 12, 0), G30)]
    assert len(plages_matin) == 2

    total_sans_reunion = 16
    total_avec_reunion = sum(p.longueur for p in disp.plages)
    assert total_sans_reunion - total_avec_reunion == 3


# --------------------------------------------------------------------------
# 3. reunion coupant une plage en deux : verification explicite du nombre de Plage
# --------------------------------------------------------------------------

def test_reunion_coupe_une_plage_en_deux_plages_distinctes():
    reunion = Reunion(
        titre="reunion test",
        debut=datetime(2026, 9, 21, 10, 15),
        fin=datetime(2026, 9, 21, 11, 15),
    )
    disp = disponibilite(PRO, LUNDI, T0, G30, reunions=(reunion,))
    assert len(disp.plages) == 3   # matin coupe en 2 + apres-midi intact = 3
    debut_09h = indice_creneau(T0, datetime(2026, 9, 21, 9, 0), G30)
    fin_09h30 = indice_creneau(T0, datetime(2026, 9, 21, 10, 0), G30)
    assert disp.plages[0].debut == indice_creneau(T0, datetime(2026, 9, 21, 8, 30), G30)
    assert disp.plages[0].fin == indice_creneau(T0, datetime(2026, 9, 21, 10, 0), G30)
    assert disp.plages[1].debut == indice_creneau(T0, datetime(2026, 9, 21, 11, 30), G30)
    assert disp.plages[1].fin == indice_creneau(T0, datetime(2026, 9, 21, 12, 0), G30)


# --------------------------------------------------------------------------
# 4. week-end vide
# --------------------------------------------------------------------------

@pytest.mark.parametrize("jour", [SAMEDI, DIMANCHE])
def test_weekend_vide_en_pro(jour):
    disp = disponibilite(PRO, jour, T0, G30)
    assert disp.plages == ()
    assert disp.capacite == 0


# --------------------------------------------------------------------------
# 5. marge superieure a la grille -> capacite = 0, jamais negative
# --------------------------------------------------------------------------

def test_marge_superieure_a_la_grille_rend_zero():
    # contexte synthetique (donc explicitement fabrique, pas une grille "realiste") :
    # une seule petite plage de 1h le lundi, avec une marge de 8h, tres superieure
    # au total disponible du jour.
    contexte_synthetique = Contexte(
        nom="synthetique_marge",
        contexte_tw="synthetique_marge",
        bloc_min=timedelta(hours=1),
        marge_jour=timedelta(hours=8),
        grille={0: (Creneau(9 * 60, 10 * 60),)},   # lundi 09:00-10:00 seulement
    )
    disp = disponibilite(contexte_synthetique, LUNDI, T0, G30)
    assert disp.capacite >= 0
    assert disp.capacite == 0


# --------------------------------------------------------------------------
# 6. granularite 15 min
# --------------------------------------------------------------------------

def test_granularite_15_min_double_les_comptes():
    disp = disponibilite(PRO, LUNDI, T0, G15)
    total = sum(p.longueur for p in disp.plages)
    assert total == 32
    assert disp.capacite == 24


# --------------------------------------------------------------------------
# 7. alignement qui retrecit (perso : 18:40-19:30 -> 19:00-19:30 avec g=30min)
# --------------------------------------------------------------------------

def test_alignement_retrecit_vers_l_interieur():
    disp = disponibilite(PERSO, LUNDI, T0, G30)
    assert len(disp.plages) == 2
    seconde_plage = disp.plages[1]
    assert seconde_plage.longueur == 1
    debut_attendu = indice_creneau(T0, datetime(2026, 9, 21, 19, 0), G30)
    fin_attendue = indice_creneau(T0, datetime(2026, 9, 21, 19, 30), G30)
    assert seconde_plage.debut == debut_attendu
    assert seconde_plage.fin == fin_attendue
    assert seconde_plage.longueur != 2


# --------------------------------------------------------------------------
# 8. indice_creneau / instant_creneau
# --------------------------------------------------------------------------

def test_indice_et_instant_sont_inverses():
    for indice in (0, 1, 5, 20, 100):
        instant = instant_creneau(T0, indice, G30)
        assert indice_creneau(T0, instant, G30) == indice


def test_indice_creneau_est_un_plancher():
    a = indice_creneau(T0, datetime(2026, 9, 21, 10, 0), G30)
    b = indice_creneau(T0, datetime(2026, 9, 21, 10, 29), G30)
    assert a == b


# --------------------------------------------------------------------------
# 9. plus_grande_plage
# --------------------------------------------------------------------------

def test_plus_grande_plage_rend_la_plus_longue_pas_la_premiere_ni_la_somme():
    # pro un lundi normal : plages de 7 et 9 creneaux -> la plus grande est 9,
    # ni la premiere (7) ni la somme (16).
    plus_grande = plus_grande_plage(PRO, LUNDI, T0, G30)
    assert plus_grande == 9
    assert plus_grande != 7
    assert plus_grande != 16


def test_plus_grande_plage_zero_si_jour_ferme():
    assert plus_grande_plage(PRO, SAMEDI, T0, G30) == 0
