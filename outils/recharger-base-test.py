"""Recharge une base Taskwarrior JETABLE avec le jeu de donnees realiste de
tests/base_realiste.py, pour experimenter a la main sans jamais toucher aux
vraies bases (taskwarrior-dev, taskWarrior-copie, ou la base reelle
synchronisee par Syncthing).

Usage :

    venv/Scripts/python.exe outils/recharger-base-test.py [--dossier DIR]

Sans --dossier, DIR vaut DOSSIER_PAR_DEFAUT (C:/Users/irpaui/taskwarrior-test).
Si DIR n'existe pas ou est vide, il est initialise (taskrc + data/.jetable)
puis seme. Si DIR existe deja et n'est pas vide, il doit deja porter taskrc et
data/.jetable (sinon le script refuse, sans rien modifier) ; dans ce cas la
base est effacee puis resemee a l'identique.

A la fin, le script ecrit DIR/config.json et DIR/echeances.json (le contenu
config/echeances du jeu de donnees) et DIR/reunions.json (agenda vide : `[]`),
et affiche le nombre de taches semees ainsi que la commande PowerShell pour
pointer Taskwarrior sur ce taskrc.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import tests.base_realiste as base_realiste  # noqa: E402

DOSSIER_PAR_DEFAUT = "C:/Users/irpaui/taskwarrior-test"

# Contenu du taskrc : duplique de la fixture base_jetable de tests/conftest.py
# (ne pas modifier conftest.py, ni le lire depuis ici : c'est une fixture de
# test, pas un module reutilisable). Garder les deux en phase a la main si
# l'un des deux change.
GABARIT_TASKRC = (
    "data.location={donnees}\n"
    "confirmation=off\n"
    "bulk=0\n"
    "verbose=nothing\n"
    "uda.estTime.type=duration\n"
    "uda.estTime.label=Est Time\n"
    "uda.duePlanif.type=date\n"
    "uda.duePlanif.label=Due Planif\n"
)


def _dossier_pret_pour_semis(dossier):
    """Verifie qu'on a le droit d'ecrire dans `dossier` sans avoir encore rien
    ecrit. Leve ValueError sinon (message destine a stderr)."""
    if not dossier.exists():
        return
    contenu = list(dossier.iterdir())
    if not contenu:
        return
    taskrc = dossier / "taskrc"
    temoin = dossier / "data" / ".jetable"
    if not taskrc.exists() or not temoin.exists():
        raise ValueError(
            "{} existe deja et n'est pas vide, mais ne porte pas a la fois "
            "taskrc et data/.jetable : refus de le modifier.".format(dossier)
        )


def _initialiser(dossier):
    """Cree taskrc et data/.jetable s'ils n'existent pas deja."""
    donnees = dossier / "data"
    donnees.mkdir(parents=True, exist_ok=True)
    taskrc = dossier / "taskrc"
    if not taskrc.exists():
        taskrc.write_text(
            GABARIT_TASKRC.format(donnees=donnees.as_posix()), encoding="utf-8",
        )
    temoin = donnees / ".jetable"
    if not temoin.exists():
        temoin.write_text("", encoding="utf-8")
    return taskrc


def recharger(dossier):
    """Initialise (si besoin) et reseme `dossier`. Rend (base, taskrc)."""
    dossier = Path(dossier)
    _dossier_pret_pour_semis(dossier)

    taskrc = _initialiser(dossier)

    base = base_realiste.generer()
    base_realiste.semer(taskrc, base)

    (dossier / "config.json").write_text(
        json.dumps(base.config, ensure_ascii=False), encoding="utf-8",
    )
    (dossier / "echeances.json").write_text(
        json.dumps(base.echeances, ensure_ascii=False), encoding="utf-8",
    )
    (dossier / "reunions.json").write_text(
        json.dumps([], ensure_ascii=False), encoding="utf-8",
    )

    return base, taskrc


def main():
    parseur = argparse.ArgumentParser(
        description="Recharge une base Taskwarrior jetable avec le jeu de "
                     "donnees realiste de tests/base_realiste.py.",
    )
    parseur.add_argument("--dossier", default=DOSSIER_PAR_DEFAUT)
    arguments = parseur.parse_args()

    dossier = Path(arguments.dossier)

    try:
        base, taskrc = recharger(dossier)
    except (ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    print(
        "{} taches semees dans {} -- pour les utiliser :\n"
        "$env:TASKRC='{}'".format(len(base.taches), taskrc, taskrc)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
