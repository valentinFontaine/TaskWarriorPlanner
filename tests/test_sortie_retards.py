"""Contrat de test — l'echeance ratee et le retard exposes dans plan.json.

## Le constat qui motive ce lot

`planif/sortie.py::plan_en_dict` ecrit, pour chaque tache, une `due` qui est
la date CALCULEE (fin du dernier bloc, ce que `ecrire_due` ecrirait) -- jamais
l'echeance d'origine. `../WebTaskManager` ne peut donc ni afficher l'echeance
ratee, ni le retard ; et une tache SANS `due` propre (limite heritee d'un
successeur, ex. "Assembler prototype" dans `tests/base_realiste.py`) n'a
d'ailleurs aucune echeance du tout cote Taskwarrior.

## Le format ajoute

Pour chaque uuid de `plan.en_retard` UNIQUEMENT (choix : le plus simple ; une
tache a l'heure ne porte ni `limite`, ni `retard_minutes`, ni
`limite_heritee_de` -- ces trois champs vont ensemble ou pas du tout) :

    - "limite" : l'echeance effective utilisee par le solveur pour DECIDER du
      retard (due propre ou heritee des successeurs), meme format ISO local
      naif que les autres dates de plan.json ;
    - "retard_minutes" : entier, fin du dernier bloc planifie moins `limite`,
      en minutes, > 0 ;
    - "limite_heritee_de" : uuid de la tache DATEE dont la limite est heritee,
      ou None si la tache porte sa propre `due`.

## Le point qui aurait pu se rater : QUEL tampon

`planif/tampon.py::limites_effectives` accepte un `tampon` optionnel.
`planif/solveur.py` (~ligne 521, fonction `resoudre`) appelle
`limites_effectives(taches, contextes, tampon=timedelta(0))` -- PAS le tampon
par defaut de 24 h -- precisement pour que `Plan.en_retard` et
`Plan.retard_total` refletent la limite VRAIE ("apres, c'est trop tard"), pas
une marge de confort (commentaire du solveur : "Passe 1 sans tampon : sa
sortie est une LIMITE [...] pas une intention"). `planif/__main__.py::
_retards_par_tache`, elle, appelle `limites_effectives(taches, contextes)`
SANS argument -- tampon 24 h par defaut -- mais seulement pour un resume
humain (max/mediane), jamais pour decider qui est en retard.

Consequence pour ce lot : `plan_en_dict` doit calculer `limite` avec
`tampon=timedelta(0)`, exactement comme le solveur, sinon `retard_minutes`
serait incoherent avec `en_retard` (une tache peut etre juste dans les clous
au sens du solveur -- tampon 0 -- mais ressortir "en retard de X minutes" a
cause d'un tampon de confort applique en plus, ou l'inverse). C'est le point a
ne pas rater en lisant `planif/solveur.py` avant d'implementer : reutiliser le
`tampon` par defaut de `limites_effectives` serait un bug silencieux, invisible
tant qu'on ne compare pas aux uuids de `en_retard`.

## Signature

`plan_en_dict(plan, taches=None, contextes=None)` (nouveau parametre
`contextes`, a la fin, defaut `None`) : sans `contextes`, le format est
STRICTEMENT INCHANGE (aucun des trois champs n'apparait) -- c'est ce qui
garde `tests/test_lot7_sortie.py` vert sans le modifier, et ce qui permet a
`ecrire_scheduled`/`ecrire_due` de ne pas avoir a fournir de contextes. Meme
ajout sur `ecrire_json(plan, chemin, taches=None, contextes=None)`, simple
relai. `planif/__main__.py` doit passer `config.contextes` a son appel de
`ecrire_json` (actuellement `ecrire_json(plan, chemin_sortie, taches=taches)`,
sans contextes) pour que la CLI produise ces champs.

## Compatibilite du contrat JSON

`VERSION_FORMAT` reste a 1 : c'est un ajout de cles, jamais un retrait ni un
changement de sens d'une cle existante. Un lecteur qui ignore les cles
inconnues (le comportement JSON normal) continue de lire exactement ce qu'il
lisait avant. `design.md §7` reserve le bump de version aux changements
INCOMPATIBLES (voir docstring de `VERSION_FORMAT` dans `planif/sortie.py`) ;
ajouter des champs optionnels n'en est pas un.

## Etat attendu en lancant ce fichier, maintenant

Rouge partout : `plan_en_dict` ne connait pas encore `contextes`, donc les
trois champs sont absents (et le test 4, qui lit un vrai `plan.json` ecrit
par `python -m planif`, echoue au meme endroit).

Rien ici ne touche `planif/` (contrat de tests seulement) ni
`tests/base_realiste.py` (modifie en parallele par quelqu'un d'autre) : le
test 4 construit sa propre base jetable, minimale, independante.
"""
# Note sur la couverture par mutation : la mutation R5 (calculer les limites
# sur TOUTES les taches au lieu de la seule passe 1) est EQUIVALENTE, aucun
# test ne peut la distinguer. Une tache de passe 2 n'a ni due ni successeur
# date, donc elle ne change aucune limite de passe 1.
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

from planif.calendrier import indice_creneau
from planif.modele import Tache
from planif.solveur import Bloc, Plan
from planif.sortie import plan_en_dict
from tests.cas_reference import CONTEXTE_PRO, GRANULARITE

RACINE_DEPOT = __import__("pathlib").Path(__file__).resolve().parent.parent
PYTHON = sys.executable

CONTEXTES = {"pro": CONTEXTE_PRO}

# Lundi 2026-11-09, minuit : la meme semaine que le Thursday 16h utilise
# partout ci-dessous (grille CONTEXTE_PRO : 09h-12h/14h-17h, ouverte lun-ven).
T0 = datetime(2026, 11, 9, 0, 0)

# Echeance de reference : jeudi 2026-11-12 16:00, DANS la fenetre 14h-17h.
# Avec tampon=timedelta(0) (celui du solveur, voir docstring de module),
# echeance_effective(due, CONTEXTE_PRO, tampon=timedelta(0)) rend `due`
# lui-meme : le jour est ouvre et 16:00 <= fin de journee (17:00), donc
# min(due, fin_de_journee) == due. C'est ce qui rend ce cas simple a verifier
# a la main, sans reimplementer echeance_effective dans le test.
DUE_INTENABLE = datetime(2026, 11, 12, 16, 0)


def _indice(instant):
    return indice_creneau(T0, instant, GRANULARITE)


def _plan(blocs, en_retard, retard_total=0, statut="FEASIBLE"):
    return Plan(blocs=tuple(blocs), t0=T0, granularite=GRANULARITE,
               statut=statut, retard_total=retard_total,
               en_retard=tuple(sorted(en_retard)))


def _bloc(uuid, debut, fin):
    return Bloc(uuid=uuid, indice=0, debut=_indice(debut), fin=_indice(fin),
               externe=False)


# ---------------------------------------------------------------------------
# 1. Tache datee, intenable : limite = son due, pas d'heritage.
# ---------------------------------------------------------------------------

def test_tache_datee_intenable_limite_est_son_propre_due():
    tache = Tache(uuid="x", description="Datee intenable", due=DUE_INTENABLE)
    fin_reelle = DUE_INTENABLE + timedelta(hours=2)   # jeudi 18:00
    bloc = _bloc("x", DUE_INTENABLE - timedelta(minutes=30), fin_reelle)
    plan = _plan([bloc], en_retard=["x"])

    d = plan_en_dict(plan, taches=[tache], contextes=CONTEXTES)
    entree = d["taches"]["x"]

    assert entree["limite"] == DUE_INTENABLE.isoformat()
    assert entree["limite_heritee_de"] is None
    assert entree["retard_minutes"] == 120


# ---------------------------------------------------------------------------
# 2. Predecesseur non date d'une tache datee intenable, lui-meme en retard.
# ---------------------------------------------------------------------------

def test_predecesseur_non_date_herite_la_limite_du_successeur():
    """"s" (successeur) porte la due propre intenable du test 1. "p"
    (predecesseur, s.depends == (p.uuid,) car depends liste les
    PREDECESSEURS) n'a pas de due propre : sa limite doit venir de "s",
    exactement (16:00), et `limite_heritee_de` doit nommer "s"."""
    succ = Tache(uuid="s", description="Succ datee intenable", due=DUE_INTENABLE,
                 depends=("p",))
    pred = Tache(uuid="p", description="Pred non date", due=None)

    bloc_succ = _bloc("s", DUE_INTENABLE - timedelta(minutes=30),
                      DUE_INTENABLE + timedelta(hours=2))          # 18:00, retard 120
    bloc_pred = _bloc("p", DUE_INTENABLE - timedelta(hours=1),
                      DUE_INTENABLE + timedelta(hours=1))          # 17:00, retard 60
    plan = _plan([bloc_succ, bloc_pred], en_retard=["p", "s"])

    d = plan_en_dict(plan, taches=[succ, pred], contextes=CONTEXTES)

    entree_p = d["taches"]["p"]
    assert entree_p["limite"] == DUE_INTENABLE.isoformat()
    assert entree_p["limite_heritee_de"] == "s"
    assert entree_p["retard_minutes"] == 60

    entree_s = d["taches"]["s"]
    assert entree_s["limite_heritee_de"] is None
    assert entree_s["retard_minutes"] == 120


# ---------------------------------------------------------------------------
# 2bis. Tache fragmentee en 2 blocs (le 1er finit AVANT la limite, le 2e
#       APRES) : le retard se mesure sur la fin du DERNIER bloc.
# ---------------------------------------------------------------------------

def test_retard_mesure_sur_la_fin_du_dernier_bloc():
    tache = Tache(uuid="f", description="Fragmentee", due=DUE_INTENABLE)
    bloc1 = _bloc("f", DUE_INTENABLE - timedelta(hours=3),
                  DUE_INTENABLE - timedelta(hours=2))              # 13:00 < limite
    bloc2 = _bloc("f", DUE_INTENABLE + timedelta(hours=0),
                  DUE_INTENABLE + timedelta(hours=1))              # 17:00 > limite
    plan = _plan([bloc1, bloc2], en_retard=["f"])

    d = plan_en_dict(plan, taches=[tache], contextes=CONTEXTES)
    entree = d["taches"]["f"]

    assert entree["limite"] == DUE_INTENABLE.isoformat()
    assert entree["retard_minutes"] == 60


# ---------------------------------------------------------------------------
# 2ter. Chaine p -> q -> s : l'origine est la tache DATEE (s), pas le
#       successeur direct.
# ---------------------------------------------------------------------------

def test_limite_heritee_de_pointe_la_tache_datee_d_origine():
    s_ = Tache(uuid="s", description="Succ datee", due=DUE_INTENABLE,
               depends=("q",))
    q = Tache(uuid="q", description="Milieu", due=None, depends=("p",))
    p = Tache(uuid="p", description="Pred", due=None)

    plan = _plan([
        _bloc("s", DUE_INTENABLE - timedelta(minutes=30),
              DUE_INTENABLE + timedelta(hours=2)),
        _bloc("q", DUE_INTENABLE - timedelta(hours=1),
              DUE_INTENABLE + timedelta(hours=1)),
        _bloc("p", DUE_INTENABLE - timedelta(hours=2),
              DUE_INTENABLE + timedelta(minutes=30)),
    ], en_retard=["p", "q", "s"])

    d = plan_en_dict(plan, taches=[s_, q, p], contextes=CONTEXTES)

    assert d["taches"]["p"]["limite"] == DUE_INTENABLE.isoformat()
    assert d["taches"]["p"]["limite_heritee_de"] == "s"
    assert d["taches"]["q"]["limite_heritee_de"] == "s"

# ---------------------------------------------------------------------------
# 3. Tache a l'heure : aucun des trois champs.
# ---------------------------------------------------------------------------

def test_tache_a_l_heure_n_a_pas_de_champ_retard():
    due_large = datetime(2026, 12, 3, 16, 0)   # jeudi lointain, large marge
    tache = Tache(uuid="t3", description="A l'heure", due=due_large)
    bloc = _bloc("t3", T0 + timedelta(hours=10), T0 + timedelta(hours=11))
    plan = _plan([bloc], en_retard=[])   # "t3" n'est PAS en retard

    d = plan_en_dict(plan, taches=[tache], contextes=CONTEXTES)
    entree = d["taches"]["t3"]

    assert "retard_minutes" not in entree
    assert "limite" not in entree
    assert "limite_heritee_de" not in entree


# ---------------------------------------------------------------------------
# 3bis. Sans `contextes`, le format est STRICTEMENT inchange (compatibilite).
# ---------------------------------------------------------------------------

def test_sans_contextes_le_format_ne_bouge_pas():
    tache = Tache(uuid="x", description="Datee intenable", due=DUE_INTENABLE)
    bloc = _bloc("x", DUE_INTENABLE - timedelta(minutes=30),
                DUE_INTENABLE + timedelta(hours=2))
    plan = _plan([bloc], en_retard=["x"])

    d = plan_en_dict(plan, taches=[tache])   # contextes omis
    entree = d["taches"]["x"]

    assert "limite" not in entree
    assert "retard_minutes" not in entree
    assert "limite_heritee_de" not in entree
    assert d["version"] == 1


# ---------------------------------------------------------------------------
# 4. Bout en bout : `python -m planif` sur une base jetable, chaine forcee
#    en retard derriere un +external (motif "Monter assemblage", en plus
#    petit, construit ici -- ne touche pas tests/base_realiste.py).
# ---------------------------------------------------------------------------

def _tw(instant_local_naif):
    from datetime import timezone
    return instant_local_naif.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _lancer(env, cwd, *args):
    env = dict(env)
    env["PYTHONPATH"] = str(RACINE_DEPOT)
    return subprocess.run(
        [PYTHON, "-m", "planif", *args],
        capture_output=True, text=True, encoding="utf-8",
        env=env, cwd=str(cwd), check=False,
    )


def _ecrire(chemin, contenu):
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return chemin


def _config_large():
    """Grille `pro` largement ouverte tous les jours ouvres : la seule
    contrainte du scenario doit etre la duree de l'externe, jamais un manque
    de capacite pro."""
    jours_ouvres = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return {
        "timeSlots": {"pro": {j: ["08:00-18:00"] for j in jours_ouvres}
                             | {"Saturday": [], "Sunday": []}},
        "freeTimeHours": 0,
    }


def test_plan_json_bout_en_bout_porte_le_retard(base_jetable, tmp_path):
    """"ext" (+external, 10 jours) precede "succ" (due propre, dans 2 jours).
    10 jours d'externe ne peuvent structurellement pas tenir avant une
    echeance a 2 jours, quel que soit le jour reel d'execution : le retard
    est force, pas un artefact d'ordonnancement."""
    maintenant = datetime.now()
    due_succ = maintenant + timedelta(days=2)

    base_jetable.semer([
        {"uuid": "11111111-1111-1111-1111-111111111111",
         "description": "Delai fournisseur", "status": "pending",
         "entry": _tw(maintenant - timedelta(days=1)), "estTime": "P10D",
         "project": "NPD.test_retard", "tags": ["pro", "external"]},
        {"uuid": "22222222-2222-2222-2222-222222222222",
         "description": "Reception, datee intenable", "status": "pending",
         "entry": _tw(maintenant - timedelta(days=1)), "estTime": "PT1H",
         "project": "NPD.test_retard", "tags": ["pro"],
         "due": _tw(due_succ),
         "depends": ["11111111-1111-1111-1111-111111111111"]},
    ])

    config_path = _ecrire(tmp_path / "config.json", _config_large())
    echeances_path = _ecrire(tmp_path / "echeances.json", {})
    reunions_path = _ecrire(tmp_path / "reunions.json", [])
    sortie_path = tmp_path / "plan.json"

    resultat = _lancer(
        base_jetable.env, tmp_path,
        "--config", str(config_path),
        "--echeances", str(echeances_path),
        "--reunions", str(reunions_path),
        "--sortie", str(sortie_path),
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert sortie_path.exists()

    plan = json.loads(sortie_path.read_text(encoding="utf-8"))
    uuid_succ = "22222222-2222-2222-2222-222222222222"
    assert uuid_succ in plan["en_retard"], (
        "\"Reception, datee intenable\" doit apparaitre en_retard : {}"
        .format(plan["en_retard"]))

    entree = plan["taches"][uuid_succ]
    assert entree.get("retard_minutes", 0) > 0
    assert "limite" in entree

    # coherence interne : retard_minutes == fin du dernier bloc - limite,
    # recalcule a partir des SEULS champs du plan.json, sans rien halluciner
    # sur la config ou le tampon.
    fin = datetime.fromisoformat(entree["fin"])
    limite = datetime.fromisoformat(entree["limite"])
    attendu = round((fin - limite).total_seconds() / 60)
    assert entree["retard_minutes"] == attendu
