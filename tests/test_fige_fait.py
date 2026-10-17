"""Contrat de test — le bloc 0 d'une tache +fixed est un FAIT, pas une decision.

Deux defauts trouves la nuit 3, sur `planif/solveur.py` :

- **Probleme 3** (`_resoudre_une_fois`, contrainte 8, ~ligne 677) : pose
  `depart(bloc 0) == indice(scheduled)` sur la variable `depart`, dont le
  DOMAINE a deja ete restreint a l'union des fenetres candidates AVANT que la
  contrainte 8 ne soit ecrite (lignes 566-586). Si `scheduled` ne tombe dans
  AUCUNE fenetre candidate du bloc (hors grille, ou journee agregee dont la
  seule fenetre est le creneau ouvert du jour et `scheduled` tombe hors de ce
  creneau), la variable n'a simplement pas cette valeur dans son domaine : la
  contrainte 8 rend alors TOUT le modele infaisable, et la passe 1 entiere
  rend un plan VIDE. Mesure reelle : 16 taches placees -> 0.
- **Probleme 1** (`completer`, passe 2, lot 6) : ne regarde jamais `tache.fige`.
  Une tache non datee figee y est une candidate OPTIONNELLE comme une autre ;
  le second objectif (« au plus tot ») la deplace ou l'arrange bon lui semble,
  et `--appliquer` (`planif/__main__.py::_appliquer`,
  `planif/sortie.py::ecrire_scheduled`) reecrit ensuite son `scheduled` avec ce
  placement invente.

Specification retenue (voir le prompt qui a produit ce fichier) : le bloc 0
d'une tache `+fixed` qui porte un `scheduled` est un intervalle CONSTANT
commencant exactement a `scheduled`, de la taille du bloc 0, dans les DEUX
passes — meme hors grille ou au-dela de la frontiere. Il occupe la ressource,
consomme la capacite du jour, contraint ses successeurs, et ne rend jamais le
plan infaisable. `--appliquer` ne reecrit JAMAIS le `scheduled` (ni les tags)
d'une tache `+fixed`.

Horloge figee : aucun `datetime.now()` dans les tests 1 a 6 (T0/MAINTENANT
constants du fichier). Le test 7 (sous-processus, `--appliquer`) suit le
patron de `tests/test_nuit3_appliquer.py`, qui ancre T0 sur l'horloge reelle +
1 jour — seule exception, deja actee par ce patron existant.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from planif.calendrier import indice_creneau
from planif.modele import Contexte, Creneau, Tache
from planif.selection import selectionner_candidates
from planif.solveur import completer, resoudre

# ==========================================================================
# Horloge et contexte communs aux tests 1-6
# ==========================================================================

T0 = datetime(2026, 10, 5, 0, 0)          # lundi, minuit
MAINTENANT = datetime(2026, 10, 5, 8, 0)  # lundi 08:00
GRANULARITE = timedelta(minutes=30)
HORIZON_FIN = T0 + timedelta(days=35)

_VIDE = ()

# lun-ven 09:00-13:00, marge nulle -> 4 h utiles/jour, bloc minimum 1 h.
CONTEXTE_A = Contexte(
    nom="ctxA", contexte_tw="ctxA",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(9 * 60, 13 * 60),), 1: (Creneau(9 * 60, 13 * 60),),
        2: (Creneau(9 * 60, 13 * 60),), 3: (Creneau(9 * 60, 13 * 60),),
        4: (Creneau(9 * 60, 13 * 60),), 5: _VIDE, 6: _VIDE,
    },
)
CONTEXTES_A = {"ctxA": CONTEXTE_A}


def _resoudre(taches, horizon_detaille_fin=None):
    return resoudre(taches, CONTEXTES_A, T0, MAINTENANT, HORIZON_FIN,
                    GRANULARITE, horizon_detaille_fin=horizon_detaille_fin)


# ==========================================================================
# 1. Passe 1 -- fige HORS GRILLE (probleme 3, sans agregation)
# ==========================================================================

UUID_F1 = "f1f1f1f1-0000-0000-0000-000000000001"
UUID_G1 = "01010101-0000-0000-0000-000000000001"

# Lundi 20:00 : hors de toute plage de "ctxA" (grille 09:00-13:00 uniquement).
SCHEDULED_HORS_GRILLE = T0.replace(hour=20, minute=0)


def _tache_f_hors_grille():
    return Tache(uuid=UUID_F1, description="F - figee hors grille",
                tags=("fixed",), estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=10), contexte="ctxA",
                scheduled=SCHEDULED_HORS_GRILLE)


def _tache_g_independante():
    return Tache(uuid=UUID_G1, description="G - datee independante, tenable",
                estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=3), contexte="ctxA")


def test_passe1_fige_hors_grille_ne_rend_pas_le_plan_vide():
    """Probleme 3, cas hors grille : attendu ROUGE avant correction.

    Aujourd'hui, le domaine de `depart` pour le bloc 0 de F est restreint aux
    fenetres 09:00-13:00 ; `scheduled` (20:00) n'y est pas, donc
    `modele.Add(... == fixe)` rend le modele entier INFEASIBLE et G, pourtant
    tenable et independante, n'est pas placee non plus.
    """
    plan = _resoudre([_tache_f_hors_grille(), _tache_g_independante()])

    assert plan.statut != "INFEASIBLE", (
        "statut={} (plan vide) au lieu de placer F a son scheduled et G "
        "normalement".format(plan.statut))
    assert plan.debut(UUID_F1) == SCHEDULED_HORS_GRILLE, (
        "le bloc 0 de F ne commence pas exactement a scheduled : {}"
        .format(plan.debut(UUID_F1)))
    blocs_g = plan.blocs_de(UUID_G1)
    assert sum(b.longueur for b in blocs_g) == 2, (
        "G (1 h, tenable) devrait etre integralement placee, trouve {} creneaux"
        .format(sum(b.longueur for b in blocs_g)))


# ==========================================================================
# 2. Passe 1 -- fige AU-DELA DE LA FRONTIERE, journee agregee (probleme 3)
# ==========================================================================

UUID_F2 = "f2f2f2f2-0000-0000-0000-000000000002"

# Frontiere a J+1 : le lundi (T0) reste detaille (sa derniere plage, 13:00,
# finit avant la frontiere) ; le mardi (T0+1j) devient agrege (sa plage finit
# apres). scheduled tombe mardi a 20:00 -- hors de la plage 09:00-13:00 de ce
# jour agrege, exactement le meme mecanisme que le test 1 mais cote regime
# agrege : la fenetre agregee d'un jour n'est PAS la journee entiere, c'est
# la plage d'ouverture du jour (planif/solveur.py::_horizons).
HORIZON_DETAILLE_FIN_2 = T0 + timedelta(days=1)
SCHEDULED_AGREGE_HORS_PLAGE = T0 + timedelta(days=1, hours=20)  # mardi 20:00


def _tache_f_agregee_hors_plage():
    # Pas de due : sans limite, la tache est non-datee, donc AGREGEE par
    # construction des que l'agregation est active (planif/solveur.py, le
    # choix du regime). C'est le cas le plus direct pour exercer une fenetre
    # agregee.
    return Tache(uuid=UUID_F2, description="F - figee, jour agrege, hors plage",
                tags=("fixed",), estimated=timedelta(hours=1),
                contexte="ctxA", scheduled=SCHEDULED_AGREGE_HORS_PLAGE)


def test_passe1_fige_au_dela_frontiere_journee_agregee_ne_rend_pas_le_plan_vide():
    """Probleme 3, cas agrege : attendu ROUGE avant correction, meme mecanisme
    que le test 1 mais sur une fenetre de journee agregee."""
    plan = _resoudre([_tache_f_agregee_hors_plage()],
                     horizon_detaille_fin=HORIZON_DETAILLE_FIN_2)

    assert plan.statut != "INFEASIBLE", (
        "statut={} (plan vide) au lieu de placer F a son scheduled".format(plan.statut))
    assert plan.debut(UUID_F2) == SCHEDULED_AGREGE_HORS_PLAGE, (
        "le bloc 0 de F ne commence pas exactement a scheduled : {}"
        .format(plan.debut(UUID_F2)))


# ==========================================================================
# 3. Passe 1 -- precedence : un successeur ne commence pas avant la fin du fige
# ==========================================================================

UUID_F3 = "f3f3f3f3-0000-0000-0000-000000000003"
UUID_S3 = "53535353-0000-0000-0000-000000000003"

# scheduled DANS une fenetre valide (lundi 09:00) : ce test isole la
# precedence du probleme 3 (qui exige un scheduled hors fenetre). Il porte
# donc sur ce que la contrainte 8 fait deja bien aujourd'hui, pas sur le
# defaut lui-meme -- voir le rapport pour ce que ca donne en pratique.
SCHEDULED_VALIDE = T0.replace(hour=9, minute=0)


def _tache_f_valide():
    return Tache(uuid=UUID_F3, description="F - figee, creneau valide",
                tags=("fixed",), estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=10), contexte="ctxA",
                scheduled=SCHEDULED_VALIDE)


def _tache_s_dependante():
    return Tache(uuid=UUID_S3, description="S - depend de F",
                estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=10), contexte="ctxA",
                depends=(UUID_F3,))


def test_passe1_precedence_successeur_apres_la_fin_du_fige():
    plan = _resoudre([_tache_f_valide(), _tache_s_dependante()])

    assert plan.statut != "INFEASIBLE"
    assert plan.debut(UUID_F3) == SCHEDULED_VALIDE
    assert plan.debut(UUID_S3) >= plan.fin(UUID_F3), (
        "S commence avant la fin du bloc fige de F : debut(S)={}, fin(F)={}"
        .format(plan.debut(UUID_S3), plan.fin(UUID_F3)))


# ==========================================================================
# 4. Passe 1 -- ressource : rien ne chevauche le bloc fige
# ==========================================================================

UUID_F4 = "f4f4f4f4-0000-0000-0000-000000000004"
UUID_H4 = "64646464-0000-0000-0000-000000000004"


def _tache_f_valide_4():
    return Tache(uuid=UUID_F4, description="F - figee, creneau valide",
                tags=("fixed",), estimated=timedelta(hours=1),
                contexte="ctxA", scheduled=SCHEDULED_VALIDE)


def _tache_h_meme_contexte():
    # Aucune due : elle a acces a toutes les fenetres de "ctxA", y compris
    # celle qui couvre exactement le bloc fige (lundi 09:00-13:00).
    return Tache(uuid=UUID_H4, description="H - meme contexte que F",
                estimated=timedelta(hours=1), contexte="ctxA")


def test_passe1_ressource_rien_ne_chevauche_le_bloc_fige():
    plan = _resoudre([_tache_f_valide_4(), _tache_h_meme_contexte()])

    assert plan.statut != "INFEASIBLE"
    blocs = [b for b in (list(plan.blocs_de(UUID_F4)) + list(plan.blocs_de(UUID_H4)))
            if not b.externe]
    assert len(blocs) == 2   # 1 h chacune, bloc_min 1 h -> un seul bloc chacune

    blocs.sort(key=lambda b: b.debut)
    assert blocs[0].fin <= blocs[1].debut, (
        "chevauchement entre {} et {}".format(blocs[0], blocs[1]))


# ==========================================================================
# 5. Passe 2 -- fige non datee (probleme 1) + selection de capacite
# ==========================================================================

UUID_N5 = "5e5e5e5e-0000-0000-0000-000000000005"

# Lundi 12:00 : DANS la fenetre valide (09:00-13:00) mais tard dans la
# journee. Le second objectif de `completer` (« au plus tot ») pousserait une
# candidate libre vers 09:00 : si la contrainte 8 manque en passe 2, N glisse
# vers le debut de la journee au lieu de rester a 12:00.
SCHEDULED_TARD_DANS_LA_FENETRE = T0.replace(hour=12, minute=0)


def _tache_n_figee_non_datee():
    return Tache(uuid=UUID_N5, description="N - figee, non datee",
                tags=("fixed",), estimated=timedelta(hours=1),
                contexte="ctxA", scheduled=SCHEDULED_TARD_DANS_LA_FENETRE)


def test_passe2_fige_non_datee_bloc_0_reste_a_scheduled():
    """Probleme 1 : attendu ROUGE avant correction -- `completer` ignore
    `tache.fige` et replace N au plus tot, au lieu de la garder a 12:00."""
    plan1 = _resoudre([])   # passe 1 vide : aucune tache datee dans ce test
    plan2 = completer(plan1, [_tache_n_figee_non_datee()], CONTEXTES_A,
                      T0, MAINTENANT, HORIZON_FIN, GRANULARITE)

    assert plan2.debut(UUID_N5) == SCHEDULED_TARD_DANS_LA_FENETRE, (
        "le bloc 0 de N (figee, non datee) ne commence pas exactement a "
        "scheduled : {}".format(plan2.debut(UUID_N5)))


def test_passe2_selection_ne_doit_jamais_ecarter_une_tache_figee():
    """`selectionner_candidates` ne connait pas `fige` : une capacite nulle
    ecarte donc une tache figee comme n'importe quelle autre. Attendu ROUGE
    avant correction -- on teste directement ce que la fonction EXPOSE
    aujourd'hui, sans passer par `completer`."""
    capacites = {"ctxA": timedelta(0)}
    retenues, ecartees = selectionner_candidates(
        [_tache_n_figee_non_datee()], capacites)

    uuids_ecartees = {t.uuid for t in ecartees}
    assert UUID_N5 not in uuids_ecartees, (
        "N (figee) a ete ecartee par la selection de capacite malgre une "
        "capacite nulle : retenues={}, ecartees={}".format(
            [t.uuid for t in retenues], uuids_ecartees))


# ==========================================================================
# 6. Temoin -- sans +fixed, meme scenario que le test 1 : vert avant et apres
# ==========================================================================

UUID_F6 = "f6f6f6f6-0000-0000-0000-000000000006"
UUID_G6 = "06060606-0000-0000-0000-000000000006"


def _tache_f_libre():
    # Memes donnees que le test 1 (meme scheduled, meme due, meme estimated),
    # SANS le tag +fixed : scheduled n'est alors qu'une indication passee, sans
    # effet sur le modele (design.md : scheduled n'est contraignant qu'avec fige).
    return Tache(uuid=UUID_F6, description="F - libre (temoin, pas fige)",
                estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=10), contexte="ctxA",
                scheduled=SCHEDULED_HORS_GRILLE)


def _tache_g_libre():
    return Tache(uuid=UUID_G6, description="G - datee independante, tenable",
                estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=3), contexte="ctxA")


def test_temoin_sans_fige_placement_libre():
    plan = _resoudre([_tache_f_libre(), _tache_g_libre()])

    assert plan.statut != "INFEASIBLE"
    assert sum(b.longueur for b in plan.blocs_de(UUID_F6)) == 2
    assert sum(b.longueur for b in plan.blocs_de(UUID_G6)) == 2


# ==========================================================================
# M3. Passe 1 -- ressource : le bloc fige doit rester dans AddNoOverlap meme
# quand le solveur aurait interet a le traverser.
#
# Le test 4 existant ne discrimine pas ce defaut : rien n'y force le solveur
# a vouloir chevaucher le bloc fige, donc il l'evite de lui-meme meme si la
# contrainte de ressource etait absente. Ici, la tache O n'a QU'UNE seule
# fenetre tenable dans tout l'horizon (son echeance tombe a la fin du bloc
# fige), et cette fenetre EST le bloc fige de F : le seul placement a retard
# nul pour O consiste a occuper exactement le meme creneau que F. Si le bloc
# fige n'entre plus dans AddNoOverlap (M3), le solveur choisit ce placement
# (retard nul, meilleur pour l'objectif). S'il y entre bien (code correct),
# ce placement est interdit : O deborde apres la fin du bloc fige et prend du
# retard.
# ==========================================================================

UUID_FM3 = "3f3f3f3f-0000-0000-0000-000000000031"
UUID_OM3 = "0d0d0d0d-0000-0000-0000-000000000032"

# meme creneau que SCHEDULED_VALIDE (lundi 09:00), 1 h -> bloc fige 09:00-10:00.
DUE_OM3 = T0.replace(hour=10, minute=0)  # a boucler avant la fin du bloc fige


def _tache_f_valide_m3():
    return Tache(uuid=UUID_FM3, description="F - figee, creneau valide",
                tags=("fixed",), estimated=timedelta(hours=1),
                contexte="ctxA", scheduled=SCHEDULED_VALIDE)


def _tache_o_echeance_serree_m3():
    # Aucune autre fenetre de "ctxA", sur tout l'horizon, ne finit avant
    # 10:00 lundi : la SEULE facon d'eviter le retard est de commencer a
    # 09:00 -- exactement le bloc fige de F.
    return Tache(uuid=UUID_OM3, description="O - echeance a la fin du bloc fige",
                estimated=timedelta(hours=1), contexte="ctxA", due=DUE_OM3)


def test_m3_passe1_bloc_fige_reste_dans_addnooverlap():
    plan = _resoudre([_tache_f_valide_m3(), _tache_o_echeance_serree_m3()])

    assert plan.statut != "INFEASIBLE"
    assert plan.debut(UUID_FM3) == SCHEDULED_VALIDE

    fin_f = plan.fin(UUID_FM3)
    debut_o = plan.debut(UUID_OM3)
    assert debut_o >= fin_f, (
        "O chevauche le bloc fige de F : debut(O)={}, fin(F)={}"
        .format(debut_o, fin_f))
    # Consequence directe de la non-collision : O ne peut plus boucler avant
    # son echeance (09:00-10:00 lui est interdit), donc elle est en retard.
    assert UUID_OM3 in plan.en_retard, (
        "O n'est pas en retard alors que la seule fenetre a temps est prise "
        "par le bloc fige de F : plan.en_retard={}".format(plan.en_retard))


# ==========================================================================
# M4. Passe 1 -- capacite : un bloc fige en regime AGREGE doit rester
# soustrait de la capacite du jour.
#
# Jour agrege (mardi, au-dela de la frontiere) dont la capacite est EXACTEMENT
# la taille du bloc fige de F. Une autre tache agregee (O, meme contexte,
# echeance qui ne tombe a temps QUE le mardi) voudrait ce meme jour. Si
# `_consommer_capacite_figee` ne soustrait rien (M4), la capacite du jour
# parait entiere disponible et O s'y ajoute par-dessus F : la somme des
# creneaux du jour depasse la capacite reelle. Code correct : la capacite est
# deja prise par F, O est repoussee au mercredi (et prend du retard), le jour
# du mardi ne depasse jamais sa capacite.
# ==========================================================================

CONTEXTE_M4 = Contexte(
    nom="ctxM4", contexte_tw="ctxM4",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        # mardi et mercredi (fenetre 09:00-10:00) au-dela de la frontiere ->
        # agreges. Le reste de la semaine ferme : mercredi est la SEULE
        # echappatoire pour O si mardi est plein. Lundi (avant la frontiere)
        # est ferme lui aussi : depuis le 17/10/2026 une tache a limite
        # lointaine peut utiliser la capacite detaillee
        # (tests/test_capacite_avant_frontiere.py), et un lundi ouvert
        # laisserait O s'y placer a temps sans rien dire du mardi.
        0: _VIDE, 1: (Creneau(9 * 60, 10 * 60),),
        2: (Creneau(9 * 60, 10 * 60),), 3: _VIDE, 4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)

FRONTIERE_M4 = T0 + timedelta(days=1)          # mardi 00:00
MARDI_M4 = (T0 + timedelta(days=1)).date()
SCHEDULED_FM4 = T0 + timedelta(days=1, hours=9)  # mardi 09:00 (dans la fenetre)
DUE_OM4 = T0 + timedelta(days=1, hours=10)       # mardi 10:00 -- fin de la fenetre

UUID_FM4 = "4f4f4f4f-0000-0000-0000-000000000041"
UUID_OM4 = "0d0d0d0d-0000-0000-0000-000000000042"


def _tache_f_agregee_m4():
    # Pas de due : non-datee -> agregee des que le regime est actif.
    return Tache(uuid=UUID_FM4, description="F - figee, jour agrege, capacite pile",
                tags=("fixed",), estimated=timedelta(hours=1),
                contexte="ctxM4", scheduled=SCHEDULED_FM4)


def _tache_o_agregee_veut_le_meme_jour_m4():
    return Tache(uuid=UUID_OM4, description="O - agregee, veut le mardi",
                estimated=timedelta(hours=1), contexte="ctxM4", due=DUE_OM4)


def test_m4_passe1_capacite_du_jour_agrege_reste_amputee_du_bloc_fige():
    plan = resoudre(
        [_tache_f_agregee_m4(), _tache_o_agregee_veut_le_meme_jour_m4()],
        {"ctxM4": CONTEXTE_M4}, T0, MAINTENANT, HORIZON_FIN, GRANULARITE,
        horizon_detaille_fin=FRONTIERE_M4)

    assert plan.statut != "INFEASIBLE"
    assert plan.debut(UUID_FM4) == SCHEDULED_FM4

    capacite_mardi_en_creneaux = 2  # 1 h / 30 min
    creneaux_mardi = plan.creneaux_par_jour().get(MARDI_M4, 0)
    assert creneaux_mardi <= capacite_mardi_en_creneaux, (
        "le mardi depasse sa capacite ({} creneaux occupes pour une capacite "
        "de {}) : le bloc fige de F ne semble plus soustrait de la capacite "
        "du jour".format(creneaux_mardi, capacite_mardi_en_creneaux))
    assert UUID_OM4 in plan.en_retard, (
        "O n'est pas en retard : elle a du s'installer sur le mardi malgre "
        "la capacite deja prise par le bloc fige de F, plutot que d'etre "
        "repoussee au mercredi".format())


# ==========================================================================
# M5. Passe 1 -- les blocs suivants d'une tache figee restent bornes par la
# fin du bloc 0 (le FAIT), meme quand une echeance serree les inciterait a
# passer devant.
#
# F, figee, 2 blocs (bloc_min 1 h, estimated 2 h) : bloc 0 fixe a 11:00-12:00,
# dans une fenetre qui offre de la place AVANT (09:00-11:00) et APRES
# (12:00-13:00) scheduled. Avec une echeance a midi, le meilleur retard
# possible EN RESPECTANT la borne place le bloc 1 apres 12:00 (retard forcé
# d'1 h) ; sans la borne (M5), le solveur prefererait glisser le bloc 1 AVANT
# le bloc 0 (09:00 ou 10:00) pour boucler a temps (retard nul) -- exactement
# ce que la contrainte de precedence intra-tache doit interdire.
#
# Attendu VERT sur le code actuel : bloc 1 commence bien apres la fin du
# bloc 0.
# ==========================================================================

UUID_FM5 = "5f5f5f5f-0000-0000-0000-000000000051"

SCHEDULED_FM5 = T0.replace(hour=11, minute=0)   # bloc 0 : 11:00-12:00
DUE_FM5 = T0.replace(hour=12, minute=0)         # echeance a la fin du bloc 0


def _tache_f_figee_2blocs_m5():
    return Tache(uuid=UUID_FM5, description="F - figee, 2 blocs, place avant et apres",
                tags=("fixed",), estimated=timedelta(hours=2),
                contexte="ctxA", scheduled=SCHEDULED_FM5, due=DUE_FM5)


def test_m5_passe1_bloc_suivant_borne_par_la_fin_du_bloc_fige():
    plan = _resoudre([_tache_f_figee_2blocs_m5()])

    assert plan.statut != "INFEASIBLE"
    blocs = sorted(plan.blocs_de(UUID_FM5), key=lambda b: b.indice)
    assert len(blocs) == 2, "attendu 2 blocs pour F, trouve {}".format(len(blocs))

    bloc0, bloc1 = blocs[0], blocs[1]
    assert bloc0.debut == indice_creneau(T0, SCHEDULED_FM5, GRANULARITE)
    assert bloc1.debut >= bloc0.fin, (
        "le bloc 1 de F commence avant la fin du bloc 0 (le FAIT) : "
        "bloc0={}, bloc1={}".format(bloc0, bloc1))


# ==========================================================================
# 7. --appliquer ne reecrit jamais le scheduled (ni les tags) d'une figee
# ==========================================================================

RACINE = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

U_FIGE7 = "70707070-0000-4000-8000-000000000001"
U_NORMALE7 = "70707070-0000-4000-8000-000000000002"

T0_7 = (datetime.now() + timedelta(days=1)).replace(
    hour=0, minute=0, second=0, microsecond=0)
SCHEDULED_FIGE_X = T0_7 + timedelta(days=2, hours=9)      # X : la date reelle
SCHEDULED_FIGE_AILLEURS = T0_7 + timedelta(days=5, hours=14)  # ou le plan la met
SCHEDULED_NORMALE_Z = T0_7 + timedelta(days=1, hours=10)


def _tw(instant):
    return instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _bloc7(debut, fin):
    return {"indice": 0, "debut": debut.isoformat(), "fin": fin.isoformat(),
            "externe": False, "agrege": False, "opportuniste": False,
            "precision": "heure"}


def _plan_json_7():
    return {
        "version": 1, "statut": "OPTIMAL", "retard_total": 0, "en_retard": [],
        "t0": T0_7.isoformat(), "granularite_minutes": 30,
        "taches": {
            # le plan replace la figee AILLEURS que sa vraie date X.
            U_FIGE7: {
                "blocs": [_bloc7(SCHEDULED_FIGE_AILLEURS,
                                SCHEDULED_FIGE_AILLEURS + timedelta(hours=1))],
                "debut": SCHEDULED_FIGE_AILLEURS.isoformat(),
                "fin": (SCHEDULED_FIGE_AILLEURS + timedelta(hours=1)).isoformat(),
                "due": None,
            },
            U_NORMALE7: {
                "blocs": [_bloc7(SCHEDULED_NORMALE_Z,
                                 SCHEDULED_NORMALE_Z + timedelta(hours=1))],
                "debut": SCHEDULED_NORMALE_Z.isoformat(),
                "fin": (SCHEDULED_NORMALE_Z + timedelta(hours=1)).isoformat(),
                "due": None,
            },
        },
    }


def _semer_7(base_jetable):
    commun = {"status": "pending", "entry": "20260901T080000Z",
              "estTime": "PT1H", "project": "NPD.figefait"}
    base_jetable.semer([
        dict(commun, uuid=U_FIGE7, description="Figee, vraie date X",
             tags=["pro", "fixed"], scheduled=_tw(SCHEDULED_FIGE_X)),
        dict(commun, uuid=U_NORMALE7, description="Normale, pas figee",
             tags=["pro"]),
    ])


def _lancer_appliquer(base_jetable, chemin):
    env = dict(base_jetable.env)
    env["PYTHONPATH"] = str(RACINE)
    return subprocess.run(
        [PYTHON, "-m", "planif", "--appliquer", str(chemin)],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(chemin.parent), check=False)


def _export_7(base_jetable):
    return {t["uuid"]: t for t in json.loads(base_jetable.task("export").stdout)}


# ==========================================================================
# 8. Passe 1 -- tache figee multi-blocs sans capacite pour la suite (trou de
#    contrat : les blocs 1..n restent aujourd'hui OBLIGATOIRES)
# ==========================================================================

UUID_F8 = "f8f8f8f8-0000-0000-0000-000000000008"
UUID_G8 = "08080808-0000-0000-0000-000000000008"

# bloc_min 2 h : 6 h d'estimated -> 3 blocs de 2 h (indices 0, 1, 2).
CONTEXTE_B = Contexte(
    nom="ctxB", contexte_tw="ctxB",
    bloc_min=timedelta(hours=2), marge_jour=timedelta(0),
    grille={
        # Une SEULE fenetre, le lundi, exactement la taille du bloc 0 : rien
        # ne reste pour les blocs 1 et 2 ce jour-la, et aucun autre jour de la
        # semaine n'ouvre.
        0: (Creneau(9 * 60, 11 * 60),), 1: _VIDE, 2: _VIDE, 3: _VIDE,
        4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)
# Horizon coupe AVANT le lundi suivant : la grille de ctxB est hebdomadaire
# (planif/modele.py::Contexte.creneaux, cle = weekday()), donc sans cette
# coupure le lundi d'apres offrirait une fenetre fraiche aux blocs 1 et 2, et
# le scenario ("aucune capacite pour la suite jusqu'a la fin de l'horizon")
# ne serait plus celui teste.
HORIZON_FIN_8 = T0 + timedelta(days=6)

SCHEDULED_F8 = T0.replace(hour=9, minute=0)


def _tache_f8_figee_multi_blocs_sans_suite():
    return Tache(uuid=UUID_F8,
                description="F - figee, 3 blocs, aucune place pour 1 et 2",
                tags=("fixed",), estimated=timedelta(hours=6), contexte="ctxB",
                scheduled=SCHEDULED_F8)


def _tache_g8_independante():
    return Tache(uuid=UUID_G8, description="G - datee independante, tenable",
                estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=3), contexte="ctxA")


def test_passe1_fige_multi_blocs_sans_capacite_pour_la_suite():
    """Trou de contrat : aujourd'hui, les blocs 1 et 2 du bloc 0 fige passent
    par le meme mecanisme qu'un bloc ordinaire (`_resoudre_une_fois`, ~ligne
    674) -- aucune fenetre retenue leur pose `modele.Add(depart > horizon)`,
    un domaine vide, ce qui rend TOUT le modele INFEASIBLE. Attendu ROUGE
    avant correction : la specification (docstring de ce fichier) dit qu'une
    tache +fixed ne rend JAMAIS le plan infaisable -- meme quand sa suite ne
    tient nulle part."""
    plan = resoudre(
        [_tache_f8_figee_multi_blocs_sans_suite(), _tache_g8_independante()],
        {"ctxA": CONTEXTE_A, "ctxB": CONTEXTE_B}, T0, MAINTENANT, HORIZON_FIN_8,
        GRANULARITE)

    assert plan.statut != "INFEASIBLE", (
        "statut={} : la tache figee F rend le plan entier infaisable a "
        "cause de ses blocs 1 et 2, qui ne tiennent nulle part -- G, "
        "pourtant independante et tenable, n'est alors pas placee non plus"
        .format(plan.statut))
    assert plan.debut(UUID_F8) == SCHEDULED_F8, (
        "le bloc 0 de F (le FAIT) ne commence pas exactement a scheduled : {}"
        .format(plan.debut(UUID_F8)))
    blocs_g = plan.blocs_de(UUID_G8)
    assert sum(b.longueur for b in blocs_g) == 2, (
        "G (1 h, tenable, independante de F) devrait etre integralement "
        "placee, trouve {} creneaux".format(sum(b.longueur for b in blocs_g)))


# ==========================================================================
# 9. Passe 2 -- fige NON DATEE multi-blocs sans place pour la suite : le
#    remplissage opportuniste d'une candidate ordinaire ne doit pas s'effondrer
# ==========================================================================

UUID_N9 = "9e9e9e9e-0000-0000-0000-000000000009"
UUID_C9 = "09090909-0000-0000-0000-000000000009"

SCHEDULED_N9 = T0.replace(hour=9, minute=0)


def _tache_n9_figee_non_datee_multi_blocs():
    return Tache(uuid=UUID_N9,
                description="N - figee, non datee, 3 blocs, aucune place pour 1 et 2",
                tags=("fixed",), estimated=timedelta(hours=6), contexte="ctxB",
                scheduled=SCHEDULED_N9)


def _tache_c9_opportuniste_ordinaire():
    return Tache(uuid=UUID_C9,
                description="C - candidate opportuniste ordinaire, tenable",
                estimated=timedelta(hours=1), contexte="ctxA")


def test_passe2_fige_multi_blocs_ne_doit_pas_effondrer_le_remplissage_opportuniste():
    """Trou de contrat, cote passe 2 : `completer` force `presence == 1` pour
    toute tache figee (~ligne 981), puis, si les blocs 1 et 2 ne tiennent
    nulle part, ajoute aussi `presence == 0` (~ligne 1017) -- une
    contradiction qui rend le MODELE ENTIER de la passe 2 infaisable. Le
    code de secours (`_replan`) sauve alors le FAIT (bloc 0 de N), mais C,
    une candidate ordinaire pourtant tenable, n'est jamais soumise a un
    solveur qui n'a jamais tourne avec succes : le remplissage opportuniste
    entier s'effondre a cause d'UNE tache figee. Attendu ROUGE avant
    correction."""
    contextes = {"ctxA": CONTEXTE_A, "ctxB": CONTEXTE_B}
    horizon_fin_9 = T0 + timedelta(days=6)
    plan1 = resoudre([], contextes, T0, MAINTENANT, horizon_fin_9, GRANULARITE)
    plan2 = completer(
        plan1,
        [_tache_n9_figee_non_datee_multi_blocs(), _tache_c9_opportuniste_ordinaire()],
        contextes, T0, MAINTENANT, horizon_fin_9, GRANULARITE)

    assert plan2.debut(UUID_N9) == SCHEDULED_N9, (
        "le bloc 0 de N (figee, non datee) ne commence pas exactement a "
        "scheduled : {}".format(plan2.debut(UUID_N9)))
    blocs_c = plan2.blocs_de(UUID_C9)
    assert sum(b.longueur for b in blocs_c) == 2, (
        "C (candidate ordinaire, 1 h, tenable) devrait etre placee -- le "
        "remplissage opportuniste ne doit pas s'effondrer a cause d'une "
        "seule tache figee dont la suite ne tient nulle part, trouve {} "
        "creneaux".format(sum(b.longueur for b in blocs_c)))


# ==========================================================================
# F1. Passe 1 -- la seule fenetre existante pour le bloc 1 d'une figee est
#    disputee : occupee en entier par le bloc 0 d'une AUTRE tache figee.
#
# Contrairement au test 8 (aucune fenetre du tout), il y a bien ici une
# fenetre CANDIDATE pour le bloc 1 de F (la meme journee, apres son bloc 0) --
# mais elle est integralement prise par le bloc 0 fige d'une autre tache H.
# Code correct (bloc suivant optionnel, contrainte 8 de nuit 3) : F garde son
# FAIT (bloc 0), son bloc 1 reste absent faute de place reelle, H occupe sa
# fenetre, et l'independante G (autre contexte) est normalement placee.
#
# Mutation testee (passe 1, suite redevenue obligatoire) : forcer
# `presence_bloc == 1` juste apres sa creation (~ligne 689) revient a l'ancien
# defaut ou la suite d'une figee est une contrainte, jamais une option. Le
# bloc 1 de F doit alors occuper la fenetre disputee, en chevauchement avec
# le bloc fige de H -> modele entier INFEASIBLE.
# ==========================================================================

UUID_F1B = "f1f1f1f1-0000-0000-0000-000000000101"
UUID_H1B = "h1h1h1h1-0000-0000-0000-000000000102"
UUID_G1B = "01010101-0000-0000-0000-000000000103"

# Fenetre unique du lundi de ctxC : exactement 2 h, la taille du bloc 0 (1 h)
# de F plus celle du bloc 1 (1 h). Semaine fermee sinon, horizon coupe avant
# le lundi suivant -- comme ctxB du test 8, aucune autre place n'existe.
CONTEXTE_C = Contexte(
    nom="ctxC", contexte_tw="ctxC",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(9 * 60, 11 * 60),), 1: _VIDE, 2: _VIDE, 3: _VIDE,
        4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)
HORIZON_FIN_F1 = T0 + timedelta(days=6)

SCHEDULED_F1B = T0.replace(hour=9, minute=0)   # bloc 0 de F : 09:00-10:00
SCHEDULED_H1B = T0.replace(hour=10, minute=0)  # bloc 0 (unique) de H : 10:00-11:00


def _tache_f1b_figee_2blocs():
    return Tache(uuid=UUID_F1B, description="F - figee, 2 blocs, suite disputee",
                tags=("fixed",), estimated=timedelta(hours=2), contexte="ctxC",
                scheduled=SCHEDULED_F1B)


def _tache_h1b_figee_occupe_la_suite():
    return Tache(uuid=UUID_H1B, description="H - figee, occupe la seule fenetre de F",
                tags=("fixed",), estimated=timedelta(hours=1), contexte="ctxC",
                scheduled=SCHEDULED_H1B)


def _tache_g1b_independante():
    return Tache(uuid=UUID_G1B, description="G - datee independante, tenable",
                estimated=timedelta(hours=1),
                due=MAINTENANT + timedelta(days=3), contexte="ctxA")


def test_f1_passe1_suite_optionnelle_quand_l_unique_fenetre_est_disputee():
    plan = resoudre(
        [_tache_f1b_figee_2blocs(), _tache_h1b_figee_occupe_la_suite(),
         _tache_g1b_independante()],
        {"ctxA": CONTEXTE_A, "ctxC": CONTEXTE_C}, T0, MAINTENANT, HORIZON_FIN_F1,
        GRANULARITE)

    assert plan.statut != "INFEASIBLE", (
        "statut={} : la suite (bloc 1) de F devrait rester optionnelle et "
        "absente, pas rendre tout le modele infaisable".format(plan.statut))
    assert plan.debut(UUID_F1B) == SCHEDULED_F1B, (
        "le bloc 0 de F (le FAIT) ne commence pas exactement a scheduled : {}"
        .format(plan.debut(UUID_F1B)))
    assert plan.debut(UUID_H1B) == SCHEDULED_H1B, (
        "le bloc 0 de H (le FAIT) ne commence pas exactement a scheduled : {}"
        .format(plan.debut(UUID_H1B)))
    blocs_f = [b for b in plan.blocs_de(UUID_F1B) if not b.externe]
    assert len(blocs_f) == 1, (
        "le bloc 1 de F devrait rester absent (sa seule fenetre est prise "
        "par H), trouve {} blocs".format(len(blocs_f)))
    blocs_g = plan.blocs_de(UUID_G1B)
    assert sum(b.longueur for b in blocs_g) == 2, (
        "G (1 h, tenable, independante) devrait etre integralement placee, "
        "trouve {} creneaux".format(sum(b.longueur for b in blocs_g)))


# ==========================================================================
# F2. Passe 2 -- meme idee que F1, mais pour une figee NON DATEE (`completer`)
#    dont la suite n'a qu'une fenetre, prise par le FAIT d'une autre figee
#    deja posee en passe 1.
#
# Code correct : le bloc 0 de N (le FAIT) reste a son scheduled, son bloc 1
# reste absent (fenetre disputee par M, figee de la passe 1), et la
# candidate ordinaire C (autre contexte) est normalement placee.
#
# Mutation testee (passe 2, presence des blocs suivants liee au bloc 0) :
# remplacer le litteral de presence PAR BLOC (`presence_bloc`) de la suite de
# N par le `presence` du bloc 0 (deja force a 1 pour toute figee, ~ligne
# 1095) revient a rendre la suite obligatoire, alors que sa seule fenetre est
# prise par M -> modele de la passe 2 infaisable, repli sur `_replan`, et le
# remplissage opportuniste (donc C) ne tourne plus jamais.
# ==========================================================================

UUID_M2B = "m2b2m2b2-0000-0000-0000-000000000201"
UUID_N2B = "9e9e9e9e-0000-0000-0000-000000000202"
UUID_C2B = "09090909-0000-0000-0000-000000000203"

HORIZON_FIN_F2 = T0 + timedelta(days=6)

SCHEDULED_M2B = T0.replace(hour=10, minute=0)  # bloc 0 (unique) de M : 10:00-11:00
SCHEDULED_N2B = T0.replace(hour=9, minute=0)   # bloc 0 de N : 09:00-10:00


def _tache_m2b_figee_fait_de_passe1():
    return Tache(uuid=UUID_M2B, description="M - figee, deja posee en passe 1",
                tags=("fixed",), estimated=timedelta(hours=1), contexte="ctxC",
                scheduled=SCHEDULED_M2B)


def _tache_n2b_figee_non_datee_2blocs():
    return Tache(uuid=UUID_N2B, description="N - figee, non datee, 2 blocs, suite disputee",
                tags=("fixed",), estimated=timedelta(hours=2), contexte="ctxC",
                scheduled=SCHEDULED_N2B)


def _tache_c2b_candidate_ordinaire():
    return Tache(uuid=UUID_C2B, description="C - candidate ordinaire, tenable",
                estimated=timedelta(hours=1), contexte="ctxA")


def test_f2_passe2_suite_optionnelle_quand_l_unique_fenetre_est_disputee():
    contextes = {"ctxA": CONTEXTE_A, "ctxC": CONTEXTE_C}
    plan1 = resoudre([_tache_m2b_figee_fait_de_passe1()], contextes, T0, MAINTENANT,
                     HORIZON_FIN_F2, GRANULARITE)
    assert plan1.statut != "INFEASIBLE"
    assert plan1.debut(UUID_M2B) == SCHEDULED_M2B

    plan2 = completer(
        plan1, [_tache_n2b_figee_non_datee_2blocs(), _tache_c2b_candidate_ordinaire()],
        contextes, T0, MAINTENANT, HORIZON_FIN_F2, GRANULARITE)

    assert plan2.debut(UUID_N2B) == SCHEDULED_N2B, (
        "le bloc 0 de N (le FAIT) ne commence pas exactement a scheduled : {}"
        .format(plan2.debut(UUID_N2B)))
    blocs_n = [b for b in plan2.blocs_de(UUID_N2B) if not b.externe]
    assert len(blocs_n) == 1, (
        "le bloc 1 de N devrait rester absent (sa seule fenetre est prise "
        "par le FAIT de M), trouve {} blocs".format(len(blocs_n)))
    blocs_c = plan2.blocs_de(UUID_C2B)
    assert sum(b.longueur for b in blocs_c) == 2, (
        "C (candidate ordinaire, 1 h, tenable) devrait etre placee -- le "
        "remplissage opportuniste ne doit pas s'effondrer a cause d'une "
        "suite figee disputee, trouve {} creneaux"
        .format(sum(b.longueur for b in blocs_c)))


# ==========================================================================
# F3. Passe 1 -- la suite d'une figee doit etre placee des qu'il y a de la
#    place, MEME quand ce placement est en retard, et MEME quand la LAISSER
#    absente ferait baisser le retard TOTAL (PENALITE_ABSENCE_FIGE).
#
# Le retard du bloc 1 lui-meme est IDENTIQUE qu'il soit present ou absent (sa
# position "absente" est fixee au meme creneau le plus tot que sa position
# "presente", ~ligne 726) : un scenario ou seul le retard de F varie ne
# distingue donc rien (verifie empiriquement -- un tel scenario reste VERT
# sous la mutation). Ce qui distingue reellement le poids de la penalite,
# c'est la RESSOURCE : le bloc 1 de F et une tache ordinaire X due au meme
# instant se disputent le MEME creneau, unique dans leurs deux grilles.
#
# F, figee, 2 blocs, contexte ctxD (lundi 10:00-11:00, SEULE fenetre de toute
# la semaine) : bloc 0 fixe 09:00-10:00, bloc 1 ne peut aller QUE sur ce
# creneau. X, ordinaire, contexte ctxX (meme creneau lundi 10:00-11:00, PLUS
# un repli mardi 10:00-11:00), due lundi 11:00 -- pile la fin du creneau
# dispute. La ressource est UNIQUE (contrainte 4) : quel que soit le
# contexte, les deux ne peuvent pas occuper le meme instant.
#
# Code correct : le bloc 1 de F est place sur le creneau dispute (retard de F
# inchangee, cf. plus haut), X est repousse au mardi et prend du retard.
# Mutation testee (PENALITE_ABSENCE_FIGE = 0) : plus rien ne pousse a placer
# le bloc 1 de F, alors que le laisser absent LIBERE le creneau pour X et fait
# strictement baisser le retard TOTAL (celui de F ne change pas, celui de X
# tombe a zero) -- le seul objectif restant (minimiser le retard) prefere donc
# l'absence : bloc 1 de F disparait, X reste sur son creneau au lundi, a
# l'heure.
# ==========================================================================

CONTEXTE_D = Contexte(
    nom="ctxD", contexte_tw="ctxD",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        # Fenetre 09:00-11:00 : exactement bloc 0 (09:00-10:00) + bloc 1
        # (10:00-11:00), pour que le bloc 0 reste DANS la grille -- sinon
        # `_consommer_capacite_figee` impute son volume a la capacite du jour
        # sans que ses creneaux appartiennent a la fenetre, et epuise a tort
        # la capacite qui resterait pour le bloc 1 (defaut distinct de F1/F2,
        # hors perimetre de ce test).
        0: (Creneau(9 * 60, 11 * 60),), 1: _VIDE, 2: _VIDE, 3: _VIDE,
        4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)
CONTEXTE_X_F3 = Contexte(
    nom="ctxX", contexte_tw="ctxX",
    bloc_min=timedelta(hours=1), marge_jour=timedelta(0),
    grille={
        0: (Creneau(10 * 60, 11 * 60),), 1: (Creneau(10 * 60, 11 * 60),),
        2: _VIDE, 3: _VIDE, 4: _VIDE, 5: _VIDE, 6: _VIDE,
    },
)
HORIZON_FIN_F3 = T0 + timedelta(days=3)  # coupe juste apres mardi

UUID_F3B = "f3b3f3b3-0000-0000-0000-000000000301"
UUID_X_F3 = "x3f3x3f3-0000-0000-0000-000000000302"

SCHEDULED_F3B = T0.replace(hour=9, minute=0)     # bloc 0 : lundi 09:00-10:00
DUE_F3B = T0.replace(hour=10, minute=0)          # due juste apres le bloc 0
DUE_X_F3 = T0.replace(hour=11, minute=0)         # due X : lundi 11:00
MARDI_10H_F3 = T0.replace(hour=10, minute=0) + timedelta(days=1)  # repli de X


def _tache_f3b_figee_2blocs_creneau_dispute():
    return Tache(uuid=UUID_F3B, description="F - figee, 2 blocs, bloc 1 dispute avec X",
                tags=("fixed",), estimated=timedelta(hours=2), contexte="ctxD",
                scheduled=SCHEDULED_F3B, due=DUE_F3B)


def _tache_x_f3_ordinaire_meme_creneau():
    return Tache(uuid=UUID_X_F3, description="X - ordinaire, veut le meme creneau que F",
                estimated=timedelta(hours=1), contexte="ctxX", due=DUE_X_F3)


def test_f3_passe1_bloc_suivant_place_meme_si_son_absence_reduirait_le_retard_total():
    plan = resoudre(
        [_tache_f3b_figee_2blocs_creneau_dispute(), _tache_x_f3_ordinaire_meme_creneau()],
        {"ctxD": CONTEXTE_D, "ctxX": CONTEXTE_X_F3}, T0, MAINTENANT, HORIZON_FIN_F3,
        GRANULARITE)

    assert plan.statut != "INFEASIBLE"
    assert plan.debut(UUID_F3B) == SCHEDULED_F3B
    blocs_f = [b for b in plan.blocs_de(UUID_F3B) if not b.externe]
    assert len(blocs_f) == 2, (
        "le bloc 1 de F devrait etre place sur le creneau dispute meme si "
        "son absence ferait baisser le retard total (en liberant ce creneau "
        "pour X) : trouve {} blocs".format(len(blocs_f)))
    assert plan.debut(UUID_X_F3) == MARDI_10H_F3, (
        "X devrait etre repousse au mardi, le lundi etant pris par le bloc 1 "
        "de F : debut(X)={}".format(plan.debut(UUID_X_F3)))
    assert UUID_X_F3 in plan.en_retard, (
        "X devrait etre en retard (repoussee au mardi alors que sa due est "
        "lundi 11:00) : plan.en_retard={}".format(plan.en_retard))


def test_appliquer_ne_reecrit_jamais_le_scheduled_d_une_figee(base_jetable, tmp_path):
    """Probleme 1, cote ecriture : attendu ROUGE avant correction.

    `ecrire_scheduled` (planif/sortie.py) ne regarde ni les tags ni `fige` :
    elle ecrit le debut du premier bloc du plan pour TOUTE tache non externe,
    y compris une figee que le plan replace ailleurs. Le controle (la tache
    normale) doit lui etre modifiee -- pour prouver que le test ne passe pas
    par accident faute d'ecriture du tout.
    """
    _semer_7(base_jetable)
    chemin = tmp_path / "plan.json"
    chemin.write_text(json.dumps(_plan_json_7()), encoding="utf-8")

    res = _lancer_appliquer(base_jetable, chemin)
    assert res.returncode == 0, res.stdout + res.stderr

    apres = _export_7(base_jetable)

    assert apres[U_FIGE7]["scheduled"] == _tw(SCHEDULED_FIGE_X), (
        "le scheduled de la tache figee a ete reecrit : attendu {}, trouve {}"
        .format(_tw(SCHEDULED_FIGE_X), apres[U_FIGE7].get("scheduled")))
    assert set(apres[U_FIGE7].get("tags") or []) == {"pro", "fixed"}, (
        "les tags de la tache figee ont change : {}".format(apres[U_FIGE7].get("tags")))

    # temoin : la tache normale, elle, EST bien modifiee par --appliquer.
    assert apres[U_NORMALE7]["scheduled"] == _tw(SCHEDULED_NORMALE_Z), (
        "la tache normale n'a pas ete ecrite : le test ne prouve rien si "
        "--appliquer n'ecrit rien du tout")
