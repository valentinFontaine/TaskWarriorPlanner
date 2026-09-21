"""Fixtures communes. Toute base Taskwarrior utilisee par les tests est jetable et
creee dans le repertoire temporaire du test lui-meme (AGENTS.md §2)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))


@pytest.fixture
def base_jetable(tmp_path):
    """Cree un taskrc + une base Taskwarrior vierges sous tmp_path.

    Rend une fonction `task(*args)` qui execute la commande en isolation totale,
    et une fonction `semer(liste_de_dicts)` qui importe depuis un fichier UTF-8
    (seule voie qui preserve les accents sous Windows, AGENTS.md §5).
    """
    donnees = tmp_path / "data"
    donnees.mkdir()
    taskrc = tmp_path / "taskrc"
    taskrc.write_text(
        "data.location={}\n"
        "confirmation=off\n"
        "bulk=0\n"
        "verbose=nothing\n"
        "uda.estTime.type=duration\n"
        "uda.estTime.label=Est Time\n".format(donnees.as_posix()),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["TASKRC"] = str(taskrc)
    env.pop("TASKDATA", None)

    def task(*args):
        return subprocess.run(
            ["task", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )

    # garde-fou : on refuse de continuer si l'isolation ne pointe pas ou on croit
    montre = task("_show")
    assert donnees.as_posix() in montre.stdout, "isolation Taskwarrior non confirmee"

    def semer(taches):
        fichier = tmp_path / "seed.json"
        fichier.write_text(json.dumps(taches, ensure_ascii=False), encoding="utf-8")
        res = task("import", str(fichier))
        assert res.returncode == 0, res.stderr
        return res

    return type("BaseJetable", (), {"task": staticmethod(task),
                                    "semer": staticmethod(semer),
                                    "taskrc": taskrc,
                                    "env": env})
