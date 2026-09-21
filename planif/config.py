"""Chargement de la configuration — design.md §2 et §7.

Les grilles viennent de `config.json` a la racine (les vraies grilles de mars 2025).
Rien n'y est invente : ce qui ne s'y trouve pas vient du cahier des charges, et la
provenance est notee en face de chaque valeur.
"""
import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from planif.modele import Contexte, Creneau, JOURS

__all__ = ["Config", "charger_config", "CONFIG_JSON"]

CONFIG_JSON = Path(__file__).resolve().parent.parent / "config.json"

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
        )

    from planif.modele import Projet
    projets = {n: Projet(n, e) for n, e in (echeances_projet or {}).items()}

    return Config(contextes=contextes, projets=projets)
