"""Modele de contraintes — design.md §5, passe 1 (« le mur »).

Ce module ne reimplemente ni solveur ni propagation : CP-SAT fait ce travail.
Il se contente de traduire le cahier des charges en contraintes.

Ce qui est ecrit ici couvre les lots 4 et 5 :

- lot 4 : intervalles, fenetres, bloc minimum, `AddNoOverlap` sur la ressource
  unique, precedences, echeances, objectif lexicographique ;
- lot 5 : les taches `+external`. C'est une seule ligne de difference et c'est
  tout le projet : leur intervalle est **absent** de `AddNoOverlap` et **absent**
  de la contrainte de capacite quotidienne. Elles prennent du temps sans prendre
  de capacite (proposal.md decision 10).

## Les deux horizons (design.md §1, proposal.md risque n° 1)

    « Horizon detaille H_d = 2 semaines par defaut, parametrable. C'est la
    fenetre ou l'on produit des heures. Horizon de faisabilite H_f >= H_d,
    couvrant la plus lointaine echeance de projet. Au-dela de H_d, la capacite
    est agregee par jour au lieu d'etre posee au creneau. »

Concretement, `resoudre` prend `horizon_detaille_fin` :

- **`None` (defaut)** : pas d'agregation, tout est pose au creneau. C'est le
  comportement d'origine, bit pour bit.
- **une date** : la frontiere. Avant elle, regime DETAILLE — un litteral par
  fenetre de grille, intervalle dans `AddNoOverlap`, heure exacte. Apres elle,
  regime AGREGE — un litteral par *journee*, aucune entree dans `AddNoOverlap`,
  et l'on ne garantit plus que le **volume du jour**.

Une tache est **detaillee** si elle porte une limite qui tombe dans l'horizon
detaille ; sinon elle est **agregee**. C'est la transcription de la parade
annoncee par `proposal.md` : « ne modeliser finement que ce qui porte une
echeance ». Une tache sans limite n'a aucune pression de date : elle n'a pas
besoin de l'heure exacte en passe 1.

**Ce que l'agregation lache, et il faut le savoir en lisant un plan :** au-dela
de la frontiere, deux blocs d'une meme journee peuvent se chevaucher dans la
sortie. Ce ne sont plus des placements horaires, ce sont des affectations a une
journee. Le volume quotidien, lui, reste garanti — l'agregation relache les
heures, jamais la capacite.

**Ce qu'elle garde :** les deux regimes vivent dans des plages de temps
disjointes (un bloc agrege ne peut jamais commencer avant la frontiere), donc un
bloc agrege ne peut pas venir se superposer a un bloc detaille. La ressource
unique reste vraie la ou on la mesure.

## Conventions

- toutes les positions et durees sont des **entiers en nombre de creneaux**
  (design.md §1). Jamais de flottant d'heures dans le modele.
- `t0`, `maintenant`, `horizon_fin` et les `due` sont **naifs, en heure locale**
  (design.md §2). La conversion depuis l'UTC de Taskwarrior se fait a la
  frontiere, dans `planif/taskwarrior.py`, et nulle part ailleurs.
- l'instant courant est **injecte**. Ce module n'appelle jamais `datetime.now()` :
  c'est ce qui rend les tests deterministes.

Deux choix de formulation, parmi ceux que `design.md` laisse ouverts. La consigne
est de prendre la plus lisible et de dire pourquoi :

1. **Les tailles de blocs sont des constantes, pas des variables.** `design.md` §5
   pose une contrainte de conservation `Σ size = estimated` sur des `size`
   variables, mais il fixe lui-meme les tailles juste au-dessus (« chacun de duree
   `bloc_min` sauf le dernier (le reste) »). Les tailles etant determinees par la
   regle, la conservation est vraie par construction et la contrainte devient
   redondante. On garde la forme constante : un test verifie quand meme la
   conservation, pour que la propriete reste assenee et pas seulement supposee.
2. **« Chaque intervalle est inclus dans un creneau disponible » est pose par un
   litteral par fenetre candidate, avec `AddExactlyOne`.** C'est plus verbeux
   qu'un encodage par domaines interdits, mais c'est directement lisible — et ce
   sont les memes litteraux qui servent a la contrainte de capacite quotidienne,
   ce qui evite d'avoir deux representations du meme fait. Le regime agrege
   reutilise exactement le meme mecanisme, avec la journee entiere pour fenetre.
"""
import logging
import math
from dataclasses import dataclass
from datetime import timedelta

from ortools.sat.python import cp_model

from planif.calendrier import disponibilite, indice_creneau, instant_creneau
from planif.tampon import limites_effectives

__all__ = ["Bloc", "Plan", "resoudre", "completer", "decouper_en_blocs"]

# Ce module ne configure PAS le journal : c'est a l'appelant (la ligne de
# commande) de decider ou vont les messages. Il se contente de les emettre.
_LOG = logging.getLogger(__name__)

# Budget laisse au solveur, en unites de TRAVAIL et non en secondes d'horloge.
#
# C'est une correction, et elle merite ses chiffres. Le critere d'arret etait
# `max_time_in_seconds = 60`, et il rendait le plan dependant de la charge de la
# machine : memes donnees, meme code, 26 s / OPTIMAL sur une execution et
# 94 s / FEASIBLE sur la suivante. L'instrumentation des deux `Solve` sur les
# donnees reelles (278 taches, 54 datees) a montre ou etait la bascule :
#
#     temps DETERMINISTE : 5,460 puis 12,978  -- identique a la milliseconde
#     branches explorees : 136 568 / 277 628  -- identique
#     temps MUR          : 21,82 s / 20,17 s  -- lui, non
#
# La recherche est donc parfaitement deterministe ; seul son critere d'arret ne
# l'etait pas. `num_search_workers = 1` et `random_seed = 0` figent le CHEMIN,
# pas le moment ou l'on cesse de le parcourir — la promesse de reproductibilite
# ecrite en face d'eux etait fausse tant que l'horloge decidait de la fin.
#
# Et ce que l'arret premature coutait n'est pas ce qu'on croit :
#
#     budget mur | statut   | objectif | empreinte du plan
#        300 s   | OPTIMAL  |   1949   | -4562147786156008567
#         60 s   | OPTIMAL  |   1949   | -4562147786156008567
#         20 s   | FEASIBLE |   1949   |  5071140208841883476
#         12 s   | FEASIBLE |   1949   |  5071140208841883476
#
# L'objectif ne bouge pas : le plan rendu plus tot est aussi BON. Il est
# seulement AUTRE — l'optimum n'est pas unique. Le degat n'etait pas un plan
# degrade, c'etait un plan qui se deplace sans raison d'une execution a l'autre.
#
# La VALEUR, elle, vient d'un second balayage, sur deux instances reelles. On y
# lit l'empreinte du plan en fonction du budget -- autrement dit : a partir de
# quand le plan cesse-t-il de changer ?
#
#     budget |   instance facile (09:00)   |    instance dure (17:00)
#            |  mur  | blocs |  empreinte  |  mur  | blocs |  empreinte
#        2   |  7,3s |  21   |  8dc276e2   |  8,5s |   0   |   VIDE
#        3   |  9,5s |  21   |  8dc276e2   | 11,6s |   0   |   VIDE
#        5   | 15,1s |  21   |  8dc276e2   | 17,4s |  21   |  a1b6830c
#       13   | 26,4s |  21   |  8dc276e2   | 41,2s |  21   |  a1b6830c
#       30   | 26,0s |  21   |  8dc276e2   | 75,7s |  21   |  a1b6830c
#
# Sur ces deux instances, le plan est FIGE des 2 unites (facile) ou 5 (dure), et
# ne bouge plus jusqu'a 30 -- a objectif rigoureusement egal, donc sans rien
# perdre. Ces 25 unites de plus coutent **58 secondes** sur l'instance dure et
# n'achetent meme pas la preuve : la borne descend de 3456 a 3254 sans jamais
# rejoindre l'objectif 2578.
#
# **Mais ca ne se generalise pas, et c'est mesure.** Sur le banc synthetique de
# 100 taches datees de `tests/test_perf_horizon.py` -- deux fois la charge datee
# reelle -- l'objectif continue de progresser au-dela de 13 :
#
#     budget | mur    | objectif « au plus tard » | empreinte
#        5   |  29 s  |        154 936            | 6ae0ca8e
#       13   |  64 s  |        154 936            | 6ae0ca8e
#       30   | 122 s  |        155 032            | d8b21563
#
# Le budget 5 y rend donc un optimum STRICTEMENT inferieur. De 0,062 %, soit
# 96 creneaux cumules sur 100 taches -- une demi-heure par tache placee plus tot
# que necessaire. Et aucune echeance n'est manquee dans aucun des trois cas : la
# premiere resolution rend un retard NUL aux trois budgets. Ce qui se degrade
# est la marge, pas le respect des dates.
#
# A noter, parce que ca change la lecture : la borne reste a 158 524 aux trois
# budgets. AUCUN d'eux ne prouve son optimum. Le plan a 30 n'est pas « la bonne
# reponse » face a une degradation, c'est un point un peu meilleur sur une
# asymptote, non prouve lui aussi.
#
# Reste que la falaise, elle, est brutale : sous 2 (facile) ou 5 (dure), ce
# n'est pas un plan moins bon, c'est **zero bloc**. Et elle se DEPLACE avec la
# difficulte de l'instance. Aucune valeur fixe n'est a la fois rapide et sure :
# d'ou une valeur de depart basse, et l'escalade juste dessous.
#
# Le choix assume : 5 par defaut. Sur les donnees reelles de l'utilisateur
# (54 taches datees, 13 placees) il est prouve sans perte ; sur le banc a
# 100 taches il coute 0,06 % de marge pour 4x moins d'attente. Si la base grossit
# jusqu'a ressembler au banc, c'est cette valeur qu'il faudra remonter.
TEMPS_DETERMINISTE_MAX = 5.0

#: De combien on remonte le budget quand le plan ressort VIDE, et seulement dans
#: ce cas : jamais pour ameliorer un plan, qui ne s'ameliore plus (voir le
#: tableau ci-dessus). 5, puis 15, puis 45 unites. Le cas courant paie la
#: premiere ligne ; le cas degrade paie la somme, ce qui reste infiniment
#: preferable au plan vide qu'il rendait avant.
FACTEURS_ESCALADE = (1, 3, 9)

#: Filet de securite, en secondes d'horloge. **Ce n'est pas le critere d'arret**
#: — c'est la garantie qu'une instance pathologique finit par rendre la main.
#: Il est place tres au-dessus de ce que le budget de travail peut consommer
#: (22 s d'horloge mesurees pour 13 unites, machine au repos), de sorte qu'il ne
#: morde jamais en usage normal. Et s'il mord quand meme, `_signaler_arret_horloge`
#: le dit : a cet instant precis, et a cet instant seulement, le plan rendu cesse
#: d'etre reproductible.
#: Mise a l'echelle de l'urgence dans le second objectif de la passe 2. CP-SAT
#: ne manipule que des entiers ; le plancher garantit qu'une tache d'urgence
#: nulle est quand meme tiree vers le tot.
ECHELLE_URGENCE = 100
POIDS_PLANCHER = 100

#: Poids d'un bloc de la SUITE d'une tache figee reste ABSENT (probleme
#: contrats 8 et 9, tests/test_fige_fait.py) : les blocs suivants du bloc 0
#: (le FAIT) sont OPTIONNELS, mais leur absence doit peser bien plus lourd
#: que n'importe quel autre terme du meme objectif -- y compris le retard de
#: la tache elle-meme (voir M5 : le bloc suivant doit rester place meme quand
#: ca degrade legerement le retard mesure sur cette tache). 10**7 creneaux
#: domine trivialement toute somme de retards ou d'urgences realiste (des
#: annees d'horizon, a 30 minutes pres).
PENALITE_ABSENCE_FIGE = 10 ** 7

SECONDES_MAX = 300.0


def _solveur(budget=None):
    """Le solveur, configure identiquement pour les deux passes.

    Trois reglages, un seul but : que deux executions de la meme instance
    rendent le meme plan. La graine et le worker unique figent le chemin de
    recherche ; le budget deterministe fige le point d'arret. Il faut les trois,
    et c'est le troisieme qui manquait.
    """
    s = cp_model.CpSolver()
    s.parameters.max_deterministic_time = (
        TEMPS_DETERMINISTE_MAX if budget is None else budget)
    s.parameters.max_time_in_seconds = SECONDES_MAX
    s.parameters.num_search_workers = 1
    s.parameters.random_seed = 0
    return s


def _signaler_arret_horloge(s, etat, etape):
    """Dit tout haut quand c'est l'HORLOGE qui a arrete la recherche.

    Le mode de panne caracteristique de ce projet est de perdre du contenu en
    silence. Qu'un plan soit arrete par le filet est tolerable ; qu'il soit
    presente comme un plan normal ne l'est pas, parce qu'une autre execution en
    rendrait un autre.
    """
    if etat in (cp_model.OPTIMAL, cp_model.INFEASIBLE):
        return
    if s.ResponseProto().deterministic_time >= (
            s.parameters.max_deterministic_time * 0.99):
        return   # arret sur le budget de travail : reproductible, donc normal
    _LOG.warning(
        "%s : recherche arretee par le filet d'horloge (%.0f s) avant son "
        "budget de travail -- CE PLAN N'EST PAS REPRODUCTIBLE, une machine "
        "moins chargee en rendrait un autre", etape, SECONDES_MAX)


def _sans_solution(s, etat, etape, t0, granularite):
    """Le Plan vide a rendre quand une resolution n'a rien trouve -- et le mot juste.

    Ces deux verdicts n'appellent pas du tout la meme reaction, et on les
    confondait en rendant `INFEASIBLE` dans les deux cas :

    - `INFEASIBLE` : les contraintes se contredisent, aucun plan n'existe. On
      cherche la tache coupable, on lance `planif/diagnostic.py`.
    - `UNKNOWN` : le budget s'est epuise avant qu'on ait trouve quoi que ce
      soit. Il n'y a rien a diagnostiquer, il faut du budget.

    Annoncer le premier quand c'est le second envoie l'utilisateur chercher un
    probleme qui n'existe pas. Constate en balayant le budget sur les donnees
    reelles : sous 2 unites, la passe 1 rendait un plan VIDE etiquete
    INFEASIBLE, et sans un mot -- l'arret etant bien tombe sur le budget de
    travail, `_signaler_arret_horloge` se taisait a juste titre.
    """
    if etat == cp_model.INFEASIBLE:
        _LOG.warning("%s : modele INFAISABLE, les contraintes se contredisent. "
                     "Le diagnostic (planif/diagnostic.py) nomme les "
                     "responsables.", etape)
    else:
        _LOG.warning(
            "%s : budget de calcul epuise sans AUCUNE solution (%s). Le plan "
            "ressort VIDE. Ce n'est pas une infaisabilite : il n'y a rien a "
            "diagnostiquer, il faut augmenter le budget.",
            etape, s.StatusName(etat))
    return Plan(blocs=(), t0=t0, granularite=granularite,
                statut=s.StatusName(etat), retard_total=0, en_retard=())


@dataclass(frozen=True)
class Bloc:
    """Un intervalle place. Positions en indices de creneaux absolus depuis t0."""

    uuid: str
    indice: int      # numero du bloc dans la tache, 0-based
    debut: int       # inclus
    fin: int         # exclu
    externe: bool
    # True si place en regime agrege : on repond a la journee, pas a l'heure.
    agrege: bool = False
    # True si place par la passe 2 (regime opportuniste, lot 6). La passe 1
    # ne pose jamais ce drapeau ; il est ici pour que le contrat de sortie
    # (lot 7) soit fige des maintenant et que les deux regimes soient
    # distinguables dans le JSON sans avoir a les deduire.
    opportuniste: bool = False

    @property
    def longueur(self):
        return self.fin - self.debut


@dataclass(frozen=True)
class Plan:
    """Le resultat d'une resolution."""

    blocs: tuple
    t0: object
    granularite: timedelta
    statut: str          # 'OPTIMAL', 'FEASIBLE' ou 'INFEASIBLE'
    retard_total: int    # somme des retards, en creneaux
    en_retard: tuple     # uuids dont la limite n'est pas tenue

    def blocs_de(self, uuid):
        return tuple(b for b in self.blocs if b.uuid == uuid)

    def instants(self, uuid):
        """Les (debut, fin) de chaque bloc de la tache, en datetime."""
        return tuple(
            (instant_creneau(self.t0, b.debut, self.granularite),
             instant_creneau(self.t0, b.fin, self.granularite))
            for b in self.blocs_de(uuid)
        )

    def debut(self, uuid):
        blocs = self.blocs_de(uuid)
        if not blocs:
            return None
        return instant_creneau(self.t0, min(b.debut for b in blocs), self.granularite)

    def fin(self, uuid):
        blocs = self.blocs_de(uuid)
        if not blocs:
            return None
        return instant_creneau(self.t0, max(b.fin for b in blocs), self.granularite)

    def creneaux_par_jour(self, uuid=None):
        """date -> nombre de creneaux occupes ce jour-la par des blocs NON externes.

        Les blocs `+external` sont exclus **par definition** : ils ne consomment
        aucune capacite. C'est exactement ce que le controle du lot 5 mesure.

        On compte le **volume** de chaque bloc, pas l'union des instants
        occupes : en regime agrege deux blocs d'une meme journee peuvent se
        chevaucher, et c'est bien leur somme qui doit tenir dans la capacite.
        """
        par_jour = {}
        for b in self.blocs:
            if b.externe:
                continue
            if uuid is not None and b.uuid != uuid:
                continue
            for indice in range(b.debut, b.fin):
                jour = instant_creneau(self.t0, indice, self.granularite).date()
                par_jour[jour] = par_jour.get(jour, 0) + 1
        return par_jour


def _en_creneaux(duree, granularite):
    """Arrondi au creneau superieur : on ne raccourcit jamais une tache."""
    return max(1, math.ceil(duree / granularite))


def _construire_bloc_fige(modele, nom, fixe, t_bloc, frontiere, agregation):
    """Le bloc 0 d'une tache `+fixed` avec `scheduled` est un FAIT, pas une
    decision (tests/test_fige_fait.py) : un intervalle CONSTANT, commencant
    exactement a `fixe`, HORS du domaine des fenetres candidates.

    C'est la correction du probleme 3 : l'ancienne contrainte 8 posait
    `modele.Add(depart == fixe)` sur une variable dont le DOMAINE avait deja
    ete restreint a l'union des fenetres candidates (lignes plus haut). Si
    `fixe` n'y figurait pas -- hors grille, ou au-dela de la frontiere d'un
    jour agrege -- cette egalite rendait tout le modele INFEASIBLE. Ici, le
    domaine de `depart`/`arrivee` est un singleton DES LA CONSTRUCTION : il n'a
    jamais ete restreint a autre chose, et il n'y a pas de contrainte d'egalite
    a poser en plus.

    Rend `(depart, arrivee, fin, agrege)`. `agrege` dit si le fait tombe
    au-dela de la frontiere du regime agrege, pour l'exclure de `AddNoOverlap`
    exactement comme n'importe quel autre bloc agrege (design.md §1) : deux
    blocs d'une meme journee agregee peuvent legitimement s'y chevaucher.
    """
    fin = fixe + t_bloc
    depart = modele.NewIntVar(fixe, fixe, "d_" + nom)
    arrivee = modele.NewIntVar(fin, fin, "f_" + nom)
    modele.Add(arrivee == depart + t_bloc)
    agrege = agregation and fixe >= frontiere
    return depart, arrivee, fin, agrege


def _consommer_capacite_figee(charge_figee, t0, granularite, contexte_nom,
                              fixe, fin, cache_contexte):
    """Impute le volume d'un bloc fige a la capacite de son/ses jour(s).

    Jamais une contrainte : `charge_figee` est seulement soustrait de la
    capacite restante offerte aux blocs encore DECIDES par le solveur
    (`max(0, capacite - sa taille)`), ce qui ne peut jamais rendre le modele
    infaisable -- au pire, il ne reste plus de capacite pour les autres.
    """
    for indice in range(fixe, fin):
        jour = instant_creneau(t0, indice, granularite).date()
        if jour in cache_contexte:
            cle = (contexte_nom, jour)
            charge_figee[cle] = charge_figee.get(cle, 0) + 1


def decouper_en_blocs(taille_totale, bloc_min, insecable=False):
    """design.md §5, variables.

    Un seul bloc si la tache est `+nosplit` ou si elle tient dans le bloc
    minimum. Sinon `k = ceil(estimated / bloc_min)` blocs : les `k-1` premiers de
    duree `bloc_min`, le dernier du reste.
    """
    if insecable or taille_totale <= bloc_min:
        return [taille_totale]
    k = math.ceil(taille_totale / bloc_min)
    return [bloc_min] * (k - 1) + [taille_totale - bloc_min * (k - 1)]


def _horizons(contexte, t0, horizon_fin, granularite, reunions, frontiere):
    """Partage l'horizon d'un contexte en deux regimes (design.md §1).

    Rend `(fenetres, journees, capacites)` :

    - `fenetres` : liste de `(jour, Plage)` pour les jours **detailles**, c'est-a-dire
      ceux dont toutes les plages finissent avant `frontiere`. C'est la qu'on place
      a l'heure.
    - `journees` : liste de `(jour, debut, fin)` pour les jours **agreges**. La
      journee y est un seul seau : on n'y garantit que le volume.
    - `capacites` : `jour -> capacite en creneaux`, commune aux deux regimes.

    **Un jour n'est jamais coupe en deux** : il est detaille si TOUTES ses plages
    finissent avant la frontiere, agrege sinon. C'est la formulation la plus
    lisible — elle evite d'avoir a raisonner sur une journee a cheval — et elle
    est conservatrice : la journee a cheval perd sa partie d'avant-frontiere
    plutot que de risquer un double placement.
    """
    fenetres, journees, capacites = [], [], {}
    jour = t0.date()
    dernier = horizon_fin.date()
    while jour <= dernier:
        disp = disponibilite(contexte, jour, t0, granularite, reunions)
        if disp.plages:
            capacites[jour] = disp.capacite
            if disp.plages[-1].fin <= frontiere:
                for plage in disp.plages:
                    fenetres.append((jour, plage))
            else:
                journees.append((jour, disp.plages[0].debut, disp.plages[-1].fin))
        jour += timedelta(days=1)
    return fenetres, journees, capacites


def resoudre(taches, contextes, t0, maintenant, horizon_fin, granularite,
             reunions=(), limites=None, horizon_detaille_fin=None):
    """Passe 1 : le budget est essaye, puis augmente TANT QUE le plan est vide.

    Voir `_resoudre_une_fois` pour le modele lui-meme. Ici, une seule question :
    combien de travail donner au solveur.

    Le balayage du budget sur les donnees reelles a rendu deux verdicts
    contradictoires — empreinte du plan en fonction du budget :

        instance facile (09:00) : plan final des  2 unites, VIDE en dessous
        instance dure   (17:00) : plan final des  5 unites, VIDE en dessous

    « Plan final » au sens fort : l'empreinte ne bouge plus d'un iota jusqu'a
    30 unites, alors que ces 25 unites supplementaires coutent **58 secondes**
    sur l'instance dure — et n'achetent meme pas la preuve d'optimalite, la
    borne descendant de 3456 a 3254 sans jamais rejoindre l'objectif 2578.

    Mais sous la falaise, ce n'est pas un plan degrade : c'est **zero bloc**. Et
    la falaise se deplace avec la difficulte de l'instance. Aucune valeur fixe
    n'est donc a la fois rapide et sure : trop haute, on paie une minute pour
    rien ; trop basse, on n'a plus de plan du tout.

    D'ou l'escalade. On ne remonte le budget que sur le seul symptome qui
    compte, le plan vide — jamais sur la qualite, qui ne s'ameliore plus. Chaque
    tentative etant deterministe, le resultat final l'est aussi.

    Un plan vide mais `OPTIMAL` (aucune tache a placer) est une reponse juste et
    ne declenche rien.
    """
    budget = TEMPS_DETERMINISTE_MAX
    for rang in range(len(FACTEURS_ESCALADE)):
        budget = TEMPS_DETERMINISTE_MAX * FACTEURS_ESCALADE[rang]
        plan = _resoudre_une_fois(taches, contextes, t0, maintenant, horizon_fin,
                                  granularite, reunions=reunions, limites=limites,
                                  horizon_detaille_fin=horizon_detaille_fin,
                                  budget=budget)
        if plan.statut in ("OPTIMAL", "FEASIBLE", "INFEASIBLE"):
            return plan
        if rang + 1 < len(FACTEURS_ESCALADE):
            _LOG.warning(
                "passe 1 : aucune solution avec un budget de %.3g ; nouvelle "
                "tentative a %.3g.", budget,
                TEMPS_DETERMINISTE_MAX * FACTEURS_ESCALADE[rang + 1])
    _LOG.warning(
        "passe 1 : toujours aucune solution apres un budget de %.3g. Le plan "
        "ressort VIDE.", budget)
    return plan


def _resoudre_une_fois(taches, contextes, t0, maintenant, horizon_fin, granularite,
                       reunions=(), limites=None, horizon_detaille_fin=None,
                       budget=None):
    """Passe 1 du design.md §5 : les taches datees, placees au plus tard en securite.

    `limites` : dict uuid -> datetime de fin au plus tard. Si None, il est calcule
    par `planif.tampon.limites_effectives` — c'est-a-dire tampon applique une seule
    fois sur les `due` reelles, puis herite le long du graphe sans re-tamponner.

    `horizon_detaille_fin` : la frontiere entre le regime detaille et le regime
    agrege (design.md §1). `None` desactive l'agregation et pose tout au creneau.

    L'echeance est une contrainte **souple** : une echeance intenable produit du
    retard et l'uuid remonte dans `Plan.en_retard`, mais elle n'empeche pas les
    autres taches d'etre planifiees. C'est une exigence explicite du lot 4.
    """
    horizon = indice_creneau(t0, horizon_fin, granularite)
    tot = indice_creneau(t0, maintenant, granularite)  # rien ne commence avant

    # La frontiere des deux regimes. Sans agregation, elle est au bout de
    # l'horizon : aucune journee n'est agregee, et le modele est celui d'avant.
    agregation = horizon_detaille_fin is not None
    frontiere = (min(horizon, indice_creneau(t0, horizon_detaille_fin, granularite))
                 if agregation else horizon)

    if limites is None:
        # Passe 1 sans tampon : sa sortie est une LIMITE (« apres, c'est trop
        # tard »), pas une intention. Le coussin, si on en veut un, se pose sur
        # le placement de la passe 2, pas sur la date qu'on annonce.
        limites = limites_effectives(taches, contextes, tampon=timedelta(0))

    par_uuid = {t.uuid: t for t in taches}
    modele = cp_model.CpModel()

    # fenetres, journees agregees et capacites, une fois par contexte
    cache = {}
    for nom, ctx in contextes.items():
        cache[nom] = _horizons(ctx, t0, horizon_fin, granularite, reunions, frontiere)

    intervalles_ressource = []   # ce qui entre dans AddNoOverlap
    # (contexte, jour) -> liste de (taille, litteral) pour la capacite quotidienne
    charge_du_jour = {}
    # (contexte, jour) -> creneaux deja consommes par un bloc fige (un FAIT,
    # jamais une contrainte -- voir _consommer_capacite_figee).
    charge_figee = {}
    blocs_modele = {}            # uuid -> liste de (indice, start, end, taille)
    debuts = {}
    fins = {}
    termes_objectif = []   # « au plus tard » : voir la note a la fin
    # (uuid, indice) -> litteral de presence d'un bloc de la SUITE d'une tache
    # figee (indice >= 1). Absent de ce dict == bloc toujours present (bloc 0,
    # le FAIT, ou bloc ordinaire d'une tache non figee) -- voir plus bas.
    presences_fige_bloc = {}

    for tache in taches:
        if tache.estimated is None:
            continue  # signale par les pre-verifications, pas devine ici
        taille = _en_creneaux(tache.estimated, granularite)

        if tache.externe:
            # ---- LOT 5, le coeur du projet ----------------------------------
            # Un seul intervalle, de duree `estimated` lue comme un DELAI
            # calendaire. Il n'est contraint ni par la grille, ni par la
            # capacite du jour, et il n'entre PAS dans AddNoOverlap : le tiers
            # travaille pendant que l'utilisateur fait autre chose.
            # Les deux horizons ne le concernent pas : ne consommant aucune
            # capacite, il n'y a rien a agreger. Il reste donc exact meme loin.
            depart = modele.NewIntVar(tot, max(tot, horizon - taille), "d_" + tache.uuid)
            arrivee = modele.NewIntVar(tot, horizon, "f_" + tache.uuid)
            modele.Add(arrivee == depart + taille)
            debuts[tache.uuid] = depart
            fins[tache.uuid] = arrivee
            blocs_modele[tache.uuid] = [(0, depart, arrivee, taille)]
            termes_objectif.append(depart)
            continue

        ctx = contextes.get(tache.contexte)
        if ctx is None:
            continue  # sortie du modele, listee par les pre-verifications
        fenetres, journees, capacites = cache[tache.contexte]
        bloc_min = _en_creneaux(ctx.bloc_min, granularite)

        # --- le choix du regime, en UN seul endroit ------------------------
        # Detaillee si elle porte une limite qui tombe dans l'horizon detaille.
        # Sans agregation, tout est detaille et le modele est celui d'avant.
        limite = (limites or {}).get(tache.uuid)
        detaillee = (not agregation) or (
            limite is not None
            and indice_creneau(t0, limite, granularite) <= frontiere)

        tailles = decouper_en_blocs(taille, bloc_min, insecable=tache.insecable)
        blocs_modele[tache.uuid] = []
        starts_tache, ends_tache = [], []

        # Le bloc 0 d'une tache `+fixed` avec `scheduled` est un FAIT (contrainte
        # 8, tests/test_fige_fait.py) : `fin_fige` borne les blocs SUIVANTS de
        # la meme tache -- ils ne commencent jamais avant que le fait ne soit
        # termine.
        fige0 = tache.fige and tache.scheduled is not None
        fin_fige = None
        if fige0:
            fixe0 = indice_creneau(t0, tache.scheduled, granularite)

        candidates_detaillees = [
            (jour, plage.debut, plage.fin, False) for jour, plage in fenetres]
        candidates_agregees = [(jour, debut, fin, True) for jour, debut, fin in journees]
        if detaillee:
            # Regime DETAILLE, avec une SOUPAPE : en plus de ses fenetres
            # detaillees (ou le bloc tient tout entier dans une plage de la
            # grille et entre dans la ressource unique), un bloc peut aussi
            # tomber sur une journee AGREGEE au-dela de la frontiere, exactement
            # comme un bloc d'une tache agregee. C'est ce qui rend l'echeance
            # souple meme quand la capacite avant frontiere ne suffit pas
            # (design.md §1) : sans cette soupape, `retenues` restait vide pour
            # un bloc et le modele entier devenait INFEASIBLE (voir la note en
            # tete de fichier de tests/test_echeance_souple_frontiere.py).
            # L'objectif continue de preferer le regime detaille : minimiser le
            # retard (premiere passe de l'objectif, plus bas) exclut d'office
            # les debordements agreges qui depasseraient la limite quand la
            # capacite detaillee suffit deja.
            candidates = candidates_detaillees + candidates_agregees
        else:
            # Regime AGREGE : la journee entiere sert de fenetre, et le bloc
            # n'entre PAS dans AddNoOverlap. `frontiere` dans la borne basse
            # garantit qu'un bloc agrege ne vient jamais se superposer a un
            # bloc detaille : les deux regimes restent dans des plages de temps
            # disjointes.
            candidates = candidates_agregees

        for indice, t_bloc in enumerate(tailles):
            nom = "{}#{}".format(tache.uuid[:8], indice)

            if indice == 0 and fige0:
                # Le FAIT, pas une decision : voir _construire_bloc_fige.
                depart, arrivee, fin_fige, agrege_fige = _construire_bloc_fige(
                    modele, nom, fixe0, t_bloc, frontiere, agregation)
                if not agrege_fige:
                    intervalles_ressource.append(
                        modele.NewIntervalVar(depart, t_bloc, arrivee, "i_" + nom))
                _consommer_capacite_figee(
                    charge_figee, t0, granularite, tache.contexte, fixe0,
                    fin_fige, cache[tache.contexte][2])
                blocs_modele[tache.uuid].append((indice, depart, arrivee, t_bloc))
                starts_tache.append(depart)
                ends_tache.append(arrivee)
                continue

            # On calcule les fenetres retenues AVANT de creer les variables,
            # pour donner a `depart` un domaine reduit a l'union exacte des
            # positions possibles, au lieu de tout l'horizon.
            #
            # Ce n'est PAS un affaiblissement du modele : l'ensemble des
            # solutions est rigoureusement le meme, puisque `AddExactlyOne`
            # sur les memes litteraux imposait deja cette union. On donne
            # seulement l'information au solveur des la construction, au lieu
            # de la lui faire redecouvrir par propagation. Sans ca, chaque bloc
            # part avec un domaine de plusieurs milliers de valeurs dont
            # l'immense majorite est interdite (nuits, week-ends, pauses).
            retenues = []
            for jour, borne_brute, borne_haute, cand_agrege in candidates:
                borne_basse = max(borne_brute, tot)
                if fin_fige is not None:
                    # Les blocs suivants d'une tache figee ne commencent
                    # jamais avant que le FAIT (bloc 0) ne soit termine.
                    borne_basse = max(borne_basse, fin_fige)
                if cand_agrege:
                    borne_basse = max(borne_basse, frontiere)
                if borne_haute - borne_basse < t_bloc:
                    continue
                retenues.append((jour, borne_basse, borne_haute, cand_agrege))

            if fin_fige is not None:
                # --- la SUITE d'une tache figee (indice >= 1) : chaque bloc
                # est OPTIONNEL, jamais une contrainte qui pourrait rendre le
                # modele infaisable (probleme des contrats 8/9,
                # tests/test_fige_fait.py). Le bloc 0 (le FAIT) est deja pose
                # plus haut, hors de ce chemin.
                if not retenues:
                    # Aucune fenetre candidate d'ici l'horizon : le bloc est
                    # simplement absent, jamais `depart > horizon`.
                    _LOG.warning(
                        "tache %s (figee) : le bloc %d de sa suite n'a aucune "
                        "fenetre candidate d'ici l'horizon, il reste absent "
                        "du plan (le FAIT, bloc 0, est preserve)",
                        tache.uuid, indice)
                    continue

                domaine = cp_model.Domain.FromIntervals(
                    [[bas, haut - t_bloc] for _, bas, haut, _ in retenues])
                depart = modele.NewIntVarFromDomain(domaine, "d_" + nom)
                arrivee = modele.NewIntVarFromDomain(
                    cp_model.Domain.FromIntervals(
                        [[bas + t_bloc, haut] for _, bas, haut, _ in retenues]),
                    "f_" + nom)
                modele.Add(arrivee == depart + t_bloc)

                presence_bloc = modele.NewBoolVar("pf_" + nom)
                presences_fige_bloc[(tache.uuid, indice)] = presence_bloc

                litteraux = []
                litteraux_detailles = []
                for jour, borne_basse, borne_haute, cand_agrege in retenues:
                    lit = modele.NewBoolVar(
                        "w_{}_{}_{}".format(nom, jour, borne_basse))
                    modele.Add(depart >= borne_basse).OnlyEnforceIf(lit)
                    modele.Add(depart + t_bloc <= borne_haute).OnlyEnforceIf(lit)
                    litteraux.append(lit)
                    if not cand_agrege:
                        litteraux_detailles.append(lit)
                    charge_du_jour.setdefault(
                        (tache.contexte, jour), []).append((t_bloc, lit))
                # Exactement une fenetre SI le bloc est retenu, aucune sinon --
                # le meme patron que les candidates opportunistes de `completer`.
                modele.AddExactlyOne(litteraux).OnlyEnforceIf(presence_bloc)
                for lit in litteraux:
                    modele.AddImplication(lit, presence_bloc)

                if litteraux_detailles:
                    if len(litteraux_detailles) == len(litteraux):
                        intervalles_ressource.append(
                            modele.NewOptionalIntervalVar(
                                depart, t_bloc, arrivee, presence_bloc, "i_" + nom))
                    else:
                        en_detaille = modele.NewBoolVar("edet_" + nom)
                        modele.Add(en_detaille == sum(litteraux_detailles))
                        intervalles_ressource.append(
                            modele.NewOptionalIntervalVar(
                                depart, t_bloc, arrivee, en_detaille, "i_" + nom))

                # Si absent, on fixe `depart` au minimum de son domaine plutot
                # que de le laisser libre : sans ca, une valeur arbitraire du
                # domaine gonflerait `d_t`/`f_t` (debut/fin de la TACHE, plus
                # bas) sans correspondre a un placement reel.
                borne_min_domaine = min(bas for _, bas, _, _ in retenues)
                modele.Add(depart == borne_min_domaine).OnlyEnforceIf(
                    presence_bloc.Not())

                blocs_modele[tache.uuid].append((indice, depart, arrivee, t_bloc))
                starts_tache.append(depart)
                ends_tache.append(arrivee)
                # PAS dans `termes_objectif` : la suite d'une tache figee ne
                # doit pas etre repoussee « au plus tard » comme un bloc
                # ordinaire -- au contraire, elle doit etre placee des que
                # possible (voir PENALITE_ABSENCE_FIGE, plus bas).
                continue

            if retenues:
                domaine = cp_model.Domain.FromIntervals(
                    [[bas, haut - t_bloc] for _, bas, haut, _ in retenues])
                depart = modele.NewIntVarFromDomain(domaine, "d_" + nom)
                arrivee = modele.NewIntVarFromDomain(
                    cp_model.Domain.FromIntervals(
                        [[bas + t_bloc, haut] for _, bas, haut, _ in retenues]),
                    "f_" + nom)
            else:
                depart = modele.NewIntVar(tot, max(tot, horizon - t_bloc), "d_" + nom)
                arrivee = modele.NewIntVar(tot, horizon, "f_" + nom)
            modele.Add(arrivee == depart + t_bloc)

            litteraux = []
            litteraux_detailles = []
            for jour, borne_basse, borne_haute, cand_agrege in retenues:
                lit = modele.NewBoolVar("w_{}_{}_{}".format(nom, jour, borne_basse))
                modele.Add(depart >= borne_basse).OnlyEnforceIf(lit)
                modele.Add(depart + t_bloc <= borne_haute).OnlyEnforceIf(lit)
                litteraux.append(lit)
                if not cand_agrege:
                    litteraux_detailles.append(lit)
                charge_du_jour.setdefault(
                    (tache.contexte, jour), []).append((t_bloc, lit))

            if not litteraux:
                # Aucune fenetre ne peut accueillir ce bloc : le modele est
                # infaisable, et c'est le bon verdict. Les pre-verifications du
                # lot 3 sont la pour l'annoncer avant d'en arriver la.
                modele.Add(depart > horizon)   # domaine vide : INFEASIBLE
            else:
                modele.AddExactlyOne(litteraux)

            # L'intervalle n'entre dans la ressource unique QUE quand le bloc
            # est effectivement place en regime detaille. Quand toutes les
            # fenetres retenues sont detaillees (cas d'origine, sans soupape),
            # l'intervalle est inconditionnel. Des qu'une soupape agregee est
            # possible en plus, il devient OPTIONNEL, conditionne au litteral
            # « en detaille » -- sinon un bloc reellement place en agrege
            # entrerait quand meme dans AddNoOverlap et pourrait se voir
            # interdire de chevaucher un autre bloc agrege de la meme journee,
            # ce que le regime agrege autorise explicitement (design.md §1).
            if litteraux_detailles:
                if len(litteraux_detailles) == len(litteraux):
                    intervalles_ressource.append(
                        modele.NewIntervalVar(depart, t_bloc, arrivee, "i_" + nom))
                else:
                    en_detaille = modele.NewBoolVar("edet_" + nom)
                    modele.Add(en_detaille == sum(litteraux_detailles))
                    intervalles_ressource.append(
                        modele.NewOptionalIntervalVar(
                            depart, t_bloc, arrivee, en_detaille, "i_" + nom))

            # « au plus tard en securite » : chaque debut entre dans
            # l'objectif. Une variante a ete essayee et ABANDONNEE — n'optimiser
            # que le JOUR choisi pour les blocs agreges, la position dans la
            # journee n'ayant aucun sens metier la-bas. Elle est defendable et
            # elle n'a rien change au temps de resolution (60,8 s dans les deux
            # cas) : on garde donc la formulation la plus simple, et la question
            # est posee a l'utilisateur dans RAPPORT-NUIT-2.md.
            termes_objectif.append(depart)

            blocs_modele[tache.uuid].append((indice, depart, arrivee, t_bloc))
            starts_tache.append(depart)
            ends_tache.append(arrivee)

        # Debut et fin de la TACHE : min des debuts, max des fins. On ne force
        # pas d'ordre entre les blocs d'une meme tache — ce serait une
        # restriction gratuite, et le reste du modele n'en a pas besoin.
        d_t = modele.NewIntVar(tot, horizon, "dt_" + tache.uuid)
        f_t = modele.NewIntVar(tot, horizon, "ft_" + tache.uuid)
        modele.AddMinEquality(d_t, starts_tache)
        modele.AddMaxEquality(f_t, ends_tache)
        debuts[tache.uuid] = d_t
        fins[tache.uuid] = f_t

    # --- reunions : intervalles fixes dans la ressource unique ---------------
    for numero, reunion in enumerate(reunions):
        r_debut = indice_creneau(t0, reunion.debut, granularite)
        r_fin = indice_creneau(t0, reunion.fin, granularite)
        if r_fin > r_debut:
            intervalles_ressource.append(
                modele.NewIntervalVar(r_debut, r_fin - r_debut, r_fin,
                                      "reunion_{}".format(numero)))

    # --- contrainte 4 : ressource unique -------------------------------------
    # Tout ce qui est la-dedans est du temps de l'utilisateur. Les taches
    # `+external` en sont absentes : c'est toute la difference (decision 10).
    # Les blocs agreges en sont absents aussi, mais pour une autre raison : ils
    # sont au-dela de la frontiere, ou l'on ne repond plus a l'heure.
    if intervalles_ressource:
        modele.AddNoOverlap(intervalles_ressource)

    # --- marge quotidienne (decision 11), posee en volume --------------------
    # C'est la contrainte qui tient AUSSI en regime agrege : on relache les
    # heures, jamais la capacite. Un bloc fige (contrainte 8) n'y ajoute aucun
    # litteral : il REDUIT la capacite offerte aux blocs encore decides,
    # jamais en dessous de zero -- ce qui ne peut jamais rendre le modele
    # infaisable, contrairement a l'ancienne egalite sur variable restreinte.
    for (nom_ctx, jour), charges in charge_du_jour.items():
        capacite = cache[nom_ctx][2].get(jour)
        if capacite is None:
            continue
        reste = max(0, capacite - charge_figee.get((nom_ctx, jour), 0))
        modele.Add(sum(taille * lit for taille, lit in charges) <= reste)

    # --- contrainte 6 : precedences -----------------------------------------
    for tache in taches:
        if tache.uuid not in debuts:
            continue
        for predecesseur in tache.depends:
            if predecesseur in fins:
                modele.Add(debuts[tache.uuid] >= fins[predecesseur])

    # --- contrainte 7 : echeances, en SOUPLE --------------------------------
    retards = []
    ordre_retard = []
    for uuid, limite in (limites or {}).items():
        if uuid not in fins or limite is None:
            continue
        borne = indice_creneau(t0, limite, granularite)
        # Le plafond est `horizon - borne`, et non `horizon`. Quand la limite
        # est ANTERIEURE a t0 -- une echeance deja depassee -- `borne` est
        # negative, et le retard reellement necessaire vaut `fin + |borne|`.
        # Avec un plafond a `horizon`, le domaine ne peut pas porter cette
        # valeur des que la tache est en retard de plus que la longueur de
        # l'horizon, et CP-SAT declare le modele INFAISABLE.
        #
        # L'echeance souple redevenait donc dure, en silence, et UNE seule
        # vieille tache annulait la planification de toutes les autres --
        # constate sur les donnees reelles : 278 taches, INFEASIBLE en 0,04 s,
        # une dichotomie a designe « aller chercher veste Christina pressing »,
        # due depuis 134 jours pour un horizon de 90. C'est exactement ce que
        # le lot 4 exigeait d'eviter : « une echeance intenable est signalee
        # sans empecher les autres d'etre planifiees ».
        plafond = max(0, horizon - borne)
        retard = modele.NewIntVar(0, plafond, "retard_" + uuid[:8])
        modele.AddMaxEquality(retard, [fins[uuid] - borne, 0])
        retards.append(retard)
        ordre_retard.append((uuid, retard))

    # === Objectif, en DEUX resolutions et non deux objectifs (design.md §5) ===
    # CP-SAT n'optimise pas lexicographiquement. On minimise d'abord le retard
    # -- avec, dans le MEME terme, l'absence de tout bloc de la suite d'une
    # tache figee, fortement penalisee (PENALITE_ABSENCE_FIGE) pour qu'elle
    # domine le retard : le solveur place la suite des qu'il le peut, meme au
    # prix d'un retard marginal sur cette meme tache (M5) -- puis on fige
    # l'optimum trouve et on maximise la somme des debuts.
    presences_fige = list(presences_fige_bloc.values())
    if retards or presences_fige:
        objectif1 = list(retards) + [
            PENALITE_ABSENCE_FIGE * (1 - p) for p in presences_fige]
        modele.Minimize(sum(objectif1))
        s1 = _solveur(budget)
        etat1 = s1.Solve(modele)
        _signaler_arret_horloge(s1, etat1, "passe 1 (retard + suite figee)")
        if etat1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return _sans_solution(s1, etat1, "passe 1 (retard + suite figee)",
                                  t0, granularite)
        if retards:
            retard_optimal = s1.Value(sum(retards))
            modele.Add(sum(retards) <= retard_optimal)
        if presences_fige:
            absences = [1 - p for p in presences_fige]
            absences_optimal = s1.Value(sum(absences))
            modele.Add(sum(absences) <= absences_optimal)
            for (uuid, indice), p in presences_fige_bloc.items():
                if not s1.Value(p):
                    _LOG.warning(
                        "tache %s (figee) : le bloc %d de sa suite reste "
                        "absent du plan faute de place (le FAIT, bloc 0, "
                        "est preserve)", uuid, indice)

    # « au plus tard en securite » (decision 7) : on pousse chaque intervalle
    # aussi loin que les contraintes le permettent. La date planifiee EST la marge.
    modele.Maximize(sum(termes_objectif) if termes_objectif else 0)
    s2 = _solveur(budget)
    etat = s2.Solve(modele)
    _signaler_arret_horloge(s2, etat, "passe 1 (au plus tard)")
    if etat not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _sans_solution(s2, etat, "passe 1 (au plus tard)", t0, granularite)

    blocs = []
    for uuid, liste in blocs_modele.items():
        externe = par_uuid[uuid].externe
        for indice, depart, arrivee, _ in liste:
            presence_bloc = presences_fige_bloc.get((uuid, indice))
            if presence_bloc is not None and not s2.Value(presence_bloc):
                continue   # bloc de la suite d'une tache figee, absent ici
            debut = s2.Value(depart)
            # Le regime effectif se lit sur le PLACEMENT, pas sur le statut
            # "detaillee"/"agregee" de la tache : une tache detaillee dont un
            # bloc a du emprunter la soupape agregee (voir plus haut) rend un
            # bloc agrege comme n'importe quel autre. `frontiere` separe les
            # deux regimes dans le temps par construction : un bloc detaille
            # ne peut jamais commencer a ou apres elle.
            agrege = (not externe) and agregation and debut >= frontiere
            blocs.append(Bloc(uuid=uuid, indice=indice,
                              debut=debut, fin=s2.Value(arrivee),
                              externe=externe, agrege=agrege))
    blocs.sort(key=lambda b: (b.debut, b.uuid, b.indice))

    retard_total = sum(s2.Value(r) for r in retards)
    en_retard = tuple(sorted(u for u, r in ordre_retard if s2.Value(r) > 0))

    return Plan(
        blocs=tuple(blocs),
        t0=t0,
        granularite=granularite,
        statut=s2.StatusName(etat),
        retard_total=retard_total,
        en_retard=en_retard,
    )


def _replan(plan, blocs_supplementaires):
    """Rend `plan` augmente de `blocs_supplementaires`, sans rien changer d'autre.

    Sert aux issues de secours de `completer` : un FAIT (bloc 0 fige) reste vrai
    meme quand le remplissage opportuniste, lui, echoue -- ce n'est pas une
    candidate que l'echec du solveur pourrait annuler.
    """
    if not blocs_supplementaires:
        return plan
    blocs = tuple(plan.blocs) + tuple(blocs_supplementaires)
    return Plan(blocs=tuple(sorted(blocs, key=lambda b: (b.debut, b.uuid, b.indice))),
               t0=plan.t0, granularite=plan.granularite, statut=plan.statut,
               retard_total=plan.retard_total, en_retard=plan.en_retard)


def completer(plan, taches, contextes, t0, maintenant, horizon_fin, granularite,
              reunions=(), horizon_detaille_fin=None):
    """Passe 2, le regime opportuniste — design.md §5, lot 6.

        « Le plan de la passe 1 est **fige**. Les taches non datees remplissent
        la capacite restante, par urgence decroissante, au plus tot. »

    `plan`   : le Plan rendu par la passe 1. Il est FIGE — et figé veut dire
               figé : ses blocs ne sont pas des variables de ce modele, ce sont
               des constantes. Rien ici ne peut les deplacer d'un creneau.
    `taches` : les candidates au regime opportuniste (typiquement les non
               datees). Chacune est placee ENTIEREMENT ou pas du tout.

    Rend un nouveau Plan : les blocs de `plan` tels quels, plus les blocs
    opportunistes, ces derniers portant `opportuniste=True`.

    **Pourquoi figer la passe 1**, et pourquoi ce n'est pas un detail
    d'implementation (design.md §5) : pour que la marge annoncee soit
    *actionnable*. Une marge obtenue en reorganisant tout le reste est vraie
    mais inutilisable — on ne la suivra pas, et on cessera de faire confiance
    au chiffre. C'est la raison d'etre de cette fonction separee : on ne
    resout pas « tout ensemble en deux objectifs », on resout la passe 1, on
    la coule dans le beton, et on remplit ce qui reste.
    """
    horizon = indice_creneau(t0, horizon_fin, granularite)
    tot = indice_creneau(t0, maintenant, granularite)

    agregation = horizon_detaille_fin is not None
    frontiere = (min(horizon, indice_creneau(t0, horizon_detaille_fin, granularite))
                 if agregation else horizon)

    modele = cp_model.CpModel()

    cache = {}
    for nom, ctx in contextes.items():
        cache[nom] = _horizons(ctx, t0, horizon_fin, granularite, reunions, frontiere)

    # --- la passe 1, en CONSTANTES et non en variables ---------------------
    # Ses intervalles entrent dans AddNoOverlap et consomment de la capacite,
    # mais ils ne sont pas deplacables : ce sont des intervalles fixes.
    intervalles_ressource = []
    charge_figee = {}            # (contexte, jour) -> creneaux deja consommes
    deja_planifiees = set()

    for bloc in plan.blocs:
        deja_planifiees.add(bloc.uuid)
        if bloc.externe:
            continue   # ne consomme aucune capacite, par definition (decision 10)
        # Un bloc AGREGE n'entre PAS dans AddNoOverlap. Ce n'est pas une
        # tolerance, c'est la definition du regime : au-dela de la frontiere on
        # repond a la journee et non a l'heure, et deux blocs d'une meme journee
        # peuvent donc legitimement se chevaucher (design.md §1). Les verser
        # dans une contrainte de non-chevauchement rendait le modele infaisable
        # DES SA CONSTRUCTION -- `completer` retombait sur son `return plan` de
        # secours et ne placait plus une seule tache non datee, en silence.
        # Leur capacite reste comptee juste en dessous par `charge_figee`, qui
        # travaille en VOLUME par journee : c'est exactement la garantie que le
        # regime agrege promet, et la seule qu'il puisse tenir.
        if not bloc.agrege:
            intervalles_ressource.append(
                modele.NewIntervalVar(bloc.debut, bloc.fin - bloc.debut, bloc.fin,
                                      "fige_{}_{}".format(bloc.uuid[:8], bloc.indice)))
        for indice in range(bloc.debut, bloc.fin):
            jour = instant_creneau(t0, indice, granularite).date()
            for nom in contextes:
                if jour in cache[nom][2]:
                    charge_figee[(nom, jour)] = charge_figee.get((nom, jour), 0) + 1
                    break

    # --- les candidates, en intervalles OPTIONNELS -------------------------
    # Optionnels parce qu'une tache non datee n'a aucune obligation d'etre
    # placee : s'il ne reste pas de place, elle attend. C'est la difference de
    # nature avec la passe 1, ou ne pas placer produit du retard.
    charge_du_jour = {}
    blocs_modele = {}
    presences = {}
    debuts, fins = {}, {}
    # Debuts PONDERES PAR L'URGENCE. Une somme de debuts non ponderee est
    # indifferente a QUI passe devant : avancer n'importe quelle tache de cinq
    # jours y vaut exactement autant qu'avancer la plus urgente. Mesure sur le
    # jeu du lot 6 avant correction -- l'ordre etait presque exactement inverse :
    #
    #     urgence 20,00 -> 12/10     (la plus urgente, placee en DERNIER)
    #     urgence  9,00 -> 05/10
    #     urgence  6,00 -> 07/10
    #     urgence  5,50 -> 08/10
    #
    # C'est le « par urgence decroissante » du lot 6, jamais ecrit jusqu'ici.
    debuts_ponderes = []
    # Le bloc 0 des taches `+fixed` non datees soumises en passe 2 (probleme 1,
    # tests/test_fige_fait.py) : un FAIT construit avec `_construire_bloc_fige`,
    # au meme titre que les blocs de la passe 1 ci-dessus -- pas une candidate
    # que « au plus tot » pourrait deplacer.
    blocs_fige_completer = []
    # (uuid, indice) -> litteral de presence d'un bloc de la SUITE d'une tache
    # figee non datee (indice >= 1, probleme 1 cote passe 2). Jamais la
    # presence, forcee a 1, du bloc 0 (le FAIT) -- voir le fork plus bas.
    presences_fige_bloc = {}

    for tache in taches:
        if tache.estimated is None or tache.uuid in deja_planifiees:
            continue
        ctx = contextes.get(tache.contexte)
        if ctx is None:
            continue
        if tache.externe:
            continue   # un delai fournisseur n'est pas du travail opportuniste

        fenetres, journees, _ = cache[tache.contexte]
        bloc_min = _en_creneaux(ctx.bloc_min, granularite)
        taille = _en_creneaux(tache.estimated, granularite)
        tailles = decouper_en_blocs(taille, bloc_min, insecable=tache.insecable)

        # UNE presence pour toute la tache : entierement placee, ou pas du tout.
        # Un demi-travail planifie ne rend service a personne.
        presence = modele.NewBoolVar("p_" + tache.uuid[:8])
        presences[tache.uuid] = presence
        blocs_modele[tache.uuid] = []
        starts_tache, ends_tache = [], []

        fige0 = tache.fige and tache.scheduled is not None
        fin_fige = None
        indice_depart = 0
        if fige0:
            # Une tache figee n'est jamais optionnelle : son bloc 0 est deja
            # un fait accompli, pas une decision que « au plus tot » pourrait
            # reorganiser (probleme 1).
            modele.Add(presence == 1)
            fixe0 = indice_creneau(t0, tache.scheduled, granularite)
            t_bloc0 = tailles[0]
            nom0 = "o_{}#0".format(tache.uuid[:8])
            depart0, arrivee0, fin_fige, agrege0 = _construire_bloc_fige(
                modele, nom0, fixe0, t_bloc0, frontiere, agregation)
            if not agrege0:
                intervalles_ressource.append(
                    modele.NewIntervalVar(depart0, t_bloc0, arrivee0, "i_" + nom0))
            _consommer_capacite_figee(
                charge_figee, t0, granularite, tache.contexte, fixe0, fin_fige,
                cache[tache.contexte][2])
            blocs_fige_completer.append(Bloc(
                uuid=tache.uuid, indice=0, debut=fixe0, fin=fin_fige,
                externe=False, agrege=agrege0, opportuniste=False))
            starts_tache.append(depart0)
            ends_tache.append(arrivee0)
            tailles = tailles[1:]   # le reste, s'il y en a, suit le chemin normal
            indice_depart = 1

        candidates = [(jour, plage.debut, plage.fin) for jour, plage in fenetres]
        candidates += journees

        for indice_rel, t_bloc in enumerate(tailles):
            indice = indice_rel + indice_depart
            nom = "o_{}#{}".format(tache.uuid[:8], indice)
            retenues = []
            for jour, borne_brute, borne_haute in candidates:
                borne_basse = max(borne_brute, tot)
                if fin_fige is not None:
                    # Les blocs suivants d'une tache figee ne commencent
                    # jamais avant que le FAIT (bloc 0) ne soit termine.
                    borne_basse = max(borne_basse, fin_fige)
                if borne_haute - borne_basse >= t_bloc:
                    retenues.append((jour, borne_basse, borne_haute))

            if fige0:
                # --- la SUITE d'une tache figee non datee (probleme 1) : un
                # litteral de presence PAR BLOC, jamais le `presence` du bloc 0
                # (le FAIT, force a 1 plus haut) -- sinon on retombe sur la
                # contradiction du contrat (test 9) : `presence == 1` puis
                # `presence == 0` sur la MEME variable, modele entier infaisable.
                if not retenues:
                    _LOG.warning(
                        "tache %s (figee) : le bloc %d de sa suite n'a aucune "
                        "fenetre candidate d'ici l'horizon, il reste absent "
                        "du plan (le FAIT, bloc 0, est preserve)",
                        tache.uuid, indice)
                    continue

                presence_bloc = modele.NewBoolVar("pf_" + nom)
                presences_fige_bloc[(tache.uuid, indice)] = presence_bloc

                domaine = cp_model.Domain.FromIntervals(
                    [[bas, haut - t_bloc] for _, bas, haut in retenues])
                depart = modele.NewIntVarFromDomain(domaine, "d_" + nom)
                arrivee = modele.NewIntVarFromDomain(
                    cp_model.Domain.FromIntervals(
                        [[bas + t_bloc, haut] for _, bas, haut in retenues]),
                    "f_" + nom)
                modele.Add(arrivee == depart + t_bloc)

                intervalles_ressource.append(
                    modele.NewOptionalIntervalVar(
                        depart, t_bloc, arrivee, presence_bloc, "i_" + nom))

                litteraux = []
                for jour, borne_basse, borne_haute in retenues:
                    lit = modele.NewBoolVar("w_{}_{}".format(nom, jour))
                    modele.Add(depart >= borne_basse).OnlyEnforceIf(lit)
                    modele.Add(depart + t_bloc <= borne_haute).OnlyEnforceIf(lit)
                    litteraux.append(lit)
                    charge_du_jour.setdefault(
                        (tache.contexte, jour), []).append((t_bloc, lit))
                modele.AddExactlyOne(litteraux).OnlyEnforceIf(presence_bloc)
                for lit in litteraux:
                    modele.AddImplication(lit, presence_bloc)

                # Si absent, `depart` est fixe au minimum de son domaine plutot
                # que laisse libre -- sinon une valeur arbitraire gonflerait
                # `d_t`/`f_t` (debut/fin de la tache, plus bas) sans
                # correspondre a un placement reel.
                borne_min_domaine = min(bas for _, bas, _ in retenues)
                modele.Add(depart == borne_min_domaine).OnlyEnforceIf(
                    presence_bloc.Not())

                blocs_modele[tache.uuid].append((indice, depart, arrivee, t_bloc))
                starts_tache.append(depart)
                ends_tache.append(arrivee)
                # Plancher d'urgence, meme logique que les candidates
                # ordinaires : « au plus tot » doit aussi pousser la suite
                # d'une figee des qu'elle est presente.
                poids_urgence = POIDS_PLANCHER + int(round(
                    max(0.0, tache.urgency) * ECHELLE_URGENCE))
                debuts_ponderes.append((poids_urgence, depart))
                continue

            if not retenues:
                modele.Add(presence == 0)
                break

            domaine = cp_model.Domain.FromIntervals(
                [[bas, haut - t_bloc] for _, bas, haut in retenues])
            depart = modele.NewIntVarFromDomain(domaine, "d_" + nom)
            arrivee = modele.NewIntVarFromDomain(
                cp_model.Domain.FromIntervals(
                    [[bas + t_bloc, haut] for _, bas, haut in retenues]),
                "f_" + nom)
            modele.Add(arrivee == depart + t_bloc)

            # L'intervalle n'existe que si la tache est retenue.
            intervalles_ressource.append(
                modele.NewOptionalIntervalVar(depart, t_bloc, arrivee, presence,
                                              "i_" + nom))

            litteraux = []
            for jour, borne_basse, borne_haute in retenues:
                lit = modele.NewBoolVar("w_{}_{}".format(nom, jour))
                modele.Add(depart >= borne_basse).OnlyEnforceIf(lit)
                modele.Add(depart + t_bloc <= borne_haute).OnlyEnforceIf(lit)
                litteraux.append(lit)
                charge_du_jour.setdefault(
                    (tache.contexte, jour), []).append((t_bloc, lit))
            # Exactement une fenetre SI la tache est retenue, aucune sinon :
            # c'est ce qui evite qu'un bloc absent consomme de la capacite.
            modele.AddExactlyOne(litteraux).OnlyEnforceIf(presence)
            for lit in litteraux:
                modele.AddImplication(lit, presence)

            blocs_modele[tache.uuid].append((indice, depart, arrivee, t_bloc))
            starts_tache.append(depart)
            ends_tache.append(arrivee)
            # Plancher : une urgence nulle doit quand meme pousser vers le tot,
            # sinon la tache devient libre de se poser n'importe ou.
            poids_urgence = POIDS_PLANCHER + int(round(
                max(0.0, tache.urgency) * ECHELLE_URGENCE))
            debuts_ponderes.append((poids_urgence, depart))

        if starts_tache:
            d_t = modele.NewIntVar(tot, horizon, "dt_o_" + tache.uuid[:8])
            f_t = modele.NewIntVar(tot, horizon, "ft_o_" + tache.uuid[:8])
            modele.AddMinEquality(d_t, starts_tache)
            modele.AddMaxEquality(f_t, ends_tache)
            debuts[tache.uuid] = d_t
            fins[tache.uuid] = f_t

    # --- ressource unique : la passe 1 figee + les candidates retenues ------
    if intervalles_ressource:
        modele.AddNoOverlap(intervalles_ressource)

    # --- capacite quotidienne : ce que la passe 1 a deja pris compte --------
    for (nom_ctx, jour), charges in charge_du_jour.items():
        capacite = cache[nom_ctx][2].get(jour)
        if capacite is None:
            continue
        reste = capacite - charge_figee.get((nom_ctx, jour), 0)
        modele.Add(sum(taille * lit for taille, lit in charges) <= max(0, reste))

    # --- precedences, entre candidates et vers la passe 1 ------------------
    fins_passe1 = {}
    for bloc in plan.blocs:
        fins_passe1[bloc.uuid] = max(fins_passe1.get(bloc.uuid, 0), bloc.fin)
    for tache in taches:
        if tache.uuid not in debuts:
            continue
        for predecesseur in tache.depends:
            if predecesseur in fins:
                modele.Add(debuts[tache.uuid] >= fins[predecesseur])
            elif predecesseur in fins_passe1:
                modele.Add(debuts[tache.uuid] >= fins_passe1[predecesseur])

    if not presences:
        _LOG.info("passe 2 : aucune candidate soumise, le plan ressort intact")
        return plan   # rien a faire : le plan de la passe 1 ressort intact

    # === Objectif, en deux resolutions (design.md §5) =======================
    # D'abord placer le plus d'urgence possible, ensuite seulement le faire au
    # plus tot. L'urgence de Taskwarrior est un flottant ; on la met a l'echelle
    # en entier, CP-SAT ne manipulant que des entiers.
    echelle = 1000
    poids = []
    # Plancher + decalage sur l'urgence minimale des candidates : une tache
    # bloquee vaut -5 d'urgence dans Taskwarrior, or un poids negatif
    # penaliserait sa presence au lieu de rester indifferent. On decale donc
    # toutes les urgences par rapport au minimum observe ici (u_min <= 0
    # possible) pour que le poids de presence reste toujours strictement
    # positif, en preservant l'ordre relatif des urgences (POIDS_PLANCHER >
    # 0 partout, meme quand u_min == urgency).
    urgences_candidates = [tache.urgency for tache in taches
                           if tache.uuid in presences]
    u_min = min(urgences_candidates) if urgences_candidates else 0.0
    for tache in taches:
        if tache.uuid in presences:
            poids_presence = POIDS_PLANCHER + int(round(
                (tache.urgency - u_min) * echelle))
            poids.append(poids_presence * presences[tache.uuid])
    # La suite d'une tache figee (probleme 1) pese, dans ce MEME objectif,
    # bien plus que n'importe quelle urgence : sa presence doit dominer, sans
    # quoi elle serait mise en concurrence avec des candidates ordinaires pour
    # de la capacite -- exactement ce que le contrat interdit (test 9).
    presences_fige = list(presences_fige_bloc.values())
    objectif1 = list(poids) + [PENALITE_ABSENCE_FIGE * p for p in presences_fige]
    modele.Maximize(sum(objectif1) if objectif1 else 0)
    s1 = _solveur()
    etat1 = s1.Solve(modele)
    _signaler_arret_horloge(s1, etat1, "passe 2 (maximisation de l'urgence)")
    if etat1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Ne devrait pas arriver : les candidates sont des intervalles
        # OPTIONNELS, donc « ne rien placer » est toujours une solution. Si on
        # passe ici, c'est que le modele est contradictoire avant meme d'avoir
        # a choisir -- ce qui etait precisement le cas des blocs agreges verses
        # dans AddNoOverlap. Le plan ressort ampute : on le dit fort.
        _LOG.warning(
            "passe 2 : modele sans solution (%s), 0 tache placee sur %d "
            "candidates ; le plan ressort tel quel",
            s1.StatusName(etat1), len(presences))
        # Les FAITS (blocs figes non-datees) restent vrais meme quand le
        # remplissage opportuniste echoue : ce ne sont pas des candidates.
        return _replan(plan, blocs_fige_completer)
    urgence_optimale = s1.Value(sum(poids)) if poids else 0
    modele.Add(sum(poids) >= urgence_optimale)
    if presences_fige:
        presence_fige_optimale = s1.Value(sum(presences_fige))
        modele.Add(sum(presences_fige) >= presence_fige_optimale)
        for (uuid, indice), p in presences_fige_bloc.items():
            if not s1.Value(p):
                _LOG.warning(
                    "tache %s (figee) : le bloc %d de sa suite reste absent "
                    "du plan faute de place (le FAIT, bloc 0, est preserve)",
                    uuid, indice)

    # « au plus tot » : c'est l'inverse exact de la passe 1, et c'est voulu.
    # Le travail sans echeance se fait des qu'il y a de la place ; le travail
    # date se fait contre son mur.
    modele.Minimize(sum(poids * depart for poids, depart in debuts_ponderes)
                    if debuts_ponderes else 0)
    s2 = _solveur()
    etat = s2.Solve(modele)
    _signaler_arret_horloge(s2, etat, "passe 2 (au plus tot)")
    if etat not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _LOG.warning(
            "passe 2 : pas de solution au second objectif (%s), 0 tache placee "
            "sur %d candidates ; le plan ressort tel quel",
            s2.StatusName(etat), len(presences))
        return _replan(plan, blocs_fige_completer)

    # --- on recolle : la passe 1 d'abord, telle quelle ---------------------
    blocs = list(plan.blocs) + blocs_fige_completer
    for uuid, liste in blocs_modele.items():
        if not s2.Value(presences[uuid]):
            continue
        for indice, depart, arrivee, _ in liste:
            presence_bloc = presences_fige_bloc.get((uuid, indice))
            if presence_bloc is not None and not s2.Value(presence_bloc):
                continue   # bloc de la suite d'une tache figee, absent ici
            debut = s2.Value(depart)
            blocs.append(Bloc(uuid=uuid, indice=indice,
                              debut=debut, fin=s2.Value(arrivee),
                              externe=False,
                              agrege=debut >= frontiere if agregation else False,
                              opportuniste=True))
    blocs.sort(key=lambda b: (b.debut, b.uuid, b.indice))

    # Les deux nombres, toujours, meme quand tout va bien : c'est ce qui permet
    # de voir un plan ampute dans la sortie au lieu de le prendre pour complet.
    placees = sum(1 for uuid in presences if s2.Value(presences[uuid]))
    journal = _LOG.info if placees == len(presences) else _LOG.warning
    journal("passe 2 : %d tache(s) placee(s) sur %d candidate(s)",
            placees, len(presences))

    return Plan(
        blocs=tuple(blocs),
        t0=plan.t0,
        granularite=plan.granularite,
        statut=plan.statut,
        retard_total=plan.retard_total,
        en_retard=plan.en_retard,
    )
