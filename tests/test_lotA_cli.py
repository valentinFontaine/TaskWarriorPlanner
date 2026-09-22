"""Lot A — la ligne de commande de l'ordonnanceur (`planif/__main__.py`).

Tous ces tests lancent `python -m planif` en **sous-processus**, sur une base
jetable (`base_jetable`, AGENTS.md §2) ou sans `TASKRC`/`TASKDATA` du tout pour
le controle 1. Aucun ne touche a la vraie base de l'utilisateur, aucun ne va
sur le reseau.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _lancer(env, *args, cwd=None):
    return subprocess.run(
        [PYTHON, "-m", "planif", *args],
        capture_output=True, text=True, encoding="utf-8",
        env=env, cwd=str(cwd or RACINE), check=False,
    )


# --------------------------------------------------------------------------
# 1. Le garde-fou d'isolation, sans base jetable
# --------------------------------------------------------------------------

def test_refuse_sans_taskrc_ni_taskdata():
    """Sans TASKRC ni TASKDATA, la CLI refuse de demarrer et nomme la variable.

    Aucune fixture `base_jetable` ici : c'est precisement le cas qu'on ne veut
    JAMAIS declencher contre la vraie base, donc on construit un environnement
    qui n'a explicitement ni l'un ni l'autre.
    """
    env = dict(os.environ)
    env.pop("TASKRC", None)
    env.pop("TASKDATA", None)

    resultat = _lancer(env)

    assert resultat.returncode != 0
    sortie = resultat.stdout + resultat.stderr
    assert "TASKRC" in sortie


# --------------------------------------------------------------------------
# 2. Le plan JSON, format design.md §7, accents preserves
# --------------------------------------------------------------------------

def test_plan_json_valide_et_accents_survivent(base_jetable, tmp_path):
    base_jetable.semer([
        {"uuid": "11111111-1111-1111-1111-111111111111",
         "description": "Tester la vanne à débit variable", "status": "pending",
         "entry": "20261005T080000Z", "estTime": "PT2H",
         "project": "NPD.exemple", "tags": ["pro"],
         "due": "20270301T170000Z"},
    ])
    sortie = tmp_path / "plan.json"

    resultat = _lancer(base_jetable.env, "--sortie", str(sortie))

    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert sortie.exists()
    donnees = json.loads(sortie.read_text(encoding="utf-8"))

    assert donnees["version"] == 1
    assert donnees["statut"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE")
    assert "t0" in donnees and "granularite_minutes" in donnees

    entree = donnees["taches"]["11111111-1111-1111-1111-111111111111"]
    assert entree["description"] == "Tester la vanne à débit variable"
    for bloc in entree["blocs"]:
        assert bloc["precision"] in ("heure", "jour")
        assert {"externe", "agrege", "opportuniste"} <= bloc.keys()


# --------------------------------------------------------------------------
# 3. Le rapport de pre-verifications, en tete de sortie
# --------------------------------------------------------------------------

def test_rapport_pre_verifications_avant_le_plan(base_jetable, tmp_path):
    base_jetable.semer([
        {"uuid": "22222222-2222-2222-2222-222222222222",
         "description": "Tâche en retard depuis longtemps", "status": "pending",
         "entry": "20200101T080000Z", "estTime": "PT1H",
         "project": "NPD.exemple", "tags": ["pro"],
         "due": "20200102T170000Z"},
    ])
    sortie = tmp_path / "plan.json"

    resultat = _lancer(base_jetable.env, "--sortie", str(sortie))

    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    stdout = resultat.stdout

    assert "=== Pre-verifications ===" in stdout
    assert "due-depassee" in stdout
    assert "Tâche en retard depuis longtemps" in stdout

    pos_rapport = stdout.index("=== Pre-verifications ===")
    pos_resume = stdout.index("=== Resume ===")
    assert pos_rapport < pos_resume, (
        "le rapport de pre-verifications doit apparaitre AVANT le resume/plan")


# --------------------------------------------------------------------------
# 4. --ignorer-due-depassee retire les taches et annonce le compte
# --------------------------------------------------------------------------

def test_ignorer_due_depassee_retire_et_annonce(base_jetable, tmp_path):
    base_jetable.semer([
        {"uuid": "33333333-3333-3333-3333-333333333333",
         "description": "Tâche due dépassée", "status": "pending",
         "entry": "20200101T080000Z", "estTime": "PT1H",
         "project": "NPD.exemple", "tags": ["pro"],
         "due": "20200102T170000Z"},
        {"uuid": "44444444-4444-4444-4444-444444444444",
         "description": "Tâche due future", "status": "pending",
         "entry": "20261005T080000Z", "estTime": "PT1H",
         "project": "NPD.exemple", "tags": ["pro"],
         "due": "20270301T170000Z"},
    ])
    sortie = tmp_path / "plan.json"

    resultat = _lancer(base_jetable.env, "--sortie", str(sortie),
                       "--ignorer-due-depassee")

    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert "1 tache(s) avec due depassee retiree(s)" in resultat.stdout

    donnees = json.loads(sortie.read_text(encoding="utf-8"))
    assert "33333333-3333-3333-3333-333333333333" not in donnees["taches"]


# --------------------------------------------------------------------------
# 5. Sans --ecrire-scheduled, la base Taskwarrior n'est jamais touchee
# --------------------------------------------------------------------------

def test_sans_ecrire_scheduled_export_identique(base_jetable, tmp_path):
    base_jetable.semer([
        {"uuid": "55555555-5555-5555-5555-555555555555",
         "description": "Tâche ordinaire", "status": "pending",
         "entry": "20261005T080000Z", "estTime": "PT1H",
         "project": "NPD.exemple", "tags": ["pro"],
         "due": "20270301T170000Z"},
    ])
    sortie = tmp_path / "plan.json"

    avant = base_jetable.task("export")
    assert avant.returncode == 0

    resultat = _lancer(base_jetable.env, "--sortie", str(sortie))
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr

    apres = base_jetable.task("export")
    assert apres.returncode == 0

    assert json.loads(avant.stdout) == json.loads(apres.stdout), (
        "l'export Taskwarrior avant/apres doit etre identique sans "
        "--ecrire-scheduled : la CLI n'a pas le droit d'ecrire dans la base")


# --------------------------------------------------------------------------
# 6. Idempotence de l'ecriture du plan JSON
# --------------------------------------------------------------------------

def test_deux_executions_sans_changement_n_ecrivent_pas_deux_fois(base_jetable, tmp_path):
    base_jetable.semer([
        {"uuid": "66666666-6666-6666-6666-666666666666",
         "description": "Tâche stable", "status": "pending",
         "entry": "20261005T080000Z", "estTime": "PT1H",
         "project": "NPD.exemple", "tags": ["pro"],
         "due": "20270301T170000Z"},
    ])
    sortie = tmp_path / "plan.json"

    resultat1 = _lancer(base_jetable.env, "--sortie", str(sortie))
    assert resultat1.returncode == 0, resultat1.stdout + resultat1.stderr
    assert sortie.exists()
    mtime1 = sortie.stat().st_mtime_ns

    resultat2 = _lancer(base_jetable.env, "--sortie", str(sortie))
    assert resultat2.returncode == 0, resultat2.stdout + resultat2.stderr
    mtime2 = sortie.stat().st_mtime_ns

    assert mtime1 == mtime2, "le mtime ne doit pas bouger sur une seconde " \
                             "execution sans changement d'entree"
