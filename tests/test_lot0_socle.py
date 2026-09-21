"""Lot 0 — socle : lecture Taskwarrior, modele de donnees, configuration.

Les tests qui touchent Taskwarrior utilisent la fixture `base_jetable` : une base
creee dans le tmp_path du test, jamais celle de l'utilisateur (AGENTS.md §2).
"""
from datetime import datetime, timedelta, timezone

import pytest

from planif.config import charger_config
from planif.duree import ParseDureeErreur, parse_duree
from planif.modele import Creneau, Marqueur, Tache
from planif.taskwarrior import charger_taches, exporter


# --------------------------------------------------------------------------
# duree
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texte,attendu", [
    ("PT4H", timedelta(hours=4)),
    ("PT30M", timedelta(minutes=30)),
    ("PT1H30M", timedelta(hours=1, minutes=30)),
    ("P28D", timedelta(days=28)),
    ("P4W", timedelta(days=28)),
    ("90min", timedelta(minutes=90)),
    ("1.5h", timedelta(hours=1, minutes=30)),
    ("2h", timedelta(hours=2)),
    ("28d", timedelta(days=28)),
    ("30min", timedelta(minutes=30)),
])
def test_parse_duree_formats_valides(texte, attendu):
    assert parse_duree(texte) == attendu


def test_parse_duree_refuse_1h30():
    """AGENTS.md §5 : Taskwarrior rejette `1h30`. On le rejette aussi, plutot que
    de deviner si l'utilisateur voulait 1 h 30 ou 1 h et 30 jours."""
    with pytest.raises(ParseDureeErreur):
        parse_duree("1h30")


def test_parse_duree_refuse_vide():
    with pytest.raises(ParseDureeErreur):
        parse_duree("")


# --------------------------------------------------------------------------
# marqueurs par tags
# --------------------------------------------------------------------------

def test_tags_traduits_en_marqueurs():
    t = Tache(uuid="u", description="x", tags=("pro", "externe", "insecable"))
    assert t.externe is True
    assert t.insecable is True
    assert t.fige is False
    assert t.asap is False
    assert t.marqueurs == frozenset({Marqueur.EXTERNE, Marqueur.INSECABLE})


def test_tag_inconnu_n_est_pas_un_marqueur():
    t = Tache(uuid="u", description="x", tags=("pro", "urgent"))
    assert t.marqueurs == frozenset()


# --------------------------------------------------------------------------
# lecture Taskwarrior
# --------------------------------------------------------------------------

CHAINE = [
    {"uuid": "11111111-1111-1111-1111-111111111111",
     "description": "Faire le plan de la platine élargie", "status": "pending",
     "entry": "20261005T080000Z", "estTime": "PT4H", "project": "NPD.helisides",
     "tags": ["pro"]},
    {"uuid": "22222222-2222-2222-2222-222222222222",
     "description": "Commander chez le fournisseur", "status": "pending",
     "entry": "20261005T080000Z", "estTime": "PT30M", "project": "NPD.helisides",
     "tags": ["pro"], "depends": ["11111111-1111-1111-1111-111111111111"]},
    {"uuid": "33333333-3333-3333-3333-333333333333",
     "description": "Fabrication fournisseur", "status": "pending",
     "entry": "20261005T080000Z", "estTime": "P28D", "project": "NPD.helisides",
     "tags": ["pro", "externe"], "depends": ["22222222-2222-2222-2222-222222222222"]},
    {"uuid": "44444444-4444-4444-4444-444444444444",
     "description": "Tester la pièce reçue", "status": "pending",
     "entry": "20261005T080000Z", "estTime": "PT3H", "project": "NPD.helisides",
     "tags": ["pro"], "due": "20261124T160000Z",
     "depends": ["33333333-3333-3333-3333-333333333333"]},
]


def test_chargement_rend_le_bon_nombre_de_taches(base_jetable):
    base_jetable.semer(CHAINE)
    taches = charger_taches(env=base_jetable.env)
    assert len(taches) == 4


def test_accents_survivent_a_l_aller_retour(base_jetable):
    """AGENTS.md §5 : sans encoding='utf-8' explicite, les accents se corrompent
    sous Windows. Ce test echoue si on l'oublie."""
    base_jetable.semer(CHAINE)
    par_uuid = {t.uuid: t for t in charger_taches(env=base_jetable.env)}
    assert par_uuid["11111111-1111-1111-1111-111111111111"].description == \
        "Faire le plan de la platine élargie"
    assert par_uuid["44444444-4444-4444-4444-444444444444"].description == \
        "Tester la pièce reçue"


def test_champs_metier_traduits(base_jetable):
    base_jetable.semer(CHAINE)
    par_uuid = {t.uuid: t for t in charger_taches(env=base_jetable.env)}
    a = par_uuid["11111111-1111-1111-1111-111111111111"]
    c = par_uuid["33333333-3333-3333-3333-333333333333"]
    d = par_uuid["44444444-4444-4444-4444-444444444444"]

    assert a.estimated == timedelta(hours=4)
    assert a.projet == "NPD.helisides"
    assert a.due is None

    assert c.externe is True
    assert c.estimated == timedelta(days=28)
    assert c.depends == ("22222222-2222-2222-2222-222222222222",)

    # Convention du depot (design.md §2) : tout est naif en heure locale a
    # l'interieur du modele, et la conversion depuis l'UTC de Taskwarrior se
    # fait a la frontiere, dans planif/taskwarrior.py. On attend donc du naif.
    # L'attendu est CALCULE depuis le fuseau de la machine, jamais ecrit en
    # dur : sinon le test ne passerait que sur une machine.
    attendu = (datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc)
               .astimezone().replace(tzinfo=None))
    assert d.due == attendu
    assert d.due.tzinfo is None


def test_exporter_utilise_utf8_explicite(base_jetable):
    """Preuve que le chemin vise est bien exerce : on lit la sortie brute."""
    base_jetable.semer(CHAINE)
    brut = exporter(env=base_jetable.env)
    assert len(brut) == 4
    assert any("élargie" in t["description"] for t in brut)


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

def test_config_reprend_les_grilles_reelles():
    """config.json porte les vraies grilles de mars 2025. On les reprend telles
    quelles, sans en inventer."""
    cfg = charger_config()
    pro = cfg.contextes["pro"]
    assert pro.bloc_min == timedelta(hours=2)          # proposal.md decision 3
    assert pro.marge_jour == timedelta(hours=2)        # config.json freeTimeHours
    # lundi (0) : 08:30-12:00 et 14:00-18:30
    assert pro.grille[0] == (Creneau(8 * 60 + 30, 12 * 60), Creneau(14 * 60, 18 * 60 + 30))
    assert pro.grille[5] == ()                         # samedi vide
    assert pro.grille[6] == ()                         # dimanche vide

    perso = cfg.contextes["perso"]
    assert perso.bloc_min == timedelta(hours=1)        # proposal.md decision 3
    assert perso.marge_jour == timedelta(minutes=30)   # proposal.md decision 11
    assert perso.grille[5] == (Creneau(7 * 60, 12 * 60), Creneau(16 * 60, 18 * 60))


def test_config_granularite_par_defaut():
    cfg = charger_config()
    assert cfg.granularite == timedelta(minutes=30)    # proposal.md decision 1


def test_config_ignore_sleep_et_asso():
    """`sleep` et `asso` sont dans config.json mais ne sont pas des contextes de
    travail du cahier des charges. On ne les invente pas en contextes."""
    cfg = charger_config()
    assert set(cfg.contextes) == {"pro", "perso"}


def test_echeances_de_projet_sont_un_bouchon():
    """Aucune echeance de projet n'existe dans les donnees reelles. Le bouchon doit
    etre explicite et repérable."""
    from planif import stub_echeances
    assert stub_echeances.ECHEANCES_PROJET["NPD.helisides"] == \
        datetime(2026, 11, 24, 17, 0)


def test_reunions_sont_un_bouchon_vide():
    from planif import stub_reunions
    assert stub_reunions.reunions(datetime(2026, 10, 5), datetime(2026, 12, 1)) == ()
