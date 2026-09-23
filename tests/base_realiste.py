"""Generateur de la base de test realiste (G1 / G1bis, RESTE-A-FAIRE.md).

Une seule horloge (celle du systeme, ou celle injectee via `aujourdhui`) : toutes
les dates de la base sont calculees RELATIVEMENT a cet instant, jamais en dur.
Voir RESTE-A-FAIRE.md §G1bis pour la justification (uuid stables, echeances en
« N-ieme vendredi/lundi a venir », regle de marge verifiee statiquement).

Ce module ne fait aucun appel a `datetime.now()` en dehors de la valeur par
defaut de `aujourdhui`.
"""
import json
import math
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

__all__ = ["Base", "generer", "semer"]

FORMAT_TW = "%Y%m%dT%H%M%SZ"

# Espace de noms constant pour les uuid5 : les uuid sont derives du nom (la
# description) de la tache, jamais de la date de generation -> determinisme
# d'un jour sur l'autre (G1bis point 3).
_NAMESPACE = uuid.UUID("3fae5b8c-13a4-4c1b-9f0e-6f2b1a6d9b2e")


@dataclass(frozen=True)
class Base:
    taches: list
    echeances: dict
    config: dict


def _uuid_pour(description):
    return str(uuid.uuid5(_NAMESPACE, description))


def _duree_iso(heures=None, jours=None):
    """Ecriture ISO-8601 acceptee par planif/duree.py (`PT...H...M` ou `P...D`)."""
    if jours is not None:
        return "P{}D".format(int(jours))
    minutes_total = round(heures * 60)
    h, m = divmod(minutes_total, 60)
    if h and m:
        return "PT{}H{}M".format(h, m)
    if h:
        return "PT{}H".format(h)
    return "PT{}M".format(m)


def _nieme_jour_a_venir(aujourdhui, jour_semaine, n):
    """La n-ieme date > aujourdhui dont weekday() == jour_semaine."""
    jour = aujourdhui
    trouves = 0
    while trouves < n:
        jour += timedelta(days=1)
        if jour.weekday() == jour_semaine:
            trouves += 1
    return jour


LUNDI, VENDREDI = 0, 4

# --- ages de creation (G1bis point 2) : quelques taches anciennes (> 365 j),
# les autres reparties de « quelques jours » a « quelques mois ». Cycle
# reutilise pour les ~50 taches de la base.
_CYCLE_AGES = [400, 20, 90, 45, 180, 10, 250, 420, 35, 150,
               60, 15, 200, 300, 25, 500, 80, 130, 5, 110,
               70, 160, 40, 220, 95]


def _grille_config():
    """Grilles de contexte (independantes de config.json, self-contenues dans
    la base). pro/perso reprennent les plages reelles ; sport est ajoute,
    simple, pour le scenario S7 (RESTE-A-FAIRE.md §G1bis)."""
    return {
        "pro": {
            "Monday": ["08:30-12:00", "14:00-18:30"],
            "Tuesday": ["08:30-12:00", "14:00-18:30"],
            "Wednesday": ["08:30-12:00", "14:00-18:30"],
            "Thursday": ["08:30-12:00", "14:00-18:30"],
            "Friday": ["08:30-12:00", "14:00-18:30"],
            "Saturday": [],
            "Sunday": [],
        },
        "perso": {
            "Monday": ["7:00-8:00", "18:40-19:30"],
            "Tuesday": ["7:00-8:00", "18:40-19:30"],
            "Wednesday": ["7:00-8:00", "18:40-19:30"],
            "Thursday": ["7:00-8:00", "18:40-19:30"],
            "Friday": ["7:00-8:00", "18:40-19:30"],
            "Saturday": ["7:00-12:00", "16:00-18:00"],
            "Sunday": ["7:00-12:00"],
        },
        "sport": {
            "Monday": [],
            "Tuesday": ["19:00-20:30"],
            "Wednesday": [],
            "Thursday": ["19:00-20:30"],
            "Friday": [],
            "Saturday": [],
            "Sunday": [],
        },
    }


def _specs(aujourdhui):
    """La liste des taches de la base, sous forme de specs legeres.

    Chaque spec : description (unique, sert de nom stable pour l'uuid5),
    project, tags, duree (heures= ou jours=), depends (descriptions),
    et optionnellement scheduled_offset (jours depuis aujourdhui).
    """
    specs = []

    # -----------------------------------------------------------------
    # S1 - deux livrables pour la meme revue (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : deux projets doivent etre prets pour la meme revue de
    # jalon. L'un est une chaine longue avec un delai fournisseur (+externe),
    # l'autre est une liste de petites verifications independantes. Les deux
    # partagent l'echeance : c'est le cas qui met les contextes en concurrence.
    # -----------------------------------------------------------------
    specs += [
        dict(description="Finaliser plan de detail axe pompe",
             project="NPD.Vulcan.revueA", tags=("pro",), heures=4),
        dict(description="Etablir devis fabrication axe pompe",
             project="NPD.Vulcan.revueA", tags=("pro",), heures=2,
             depends=("Finaliser plan de detail axe pompe",)),
        dict(description="Fabrication axe pompe",
             project="NPD.Vulcan.revueA", tags=("pro", "externe"), jours=18,
             depends=("Etablir devis fabrication axe pompe",)),
        dict(description="Controler reception axe pompe",
             project="NPD.Vulcan.revueA", tags=("pro",), heures=2,
             depends=("Fabrication axe pompe",)),
    ]
    for nom in ("Verifier tolerances plan ensemble",
                "Actualiser nomenclature carter",
                "Controler interference CAO",
                "Preparer dossier fabrication",
                "Verifier compatibilite norme CE",
                "Relire note de calcul preliminaire"):
        specs.append(dict(description=nom, project="NPD.Vulcan.revueB",
                           tags=("pro",), heures=2))

    # -----------------------------------------------------------------
    # S2 - projet facon Heliside.US (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : un projet a plusieurs sous-projets techniques
    # (plans, achats, essais). L'echeance porte sur la racine, pas sur
    # chaque sous-projet : c'est le cas qui exerce planif/echeances.py
    # (terminales calculees sur l'arbre entier).
    # -----------------------------------------------------------------
    specs += [
        dict(description="Plan de detail carter",
             project="NPD.Orion.plans", tags=("pro",), heures=6),
        dict(description="Devis fournisseur usinage carter",
             project="NPD.Orion.achats", tags=("pro",), heures=1,
             depends=("Plan de detail carter",)),
        dict(description="Essai fonctionnel carter",
             project="NPD.Orion.essais", tags=("pro",), heures=4,
             depends=("Devis fournisseur usinage carter",)),
    ]

    # -----------------------------------------------------------------
    # S3 - montage prototype (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : le montage d'un prototype ne peut demarrer qu'une
    # fois le plan pret ET les pieces sous-traitees ET le moteur commande
    # arrives : convergence de trois chaines, dont deux +externe.
    # -----------------------------------------------------------------
    specs += [
        dict(description="Plan de detail support moteur",
             project="NPD.Orion.plans", tags=("pro",), heures=5),
        dict(description="Usinage sous-traite support",
             project="NPD.Orion.achats", tags=("pro", "externe"), jours=15),
        dict(description="Commande moteur fournisseur",
             project="NPD.Orion.achats", tags=("pro", "externe"), jours=20),
        dict(description="Assembler prototype",
             project="NPD.Orion.montage", tags=("pro",), heures=8,
             depends=("Plan de detail support moteur",
                      "Usinage sous-traite support",
                      "Commande moteur fournisseur")),
    ]

    # -----------------------------------------------------------------
    # S4 - revue de conception validee (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : une revue de conception, une fois validee,
    # debloque plusieurs plans de detail et la note de calcul associee :
    # divergence, une tache dont plusieurs autres dependent.
    # -----------------------------------------------------------------
    specs += [
        dict(description="Revue de conception validee",
             project="NPD.Orion.concept", tags=("pro",), heures=0.5),
        dict(description="Plan de detail axe",
             project="NPD.Orion.plans", tags=("pro",), heures=5,
             depends=("Revue de conception validee",)),
        dict(description="Plan de detail flasque",
             project="NPD.Orion.plans", tags=("pro",), heures=4,
             depends=("Revue de conception validee",)),
        dict(description="Plan de detail joint",
             project="NPD.Orion.plans", tags=("pro",), heures=3,
             depends=("Revue de conception validee",)),
        dict(description="Note de calcul tenue mecanique",
             project="NPD.Orion.concept", tags=("pro",), heures=4,
             depends=("Revue de conception validee",)),
    ]

    # -----------------------------------------------------------------
    # S5 - losange entre sous-projets (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : un concept d'assemblage se decline en un plan et un
    # devis fournisseur en parallele, qui se rejoignent au montage. Traverse
    # deux sous-projets differents (.plans et .achats) vers un troisieme.
    # -----------------------------------------------------------------
    specs += [
        dict(description="Definir concept assemblage",
             project="NPD.Orion.concept", tags=("pro",), heures=3),
        dict(description="Plan de detail bati",
             project="NPD.Orion.plans", tags=("pro",), heures=6,
             depends=("Definir concept assemblage",)),
        dict(description="Devis fournisseur assemblage",
             project="NPD.Orion.achats", tags=("pro",), heures=2,
             depends=("Definir concept assemblage",)),
        dict(description="Monter assemblage",
             project="NPD.Orion.montage", tags=("pro",), heures=5,
             depends=("Plan de detail bati", "Devis fournisseur assemblage")),
    ]

    # -----------------------------------------------------------------
    # S6 - circuit d'achat (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : demande de devis -> commande -> fabrication sous-
    # traitee -> controle reception. Chaine utilisateur/externe/utilisateur/
    # externe (le devis et la fabrication sont +externe).
    # -----------------------------------------------------------------
    specs += [
        dict(description="Definir besoin outillage montage",
             project="NPD.Triton.outillage", tags=("pro",), heures=2),
        dict(description="Devis fournisseur outillage",
             project="NPD.Triton.outillage", tags=("pro", "externe", "serviceAchat"),
             jours=10, depends=("Definir besoin outillage montage",)),
        dict(description="Commander outillage montage",
             project="NPD.Triton.outillage", tags=("pro",), heures=1,
             depends=("Devis fournisseur outillage",)),
        dict(description="Fabrication outillage montage",
             project="NPD.Triton.outillage", tags=("pro", "externe"), jours=15,
             depends=("Commander outillage montage",)),
        dict(description="Controler reception outillage",
             project="NPD.Triton.outillage", tags=("pro",), heures=2,
             depends=("Fabrication outillage montage",)),
    ]

    # -----------------------------------------------------------------
    # S7 - travail non date (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : taches de fond, sans echeance ni dependance, dans
    # plusieurs contextes (pro, perso, sport) : le regime opportuniste.
    # -----------------------------------------------------------------
    for nom, h in (("Veille normes usinage", 2),
                   ("Lecture retour d'experience Orion", 1),
                   ("Mise a jour gabarit de calcul", 3),
                   ("Formation logiciel CAO", 4),
                   ("Archivage plans anciens projets", 1)):
        specs.append(dict(description=nom, project="NPD.veille",
                           tags=("pro",), heures=h))
    for nom, h in (("Entretien chaudiere", 2),
                   ("Tri des papiers administratifs", 1),
                   ("Reparation volet roulant", 3),
                   ("Achat mobilier bureau", 1),
                   ("Nettoyage garage", 2)):
        specs.append(dict(description=nom, project="Perso.maison",
                           tags=("perso",), heures=h))
    for nom, h in (("Seance de course a pied", 1),
                   ("Seance de musculation", 1),
                   ("Achat chaussures de trail", 0.5),
                   ("Inscription trail local", 0.5),
                   ("Preparation sac de course", 0.5)):
        specs.append(dict(description=nom, project="Sport.entrainement",
                           tags=("sport",), heures=h))

    # -----------------------------------------------------------------
    # S8 - echeance perso (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : un demenagement personnel a aussi une date limite ;
    # elle ne doit pas manger la capacite du contexte pro.
    # -----------------------------------------------------------------
    specs += [
        dict(description="Trouver logement",
             project="Perso.demenagement", tags=("perso",), heures=5),
        dict(description="Signer bail location",
             project="Perso.demenagement", tags=("perso",), heures=1,
             depends=("Trouver logement",)),
        dict(description="Organiser demenagement",
             project="Perso.demenagement", tags=("perso",), heures=3,
             depends=("Signer bail location",)),
    ]

    # -----------------------------------------------------------------
    # S9 - creneau impose (RESTE-A-FAIRE.md, tableau G1bis)
    # Situation reelle : une reunion client fixe un debut impose (+fige),
    # deux jours apres aujourd'hui.
    # -----------------------------------------------------------------
    specs.append(dict(description="Preparer salle reunion client",
                       project="NPD.reunions", tags=("pro", "fige"), heures=1,
                       scheduled_offset=2))

    # ages de creation, assignes dans l'ordre de construction (deterministe,
    # independant d'aujourd'hui : G1bis point 2)
    for i, spec in enumerate(specs):
        spec["age"] = _CYCLE_AGES[i % len(_CYCLE_AGES)]

    return specs


def _echeances(aujourdhui):
    # N choisis larges expres : la regle de marge (G1bis point 5) doit tenir
    # meme au pire des 7 jours de lancement possibles, une semaine de
    # capacite deja retranchee par la regle elle-meme n'etant pas suffisante
    # face a un delai +externe de plusieurs semaines dans la chaine.
    e1 = _nieme_jour_a_venir(aujourdhui, VENDREDI, 7)
    e2 = _nieme_jour_a_venir(aujourdhui, VENDREDI, 12)
    e3 = _nieme_jour_a_venir(aujourdhui, VENDREDI, 9)
    e4 = _nieme_jour_a_venir(aujourdhui, LUNDI, 8)
    return {
        "NPD.Vulcan.revueA": e1.isoformat(),
        "NPD.Vulcan.revueB": e1.isoformat(),
        "NPD.Orion": e2.isoformat(),
        "NPD.Triton.outillage": e3.isoformat(),
        "Perso.demenagement": e4.isoformat(),
    }


def generer(aujourdhui=None):
    """Rend la Base de test realiste, entierement relative a `aujourdhui`."""
    if aujourdhui is None:
        aujourdhui = date.today()

    specs = _specs(aujourdhui)
    index_uuid = {}
    for spec in specs:
        if spec["description"] in index_uuid:
            raise ValueError("description dupliquee : {!r}".format(spec["description"]))
        index_uuid[spec["description"]] = _uuid_pour(spec["description"])

    taches = []
    for spec in specs:
        entree = datetime.combine(aujourdhui, dtime(8, 0)) - timedelta(days=spec["age"])
        tache = {
            "uuid": index_uuid[spec["description"]],
            "description": spec["description"],
            "status": "pending",
            "entry": entree.strftime(FORMAT_TW),
            "project": spec["project"],
            "estTime": _duree_iso(heures=spec.get("heures"), jours=spec.get("jours")),
            "tags": list(spec["tags"]),
        }
        depends = spec.get("depends")
        if depends:
            tache["depends"] = [index_uuid[d] for d in depends]
        offset = spec.get("scheduled_offset")
        if offset is not None:
            planifie = datetime.combine(aujourdhui + timedelta(days=offset), dtime(9, 0))
            tache["scheduled"] = planifie.strftime(FORMAT_TW)
        taches.append(tache)

    config = {"timeSlots": _grille_config(), "freeTimeHours": 2}

    return Base(taches=taches, echeances=_echeances(aujourdhui), config=config)


# ---------------------------------------------------------------------------
# Semis dans une base Taskwarrior jetable
# ---------------------------------------------------------------------------

def _data_dir_de(taskrc_path):
    for ligne in Path(taskrc_path).read_text(encoding="utf-8").splitlines():
        if ligne.startswith("data.location="):
            return Path(ligne.split("=", 1)[1])
    raise RuntimeError("data.location introuvable dans {}".format(taskrc_path))


def semer(env_ou_taskrc, base):
    """Efface completement la base pointee par le taskrc et y importe `base`.

    Refuse (leve une exception, n'importe RIEN) si le dossier de donnees ne
    porte pas de fichier temoin `.jetable` -- voir l'en-tete du contrat de
    test et AGENTS.md §3 : on n'ecrit jamais dans une base Taskwarrior qui
    n'a pas explicitement ete marquee jetable.
    """
    if isinstance(env_ou_taskrc, dict):
        env = dict(env_ou_taskrc)
        taskrc_path = Path(env["TASKRC"])
    else:
        taskrc_path = Path(env_ou_taskrc)
        env = dict(os.environ)
        env["TASKRC"] = str(taskrc_path)
        env.pop("TASKDATA", None)

    dossier_donnees = _data_dir_de(taskrc_path)
    if not (dossier_donnees / ".jetable").exists():
        raise RuntimeError(
            "refus de semer : {} ne porte pas de fichier .jetable, "
            "ce n'est peut-etre pas une base jetable".format(dossier_donnees))

    # effacement complet : Taskwarrior 3 range les taches dans
    # taskchampion.sqlite3 (+ eventuels -wal/-shm), plus les anciens *.data
    # selon la version -- on vide donc tout le dossier de donnees, sauf le
    # fichier .jetable qui autorise ce nettoyage. On reste strictement dans
    # ce dossier (jamais de remontee via ..) : le refus ci-dessus a deja eu
    # lieu, rien n'est supprime si .jetable est absent.
    for entree in dossier_donnees.iterdir():
        if entree.name == ".jetable":
            continue
        if entree.is_dir():
            shutil.rmtree(entree)
        else:
            entree.unlink()

    fichier_seed = dossier_donnees / "_seed_base_realiste.json"
    fichier_seed.write_text(json.dumps(base.taches, ensure_ascii=False), encoding="utf-8")
    try:
        res = subprocess.run(
            ["task", "import", str(fichier_seed)],
            capture_output=True, text=True, encoding="utf-8", env=env, check=False,
        )
        if res.returncode != 0:
            raise RuntimeError("task import a echoue ({}) : {}".format(
                res.returncode, res.stderr.strip()))
    finally:
        try:
            fichier_seed.unlink()
        except OSError:
            pass
