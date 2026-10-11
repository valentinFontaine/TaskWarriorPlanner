"""Chargement de la configuration — design.md §2 et §7.

Les grilles viennent de `config.json` a la racine (les vraies grilles de mars 2025).
Rien n'y est invente : ce qui ne s'y trouve pas vient du cahier des charges, et la
provenance est notee en face de chaque valeur.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from planif.modele import Contexte, Creneau, JOURS

__all__ = ["Config", "charger_config", "charger_echeances",
           "CONFIG_JSON", "ECHEANCES_JSON"]

CONFIG_JSON = Path(__file__).resolve().parent.parent / "config.json"

#: Echeances de projet, editees a la main par l'utilisateur. Taskwarrior ne
#: porte pas d'echeance *de projet* -- seulement des `due` par tache -- et il
#: n'en existait aucune dans les donnees reelles. Ce fichier remplace le
#: bouchon `planif/stub_echeances.py`.
ECHEANCES_JSON = Path(__file__).resolve().parent.parent / "echeances.json"

# Contextes de travail retenus. `sleep` et `asso` sont presents dans config.json mais
# ne sont pas des contextes de travail du cahier des charges : on ne les invente pas.
CONTEXTES_RETENUS = ("pro", "perso")

# proposal.md decision 3 : le bloc minimum est une propriete du contexte.
# (Ne pas confondre avec `deepWorkLimit=4` de config.json, qui est un plafond de
# travail profond, pas un bloc minimum. Voir INVENTAIRE.md §6.)
BLOC_MIN_DEFAUT = {"pro": timedelta(hours=2), "perso": timedelta(hours=1)}

# proposal.md decision 11 : marge quotidienne reservee. La valeur `pro` se lit dans
# config.json (`freeTimeHours`) ; la valeur `perso` n'y est pas et vient du cahier
# des charges.
MARGE_PERSO_DEFAUT = timedelta(minutes=30)


def charger_echeances(chemin=None):
    """Lit `echeances.json` : nom de projet -> echeance (naif, heure locale).

    Format attendu, un objet JSON plat que l'utilisateur edite a la main ::

        {
          "NPD.helisides": "2026-11-24T17:00:00",
          "NPD.brevets":   "2027-01-15"
        }

    Trois regles, et chacune vient d'un defaut qu'on ne veut pas reproduire :

    - **une date seule vaut la FIN de la journee** (23:59), pas son debut.
      « Pour le 24 » veut dire « avant la fin du 24 » ; l'interpreter a minuit
      avancerait tout le projet d'une journee entiere, sans que rien ne le
      signale.
    - **le fichier est optionnel** : absent, il rend un dictionnaire vide. Un
      depot frais doit pouvoir tourner. C'est a l'appelant de dire combien
      d'echeances il a chargees, pas a ce module de refuser de demarrer.
    - **une date illisible leve**, en nommant le projet. Ignorer une echeance
      mal ecrite la ferait disparaitre du plan en silence, ce qui est le seul
      comportement vraiment interdit dans cet outil.
    """
    chemin = Path(chemin) if chemin else ECHEANCES_JSON
    if not chemin.exists():
        return {}

    brut = json.loads(chemin.read_text(encoding="utf-8"))
    echeances = {}
    for projet, texte in brut.items():
        # JSON n'a pas de commentaires : une cle prefixee par « _ » en tient
        # lieu, ce qui permet a `echeances.exemple.json` de se documenter
        # lui-meme. Aucun projet Taskwarrior ne commence par un souligne.
        if projet.startswith("_"):
            continue
        valeur = str(texte).strip()
        try:
            instant = datetime.fromisoformat(valeur)
        except ValueError:
            raise ValueError(
                "echeance illisible pour le projet {} : {!r}. Format attendu : "
                "« 2026-11-24 » ou « 2026-11-24T17:00:00 ».".format(projet, texte))
        if len(valeur) == 10:      # « AAAA-MM-JJ », sans heure
            instant = instant.replace(hour=23, minute=59)
        if instant.tzinfo is not None:
            # design.md §2 : tout est naif local a l'interieur du modele.
            instant = instant.astimezone().replace(tzinfo=None)
        echeances[projet] = instant
    return echeances


def _parse_creneau(texte):
    """« 08:30-12:00 » -> Creneau(510, 720). Accepte aussi « 7:00-8:00 »."""
    debut, fin = texte.split("-")

    def minutes(hm):
        h, m = hm.strip().split(":")
        return int(h) * 60 + int(m)

    return Creneau(minutes(debut), minutes(fin))


def _parse_grille(grille_json):
    grille = {}
    for indice, nom in enumerate(JOURS):
        plages = grille_json.get(nom, [])
        grille[indice] = tuple(sorted(_parse_creneau(p) for p in plages))
    return grille


def _parse_periodes(periodes_json, nom_contexte):
    """Periodes datees d'un contexte : tuple de (debut, fin, creneaux).

    Une periode (`config.json`, cle `periodes`) remplace, du `debut` a la `fin`
    inclus, la grille des contextes qu'elle cite dans `timeSlots` ; les autres
    gardent leur grille hebdomadaire. Cas d'origine : des vacances, `pro` a
    zero et `perso` en journee entiere. Une date illisible leve en nommant la
    periode : une periode ignoree en silence fausserait tout le plan.
    """
    periodes = []
    for periode in periodes_json:
        nom = periode.get("nom", "?")
        try:
            debut = date.fromisoformat(periode["debut"])
            fin = date.fromisoformat(periode["fin"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                "periode {} : debut et fin attendus au format « 2026-10-24 », "
                "lu {!r} et {!r}".format(nom, periode.get("debut"),
                                        periode.get("fin")))
        if debut > fin:
            raise ValueError("periode {} : debut {} apres la fin {}".format(
                nom, debut, fin))
        plages = periode.get("timeSlots", {}).get(nom_contexte)
        if plages is None:
            continue
        creneaux = tuple(sorted(_parse_creneau(p) for p in plages))
        periodes.append((debut, fin, creneaux))
    return tuple(periodes)


@dataclass(frozen=True)
class Config:
    contextes: dict = field(default_factory=dict)
    projets: dict = field(default_factory=dict)
    granularite: timedelta = timedelta(minutes=30)   # proposal.md decision 1
    horizon_detaille: timedelta = timedelta(weeks=2)  # design.md §1


def charger_config(chemin=None, echeances_projet=None):
    """Lit `config.json` et rend une `Config`.

    `echeances_projet` : dict nom_projet -> datetime. Aucune echeance de projet
    n'existe dans les donnees reelles ; a defaut, l'appelant passe le bouchon
    `planif.stub_echeances.ECHEANCES_PROJET`.
    """
    chemin = Path(chemin) if chemin else CONFIG_JSON
    brut = json.loads(chemin.read_text(encoding="utf-8"))

    marge_pro = timedelta(hours=float(brut.get("freeTimeHours", 2)))

    contextes = {}
    for nom in CONTEXTES_RETENUS:
        grille_json = brut.get("timeSlots", {}).get(nom)
        if grille_json is None:
            continue
        contextes[nom] = Contexte(
            nom=nom,
            contexte_tw=nom,
            bloc_min=BLOC_MIN_DEFAUT[nom],
            marge_jour=marge_pro if nom == "pro" else MARGE_PERSO_DEFAUT,
            grille=_parse_grille(grille_json),
            periodes=_parse_periodes(brut.get("periodes", []), nom),
        )

    from planif.modele import Projet
    projets = {n: Projet(n, e) for n, e in (echeances_projet or {}).items()}

    return Config(contextes=contextes, projets=projets)
