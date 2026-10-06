"""Contrat : tout predecesseur (direct ou transitif) d'une tache DATEE doit
etre planifie en PASSE 1, precedence respectee -- jamais laisse en passe 2.

## Le defaut (diagnostique dans planif/__main__.py)

    taches_datees = [t for t in taches if t.due is not None]

Seules les taches qui portent elles-memes un `due` entrent en passe 1
(`planif/__main__.py`, juste avant l'appel a `resoudre`). Un predecesseur NON
date d'une tache datee part donc en passe 2 (regime opportuniste), meme si
`planif/tampon.py::limites_effectives` sait deja tres bien lui heriter une
limite depuis ses successeurs -- cette fonction n'est simplement jamais
appelee sur lui, puisqu'il n'entre jamais dans la liste passee a `resoudre`.

Consequence concrete, verifiee ci-dessous :

- passe 1 pose `debut(successeur) >= fin(predecesseur)` uniquement quand le
  predecesseur est LUI-MEME dans le modele de la passe 1
  (`planif/solveur.py`, contrainte 6 -- `if predecesseur in fins`). Un
  predecesseur non date n'y est jamais, donc rien ne l'y contraint.
- passe 2 pose la precedence uniquement pour les taches qui sont ELLES-MEMES
  candidates de la passe 2 (`planif/solveur.py::completer`, meme motif). Le
  successeur DATE n'est pas une candidate de la passe 2 (il est deja fige par
  la passe 1) : sa dependance vers un predecesseur non date n'est donc jamais
  relue, dans aucune des deux passes.
- les taches `+external` non datees sont en plus explicitement ecartees de la
  passe 2 (`planif/solveur.py`, ~ligne 831 : `if tache.externe: continue`,
  "un delai fournisseur n'est pas du travail opportuniste"). Un `+external`
  non date n'apparait donc dans AUCUNE des deux passes : il est absent du
  plan.

## Le contrat attendu

Tout predecesseur, direct ou transitif, d'une tache datee doit etre planifie
COMME une tache datee (passe 1), avec pour limite celle heritee de ses
successeurs (`limites_effectives` sait deja le faire -- il faut juste lui
donner ces taches en entree). La precedence doit etre respectee. Une tache
non datee SANS successeur date reste en regime opportuniste (passe 2) : ceci
n'est PAS a changer, et le test 4 en est le garde-fou.

## Ce que la sortie expose, et qui sert de verdict

`planif/sortie.py::plan_en_dict` : chaque tache porte un champ `due` --
non-None si au moins un de ses blocs est place par la passe 1 (docstring de
`plan_en_dict`), None si elle n'est placee QUE par la passe 2. Chaque bloc
porte en plus, explicitement, `opportuniste` (bool). Ce sont ces deux champs
qui servent de verdict "opportuniste ou non" ci-dessous -- jamais un
recalcul local.

## Comment chaque cas est rendu contraignant (pas de precedence "par chance")

Grille `pro` reduite a un SEUL creneau de 2 h, le vendredi (`freeTimeHours`
mis a 0 pour que ce creneau ne soit pas ronge par la marge quotidienne). La
tache datee choisit pour `due` le TOUT PREMIER vendredi a venir : il n'existe
donc, dans tout l'horizon, structurellement AUCUNE capacite `pro` avant cette
echeance. Sous le code actuel, le(s) predecesseur(s) non date(s) ne peuvent
donc physiquement pas se placer avant le successeur -- ils sont repousses au
premier creneau libre APRES, un vendredi ULTERIEUR. Ce n'est jamais un hasard
de tri : c'est la seule capacite qui existe.
"""
from datetime import datetime, timedelta

from tests.test_nuit3_chemins import (
    RACINE,
    UUID_A,
    _config_base,
    _ecrire,
    _jour_a_venir,
    _lancer,
    _tw,
)

UUID_B = "b2b2b2b2-0000-4000-8000-000000000002"
UUID_M = "c3c3c3c3-0000-4000-8000-000000000003"


# --------------------------------------------------------------------------
# outils propres a ce fichier
# --------------------------------------------------------------------------

def _config_vendredi_seul(fenetre="15:00-17:00"):
    """La config de base, grille `pro` reduite au seul vendredi, `fenetre`.

    `freeTimeHours` a 0 : sinon la marge quotidienne (2 h par defaut) rongerait
    integralement une fenetre de 2 h, et meme la tache datee seule ne
    tiendrait plus (contrainte 11, capacite quotidienne en volume).
    """
    config = _config_base()
    for jour in list(config["timeSlots"]["pro"]):
        config["timeSlots"]["pro"][jour] = [fenetre] if jour == "Friday" else []
    config["freeTimeHours"] = 0
    return config


def _tache(uuid, description, heures=None, jours=None, projet="NPD.precedence",
          tags=("pro",), due=None, depends=()):
    tache = {"uuid": uuid, "description": description, "status": "pending",
             "entry": "20260901T080000Z", "project": projet,
             "tags": list(tags)}
    tache["estTime"] = ("P{}D".format(int(jours)) if jours is not None
                        else "PT{}H".format(int(heures)))
    if due is not None:
        tache["due"] = _tw(due)
    if depends:
        tache["depends"] = list(depends)
    return tache


def _plan(base_jetable, tmp_path, config, sortie="p.json"):
    cfg = _ecrire(tmp_path / "config.json", config)
    vide = _ecrire(tmp_path / "echeances.json", {})
    agenda = _ecrire(tmp_path / "reunions.json", [])
    chemin_sortie = tmp_path / sortie
    res = _lancer(base_jetable.env, tmp_path, "--config", str(cfg),
                  "--echeances", str(vide), "--reunions", str(agenda),
                  "--sortie", str(chemin_sortie))
    assert res.returncode == 0, res.stdout + res.stderr
    import json
    return json.loads(chemin_sortie.read_text(encoding="utf-8"))


def _entree(plan, uuid):
    assert uuid in plan["taches"], (
        "{} absent du plan -- blocs presents : {}".format(
            uuid, sorted(plan["taches"])))
    return plan["taches"][uuid]


def _premier_debut(entree):
    return datetime.fromisoformat(entree["blocs"][0]["debut"])


def _dernier_fin(entree):
    return max(datetime.fromisoformat(b["fin"]) for b in entree["blocs"])


def _est_opportuniste(entree):
    """Verdict expose par la sortie (planif/sortie.py::plan_en_dict) : `due`
    vaut None quand la tache n'est placee QUE par la passe 2, et chaque bloc
    porte lui-meme `opportuniste`. On verifie les deux, coherents entre eux."""
    tous_opportunistes = all(b["opportuniste"] for b in entree["blocs"])
    assert (entree["due"] is None) == tous_opportunistes, (
        "incoherence entre le champ due ({!r}) et les blocs opportuniste "
        "({})".format(entree["due"], [b["opportuniste"] for b in entree["blocs"]]))
    return tous_opportunistes


# --------------------------------------------------------------------------
# 1. predecesseur DIRECT d'une tache datee
# --------------------------------------------------------------------------

def test_predecesseur_direct_est_planifie_avant_le_successeur_date(
        base_jetable, tmp_path):
    due = _jour_a_venir(4, 1, 17)   # le TOUT PREMIER vendredi a venir, 17:00
    base_jetable.semer([
        _tache(UUID_A, "A non datee", heures=2),
        _tache(UUID_B, "B datee", heures=2, due=due, depends=(UUID_A,)),
    ])

    plan = _plan(base_jetable, tmp_path, _config_vendredi_seul())

    a = _entree(plan, UUID_A)
    b = _entree(plan, UUID_B)
    assert a["blocs"], "A n'a aucun bloc"
    assert b["blocs"], "B n'a aucun bloc"

    assert _dernier_fin(a) <= _premier_debut(b), (
        "precedence violee : A finit a {}, B commence a {}".format(
            _dernier_fin(a), _premier_debut(b)))
    assert not _est_opportuniste(a), (
        "A ne devrait pas etre opportuniste : c'est un predecesseur direct "
        "d'une tache datee (due={!r})".format(a["due"]))


# --------------------------------------------------------------------------
# 2. chaine TRANSITIVE A <- M <- B (seul B est date)
# --------------------------------------------------------------------------

def test_chaine_transitive_est_planifiee_et_ordonnee(base_jetable, tmp_path):
    due = _jour_a_venir(4, 1, 17)
    base_jetable.semer([
        _tache(UUID_A, "A, tete de chaine", heures=2),
        _tache(UUID_M, "M, intermediaire", heures=2, depends=(UUID_A,)),
        _tache(UUID_B, "B, datee", heures=2, due=due, depends=(UUID_M,)),
    ])

    plan = _plan(base_jetable, tmp_path, _config_vendredi_seul())

    a = _entree(plan, UUID_A)
    m = _entree(plan, UUID_M)
    b = _entree(plan, UUID_B)
    assert a["blocs"] and m["blocs"] and b["blocs"]

    assert _dernier_fin(a) <= _premier_debut(m), (
        "A ({}) n'est pas avant M ({})".format(_dernier_fin(a), _premier_debut(m)))
    assert _dernier_fin(m) <= _premier_debut(b), (
        "M ({}) n'est pas avant B ({})".format(_dernier_fin(m), _premier_debut(b)))
    assert not _est_opportuniste(a)
    assert not _est_opportuniste(m)


# --------------------------------------------------------------------------
# 3. +external non date, predecesseur d'une tache datee
# --------------------------------------------------------------------------

def test_externe_non_date_apparait_et_precede_le_successeur_date(
        base_jetable, tmp_path):
    """Represente comme le fait tests/base_realiste.py : tags=("pro",
    "external"), duree en JOURS (delai calendaire fournisseur, planif/solveur.py
    lot 5). Sa duree (3 jours) tient largement avant l'echeance choisie (le
    2e vendredi a venir), sans faire jouer la capacite `pro` -- l'externe n'en
    consomme aucune, par definition (decision 10)."""
    due = _jour_a_venir(4, 2, 17)   # 2e vendredi : de la place pour 3 jours avant
    base_jetable.semer([
        _tache(UUID_A, "Delai fournisseur", jours=3, tags=("pro", "external")),
        _tache(UUID_B, "Reception, datee", heures=2, due=due, depends=(UUID_A,)),
    ])

    plan = _plan(base_jetable, tmp_path, _config_vendredi_seul())

    a = _entree(plan, UUID_A)
    b = _entree(plan, UUID_B)
    assert a["blocs"], "le delai fournisseur (+external) est absent du plan"
    assert b["blocs"]
    assert all(bloc["externe"] for bloc in a["blocs"])
    assert _dernier_fin(a) <= _premier_debut(b), (
        "le successeur commence ({}) avant la fin du delai fournisseur "
        "({})".format(_premier_debut(b), _dernier_fin(a)))


# --------------------------------------------------------------------------
# 4. temoin : sans successeur date, une tache reste opportuniste
# --------------------------------------------------------------------------

def test_sans_successeur_date_la_tache_reste_opportuniste(base_jetable, tmp_path):
    """Garde-fou contre « tout mettre en passe 1 » : ce test doit rester VERT
    avant ET apres la correction. Grille complete (pas la grille restreinte
    des tests 1-3) : c'est la meme base realiste que `test_nuit3_chemins.py`,
    largement assez de capacite pour placer une tache pro de 2 h dans les 21
    jours de l'horizon opportuniste."""
    base_jetable.semer([_tache(UUID_A, "C, isolee, sans due", heures=2)])

    plan = _plan(base_jetable, tmp_path, _config_base())

    c = _entree(plan, UUID_A)
    assert c["blocs"], "C aurait du etre placee par le regime opportuniste"
    assert _est_opportuniste(c), (
        "C n'a pas de successeur date : elle doit rester opportuniste, "
        "pas partir en passe 1")
