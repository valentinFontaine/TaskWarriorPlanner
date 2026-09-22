"""Modele de contraintes — design.md §5, passe 1 (« le mur »).

Ce module ne reimplemente ni solveur ni propagation : CP-SAT fait ce travail.
Il se contente de traduire le cahier des charges en contraintes.

Ce qui est ecrit ici couvre les lots 4 et 5 :

- lot 4 : intervalles, fenetres, bloc minimum, `AddNoOverlap` sur la ressource
  unique, precedences, echeances, objectif lexicographique ;
- lot 5 : les taches `+externe`. C'est une seule ligne de difference et c'est
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

# Duree maximale laissee au solveur. Au-dela on rend ce qu'on a trouve, plutot
# que de bloquer : le plan doit sortir.
SECONDES_MAX = 60.0


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

        Les blocs `+externe` sont exclus **par definition** : ils ne consomment
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


def decouper_en_blocs(taille_totale, bloc_min, insecable=False):
    """design.md §5, variables.

    Un seul bloc si la tache est `+insecable` ou si elle tient dans le bloc
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
        limites = limites_effectives(taches, contextes)

    par_uuid = {t.uuid: t for t in taches}
    modele = cp_model.CpModel()

    # fenetres, journees agregees et capacites, une fois par contexte
    cache = {}
    for nom, ctx in contextes.items():
        cache[nom] = _horizons(ctx, t0, horizon_fin, granularite, reunions, frontiere)

    intervalles_ressource = []   # ce qui entre dans AddNoOverlap
    # (contexte, jour) -> liste de (taille, litteral) pour la capacite quotidienne
    charge_du_jour = {}
    blocs_modele = {}            # uuid -> liste de (indice, start, end, taille)
    debuts = {}
    fins = {}
    termes_objectif = []   # « au plus tard » : voir la note a la fin
    agreges = set()              # uuids modelises en regime agrege

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
        if not detaillee:
            agreges.add(tache.uuid)

        tailles = decouper_en_blocs(taille, bloc_min, insecable=tache.insecable)
        blocs_modele[tache.uuid] = []
        starts_tache, ends_tache = [], []

        if detaillee:
            # Regime DETAILLE : le bloc tient tout entier dans UNE plage de la
            # grille. Il ne peut ni enjamber la pause du midi, ni franchir
            # minuit. Et il entre dans la ressource unique.
            candidates = [(jour, plage.debut, plage.fin) for jour, plage in fenetres]
        else:
            # Regime AGREGE : la journee entiere sert de fenetre, et le bloc
            # n'entre PAS dans AddNoOverlap. `frontiere` dans la borne basse
            # garantit qu'un bloc agrege ne vient jamais se superposer a un
            # bloc detaille : les deux regimes restent dans des plages de temps
            # disjointes.
            candidates = journees

        for indice, t_bloc in enumerate(tailles):
            nom = "{}#{}".format(tache.uuid[:8], indice)

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
            for jour, borne_brute, borne_haute in candidates:
                borne_basse = max(borne_brute, tot)
                if not detaillee:
                    borne_basse = max(borne_basse, frontiere)
                if borne_haute - borne_basse < t_bloc:
                    continue
                retenues.append((jour, borne_basse, borne_haute))

            if retenues:
                domaine = cp_model.Domain.FromIntervals(
                    [[bas, haut - t_bloc] for _, bas, haut in retenues])
                depart = modele.NewIntVarFromDomain(domaine, "d_" + nom)
                arrivee = modele.NewIntVarFromDomain(
                    cp_model.Domain.FromIntervals(
                        [[bas + t_bloc, haut] for _, bas, haut in retenues]),
                    "f_" + nom)
            else:
                depart = modele.NewIntVar(tot, max(tot, horizon - t_bloc), "d_" + nom)
                arrivee = modele.NewIntVar(tot, horizon, "f_" + nom)
            modele.Add(arrivee == depart + t_bloc)

            if detaillee:
                intervalles_ressource.append(
                    modele.NewIntervalVar(depart, t_bloc, arrivee, "i_" + nom))

            litteraux = []
            for jour, borne_basse, borne_haute in retenues:
                lit = modele.NewBoolVar("w_{}_{}_{}".format(nom, jour, borne_basse))
                modele.Add(depart >= borne_basse).OnlyEnforceIf(lit)
                modele.Add(depart + t_bloc <= borne_haute).OnlyEnforceIf(lit)
                litteraux.append(lit)
                charge_du_jour.setdefault(
                    (tache.contexte, jour), []).append((t_bloc, lit))

            if not litteraux:
                # Aucune fenetre ne peut accueillir ce bloc : le modele est
                # infaisable, et c'est le bon verdict. Les pre-verifications du
                # lot 3 sont la pour l'annoncer avant d'en arriver la.
                modele.Add(depart > horizon)   # domaine vide : INFEASIBLE
            else:
                modele.AddExactlyOne(litteraux)

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
    # `+externe` en sont absentes : c'est toute la difference (decision 10).
    # Les blocs agreges en sont absents aussi, mais pour une autre raison : ils
    # sont au-dela de la frontiere, ou l'on ne repond plus a l'heure.
    if intervalles_ressource:
        modele.AddNoOverlap(intervalles_ressource)

    # --- marge quotidienne (decision 11), posee en volume --------------------
    # C'est la contrainte qui tient AUSSI en regime agrege : on relache les
    # heures, jamais la capacite.
    for (nom_ctx, jour), charges in charge_du_jour.items():
        capacite = cache[nom_ctx][2].get(jour)
        if capacite is None:
            continue
        modele.Add(sum(taille * lit for taille, lit in charges) <= capacite)

    # --- contrainte 8 : taches figees ---------------------------------------
    for tache in taches:
        if tache.fige and tache.scheduled is not None and tache.uuid in blocs_modele:
            fixe = indice_creneau(t0, tache.scheduled, granularite)
            modele.Add(blocs_modele[tache.uuid][0][1] == fixe)

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
        retard = modele.NewIntVar(0, horizon, "retard_" + uuid[:8])
        modele.AddMaxEquality(retard, [fins[uuid] - borne, 0])
        retards.append(retard)
        ordre_retard.append((uuid, retard))

    def _solveur():
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = SECONDES_MAX
        # Un seul worker et une graine fixe : le plan doit etre reproductible.
        s.parameters.num_search_workers = 1
        s.parameters.random_seed = 0
        return s

    # === Objectif, en DEUX resolutions et non deux objectifs (design.md §5) ===
    # CP-SAT n'optimise pas lexicographiquement. On minimise d'abord le retard,
    # on fige l'optimum trouve, puis on maximise la somme des debuts.
    if retards:
        modele.Minimize(sum(retards))
        s1 = _solveur()
        etat1 = s1.Solve(modele)
        if etat1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return Plan(blocs=(), t0=t0, granularite=granularite,
                        statut="INFEASIBLE", retard_total=0, en_retard=())
        retard_optimal = int(s1.ObjectiveValue())
        modele.Add(sum(retards) <= retard_optimal)

    # « au plus tard en securite » (decision 7) : on pousse chaque intervalle
    # aussi loin que les contraintes le permettent. La date planifiee EST la marge.
    modele.Maximize(sum(termes_objectif) if termes_objectif else 0)
    s2 = _solveur()
    etat = s2.Solve(modele)
    if etat not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Plan(blocs=(), t0=t0, granularite=granularite,
                    statut="INFEASIBLE", retard_total=0, en_retard=())

    blocs = []
    for uuid, liste in blocs_modele.items():
        externe = par_uuid[uuid].externe
        agrege = uuid in agreges
        for indice, depart, arrivee, _ in liste:
            blocs.append(Bloc(uuid=uuid, indice=indice,
                              debut=s2.Value(depart), fin=s2.Value(arrivee),
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
    tous_les_debuts = []

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

        candidates = [(jour, plage.debut, plage.fin) for jour, plage in fenetres]
        candidates += journees

        for indice, t_bloc in enumerate(tailles):
            nom = "o_{}#{}".format(tache.uuid[:8], indice)
            retenues = []
            for jour, borne_brute, borne_haute in candidates:
                borne_basse = max(borne_brute, tot)
                if borne_haute - borne_basse >= t_bloc:
                    retenues.append((jour, borne_basse, borne_haute))
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
            tous_les_debuts.append(depart)

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

    def _solveur():
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = SECONDES_MAX
        s.parameters.num_search_workers = 1
        s.parameters.random_seed = 0
        return s

    if not presences:
        _LOG.info("passe 2 : aucune candidate soumise, le plan ressort intact")
        return plan   # rien a faire : le plan de la passe 1 ressort intact

    # === Objectif, en deux resolutions (design.md §5) =======================
    # D'abord placer le plus d'urgence possible, ensuite seulement le faire au
    # plus tot. L'urgence de Taskwarrior est un flottant ; on la met a l'echelle
    # en entier, CP-SAT ne manipulant que des entiers.
    echelle = 1000
    poids = []
    for tache in taches:
        if tache.uuid in presences:
            poids.append(int(round(tache.urgency * echelle)) * presences[tache.uuid])
    modele.Maximize(sum(poids) if poids else 0)
    s1 = _solveur()
    etat1 = s1.Solve(modele)
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
        return plan   # aucune place : on rend la passe 1 telle quelle
    urgence_optimale = int(s1.ObjectiveValue())
    modele.Add(sum(poids) >= urgence_optimale)

    # « au plus tot » : c'est l'inverse exact de la passe 1, et c'est voulu.
    # Le travail sans echeance se fait des qu'il y a de la place ; le travail
    # date se fait contre son mur.
    modele.Minimize(sum(tous_les_debuts) if tous_les_debuts else 0)
    s2 = _solveur()
    etat = s2.Solve(modele)
    if etat not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _LOG.warning(
            "passe 2 : pas de solution au second objectif (%s), 0 tache placee "
            "sur %d candidates ; le plan ressort tel quel",
            s2.StatusName(etat), len(presences))
        return plan

    # --- on recolle : la passe 1 d'abord, telle quelle ---------------------
    blocs = list(plan.blocs)
    for uuid, liste in blocs_modele.items():
        if not s2.Value(presences[uuid]):
            continue
        for indice, depart, arrivee, _ in liste:
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
