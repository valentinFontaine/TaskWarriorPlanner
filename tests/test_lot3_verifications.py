"""Tests du lot 3 : pre-verifications, avant tout appel au solveur.

Aucun Taskwarrior, aucun reseau, aucun ortools. `maintenant` est toujours
fige et injecte : jamais d'appel a datetime.now() ici ni dans le code teste.
"""
from datetime import datetime, timedelta, timezone

import pytest

from planif.config import charger_config
from planif.modele import Contexte, Creneau, Tache

MAINTENANT = datetime(2026, 9, 21, 9, 0, 0)  # figé, cf. "Aujourd'hui" = 2026-09-21


def _config_reelle():
    """Charge la vraie config.json (grilles reelles pro/perso)."""
    return charger_config()


def _tache(uuid, description, **kwargs):
    kwargs.setdefault("contexte", "pro")
    return Tache(uuid=uuid, description=description, **kwargs)


# ---------------------------------------------------------------------------
# 1. Cas nominal
# ---------------------------------------------------------------------------

def test_cas_nominal_aucune_anomalie():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("u1", "Ecrire la spec", estimated=timedelta(hours=2),
               due=MAINTENANT + timedelta(days=5)),
        _tache("u2", "Relire la spec", estimated=timedelta(hours=1),
               due=MAINTENANT + timedelta(days=6), depends=("u1",)),
    ]
    assert pre_verifications(taches, config.contextes, MAINTENANT) == []


# ---------------------------------------------------------------------------
# 2 et 3. insecable-trop-longue
# ---------------------------------------------------------------------------

def test_insecable_trop_longue():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    # Plus longue plage contigue du contexte pro (config.json reel) : 14:00-18:30,
    # soit 4h30. Une tache insecable de 8h ne peut donc tenir en un seul bloc.
    taches = [
        _tache("u1", "Gros bloc indivisible", estimated=timedelta(hours=8),
               tags=("insecable",)),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.code == "insecable-trop-longue"
    assert a.uuids == ("u1",)
    assert "découp" in a.message
    assert "exceptionnelle" in a.message
    assert "marge" in a.message
    # La duree reelle (8 h) est citee, pas un chiffre en dur.
    assert "8 h" in a.message
    # La plage max reelle (4h30) est citee, pas "6 h" recopie de l'exemple du cdc.
    assert "4 h 30" in a.message


def test_insecable_qui_tient_ne_produit_aucune_anomalie():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("u1", "Bloc indivisible qui tient", estimated=timedelta(hours=4),
               tags=("insecable",)),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    assert anomalies == []


# ---------------------------------------------------------------------------
# 4 et 5. cycle-dependances
# ---------------------------------------------------------------------------

def test_cycle_dependances_nomme_le_cycle():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("a", "Tache Alpha", depends=("b",)),
        _tache("b", "Tache Beta", depends=("c",)),
        _tache("c", "Tache Gamma", depends=("a",)),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    cycles = [an for an in anomalies if an.code == "cycle-dependances"]
    assert len(cycles) == 1
    message = cycles[0].message
    assert "Tache Alpha" in message
    assert "Tache Beta" in message
    assert "Tache Gamma" in message


def test_dependance_vers_uuid_absent_pas_de_cycle():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("a", "Tache seule", depends=("uuid-termine-et-absent",)),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    assert not any(an.code == "cycle-dependances" for an in anomalies)


# ---------------------------------------------------------------------------
# 6 et 7. due-depassee
# ---------------------------------------------------------------------------

def test_due_depassee_liste_seulement_les_taches_en_retard():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("u1", "En retard 1", due=MAINTENANT - timedelta(days=1)),
        _tache("u2", "En retard 2", due=MAINTENANT - timedelta(hours=1)),
        _tache("u3", "A l'heure", due=MAINTENANT + timedelta(days=1)),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    dues = [an for an in anomalies if an.code == "due-depassee"]
    assert len(dues) == 1
    assert set(dues[0].uuids) == {"u1", "u2"}
    assert "En retard 1" in dues[0].message
    assert "En retard 2" in dues[0].message
    assert "A l'heure" not in dues[0].message


def test_due_depassee_avec_due_aware_et_maintenant_naif():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    # `due` aware (comme exporte par Taskwarrior, en UTC), `maintenant` naif.
    due_aware_passee = (MAINTENANT - timedelta(days=1)).replace(tzinfo=timezone.utc)
    taches = [
        _tache("u1", "Due aware en retard", due=due_aware_passee),
    ]
    # Ne doit pas lever d'exception.
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    dues = [an for an in anomalies if an.code == "due-depassee"]
    assert len(dues) == 1
    assert dues[0].uuids == ("u1",)


# ---------------------------------------------------------------------------
# 8. externe-sans-estimated
# ---------------------------------------------------------------------------

def test_externe_sans_estimated():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("u1", "Commande fournisseur sans delai", tags=("externe",),
               estimated=None),
        _tache("u2", "Commande fournisseur avec delai", tags=("externe",),
               estimated=timedelta(days=3)),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    externes = [an for an in anomalies if an.code == "externe-sans-estimated"]
    assert len(externes) == 1
    assert externes[0].uuids == ("u1",)
    assert "délai fournisseur non renseigné" in externes[0].message
    assert "Commande fournisseur sans delai" in externes[0].message
    assert "Commande fournisseur avec delai" not in externes[0].message


# ---------------------------------------------------------------------------
# 9. sans-contexte
# ---------------------------------------------------------------------------

def test_sans_contexte():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("u1", "Sans contexte du tout", contexte=None),
        _tache("u2", "Contexte inconnu", contexte="inconnu"),
        _tache("u3", "Contexte connu", contexte="pro"),
    ]
    anomalies = pre_verifications(taches, config.contextes, MAINTENANT)
    sans_ctx = [an for an in anomalies if an.code == "sans-contexte"]
    assert len(sans_ctx) == 1
    assert set(sans_ctx[0].uuids) == {"u1", "u2"}


# ---------------------------------------------------------------------------
# 10. plusieurs anomalies a la fois + determinisme
# ---------------------------------------------------------------------------

def test_plusieurs_anomalies_et_ordre_deterministe():
    from planif.verifications import pre_verifications

    config = _config_reelle()
    taches = [
        _tache("u1", "En retard", due=MAINTENANT - timedelta(days=1)),
        _tache("u2", "Externe sans delai", tags=("externe",), estimated=None),
        _tache("u3", "Sans contexte", contexte=None),
    ]
    anomalies_1 = pre_verifications(taches, config.contextes, MAINTENANT)
    anomalies_2 = pre_verifications(taches, config.contextes, MAINTENANT)

    assert len(anomalies_1) == 3
    codes = {an.code for an in anomalies_1}
    assert codes == {"due-depassee", "externe-sans-estimated", "sans-contexte"}
    assert anomalies_1 == anomalies_2


# ---------------------------------------------------------------------------
# 11. aucun import d'ortools
# ---------------------------------------------------------------------------

def test_aucun_import_ortools_dans_le_source():
    """Assertion la plus honnete : on inspecte directement le texte source,
    ce qui prouve qu'aucun `import ortools` (ni `from ortools import`) n'existe,
    sans dependre de la presence ou non du paquet dans l'environnement de test.
    """
    import inspect

    import planif.verifications as verifications

    source = inspect.getsource(verifications)
    assert "ortools" not in source


def test_module_importable_sans_ortools_installe(monkeypatch):
    """Complement : le module s'importe encore si `ortools` est retire de
    sys.modules et bloque, prouvant qu'il n'est pas requis a l'execution.
    """
    import builtins
    import importlib
    import sys

    reel_import = builtins.__import__

    def import_bloque(name, *args, **kwargs):
        if name == "ortools" or name.startswith("ortools."):
            raise ImportError("ortools bloque pour ce test")
        return reel_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_bloque)
    for mod in list(sys.modules):
        if mod == "ortools" or mod.startswith("ortools."):
            monkeypatch.delitem(sys.modules, mod)
    monkeypatch.delitem(sys.modules, "planif.verifications", raising=False)

    importlib.import_module("planif.verifications")
