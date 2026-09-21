"""Lot de correction de dette — convention sur les `datetime` naifs.

RAPPORT-NUIT.md §1.2 point 8 : `planif/tampon.py` traitait un naif comme
local, `planif/verifications.py` le traitait comme UTC. Les deux ne peuvent
pas etre vrais en meme temps des lors que `planif/taskwarrior.py` produit de
l'UTC aware et que les grilles horaires sont locales et naives.

Convention retenue (design.md §2) : tout est naif local A L'INTERIEUR du
modele ; la conversion se fait a la frontiere, dans
`planif/taskwarrior.py::vers_local_naif`, importee telle quelle par
`planif/tampon.py` et `planif/verifications.py`.

Ce fichier melange volontairement les deux sources (Taskwarrior et les
modules de calcul) : c'est l'exigence explicite de ce lot de dette.

Horloge figee : aucun `datetime.now()` ici, `maintenant` est toujours passe
en argument.
"""
from datetime import datetime, timedelta, timezone

from planif import tampon, verifications
from planif.modele import Contexte, Creneau, Tache
from planif.taskwarrior import charger_taches, vers_local_naif

CHAINE_AVEC_DUE = [
    {"uuid": "11111111-1111-1111-1111-111111111111",
     "description": "Tester la piece recue", "status": "pending",
     "entry": "20261005T080000Z", "estTime": "PT3H",
     "due": "20261124T160000Z", "tags": ["pro"]},
]


def _contexte_toujours_ouvert(nom="pro"):
    """Un contexte dont la grille est ouverte tous les jours, journee entiere.

    Sert uniquement a isoler le calcul du tampon/verification de la
    question, hors sujet ici, des jours feries ou des grilles partielles
    (deja traitees par les lots 1 et 2).
    """
    grille = {jour: (Creneau(0, 24 * 60),) for jour in range(7)}
    return Contexte(nom=nom, contexte_tw=nom, bloc_min=timedelta(hours=1),
                     marge_jour=timedelta(0), grille=grille)


# ---------------------------------------------------------------------------
# 1. La frontiere Taskwarrior rend du naif local
# ---------------------------------------------------------------------------

def test_taskwarrior_rend_du_naif_local(base_jetable):
    base_jetable.semer(CHAINE_AVEC_DUE)
    taches = charger_taches(env=base_jetable.env)
    assert len(taches) == 1
    due = taches[0].due

    assert due.tzinfo is None, "la frontiere doit rendre un naif local, pas de l'UTC aware"

    # L'attendu est calcule a partir du fuseau de la machine qui execute le
    # test, jamais ecrit en dur (sinon le test ne passerait que sur une
    # machine dans le bon fuseau).
    due_utc_aware = datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc)
    attendu = due_utc_aware.astimezone().replace(tzinfo=None)
    assert due == attendu


# ---------------------------------------------------------------------------
# 2. tampon et verifications s'accordent sur un meme instant
# ---------------------------------------------------------------------------

def test_tampon_et_verifications_s_accordent_sur_un_meme_instant():
    contexte = _contexte_toujours_ouvert()

    due_aware = datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc)
    due_local_naif = due_aware.astimezone().replace(tzinfo=None)

    effective_aware = tampon.echeance_effective(due_aware, contexte)
    effective_local = tampon.echeance_effective(due_local_naif, contexte)
    assert effective_aware == effective_local

    # Meme chose pour la detection de due depassee (code "due-depassee").
    maintenant = due_local_naif + timedelta(days=1)  # naif local, apres due
    tache_aware = Tache(uuid="a", description="A", due=due_aware, contexte="pro")
    tache_local = Tache(uuid="b", description="B", due=due_local_naif, contexte="pro")

    anomalies_aware = verifications.verifier_dues([tache_aware], maintenant)
    anomalies_local = verifications.verifier_dues([tache_local], maintenant)

    assert len(anomalies_aware) == 1
    assert len(anomalies_local) == 1
    assert anomalies_aware[0].code == anomalies_local[0].code == "due-depassee"
    assert anomalies_aware[0].uuids == ("a",)
    assert anomalies_local[0].uuids == ("b",)


# ---------------------------------------------------------------------------
# 3. due aware + maintenant naif : pas d'exception, verdict correct
# ---------------------------------------------------------------------------

def test_due_aware_et_maintenant_naif_ne_plantent_pas_et_tranchent_juste():
    contexte = _contexte_toujours_ouvert()
    contextes = {"pro": contexte}

    due_aware = datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc)
    due_local_naif = due_aware.astimezone().replace(tzinfo=None)

    # Cas 1 : maintenant naif strictement APRES due -> due depassee.
    maintenant_apres = due_local_naif + timedelta(hours=1)
    tache_en_retard = Tache(uuid="r", description="En retard",
                             estimated=timedelta(hours=1),
                             due=due_aware, contexte="pro")
    anomalies = verifications.pre_verifications(
        [tache_en_retard], contextes, maintenant_apres)
    codes = {a.code for a in anomalies}
    assert "due-depassee" in codes

    # Cas 2 : maintenant naif strictement AVANT due -> pas de due-depassee.
    maintenant_avant = due_local_naif - timedelta(hours=1)
    tache_a_temps = Tache(uuid="t", description="A temps",
                           estimated=timedelta(hours=1),
                           due=due_aware, contexte="pro")
    anomalies_ok = verifications.pre_verifications(
        [tache_a_temps], contextes, maintenant_avant)
    codes_ok = {a.code for a in anomalies_ok}
    assert "due-depassee" not in codes_ok


# ---------------------------------------------------------------------------
# 4. La factorisation : les deux modules utilisent la meme fonction
# ---------------------------------------------------------------------------

def test_les_deux_modules_utilisent_la_meme_conversion():
    """Assene la factorisation : `tampon` et `verifications` importent, sous
    le meme nom, exactement le meme objet fonction que
    `planif.taskwarrior.vers_local_naif` (identite d'objet, pas simple
    equivalence de comportement)."""
    assert tampon.vers_local_naif is vers_local_naif
    assert verifications.vers_local_naif is vers_local_naif
