"""Ligne de commande de l'ordonnanceur — Lot A.

Usage : ``./venv/Scripts/python.exe -m planif [options]``.

``--config``, ``--echeances`` et ``--reunions`` permettent de viser des chemins
explicites (par exemple une base de test) au lieu des defauts (``config.json``
et ``echeances.json`` a cote du paquet, ``reunions.json`` du repertoire
courant). Un chemin explicite absent est une erreur, avant tout calcul et
avant toute ecriture de plan ; sans option, les fichiers restent optionnels
comme avant.

Deroule (BRIEF-LOT-A.md) :

1. configuration + echeances de projet (``echeances.json``, optionnel) ;
2. taches ``status:pending`` (ou ``--filtre``) via ``planif.taskwarrior`` ;
3. echeances de projet appliquees ;
4. pre-verifications, rapport EN TETE de sortie ;
5. passe 1 (``resoudre``) sur les taches datees, passe 2 (``completer``) sur
   les non datees ;
6. ecriture du plan JSON, de ``scheduled:`` seulement sur ``--ecrire-scheduled``,
   et de ``due:``/``duePlanif:`` seulement sur ``--ecrire-due`` ;
7. resume final : blocs par regime, statut, retard, taches en retard, temps
   des deux passes.

Le garde-fou le plus important vit tout en haut de ``main()`` : sans ``TASKRC``
ni ``TASKDATA`` dans l'environnement, la commande refuse de demarrer avant
d'avoir touche quoi que ce soit (AGENTS.md §2, sur le modele de
``../WebTaskManager/playwright.config.js``).

``--appliquer <plan.json>`` (Nuit 3, etape 3) est un mode a part : celui du
bouton Valider (E4). Il n'existe QUE pour ecrire dans Taskwarrior exactement
le plan qu'un ``plan.json`` deja ecrit contient -- pas un plan recalcule
entre-temps, qui pourrait differer de ce que l'utilisateur a regarde a
l'ecran avant de cliquer. Il ne charge donc ni config, ni echeances, ni
reunions, ne lance pas le solveur : il relit le fichier, reconstruit un
``planif.solveur.Plan`` a partir de son contenu, et appelle
``ecrire_scheduled``/``ecrire_due`` comme le ferait ``--ecrire-scheduled``/
``--ecrire-due`` -- avec lesquels il est donc mutuellement exclusif, les deux
voies d'ecriture ne se melangent pas. Il ne pose jamais ``+fige`` : c'est E3
(``+fige``) qui le fait, ailleurs.
"""
import argparse
import json
import logging
import os
import shlex
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from planif.config import charger_config, charger_echeances
from planif.echeances import appliquer_echeances_projet
from planif.calendrier import indice_creneau
from planif.selection import capacite_restante, selectionner_candidates
from planif.solveur import Bloc, Plan, completer, resoudre
from planif.dues import oublier_dues_calculees
from planif.sortie import ecrire_due, ecrire_json, ecrire_scheduled
from planif.reunions import reunions as charger_reunions
from planif.tampon import limites_effectives
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
    analyseur.add_argument("--appliquer", default=None, metavar="CHEMIN",
                           help="applique un plan.json deja ecrit, sans rien "
                                "recalculer (bouton Valider, E4) ; incompatible "
                                "avec --ecrire-scheduled et --ecrire-due")
    analyseur.add_argument("--ecrire-scheduled", action="store_true",
                           help="ecrit scheduled: dans Taskwarrior ; sans cette "
                                "option on n'ecrit jamais dans la base")
    analyseur.add_argument("--ecrire-due", action="store_true",
                           help="ecrit due: et duePlanif: dans Taskwarrior ; "
                                "sans cette option on n'ecrit jamais dans la "
                                "base")
    analyseur.add_argument("--ignorer-due-depassee", action="store_true",
                           help="exclut du plan les taches dont due est "
                                "anterieure a maintenant")
    analyseur.add_argument("--horizon-detaille", type=int, default=None,
                           metavar="JOURS",
                           help="frontiere du regime agrege, en jours "
                                "(defaut : celle de Config)")
    analyseur.add_argument("--horizon", type=int, default=90, metavar="JOURS",
                           help="fin de l'horizon total, en jours (defaut : 90)")
    analyseur.add_argument("--horizon-opportuniste", type=int, default=21,
                           metavar="JOURS",
                           help="horizon de la passe 2, en jours (defaut : 21). "
                                "C'est le reglage qui gouverne sa performance : "
                                "a 90 jours elle ne place RIEN, a 21 elle place "
                                "135 taches sur 147 (mesure sur 278 taches "
                                "reelles). Et c'est juste sur le fond : remplir "
                                "avec des taches non datees trois mois a "
                                "l'avance n'a aucun sens.")
    analyseur.add_argument("--filtre", default="status:pending", metavar="EXPR",
                           help="filtre Taskwarrior (defaut : status:pending)")
    analyseur.add_argument("--config", default=None, metavar="CHEMIN",
                           help="chemin de config.json (defaut : celui de "
                                "planif.config, a cote du paquet)")
    analyseur.add_argument("--echeances", default=None, metavar="CHEMIN",
                           help="chemin de echeances.json (defaut : celui de "
                                "planif.config, a cote du paquet ; fichier "
                                "optionnel)")
    analyseur.add_argument("--reunions", default=None, metavar="CHEMIN",
                           help="chemin de l'agenda (defaut : reunions.json du "
                                "repertoire courant ; fichier optionnel)")
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


def _retards_par_tache(plan, taches, contextes):
    """Le retard de CHAQUE tache en retard, en creneaux.

    `Plan` ne porte que la somme (`retard_total`), qui n'apprend rien : sur les
    donnees reelles elle valait « 1448 j 4 h 30 » pour treize taches dont
    certaines dataient de mai. On recalcule donc le detail, a partir des memes
    limites effectives que le solveur, pour en tirer un maximum et une mediane.
    """
    limites = limites_effectives(taches, contextes)
    retards = []
    for uuid in plan.en_retard:
        limite = limites.get(uuid)
        fin = plan.fin(uuid)
        if limite is None or fin is None:
            continue
        borne = indice_creneau(plan.t0, limite, plan.granularite)
        fin_indice = indice_creneau(plan.t0, fin, plan.granularite)
        retards.append(max(0, fin_indice - borne))
    return retards


def formater_resume(plan, taches, temps_passe1, temps_passe2,
                    candidates_passe2=None, retards_par_tache=None,
                    ecartees_passe2=None):
    """Le resume final (BRIEF-LOT-A.md §7).

    Deux corrections nees d'une execution sur les donnees reelles :

    - **un resultat par passe.** Le resume annoncait « Statut : OPTIMAL » alors
      que la passe 2 n'avait rien place du tout. Les deux faits etaient vrais
      separement -- le statut affiche etait celui de la passe 1 -- et
      l'ensemble etait trompeur. `Plan` ne porte qu'un statut, alors on compte
      ce que la passe 2 a place face a ce qu'on lui a soumis : c'est plus
      parlant qu'un mot-cle CP-SAT.
    - **un retard exploitable.** « Retard total : 1448 j 4 h 30 » est exact et
      n'apprend rien : c'est la somme des retards de treize taches dont
      certaines datent de mai. Le maximum dit l'urgence, la mediane dit si
      c'est general ou si une seule tache tire tout.
    """
    par_uuid = {t.uuid: t for t in taches}
    n_heure = sum(1 for b in plan.blocs if not b.agrege)
    n_jour = sum(1 for b in plan.blocs if b.agrege)
    n_opportuniste = sum(1 for b in plan.blocs if b.opportuniste)
    uuids_opportunistes = {b.uuid for b in plan.blocs if b.opportuniste}

    lignes = ["=== Resume ==="]
    lignes.append("Blocs regime detaille (heure) : {}".format(n_heure))
    lignes.append("Blocs regime agrege (jour)    : {}".format(n_jour))
    lignes.append("Blocs regime opportuniste     : {}".format(n_opportuniste))
    lignes.append("Passe 1 (travail date) : {} — {} tache(s) placee(s)".format(
        plan.statut, len({b.uuid for b in plan.blocs} - uuids_opportunistes)))
    if plan.statut == "FEASIBLE":
        # `FEASIBLE` est un code CP-SAT, pas une phrase. Depuis que le critere
        # d'arret est un budget de TRAVAIL et non une horloge (voir
        # `planif.solveur.TEMPS_DETERMINISTE_MAX`), il a une traduction stable,
        # et rassurante : la recherche a depense son budget sans prouver
        # qu'elle ne pouvait pas mieux faire. Le plan est valide, et il sera le
        # meme a la prochaine execution.
        lignes.append("  FEASIBLE : budget de calcul epuise sans preuve "
                      "d'optimalite. Le plan est valide et reproductible, "
                      "simplement pas demontre le meilleur.")
    if candidates_passe2 is not None:
        ligne = "Passe 2 (opportuniste) : {} tache(s) placee(s) sur {} soumise(s)".format(
            len(uuids_opportunistes), candidates_passe2)
        if candidates_passe2 and not uuids_opportunistes:
            ligne += "  <-- AUCUNE : le solveur n'a rien trouve dans le temps imparti"
        lignes.append(ligne)
    if ecartees_passe2:
        lignes.append("  {} tache(s) ecartee(s) avant le solveur, faute de "
                      "capacite sur l'horizon.".format(ecartees_passe2))

    retards = list(retards_par_tache or ())
    if retards:
        retards.sort()
        milieu = len(retards) // 2
        mediane = (retards[milieu] if len(retards) % 2
                   else (retards[milieu - 1] + retards[milieu]) / 2)
        lignes.append("Retard : max {} | median {} | {} tache(s) concernee(s)".format(
            _fmt_duree_creneaux(max(retards), plan.granularite),
            _fmt_duree_creneaux(int(mediane), plan.granularite),
            len(retards)))
    else:
        lignes.append("Retard : aucun")
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


def _plan_depuis_fichier(donnees):
    """Reconstruit un `planif.solveur.Plan` a partir d'un `plan.json` deja ecrit.

    Aucun calcul : chaque bloc est repris tel quel, converti en indices de
    creneaux via `planif.calendrier.indice_creneau`. `statut`, `retard_total`
    et `en_retard` sont repris du fichier, pas recalcules.
    """
    t0 = datetime.fromisoformat(donnees["t0"])
    granularite = timedelta(minutes=donnees["granularite_minutes"])
    blocs = []
    for uuid, entree in donnees["taches"].items():
        for bloc in entree["blocs"]:
            blocs.append(Bloc(
                uuid=uuid,
                indice=bloc["indice"],
                debut=indice_creneau(t0, datetime.fromisoformat(bloc["debut"]),
                                     granularite),
                fin=indice_creneau(t0, datetime.fromisoformat(bloc["fin"]),
                                   granularite),
                externe=bool(bloc["externe"]),
                agrege=bool(bloc["agrege"]),
                opportuniste=bool(bloc["opportuniste"]),
            ))
    return Plan(blocs=tuple(blocs), t0=t0, granularite=granularite,
               statut=donnees["statut"], retard_total=donnees["retard_total"],
               en_retard=tuple(donnees["en_retard"]))


def _appliquer(chemin_arg, env, analyseur):
    """Le mode `--appliquer` : lit un `plan.json`, l'ecrit tel quel, sans calcul.

    Voir la docstring du module : c'est ce que lance Valider (E4).
    """
    chemin = Path(chemin_arg)
    if not chemin.exists():
        analyseur.error("--appliquer : fichier introuvable : {}".format(chemin))

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if donnees.get("version") != 1:
        analyseur.error(
            "--appliquer : version de plan non prise en charge ({}), "
            "seule la version 1 est lue : {}".format(
                donnees.get("version"), chemin))

    plan = _plan_depuis_fichier(donnees)
    taches = charger_taches(filtre=("status:pending",), env=env)

    dues = {uuid: datetime.fromisoformat(entree["due"])
           for uuid, entree in donnees["taches"].items()
           if entree.get("due") is not None}

    compte_scheduled = ecrire_scheduled(plan, env=env)
    compte_due = ecrire_due(plan, taches, env=env, dues=dues)

    print(json.dumps({"scheduled": compte_scheduled, "due": compte_due}))
    return 0


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

    if args.appliquer is not None:
        if args.ecrire_scheduled or args.ecrire_due:
            analyseur.error(
                "--appliquer ne se combine pas avec --ecrire-scheduled ni "
                "--ecrire-due : les deux voies d'ecriture ne se melangent pas.")
        return _appliquer(args.appliquer, env, analyseur)

    # --- garde-fou : un chemin EXPLICITE absent est une erreur, pas un fichier
    # optionnel (contrairement au defaut d'echeances/reunions). Avant tout
    # calcul et avant toute ecriture de plan.
    for option, chemin in (("--config", args.config),
                           ("--echeances", args.echeances),
                           ("--reunions", args.reunions)):
        if chemin is not None and not Path(chemin).exists():
            analyseur.error("{} : fichier introuvable : {}".format(option, chemin))

    if args.verbeux:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # --- 1. configuration + echeances de projet -----------------------------
    echeances_projet = charger_echeances(chemin=args.echeances)
    config = charger_config(chemin=args.config, echeances_projet=echeances_projet)
    print("{} echeance(s) de projet chargee(s).".format(len(echeances_projet)))

    # --- 2. taches status:pending (ou --filtre) ------------------------------
    filtre = tuple(shlex.split(args.filtre))
    taches = charger_taches(filtre=filtre, env=env,
                            contextes_connus=config.contextes.keys())
    # les `due` que NOUS avons ecrites au run precedent ne sont pas des
    # engagements : sans cet oubli, le plan se figerait sur sa propre sortie
    # de la veille (planif/dues.py::oublier_dues_calculees).
    taches = oublier_dues_calculees(taches)

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
    reunions = charger_reunions(t0, horizon_fin, source=args.reunions)

    taches_datees = [t for t in taches if t.due is not None]
    taches_non_datees = [t for t in taches if t.due is None]

    debut_passe1 = time.perf_counter()
    plan = resoudre(taches_datees, config.contextes, t0, maintenant, horizon_fin,
                    config.granularite, reunions=reunions,
                    horizon_detaille_fin=horizon_detaille_fin)
    temps_passe1 = time.perf_counter() - debut_passe1

    # Ce que la passe 1 a consomme, par contexte : c'est ce qu'il faut retirer
    # de la capacite avant de decider combien de candidates soumettre.
    par_uuid = {t.uuid: t for t in taches}
    deja_pris = {}
    for bloc in plan.blocs:
        if bloc.externe:
            continue           # un delai fournisseur ne consomme rien
        tache = par_uuid.get(bloc.uuid)
        if tache is None or tache.contexte is None:
            continue
        deja_pris[tache.contexte] = (deja_pris.get(tache.contexte, timedelta(0))
                                     + (bloc.fin - bloc.debut) * config.granularite)

    # L'horizon de la passe 2 est PLUS COURT que l'horizon total, et c'est le
    # reglage qui gouverne sa performance : a 90 jours elle ne place rien du
    # tout, a 21 elle place 135 taches sur 147 (mesure sur les donnees reelles).
    # C'est aussi juste sur le fond -- remplir avec des taches non datees trois
    # mois a l'avance n'a aucun sens, tout aura change d'ici la.
    horizon_opportuniste_fin = t0 + timedelta(days=args.horizon_opportuniste)
    capacites = capacite_restante(config.contextes, t0, maintenant,
                                  horizon_opportuniste_fin, config.granularite,
                                  deja_pris=deja_pris)
    candidates, ecartees = selectionner_candidates(taches_non_datees, capacites)
    if ecartees:
        print("Passe 2 : {} candidate(s) retenue(s), {} ecartee(s) faute de "
              "capacite sur {} jours.\n".format(
                  len(candidates), len(ecartees), args.horizon_opportuniste))

    debut_passe2 = time.perf_counter()
    plan = completer(plan, candidates, config.contextes, t0, maintenant,
                     horizon_opportuniste_fin, config.granularite,
                     reunions=reunions,
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

    if args.ecrire_due:
        compte_rendu = ecrire_due(plan, taches, env=env)
        print("due: {} modifiee(s), {} inchangee(s), {} ignoree(s).".format(
            len(compte_rendu["modifiees"]), len(compte_rendu["inchangees"]),
            len(compte_rendu["ignorees"])))

    # --- 7. resume ------------------------------------------------------------
    print()
    retards = _retards_par_tache(plan, taches, config.contextes)
    print(formater_resume(plan, taches, temps_passe1, temps_passe2,
                          candidates_passe2=len(candidates),
                          retards_par_tache=retards,
                          ecartees_passe2=len(ecartees)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
