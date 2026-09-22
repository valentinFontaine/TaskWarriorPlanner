"""Les reunions cessent d'etre un bouchon.

`planif/stub_reunions.py` rendait toujours une liste vide, et le declarait
bloquant pour la production : le plan ignorait purement et simplement l'agenda.

## D'ou viennent les regles testees ici

Elles ne sont pas inventees : elles sont MESUREES sur un export reel de 6
semaines (22/09/2026 -> 03/11/2026), dont `tests/donnees/outlook-exemple.json`
garde la forme exacte et rien du contenu -- memes dates, memes durees, memes
statuts, memes series ; sujets et lieux remplaces.

Ce que cet export a appris, et qu'on ne savait pas en concevant le lot :

| Constat mesure | Consequence |
|---|---|
| 18 occurrences pour **6 `entryId` distincts** | l'identifiant appartient a la SERIE, pas a l'occurrence ; il ne peut pas servir de cle seul |
| **6 evenements sur 18 sont `BusyStatus = Free`** | la presence d'un evenement ne veut pas dire temps occupe ; c'est le statut qui decide, sinon on supprime un tiers de la capacite pour rien |
| un evenement de **5 jours** (absence, `OutOfOffice`) | 120 h des 133 h d'occupation totale ; les vraies reunions pesent ~13 h sur 6 semaines |

## Ou passe la frontiere

PowerShell extrait **brut** : il ne filtre rien, il recopie ce qu'Outlook dit.
Le filtrage est de la regle metier, et il vit ici, en Python, ou il est testable
sans Outlook et sans machine professionnelle. Changer une regle ne doit pas
obliger a relancer une extraction.
"""
import json
from datetime import datetime, timedelta

import pytest

from planif.calendrier import disponibilite
from tests.cas_reference import CONTEXTE_PRO, GRANULARITE

ECHANTILLON = "tests/donnees/outlook-exemple.json"

T0 = datetime(2026, 9, 21, 0, 0)          # lundi, avant le premier evenement
FIN = datetime(2026, 11, 3, 0, 0)

#: L'absence de 5 jours de l'echantillon : du lundi 19 au samedi 24 octobre.
ABSENCE_DEBUT = datetime(2026, 10, 19, 0, 0)


def _brut(**champs):
    """Un evenement au format d'extraction, avec des valeurs neutres par defaut."""
    base = {"entryId": "SERIE-99", "sujet": "Test", "debut": "2026-09-23T10:00:00",
            "fin": "2026-09-23T11:00:00", "dureeMin": 60, "journeeEntiere": False,
            "occupation": 2, "reponse": 3, "recurrent": False, "lieu": ""}
    base.update(champs)
    return base


@pytest.fixture
def fichier(tmp_path):
    """Ecrit une liste d'evenements bruts et rend le chemin."""
    def ecrire(evenements):
        p = tmp_path / "reunions.json"
        p.write_text(json.dumps(evenements, ensure_ascii=False), encoding="utf-8")
        return str(p)
    return ecrire


# --------------------------------------------------------------------------
# Les regles de filtrage, mesurees sur l'export reel
# --------------------------------------------------------------------------

def test_une_plage_marquee_libre_ne_bloque_rien(fichier):
    """`BusyStatus = Free` (0) : l'evenement existe, il n'occupe pas.

    Six des dix-huit evenements de l'export reel sont dans ce cas. Les compter
    retirerait un tiers de la capacite sans aucune raison.
    """
    from planif.reunions import reunions
    assert reunions(T0, FIN, source=fichier([_brut(occupation=0)])) == ()


def test_une_reunion_refusee_ne_bloque_rien(fichier):
    """`ResponseStatus = Declined` (4) : on n'y va pas, elle n'occupe pas."""
    from planif.reunions import reunions
    assert reunions(T0, FIN, source=fichier([_brut(reponse=4)])) == ()


def test_une_reunion_provisoire_bloque(fichier):
    """`Tentative` : on garde. Decision utilisateur du 22/09/2026 -- une reunion
    non confirmee occupe quand meme la place tant qu'elle n'est pas annulee."""
    from planif.reunions import reunions
    assert len(reunions(T0, FIN, source=fichier([_brut(occupation=1)]))) == 1


def test_une_absence_bloque(fichier):
    """`OutOfOffice` (3) : c'est le cas de l'absence de 5 jours de l'export."""
    from planif.reunions import reunions
    assert len(reunions(T0, FIN, source=fichier([_brut(occupation=3)]))) == 1


def test_seules_les_reunions_de_la_fenetre_sortent(fichier):
    """Une reunion hors de [t0, fin[ n'a rien a dire sur ce plan."""
    from planif.reunions import reunions
    evs = [_brut(debut="2026-09-23T10:00:00", fin="2026-09-23T11:00:00"),
           _brut(debut="2027-03-01T10:00:00", fin="2027-03-01T11:00:00")]
    assert len(reunions(T0, FIN, source=fichier(evs))) == 1


# --------------------------------------------------------------------------
# Le piege mesure : l'identifiant appartient a la serie
# --------------------------------------------------------------------------

def test_les_occurrences_d_une_meme_serie_sortent_toutes(fichier):
    """18 occurrences pour 6 `entryId` dans l'export reel.

    Dedupliquer sur `entryId` -- ce que tout le monde fait spontanement, et ce
    qu'un UDA `outlookId` ferait -- ne garderait qu'UNE occurrence sur six et
    rendrait 5/6 de l'agenda invisible au solveur.
    """
    from planif.reunions import reunions
    evs = [_brut(entryId="SERIE-01", debut="2026-09-23T10:00:00",
                 fin="2026-09-23T11:00:00", recurrent=True),
           _brut(entryId="SERIE-01", debut="2026-09-30T10:00:00",
                 fin="2026-09-30T11:00:00", recurrent=True),
           _brut(entryId="SERIE-01", debut="2026-10-07T10:00:00",
                 fin="2026-10-07T11:00:00", recurrent=True)]
    assert len(reunions(T0, FIN, source=fichier(evs))) == 3


# --------------------------------------------------------------------------
# Ce qui se passe quand le fichier manque, ou ment
# --------------------------------------------------------------------------

def test_le_fichier_absent_ne_fait_pas_semblant(tmp_path, caplog):
    """Rendre une liste vide en silence, c'est ce que faisait le bouchon : le
    plan sortait trop optimiste sans que rien ne le dise. Vide, oui ; muet, non.
    """
    from planif.reunions import reunions
    absent = str(tmp_path / "pas-la.json")
    with caplog.at_level("WARNING"):
        assert reunions(T0, FIN, source=absent) == ()
    assert caplog.records, "aucun avertissement pour un agenda absent"


def test_un_fichier_illisible_se_plaint(tmp_path):
    """Un agenda qu'on ne sait pas lire doit arreter le calcul, pas l'edulcorer."""
    from planif.reunions import reunions
    p = tmp_path / "casse.json"
    p.write_text("{ ceci n'est pas du json", encoding="utf-8")
    with pytest.raises(ValueError):
        reunions(T0, FIN, source=str(p))


# --------------------------------------------------------------------------
# Le controle de MECANISME : la capacite recule vraiment
# --------------------------------------------------------------------------

def test_l_echantillon_reel_se_lit_en_entier():
    """L'export anonymise passe le chargeur, et les `Free` en sont retires.

    18 evenements, dont 6 marques libres : il doit en rester 12.
    """
    from planif.reunions import reunions
    lues = reunions(T0, FIN, source=ECHANTILLON)
    assert len(lues) == 12, "12 attendues (18 moins les 6 marquees libres)"


def test_une_absence_de_cinq_jours_vide_les_journees(fichier):
    """LE controle de mecanisme.

    Une absence du 19 au 24 octobre doit retirer la journee du 20 ENTIEREMENT.
    Si elle etait traitee comme une reunion ordinaire posee a 00:00, elle ne
    mordrait sur aucun creneau ouvre et l'absence serait invisible : on
    planifierait pendant les vacances.
    """
    from planif.reunions import reunions
    absence = _brut(debut="2026-10-19T00:00:00", fin="2026-10-24T00:00:00",
                    dureeMin=7200, journeeEntiere=True, occupation=3)
    lues = reunions(T0, FIN, source=fichier([absence]))

    mardi = (ABSENCE_DEBUT + timedelta(days=1)).date()
    libre = disponibilite(CONTEXTE_PRO, mardi, T0, GRANULARITE)
    occupe = disponibilite(CONTEXTE_PRO, mardi, T0, GRANULARITE, reunions=lues)

    assert libre.plages, "le mardi 20/10 doit etre ouvre sans l'absence"
    assert libre.capacite > 0
    assert occupe.plages == (), "le 20/10 reste planifiable pendant une absence"
    assert occupe.capacite == 0
