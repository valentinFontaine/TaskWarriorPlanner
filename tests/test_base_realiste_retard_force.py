"""Contrat de test pour l'integration, dans `tests/base_realiste.py`, des
modifications que l'utilisateur a faites A LA MAIN dans sa base de test reelle
(bases de reference : `export_all.json`, `base_generee.json`, `plan.json`,
`verif2_out.txt` du scratchpad de la session -- mesure de reference deja
obtenue par l'utilisateur avec le vrai solveur).

`tests/base_realiste.py` N'EST PAS MODIFIE PAR CE FICHIER : c'est un contrat,
a satisfaire par une implementation dans ce module. Ce docstring (jusqu'a la
ligne "FIN DE LA SPEC A REPORTER") est la SPEC DU SCENARIO que l'implementeur
doit reporter, telle quelle ou reformulee fidelement, dans l'en-tete ou les
commentaires de `tests/base_realiste.py`, a cote des sections qu'elle modifie.

SPEC DU SCENARIO -- RETARD FORCE (voulu)
==========================================

C'est un scenario de retard FORCE, pas un bug a corriger : une dependance
ajoutee tardivement (par l'utilisateur, a la main, dans sa vraie base) rend une
echeance qui etait tenable intenable. Le but de la base de test est de fixer ce
cas pour qu'il reste rouge (en retard) tant que le solveur ne change pas de
comportement, pas de le rendre vert.

1. Cinq dependances (pred -> succ), ajoutees A CELLES QUI EXISTENT DEJA (aucune
   des dependances actuelles de S3/S4/S5 n'est retiree) :

   - "Plan de detail axe"        -> "Assembler prototype"
   - "Plan de detail joint"      -> "Assembler prototype"
   - "Plan de detail flasque"    -> "Assembler prototype"
   - "Essai fonctionnel carter"  -> "Assembler prototype"
   - "Assembler prototype"       -> "Monter assemblage"

   Consequence structurelle : "Assembler prototype" n'est plus terminale de
   NPD.Orion (Monter assemblage lui succede desormais) ; le plus long chemin
   qui passe par "Commande moteur fournisseur" (+externe, P20D) se retrouve
   reporte sur "Monter assemblage".

2. Un `due` PROPRE (pas une echeance de projet) sur deux taches, ecrit au
   format Taskwarrior UTC (`FORMAT_TW`), pour une heure locale de 18:00 -- donc
   `datetime.combine(jour_du_vendredi, dtime(18, 0)).astimezone(timezone.utc)
   .strftime(FORMAT_TW)` (meme convention que `tests/test_ecriture_due.py`,
   PAS la conversion naive-directe utilisee ailleurs dans ce module pour
   `scheduled` -- l'heure locale affichee doit etre 18:00, pas l'heure UTC) :

   - "Monter assemblage" [NPD.Orion.montage] : le N-ieme VENDREDI a venir avec
     N=3 (`_nieme_jour_a_venir(aujourdhui, VENDREDI, 3)`). Choisi pour que,
     QUEL QUE SOIT le jour de lancement parmi les 7 (meme fenetre que
     `tests/test_base_realiste.py`, `LUNDI_FIXE` + 6 jours), le retard soit
     TOUJOURS force : mesure ici avec le calcul grossier deja outille par
     `tests/test_base_realiste.py` (chemin le plus long jusqu'a la tache,
     simule jour par jour) -- la marge rendue par `_marge_chemin_critique` est
     negative pour les 7 jours (constate : -11 a -5 j selon le jour de
     lancement, deriv, sur la fenetre LUNDI_FIXE ; -5 j avec la date reelle du
     jour ou ce contrat a ete ecrit). Une due plus proche (N=1 ou 2) force le
     retard avec une marge encore plus negative mais s'eloigne de l'ordre de
     grandeur mesure par l'utilisateur avec le vrai solveur (2,7 a 4,7 j de
     retard) ; une due plus lointaine (N=4) n'est PLUS forcee sur tous les
     jours de lancement (marge positive un jour sur 7 dans la fenetre testee).
     N=3 est donc la valeur la PLUS PETITE qui reste a la fois proche de
     l'ordre de grandeur reel et robuste sur les 7 jours.
   - "Controler reception axe pompe" [NPD.Vulcan.revueA] : le N-ieme vendredi
     a venir avec N=6 (~6 semaines). Choisi TENABLE sur les 7 jours de
     lancement avec la MEME regle de marge que le reste de la base (marge
     `_marge_chemin_critique` >= 7 j) : constate >= 10 j sur la fenetre
     LUNDI_FIXE, 17 j avec la date reelle du jour ou ce contrat a ete ecrit.
     N=5 ne suffit pas (marge aussi basse que 3 j un jour sur 7).

3. La tache "test ajout VF" est un essai personnel de l'utilisateur, PAS a
   integrer : `generer()` ne doit produire aucune tache de ce nom.

CONFLIT POTENTIEL AVEC LES PROPRIETES EXISTANTES -- ANALYSE, PAS DE MODIFICATION
==================================================================================

`tests/test_base_realiste.py` a deux proprietes qui supposent (implicitement)
que la base est tenable : `test_regle_de_marge_travail_utilisateur_sous_capacite`
et `test_regle_de_marge_chemin_critique_laisse_une_semaine`. Analyse (voir le
rapport de l'agent qui a ecrit ce contrat pour le detail des calculs) : NI L'UNE
NI L'AUTRE n'est mise en defaut par ce scenario, et ELLES NE SONT PAS MODIFIEES
ICI. Raison structurelle, dans les deux cas :

- les deux taches qui recoivent un `due` propre ("Monter assemblage",
  "Controler reception axe pompe") appartiennent chacune a un projet deja
  couvert par une cle de `base.echeances` (NPD.Orion, NPD.Vulcan.revueA) ;
- le filtre de ces deux proprietes pour les taches a `due` propre
  (`_projet_racine_de(t["project"], base.echeances) is not None: continue`)
  les EXCLUT donc de la branche qui testerait la tenabilite de LEUR PROPRE due ;
- la branche qui s'applique a elles est celle des echeances DE PROJET
  (NPD.Orion = 12e vendredi, NPD.Vulcan.revueA = 7e vendredi), choisies dans
  `_echeances()` avec une marge tres large (voir le commentaire de
  `_echeances()`) ; le travail total (§ capacite) ne change pas (les 5
  dependances ajoutees ne changent aucune duree, seulement l'ordre), et le plus
  long chemin jusqu'a la nouvelle terminale de NPD.Orion ("Monter assemblage"
  remplace "Assembler prototype" comme terminale, chemin quasi identique,
  +5 h) reste tres en-dessous de la marge de 12 semaines.

Donc : aucune propriete existante n'est rouge a cause de ce scenario. Si une
future modification de la base venait a le rendre faux, ce serait le signe que
la marge de `_echeances()` (S1/S2, e1/e2) est devenue trop juste -- pas que ce
scenario est en cause.

FIN DE LA SPEC A REPORTER
==========================

INTERFACE DE CE FICHIER DE TEST
================================

Reutilise `tests/test_base_realiste.py` comme bibliotheque (memes fonctions
utilitaires : `_index_par_uuid`, `_marge_chemin_critique`, `_tw_vers_date`,
`_est_externe`...), sur le meme jeu de 7 jours de lancement
(`LUNDI_FIXE = date(2026, 10, 5)` + 6 jours), pour ne pas dupliquer la logique
de simulation de marge.
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tests.base_realiste import generer, semer  # noqa: E402
import tests.test_base_realiste as T  # noqa: E402

PYTHON = sys.executable
LUNDI_FIXE = T.LUNDI_FIXE
JOURS_DE_LANCEMENT = T.JOURS_DE_LANCEMENT

# Les 5 dependances ajoutees par l'utilisateur (pred -> succ, par description).
DEPENDANCES_AJOUTEES = (
    ("Plan de detail axe", "Assembler prototype"),
    ("Plan de detail joint", "Assembler prototype"),
    ("Plan de detail flasque", "Assembler prototype"),
    ("Essai fonctionnel carter", "Assembler prototype"),
    ("Assembler prototype", "Monter assemblage"),
)

NOM_MONTER = "Monter assemblage"
NOM_CONTROLER = "Controler reception axe pompe"
NOM_ESSAI_UTILISATEUR = "test ajout VF"

# marge minimale exigee pour "tenable", identique a
# tests/test_base_realiste.py:test_regle_de_marge_chemin_critique_laisse_une_semaine
MARGE_MIN_TENABLE = 7


def _index_par_description(taches):
    return {t["description"]: t for t in taches}


# ---------------------------------------------------------------------------
# 1. Integration des cinq dependances, absence de "test ajout VF"
# ---------------------------------------------------------------------------

def test_les_cinq_dependances_ajoutees_existent():
    base = generer(LUNDI_FIXE)
    par_desc = _index_par_description(base.taches)

    for nom_pred, nom_succ in DEPENDANCES_AJOUTEES:
        assert nom_pred in par_desc, "tache manquante : {!r}".format(nom_pred)
        assert nom_succ in par_desc, "tache manquante : {!r}".format(nom_succ)
        pred_uuid = par_desc[nom_pred]["uuid"]
        succ = par_desc[nom_succ]
        assert pred_uuid in succ.get("depends", ()), (
            "{!r} ne depend pas (encore) de {!r}".format(nom_succ, nom_pred))


def test_essai_utilisateur_non_integre():
    base = generer(LUNDI_FIXE)
    descriptions = {t["description"] for t in base.taches}
    assert NOM_ESSAI_UTILISATEUR not in descriptions


# ---------------------------------------------------------------------------
# 2. Retard force sur "Monter assemblage", statique sur les 7 jours
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("jour", JOURS_DE_LANCEMENT)
def test_monter_assemblage_retard_force(jour):
    """Calcul grossier (meme outillage que test_base_realiste.py) : la marge
    du plus long chemin jusqu'a "Monter assemblage" (chemin qui passe par
    "Commande moteur fournisseur", +externe P20D, puis "Assembler prototype")
    face a son `due` propre est NEGATIVE -- le retard est force, pas une
    consequence d'un ordonnancement sous-optimal."""
    base = generer(jour)
    par_desc = _index_par_description(base.taches)
    cible = par_desc[NOM_MONTER]
    assert cible.get("due"), "Monter assemblage doit porter un due propre"

    index_uuid = T._index_par_uuid(base.taches)
    contextes_connus = set(base.config["timeSlots"])
    lendemain = jour + timedelta(days=1)
    E = T._tw_vers_date(cible["due"])

    marge = T._marge_chemin_critique(base, contextes_connus, index_uuid,
                                     cible["uuid"], E, lendemain)
    assert marge < 0, (jour, E, marge)


# ---------------------------------------------------------------------------
# 3. "Controler reception axe pompe" reste tenable, statique sur les 7 jours
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("jour", JOURS_DE_LANCEMENT)
def test_controler_reception_axe_pompe_reste_tenable(jour):
    """Meme regle de marge (>= 7 j) que
    test_regle_de_marge_chemin_critique_laisse_une_semaine, appliquee au due
    propre de "Controler reception axe pompe" (chaine : Finaliser plan ->
    Etablir devis -> Fabrication axe pompe [+externe P18D] -> elle-meme)."""
    base = generer(jour)
    par_desc = _index_par_description(base.taches)
    cible = par_desc[NOM_CONTROLER]
    assert cible.get("due"), "Controler reception axe pompe doit porter un due propre"

    index_uuid = T._index_par_uuid(base.taches)
    contextes_connus = set(base.config["timeSlots"])
    lendemain = jour + timedelta(days=1)
    E = T._tw_vers_date(cible["due"])

    marge = T._marge_chemin_critique(base, contextes_connus, index_uuid,
                                     cible["uuid"], E, lendemain)
    assert marge >= MARGE_MIN_TENABLE, (jour, E, marge)


# ---------------------------------------------------------------------------
# 4. Bout en bout : le vrai solveur, sur une base jetable
# ---------------------------------------------------------------------------

def _lancer_planif(env, *args, cwd=None):
    return subprocess.run(
        [PYTHON, "-m", "planif", *args],
        capture_output=True, text=True, encoding="utf-8",
        env=env, cwd=str(cwd or RACINE), check=False,
    )


def test_plan_final_montre_le_retard_force_sans_violation(base_jetable, tmp_path):
    base = generer()  # date du jour reel : coherent avec l'horloge du solveur
    donnees = Path(base_jetable.taskrc).read_text(encoding="utf-8")
    dossier_donnees = None
    for ligne in donnees.splitlines():
        if ligne.startswith("data.location="):
            dossier_donnees = Path(ligne.split("=", 1)[1])
    assert dossier_donnees is not None
    (dossier_donnees / ".jetable").write_text("test", encoding="utf-8")

    semer(base_jetable.env, base)

    config_path = tmp_path / "config.json"
    echeances_path = tmp_path / "echeances.json"
    reunions_path = tmp_path / "reunions.json"
    sortie_path = tmp_path / "plan.json"
    config_path.write_text(json.dumps(base.config, ensure_ascii=False), encoding="utf-8")
    echeances_path.write_text(json.dumps(base.echeances, ensure_ascii=False), encoding="utf-8")
    reunions_path.write_text("[]", encoding="utf-8")

    resultat = _lancer_planif(
        base_jetable.env,
        "--config", str(config_path),
        "--echeances", str(echeances_path),
        "--reunions", str(reunions_path),
        "--sortie", str(sortie_path),
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    assert sortie_path.exists()

    plan = json.loads(sortie_path.read_text(encoding="utf-8"))
    assert plan["statut"] != "INFEASIBLE", plan["statut"]

    par_desc = _index_par_description(base.taches)
    uuid_monter = par_desc[NOM_MONTER]["uuid"]
    assert uuid_monter in plan["en_retard"], (
        "\"Monter assemblage\" doit apparaitre en_retard : {}".format(plan["en_retard"]))

    # aucune violation de precedence : fin(pred) <= debut(succ) pour toute
    # tache planifiee qui porte un `depends`
    par_uuid_base = {t["uuid"]: t for t in base.taches}
    taches_planifiees = plan["taches"]
    violations = []
    for uuid, entree in taches_planifiees.items():
        tache_source = par_uuid_base.get(uuid)
        if tache_source is None:
            continue
        for pred_uuid in tache_source.get("depends", ()):
            pred_entree = taches_planifiees.get(pred_uuid)
            if pred_entree is None:
                continue
            fin_pred = datetime.fromisoformat(pred_entree["fin"])
            debut_succ = datetime.fromisoformat(entree["debut"])
            if fin_pred > debut_succ:
                violations.append((pred_uuid, uuid, fin_pred, debut_succ))
    assert not violations, violations
