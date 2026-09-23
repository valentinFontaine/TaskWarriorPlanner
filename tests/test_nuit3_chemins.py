"""Nuit 3, etape 1 -- le planificateur tourne sur la base de test.

Contrat des options `--config`, `--echeances` et `--reunions` de
`python -m planif`, et du `reunions.json` vide que `outils/recharger-base-test.py`
doit ecrire.

## Pourquoi c'est le prerequis de tout le reste

Sans ces options, un calcul sur `taskwarrior-test` lit la VRAIE grille de
l'utilisateur (`config.json` a la racine du depot), ses VRAIES echeances
(`echeances.json`) et, des qu'une extraction Outlook a tourne, ses VRAIES
reunions (`reunions.json` du repertoire courant). Un plan calcule ainsi ne dit
rien de la base de test.

## Ce qui est sous contrat

1. chaque option est **lue** : un fichier different change le plan, dans le
   sens attendu, et un temoin sans l'option montre que le test discrimine ;
2. une option qui designe un fichier **absent** fait echouer la commande, en
   nommant le chemin, sans ecrire de plan. Sans option, les fichiers restent
   optionnels comme avant (echeances et reunions) ;
3. sans option, le comportement est inchange : `reunions.json` est toujours lu
   dans le repertoire courant ;
4. `recharger-base-test.py` ecrit `reunions.json` = `[]`.

Aucune valeur de reglage n'est inventee : les grilles viennent de
`tests/base_realiste.generer().config`. La grille « mercredi seul » du test 1
en est un sous-ensemble strict (les autres jours vides).

Tous les lancements se font en sous-processus, sur `base_jetable`, avec
`cwd=tmp_path` (et `PYTHONPATH` sur la racine) pour qu'aucun `reunions.json`
du depot ne puisse s'inviter dans un temoin.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import tests.base_realiste as base_realiste  # noqa: E402

PYTHON = sys.executable
SCRIPT_RECHARGER = RACINE / "outils" / "recharger-base-test.py"

UUID_A = "a1a1a1a1-0000-4000-8000-000000000001"


# --------------------------------------------------------------------------
# outils
# --------------------------------------------------------------------------

def _tw(instant_local_naif):
    return instant_local_naif.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _jour_a_venir(jour_semaine, rang, heure):
    """Le `rang`-ieme jour `jour_semaine` (0 = lundi) strictement a venir."""
    jour = datetime.now().replace(hour=heure, minute=0, second=0, microsecond=0)
    trouves = 0
    while trouves < rang:
        jour += timedelta(days=1)
        if jour.weekday() == jour_semaine:
            trouves += 1
    return jour


def _lancer(env, cwd, *args):
    env = dict(env)
    env["PYTHONPATH"] = str(RACINE)
    return subprocess.run(
        [PYTHON, "-m", "planif", *args],
        capture_output=True, text=True, encoding="utf-8",
        env=env, cwd=str(cwd), check=False,
    )


def _config_base():
    return base_realiste.generer().config


def _ecrire(chemin, contenu):
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return chemin


def _blocs(sortie, uuid=UUID_A):
    donnees = json.loads(Path(sortie).read_text(encoding="utf-8"))
    return donnees["taches"][uuid]["blocs"]


def _semer_une_tache_pro(base_jetable, due, heures=2, projet="NPD.nuit3"):
    tache = {"uuid": UUID_A, "description": "Tache nuit 3", "status": "pending",
             "entry": "20260901T080000Z", "estTime": "PT{}H".format(heures),
             "project": projet, "tags": ["pro"]}
    if due is not None:
        tache["due"] = _tw(due)
    base_jetable.semer([tache])


# --------------------------------------------------------------------------
# 1. --config est lu
# --------------------------------------------------------------------------

def test_config_mercredi_seul_place_tout_le_travail_pro_un_mercredi(base_jetable, tmp_path):
    """Grille pro reduite au seul mercredi : chaque bloc tombe un mercredi.

    Temoin : meme tache, grille complete de la base realiste -- le plan « au
    plus tard » d'une echeance un vendredi ne tombe pas un mercredi. Sans ce
    temoin, un planificateur qui ignorerait `--config` pourrait passer par
    chance.
    """
    due = _jour_a_venir(4, 2, 17)          # 2e vendredi a venir, 17:00
    _semer_une_tache_pro(base_jetable, due)

    complete = _config_base()
    mercredi = json.loads(json.dumps(complete))
    for jour in list(mercredi["timeSlots"]["pro"]):
        if jour != "Wednesday":
            mercredi["timeSlots"]["pro"][jour] = []

    vide = _ecrire(tmp_path / "echeances.json", {})
    temoin_cfg = _ecrire(tmp_path / "config-complete.json", complete)
    test_cfg = _ecrire(tmp_path / "config-mercredi.json", mercredi)

    temoin = _lancer(base_jetable.env, tmp_path, "--config", str(temoin_cfg),
                     "--echeances", str(vide), "--sortie", str(tmp_path / "t.json"))
    assert temoin.returncode == 0, temoin.stdout + temoin.stderr
    jours_temoin = {datetime.fromisoformat(b["debut"]).weekday()
                    for b in _blocs(tmp_path / "t.json")}
    assert jours_temoin != {2}, "temoin non discriminant : {}".format(jours_temoin)

    res = _lancer(base_jetable.env, tmp_path, "--config", str(test_cfg),
                  "--echeances", str(vide), "--sortie", str(tmp_path / "p.json"))
    assert res.returncode == 0, res.stdout + res.stderr
    blocs = _blocs(tmp_path / "p.json")
    assert blocs
    assert {datetime.fromisoformat(b["debut"]).weekday() for b in blocs} == {2}


# --------------------------------------------------------------------------
# 2. --echeances est lu
# --------------------------------------------------------------------------

def test_echeances_est_lu_et_date_la_tache_du_projet(base_jetable, tmp_path):
    """Une echeance de projet transforme une tache non datee (passe 2,
    opportuniste) en tache datee (passe 1). Temoin : fichier vide."""
    _semer_une_tache_pro(base_jetable, due=None, projet="NPD.Orion")
    cfg = _ecrire(tmp_path / "config.json", _config_base())
    echeance = _jour_a_venir(4, 2, 17)
    avec = _ecrire(tmp_path / "echeances.json",
                   {"NPD.Orion": echeance.isoformat()})
    sans = _ecrire(tmp_path / "echeances-vide.json", {})

    temoin = _lancer(base_jetable.env, tmp_path, "--config", str(cfg),
                     "--echeances", str(sans), "--sortie", str(tmp_path / "t.json"))
    assert temoin.returncode == 0, temoin.stdout + temoin.stderr
    assert "0 echeance(s) de projet" in temoin.stdout
    assert all(b["opportuniste"] for b in _blocs(tmp_path / "t.json"))

    res = _lancer(base_jetable.env, tmp_path, "--config", str(cfg),
                  "--echeances", str(avec), "--sortie", str(tmp_path / "p.json"))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "1 echeance(s) de projet" in res.stdout
    blocs = _blocs(tmp_path / "p.json")
    assert blocs and not any(b["opportuniste"] for b in blocs)
    assert max(datetime.fromisoformat(b["fin"]) for b in blocs) <= echeance


# --------------------------------------------------------------------------
# 3. --reunions est lu, et le defaut (repertoire courant) est inchange
# --------------------------------------------------------------------------

def _reunion_avant(due):
    """Une reunion occupee qui couvre les quatre jours precedant `due`."""
    debut = (due - timedelta(days=4)).replace(hour=0, minute=0)
    return debut, due, [{"sujet": "Revue nuit 3", "debut": debut.isoformat(),
                         "fin": due.isoformat(), "occupation": 2}]


def _chevauche(blocs, debut, fin):
    return any(datetime.fromisoformat(b["debut"]) < fin
               and datetime.fromisoformat(b["fin"]) > debut for b in blocs)


def test_reunions_est_lu_et_aucun_bloc_ne_tombe_dedans(base_jetable, tmp_path):
    due = _jour_a_venir(3, 2, 18)          # 2e jeudi a venir, 18:00
    _semer_une_tache_pro(base_jetable, due)
    cfg = _ecrire(tmp_path / "config.json", _config_base())
    vide = _ecrire(tmp_path / "echeances.json", {})
    debut, fin, evenements = _reunion_avant(due)
    agenda = _ecrire(tmp_path / "agenda-test.json", evenements)
    agenda_vide = _ecrire(tmp_path / "agenda-vide.json", [])

    temoin = _lancer(base_jetable.env, tmp_path, "--config", str(cfg),
                     "--echeances", str(vide), "--reunions", str(agenda_vide),
                     "--sortie", str(tmp_path / "t.json"))
    assert temoin.returncode == 0, temoin.stdout + temoin.stderr
    assert _chevauche(_blocs(tmp_path / "t.json"), debut, fin), \
        "temoin non discriminant : sans reunion, le bloc n'est pas dans la fenetre"

    res = _lancer(base_jetable.env, tmp_path, "--config", str(cfg),
                  "--echeances", str(vide), "--reunions", str(agenda),
                  "--sortie", str(tmp_path / "p.json"))
    assert res.returncode == 0, res.stdout + res.stderr
    blocs = _blocs(tmp_path / "p.json")
    assert blocs
    assert not _chevauche(blocs, debut, fin)


def test_sans_option_reunions_json_du_repertoire_courant_est_toujours_lu(base_jetable, tmp_path):
    """Comportement inchange : sans --reunions, `reunions.json` du cwd."""
    due = _jour_a_venir(3, 2, 18)
    _semer_une_tache_pro(base_jetable, due)
    cfg = _ecrire(tmp_path / "config.json", _config_base())
    vide = _ecrire(tmp_path / "echeances.json", {})
    debut, fin, evenements = _reunion_avant(due)
    _ecrire(tmp_path / "reunions.json", evenements)

    res = _lancer(base_jetable.env, tmp_path, "--config", str(cfg),
                  "--echeances", str(vide), "--sortie", str(tmp_path / "p.json"))
    assert res.returncode == 0, res.stdout + res.stderr
    assert not _chevauche(_blocs(tmp_path / "p.json"), debut, fin)


# --------------------------------------------------------------------------
# 4. un chemin explicite absent est une erreur, pas un fichier optionnel
# --------------------------------------------------------------------------

def _absent_echoue(base_jetable, tmp_path, option):
    _semer_une_tache_pro(base_jetable, _jour_a_venir(4, 2, 17))
    cfg = _ecrire(tmp_path / "config.json", _config_base())
    vide = _ecrire(tmp_path / "echeances.json", {})
    agenda = _ecrire(tmp_path / "agenda.json", [])
    chemins = {"--config": str(cfg), "--echeances": str(vide),
               "--reunions": str(agenda)}
    absent = str(tmp_path / "n-existe-pas" / "fichier.json")
    chemins[option] = absent
    args = [a for paire in chemins.items() for a in paire]
    sortie = tmp_path / "p.json"
    res = _lancer(base_jetable.env, tmp_path, *args, "--sortie", str(sortie))
    assert res.returncode != 0
    # argparse rejette une option inconnue en citant sa valeur : sans cette
    # ligne, le test passerait avant meme que l'option existe.
    assert "unrecognized arguments" not in res.stderr
    assert "fichier.json" in res.stdout + res.stderr
    assert not sortie.exists()


def test_config_absent_echoue(base_jetable, tmp_path):
    _absent_echoue(base_jetable, tmp_path, "--config")


def test_echeances_absent_echoue(base_jetable, tmp_path):
    _absent_echoue(base_jetable, tmp_path, "--echeances")


def test_reunions_absent_echoue(base_jetable, tmp_path):
    _absent_echoue(base_jetable, tmp_path, "--reunions")


def test_les_options_ont_none_pour_defaut():
    from planif.__main__ import construire_analyseur
    args = construire_analyseur().parse_args([])
    assert args.config is None
    assert args.echeances is None
    assert args.reunions is None


# --------------------------------------------------------------------------
# 5. recharger-base-test.py ecrit un agenda vide
# --------------------------------------------------------------------------

def test_recharger_ecrit_un_reunions_json_vide(tmp_path):
    dossier = tmp_path / "base"
    res = subprocess.run(
        [PYTHON, str(SCRIPT_RECHARGER), "--dossier", str(dossier)],
        capture_output=True, text=True, encoding="utf-8",
        env=dict(os.environ), cwd=str(RACINE), check=False)
    assert res.returncode == 0, res.stdout + res.stderr

    chemin = dossier / "reunions.json"
    assert chemin.exists()
    assert json.loads(chemin.read_text(encoding="utf-8-sig")) == []

    from planif.reunions import reunions
    maintenant = datetime.now()
    assert reunions(maintenant, maintenant + timedelta(days=90),
                    source=str(chemin)) == ()
