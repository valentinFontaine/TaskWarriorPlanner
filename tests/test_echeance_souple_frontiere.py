"""L'echeance est une contrainte SOUPLE au regard de la frontiere detaillee.

design.md §5 et la docstring de `_resoudre_une_fois` (planif/solveur.py) :

    « L'echeance est une contrainte souple : une echeance intenable produit du
    retard et l'uuid remonte dans Plan.en_retard, mais elle n'empeche pas les
    autres taches d'etre planifiees. »

Or une tache est "detaillee" (planif/solveur.py, `_horizons` et la boucle
principale de `_resoudre_une_fois`) des que sa limite tombe avant la frontiere
`horizon_detaille_fin`. Ses blocs n'ont alors acces QU'AUX fenetres detaillees
(les jours entierement avant la frontiere) : si la capacite qui s'y trouve ne
suffit pas a caser toute la charge, `retenues` est vide pour un bloc, et
`planif/solveur.py` pose `modele.Add(depart > horizon)` -- domaine vide,
INFEASIBLE. Ce chemin ne passe jamais par la variable de retard : l'echeance
redevient dure en silence des qu'elle tombe avant la frontiere ET que la
capacite avant frontiere est insuffisante.

Hypothese testee : UNE SEULE tache datee, sans dependance, dont la charge
depasse la capacite disponible avant la frontiere (mais pas la capacite totale
de l'horizon), suffit a rendre la passe 1 INFAISABLE -- au lieu de produire du
retard sur cette seule tache et de planifier le reste.

Horloge figee : aucun `datetime.now()`. `T0`/`MAINTENANT` sont des constantes
du fichier, passees en argument a `resoudre`.
"""
from datetime import datetime, timedelta

from planif.calendrier import indice_creneau
from planif.modele import Contexte, Creneau, Tache
from planif.solveur import resoudre

# --- horloge figee ---------------------------------------------------------

T0 = datetime(2026, 10, 5, 0, 0)          # lundi, minuit
MAINTENANT = datetime(2026, 10, 5, 8, 0)  # lundi 08:00
GRANULARITE = timedelta(hours=1)          # grilles alignees sur l'heure : suffit ici

HORIZON_DETAILLE_FIN = T0 + timedelta(days=14)   # lundi aussi (14 = 2 semaines)
HORIZON_FIN = T0 + timedelta(days=35)            # >= 35 j, largement au-dela

# --- contexte "rare" : un seul creneau de 2 h, le lundi, chaque semaine -----
#
# Sur les deux lundis strictement avant la frontiere (celui de T0 et celui de
# T0 + 7 j ; celui de T0 + 14 j tombe PILE sur la frontiere et est donc deja
# considere agrege par `_horizons`, qui exige `plage.fin <= frontiere`), la
# capacite avant frontiere est de 2 x 2 h = 4 h. La tache B ci-dessous demande
# 6 h : 4 h ne suffisent pas, mais l'horizon complet (35 j, soit 5 lundis) en
# offre 10 h, largement assez -- la charge ne depasse que la capacite AVANT
# frontiere, pas la capacite totale.
_CRENEAU_LUNDI = (Creneau(9 * 60, 11 * 60),)   # 09:00-11:00, 2 h
_VIDE = ()

CONTEXTE_RARE = Contexte(
    nom="rare", contexte_tw="rare",
    bloc_min=timedelta(hours=2), marge_jour=timedelta(0),
    grille={
        0: _CRENEAU_LUNDI,  # lundi seulement
        1: _VIDE, 2: _VIDE, 3: _VIDE, 4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)

# --- contexte "large" : lundi a jeudi, 2 h/jour -- pour le temoin 4 ---------
#
# Assez de capacite avant frontiere pour qu'une tache de 2 h y tienne sans
# etre poussee en regime agrege.
CONTEXTE_LARGE = Contexte(
    nom="large", contexte_tw="large",
    bloc_min=timedelta(hours=2), marge_jour=timedelta(0),
    grille={
        0: _CRENEAU_LUNDI, 1: _CRENEAU_LUNDI, 2: _CRENEAU_LUNDI, 3: _CRENEAU_LUNDI,
        4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)

CONTEXTES = {"rare": CONTEXTE_RARE, "large": CONTEXTE_LARGE}

UUID_B = "bbbbbbbb-1111-0000-0000-000000000001"
UUID_D = "dddddddd-1111-0000-0000-000000000002"
UUID_C = "cccccccc-1111-0000-0000-000000000003"


def _tache_b():
    """Datee a J+1, 6 h de charge, contexte "rare" (4 h dispo avant frontiere)."""
    return Tache(uuid=UUID_B, description="B - datee, charge > capacite avant frontiere",
                 estimated=timedelta(hours=6), due=MAINTENANT + timedelta(days=1),
                 tags=("rare",), contexte="rare")


def _tache_d():
    """Independante, datee a J+30, 2 h -- doit rester planifiable malgre B."""
    return Tache(uuid=UUID_D, description="D - independante, echeance lointaine",
                 estimated=timedelta(hours=2), due=MAINTENANT + timedelta(days=30),
                 tags=("rare",), contexte="rare")


def _resoudre(taches, horizon_detaille_fin):
    return resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
                     horizon_detaille_fin=horizon_detaille_fin)


def _sans_chevauchement(blocs):
    """Les blocs, tries par debut, ne se chevauchent jamais entre eux."""
    tries = sorted(blocs, key=lambda b: b.debut)
    return all(tries[i].fin <= tries[i + 1].debut for i in range(len(tries) - 1))


# ==========================================================================
# 1. Une seule tache datee, charge > capacite avant frontiere
# ==========================================================================

def test_echeance_intenable_avant_frontiere_produit_du_retard_pas_infeasible():
    """B doit produire du retard (en_retard), pas rendre la passe 1 vide.

    C'est le coeur de la specification : « une echeance intenable produit du
    retard [...] mais elle n'empeche pas les autres taches d'etre
    planifiees. » Sous le mecanisme actuel, faute de capacite AVANT la
    frontiere, `retenues` est vide pour au moins un bloc et le modele est
    force INFEASIBLE -- ce test est donc attendu ROUGE avant correction.
    """
    plan = _resoudre([_tache_b()], HORIZON_DETAILLE_FIN)

    assert plan.statut != "INFEASIBLE", (
        "statut={} (plan vide) au lieu d'un retard localise sur B".format(plan.statut))

    blocs_b = plan.blocs_de(UUID_B)
    assert sum(b.longueur for b in blocs_b) == 6, (
        "B devrait avoir 6 h placees (3 blocs de 2 h), trouve {} creneaux"
        .format(sum(b.longueur for b in blocs_b)))
    assert len(blocs_b) == 3
    assert UUID_B in plan.en_retard, "B a une echeance intenable : elle doit remonter en_retard"
    assert _sans_chevauchement(blocs_b), "les blocs de B se chevauchent"

    # Trou de contrat (mutation M4) : sans ceci, un solveur qui poserait
    # toujours agrege=False sur les blocs rendus passerait ce test inaperçu.
    # La specification exige agrege == (debut >= frontiere) pour chaque bloc,
    # et au moins un bloc doit tomber au-dela de la frontiere pour que
    # l'assertion soit probante (sinon elle est vraie par vacuite). b.debut
    # est un indice de creneaux depuis T0 (pas un datetime) : on convertit
    # la frontiere avec le meme indice_creneau que le solveur.
    frontiere_indice = indice_creneau(T0, HORIZON_DETAILLE_FIN, GRANULARITE)
    assert any(b.debut >= frontiere_indice for b in blocs_b), (
        "aucun bloc de B au-dela de la frontiere : le test ne prouve rien sur agrege")
    for b in blocs_b:
        assert b.agrege == (b.debut >= frontiere_indice), (
            "bloc indice {}-{} : agrege={} attendu {}"
            .format(b.debut, b.fin, b.agrege, b.debut >= frontiere_indice))


# ==========================================================================
# 2. B (intenable) + D (independante, echeance lointaine) : D doit passer
# ==========================================================================

def test_tache_independante_reste_planifiee_malgre_echeance_intenable_ailleurs():
    """Une echeance intenable sur B ne doit pas empecher D d'etre placee."""
    plan = _resoudre([_tache_b(), _tache_d()], HORIZON_DETAILLE_FIN)

    assert plan.statut != "INFEASIBLE", (
        "statut={} : D aurait du etre planifiee malgre B".format(plan.statut))

    blocs_d = plan.blocs_de(UUID_D)
    assert sum(b.longueur for b in blocs_d) == 2, (
        "D (2 h, echeance tenable) doit etre integralement placee, trouve {} creneaux"
        .format(sum(b.longueur for b in blocs_d)))


# ==========================================================================
# 3. Temoin : sans frontiere (horizon_detaille_fin=None), pas de regression
# ==========================================================================

def test_temoin_sans_frontiere_B_seule_reste_faisable():
    """Sans agregation, B a acces a tout l'horizon (35 j = 5 lundis = 10 h) :
    la charge de 6 h tient largement. Ce test doit etre VERT avant ET apres
    la correction -- il montre que c'est bien la frontiere qui casse le cas
    1, pas un defaut plus general du modele d'echeance souple.
    """
    plan = _resoudre([_tache_b()], None)

    assert plan.statut != "INFEASIBLE"
    blocs_b = plan.blocs_de(UUID_B)
    assert sum(b.longueur for b in blocs_b) == 6
    assert _sans_chevauchement(blocs_b)


def test_temoin_sans_frontiere_B_et_D_ensemble():
    """Meme temoin, avec D en plus : les deux doivent etre integralement
    placees sans frontiere -- vert avant et apres correction.
    """
    plan = _resoudre([_tache_b(), _tache_d()], None)

    assert plan.statut != "INFEASIBLE"
    assert sum(b.longueur for b in plan.blocs_de(UUID_B)) == 6
    assert sum(b.longueur for b in plan.blocs_de(UUID_D)) == 2


# ==========================================================================
# 4. Garde-fou : une tache datee dont la charge TIENT avant la frontiere
#    reste placee entierement en regime detaille (pas d'agregation abusive)
# ==========================================================================

def test_charge_qui_tient_avant_frontiere_reste_en_regime_detaille():
    """Une tache C, datee a J+5, 2 h, contexte "large" (4 x 2 h = 8 h dispo
    avant frontiere) : elle tient sans probleme avant la frontiere. Ce test
    garantit qu'une eventuelle correction ne se contente pas de tout basculer
    en regime agrege -- ses blocs doivent rester au regime detaille (agrege
    == False) et se situer avant la frontiere.
    """
    tache_c = Tache(uuid=UUID_C, description="C - tient avant frontiere",
                     estimated=timedelta(hours=2), due=MAINTENANT + timedelta(days=5),
                     tags=("large",), contexte="large")

    plan = _resoudre([tache_c], HORIZON_DETAILLE_FIN)

    assert plan.statut != "INFEASIBLE"
    blocs_c = plan.blocs_de(UUID_C)
    assert sum(b.longueur for b in blocs_c) == 2
    assert all(not b.agrege for b in blocs_c), (
        "C tient avant la frontiere : ses blocs ne doivent pas passer en regime agrege")

    from planif.calendrier import indice_creneau
    frontiere_idx = indice_creneau(T0, HORIZON_DETAILLE_FIN, GRANULARITE)
    assert all(b.fin <= frontiere_idx for b in blocs_c), (
        "C devrait etre entierement placee avant la frontiere")
    assert UUID_C not in plan.en_retard
