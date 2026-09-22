"""Le plan ne doit pas dependre de la charge de la machine.

## Le symptome

Deux executions de la passe 1, **memes donnees et meme code**, a quelques
minutes d'intervalle :

    run A : 26 s -> OPTIMAL
    run B : 94 s -> FEASIBLE

Pour 13 taches. La seule variable etait la charge de la machine.

## Ce que la mesure a montre

On a instrumente les deux `Solve` de `resoudre` sur les donnees reelles
(278 taches, 54 datees), a budget d'horloge variable :

    budget mur | statut   | objectif | empreinte du plan
       300 s   | OPTIMAL  |   1949   | -4562147786156008567
        60 s   | OPTIMAL  |   1949   | -4562147786156008567
        20 s   | FEASIBLE |   1949   |  5071140208841883476
        12 s   | FEASIBLE |   1949   |  5071140208841883476

Et surtout, d'un run a l'autre :

    temps DETERMINISTE : 5,460 puis 12,978  -- identique a la milliseconde
    branches           : 136 568 / 277 628  -- identique
    temps MUR          : 21,82 s puis 20,17 s  -- ca, non

**La recherche est parfaitement deterministe. Le seul element non
deterministe de la passe 1 etait son critere d'ARRET**, une horloge murale
(`max_time_in_seconds`). `num_search_workers = 1` et `random_seed = 0` ne
suffisaient donc pas a tenir la promesse de reproductibilite ecrite en face
d'eux : ils figent le chemin, pas le moment ou l'on s'arrete de le parcourir.

Noter ce que le tableau dit exactement : l'objectif ne bouge pas (1949 dans
les quatre cas), mais **le plan, lui, change**. L'optimum n'est pas unique ;
s'arreter plus tot rend un autre optimum, aussi bon et pourtant different. Le
degat n'est pas « un plan moins bon », c'est « un plan qui bouge sans raison ».

Avec 21,8 s consommees pour un plafond a 60 s, la marge etait de 2,7x : toute
machine ralentie au-dela faisait basculer le resultat. C'est exactement ce que
l'utilisateur a observe.

## La correction

Le critere d'arret devient `max_deterministic_time` : un budget de TRAVAIL,
insensible a la vitesse de la machine. L'horloge reste, mais reculee et
retrogradee au rang de **filet** — et quand ce filet mord, on le dit, parce
qu'a ce moment-la, et a ce moment-la seulement, le plan cesse d'etre
reproductible.

## Verification apres correction, sur les donnees reelles

Six resolutions de la meme instance, dans trois processus distincts, budget
volontairement rogne a 3 unites pour que la recherche soit bien COUPEE — c'est
le cas ou le defaut se manifestait :

    determ = 3,000 partout | branches = 86 850 puis 106 983 partout
    empreinte du plan : 8dc276e26678cd74, les six fois

Dont deux resolutions lancees pendant que la suite de tests chargeait la
machine : meme plan.

Une note pour qui relira ce banc : la premiere version comparait les plans avec
`hash()`, et donnait deux empreintes differentes pour le meme plan d'un
processus a l'autre — de quoi croire un instant que la correction ne tenait
pas. `hash()` est **sale par processus** pour les chaines de caracteres. C'etait
l'instrument, pas la mesure. Les empreintes ci-dessus sont des SHA-1.

## Pourquoi il n'y a pas ici de test « deux runs sous charges differentes »

Ce serait le test le plus direct, et il serait malhonnete : charger une
machine depuis pytest ne se fait pas de facon fiable, et un test dont le
verdict depend de la charge aurait exactement le defaut qu'il pretend
attraper. On teste donc le **mecanisme** — le critere d'arret pose sur chaque
solveur — plutot que sa consequence statistique. AGENTS.md §3.
"""
import logging
from dataclasses import replace
from datetime import timedelta

import pytest
from ortools.sat.python import cp_model

from planif import solveur
from planif.modele import Tache
from planif.solveur import completer, resoudre
from tests.cas_reference import (CONTEXTES, GRANULARITE, HORIZON_FIN,
                                 MAINTENANT, T0, chaine)


@pytest.fixture
def parametres_observes(monkeypatch):
    """Les `parameters` de chaque `CpSolver` reellement utilise."""
    observes = []
    original = cp_model.CpSolver.Solve

    def espion(self, modele, *a, **kw):
        observes.append(self.parameters)
        return original(self, modele, *a, **kw)

    monkeypatch.setattr(cp_model.CpSolver, "Solve", espion)
    return observes


def _instance_lourde(nombre=24):
    """Assez de taches pour que la recherche dure plus que quelques millisecondes.

    Le cas de reference a quatre taches se resout trop vite pour qu'un filet
    d'horloge puisse mordre de facon fiable ; ce test-ci a besoin qu'il morde.
    """
    taches = list(chaine())
    for i in range(nombre):
        taches.append(Tache(
            uuid="eeee{:04d}-0000-0000-0000-00000000eeee".format(i),
            description="charge {}".format(i),
            estimated=timedelta(hours=3),
            due=MAINTENANT + timedelta(days=5 + i),
            tags=("pro",), contexte="pro", urgency=float(i)))
    return taches


def _empreinte(plan):
    return tuple(sorted((b.uuid, b.indice, b.debut, b.fin) for b in plan.blocs))


def test_resoudre_s_arrete_sur_un_budget_de_travail_pas_sur_une_horloge(
        parametres_observes):
    """Le critere d'arret de la passe 1 ne doit pas dependre de la machine."""
    resoudre(chaine(), CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)

    assert parametres_observes, "aucun solveur n'a ete construit"
    for parametres in parametres_observes:
        assert parametres.max_deterministic_time == solveur.TEMPS_DETERMINISTE_MAX, (
            "la passe 1 s'arrete encore sur l'horloge murale : deux executions "
            "identiques peuvent rendre deux plans differents")


def test_completer_s_arrete_sur_le_meme_budget_de_travail(parametres_observes):
    """La passe 2 a exactement le meme defaut, et il y mord a chaque execution.

    Sur les donnees reelles elle consommait ses 60 s a tous les coups : son
    resultat etait donc integralement decide par la vitesse de la machine.
    """
    plan = resoudre([], CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    del parametres_observes[:]

    libre = Tache(uuid="ffff0001-0000-0000-0000-0000000000ff",
                  description="non datee", estimated=timedelta(hours=2),
                  tags=("pro",), contexte="pro")
    completer(plan, [libre], CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)

    assert parametres_observes, "aucun solveur n'a ete construit"
    for parametres in parametres_observes:
        assert parametres.max_deterministic_time == solveur.TEMPS_DETERMINISTE_MAX


def test_le_diagnostic_s_arrete_lui_aussi_sur_un_budget_de_travail(
        parametres_observes):
    """Le meme defaut, au meme endroit du code, pour un degat different.

    `diagnostic.py` ne produit pas de plan : il nomme les contraintes qui
    rendent le modele infaisable. Arrete par l'horloge, il peut designer un
    noyau different d'une execution a l'autre — donc accuser une autre tache.
    Un diagnostic qui change d'avis selon la charge de la machine ne sert a
    rien.
    """
    from planif import diagnostic

    diagnostic.diagnostiquer(chaine(), CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                             GRANULARITE)

    assert parametres_observes, "aucun solveur n'a ete construit"
    for parametres in parametres_observes:
        assert parametres.max_deterministic_time == diagnostic.TEMPS_DETERMINISTE_MAX


def test_le_filet_d_horloge_est_beaucoup_plus_large_que_le_budget_de_travail():
    """Un filet qui mord en usage normal n'est pas un filet, c'est un critere.

    La comparaison doit porter sur le budget MAXIMAL, celui du dernier palier
    d'escalade, et non sur le budget de depart : c'est lui qui peut approcher le
    filet. 45 unites valent environ 76 s d'horloge sur une machine au repos
    (mesure sur l'instance dure), le filet est a 300 s.
    """
    budget_max = solveur.TEMPS_DETERMINISTE_MAX * max(solveur.FACTEURS_ESCALADE)
    assert solveur.SECONDES_MAX >= 3 * budget_max


def test_quand_le_filet_mord_on_le_dit(monkeypatch, caplog):
    """Le mode de panne de ce projet, c'est de perdre du contenu en silence.

    Si l'horloge arrete la recherche, le plan cesse d'etre reproductible. C'est
    tolerable ; le taire ne l'est pas.
    """
    monkeypatch.setattr(solveur, "SECONDES_MAX", 0.02)

    with caplog.at_level(logging.WARNING, logger="planif.solveur"):
        resoudre(_instance_lourde(), CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                 GRANULARITE)

    messages = [enregistrement.message for enregistrement in caplog.records]
    assert any("reproductible" in message.lower() for message in messages), (
        "la recherche a ete arretee par l'horloge et le plan rendu ne le dit "
        "pas : il est presente comme un plan normal alors qu'une autre "
        "execution en rendrait un autre. Messages vus : {}".format(messages))


def test_un_budget_epuise_sans_solution_ne_se_fait_pas_passer_pour_infaisable(
        monkeypatch, caplog):
    """Defaut trouve en balayant le budget, pas en relisant le code.

    Sous 2 unites de budget, sur les donnees reelles, le second `Solve` de la
    passe 1 rend `UNKNOWN` et `resoudre` rendait un plan vide etiquete
    **INFEASIBLE**. C'est faux, et c'est la pire des deux erreurs possibles :

    - `INFEASIBLE` veut dire « tes contraintes se contredisent, aucun plan
      n'existe » — on va chercher la tache coupable, on lance le diagnostic ;
    - `UNKNOWN` veut dire « je n'ai pas eu le temps » — on augmente le budget.

    Le premier envoie l'utilisateur chercher un probleme qui n'existe pas. Et
    rien ne le signalait : l'arret etant bien tombe sur le budget de travail,
    `_signaler_arret_horloge` se taisait, a juste titre. Un plan vide sortait
    donc sans un mot.
    """
    monkeypatch.setattr(solveur, "TEMPS_DETERMINISTE_MAX", 0.002)

    with caplog.at_level(logging.WARNING, logger="planif.solveur"):
        plan = resoudre(_instance_lourde(60), CONTEXTES, T0, MAINTENANT,
                        HORIZON_FIN, GRANULARITE)

    if plan.blocs:
        pytest.skip("budget trop genereux sur cette machine : le solveur a "
                    "trouve une solution, le cas vise n'est pas atteint")

    assert plan.statut != "INFEASIBLE", (
        "un plan vide faute de budget est annonce INFEASIBLE : l'utilisateur "
        "va chercher une contradiction dans ses taches alors qu'il lui suffit "
        "d'augmenter le budget")
    messages = [e.message for e in caplog.records]
    assert any("budget" in m.lower() for m in messages), (
        "plan vide rendu sans un mot. Messages vus : {}".format(messages))


def test_le_budget_monte_seulement_si_le_plan_ressort_vide(monkeypatch, caplog):
    """Le budget n'est pas devine : il est essaye, puis augmente si besoin.

    Le balayage sur les donnees reelles a montre deux choses contradictoires :

        instance facile (09:00) : plan final des 2 unites, falaise a 2
        instance dure   (17:00) : plan final des 5 unites, falaise a 5

    « Plan final » au sens fort : l'empreinte ne bouge plus jusqu'a 30, alors
    que le budget coute 58 s de plus. Mais sous la falaise, ce n'est pas un plan
    degrade, c'est ZERO bloc — et la falaise se deplace avec la difficulte de
    l'instance. Aucun nombre fixe n'est donc a la fois rapide et sur.

    D'ou l'escalade : on part petit, et on ne remonte que si le plan est vide.
    Chaque tentative restant deterministe, le resultat final l'est aussi.
    """
    appels = []
    original = solveur._resoudre_une_fois

    def espion(*a, **kw):
        appels.append(kw.get("budget", a[-1] if a else None))
        return original(*a, **kw)

    monkeypatch.setattr(solveur, "_resoudre_une_fois", espion)
    monkeypatch.setattr(solveur, "TEMPS_DETERMINISTE_MAX", 0.002)

    with caplog.at_level(logging.WARNING, logger="planif.solveur"):
        resoudre(_instance_lourde(60), CONTEXTES, T0, MAINTENANT, HORIZON_FIN,
                 GRANULARITE)

    assert len(appels) > 1, (
        "budget derisoire, plan vide, et aucune nouvelle tentative : "
        "l'utilisateur se retrouve sans plan alors qu'il suffisait d'insister")
    assert appels == sorted(appels), "le budget doit monter, pas descendre"
    assert any("budget" in e.message.lower() for e in caplog.records), (
        "l'escalade se fait en silence")


def test_un_plan_qui_tient_ne_declenche_aucune_escalade(monkeypatch):
    """L'escalade ne doit pas se declencher sur un plan vide LEGITIME.

    Zero tache a placer donne zero bloc, et c'est une reponse correcte, rendue
    `OPTIMAL`. Reessayer trois fois avec un budget triple serait absurde.
    """
    appels = []
    original = solveur._resoudre_une_fois

    def espion(*a, **kw):
        appels.append(1)
        return original(*a, **kw)

    monkeypatch.setattr(solveur, "_resoudre_une_fois", espion)
    resoudre([], CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)

    assert len(appels) == 1, (
        "un plan vide mais OPTIMAL a relance le solveur pour rien")


def test_le_resume_explique_ce_que_feasible_veut_dire():
    """`FEASIBLE` tout seul ne dit rien a qui lit son plan le matin.

    Le mot est un code CP-SAT ; sa traduction utile, maintenant que le critere
    d'arret est un budget de travail, tient en une phrase : la recherche a
    depense son budget sans prouver qu'elle ne pouvait pas faire mieux. Le plan
    est valide et reproductible — simplement pas demontre optimal.
    """
    from planif.__main__ import formater_resume
    from planif.solveur import Plan

    def _plan(statut):
        return Plan(blocs=(), t0=MAINTENANT, granularite=GRANULARITE,
                    statut=statut, retard_total=0, en_retard=())

    feasible = formater_resume(_plan("FEASIBLE"), [], 1.0, 1.0)
    assert "budget" in feasible.lower(), (
        "le resume affiche FEASIBLE sans dire ce que c'est : {}".format(feasible))

    optimal = formater_resume(_plan("OPTIMAL"), [], 1.0, 1.0)
    assert "budget" not in optimal.lower(), (
        "l'explication ne doit apparaitre que quand elle s'applique")


def test_deux_resolutions_identiques_rendent_le_meme_plan(monkeypatch):
    """La propriete elle-meme — et c'est ce test qui a surpris.

    Ecrit comme un simple garde-fou, suppose vert des l'ecriture, il est sorti
    ROUGE sur le code d'alors :

        index 0 : ('aaaaaaaa-...-0001', 0, 1230, 1234)
               != ('aaaaaaaa-...-0001', 0, 1363, 1367)

    Deux appels a `resoudre`, meme instance, meme processus, a une seconde
    d'intervalle : deux plans differents. Le bug de l'utilisateur reproduit sur
    des donnees construites, sans charger la machine et sans toucher a sa base.

    Le mecanisme est celui-la meme qu'on corrige : l'instance depasse le budget,
    la recherche est donc coupee — et quand la coupe se fait a l'horloge, elle
    ne tombe pas au meme endroit d'un appel a l'autre. On force ici un budget
    volontairement court pour que la coupe ait bien lieu : c'est justement quand
    on coupe que les deux executions doivent malgre tout s'accorder.
    """
    monkeypatch.setattr(solveur, "TEMPS_DETERMINISTE_MAX", 0.3)
    taches = _instance_lourde(12)

    premier = resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    second = resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)

    assert premier.statut == second.statut
    assert _empreinte(premier) == _empreinte(second), (
        "deux resolutions de la meme instance rendent deux plans differents")
