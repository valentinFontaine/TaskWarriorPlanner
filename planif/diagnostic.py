"""Noyau d'insatisfiabilite — design.md §6, lot 8.

    « CP-SAT rend un noyau d'insatisfiabilite via des hypotheses
    (`AddAssumption`). Chaque contrainte d'echeance et chaque tache figee est
    posee comme une hypothese etiquetee, de sorte que le noyau se retraduise en
    langage courant. »
    « **On diagnostique, on ne tranche pas.** »

## Pourquoi un modele separe de `resoudre`

Dans `planif/solveur.py`, l'echeance est une contrainte **souple** : la depasser
produit du retard, pas une infaisabilite. C'est voulu — une echeance intenable
ne doit pas empoisonner tout le plan (lot 4). Consequence : `resoudre` ne rend
presque jamais `INFEASIBLE`, et il n'y a donc **rien a diagnostiquer** dessus.

Le diagnostic pose la question inverse : « si j'exige que **toutes** les
echeances soient tenues, qu'est-ce qui s'oppose ? ». Il faut donc un modele ou
les echeances sont **dures**, chacune sous une hypothese etiquetee. C'est un
autre modele, pas un mode de celui-la.

## Ce que le noyau nomme, et ce qu'il ne nomme pas

Trois genres d'elements sont poses en hypothese, ceux que `design.md` §6 cite
dans son exemple de message :

- `echeance`  : la contrainte « cette tache finit avant sa limite » ;
- `figee`     : le debut impose d'une tache `+fige` ;
- `insecable` : le fait qu'une tache `+insecable` tienne en un seul bloc.

Tout le reste (capacite quotidienne, non-chevauchement, precedences, grille)
est **dur et non assumable** : ce sont les regles du monde, pas des exigences
negociables. Si le modele est infaisable sans qu'aucune hypothese soit en
cause, le noyau est vide et on le dit franchement — c'est que la capacite
elle-meme ne suffit pas, et aucune echeance n'y changera rien.

## Dette assumee

La pose des blocs (fenetres, capacite, non-chevauchement) est proche de celle
de `planif/solveur.py`. Elle n'a **pas** ete factorisee : extraire un
constructeur commun aurait touche `resoudre`, donc les lots 4, 5 et 6 et leurs
tests, au profit d'une economie d'une quarantaine de lignes. Le risque n'en
valait pas la chandelle a ce stade. C'est signale dans RAPPORT-NUIT-2.md comme
une dette a reprendre, pas comme un choix definitif.
"""
from dataclasses import dataclass

from ortools.sat.python import cp_model

from planif.calendrier import indice_creneau, instant_creneau
from planif.solveur import _en_creneaux, _horizons, decouper_en_blocs
from planif.tampon import limites_effectives
from planif.verifications import verifier_insecables

__all__ = ["Element", "Diagnostic", "diagnostiquer"]

SECONDES_MAX = 30.0


@dataclass(frozen=True)
class Element:
    """Un element du noyau, deja traduit en langage courant."""

    genre: str        # 'echeance' | 'figee' | 'insecable'
    uuid: str
    description: str
    texte: str        # la phrase a montrer

    def __str__(self):
        return self.texte


@dataclass(frozen=True)
class Diagnostic:
    """Le verdict. `faisable` vrai -> `noyau` vide et `message` vide."""

    faisable: bool
    noyau: tuple
    message: str

    def __bool__(self):
        return self.faisable


def _phrase(genre, tache, limite=None):
    if genre == "echeance":
        return "l'echeance du {} sur « {} »".format(
            limite.strftime("%d/%m a %H:%M"), tache.description)
    if genre == "figee":
        return "la tache figee « {} » du {}".format(
            tache.description, tache.scheduled.strftime("%d/%m a %H:%M"))
    heures = tache.estimated.total_seconds() / 3600.0
    texte = "{:g} h".format(heures)
    return "les {} indivisibles de « {} »".format(texte, tache.description)


def _message_du_noyau(noyau):
    """Retraduit le noyau en une phrase, comme l'exige design.md §6."""
    if len(noyau) == 1:
        return "Cet element est intenable a lui seul : {}.".format(noyau[0].texte)
    return "Ces {} elements s'opposent : {}.".format(
        len(noyau), ", ".join(e.texte for e in noyau))


def diagnostiquer(taches, contextes, t0, maintenant, horizon_fin, granularite,
                  reunions=(), limites=None, horizon_detaille_fin=None):
    """Rend un `Diagnostic` : faisable, ou le noyau des elements qui s'opposent.

    Les echeances sont ici **dures**, contrairement a `planif.solveur.resoudre`.
    On repond a « qu'est-ce qui empeche de tout tenir ? », pas a « quel est le
    meilleur plan possible ? ».
    """
    # --- les pre-verifications d'abord, AVANT tout appel au solveur -------
    # design.md §6 : « Elles sont betes, rapides, et evitent un INFEASIBLE sans
    # explication. » Une tache `+insecable` plus longue que la plus grande
    # plage contigue en est le cas type.
    #
    # Ce n'est pas qu'une economie : c'est le SEUL moyen de la nommer. Pose en
    # hypothese, ce cas est resolu par le PRESOLVE de CP-SAT, qui fixe le
    # litteral avant meme que le mecanisme d'hypotheses n'entre en jeu — et
    # `SufficientAssumptionsForInfeasibility` rend alors une liste **vide**.
    # Constate en l'executant, pas suppose. On traite donc ce cas ici, ou l'on
    # sait exactement quoi dire.
    par_uuid = {t.uuid: t for t in taches}
    elements_insecables = []
    for anomalie in verifier_insecables(taches, contextes):
        for uuid in anomalie.uuids:
            tache = par_uuid.get(uuid)
            if tache is not None:
                elements_insecables.append(Element(
                    genre="insecable", uuid=uuid,
                    description=tache.description,
                    texte=_phrase("insecable", tache)))
    if elements_insecables:
        noyau = tuple(sorted(elements_insecables,
                             key=lambda e: (e.description, e.uuid)))
        return Diagnostic(
            faisable=False, noyau=noyau,
            message=_message_du_noyau(noyau))

    horizon = indice_creneau(t0, horizon_fin, granularite)
    tot = indice_creneau(t0, maintenant, granularite)

    agregation = horizon_detaille_fin is not None
    frontiere = (min(horizon, indice_creneau(t0, horizon_detaille_fin, granularite))
                 if agregation else horizon)

    if limites is None:
        limites = limites_effectives(taches, contextes)

    modele = cp_model.CpModel()
    cache = {}
    for nom, ctx in contextes.items():
        cache[nom] = _horizons(ctx, t0, horizon_fin, granularite, reunions, frontiere)

    intervalles = []
    charge_du_jour = {}
    debuts, fins, premiers = {}, {}, {}
    etiquettes = {}          # litteral d'hypothese -> Element

    for tache in taches:
        if tache.estimated is None:
            continue
        taille = _en_creneaux(tache.estimated, granularite)

        if tache.externe:
            depart = modele.NewIntVar(tot, max(tot, horizon - taille), "d_" + tache.uuid[:8])
            arrivee = modele.NewIntVar(tot, horizon, "f_" + tache.uuid[:8])
            modele.Add(arrivee == depart + taille)
            debuts[tache.uuid] = depart
            fins[tache.uuid] = arrivee
            continue

        ctx = contextes.get(tache.contexte)
        if ctx is None:
            continue
        fenetres, journees, _ = cache[tache.contexte]
        bloc_min = _en_creneaux(ctx.bloc_min, granularite)
        tailles = decouper_en_blocs(taille, bloc_min, insecable=tache.insecable)

        # Une tache `+insecable` tient en un seul bloc. C'est une exigence
        # negociable (on peut la decouper), donc elle est posee en hypothese.
        presence = None
        if tache.insecable:
            presence = modele.NewBoolVar("h_insec_" + tache.uuid[:8])
            etiquettes[presence] = Element(
                genre="insecable", uuid=tache.uuid,
                description=tache.description,
                texte=_phrase("insecable", tache))

        candidates = [(jour, plage.debut, plage.fin) for jour, plage in fenetres]
        candidates += journees

        starts, ends = [], []
        for indice, t_bloc in enumerate(tailles):
            nom = "{}#{}".format(tache.uuid[:8], indice)
            retenues = [(jour, max(bas, tot), haut)
                        for jour, bas, haut in candidates
                        if haut - max(bas, tot) >= t_bloc]

            if not retenues:
                # Aucune fenetre : si c'est une insecable, c'est SON hypothese
                # qui tombe, et le noyau la nommera. Sinon le modele est
                # infaisable sans hypothese en cause, et on le dira.
                if presence is not None:
                    modele.Add(presence == 0)
                    depart = modele.NewIntVar(tot, horizon, "d_" + nom)
                    arrivee = modele.NewIntVar(tot, horizon, "f_" + nom)
                    modele.Add(arrivee == depart + t_bloc)
                    starts.append(depart)
                    ends.append(arrivee)
                    continue
                modele.Add(modele.NewIntVar(0, 0, "impossible_" + nom) == 1)
                continue

            domaine = cp_model.Domain.FromIntervals(
                [[bas, haut - t_bloc] for _, bas, haut in retenues])
            depart = modele.NewIntVarFromDomain(domaine, "d_" + nom)
            arrivee = modele.NewIntVarFromDomain(
                cp_model.Domain.FromIntervals(
                    [[bas + t_bloc, haut] for _, bas, haut in retenues]),
                "f_" + nom)
            modele.Add(arrivee == depart + t_bloc)
            intervalles.append(
                modele.NewIntervalVar(depart, t_bloc, arrivee, "i_" + nom))

            litteraux = []
            for jour, bas, haut in retenues:
                lit = modele.NewBoolVar("w_{}_{}".format(nom, jour))
                modele.Add(depart >= bas).OnlyEnforceIf(lit)
                modele.Add(depart + t_bloc <= haut).OnlyEnforceIf(lit)
                litteraux.append(lit)
                charge_du_jour.setdefault(
                    (tache.contexte, jour), []).append((t_bloc, lit))
            modele.AddExactlyOne(litteraux)

            starts.append(depart)
            ends.append(arrivee)
            if indice == 0:
                premiers[tache.uuid] = depart

        if starts:
            d_t = modele.NewIntVar(tot, horizon, "dt_" + tache.uuid[:8])
            f_t = modele.NewIntVar(tot, horizon, "ft_" + tache.uuid[:8])
            modele.AddMinEquality(d_t, starts)
            modele.AddMaxEquality(f_t, ends)
            debuts[tache.uuid] = d_t
            fins[tache.uuid] = f_t

    for numero, reunion in enumerate(reunions):
        r_debut = indice_creneau(t0, reunion.debut, granularite)
        r_fin = indice_creneau(t0, reunion.fin, granularite)
        if r_fin > r_debut:
            intervalles.append(modele.NewIntervalVar(
                r_debut, r_fin - r_debut, r_fin, "reunion_{}".format(numero)))

    if intervalles:
        modele.AddNoOverlap(intervalles)

    for (nom_ctx, jour), charges in charge_du_jour.items():
        capacite = cache[nom_ctx][2].get(jour)
        if capacite is not None:
            modele.Add(sum(t * lit for t, lit in charges) <= capacite)

    for tache in taches:
        if tache.uuid in debuts:
            for predecesseur in tache.depends:
                if predecesseur in fins:
                    modele.Add(debuts[tache.uuid] >= fins[predecesseur])

    # --- les hypotheses etiquetees -------------------------------------
    for tache in taches:
        if tache.fige and tache.scheduled is not None and tache.uuid in premiers:
            lit = modele.NewBoolVar("h_fige_" + tache.uuid[:8])
            fixe = indice_creneau(t0, tache.scheduled, granularite)
            modele.Add(premiers[tache.uuid] == fixe).OnlyEnforceIf(lit)
            etiquettes[lit] = Element(
                genre="figee", uuid=tache.uuid, description=tache.description,
                texte=_phrase("figee", tache))

    for uuid, limite in (limites or {}).items():
        if uuid not in fins or limite is None:
            continue
        lit = modele.NewBoolVar("h_ech_" + uuid[:8])
        modele.Add(fins[uuid] <= indice_creneau(t0, limite, granularite)) \
              .OnlyEnforceIf(lit)
        etiquettes[lit] = Element(
            genre="echeance", uuid=uuid,
            description=par_uuid[uuid].description,
            texte=_phrase("echeance", par_uuid[uuid], limite))

    for lit in etiquettes:
        modele.AddAssumption(lit)

    solveur = cp_model.CpSolver()
    solveur.parameters.max_time_in_seconds = SECONDES_MAX
    solveur.parameters.num_search_workers = 1
    solveur.parameters.random_seed = 0
    etat = solveur.Solve(modele)

    if etat in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Diagnostic(faisable=True, noyau=(), message="")

    indices = list(solveur.SufficientAssumptionsForInfeasibility())
    par_indice = {lit.Index(): element for lit, element in etiquettes.items()}
    noyau = tuple(par_indice[i] for i in indices if i in par_indice)
    # Ordre stable : par genre puis par description, pour que deux appels sur
    # la meme entree rendent exactement la meme chose.
    noyau = tuple(sorted(noyau, key=lambda e: (e.genre, e.description, e.uuid)))

    if not noyau:
        return Diagnostic(
            faisable=False, noyau=(),
            message="Le plan est infaisable, mais aucune echeance ni tache "
                    "figee n'est en cause : c'est la capacite elle-meme qui ne "
                    "suffit pas. Aucune date deplacee n'y changera rien.")

    return Diagnostic(faisable=False, noyau=noyau,
                      message=_message_du_noyau(noyau))
