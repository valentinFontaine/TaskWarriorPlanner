"""Lot 7 — sortie : plan en JSON (contrat avec ../WebTaskManager) et
`scheduled:` ecrit dans Taskwarrior.

Horloge FIGEE : aucun `datetime.now()` nulle part ici. Les `Plan` et `Bloc` sont
construits a la main (dataclasses simples), jamais via `planif.solveur.resoudre` :
plus rapide, deterministe, et ca isole ce lot du solveur que quelqu'un d'autre
modifie en ce moment meme (consigne).
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from planif.calendrier import instant_creneau
from planif.modele import Tache
from planif.solveur import Bloc, Plan
from planif.sortie import ecrire_json, ecrire_scheduled, plan_en_dict
from tests.cas_reference import GRANULARITE, T0

# --------------------------------------------------------------------------
# t0 dedie a ce lot : minuit local d'un jour sans ambiguite de fuseau.
# --------------------------------------------------------------------------
T0_LOT7 = datetime(2026, 11, 20, 0, 0)


def _plan(blocs, statut="OPTIMAL", retard_total=0, en_retard=()):
    return Plan(blocs=tuple(blocs), t0=T0_LOT7, granularite=GRANULARITE,
                statut=statut, retard_total=retard_total, en_retard=en_retard)


# --------------------------------------------------------------------------
# 1. Le JSON
# --------------------------------------------------------------------------

def test_le_json_distingue_les_trois_regimes():
    """Les quatre blocs (normal, externe, agrege, opportuniste) sont
    distinguables dans le dict sans recalcul : chacun porte ses propres
    drapeaux, jamais deduits d'autre chose."""
    normal = Bloc(uuid="n", indice=0, debut=0, fin=2, externe=False)
    externe = Bloc(uuid="e", indice=0, debut=0, fin=4, externe=True)
    agrege = Bloc(uuid="a", indice=0, debut=10, fin=12, externe=False, agrege=True)
    opportuniste = Bloc(uuid="o", indice=0, debut=20, fin=22, externe=False,
                         opportuniste=True)
    plan = _plan([normal, externe, agrege, opportuniste])

    d = plan_en_dict(plan)

    b_n = d["taches"]["n"]["blocs"][0]
    b_e = d["taches"]["e"]["blocs"][0]
    b_a = d["taches"]["a"]["blocs"][0]
    b_o = d["taches"]["o"]["blocs"][0]

    assert (b_n["externe"], b_n["agrege"], b_n["opportuniste"]) == (False, False, False)
    assert (b_e["externe"], b_e["agrege"], b_e["opportuniste"]) == (True, False, False)
    assert (b_a["externe"], b_a["agrege"], b_a["opportuniste"]) == (False, True, False)
    assert (b_o["externe"], b_o["agrege"], b_o["opportuniste"]) == (False, False, True)

    # la precision jour/heure decoule du regime agrege, et rien d'autre.
    assert b_n["precision"] == "heure"
    assert b_e["precision"] == "heure"
    assert b_a["precision"] == "jour"
    assert b_o["precision"] == "heure"


def test_le_json_donne_des_instants_iso_pas_des_creneaux():
    """Aucun indice de creneau ne fuit : les instants sont des chaines ISO,
    egales a ce que rend `instant_creneau`, pas des entiers."""
    bloc = Bloc(uuid="n", indice=0, debut=5, fin=9, externe=False)
    plan = _plan([bloc])

    d = plan_en_dict(plan)
    b = d["taches"]["n"]["blocs"][0]

    attendu_debut = instant_creneau(T0_LOT7, 5, GRANULARITE).isoformat()
    attendu_fin = instant_creneau(T0_LOT7, 9, GRANULARITE).isoformat()

    assert isinstance(b["debut"], str)
    assert isinstance(b["fin"], str)
    assert b["debut"] == attendu_debut
    assert b["fin"] == attendu_fin
    # ni 5 ni 9 (les indices bruts) ne doivent apparaitre comme valeur
    assert b["debut"] != 5
    assert b["fin"] != 9


def test_le_json_est_stable_octet_pour_octet():
    """Deux serialisations de la meme entree donnent EXACTEMENT la meme chaine :
    c'est ce qui rend l'idempotence de l'ecriture testable."""
    blocs = [
        Bloc(uuid="b", indice=1, debut=4, fin=6, externe=False),
        Bloc(uuid="a", indice=0, debut=0, fin=4, externe=False),
    ]
    plan = _plan(blocs)

    chaine1 = json.dumps(plan_en_dict(plan), sort_keys=True, indent=2)
    chaine2 = json.dumps(plan_en_dict(plan), sort_keys=True, indent=2)

    assert chaine1 == chaine2


def test_ecrire_json_est_idempotent(tmp_path):
    """Premier appel : True (ecrit). Second appel sur le meme plan : False, et
    le mtime du fichier n'a PAS bouge — on prouve qu'on n'a rien reecrit, pas
    seulement que la valeur de retour le dit."""
    bloc = Bloc(uuid="n", indice=0, debut=0, fin=2, externe=False)
    plan = _plan([bloc])
    chemin = tmp_path / "plan.json"

    assert ecrire_json(plan, chemin) is True
    mtime_apres_premier = chemin.stat().st_mtime_ns

    assert ecrire_json(plan, chemin) is False
    mtime_apres_second = chemin.stat().st_mtime_ns

    assert mtime_apres_second == mtime_apres_premier


def test_le_json_porte_le_statut_et_le_retard():
    """Un plan degrade (FEASIBLE, retard > 0, en_retard non vide) se relit
    fidelement dans le JSON."""
    bloc = Bloc(uuid="n", indice=0, debut=0, fin=2, externe=False)
    plan = _plan([bloc], statut="FEASIBLE", retard_total=7,
                 en_retard=("n", "autre-uuid"))

    d = plan_en_dict(plan)

    assert d["version"] == 1
    assert d["statut"] == "FEASIBLE"
    assert d["retard_total"] == 7
    assert set(d["en_retard"]) == {"n", "autre-uuid"}


def test_le_json_ajoute_description_et_projet_si_fournis():
    """`taches` est optionnel : quand il est fourni, description et projet sont
    ajoutes ; sinon, ils sont simplement absents (jamais inventes)."""
    bloc = Bloc(uuid="n", indice=0, debut=0, fin=2, externe=False)
    plan = _plan([bloc])
    tache = Tache(uuid="n", description="Faire le plan", projet="NPD.helisides")

    avec = plan_en_dict(plan, taches=[tache])
    sans = plan_en_dict(plan)

    assert avec["taches"]["n"]["description"] == "Faire le plan"
    assert avec["taches"]["n"]["projet"] == "NPD.helisides"
    assert "description" not in sans["taches"]["n"]
    assert "projet" not in sans["taches"]["n"]


# --------------------------------------------------------------------------
# 2. L'ecriture dans Taskwarrior
# --------------------------------------------------------------------------

CHAINE_LOT7 = [
    {"uuid": "11111111-0000-0000-0000-000000000001",
     "description": "Tache normale", "status": "pending",
     "entry": "20261005T080000Z", "tags": ["pro"]},
    {"uuid": "22222222-0000-0000-0000-000000000002",
     "description": "Tache externe", "status": "pending",
     "entry": "20261005T080000Z", "tags": ["pro", "externe"]},
]


def _instant_utc_tw(instant_local_naif):
    """Calcule, independamment de planif/sortie.py, la valeur `scheduled` que
    Taskwarrior devrait rendre pour un instant local naif donne. Sert de valeur
    attendue independante dans les tests, comme test_lot0_socle.py le fait pour
    la lecture."""
    return instant_local_naif.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_ecrire_scheduled_pose_le_debut_du_premier_bloc(base_jetable):
    """`scheduled` vaut le debut du premier bloc de la tache — verifie en
    relisant par `task export`, pas seulement l'absence d'erreur."""
    base_jetable.semer(CHAINE_LOT7)
    uuid_n = "11111111-0000-0000-0000-000000000001"
    # 14:00 = indice 28 (30 min de granularite depuis minuit)
    bloc = Bloc(uuid=uuid_n, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])

    ecrire_scheduled(plan, env=base_jetable.env)

    par_uuid = {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}
    attendu = _instant_utc_tw(datetime(2026, 11, 20, 14, 0))
    assert par_uuid[uuid_n]["scheduled"] == attendu


def test_ecrire_scheduled_est_idempotent(base_jetable):
    """Deux appels de suite : le second rend modifiees == [] et tout en
    inchangees. Preuve par le champ `modified` de Taskwarrior, qui ne doit pas
    bouger au second appel — sinon on a reecrit pour rien."""
    base_jetable.semer(CHAINE_LOT7)
    uuid_n = "11111111-0000-0000-0000-000000000001"
    bloc = Bloc(uuid=uuid_n, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])

    rapport1 = ecrire_scheduled(plan, env=base_jetable.env)
    assert rapport1["modifiees"] == [uuid_n]

    avant = {t["uuid"]: t["modified"]
             for t in json.loads(base_jetable.task("export").stdout)}

    rapport2 = ecrire_scheduled(plan, env=base_jetable.env)

    apres = {t["uuid"]: t["modified"]
             for t in json.loads(base_jetable.task("export").stdout)}

    assert rapport2["modifiees"] == []
    assert uuid_n in rapport2["inchangees"]
    assert avant == apres


def test_dry_run_n_ecrit_rien(base_jetable):
    """Le test qui compte le plus : preuve par l'export Taskwarrior complet
    avant/apres, pas par lecture du code. `dry_run=True` ne doit ecrire
    strictement rien, mais le compte rendu doit quand meme etre rempli."""
    base_jetable.semer(CHAINE_LOT7)
    uuid_n = "11111111-0000-0000-0000-000000000001"
    bloc = Bloc(uuid=uuid_n, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])

    avant = base_jetable.task("export").stdout

    rapport = ecrire_scheduled(plan, env=base_jetable.env, dry_run=True)

    apres = base_jetable.task("export").stdout

    assert avant == apres
    # le compte rendu, lui, dit bien ce qui AURAIT ete fait.
    assert rapport["modifiees"] == [uuid_n]


def test_les_taches_externes_sont_ignorees(base_jetable):
    """Une tache +externe planifiee n'a pas de `scheduled` apres ecriture — ce
    n'est pas du travail de l'utilisateur, ca n'a pas a apparaitre dans son
    agenda — et elle apparait dans `ignorees`."""
    base_jetable.semer(CHAINE_LOT7)
    uuid_e = "22222222-0000-0000-0000-000000000002"
    bloc = Bloc(uuid=uuid_e, indice=0, debut=0, fin=1344, externe=True)
    plan = _plan([bloc])

    rapport = ecrire_scheduled(plan, env=base_jetable.env)

    par_uuid = {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}
    assert "scheduled" not in par_uuid[uuid_e]
    assert uuid_e in rapport["ignorees"]
    assert rapport["modifiees"] == []


def test_une_tache_absente_de_la_base_ne_fait_pas_echouer(base_jetable):
    """Un plan qui reference un uuid inconnu de la base : elle atterrit dans
    `ignorees`, aucune exception, et les autres taches sont bien ecrites."""
    base_jetable.semer(CHAINE_LOT7)
    uuid_n = "11111111-0000-0000-0000-000000000001"
    uuid_inconnu = "99999999-9999-9999-9999-999999999999"
    bloc_connu = Bloc(uuid=uuid_n, indice=0, debut=28, fin=32, externe=False)
    bloc_inconnu = Bloc(uuid=uuid_inconnu, indice=0, debut=0, fin=2, externe=False)
    plan = _plan([bloc_connu, bloc_inconnu])

    rapport = ecrire_scheduled(plan, env=base_jetable.env)

    par_uuid = {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}
    assert uuid_inconnu in rapport["ignorees"]
    assert uuid_n in rapport["modifiees"]
    attendu = _instant_utc_tw(datetime(2026, 11, 20, 14, 0))
    assert par_uuid[uuid_n]["scheduled"] == attendu
