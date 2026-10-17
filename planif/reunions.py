"""Lecture de l'agenda : ce qui occupe reellement le temps.

Remplace `planif/stub_reunions.py`, qui rendait toujours une liste vide et
rendait donc tout plan trop optimiste sur un agenda charge.

## La frontiere, et pourquoi elle est la

L'extraction PowerShell (`outils/extraire-outlook.ps1`) recopie ce qu'Outlook
dit, **sans rien filtrer**. Tout le tri est ici, en Python, ou il se teste sans
Outlook et sans machine professionnelle. Changer une regle de filtrage ne doit
jamais obliger a relancer une extraction, et la sortie brute reste la piece a
conviction quand on doute d'une regle.

## Les regles, et la mesure qui les fonde

Etablies sur un export reel de 6 semaines, pas au jugement :

- **`BusyStatus = Free` n'occupe pas.** Six evenements sur dix-huit sont dans ce
  cas. La presence d'un evenement dans un agenda ne veut pas dire que le temps
  est pris ; les compter retirerait un tiers de la capacite pour rien.
- **Une invitation refusee n'occupe pas.** On n'y va pas.
- **Une reunion provisoire occupe** (decision utilisateur) : tant qu'elle n'est
  pas annulee, la place est retenue.
- **Une absence de plusieurs jours occupe ces jours entiers.** Elle arrive ici
  comme un intervalle unique du premier 00:00 au dernier 00:00 ; la soustraction
  de `planif.calendrier.disponibilite` en fait disparaitre toutes les journees,
  sans traitement particulier. C'est verifie par un test, pas suppose.

## Le piege a ne pas reproduire

Dans l'export reel, **18 occurrences ne portent que 6 `entryId` distincts** :
l'identifiant appartient a la SERIE recurrente, jamais a l'occurrence. Tout
mecanisme qui dedupliquerait la-dessus -- un UDA `outlookId`, par exemple --
garderait une occurrence sur six et rendrait cinq sixiemes de l'agenda
invisibles au solveur. Aucune deduplication n'est faite ici.
"""
import json
import logging
import os
from datetime import datetime

from planif.modele import Reunion

__all__ = ["reunions", "CHEMIN_DEFAUT"]

_LOG = logging.getLogger(__name__)

#: Fichier lu a defaut d'autre indication, a la racine du depot. Ignore par git :
#: il porte les sujets et les lieux reels de l'utilisateur.
CHEMIN_DEFAUT = "reunions.json"

#: `OlBusyStatus` : 0 Free, 1 Tentative, 2 Busy, 3 OutOfOffice, 4 WorkingElsewhere.
OCCUPATION_LIBRE = 0

#: `OlResponseStatus` : 4 = Declined.
REPONSE_REFUSEE = 4


def _occupe(evenement):
    """Vrai si cet evenement prend reellement du temps."""
    if evenement.get("occupation") == OCCUPATION_LIBRE:
        return False
    if evenement.get("reponse") == REPONSE_REFUSEE:
        return False
    return True


def reunions(debut, fin, source=None):
    """Rend les `Reunion` occupant du temps dans [debut, fin[, triees.

    Meme signature que le bouchon qu'elle remplace, pour que le branchement
    dans `planif/__main__.py` tienne en une ligne d'import.

    Fichier absent : rend un tuple vide **et le dit**. C'est exactement ce que
    faisait le bouchon, a ceci pres qu'il se taisait -- et un agenda absent qui
    ne se signale pas produit un plan trop optimiste que rien ne trahit.

    Fichier illisible : leve `ValueError`. Un agenda qu'on ne sait pas lire doit
    arreter le calcul, pas l'edulcorer en silence.
    """
    chemin = source or CHEMIN_DEFAUT

    if not os.path.exists(chemin):
        _LOG.warning(
            "agenda absent (%s) : le plan ignorera toutes les reunions et "
            "sortira donc TROP OPTIMISTE. Relancer l'extraction Outlook "
            "(outils/extraire-outlook.ps1) pour le produire.", chemin)
        return ()

    # utf-8-sig : PowerShell 5.1 ecrit un BOM, Python ne doit pas le lire comme
    # un caractere. Un fichier sans BOM passe par le meme chemin.
    with open(chemin, encoding="utf-8-sig") as f:
        texte = f.read()
    try:
        brut = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise ValueError(
            "agenda illisible ({}) : {}".format(chemin, erreur)) from erreur

    # Un export a un seul evenement sort comme un objet, pas comme une liste :
    # c'est `ConvertTo-Json` de PowerShell qui se comporte ainsi.
    if isinstance(brut, dict):
        brut = [brut]

    retenues = []
    for evenement in brut:
        if not _occupe(evenement):
            continue
        d = datetime.fromisoformat(evenement["debut"])
        f = datetime.fromisoformat(evenement["fin"])
        if f <= debut or d >= fin:
            continue
        retenues.append(Reunion(titre=evenement.get("sujet") or "(sans titre)",
                                debut=d, fin=f))

    retenues.sort(key=lambda r: (r.debut, r.fin, r.titre))
    _LOG.info("agenda : %d evenements lus, %d retenus comme occupants",
              len(brut), len(retenues))
    return tuple(retenues)


def occupations_figees(taches, exclues=()):
    """Les taches `+fixed` hors filtre, vues comme du temps OCCUPE.

    Avec `--filtre`, une figee d'un autre projet n'est pas chargee dans le
    plan, mais elle prend quand meme le temps de l'utilisateur
    (tests/test_filtre_figees_hors_filtre.py). Elle occupe `[scheduled,
    scheduled + estimated[`, d'un seul tenant, comme une reunion ; sans
    `scheduled` ou sans duree, il n'y a rien a occuper.
    """
    occupations = []
    for tache in taches:
        if (tache.uuid in exclues or not tache.fige
                or tache.scheduled is None or tache.estimated is None):
            continue
        occupations.append(Reunion(
            titre="figee hors filtre : {}".format(tache.description),
            debut=tache.scheduled, fin=tache.scheduled + tache.estimated))
    return sorted(occupations, key=lambda r: r.debut)
