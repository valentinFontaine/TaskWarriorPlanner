"""Nuit 3, etape 2 -- `plan.json` porte les `due` calculees.

Valider (E4) ecrit **exactement le plan affiche**, sans recalcul : tout ce
qu'il ecrit doit donc etre dans `plan.json`. `scheduled` s'y lisait deja (debut
du premier bloc) ; la `due` calculee, non. Chaque tache du plan gagne un champ
`"due"`.

## La regle

- tache placee par la **passe 1** (au moins un bloc non opportuniste) : `due` =
  la valeur de `planif.dues.dues_calculees`, c'est-a-dire la fin de son dernier
  bloc, en ISO local naif comme tous les instants du fichier (design.md §7
  regle 3). C'est exactement ce que `ecrire_due` ecrirait ;
- tache placee par la **passe 2** (tous ses blocs opportunistes) : `null`. La
  passe 2 place du travail non date au plus tot ; la fin de ce placement n'est
  pas une date limite, et la passe 1 n'a rien calcule pour elle ;
- une tache `+external` porte sa valeur comme les autres : le fichier dit ce que
  la passe 1 a calcule, et c'est l'ecriture qui ignore les externes (inchange).

Le champ est **toujours present** (valeur ou `null`), avec ou sans `taches`
fourni : il ne depend que du plan. `version` reste 1 : un champ ajoute est
compatible, `calendar-planner.js` ne lit que ce qu'il connait.

Horloge figee, `Plan` construits a la main, comme `test_lot7_sortie.py`, sauf le
dernier test qui passe par la ligne de commande sur `base_jetable`.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from planif.calendrier import instant_creneau
from planif.dues import dues_calculees
from planif.modele import Tache
from planif.solveur import Bloc, Plan
from planif.sortie import plan_en_dict, serialiser
from tests.cas_reference import GRANULARITE

RACINE = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 11, 20, 0, 0)


def _plan(blocs):
    return Plan(blocs=tuple(blocs), t0=T0, granularite=GRANULARITE,
                statut="OPTIMAL", retard_total=0, en_retard=())


def _iso(indice):
    return instant_creneau(T0, indice, GRANULARITE).isoformat()


def test_une_tache_de_passe_1_porte_la_fin_de_son_dernier_bloc():
    plan = _plan([Bloc(uuid="p", indice=0, debut=20, fin=24, externe=False),
                  Bloc(uuid="p", indice=1, debut=30, fin=32, externe=False)])
    d = plan_en_dict(plan)
    assert d["taches"]["p"]["due"] == _iso(32)


def test_la_due_du_fichier_est_celle_que_ecrire_due_ecrirait():
    blocs = [Bloc(uuid="p", indice=0, debut=3, fin=9, externe=False),
             Bloc(uuid="q", indice=0, debut=40, fin=44, externe=False, agrege=True),
             Bloc(uuid="q", indice=1, debut=10, fin=12, externe=False, agrege=True)]
    plan = _plan(blocs)
    d = plan_en_dict(plan)
    attendu = dues_calculees(plan, [])
    for uuid, instant in attendu.items():
        assert d["taches"][uuid]["due"] == instant.isoformat()


def test_une_tache_de_passe_2_a_une_due_nulle():
    plan = _plan([Bloc(uuid="o", indice=0, debut=2, fin=4, externe=False,
                       opportuniste=True)])
    d = plan_en_dict(plan)
    assert "due" in d["taches"]["o"]
    assert d["taches"]["o"]["due"] is None


def test_une_tache_externe_porte_sa_due_calculee():
    plan = _plan([Bloc(uuid="e", indice=0, debut=0, fin=48, externe=True)])
    d = plan_en_dict(plan)
    assert d["taches"]["e"]["due"] == _iso(48)


def test_le_champ_est_present_avec_ou_sans_taches():
    plan = _plan([Bloc(uuid="p", indice=0, debut=0, fin=2, externe=False)])
    avec = plan_en_dict(plan, taches=[Tache(uuid="p", description="x")])
    sans = plan_en_dict(plan)
    assert avec["taches"]["p"]["due"] == sans["taches"]["p"]["due"] == _iso(2)


def test_la_version_reste_1_et_le_fichier_reste_stable():
    plan = _plan([Bloc(uuid="p", indice=0, debut=0, fin=2, externe=False),
                  Bloc(uuid="o", indice=0, debut=4, fin=6, externe=False,
                       opportuniste=True)])
    assert plan_en_dict(plan)["version"] == 1
    assert serialiser(plan) == serialiser(plan)
    assert '"due": null' in serialiser(plan)


def test_la_ligne_de_commande_ecrit_la_due_dans_plan_json(base_jetable, tmp_path):
    """De bout en bout : une tache datee sort avec une `due` <= son echeance,
    egale a la fin de son dernier bloc ; une tache non datee sort a null."""
    maintenant = datetime.now()
    echeance = (maintenant + timedelta(days=15)).replace(hour=17, minute=0,
                                                          second=0, microsecond=0)
    datee = "d1d1d1d1-0000-4000-8000-000000000001"
    libre = "d1d1d1d1-0000-4000-8000-000000000002"
    base_jetable.semer([
        {"uuid": datee, "description": "Datee", "status": "pending",
         "entry": "20260901T080000Z", "estTime": "PT2H", "project": "NPD.x",
         "tags": ["pro"],
         "due": echeance.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")},
        {"uuid": libre, "description": "Libre", "status": "pending",
         "entry": "20260901T080000Z", "estTime": "PT1H", "project": "NPD.x",
         "tags": ["pro"]},
    ])
    import tests.base_realiste as base_realiste
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(base_realiste.generer().config), encoding="utf-8")
    vide = tmp_path / "echeances.json"
    vide.write_text("{}", encoding="utf-8")
    agenda = tmp_path / "reunions.json"
    agenda.write_text("[]", encoding="utf-8")
    sortie = tmp_path / "plan.json"

    env = dict(base_jetable.env)
    env["PYTHONPATH"] = str(RACINE)
    res = subprocess.run(
        [sys.executable, "-m", "planif", "--config", str(cfg), "--echeances",
         str(vide), "--reunions", str(agenda), "--sortie", str(sortie)],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(tmp_path), check=False)
    assert res.returncode == 0, res.stdout + res.stderr

    taches = json.loads(sortie.read_text(encoding="utf-8"))["taches"]
    entree = taches[datee]
    assert entree["due"] == max(b["fin"] for b in entree["blocs"])
    assert datetime.fromisoformat(entree["due"]) <= echeance
    assert taches[libre]["due"] is None
