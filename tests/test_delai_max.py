"""Contrat de test -- delai maximal entre deux taches (design.md §5, contrainte 9).

Besoin de l'utilisateur, 2026-10-17 : « vernir au plus 2 h apres la fin du
poncage ». UDA `delaiMax` (duree) sur la tache qui attend, appliquee a chacune
de ses `depends` : debut(B) - fin(A) <= delai, en heures d'HORLOGE. En SOUPLE
(decision de l'utilisateur) : le depassement est penalise, jamais interdit, et
chaque paire en depassement est signalee par un avertissement qui la nomme.

Chaque scenario a son temoin sans `delai_max`, qui montre que l'ecart serait
au-dela du delai : sans lui, un test vert ne prouverait rien.
Horloge figee : aucun `datetime.now()`.
"""
import logging
from datetime import datetime, timedelta

import pytest

from planif import taskwarrior
from planif.modele import Contexte, Creneau, Reunion, Tache
from planif.solveur import completer, resoudre

T0 = datetime(2026, 10, 5, 0, 0)          # lundi, minuit
MAINTENANT = datetime(2026, 10, 5, 8, 0)  # lundi 08:00
GRANULARITE = timedelta(minutes=30)
HORIZON_FIN = T0 + timedelta(days=21)

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

UUID_A = "aaaaaaaa-0000-0000-0000-00000000000a"   # poncer
UUID_B = "bbbbbbbb-0000-0000-0000-00000000000b"   # vernir, attend A

DEUX_H = timedelta(hours=2)


def _jour(j, h, m=0):
    return T0 + timedelta(days=j, hours=h, minutes=m)


def _a(**kw):
    kw.setdefault("estimated", timedelta(hours=1))
    return Tache(uuid=UUID_A, description="poncer", contexte="ctxA", **kw)


def _b(delai_max, **kw):
    kw.setdefault("estimated", timedelta(hours=1))
    return Tache(uuid=UUID_B, description="vernir", contexte="ctxA",
                 depends=(UUID_A,), delai_max=delai_max, **kw)


def _ecart(plan):
    assert plan.debut(UUID_A) is not None and plan.debut(UUID_B) is not None
    return plan.debut(UUID_B) - plan.fin(UUID_A)


# --- passe 1 : « au plus tard » ecarte A et B sans le delai -----------------
# B due vendredi 13:00 ; vendredi 9:00-12:00 occupe. Au plus tard : A jeudi
# 12-13, B vendredi 12-13 -> 23 h d'ecart. Avec le delai : A et B le jeudi.
REUNIONS_P1 = (Reunion(titre="occupe", debut=_jour(4, 9), fin=_jour(4, 12)),)


def _passe1(delai_max):
    return resoudre([_a(), _b(delai_max, due=_jour(4, 13))], CONTEXTES_A, T0,
                    MAINTENANT, HORIZON_FIN, GRANULARITE, reunions=REUNIONS_P1)


def test_passe1_temoin_sans_delai_ecart_au_dela():
    plan = _passe1(None)
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert _ecart(plan) > DEUX_H


def test_passe1_delai_tenu():
    plan = _passe1(DEUX_H)
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert timedelta(0) <= _ecart(plan) <= DEUX_H
    assert plan.retard_total == 0   # le delai ne s'achete pas avec du retard


# --- passe 2 : « au plus tot » pose A tout de suite, B attend ---------------
# Lundi 10:00-13:00 et mardi occupes : sans delai, A lundi 9-10 (urgente), B
# mercredi 9-10. Avec le delai, A recule au mercredi pour coller a B.
REUNIONS_P2 = (Reunion(titre="occupe lundi", debut=_jour(0, 10), fin=_jour(0, 13)),
               Reunion(titre="occupe mardi", debut=_jour(1, 0), fin=_jour(2, 0)))


def _passe2(delai_max):
    plan1 = resoudre([], CONTEXTES_A, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
                     reunions=REUNIONS_P2)
    return completer(plan1, [_a(urgency=20.0), _b(delai_max, urgency=1.0)],
                     CONTEXTES_A, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
                     reunions=REUNIONS_P2)


def test_passe2_temoin_sans_delai_ecart_au_dela():
    assert _ecart(_passe2(None)) > DEUX_H


def test_passe2_delai_tenu():
    assert timedelta(0) <= _ecart(_passe2(DEUX_H)) <= DEUX_H


# --- un delai intenable ne rend pas le plan infaisable, et il est nomme -----
# A dure 4 h insecable : elle remplit une journee, B ne peut commencer que le
# lendemain 9:00 -- au moins 20 h apres. Delai 1 h : intenable.

def test_delai_intenable_reste_souple_et_nomme_la_paire(caplog):
    taches = [_a(estimated=timedelta(hours=4), tags=("nosplit",)),
              _b(timedelta(hours=1), due=_jour(9, 13))]
    with caplog.at_level(logging.WARNING, logger="planif.solveur"):
        plan = resoudre(taches, CONTEXTES_A, T0, MAINTENANT, HORIZON_FIN,
                        GRANULARITE)
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert _ecart(plan) > timedelta(hours=1)
    messages = [r.getMessage() for r in caplog.records
                if "delai" in r.getMessage().lower()]
    assert any("poncer" in m and "vernir" in m for m in messages), messages


def test_delai_tenu_ne_signale_rien(caplog):
    with caplog.at_level(logging.WARNING, logger="planif.solveur"):
        _passe1(DEUX_H)
    assert not [r for r in caplog.records
                if "delai" in r.getMessage().lower()]


# --- lecture de l'UDA -------------------------------------------------------

@pytest.mark.parametrize("brut, attendu", [
    ("PT2H", timedelta(hours=2)),
    ("PT30M", timedelta(minutes=30)),
    (None, None),
])
def test_charger_taches_lit_delai_max(monkeypatch, brut, attendu):
    tache = {"uuid": UUID_B, "description": "vernir", "status": "pending"}
    if brut is not None:
        tache["delaiMax"] = brut
    monkeypatch.setattr(taskwarrior, "exporter", lambda filtre, env=None: [tache])
    (lue,) = taskwarrior.charger_taches()
    assert lue.delai_max == attendu
