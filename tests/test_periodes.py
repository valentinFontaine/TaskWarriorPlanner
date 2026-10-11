"""Periodes datees : une plage de dates ou certains contextes changent de grille.

Cas d'origine (2026-10-11) : une semaine de vacances, du 24/10 au 01/11 inclus.
Le contexte `pro` tombe a zero et `perso` passe a 09:00-19:00 tous les jours.
Avant ce changement, la grille ne connaissait que les jours de la semaine
(`Contexte.creneaux`) : aucune periode ne pouvait s'exprimer.

Aucun Taskwarrior, aucun ortools : la config est ecrite dans `tmp_path`.
"""
import json
from datetime import date, datetime, timedelta

import pytest

from planif.calendrier import disponibilite
from planif.config import charger_config
from planif.modele import Creneau, Tache

SEMAINE = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TOUS = SEMAINE + ["Saturday", "Sunday"]

GRILLES = {
    "pro": {**{j: ["08:30-12:00", "14:00-18:30"] for j in SEMAINE},
            "Saturday": [], "Sunday": []},
    "perso": {j: ["07:00-08:00", "18:40-19:30"] for j in TOUS},
}

VACANCES = {"nom": "vacances", "debut": "2026-10-24", "fin": "2026-11-01",
            "timeSlots": {"pro": [], "perso": ["09:00-19:00"]}}

VEILLE = date(2026, 10, 23)        # vendredi
PREMIER = date(2026, 10, 24)       # samedi, premier jour
LUNDI_VAC = date(2026, 10, 26)
DERNIER = date(2026, 11, 1)        # dimanche, dernier jour
LENDEMAIN = date(2026, 11, 2)      # lundi
NEUF_DIX_NEUF = (Creneau(9 * 60, 19 * 60),)
G30 = timedelta(minutes=30)


def _config(tmp_path, periodes):
    brut = {"timeSlots": GRILLES, "freeTimeHours": 2}
    if periodes is not None:
        brut["periodes"] = periodes
    chemin = tmp_path / "config.json"
    chemin.write_text(json.dumps(brut), encoding="utf-8")
    return charger_config(chemin)


def test_jours_de_reference():
    assert VEILLE.weekday() == 4
    assert PREMIER.weekday() == 5
    assert LUNDI_VAC.weekday() == 0
    assert DERNIER.weekday() == 6
    assert LENDEMAIN.weekday() == 0


@pytest.mark.parametrize("jour", [PREMIER, LUNDI_VAC, DERNIER])
def test_pendant_la_periode_la_grille_est_remplacee(tmp_path, jour):
    cfg = _config(tmp_path, [VACANCES])
    assert cfg.contextes["pro"].creneaux(jour) == ()
    assert not cfg.contextes["pro"].est_ouvre(jour)
    assert cfg.contextes["perso"].creneaux(jour) == NEUF_DIX_NEUF


@pytest.mark.parametrize("jour", [VEILLE, LENDEMAIN])
def test_hors_periode_la_grille_hebdomadaire_reste(tmp_path, jour):
    cfg = _config(tmp_path, [VACANCES])
    sans = _config(tmp_path, None)
    for nom in ("pro", "perso"):
        assert cfg.contextes[nom].creneaux(jour) == sans.contextes[nom].creneaux(jour)
    assert cfg.contextes["pro"].creneaux(jour) != ()


def test_contexte_absent_de_la_periode_garde_sa_grille(tmp_path):
    periode = {"nom": "stage", "debut": "2026-10-24", "fin": "2026-11-01",
               "timeSlots": {"perso": ["09:00-19:00"]}}
    cfg = _config(tmp_path, [periode])
    sans = _config(tmp_path, None)
    assert cfg.contextes["pro"].creneaux(LUNDI_VAC) == \
        sans.contextes["pro"].creneaux(LUNDI_VAC) != ()
    assert cfg.contextes["perso"].creneaux(LUNDI_VAC) == NEUF_DIX_NEUF


def test_disponibilite_suit_la_periode(tmp_path):
    cfg = _config(tmp_path, [VACANCES])
    t0 = datetime(2026, 10, 26)
    assert disponibilite(cfg.contextes["pro"], LUNDI_VAC, t0, G30).capacite == 0
    perso = disponibilite(cfg.contextes["perso"], LUNDI_VAC, t0, G30)
    assert [p.longueur for p in perso.plages] == [20]   # 10 h
    assert perso.capacite == 20 - 1                     # marge perso 30 min


def test_insecable_qui_tient_dans_une_periode(tmp_path):
    """8 h d'un bloc : impossible en semaine perso (5 h max), possible en vacances."""
    from planif.verifications import pre_verifications

    tache = Tache(uuid="u1", description="Poncer", contexte="perso",
                  estimated=timedelta(hours=8), tags=("nosplit",))
    maintenant = datetime(2026, 10, 11, 9, 0)
    sans = _config(tmp_path, None)
    assert [a.code for a in pre_verifications([tache], sans.contextes, maintenant)] \
        == ["insecable-trop-longue"]
    cfg = _config(tmp_path, [VACANCES])
    assert pre_verifications([tache], cfg.contextes, maintenant) == []


def test_date_illisible_nomme_la_periode(tmp_path):
    with pytest.raises(ValueError, match="vacances"):
        _config(tmp_path, [{**VACANCES, "fin": "1er novembre"}])


def test_debut_apres_fin_refuse(tmp_path):
    with pytest.raises(ValueError, match="vacances"):
        _config(tmp_path, [{**VACANCES, "debut": "2026-11-02"}])
