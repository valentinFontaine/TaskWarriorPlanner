"""Contrat de test -- passe 2, objectif 1 (`completer`, ~ligne 1278) :
l'urgence n'a pas le droit d'ecarter une candidate qui tient.

Defaut mesure (implementeur), une candidate seule, capacite libre :

    urgency=0.0 -> "0 tache(s) placee(s) sur 1 candidate(s)"
    urgency=5.0 -> placee

Le code actuel :

    poids.append(int(round(tache.urgency * echelle)) * presences[tache.uuid])
    ...
    modele.Maximize(sum(objectif1) if objectif1 else 0)

maximise la SOMME BRUTE `urgency * presence`. Une candidate d'urgence 0
n'apporte rien a cette somme : sa presence reste indifferente au solveur, donc
arbitrairement a 0. Une candidate d'urgence NEGATIVE fait mieux dans la somme
en restant absente (0 > urgence*echelle*1) : elle est donc activement exclue.
Or dans Taskwarrior une tache bloquee par une dependance prend -5 d'urgence
(coefficient `blocked`), et bien d'autres taches ont une urgence <= 0.

Specification retenue : la passe 2 remplit la capacite libre avec les
candidates ; toute candidate qui TIENT est placee, quelle que soit son
urgence (y compris 0 et negative). L'urgence ne sert qu'a ARBITRER quand la
capacite manque : a capacite pour une seule, la plus urgente gagne, y compris
entre deux urgences negatives (-1 bat -5).

Horloge figee, aucun `datetime.now()`. Meme patron que `tests/test_fige_fait.py`
(T0/MAINTENANT constants du fichier, `resoudre` puis `completer` appeles
directement, passe 1 vide).
"""
from datetime import datetime, timedelta

from planif.modele import Contexte, Creneau, Tache
from planif.solveur import completer, resoudre

T0 = datetime(2026, 10, 5, 0, 0)          # lundi, minuit
MAINTENANT = datetime(2026, 10, 5, 8, 0)  # lundi 08:00
GRANULARITE = timedelta(minutes=30)

_VIDE = ()

# --------------------------------------------------------------------------
# Contexte AMPLE : lun-ven 09:00-13:00 (4 h utiles/jour), largement plus que
# ce que les tests 1 a 3 demandent (au plus 3 candidates d'1 h chacune).
# --------------------------------------------------------------------------
CONTEXTE_AMPLE = Contexte(
    nom="ample", contexte_tw="ample",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(9 * 60, 13 * 60),), 1: (Creneau(9 * 60, 13 * 60),),
        2: (Creneau(9 * 60, 13 * 60),), 3: (Creneau(9 * 60, 13 * 60),),
        4: (Creneau(9 * 60, 13 * 60),), 5: _VIDE, 6: _VIDE,
    },
)
CONTEXTES_AMPLE = {"ample": CONTEXTE_AMPLE}
HORIZON_FIN_AMPLE = T0 + timedelta(days=35)

# --------------------------------------------------------------------------
# Contexte LIMITE : une seule fenetre dans tout l'horizon, exactement la
# taille d'une candidate (1 h) -- capacite pour une seule, jamais deux.
# L'horizon est coupe avant que le lundi suivant ne rouvre la meme fenetre
# (meme patron que `tests/test_fige_fait.py::CONTEXTE_B` / `HORIZON_FIN_8`).
# --------------------------------------------------------------------------
CONTEXTE_LIMITE = Contexte(
    nom="limite", contexte_tw="limite",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(9 * 60, 10 * 60),), 1: _VIDE, 2: _VIDE, 3: _VIDE,
        4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)
CONTEXTES_LIMITE = {"limite": CONTEXTE_LIMITE}
HORIZON_FIN_LIMITE = T0 + timedelta(days=6)   # avant le lundi suivant


def _completer(candidates, contextes, horizon_fin):
    plan1 = resoudre([], contextes, T0, MAINTENANT, horizon_fin, GRANULARITE)
    return completer(plan1, candidates, contextes, T0, MAINTENANT, horizon_fin,
                     GRANULARITE)


def _est_placee(plan, uuid):
    return sum(b.longueur for b in plan.blocs_de(uuid)) > 0


# ==========================================================================
# 1. Une candidate urgency=0.0, capacite largement suffisante -> placee.
# ==========================================================================

UUID_1 = "10101010-0000-0000-0000-000000000001"


def test_1_urgence_nulle_placee_si_la_capacite_le_permet():
    """Attendu ROUGE : le defaut mesure exactement sur ce cas."""
    candidate = Tache(uuid=UUID_1, description="Urgence nulle", contexte="ample",
                      estimated=timedelta(hours=1), urgency=0.0)
    plan2 = _completer([candidate], CONTEXTES_AMPLE, HORIZON_FIN_AMPLE)

    assert _est_placee(plan2, UUID_1), (
        "candidate d'urgence 0.0, capacite libre, non placee -- le defaut du "
        "contrat (indifference du solveur a une presence qui ne pese rien "
        "dans l'objectif)")


# ==========================================================================
# 2. Une candidate urgency=-5.0 -> placee.
# ==========================================================================

UUID_2 = "20202020-0000-0000-0000-000000000002"


def test_2_urgence_negative_placee_si_la_capacite_le_permet():
    """Attendu ROUGE : une urgence negative est activement exclue par
    `Maximize(sum(urgency * presence))` (0 > -5000*1)."""
    candidate = Tache(uuid=UUID_2, description="Urgence negative", contexte="ample",
                      estimated=timedelta(hours=1), urgency=-5.0)
    plan2 = _completer([candidate], CONTEXTES_AMPLE, HORIZON_FIN_AMPLE)

    assert _est_placee(plan2, UUID_2), (
        "candidate d'urgence -5.0, capacite libre, non placee -- exclue par "
        "la maximisation de la somme brute d'urgence")


# ==========================================================================
# 3. Trois candidates (3.0, 0.0, -5.0), capacite pour les trois -> toutes
#    placees.
# ==========================================================================

UUID_3_POS = "30303030-0000-0000-0000-000000000031"
UUID_3_NUL = "30303030-0000-0000-0000-000000000032"
UUID_3_NEG = "30303030-0000-0000-0000-000000000033"


def test_3_urgences_melangees_toutes_placees_si_la_capacite_le_permet():
    """Attendu ROUGE : au moins la nulle et la negative n'y sont pas -- la
    positive, elle, est deja favorisee par le code actuel."""
    candidates = [
        Tache(uuid=UUID_3_POS, description="Urgence positive", contexte="ample",
              estimated=timedelta(hours=1), urgency=3.0),
        Tache(uuid=UUID_3_NUL, description="Urgence nulle", contexte="ample",
              estimated=timedelta(hours=1), urgency=0.0),
        Tache(uuid=UUID_3_NEG, description="Urgence negative", contexte="ample",
              estimated=timedelta(hours=1), urgency=-5.0),
    ]
    plan2 = _completer(candidates, CONTEXTES_AMPLE, HORIZON_FIN_AMPLE)

    non_placees = [u for u in (UUID_3_POS, UUID_3_NUL, UUID_3_NEG)
                   if not _est_placee(plan2, u)]
    assert not non_placees, (
        "candidates non placees alors que la capacite du jour (4 h) suffit "
        "largement aux trois (1 h chacune) : {}".format(non_placees))


# ==========================================================================
# 4. Arbitrage positif : capacite pour UNE seule, urgences 2.0 et 7.0 ->
#    7.0 placee, 2.0 non. Temoin : deja vert avant et apres correction.
# ==========================================================================

UUID_4_HAUTE = "40404040-0000-0000-0000-000000000041"
UUID_4_BASSE = "40404040-0000-0000-0000-000000000042"


def test_4_arbitrage_positif_la_plus_urgente_gagne():
    """Temoin : le code actuel arbitre deja correctement entre deux urgences
    positives -- attendu VERT avant et apres correction."""
    candidates = [
        Tache(uuid=UUID_4_BASSE, description="Urgence 2.0", contexte="limite",
              estimated=timedelta(hours=1), urgency=2.0),
        Tache(uuid=UUID_4_HAUTE, description="Urgence 7.0", contexte="limite",
              estimated=timedelta(hours=1), urgency=7.0),
    ]
    plan2 = _completer(candidates, CONTEXTES_LIMITE, HORIZON_FIN_LIMITE)

    assert _est_placee(plan2, UUID_4_HAUTE), (
        "la candidate la plus urgente (7.0) n'est pas placee alors que la "
        "capacite ne permet d'en placer qu'une seule")
    assert not _est_placee(plan2, UUID_4_BASSE), (
        "la candidate la moins urgente (2.0) est placee alors que la "
        "capacite ne permet d'en placer qu'une seule, et que 7.0 l'est aussi")


# ==========================================================================
# 5. Arbitrage negatif : capacite pour une seule, urgences -1.0 et -5.0 ->
#    -1.0 placee.
# ==========================================================================

UUID_5_MOINS_NEG = "50505050-0000-0000-0000-000000000051"
UUID_5_PLUS_NEG = "50505050-0000-0000-0000-000000000052"


def test_5_arbitrage_negatif_la_moins_negative_gagne():
    """Attendu ROUGE : maximiser la somme brute prefere n'en placer AUCUNE
    (0 > -1000 > -5000) plutot que de choisir -1.0 -- la specification exige
    au contraire qu'une candidate tenable soit placee, l'urgence ne servant
    qu'a departager -1.0 contre -5.0."""
    candidates = [
        Tache(uuid=UUID_5_MOINS_NEG, description="Urgence -1.0", contexte="limite",
              estimated=timedelta(hours=1), urgency=-1.0),
        Tache(uuid=UUID_5_PLUS_NEG, description="Urgence -5.0", contexte="limite",
              estimated=timedelta(hours=1), urgency=-5.0),
    ]
    plan2 = _completer(candidates, CONTEXTES_LIMITE, HORIZON_FIN_LIMITE)

    assert _est_placee(plan2, UUID_5_MOINS_NEG), (
        "la candidate la moins negative (-1.0) n'est pas placee alors que la "
        "capacite ne permet d'en placer qu'une seule")
    assert not _est_placee(plan2, UUID_5_PLUS_NEG), (
        "la candidate la plus negative (-5.0) est placee alors que -1.0 "
        "devrait lui etre preferee")
