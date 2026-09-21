"""Lot 5 — tiers et precedences. C'est le scenario qui a motive tout le projet.

`proposal.md` decision 10 : « Les tiers ne consomment pas de capacite. Un
intervalle de duree `estimated`, hors de la contrainte de non-chevauchement. »

Les valeurs attendues servent a **detecter une erreur**, pas a valider un
resultat : aucune regle n'a ete recalibree pour tomber dessus. Un ecart est une
information, et il est ecrit dans RAPPORT-NUIT.md.

Horloge figee au lundi 2026-10-05 08:00 (voir `tests/cas_reference.py`).
"""
from datetime import date, datetime, timedelta

import pytest

from planif.calendrier import indice_creneau, instant_creneau
from planif.solveur import resoudre
from planif.tampon import limites_effectives
from tests.cas_reference import (CONTEXTE_PRO, CONTEXTES, ECHEANCE_PROJET,
                                 GRANULARITE, HORIZON_FIN, MAINTENANT, T0,
                                 UUID_A, UUID_B, UUID_C, UUID_D, chaine,
                                 taches_de_remplissage)

# L'echeance du projet porte sur la tache terminale de la chaine (D). C'est une
# INTERPRETATION : `design.md` §2 donne la forme d'une echeance de projet mais ne
# dit pas comment elle descend sur les taches. On la pose sur les taches du
# projet qui n'ont aucun successeur dans le projet. Declaree dans RAPPORT-NUIT.md.
LIMITE_D_ATTENDUE = datetime(2026, 11, 20, 17, 0)   # vendredi


def _avec_due_sur_d(taches):
    """Recree D avec le `due` du projet (les Tache sont frozen)."""
    from dataclasses import replace
    return [replace(t, due=ECHEANCE_PROJET) if t.uuid == UUID_D else t
            for t in taches]


@pytest.fixture(scope="module")
def plan_reference():
    taches = _avec_due_sur_d(chaine())
    return resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)


# --------------------------------------------------------------------------
# Le tampon, en amont du solveur
# --------------------------------------------------------------------------

def test_limite_de_d_est_vendredi_20_novembre_17h():
    """Le tampon est applique une fois : 24/11 17:00 -> 23/11 17:00 -> 20/11 17:00."""
    taches = _avec_due_sur_d(chaine())
    limites = limites_effectives(taches, CONTEXTES)
    assert limites[UUID_D] == LIMITE_D_ATTENDUE
    assert LIMITE_D_ATTENDUE.weekday() == 4        # vendredi


def test_le_tampon_distingue_bien_les_trois_cas():
    """Controle 3 : ni 24/11 (non applique), ni 19/11 ou avant (applique deux fois)."""
    taches = _avec_due_sur_d(chaine())
    limite = limites_effectives(taches, CONTEXTES)[UUID_D]
    assert limite != datetime(2026, 11, 24, 17, 0), "tampon non applique"
    assert limite > datetime(2026, 11, 19, 23, 59), "tampon applique deux fois"
    assert limite == LIMITE_D_ATTENDUE


def test_le_tampon_ne_se_cumule_pas_le_long_de_la_chaine():
    """A, B et C heritent de la limite de D sans re-tamponner."""
    taches = _avec_due_sur_d(chaine())
    limites = limites_effectives(taches, CONTEXTES)
    assert limites[UUID_A] == LIMITE_D_ATTENDUE
    assert limites[UUID_B] == LIMITE_D_ATTENDUE
    assert limites[UUID_C] == LIMITE_D_ATTENDUE


# --------------------------------------------------------------------------
# Les dates du cas de reference
# --------------------------------------------------------------------------

def test_le_plan_est_resolu(plan_reference):
    assert plan_reference.statut in ("OPTIMAL", "FEASIBLE")
    assert plan_reference.retard_total == 0
    assert plan_reference.en_retard == ()
    # quatre taches, aucune perdue en route
    for uuid in (UUID_A, UUID_B, UUID_C, UUID_D):
        assert plan_reference.blocs_de(uuid), "tache non planifiee : " + uuid


def test_fin_de_d_est_vendredi_20_novembre_17h(plan_reference):
    """Attendu du cahier de route : fin de D = vendredi 2026-11-20 a 17:00."""
    fin = plan_reference.fin(UUID_D)
    assert fin == datetime(2026, 11, 20, 17, 0)
    assert fin.weekday() == 4


def test_c_dure_exactement_28_jours_calendaires(plan_reference):
    """Le delai fournisseur est un delai CALENDAIRE : 28 jours pleins, pas 28 jours
    ouvres. Il enjambe les week-ends et les nuits sans y perdre une heure."""
    debut = plan_reference.debut(UUID_C)
    fin = plan_reference.fin(UUID_C)
    assert fin - debut == timedelta(days=28)


def test_c_finit_exactement_quand_d_commence(plan_reference):
    assert plan_reference.fin(UUID_C) == plan_reference.debut(UUID_D)


def test_b_est_le_vendredi_23_octobre_avant_14h(plan_reference):
    """Attendu du cahier de route : B le vendredi 2026-10-23, avant 14:00."""
    debut = plan_reference.debut(UUID_B)
    fin = plan_reference.fin(UUID_B)
    assert debut.date() == date(2026, 10, 23)
    assert debut.weekday() == 4                     # vendredi
    assert fin <= datetime(2026, 10, 23, 14, 0)
    # B fait 30 min et tient en un seul bloc, plus court que le bloc minimum
    assert len(plan_reference.blocs_de(UUID_B)) == 1
    assert fin - debut == timedelta(minutes=30)


def test_a_est_reparti_sur_les_22_et_23_octobre(plan_reference):
    """Attendu du cahier de route : A reparti sur les 22 et 23 octobre.

    A fait 4 h, le bloc minimum est 2 h : deux blocs. Ils ne tiennent pas tous
    les deux dans la matinee du 23 avant B, donc le premier recule au 22.
    """
    blocs = plan_reference.blocs_de(UUID_A)
    assert len(blocs) == 2
    jours = sorted({instant_creneau(T0, b.debut, GRANULARITE).date() for b in blocs})
    assert jours == [date(2026, 10, 22), date(2026, 10, 23)]
    # conservation de la duree : 4 h au total
    total = sum(b.fin - b.debut for b in blocs) * GRANULARITE
    assert total == timedelta(hours=4)


def test_a_puis_b_puis_c_puis_d(plan_reference):
    """Les precedences sont tenues de bout en bout."""
    p = plan_reference
    assert p.fin(UUID_A) <= p.debut(UUID_B)
    assert p.fin(UUID_B) <= p.debut(UUID_C)
    assert p.fin(UUID_C) <= p.debut(UUID_D)


# --------------------------------------------------------------------------
# Controle 1 — la chaine est gouvernee par le delai, pas par la capacite
# --------------------------------------------------------------------------

def test_controle_1_le_delai_se_propage_bien_en_arriere(plan_reference):
    """Si B tombait en novembre, le delai de 4 semaines ne se propagerait pas en
    arriere : la commande doit reculer d'autant que dure la fabrication."""
    assert plan_reference.debut(UUID_B) < datetime(2026, 11, 1), \
        "B est en novembre : le delai fournisseur ne remonte pas la chaine"


def test_controle_1_l_intervalle_externe_bloque_bien_ses_successeurs(plan_reference):
    """Si D tombait en octobre, l'intervalle externe ne bloquerait pas son
    successeur : le test commencerait avant la fin de la fabrication."""
    assert plan_reference.debut(UUID_D) >= datetime(2026, 11, 1), \
        "D est en octobre : l'intervalle externe ne bloque pas ses successeurs"


# --------------------------------------------------------------------------
# Controle 2 — la capacite reste INTEGRALEMENT disponible pendant les 28 jours
# --------------------------------------------------------------------------
# C'est le bug que tout ce projet existe pour eviter : si un seul jour ouvre
# montre une capacite reduite par C, c'est que C est entre dans AddNoOverlap.

@pytest.fixture(scope="module")
def plan_avec_remplissage():
    taches = _avec_due_sur_d(chaine()) + taches_de_remplissage(3, 30)
    return resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)


def test_controle_2_les_trois_taches_de_30h_sont_integralement_placees(
        plan_avec_remplissage):
    """90 h de travail supplementaire tiennent, malgre les 28 jours de fabrication.

    Si C consommait de la capacite, il ne resterait qu'une quinzaine de jours
    ouvres hors fabrication, soit environ 60 h : les 90 h ne tiendraient pas.
    """
    plan = plan_avec_remplissage
    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    for tache in taches_de_remplissage(3, 30):
        blocs = plan.blocs_de(tache.uuid)
        assert blocs, "tache de remplissage non planifiee : " + tache.description
        total = sum(b.fin - b.debut for b in blocs) * GRANULARITE
        assert total == timedelta(hours=30), tache.description
    assert plan.retard_total == 0
    assert plan.en_retard == ()


def test_controle_2_la_capacite_reste_entiere_pendant_la_fabrication(
        plan_avec_remplissage):
    """Le controle qui compte : 4 h par jour ouvre restent utilisables pendant C.

    On compte les jours ouvres, situes dans l'intervalle de fabrication, ou
    l'utilisateur travaille bien 4 h pleines sur autre chose que C. Si C etait
    entre dans `AddNoOverlap`, ce nombre serait zero.
    """
    plan = plan_avec_remplissage
    debut_c = plan.debut(UUID_C)
    fin_c = plan.fin(UUID_C)
    assert fin_c - debut_c == timedelta(days=28)

    par_jour = plan.creneaux_par_jour()
    jours_pleins = []
    jour = debut_c.date() + timedelta(days=1)   # premier jour entierement dans C
    while jour < fin_c.date():
        if CONTEXTE_PRO.est_ouvre(jour):
            occupe = par_jour.get(jour, 0)
            assert occupe <= 8, \
                "capacite quotidienne depassee le {} : {} creneaux".format(jour, occupe)
            if occupe == 8:
                jours_pleins.append(jour)
        jour += timedelta(days=1)

    # 28 jours calendaires du 23/10 au 20/11 contiennent 20 jours ouvres pleins.
    assert len(jours_pleins) >= 19, (
        "seulement {} jours ouvres pleins pendant la fabrication : la capacite "
        "est rognee par C".format(len(jours_pleins)))


def test_controle_2_du_travail_chevauche_bien_l_intervalle_externe(
        plan_avec_remplissage):
    """Assene directement l'absence de C dans AddNoOverlap.

    On compte les blocs NON externes dont l'intervalle chevauche celui de C.
    Avec un `AddNoOverlap` incluant C, ce nombre serait exactement zero.
    """
    plan = plan_avec_remplissage
    bloc_c = plan.blocs_de(UUID_C)[0]
    chevauchants = [b for b in plan.blocs
                    if not b.externe and b.debut < bloc_c.fin and b.fin > bloc_c.debut]
    assert len(chevauchants) > 0, "aucun travail pendant la fabrication"
    # Ce n'est pas un chevauchement marginal : l'essentiel des 90 h est la-dedans.
    creneaux = sum(b.fin - b.debut for b in chevauchants)
    assert creneaux * GRANULARITE >= timedelta(hours=60), (
        "seulement {} de travail pendant la fabrication".format(
            creneaux * GRANULARITE))


def test_controle_2_la_marge_quotidienne_n_est_jamais_depassee(
        plan_avec_remplissage):
    """4 h utiles par jour, jamais plus : la marge de 2 h est bien reservee."""
    for jour, occupe in plan_avec_remplissage.creneaux_par_jour().items():
        assert occupe <= 8, "{} : {} creneaux".format(jour, occupe)
        assert CONTEXTE_PRO.est_ouvre(jour), "travail place un jour non ouvre : " + str(jour)


# --------------------------------------------------------------------------
# L'intervalle externe lui-meme
# --------------------------------------------------------------------------

def test_l_intervalle_externe_ignore_la_grille(plan_reference):
    """C traverse nuits et week-ends : son intervalle n'est pas borne par la grille."""
    bloc = plan_reference.blocs_de(UUID_C)[0]
    assert bloc.externe is True
    debut = instant_creneau(T0, bloc.debut, GRANULARITE)
    fin = instant_creneau(T0, bloc.fin, GRANULARITE)
    # l'intervalle contient au moins quatre samedis
    samedis = sum(1 for n in range((fin - debut).days)
                  if (debut + timedelta(days=n)).weekday() == 5)
    assert samedis >= 4


def test_l_externe_ne_compte_pas_dans_la_capacite(plan_reference):
    """`creneaux_par_jour` ignore les blocs externes, par definition."""
    total = sum(plan_reference.creneaux_par_jour().values())
    # A (4 h) + B (30 min) + D (3 h) = 7 h 30 = 15 creneaux. C n'y est pas.
    assert total == 15
