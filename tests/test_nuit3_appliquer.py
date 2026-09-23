"""Nuit 3, etape 3 -- appliquer un `plan.json` sans recalcul.

    python -m planif --appliquer <plan.json>

C'est ce que lance le bouton Valider (E4) : il ecrit **exactement le plan
affiche**, pas un plan recalcule entre-temps. Le mode :

- lit le fichier (version 1, sinon refus) ;
- ecrit `scheduled` = debut du premier bloc de chaque tache non `+externe`
  (`ecrire_scheduled`, comportement inchange) ;
- ecrit `due` et `duePlanif` = le champ `"due"` de la tache dans le fichier
  (`ecrire_due`, meme regles : `+externe` ignorees, `due` humaine jamais
  ecrasee, tache absente de la base ignoree). Une tache dont le `"due"` vaut
  `null` (passe 2) va dans `ignorees` pour la due ;
- **ne calcule rien** : aucune grille, aucun solveur. Prouve ici en appliquant
  un bloc qu'aucun calcul ne produirait (un dimanche a 03:00) ;
- **ne pose jamais `+fige`** (c'est E3 qui le fait) ;
- imprime sur stdout **un seul objet JSON** :
  `{"scheduled": {"modifiees": [...], "inchangees": [...], "ignorees": [...]},
    "due": {...meme forme...}}`, listes d'uuid. Chaque tache du fichier se
  retrouve dans exactement une des trois listes de chaque ecriture.

`--appliquer` combine a `--ecrire-scheduled` ou `--ecrire-due` est refuse :
les deux voies d'ecriture ne se melangent pas.

Tout se passe en sous-processus sur `base_jetable`, verifie ensuite par
`task export`.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

U_NORMALE = "c0c0c0c0-0000-4000-8000-000000000001"
U_HORS_PLAN = "c0c0c0c0-0000-4000-8000-000000000002"
U_HUMAINE = "c0c0c0c0-0000-4000-8000-000000000003"
U_EXTERNE = "c0c0c0c0-0000-4000-8000-000000000004"
U_OPPORTUNISTE = "c0c0c0c0-0000-4000-8000-000000000005"
U_ABSENTE = "c0c0c0c0-0000-4000-8000-000000000009"

T0 = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                                   microsecond=0)


def _tw(instant):
    return instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _dimanche_3h():
    jour = T0 + timedelta(days=7)
    while jour.weekday() != 6:
        jour += timedelta(days=1)
    return jour.replace(hour=3)


# --- les instants du plan ecrit a la main -----------------------------------
DEBUT_NORMALE = _dimanche_3h()                     # aucun calcul ne produit ca
FIN_NORMALE = DEBUT_NORMALE + timedelta(hours=2)
DEBUT_NORMALE_2 = DEBUT_NORMALE + timedelta(days=1, hours=6)
DUE_NORMALE = DEBUT_NORMALE_2 + timedelta(hours=1)
DEBUT_HUMAINE = T0 + timedelta(days=2, hours=9)
DUE_HUMAINE_CALCULEE = DEBUT_HUMAINE + timedelta(hours=2)
DUE_HUMAINE_POSEE = T0 + timedelta(days=30, hours=17)
DEBUT_EXTERNE = T0 + timedelta(days=3)
DEBUT_OPPO = T0 + timedelta(days=1, hours=10)


def _bloc(indice, debut, fin, externe=False, opportuniste=False):
    return {"indice": indice, "debut": debut.isoformat(), "fin": fin.isoformat(),
            "externe": externe, "agrege": False, "opportuniste": opportuniste,
            "precision": "heure"}


def _entree(blocs, due):
    return {"blocs": blocs, "debut": blocs[0]["debut"],
            "fin": max(b["fin"] for b in blocs),
            "due": due.isoformat() if due else None}


def _plan_json():
    return {
        "version": 1, "statut": "OPTIMAL", "retard_total": 0, "en_retard": [],
        "t0": T0.isoformat(), "granularite_minutes": 30,
        "taches": {
            U_NORMALE: _entree([_bloc(0, DEBUT_NORMALE, FIN_NORMALE),
                                _bloc(1, DEBUT_NORMALE_2, DUE_NORMALE)],
                               DUE_NORMALE),
            U_HUMAINE: _entree([_bloc(0, DEBUT_HUMAINE, DUE_HUMAINE_CALCULEE)],
                               DUE_HUMAINE_CALCULEE),
            U_EXTERNE: _entree([_bloc(0, DEBUT_EXTERNE,
                                      DEBUT_EXTERNE + timedelta(days=10),
                                      externe=True)],
                               DEBUT_EXTERNE + timedelta(days=10)),
            U_OPPORTUNISTE: _entree([_bloc(0, DEBUT_OPPO,
                                           DEBUT_OPPO + timedelta(hours=1),
                                           opportuniste=True)], None),
            U_ABSENTE: _entree([_bloc(0, DEBUT_HUMAINE,
                                      DEBUT_HUMAINE + timedelta(hours=1))],
                               DEBUT_HUMAINE + timedelta(hours=1)),
        },
    }


def _semer(base_jetable):
    commun = {"status": "pending", "entry": "20260901T080000Z",
              "estTime": "PT2H", "project": "NPD.nuit3"}
    base_jetable.semer([
        dict(commun, uuid=U_NORMALE, description="Normale",
             tags=["pro", "acteurDupont"]),
        dict(commun, uuid=U_HORS_PLAN, description="Hors plan", tags=["pro"],
             scheduled="20261001T080000Z"),
        dict(commun, uuid=U_HUMAINE, description="Due humaine", tags=["pro"],
             due=_tw(DUE_HUMAINE_POSEE)),
        dict(commun, uuid=U_EXTERNE, description="Fournisseur",
             tags=["pro", "externe"]),
        dict(commun, uuid=U_OPPORTUNISTE, description="Sans date",
             tags=["perso"]),
    ])


def _appliquer(base_jetable, chemin, *extra, env=None):
    env = dict(env if env is not None else base_jetable.env)
    env["PYTHONPATH"] = str(RACINE)
    return subprocess.run(
        [PYTHON, "-m", "planif", "--appliquer", str(chemin), *extra],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(chemin.parent), check=False)


def _export(base_jetable):
    return {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}


@pytest.fixture
def plan_applique(base_jetable, tmp_path):
    _semer(base_jetable)
    chemin = tmp_path / "plan.json"
    chemin.write_text(json.dumps(_plan_json()), encoding="utf-8")
    avant = _export(base_jetable)
    res = _appliquer(base_jetable, chemin)
    assert res.returncode == 0, res.stdout + res.stderr
    return {"chemin": chemin, "avant": avant, "apres": _export(base_jetable),
            "rapport": json.loads(res.stdout)}


# --------------------------------------------------------------------------
# 1. ce qui est dans le fichier, et rien d'autre
# --------------------------------------------------------------------------

def test_scheduled_est_le_debut_du_premier_bloc_du_fichier(plan_applique):
    assert plan_applique["apres"][U_NORMALE]["scheduled"] == _tw(DEBUT_NORMALE)


def test_aucun_calcul_le_bloc_impossible_est_ecrit_tel_quel(plan_applique):
    """Un dimanche a 03:00 : hors de toute grille, aucun solveur ne le propose."""
    instant = datetime.strptime(plan_applique["apres"][U_NORMALE]["scheduled"],
                                "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    local = instant.astimezone().replace(tzinfo=None)
    assert (local.weekday(), local.hour) == (6, 3)


def test_due_et_due_planif_sont_le_champ_due_du_fichier(plan_applique):
    tache = plan_applique["apres"][U_NORMALE]
    assert tache["due"] == _tw(DUE_NORMALE)
    assert tache["duePlanif"] == _tw(DUE_NORMALE)


def test_une_tache_hors_du_fichier_n_est_pas_touchee(plan_applique):
    assert plan_applique["apres"][U_HORS_PLAN] == plan_applique["avant"][U_HORS_PLAN]


def test_jamais_de_fige_et_tags_inchanges(plan_applique):
    for uuid, tache in plan_applique["apres"].items():
        assert "fige" not in (tache.get("tags") or [])
        assert set(tache.get("tags") or []) == \
            set(plan_applique["avant"][uuid].get("tags") or [])


# --------------------------------------------------------------------------
# 2. les regles d'ecriture existantes tiennent
# --------------------------------------------------------------------------

def test_une_due_humaine_n_est_pas_ecrasee(plan_applique):
    tache = plan_applique["apres"][U_HUMAINE]
    assert tache["due"] == _tw(DUE_HUMAINE_POSEE)
    assert "duePlanif" not in tache
    assert U_HUMAINE in plan_applique["rapport"]["due"]["ignorees"]
    # son scheduled, lui, est ecrit
    assert tache["scheduled"] == _tw(DEBUT_HUMAINE)


def test_une_tache_externe_est_ignoree(plan_applique):
    tache = plan_applique["apres"][U_EXTERNE]
    assert "scheduled" not in tache and "due" not in tache
    assert U_EXTERNE in plan_applique["rapport"]["scheduled"]["ignorees"]
    assert U_EXTERNE in plan_applique["rapport"]["due"]["ignorees"]


def test_une_tache_absente_de_la_base_est_ignoree(plan_applique):
    assert U_ABSENTE in plan_applique["rapport"]["scheduled"]["ignorees"]
    assert U_ABSENTE in plan_applique["rapport"]["due"]["ignorees"]
    assert U_ABSENTE not in plan_applique["apres"]


def test_une_due_nulle_n_est_pas_ecrite(plan_applique):
    tache = plan_applique["apres"][U_OPPORTUNISTE]
    assert "due" not in tache and "duePlanif" not in tache
    assert tache["scheduled"] == _tw(DEBUT_OPPO)
    assert U_OPPORTUNISTE in plan_applique["rapport"]["due"]["ignorees"]


# --------------------------------------------------------------------------
# 3. le compte rendu
# --------------------------------------------------------------------------

def test_chaque_tache_du_fichier_est_dans_une_seule_liste(plan_applique):
    uuids = set(_plan_json()["taches"])
    for ecriture in ("scheduled", "due"):
        cr = plan_applique["rapport"][ecriture]
        listes = [cr["modifiees"], cr["inchangees"], cr["ignorees"]]
        assert sorted(u for l in listes for u in l) == sorted(uuids), ecriture


def test_premier_passage_les_modifiees_attendues(plan_applique):
    r = plan_applique["rapport"]
    assert sorted(r["scheduled"]["modifiees"]) == sorted(
        [U_NORMALE, U_HUMAINE, U_OPPORTUNISTE])
    assert r["due"]["modifiees"] == [U_NORMALE]


# --------------------------------------------------------------------------
# 4. idempotence : deux fois = zero modifiee la seconde fois
# --------------------------------------------------------------------------

def test_appliquer_deux_fois_ne_modifie_rien_la_seconde(base_jetable, plan_applique):
    res = _appliquer(base_jetable, plan_applique["chemin"])
    assert res.returncode == 0, res.stdout + res.stderr
    rapport = json.loads(res.stdout)
    assert rapport["scheduled"]["modifiees"] == []
    assert rapport["due"]["modifiees"] == []
    apres2 = _export(base_jetable)
    for uuid, tache in apres2.items():
        assert tache["modified"] == plan_applique["apres"][uuid]["modified"], uuid


# --------------------------------------------------------------------------
# 5. refus
# --------------------------------------------------------------------------

def test_fichier_absent_refuse(base_jetable, tmp_path):
    res = _appliquer(base_jetable, tmp_path / "n-existe-pas.json")
    assert res.returncode != 0
    assert "unrecognized arguments" not in res.stderr
    assert "n-existe-pas.json" in res.stderr


def test_version_inconnue_refusee_sans_ecrire(base_jetable, tmp_path):
    _semer(base_jetable)
    donnees = _plan_json()
    donnees["version"] = 2
    chemin = tmp_path / "plan.json"
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    avant = _export(base_jetable)
    res = _appliquer(base_jetable, chemin)
    assert res.returncode != 0
    assert "unrecognized arguments" not in res.stderr
    assert "version" in res.stderr.lower()
    assert _export(base_jetable) == avant


@pytest.mark.parametrize("drapeau", ["--ecrire-scheduled", "--ecrire-due"])
def test_appliquer_ne_se_combine_pas_avec_les_drapeaux_d_ecriture(
        base_jetable, tmp_path, drapeau):
    _semer(base_jetable)
    chemin = tmp_path / "plan.json"
    chemin.write_text(json.dumps(_plan_json()), encoding="utf-8")
    avant = _export(base_jetable)
    res = _appliquer(base_jetable, chemin, drapeau)
    assert res.returncode != 0
    assert "unrecognized arguments" not in res.stderr
    assert _export(base_jetable) == avant


def test_appliquer_refuse_sans_isolation(tmp_path):
    chemin = tmp_path / "plan.json"
    chemin.write_text(json.dumps(_plan_json()), encoding="utf-8")
    env = dict(os.environ)
    env.pop("TASKRC", None)
    env.pop("TASKDATA", None)
    env["PYTHONPATH"] = str(RACINE)
    res = subprocess.run(
        [PYTHON, "-m", "planif", "--appliquer", str(chemin)],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(tmp_path), check=False)
    assert res.returncode != 0
    assert "TASKRC" in res.stdout + res.stderr
