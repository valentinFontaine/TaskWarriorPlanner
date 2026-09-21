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

Conventions :

- toutes les positions et durees sont des **entiers en nombre de creneaux**
  (design.md §1). Jamais de flottant d'heures dans le modele.
- `t0`, `maintenant`, `horizon_fin` et les `due` sont **naifs, en heure locale**.
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
   ce qui evite d'avoir deux representations du meme fait.
"""
import math
from dataclasses import dataclass
from datetime import timedelta

from ortools.sat.python import cp_model

from planif.calendrier import disponibilite, indice_creneau, instant_creneau
from planif.tampon import limites_effectives

__all__ = ["Bloc", "Plan", "resoudre", "decouper_en_blocs"]

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


def _fenetres(contexte, t0, horizon_fin, granularite, reunions):
    """Rend (fenetres, capacites).

    `fenetres` : liste de (jour, Plage) sur tout l'horizon.
    `capacites` : jour -> capacite en creneaux (grille moins reunions moins marge).
    """
    fenetres = []
    capacites = {}
    jour = t0.date()
    dernier = horizon_fin.date()
    while jour <= dernier:
        disp = disponibilite(contexte, jour, t0, granularite, reunions)
        if disp.plages:
            for plage in disp.plages:
                fenetres.append((jour, plage))
            capacites[jour] = disp.capacite
        jour += timedelta(days=1)
    return fenetres, capacites


def resoudre(taches, contextes, t0, maintenant, horizon_fin, granularite,
             reunions=(), limites=None):
    """Passe 1 du design.md §5 : les taches datees, placees au plus tard en securite.

    `limites` : dict uuid -> datetime de fin au plus tard. Si None, il est calcule
    par `planif.tampon.limites_effectives` — c'est-a-dire tampon applique une seule
    fois sur les `due` reelles, puis herite le long du graphe sans re-tamponner.

    L'echeance est une contrainte **souple** : une echeance intenable produit du
    retard et l'uuid remonte dans `Plan.en_retard`, mais elle n'empeche pas les
    autres taches d'etre planifiees. C'est une exigence explicite du lot 4.
    """
    horizon = indice_creneau(t0, horizon_fin, granularite)
    tot = indice_creneau(t0, maintenant, granularite)  # rien ne commence avant

    if limites is None:
        limites = limites_effectives(taches, contextes)

    par_uuid = {t.uuid: t for t in taches}
    modele = cp_model.CpModel()

    # fenetres et capacites, une fois par contexte
    cache = {}
    for nom, ctx in contextes.items():
        cache[nom] = _fenetres(ctx, t0, horizon_fin, granularite, reunions)

    intervalles_ressource = []   # ce qui entre dans AddNoOverlap
    # jour -> liste de (taille, litteral) pour la capacite quotidienne
    charge_du_jour = {}
    blocs_modele = {}            # uuid -> liste de (indice, start, end, taille)
    debuts = {}
    fins = {}
    tous_les_debuts = []

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
            depart = modele.NewIntVar(tot, max(tot, horizon - taille), "d_" + tache.uuid)
            arrivee = modele.NewIntVar(tot, horizon, "f_" + tache.uuid)
            modele.Add(arrivee == depart + taille)
            debuts[tache.uuid] = depart
            fins[tache.uuid] = arrivee
            blocs_modele[tache.uuid] = [(0, depart, arrivee, taille)]
            tous_les_debuts.append(depart)
            continue

        ctx = contextes.get(tache.contexte)
        if ctx is None:
            continue  # sortie du modele, listee par les pre-verifications
        fenetres, capacites = cache[tache.contexte]
        bloc_min = _en_creneaux(ctx.bloc_min, granularite)

        tailles = decouper_en_blocs(taille, bloc_min, insecable=tache.insecable)
        blocs_modele[tache.uuid] = []
        starts_tache, ends_tache = [], []

        for indice, t_bloc in enumerate(tailles):
            nom = "{}#{}".format(tache.uuid[:8], indice)
            depart = modele.NewIntVar(tot, max(tot, horizon - t_bloc), "d_" + nom)
            arrivee = modele.NewIntVar(tot, horizon, "f_" + nom)
            modele.Add(arrivee == depart + t_bloc)
            intervalles_ressource.append(
                modele.NewIntervalVar(depart, t_bloc, arrivee, "i_" + nom))

            # Fenetres : le bloc tient tout entier dans UNE plage disponible.
            # Il ne peut donc ni enjamber la pause du midi, ni franchir minuit.
            litteraux = []
            for jour, plage in fenetres:
                borne_basse = max(plage.debut, tot)
                if plage.fin - borne_basse < t_bloc:
                    continue
                lit = modele.NewBoolVar("w_{}_{}_{}".format(nom, jour, plage.debut))
                modele.Add(depart >= borne_basse).OnlyEnforceIf(lit)
                modele.Add(depart + t_bloc <= plage.fin).OnlyEnforceIf(lit)
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

            blocs_modele[tache.uuid].append((indice, depart, arrivee, t_bloc))
            starts_tache.append(depart)
            ends_tache.append(arrivee)
            tous_les_debuts.append(depart)

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
    if intervalles_ressource:
        modele.AddNoOverlap(intervalles_ressource)

    # --- marge quotidienne (decision 11), posee en volume --------------------
    for (nom_ctx, jour), charges in charge_du_jour.items():
        capacite = cache[nom_ctx][1].get(jour)
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
    modele.Maximize(sum(tous_les_debuts) if tous_les_debuts else 0)
    s2 = _solveur()
    etat = s2.Solve(modele)
    if etat not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Plan(blocs=(), t0=t0, granularite=granularite,
                    statut="INFEASIBLE", retard_total=0, en_retard=())

    blocs = []
    for uuid, liste in blocs_modele.items():
        externe = par_uuid[uuid].externe
        for indice, depart, arrivee, _ in liste:
            blocs.append(Bloc(uuid=uuid, indice=indice,
                              debut=s2.Value(depart), fin=s2.Value(arrivee),
                              externe=externe))
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
