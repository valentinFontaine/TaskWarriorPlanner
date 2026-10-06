"""Ecriture de `due:` et `duePlanif:` — pendant de `test_lot7_sortie.py` pour
`ecrire_scheduled`, mais pour `ecrire_due` (planif/sortie.py).

Horloge FIGEE, comme dans test_lot7_sortie.py : les `Plan`/`Bloc` sont
construits a la main, jamais via `planif.solveur.resoudre`.
"""
import json
from datetime import datetime, timezone

from planif.modele import Tache
from planif.solveur import Bloc, Plan
from planif.sortie import ecrire_due
from tests.cas_reference import GRANULARITE

T0_DUE = datetime(2026, 11, 20, 0, 0)

UUID_N = "11111111-0000-0000-0000-000000000001"
UUID_HUMAIN = "22222222-0000-0000-0000-000000000002"
UUID_EXTERNE = "33333333-0000-0000-0000-000000000003"
UUID_INCONNU = "99999999-9999-9999-9999-999999999999"


def _plan(blocs, statut="OPTIMAL", retard_total=0, en_retard=()):
    return Plan(blocs=tuple(blocs), t0=T0_DUE, granularite=GRANULARITE,
                statut=statut, retard_total=retard_total, en_retard=en_retard)


def _instant_utc_tw(instant_local_naif):
    return instant_local_naif.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _seed_minimale(base_jetable, taches):
    """Seme des taches minimales (uuid + description + tags), sans due."""
    chaine = [{"uuid": u, "description": d, "status": "pending",
               "entry": "20261005T080000Z", "tags": list(tags)}
              for u, d, tags in taches]
    base_jetable.semer(chaine)


def test_due_et_due_planif_sont_ecrites_et_egales(base_jetable):
    _seed_minimale(base_jetable, [(UUID_N, "Plans", ())])
    # 14:00 = indice 28 (30 min de granularite depuis minuit)
    bloc = Bloc(uuid=UUID_N, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])
    taches = [Tache(uuid=UUID_N, description="Plans")]

    rapport = ecrire_due(plan, taches, env=base_jetable.env)

    assert rapport["modifiees"] == [UUID_N]
    par_uuid = {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}
    attendu = _instant_utc_tw(datetime(2026, 11, 20, 16, 0))
    assert par_uuid[UUID_N]["due"] == attendu
    assert par_uuid[UUID_N]["duePlanif"] == attendu


def test_une_deuxieme_ecriture_sans_changement_ne_modifie_rien(base_jetable):
    _seed_minimale(base_jetable, [(UUID_N, "Plans", ())])
    bloc = Bloc(uuid=UUID_N, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])
    taches = [Tache(uuid=UUID_N, description="Plans")]

    rapport1 = ecrire_due(plan, taches, env=base_jetable.env)
    assert rapport1["modifiees"] == [UUID_N]

    avant = {t["uuid"]: t["modified"]
             for t in json.loads(base_jetable.task("export").stdout)}

    rapport2 = ecrire_due(plan, taches, env=base_jetable.env)

    apres = {t["uuid"]: t["modified"]
             for t in json.loads(base_jetable.task("export").stdout)}

    assert rapport2["modifiees"] == []
    assert UUID_N in rapport2["inchangees"]
    assert avant == apres


def test_une_due_humaine_n_est_pas_ecrasee(base_jetable):
    """Une tache qui porte deja un `due` pose a la main (donc sans
    `due_planif` correspondant) n'est pas ecrasee : elle va dans `ignorees`."""
    engagement = datetime(2026, 11, 25, 17, 0)
    base_jetable.semer([
        {"uuid": UUID_HUMAIN, "description": "Engagement humain",
         "status": "pending", "entry": "20261005T080000Z",
         "due": _instant_utc_tw(engagement)},
    ])
    bloc = Bloc(uuid=UUID_HUMAIN, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])
    taches = [Tache(uuid=UUID_HUMAIN, description="Engagement humain",
                    due=engagement, due_planif=None)]

    rapport = ecrire_due(plan, taches, env=base_jetable.env)

    assert UUID_HUMAIN in rapport["ignorees"]
    assert rapport["modifiees"] == []
    par_uuid = {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}
    assert par_uuid[UUID_HUMAIN]["due"] == _instant_utc_tw(engagement)
    assert "duePlanif" not in par_uuid[UUID_HUMAIN]


def test_les_taches_externes_sont_ignorees(base_jetable):
    _seed_minimale(base_jetable, [(UUID_EXTERNE, "Delai fournisseur",
                                   ("external",))])
    bloc = Bloc(uuid=UUID_EXTERNE, indice=0, debut=0, fin=1344, externe=True)
    plan = _plan([bloc])
    taches = [Tache(uuid=UUID_EXTERNE, description="Delai fournisseur",
                    tags=("external",))]

    rapport = ecrire_due(plan, taches, env=base_jetable.env)

    par_uuid = {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}
    assert "due" not in par_uuid[UUID_EXTERNE]
    assert UUID_EXTERNE in rapport["ignorees"]
    assert rapport["modifiees"] == []


def test_une_tache_absente_de_la_base_ne_fait_pas_echouer(base_jetable):
    _seed_minimale(base_jetable, [(UUID_N, "Plans", ())])
    bloc_connu = Bloc(uuid=UUID_N, indice=0, debut=28, fin=32, externe=False)
    bloc_inconnu = Bloc(uuid=UUID_INCONNU, indice=0, debut=0, fin=2, externe=False)
    plan = _plan([bloc_connu, bloc_inconnu])
    taches = [Tache(uuid=UUID_N, description="Plans")]

    rapport = ecrire_due(plan, taches, env=base_jetable.env)

    assert UUID_INCONNU in rapport["ignorees"]
    assert UUID_N in rapport["modifiees"]


def test_dry_run_n_ecrit_rien(base_jetable):
    _seed_minimale(base_jetable, [(UUID_N, "Plans", ())])
    bloc = Bloc(uuid=UUID_N, indice=0, debut=28, fin=32, externe=False)
    plan = _plan([bloc])
    taches = [Tache(uuid=UUID_N, description="Plans")]

    avant = base_jetable.task("export").stdout

    rapport = ecrire_due(plan, taches, env=base_jetable.env, dry_run=True)

    apres = base_jetable.task("export").stdout

    assert avant == apres
    assert rapport["modifiees"] == [UUID_N]
