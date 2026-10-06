"""Couvre deux dettes de test non couvertes par les lots 0 a 5.

Partie 1 : la capacite quotidienne doit etre indexee par (contexte, jour), pas
seulement par jour. Un bug de ce type a ete corrige a l'aveugle dans
`planif/solveur.py` (boucle `for (nom_ctx, jour), charges in
charge_du_jour.items():`) sans qu'aucun test ne le couvre, car le cas de
reference (`tests/cas_reference.py`) n'a qu'un seul contexte. On construit ici
un scenario a DEUX contextes synthetiques, ouverts le meme jour, avec des
grilles horaires qui ne se chevauchent pas dans la journee (l'utilisateur reste
une ressource unique).

Partie 2 : le marqueur `+fixed` (contrainte 8 de `planif/solveur.py`) n'est
couvert par aucun test. Il est traite ici comme non eprouve jusqu'a preuve du
contraire.

Horloge figee : aucun `datetime.now()`. On reutilise `T0`, `MAINTENANT` et
`HORIZON_FIN` de `tests/cas_reference.py` (proposal.md decision 1 : la
granularite de 30 min convient a des grilles alignees sur l'heure).
"""
from datetime import timedelta

import pytest

from planif.modele import Contexte, Creneau, Tache
from planif.solveur import resoudre
from tests.cas_reference import GRANULARITE, HORIZON_FIN, MAINTENANT, T0

# ==========================================================================
# Partie 1 - deux contextes le meme jour
# ==========================================================================
#
# Grilles SYNTHETIQUES DE TEST, ne representant aucune donnee reelle de
# l'utilisateur :
#   - contexte "matin" : lun-ven 09:00-13:00 (4 h de grille), marge 1 h
#     -> 3 h utiles (6 creneaux de 30 min) par jour ouvre.
#   - contexte "soir"  : lun-ven 18:00-21:00 (3 h de grille), marge 1 h
#     -> 2 h utiles (4 creneaux de 30 min) par jour ouvre.
# Les deux capacites sont volontairement DIFFERENTES (3 h vs 2 h) : avec deux
# capacites identiques, une confusion entre contextes serait invisible (une
# valeur fausse ressemblerait a la bonne). C'est un ecart assume par rapport a
# l'exemple donne dans la consigne (qui suggerait deux fois 3 h) ; il rend le
# test plus mordant sans changer l'esprit du scenario.
# Les deux grilles ne se chevauchent jamais dans la journee (matin avant midi,
# soir apres 18h) : le non-chevauchement entre les deux contextes est donc
# garanti par construction et verifie explicitement (test 3).
# Samedi et dimanche sont vides dans les deux contextes.

_GRILLE_VIDE = ()

CONTEXTE_MATIN = Contexte(
    nom="matin", contexte_tw="matin",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(hours=1),
    grille={
        0: (Creneau(9 * 60, 13 * 60),),
        1: (Creneau(9 * 60, 13 * 60),),
        2: (Creneau(9 * 60, 13 * 60),),
        3: (Creneau(9 * 60, 13 * 60),),
        4: (Creneau(9 * 60, 13 * 60),),
        5: _GRILLE_VIDE,
        6: _GRILLE_VIDE,
    },
)

CONTEXTE_SOIR = Contexte(
    nom="soir", contexte_tw="soir",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(hours=1),
    grille={
        0: (Creneau(18 * 60, 21 * 60),),
        1: (Creneau(18 * 60, 21 * 60),),
        2: (Creneau(18 * 60, 21 * 60),),
        3: (Creneau(18 * 60, 21 * 60),),
        4: (Creneau(18 * 60, 21 * 60),),
        5: _GRILLE_VIDE,
        6: _GRILLE_VIDE,
    },
)

# L'ordre du dict compte pour le test de mutation (partie "premier contexte du
# cache") : "matin" est insere en premier.
CONTEXTES_DEUX = {"matin": CONTEXTE_MATIN, "soir": CONTEXTE_SOIR}

CAPACITE_MATIN_CRENEAUX = 6   # 3 h utiles, en creneaux de 30 min
CAPACITE_SOIR_CRENEAUX = 4    # 2 h utiles, en creneaux de 30 min

UUID_MATIN = "a1a1a1a1-0000-0000-0000-000000000001"
UUID_SOIR = "b2b2b2b2-0000-0000-0000-000000000002"

TACHE_MATIN = Tache(uuid=UUID_MATIN, description="Test capacite - matin",
                    estimated=timedelta(hours=3), contexte="matin")
TACHE_SOIR = Tache(uuid=UUID_SOIR, description="Test capacite - soir",
                   estimated=timedelta(hours=3), contexte="soir")


@pytest.fixture(scope="module")
def plan_deux_contextes():
    """Un seul appel au solveur pour toute la partie 1 (3 tests)."""
    return resoudre([TACHE_MATIN, TACHE_SOIR], CONTEXTES_DEUX,
                    T0, MAINTENANT, HORIZON_FIN, GRANULARITE)


def test_chaque_contexte_garde_sa_capacite_propre(plan_deux_contextes):
    """Les deux contextes atteignent chacun leur PROPRE capacite le meme jour.

    Si la capacite quotidienne etait indexee par jour seul (le bug historique),
    les deux contextes partageraient un seul volume et le total serait plafonne
    au lieu d'atteindre 3 h + 2 h = 5 h le meme jour.
    """
    plan = plan_deux_contextes
    par_jour_matin = plan.creneaux_par_jour(UUID_MATIN)
    par_jour_soir = plan.creneaux_par_jour(UUID_SOIR)

    # La tache matin (3 h) tient exactement dans sa capacite quotidienne (3 h) :
    # elle est donc entierement placee sur un seul jour, au plus tard possible.
    assert max(par_jour_matin.values()) == CAPACITE_MATIN_CRENEAUX
    assert sum(par_jour_matin.values()) == 6   # 3 h au total, conservation

    # La tache soir (3 h) DEPASSE sa capacite quotidienne (2 h) : elle doit
    # etaler sur au moins deux jours, et jamais atteindre 3 h en un seul jour.
    assert max(par_jour_soir.values()) == CAPACITE_SOIR_CRENEAUX
    assert sum(par_jour_soir.values()) == 6   # 3 h au total, conservation

    # Les deux contextes atteignent leur pleine capacite LE MEME JOUR : c'est
    # le jour le plus tard de l'horizon (l'objectif maximise les debuts), donc
    # necessairement commun aux deux grilles (ouvertes les memes jours).
    jours_pleins_matin = {j for j, n in par_jour_matin.items()
                          if n == CAPACITE_MATIN_CRENEAUX}
    jours_pleins_soir = {j for j, n in par_jour_soir.items()
                         if n == CAPACITE_SOIR_CRENEAUX}
    jour_commun = jours_pleins_matin & jours_pleins_soir
    assert jour_commun, (
        "aucun jour ou les deux contextes atteignent leur capacite en meme "
        "temps : matin={}, soir={}".format(par_jour_matin, par_jour_soir))

    jour = min(jour_commun)
    total_ce_jour = par_jour_matin[jour] + par_jour_soir[jour]
    assert total_ce_jour == CAPACITE_MATIN_CRENEAUX + CAPACITE_SOIR_CRENEAUX


def test_la_capacite_d_un_contexte_ne_deborde_pas_sur_l_autre(plan_deux_contextes):
    """Aucun jour ne depasse la capacite PROPRE d'un contexte, meme quand
    l'autre contexte est vide ce jour-la (pas de fuite de capacite inutilisee
    d'un contexte vers l'autre)."""
    plan = plan_deux_contextes
    par_jour_matin = plan.creneaux_par_jour(UUID_MATIN)
    par_jour_soir = plan.creneaux_par_jour(UUID_SOIR)

    assert par_jour_matin, "aucun creneau matin planifie : le test ne prouve rien"
    assert par_jour_soir, "aucun creneau soir planifie : le test ne prouve rien"

    for jour, n in par_jour_matin.items():
        assert n <= CAPACITE_MATIN_CRENEAUX, (
            "capacite matin depassee le {} : {} creneaux".format(jour, n))
    for jour, n in par_jour_soir.items():
        assert n <= CAPACITE_SOIR_CRENEAUX, (
            "capacite soir depassee le {} : {} creneaux".format(jour, n))


def test_les_deux_contextes_ne_se_chevauchent_jamais_dans_le_temps(plan_deux_contextes):
    """L'utilisateur est une ressource unique : matin et soir, qui partagent le
    meme jour mais des heures differentes, ne se chevauchent jamais."""
    plan = plan_deux_contextes
    blocs = list(plan.blocs_de(UUID_MATIN)) + list(plan.blocs_de(UUID_SOIR))
    blocs = [b for b in blocs if not b.externe]
    # 3 h / bloc_min 1 h = 3 blocs par tache, deux taches -> 6 blocs. Preuve
    # que le test ne passe pas trivialement sur un plan vide.
    assert len(blocs) == 6

    blocs.sort(key=lambda b: b.debut)
    for precedent, suivant in zip(blocs, blocs[1:]):
        assert precedent.fin <= suivant.debut, (
            "chevauchement entre {} et {}".format(precedent, suivant))


# ==========================================================================
# Partie 2 - la tache figee (+fixed)
# ==========================================================================
#
# Contexte de test dedie : lun-ven 09:00-13:00 (4 h), marge nulle -> 4 h
# utiles (8 creneaux de 30 min) par jour ouvre, bloc minimum 1 h. Grille
# synthetique de test, sans rapport avec une grille reelle.

CONTEXTE_FIGE = Contexte(
    nom="fige_ctx", contexte_tw="fige_ctx",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(9 * 60, 13 * 60),),
        1: (Creneau(9 * 60, 13 * 60),),
        2: (Creneau(9 * 60, 13 * 60),),
        3: (Creneau(9 * 60, 13 * 60),),
        4: (Creneau(9 * 60, 13 * 60),),
        5: _GRILLE_VIDE,
        6: _GRILLE_VIDE,
    },
)
CONTEXTES_FIGE = {"fige_ctx": CONTEXTE_FIGE}

# Creneau de reference : lundi 2026-10-05 09:00, premier creneau ouvert de la
# grille (aligne sur la granularite de 30 min), largement apres MAINTENANT
# (08:00 le meme jour).
SCHEDULED_A = T0.replace(hour=9, minute=0)

UUID_A_FIGE = "c3c3c3c3-0000-0000-0000-000000000003"
UUID_B_LIBRE = "d4d4d4d4-0000-0000-0000-000000000004"
UUID_C_DEP = "e5e5e5e5-0000-0000-0000-000000000005"

TACHE_A_FIGE = Tache(uuid=UUID_A_FIGE, description="Figee", tags=("fixed",),
                     estimated=timedelta(hours=1), contexte="fige_ctx",
                     scheduled=SCHEDULED_A)
TACHE_B_LIBRE = Tache(uuid=UUID_B_LIBRE, description="Libre",
                      estimated=timedelta(hours=1), contexte="fige_ctx")
TACHE_C_DEP = Tache(uuid=UUID_C_DEP, description="Depend de la figee",
                    estimated=timedelta(hours=1), contexte="fige_ctx",
                    depends=(UUID_A_FIGE,))


@pytest.fixture(scope="module")
def plan_fige():
    """Un seul appel au solveur pour toute la partie 2 (4 tests)."""
    return resoudre([TACHE_A_FIGE, TACHE_B_LIBRE, TACHE_C_DEP], CONTEXTES_FIGE,
                    T0, MAINTENANT, HORIZON_FIN, GRANULARITE)


def test_tache_figee_commence_exactement_a_son_scheduled(plan_fige):
    """Le debut du bloc unique d'une tache +fixed est exactement son `scheduled`."""
    assert plan_fige.debut(UUID_A_FIGE) == SCHEDULED_A


def test_tache_figee_ne_bouge_pas_meme_si_le_solveur_prefererait_plus_tard(plan_fige):
    """L'objectif maximise la somme des debuts (« au plus tard ») : sans la
    contrainte +fixed, A partirait aussi tard que possible, comme B. La figee
    doit rester a sa date alors que la tache libre part bien plus tard."""
    debut_a = plan_fige.debut(UUID_A_FIGE)
    debut_b = plan_fige.debut(UUID_B_LIBRE)
    assert debut_a == SCHEDULED_A
    # B n'a aucune contrainte qui la retienne tot : elle doit partir tres loin
    # dans l'horizon, tres au-dela de la date de A.
    assert debut_b > debut_a + timedelta(days=30), (
        "la tache libre B n'a pas ete repoussee au plus tard : debut={}".format(debut_b))


def test_une_tache_figee_repousse_ses_dependants(plan_fige):
    """Une tache qui depend de la figee ne peut pas commencer avant sa fin."""
    assert plan_fige.debut(UUID_A_FIGE) == SCHEDULED_A
    assert plan_fige.debut(UUID_C_DEP) >= plan_fige.fin(UUID_A_FIGE)


def test_tache_figee_entre_dans_le_non_chevauchement(plan_fige):
    """La figee occupe bien la ressource unique : aucun autre bloc ne la
    chevauche dans le temps."""
    blocs = [b for b in (list(plan_fige.blocs_de(UUID_A_FIGE))
                        + list(plan_fige.blocs_de(UUID_B_LIBRE))
                        + list(plan_fige.blocs_de(UUID_C_DEP)))
            if not b.externe]
    # trois taches de 1 h, bloc_min 1 h -> un seul bloc chacune.
    assert len(blocs) == 3

    blocs.sort(key=lambda b: b.debut)
    for precedent, suivant in zip(blocs, blocs[1:]):
        assert precedent.fin <= suivant.debut, (
            "chevauchement entre {} et {}".format(precedent, suivant))
