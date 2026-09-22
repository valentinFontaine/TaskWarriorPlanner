"""Tests du lot 4 — solveur, passe 1 (design.md §5).

Ce module teste `planif.solveur.resoudre` et `planif.solveur.Plan` : le
decoupage en blocs, la contrainte de non-chevauchement, la marge
quotidienne, les fenetres de la grille, la precedence et le traitement
souple des echeances intenables.

Toutes les taches utilisees ici sont construites a partir des constantes de
`tests/cas_reference.py` (contexte, horizon, granularite, echeance projet) :
aucune donnee metier n'est inventee dans ce fichier.
"""
from datetime import datetime, timedelta

import pytest

from planif.calendrier import disponibilite, instant_creneau
from planif.modele import Tache
from planif.solveur import resoudre

from tests.cas_reference import (
    CONTEXTE_PRO,
    CONTEXTES,
    ECHEANCE_PROJET,
    GRANULARITE,
    HORIZON_FIN,
    MAINTENANT,
    T0,
)


def _tache(uuid, heures=None, minutes=None, due=None, depends=(), tags=("pro",)):
    """Construit une `Tache` du contexte `pro` pour ces tests.

    `heures` et `minutes` sont mutuellement exclusifs et donnent `estimated`.
    Aucune autre valeur (grille, echeance, granularite) n'est inventee ici :
    tout vient de `tests/cas_reference.py` ou des parametres explicites de
    l'appelant.
    """
    if heures is not None:
        estimated = timedelta(hours=heures)
    else:
        estimated = timedelta(minutes=minutes)
    return Tache(
        uuid=uuid,
        description="tache de test {}".format(uuid),
        projet="NPD.helisides",
        estimated=estimated,
        due=due,
        depends=depends,
        tags=tags,
        contexte="pro",
    )


def _resoudre(taches, **kwargs):
    """Appelle `resoudre` avec les parametres communs du cas de reference."""
    params = dict(
        contextes=CONTEXTES,
        t0=T0,
        maintenant=MAINTENANT,
        horizon_fin=HORIZON_FIN,
        granularite=GRANULARITE,
    )
    params.update(kwargs)
    return resoudre(taches, **params)


def test_tache_datee_est_placee_a_sa_limite_et_pas_avant():
    """Une tache datee doit finir exactement a sa limite effective, pas avant."""
    uuid = "11111111-0000-0000-0000-000000000001"
    tache = _tache(uuid, heures=2, due=ECHEANCE_PROJET)

    plan = _resoudre([tache])

    assert plan.statut in ("OPTIMAL", "FEASIBLE")
    assert plan.retard_total == 0
    # Depuis que la passe 1 n'applique plus de tampon, la limite EST l'echeance :
    # mardi 2026-11-24 17:00, fin de la derniere demi-heure ouvrable de ce jour.
    # L'ancienne valeur (vendredi 20/11) etait l'echeance reculee de 24 h puis
    # ramenee au dernier jour ouvre -- un coussin, pas une limite.
    assert plan.fin(uuid) == datetime(2026, 11, 24, 17, 0)


def test_deux_taches_ne_se_chevauchent_jamais():
    """Prouve le non-chevauchement : aucun bloc ne commence avant la fin du precedent."""
    uuids_courts = [
        "22222222-0000-0000-0000-00000000000{}".format(i) for i in range(1, 5)
    ]
    uuid_long = "22222222-0000-0000-0000-000000000005"
    taches = [_tache(u, heures=2, due=ECHEANCE_PROJET) for u in uuids_courts]
    taches.append(_tache(uuid_long, heures=4, due=ECHEANCE_PROJET))

    plan = _resoudre(taches)

    tous_uuids = set(uuids_courts) | {uuid_long}
    blocs = sorted(
        (b for b in plan.blocs if b.uuid in tous_uuids and not b.externe),
        key=lambda b: b.debut,
    )

    # Le nombre de blocs attendu prouve que le test exerce le bon chemin :
    # 4 taches de 2h en 1 bloc chacune, 1 tache de 4h en 2 blocs (bloc_min = 2h).
    assert len(blocs) == 4 * 1 + 2

    for precedent, suivant in zip(blocs, blocs[1:]):
        assert precedent.fin <= suivant.debut


def test_marge_quotidienne_jamais_depassee():
    """Aucun jour n'occupe plus que la capacite (4h = 8 creneaux de 30 min)."""
    uuids = ["33333333-0000-0000-0000-00000000000{}".format(i) for i in range(1, 6)]
    taches = [_tache(u, heures=2, due=ECHEANCE_PROJET) for u in uuids]

    plan = _resoudre(taches)

    occupation = plan.creneaux_par_jour()
    assert occupation, "le plan ne doit pas etre vide"
    assert all(nb <= 8 for nb in occupation.values())
    # Charge totale = 10h = 2.5 jours utiles : au moins un jour doit etre
    # rempli a sa capacite maximale, sinon le test ne prouve rien.
    assert max(occupation.values()) == 8


def test_aucun_bloc_hors_des_plages_de_la_grille():
    """Chaque bloc non externe tient entierement dans une seule plage disponible."""
    uuids = ["44444444-0000-0000-0000-00000000000{}".format(i) for i in range(1, 4)]
    taches = [_tache(u, heures=2, due=ECHEANCE_PROJET) for u in uuids]

    plan = _resoudre(taches)

    blocs_internes = [b for b in plan.blocs if not b.externe]
    assert blocs_internes, "le plan ne doit pas etre vide"

    for bloc in blocs_internes:
        debut_dt = instant_creneau(T0, bloc.debut, GRANULARITE)
        fin_dt = instant_creneau(T0, bloc.fin, GRANULARITE)
        # La grille du cas de reference ne va jamais jusqu'a minuit (17:00 au
        # plus tard) : un bloc valide ne peut donc pas franchir minuit.
        assert debut_dt.date() == fin_dt.date(), "un bloc ne doit pas franchir minuit"

        jour = debut_dt.date()
        disp = disponibilite(CONTEXTE_PRO, jour, T0, GRANULARITE)
        plages_englobantes = [
            plage
            for plage in disp.plages
            if plage.debut <= bloc.debut and bloc.fin <= plage.fin
        ]
        assert len(plages_englobantes) == 1, (
            "le bloc {} doit tenir dans exactement une plage disponible"
            .format(bloc)
        )


def test_rien_ne_commence_avant_maintenant():
    """Aucun bloc ne commence avant l'instant courant injecte."""
    uuids = ["55555555-0000-0000-0000-00000000000{}".format(i) for i in range(1, 4)]
    taches = [_tache(u, heures=2, due=ECHEANCE_PROJET) for u in uuids]

    plan = _resoudre(taches)

    indice_maintenant = (MAINTENANT - T0) // GRANULARITE
    assert plan.blocs, "le plan ne doit pas etre vide"
    for bloc in plan.blocs:
        assert bloc.debut >= indice_maintenant


def test_bloc_minimum_respecte():
    """Une tache de 5h avec bloc_min=2h se decoupe en blocs 2h, 2h, 1h (somme = 5h)."""
    uuid = "66666666-0000-0000-0000-000000000001"
    tache = _tache(uuid, heures=5, due=ECHEANCE_PROJET)

    plan = _resoudre([tache])

    blocs = plan.blocs_de(uuid)
    assert len(blocs) == 3

    durees = [
        (b.fin - b.debut) * GRANULARITE for b in blocs
    ]
    assert durees == [timedelta(hours=2), timedelta(hours=2), timedelta(hours=1)]
    assert sum(durees, timedelta()) == timedelta(hours=5)


def test_tache_plus_courte_que_le_bloc_minimum_tient_en_un_bloc():
    """Une tache de 30 min (< bloc_min de 2h) donne un seul bloc de 30 min."""
    uuid = "77777777-0000-0000-0000-000000000001"
    tache = _tache(uuid, minutes=30, due=ECHEANCE_PROJET)

    plan = _resoudre([tache])

    blocs = plan.blocs_de(uuid)
    assert len(blocs) == 1
    assert (blocs[0].fin - blocs[0].debut) * GRANULARITE == timedelta(minutes=30)


def test_tache_insecable_tient_en_un_seul_bloc():
    """Une tache +insecable de 3h (qui tient exactement dans une plage) donne un seul bloc."""
    uuid = "88888888-0000-0000-0000-000000000001"
    tache = _tache(uuid, heures=3, due=ECHEANCE_PROJET, tags=("pro", "insecable"))

    plan = _resoudre([tache])

    blocs = plan.blocs_de(uuid)
    assert len(blocs) == 1
    assert (blocs[0].fin - blocs[0].debut) * GRANULARITE == timedelta(hours=3)


def test_tache_insecable_trop_longue_pour_toute_plage_est_infeasible():
    """Une tache +insecable de 4h ne tient dans aucune plage (3h max) : le plan est INFEASIBLE.

    Choix assene : puisque le decoupage en un seul bloc est une contrainte
    structurelle dure (design.md §5, "fenetres"), et non l'echeance (qui,
    elle, est souple), l'absence de toute plage capable d'accueillir ce bloc
    rend le probleme insoluble dans son ensemble — il n'y a pas de variable de
    retard qui puisse absorber ce cas. C'est donc `statut == 'INFEASIBLE'`
    qui est assene ici, pas un simple signalement dans `en_retard`.
    """
    uuid = "88888888-0000-0000-0000-000000000002"
    tache = _tache(uuid, heures=4, due=ECHEANCE_PROJET, tags=("pro", "insecable"))

    plan = _resoudre([tache])

    assert plan.statut == "INFEASIBLE"


def test_echeance_intenable_n_empeche_pas_les_autres():
    """Une tache impossible est signalee en retard sans empoisonner les taches saines.

    C'est le test le plus important du lot (tasks.md, lot 4) : un outil
    concurrent laissait une seule tache infaisable monopoliser sept journees.
    """
    uuid_impossible = "99999999-0000-0000-0000-000000000001"
    # due proche (moins d'une semaine) pour une charge de 40h : la limite
    # effective ne laisse que quelques jours ouvres, largement moins que les
    # 20h utiles necessaires pour absorber 40h de travail.
    due_proche = datetime(2026, 10, 12, 17, 0)
    tache_impossible = _tache(uuid_impossible, heures=40, due=due_proche)

    uuids_saines = [
        "99999999-0000-0000-0000-00000000000{}".format(i) for i in range(2, 5)
    ]
    taches_saines = [_tache(u, heures=2, due=ECHEANCE_PROJET) for u in uuids_saines]

    plan = _resoudre([tache_impossible] + taches_saines)

    # a. le plan n'est pas vide et n'est pas globalement infaisable.
    assert plan.blocs
    assert plan.statut != "INFEASIBLE"

    # b. le retard global est strictement positif.
    assert plan.retard_total > 0

    # c. la tache impossible est bien signalee en retard.
    assert uuid_impossible in plan.en_retard

    # d. les trois taches saines sont integralement planifiees et ne sont
    # PAS en retard : c'est le point qui compte, une seule tache impossible
    # ne doit pas empoisonner le plan.
    for uuid in uuids_saines:
        blocs = plan.blocs_de(uuid)
        duree_totale = sum(
            ((b.fin - b.debut) * GRANULARITE for b in blocs), timedelta()
        )
        assert duree_totale == timedelta(hours=2)
        assert uuid not in plan.en_retard


def test_precedence_simple():
    """B ne peut pas commencer avant la fin de A, dont il depend."""
    uuid_a = "aaaaaaab-0000-0000-0000-000000000001"
    uuid_b = "aaaaaaab-0000-0000-0000-000000000002"
    tache_a = _tache(uuid_a, heures=2)
    tache_b = _tache(uuid_b, heures=2, due=ECHEANCE_PROJET, depends=(uuid_a,))

    plan = _resoudre([tache_a, tache_b])

    blocs_a = plan.blocs_de(uuid_a)
    blocs_b = plan.blocs_de(uuid_b)
    assert blocs_a and blocs_b, "les deux taches doivent avoir des blocs"
    assert plan.fin(uuid_a) <= plan.debut(uuid_b)


def test_plan_deterministe():
    """Deux resolutions de la meme entree rendent exactement le meme plan."""
    uuids = ["abcabcab-0000-0000-0000-00000000000{}".format(i) for i in range(1, 4)]
    taches = [_tache(u, heures=2, due=ECHEANCE_PROJET) for u in uuids]

    plan1 = _resoudre(taches)
    plan2 = _resoudre(taches)

    assert plan1.blocs == plan2.blocs
