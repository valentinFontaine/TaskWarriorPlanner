"""Contrat de test pour `outils/recharger-base-test.py` (script NON ECRIT).

Ce fichier specifie l'interface en ligne de commande du script, qui n'existe pas
encore. Toute implementation qui satisfait ce fichier est valide.

INTERFACE CHOISIE
==================

    venv/Scripts/python.exe outils/recharger-base-test.py [--dossier DIR]

`--dossier` par defaut vaut `C:/Users/irpaui/taskwarrior-test` (constante du
script, jamais lue par ces tests sans --dossier explicite : AGENTS.md §2 et
consigne de la tache). Un dossier DEDIE, distinct de taskwarrior-dev et de
taskWarrior-copie.

Comportement (chaque appel se fait avec --dossier pointant sous tmp_path) :

1. DIR n'existe pas, ou existe et est vide :
   - le script l'initialise : DIR/taskrc (data.location=DIR/data, UDAs
     estTime et duePlanif, options non interactives -- meme contenu utile
     que le taskrc de la fixture `base_jetable`), DIR/data/ avec le fichier
     temoin DIR/data/.jetable ;
   - il seme la base de `tests/base_realiste.generer()` (date du jour) via
     `tests/base_realiste.semer()` ;
   - il ecrit DIR/config.json (= base.config) et DIR/echeances.json
     (= base.echeances), UTF-8 ;
   - il affiche sur stdout une ligne recapitulative : nombre de taches
     semees, chemin du taskrc, et la commande PowerShell pour l'utiliser
     ($env:TASKRC='...') ;
   - code de sortie 0.

2. DIR existe et n'est PAS vide :
   - le script EXIGE DIR/taskrc et DIR/data/.jetable pour continuer ;
   - si l'un des deux manque : refus, code de sortie non nul, message sur
     stderr, et DIR n'est modifie d'AUCUNE facon (ni fichier ajoute, retire,
     ni contenu change) ;
   - si les deux sont presents : le script reseme (efface la base pointee
     par le taskrc puis reimporte), comme au cas 1.

Ces tests lancent le script en SOUS-PROCESSUS (`sys.executable`, chemin absolu
du script), jamais en import direct : c'est le point d'entree CLI qui est sous
contrat, comme pour `planif/__main__.py` (tests/test_lotA_cli.py). Chaque appel
verifie la base resultante via `task export` avec TASKRC=DIR/taskrc, dans
l'environnement du sous-processus de verification -- jamais sans TASKRC pose
(AGENTS.md §2).

Aucun test ne touche C:/Users/irpaui/taskwarrior-dev, taskWarrior-copie, la
vraie base de l'utilisateur, ni C:/Users/irpaui/taskwarrior-test : tous les
--dossier utilises ici sont sous tmp_path. Le test 5 (valeur par defaut) ne
lance JAMAIS le script sans --dossier ; il lit la constante par un autre
moyen (import du module par chemin via importlib, ou lecture de --help).
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import tests.base_realiste as base_realiste  # noqa: E402

SCRIPT = RACINE / "outils" / "recharger-base-test.py"
PYTHON = sys.executable


def _lancer(dossier, env=None):
    """Lance le script sous test avec --dossier explicite, jamais sans."""
    return subprocess.run(
        [PYTHON, str(SCRIPT), "--dossier", str(dossier)],
        capture_output=True, text=True, encoding="utf-8",
        env=dict(env if env is not None else os.environ), cwd=str(RACINE),
        check=False,
    )


def _env_task(dossier):
    env = dict(os.environ)
    env["TASKRC"] = str(Path(dossier) / "taskrc")
    env.pop("TASKDATA", None)
    return env


def _export(dossier):
    res = subprocess.run(
        ["task", "export"], capture_output=True, text=True, encoding="utf-8",
        env=_env_task(dossier), check=False,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _snapshot(dossier):
    """Contenu octet pour octet de tout ce que porte DIR, pour verifier
    qu'un refus ne modifie rien (test 3 et 4)."""
    dossier = Path(dossier)
    etat = {}
    for chemin in sorted(dossier.rglob("*")):
        if chemin.is_file():
            etat[str(chemin.relative_to(dossier))] = chemin.read_bytes()
    return etat


# --------------------------------------------------------------------------
# 1. Dossier inexistant : initialisation complete
# --------------------------------------------------------------------------

def test_dossier_inexistant_initialise_et_seme(tmp_path):
    dossier = tmp_path / "base-test"
    assert not dossier.exists()

    resultat = _lancer(dossier)

    assert resultat.returncode == 0, resultat.stderr
    assert (dossier / "taskrc").exists()
    assert (dossier / "data" / ".jetable").exists()
    assert (dossier / "config.json").exists()
    assert (dossier / "echeances.json").exists()

    base = base_realiste.generer()
    attendus = {t["uuid"] for t in base.taches}
    exportees = {t["uuid"] for t in _export(dossier)}
    assert exportees == attendus

    config_relu = json.loads((dossier / "config.json").read_text(encoding="utf-8"))
    echeances_relues = json.loads((dossier / "echeances.json").read_text(encoding="utf-8"))
    assert config_relu == base.config
    assert echeances_relues == base.echeances


# --------------------------------------------------------------------------
# 2. Deux lancements successifs : reseme a l'identique, purge l'etranger
# --------------------------------------------------------------------------

def test_deux_lancements_resement_a_l_identique_et_purgent_etranger(tmp_path):
    dossier = tmp_path / "base-test"

    resultat1 = _lancer(dossier)
    assert resultat1.returncode == 0, resultat1.stderr
    uuids_1 = {t["uuid"] for t in _export(dossier)}

    ajout = subprocess.run(
        ["task", "add", "Tache etrangere ajoutee entre deux recharges"],
        capture_output=True, text=True, encoding="utf-8",
        env=_env_task(dossier), check=False,
    )
    assert ajout.returncode == 0, ajout.stderr

    resultat2 = _lancer(dossier)
    assert resultat2.returncode == 0, resultat2.stderr
    uuids_2 = {t["uuid"] for t in _export(dossier)}

    assert uuids_2 == uuids_1
    descriptions_2 = {t["description"] for t in _export(dossier)}
    assert "Tache etrangere ajoutee entre deux recharges" not in descriptions_2


# --------------------------------------------------------------------------
# 3. Dossier non vide, sans data/.jetable : refus total, rien modifie
# --------------------------------------------------------------------------

def test_dossier_non_vide_sans_temoin_refuse_sans_rien_modifier(tmp_path):
    dossier = tmp_path / "base-test"
    dossier.mkdir()
    (dossier / "un_fichier_quelconque.txt").write_text("contenu", encoding="utf-8")
    (dossier / "data").mkdir()
    (dossier / "data" / "fichier_factice.txt").write_text("factice", encoding="utf-8")

    avant = _snapshot(dossier)
    resultat = _lancer(dossier)

    assert resultat.returncode != 0
    assert resultat.stderr.strip() != ""
    assert _snapshot(dossier) == avant


# --------------------------------------------------------------------------
# 4. Dossier avec taskrc mais sans data/.jetable : refus, rien modifie
# --------------------------------------------------------------------------

def test_dossier_avec_taskrc_sans_temoin_refuse_sans_rien_modifier(tmp_path):
    dossier = tmp_path / "base-test"
    dossier.mkdir()
    (dossier / "taskrc").write_text(
        "data.location={}\n".format((dossier / "data").as_posix()), encoding="utf-8",
    )
    (dossier / "data").mkdir()
    (dossier / "data" / "quelque_chose.txt").write_text("x", encoding="utf-8")

    avant = _snapshot(dossier)
    resultat = _lancer(dossier)

    assert resultat.returncode != 0
    assert resultat.stderr.strip() != ""
    assert _snapshot(dossier) == avant


# --------------------------------------------------------------------------
# 5. La valeur par defaut de --dossier n'est ni taskwarrior-dev ni
#    taskWarrior-copie -- sans jamais lancer le script sans --dossier
# --------------------------------------------------------------------------

def test_defaut_dossier_nest_pas_une_base_partagee():
    spec = importlib.util.spec_from_file_location("recharger_base_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    defaut = str(getattr(module, "DOSSIER_PAR_DEFAUT"))

    assert "taskwarrior-dev" not in defaut
    assert "taskWarrior-copie" not in defaut
    assert "taskwarrior-test" in defaut


# --------------------------------------------------------------------------
# 6. Recapitulatif stdout : nombre de taches et chemin du taskrc
# --------------------------------------------------------------------------

def test_stdout_annonce_le_nombre_de_taches_et_le_taskrc(tmp_path):
    dossier = tmp_path / "base-test"

    resultat = _lancer(dossier)

    assert resultat.returncode == 0, resultat.stderr
    base = base_realiste.generer()
    assert str(len(base.taches)) in resultat.stdout
    assert str(dossier / "taskrc") in resultat.stdout or (dossier / "taskrc").as_posix() in resultat.stdout
