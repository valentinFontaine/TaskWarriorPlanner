"""Contrat de test -- avec `--filtre`, les +fixed hors filtre restent du temps OCCUPE.

Remarque de l'utilisateur, 2026-10-17 : un calcul limite a un projet proposait
deux taches de maisonChristina PENDANT une tache figee de Balise77. Le filtre
ne chargeait que les taches retenues : la figee d'un autre projet n'existait
plus, son temps paraissait libre.

Specification : avec un filtre, chaque tache `+fixed` en attente, hors du
filtre, qui porte un `scheduled` et un `estTime`, occupe `[scheduled,
scheduled + estTime[` comme une reunion. Elle n'est pas planifiee et
n'apparait pas dans le plan.
"""
import json
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from planif.modele import Tache

RACINE = Path(__file__).resolve().parent.parent

LUNDI = datetime(2026, 10, 19, 9, 0)


def _tache(uuid, fige=True, scheduled=LUNDI, estimated=timedelta(hours=2)):
    return Tache(uuid=uuid, description="t " + uuid, scheduled=scheduled,
                 estimated=estimated, tags=("fixed",) if fige else ())


def test_occupations_ne_gardent_que_les_figees_hors_filtre_completes():
    from planif.reunions import occupations_figees
    toutes = [
        _tache("dans-le-filtre"),
        _tache("hors-filtre"),
        _tache("pas-figee", fige=False),
        _tache("sans-scheduled", scheduled=None),
        _tache("sans-duree", estimated=None),
    ]
    occupations = occupations_figees(toutes, exclues={"dans-le-filtre"})
    assert len(occupations) == 1
    assert occupations[0].debut == LUNDI
    assert occupations[0].fin == LUNDI + timedelta(hours=2)
    assert "t hors-filtre" in occupations[0].titre


def _utc(instant_local):
    return instant_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_cli_filtre_ne_place_rien_pendant_une_figee_hors_filtre(
        base_jetable, tmp_path):
    # un mardi a deux semaines : avant la frontiere de l'horizon detaille
    jour = datetime.now().date() + timedelta(days=14)
    jour += timedelta(days=(1 - jour.weekday()) % 7)
    debut_b = datetime.combine(jour, time(0, 0))
    fin_b = debut_b + timedelta(hours=23)
    # A, « au plus tard », irait juste avant sa due du mardi 17:00 -- en plein
    # dans la journee occupee par B.
    due_a = datetime.combine(jour, time(17, 0))
    base_jetable.semer([
        {"uuid": "aaaaaaaa-1111-1111-1111-111111111111",
         "description": "A dans le filtre", "status": "pending",
         "entry": "20261005T080000Z", "estTime": "PT1H",
         "project": "projetA", "tags": ["pro"], "due": _utc(due_a)},
        {"uuid": "bbbbbbbb-1111-1111-1111-111111111111",
         "description": "B figee hors filtre", "status": "pending",
         "entry": "20261005T080000Z", "estTime": "PT23H",
         "project": "projetB", "tags": ["pro", "fixed"],
         "scheduled": _utc(debut_b)},
    ])
    sortie = tmp_path / "plan.json"
    resultat = subprocess.run(
        [sys.executable, "-m", "planif", "--sortie", str(sortie),
         "--filtre", "status:pending project:projetA",
         "--horizon", "30", "--horizon-detaille", "30"],
        capture_output=True, text=True, encoding="utf-8",
        env=base_jetable.env, cwd=str(RACINE), check=False)
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr

    taches = json.loads(sortie.read_text(encoding="utf-8"))["taches"]
    assert "bbbbbbbb-1111-1111-1111-111111111111" not in taches
    blocs = taches["aaaaaaaa-1111-1111-1111-111111111111"]["blocs"]
    assert blocs   # chemin exerce : A est placee
    for bloc in blocs:
        debut = datetime.fromisoformat(bloc["debut"]).replace(tzinfo=None)
        fin = datetime.fromisoformat(bloc["fin"]).replace(tzinfo=None)
        assert fin <= debut_b or debut >= fin_b, (
            "A placee pendant la figee hors filtre : {}".format(bloc))
