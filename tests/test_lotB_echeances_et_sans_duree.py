"""Lot B — les echeances de projet sortent du bouchon, et rien ne disparait en silence.

Deux sujets, tous deux nes de la premiere confrontation aux donnees reelles.

**1. Les echeances de projet.** `planif/stub_echeances.py` ne contient qu'une
valeur, celle du cas de reference. Tant qu'aucune echeance reelle n'existe,
toute tache non datee part en regime opportuniste et le plan se tasse au plus
tot -- l'inverse exact de ce que l'outil promet. Il faut une source que
l'utilisateur edite lui-meme : `echeances.json` a la racine.

Son absence n'est **pas** une erreur : le fichier est optionnel, et un depot
frais doit pouvoir tourner. C'est a la ligne de commande de dire combien
d'echeances elle a chargees, pas a ce module de refuser de demarrer.

**2. Les taches sans duree estimee.** `solveur.py` les saute, avec ce
commentaire :

    if tache.estimated is None:
        continue  # signale par les pre-verifications, pas devine ici

C'est faux. `verifications.py` ne verifie l'absence d'`estTime` que pour les
taches `+external`. Une tache ordinaire sans duree est eliminee du plan **sans
un mot** : ni anomalie, ni compteur. Sur une base ou la majorite des taches
n'ont pas d'estimation, on regarderait un calendrier confortablement vide en
ignorant que le solveur n'a jamais vu ce contenu.

C'est le meme mode de panne que les deux regimes invisibles du calendrier et
que le `return plan` muet de la passe 2 : **l'outil perd du contenu en
silence**. Il ne reste plus qu'a fermer celui-la.
"""
import json
from datetime import datetime, timedelta

import pytest

from planif.modele import Contexte, Creneau, Tache

# --------------------------------------------------------------------------
# 1. echeances.json
# --------------------------------------------------------------------------

MAINTENANT = datetime(2026, 10, 5, 8, 0)


def test_charger_echeances_lit_le_fichier(tmp_path):
    from planif.config import charger_echeances

    chemin = tmp_path / "echeances.json"
    chemin.write_text(json.dumps({
        "NPD.helisides": "2026-11-24T17:00:00",
        "NPD.brevets": "2027-01-15T12:00:00",
    }), encoding="utf-8")

    echeances = charger_echeances(chemin)

    assert echeances == {
        "NPD.helisides": datetime(2026, 11, 24, 17, 0),
        "NPD.brevets": datetime(2027, 1, 15, 12, 0),
    }
    # Naif local a l'interieur du modele (design.md §2) : aucune des valeurs
    # chargees ne doit porter de fuseau, sans quoi les comparaisons du tampon
    # exploseraient a la premiere echeance.
    for valeur in echeances.values():
        assert valeur.tzinfo is None


def test_une_date_seule_vaut_fin_de_journee(tmp_path):
    """« 2026-11-24 » doit signifier la fin du 24, pas son debut.

    Une echeance de projet s'ecrit naturellement en jour. L'interpreter a
    minuit avancerait tout le projet d'une journee entiere, silencieusement.
    """
    from planif.config import charger_echeances

    chemin = tmp_path / "echeances.json"
    chemin.write_text(json.dumps({"NPD.helisides": "2026-11-24"}), encoding="utf-8")

    echeances = charger_echeances(chemin)
    assert echeances["NPD.helisides"] == datetime(2026, 11, 24, 23, 59)


def test_le_fichier_d_exemple_du_depot_se_charge_tel_quel():
    """Un exemple qui ne passe pas le chargeur est un piege, pas un exemple.

    `echeances.exemple.json` se documente par une cle « _lisez-moi » : JSON n'a
    pas de commentaires. Le chargeur doit donc ignorer les cles prefixees par
    un souligne, sinon le premier utilisateur qui copie le fichier obtient une
    exception sur la ligne d'explication.
    """
    from pathlib import Path

    from planif.config import charger_echeances

    exemple = Path(__file__).resolve().parent.parent / "echeances.exemple.json"
    assert exemple.exists()

    echeances = charger_echeances(exemple)
    assert "_lisez-moi" not in echeances
    assert echeances["NPD.exemple-court"] == datetime(2027, 1, 15, 23, 59)
    assert echeances["NPD.exemple-precis"] == datetime(2027, 3, 2, 14, 0)


def test_fichier_absent_rend_un_dictionnaire_vide(tmp_path):
    """Optionnel veut dire optionnel : pas d'exception, pas de valeur inventee."""
    from planif.config import charger_echeances

    assert charger_echeances(tmp_path / "pas-la.json") == {}


def test_une_date_illisible_est_refusee_bruyamment(tmp_path):
    """Le silence est le seul comportement interdit.

    Ignorer une echeance mal ecrite la ferait disparaitre du plan sans que
    personne ne le sache -- exactement le defaut qu'on est en train de fermer
    ailleurs. On leve, en nommant le projet fautif.
    """
    from planif.config import charger_echeances

    chemin = tmp_path / "echeances.json"
    chemin.write_text(json.dumps({"NPD.helisides": "la semaine prochaine"}),
                      encoding="utf-8")

    with pytest.raises(ValueError, match="NPD.helisides"):
        charger_echeances(chemin)


# --------------------------------------------------------------------------
# 2. La pre-verification « sans duree estimee »
# --------------------------------------------------------------------------

_PLAGE = Creneau(9 * 60, 12 * 60)
CONTEXTE = Contexte(nom="pro", contexte_tw="pro", bloc_min=timedelta(hours=1),
                    marge_jour=timedelta(0),
                    grille={i: ((_PLAGE,) if i < 5 else ()) for i in range(7)})
CONTEXTES = {"pro": CONTEXTE}


def _tache(uuid, estimated=None, tags=("pro",)):
    return Tache(uuid=uuid, description="Tache " + uuid[:4], estimated=estimated,
                 tags=tags, contexte="pro")


def test_une_tache_sans_duree_est_signalee_nommement():
    from planif.verifications import verifier_sans_estimated

    taches = [_tache("11111111", estimated=timedelta(hours=2)),
              _tache("22222222")]

    anomalies = verifier_sans_estimated(taches)

    assert len(anomalies) == 1
    assert anomalies[0].code == "sans-estimated"
    assert anomalies[0].uuids == ("22222222",)
    # Le message doit dire la CONSEQUENCE, pas seulement le constat : c'est ce
    # qui distingue un avertissement utile d'une ligne de bruit.
    assert "plan" in anomalies[0].message.lower()


def test_le_cas_nominal_ne_signale_rien():
    from planif.verifications import verifier_sans_estimated

    taches = [_tache("11111111", estimated=timedelta(hours=2))]
    assert verifier_sans_estimated(taches) == []


def test_une_tache_externe_sans_duree_n_est_pas_comptee_deux_fois():
    """`externe-sans-estimated` existe deja et dit mieux les choses.

    Une tache `+external` sans duree n'est pas « une tache dont on ignore la
    charge » mais « un delai fournisseur non renseigne » : deux problemes
    differents, deux messages differents, et surtout un seul par tache.
    """
    from planif.verifications import verifier_sans_estimated

    taches = [_tache("33333333", tags=("pro", "external"))]
    assert verifier_sans_estimated(taches) == []


def test_la_pre_verification_est_branchee_dans_le_rapport():
    """Une verification que `pre_verifications` n'appelle pas ne sert a rien."""
    from planif.verifications import CODES, pre_verifications

    assert "sans-estimated" in CODES

    taches = [_tache("44444444")]
    codes = [a.code for a in pre_verifications(taches, CONTEXTES, MAINTENANT)]
    assert "sans-estimated" in codes
