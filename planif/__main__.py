"""Ligne de commande de l'ordonnanceur — Lot A.

Usage : ``./venv/Scripts/python.exe -m planif [options]``.

Deroule (BRIEF-LOT-A.md) :

1. configuration + echeances de projet (``echeances.json``, optionnel) ;
2. taches ``status:pending`` (ou ``--filtre``) via ``planif.taskwarrior`` ;
3. echeances de projet appliquees ;
4. pre-verifications, rapport EN TETE de sortie ;
5. passe 1 (``resoudre``) sur les taches datees, passe 2 (``completer``) sur
   les non datees ;
6. ecriture du plan JSON, et de ``scheduled:`` seulement sur ``--ecrire-scheduled`` ;
7. resume final : blocs par regime, statut, retard, taches en retard, temps
   des deux passes.

Le garde-fou le plus important vit tout en haut de ``main()`` : sans ``TASKRC``
ni ``TASKDATA`` dans l'environnement, la commande refuse de demarrer avant
d'avoir touche quoi que ce soit (AGENTS.md §2, sur le modele de
``../WebTaskManager/playwright.config.js``).
"""
import argparse
import logging
import os
import shlex
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from planif.config import charger_config, charger_echeances
from planif.echeances import appliquer_echeances_projet
from planif.solveur import completer, resoudre
from planif.sortie import ecrire_json, ecrire_scheduled
from planif.stub_reunions import reunions as charger_reunions
from planif.taskwarrior import charger_taches
from planif.verifications import CODES, pre_verifications

__all__ = ["main", "verifier_isolation", "construire_analyseur",
           "formater_pre_verifications", "formater_resume"]

RACINE = Path(__file__).resolve().parent.parent
SORTIE_DEFAUT = RACINE / "plan.json"


class ErreurIsolation(SystemExit):
    """Levee quand l'environnement n'isole pas Taskwarrior (AGENTS.md §2)."""


def verifier_isolation(env):
    """Refuse de continuer si ni TASKRC ni TASKDATA ne sont poses dans `env`.

    C'est le garde-fou le plus important du lot (BRIEF-LOT-A.md) : appele en
    tout premier dans `main`, avant tout chargement de configuration et avant
    toute commande `task`. Le message nomme la variable a poser, sur le
    modele de `../WebTaskManager/playwright.config.js`.
    """
    if not env.get("TASKRC") and not env.get("TASKDATA"):
        raise ErreurIsolation(
            "TASKRC (ou TASKDATA) n'est pas defini : refus de demarrer pour ne "
            "pas ecrire dans la base Taskwarrior de production (synchronisee "
            "par Syncthing sur plusieurs machines, AGENTS.md §2).\n"
            "  Pose l'une des deux variables sur une base jetable avant de "
            "relancer, par exemple :\n"
            "    PC      : $env:TASKRC='C:/Users/irpaui/taskwarrior-dev/taskrc'\n"
            "    Termux  : export TASKRC=~/taskwarrior-staging/taskrc"
        )


def construire_analyseur():
    analyseur = argparse.ArgumentParser(
        prog="python -m planif",
        description="Ordonnanceur de projet par contraintes pour Taskwarrior.")
    analyseur.add_argument("--sortie", default=str(SORTIE_DEFAUT),
                           help="chemin du plan JSON en sortie "
                                "(defaut : {})".format(SORTIE_DEFAUT))
    analyseur.add_argument("--ecrire-scheduled", action="store_true",
                           help="ecrit scheduled: dans Taskwarrior ; sans cette "
                                "option on n'ecrit jamais dans la base")
    analyseur.add_argument("--ignorer-due-depassee", action="store_true",
                           help="exclut du plan les taches dont due est "
                                "anterieure a maintenant")
    analyseur.add_argument("--horizon-detaille", type=int, default=None,
                           metavar="JOURS",
                           help="frontiere du regime agrege, en jours "
                                "(defaut : celle de Config)")
    analyseur.add_argument("--horizon", type=int, default=90, metavar="JOURS",
                           help="fin de l'horizon total, en jours (defaut : 90)")
    analyseur.add_argument("--filtre", default="status:pending", metavar="EXPR",
                           help="filtre Taskwarrior (defaut : status:pending)")
    analyseur.add_argument("-v", action="store_true", dest="verbeux",
                           help="passe le journal a INFO (planif.solveur compris)")
    return analyseur


def _fmt_duree_creneaux(nb_creneaux, granularite):
    """Formate un nombre de creneaux (retard_total) en duree lisible."""
    duree = nb_creneaux * granularite
    total_minutes = int(duree.total_seconds() // 60)
    jours, reste = divmod(total_minutes, 24 * 60)
    heures, minutes = divmod(reste, 60)
    morceaux = []
    if jours:
        morceaux.append("{} j".format(jours))
    if heures:
        morceaux.append("{} h".format(heures))
    if minutes or not morceaux:
        morceaux.append("{} min".format(minutes))
    return " ".join(morceaux)


#: Nombre de taches citees nommement par anomalie. Au-dela, on donne le compte
#: et on s'arrete. Constate en lancant la CLI pour de vrai : sur la base de dev,
#: le rapport deversait 114 puis 148 noms sur une seule ligne chacun. Ce bloc
#: est la premiere chose lue chaque jour ; un mur de texte n'est pas un rapport.
#: Le COMPTE, lui, n'est jamais tronque -- c'est lui qui informe.
TACHES_CITEES = 6


def _abreger(message, nb_taches):
    """Ne garde que les premieres taches citees par un message d'anomalie.

    Les messages de `planif/verifications.py` ont tous la meme forme :
    une phrase, « : » ou « — », puis la liste des taches entre guillemets
    francais, separees par des virgules. On coupe dans cette liste plutot que
    de reformuler, pour que le texte reste celui du module qui sait de quoi il
    parle.
    """
    if nb_taches <= TACHES_CITEES:
        return message

    morceaux = message.rstrip(".").split("« ")
    if len(morceaux) <= TACHES_CITEES + 1:
        return message      # forme inattendue : on rend le message tel quel

    debut = "« ".join(morceaux[:TACHES_CITEES + 1]).rstrip(", ")
    return "{}… et {} autres.".format(debut, nb_taches - TACHES_CITEES)


def formater_pre_verifications(anomalies):
    """Le bloc de rapport, en tete de sortie (BRIEF-LOT-A.md §4)."""
    lignes = ["=== Pre-verifications ==="]
    if not anomalies:
        lignes.append("Aucune anomalie.")
        lignes.append("")
        return "\n".join(lignes)

    par_code = {}
    for anomalie in anomalies:
        par_code.setdefault(anomalie.code, []).append(anomalie)

    for code in CODES:
        anomalies_code = par_code.get(code)
        if not anomalies_code:
            continue
        nb_taches = sum(len(a.uuids) for a in anomalies_code)
        lignes.append("[{}] {} tache(s)".format(code, nb_taches))
        for anomalie in anomalies_code:
            lignes.append("  " + _abreger(anomalie.message, len(anomalie.uuids)))
    lignes.append("")
    return "\n".join(lignes)


def formater_resume(plan, taches, temps_passe1, temps_passe2):
    """Le resume final (BRIEF-LOT-A.md §7)."""
    par_uuid = {t.uuid: t for t in taches}
    n_heure = sum(1 for b in plan.blocs if not b.agrege)
    n_jour = sum(1 for b in plan.blocs if b.agrege)
    n_opportuniste = sum(1 for b in plan.blocs if b.opportuniste)

    lignes = ["=== Resume ==="]
    lignes.append("Blocs regime detaille (heure) : {}".format(n_heure))
    lignes.append("Blocs regime agrege (jour)    : {}".format(n_jour))
    lignes.append("Blocs regime opportuniste     : {}".format(n_opportuniste))
    lignes.append("Statut du solveur : {}".format(plan.statut))
    lignes.append("Retard total : {}".format(
        _fmt_duree_creneaux(plan.retard_total, plan.granularite)))
    if plan.en_retard:
        descriptions = ", ".join(
            "« {} »".format(par_uuid[u].description) if u in par_uuid else u
            for u in plan.en_retard)
        lignes.append("Taches en retard : {}".format(descriptions))
    else:
        lignes.append("Taches en retard : aucune")
    lignes.append("Temps de calcul passe 1 (resoudre) : {:.2f} s".format(temps_passe1))
    lignes.append("Temps de calcul passe 2 (completer) : {:.2f} s".format(temps_passe2))
    return "\n".join(lignes)


def main(argv=None):
    # AGENTS.md §5 : un encodage non explicite corrompt les accents sous
    # Windows. `print()` passe par `sys.stdout`, dont l'encodage par defaut
    # est la page de code de la console (souvent pas UTF-8) : on le force ici,
    # symetriquement a `encoding='utf-8'` explicite partout ou ce depot parle
    # a Taskwarrior.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    env = os.environ

    # --- garde-fou : rien ne se passe sans isolation (AGENTS.md §2) --------
    verifier_isolation(env)

    analyseur = construire_analyseur()
    args = analyseur.parse_args(argv)

    if args.verbeux:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # --- 1. configuration + echeances de projet -----------------------------
    echeances_projet = charger_echeances()
    config = charger_config(echeances_projet=echeances_projet)
    print("{} echeance(s) de projet chargee(s).".format(len(echeances_projet)))

    # --- 2. taches status:pending (ou --filtre) ------------------------------
    filtre = tuple(shlex.split(args.filtre))
    taches = charger_taches(filtre=filtre, env=env,
                            contextes_connus=config.contextes.keys())

    # --- 3. echeances de projet appliquees -----------------------------------
    taches = appliquer_echeances_projet(taches, echeances_projet)

    maintenant = datetime.now()

    # --- 4. pre-verifications, rapport EN TETE -------------------------------
    anomalies = pre_verifications(taches, config.contextes, maintenant)
    print(formater_pre_verifications(anomalies))

    if args.ignorer_due_depassee:
        avant = len(taches)
        taches = [t for t in taches
                  if t.due is None or t.due >= maintenant]
        retirees = avant - len(taches)
        print("--ignorer-due-depassee : {} tache(s) avec due depassee "
              "retiree(s) du plan.\n".format(retirees))

    # --- 5. passe 1 (datees) puis passe 2 (non datees) -----------------------
    t0 = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    horizon_fin = t0 + timedelta(days=args.horizon)
    horizon_detaille_jours = (args.horizon_detaille
                              if args.horizon_detaille is not None
                              else config.horizon_detaille.days)
    horizon_detaille_fin = t0 + timedelta(days=horizon_detaille_jours)
    reunions = charger_reunions(t0, horizon_fin)

    taches_datees = [t for t in taches if t.due is not None]
    taches_non_datees = [t for t in taches if t.due is None]

    debut_passe1 = time.perf_counter()
    plan = resoudre(taches_datees, config.contextes, t0, maintenant, horizon_fin,
                    config.granularite, reunions=reunions,
                    horizon_detaille_fin=horizon_detaille_fin)
    temps_passe1 = time.perf_counter() - debut_passe1

    debut_passe2 = time.perf_counter()
    plan = completer(plan, taches_non_datees, config.contextes, t0, maintenant,
                     horizon_fin, config.granularite, reunions=reunions,
                     horizon_detaille_fin=horizon_detaille_fin)
    temps_passe2 = time.perf_counter() - debut_passe2

    # --- 6. ecriture --------------------------------------------------------
    chemin_sortie = Path(args.sortie)
    change = ecrire_json(plan, chemin_sortie, taches=taches)
    print("Plan ecrit dans {} ({}).".format(
        chemin_sortie, "modifie" if change else "inchange"))

    if args.ecrire_scheduled:
        compte_rendu = ecrire_scheduled(plan, env=env)
        print("scheduled: {} modifiee(s), {} inchangee(s), {} ignoree(s).".format(
            len(compte_rendu["modifiees"]), len(compte_rendu["inchangees"]),
            len(compte_rendu["ignorees"])))

    # --- 7. resume ------------------------------------------------------------
    print()
    print(formater_resume(plan, taches, temps_passe1, temps_passe2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
