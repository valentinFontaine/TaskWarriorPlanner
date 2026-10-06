"""Pre-verifications, avant tout appel au solveur — design.md §6.

But : detecter des problemes bon marche (aucune donnee de calendrier calcule,
aucun solveur invoque) qui rendraient de toute facon un appel au solveur
INFEASIBLE, et produire un message exploitable plutot qu'un echec muet.

Ce module n'importe aucun solveur de contraintes, et n'appelle jamais
`datetime.now()` : le moment present (`maintenant`) est toujours injecte
par l'appelant, ce qui rend les verifications entierement deterministes et
testables hors ligne.

Chaque verification est exposee comme une fonction separee
(`verifier_insecables`, `verifier_cycles`, `verifier_dues`,
`verifier_externes_sans_estimated`, `verifier_sans_contexte`) : c'est plus
lisible que de tout empiler dans une seule fonction, et ca permet a un autre
lot de n'en reutiliser qu'une partie si besoin. `pre_verifications` les
enchaine dans l'ordre de `CODES`, qui est aussi l'ordre de rendu retenu :
a code egal, les anomalies sont ensuite triees par leur premier uuid, ce qui
rend deux appels sur la meme entree strictement identiques (teste).

Convention sur les `datetime` naifs (design.md §2) : tout naif est suppose
deja en heure locale — pas en UTC. La conversion depuis l'UTC aware de
Taskwarrior se fait a la frontiere, dans
`planif/taskwarrior.py::vers_local_naif`, importee telle quelle ici.
"""
from dataclasses import dataclass
from datetime import timedelta

from planif.taskwarrior import vers_local_naif

__all__ = ["Anomalie", "CODES", "pre_verifications",
           "verifier_insecables", "verifier_cycles", "verifier_dues",
           "verifier_externes_sans_estimated", "verifier_sans_estimated",
           "verifier_sans_contexte"]

CODES = (
    "insecable-trop-longue",
    "cycle-dependances",
    "due-depassee",
    "externe-sans-estimated",
    "sans-estimated",
    "sans-contexte",
)


@dataclass(frozen=True)
class Anomalie:
    """Une anomalie detectee avant tout appel au solveur."""

    code: str
    message: str
    uuids: tuple


def _fmt_duree(duree):
    """Formate un timedelta en « X h » ou « X h MM », en francais.

    Pas de round trompeur : on tronque a la minute (une duree Taskwarrior est
    deja exprimee en minutes/heures rondes dans nos donnees).
    """
    total_minutes = int(duree.total_seconds() // 60)
    heures, minutes = divmod(total_minutes, 60)
    if minutes:
        return "{} h {:02d}".format(heures, minutes)
    return "{} h".format(heures)


def _plus_longue_plage(contexte):
    """La plus longue plage contigue de la grille, tous jours confondus.

    Une tache insecable tient en un seul bloc : elle ne peut donc pas
    enjamber une coupure de la grille (typiquement la pause du midi). C'est
    pour ca qu'on compare a la plage contigue la plus longue, et non a la
    capacite totale (utile) d'une journee.
    """
    max_duree = timedelta(0)
    for creneaux in contexte.grille.values():
        for creneau in creneaux:
            if creneau.duree > max_duree:
                max_duree = creneau.duree
    return max_duree


def _capacite_utile_max(contexte):
    """Capacite utile maximale d'une journee de ce contexte.

    Capacite utile d'un jour = total de la grille de ce jour moins la marge
    quotidienne du contexte, bornee a zero (design.md §6, phrase « max 6 h
    utiles » de l'exemple : c'est cette valeur-la, pas la plage contigue).
    """
    max_capacite = timedelta(0)
    for creneaux in contexte.grille.values():
        total_jour = sum((c.duree for c in creneaux), timedelta(0))
        capacite = total_jour - contexte.marge_jour
        if capacite < timedelta(0):
            capacite = timedelta(0)
        if capacite > max_capacite:
            max_capacite = capacite
    return max_capacite


def verifier_insecables(taches, contextes):
    """Taches +nosplit plus longues que la plus grande plage disponible.

    Une tache sans contexte attribuable n'est pas jugee ici : elle est deja
    signalee par `verifier_sans_contexte`, et on ne peut de toute facon pas
    calculer de plage sans contexte.
    """
    anomalies = []
    for tache in taches:
        if not tache.insecable or tache.estimated is None:
            continue
        contexte = contextes.get(tache.contexte)
        if contexte is None:
            continue
        plage_max = _plus_longue_plage(contexte)
        if tache.estimated > plage_max:
            capacite = _capacite_utile_max(contexte)
            message = (
                "La tâche « {desc} » ({duree} indivisible) ne tient dans "
                "aucune plage contiguë de vos journées en contexte « {ctx} » "
                "(plus grande plage disponible : {plage}, pour {cap} utiles "
                "au maximum par jour) — découpez la tâche, déclarez une "
                "journée exceptionnelle, ou rognez la marge ce jour-là."
            ).format(
                desc=tache.description,
                duree=_fmt_duree(tache.estimated),
                ctx=contexte.nom,
                plage=_fmt_duree(plage_max),
                cap=_fmt_duree(capacite),
            )
            anomalies.append(Anomalie("insecable-trop-longue", message,
                                       (tache.uuid,)))
    return anomalies


def _detecter_cycles(taches):
    """Detecte les cycles du graphe de precedence (tache -> predecesseurs).

    `tache.depends` contient des uuids de PREDECESSEURS. On ignore les uuids
    qui ne correspondent a aucune tache de la liste passee (dependance vers
    une tache deja terminee, donc absente du lot a planifier : ce n'est pas
    un cycle).

    Implementation : parcours en profondeur avec trois couleurs (blanc /
    gris / noir) classique pour la detection de cycle dans un graphe
    oriente. Quand on retombe sur un noeud gris (encore sur la pile
    d'appel), on a trouve un cycle : on le decoupe dans la pile courante,
    du noeud gris jusqu'au sommet.
    """
    par_uuid = {t.uuid: t for t in taches}
    couleur = {}
    pile = []
    cycles = []

    def dfs(uuid_tache):
        couleur[uuid_tache] = 1
        pile.append(uuid_tache)
        for pred in par_uuid[uuid_tache].depends:
            if pred not in par_uuid:
                continue
            c = couleur.get(pred, 0)
            if c == 0:
                dfs(pred)
            elif c == 1:
                idx = pile.index(pred)
                cycles.append(tuple(pile[idx:]))
        pile.pop()
        couleur[uuid_tache] = 2

    for tache in taches:
        if couleur.get(tache.uuid, 0) == 0:
            dfs(tache.uuid)
    return cycles


def verifier_cycles(taches):
    """Une Anomalie par cycle de dependances trouve, nommant le cycle."""
    par_uuid = {t.uuid: t for t in taches}
    anomalies = []
    for cycle in _detecter_cycles(taches):
        descriptions = [par_uuid[u].description for u in cycle]
        descriptions.append(descriptions[0])
        message = "Cycle de dépendances : {}.".format(
            " → ".join(descriptions))
        anomalies.append(Anomalie("cycle-dependances", message, cycle))
    return anomalies


def _rendre_comparables(due, maintenant):
    """Rend `due` et `maintenant` comparables meme si l'un est aware et
    l'autre naif.

    Convention du depot (design.md §2) : un naif est toujours de l'heure
    locale. On ramene donc les deux via `vers_local_naif`, qui laisse un
    naif tel quel et convertit un aware vers le local avant de retirer son
    `tzinfo` — jamais l'inverse (un naif n'est plus suppose etre de l'UTC).
    """
    return vers_local_naif(due), vers_local_naif(maintenant)


def verifier_dues(taches, maintenant):
    """Taches dont `due` est strictement anterieure a `maintenant`."""
    en_retard = []
    for tache in taches:
        if tache.due is None:
            continue
        due, maint = _rendre_comparables(tache.due, maintenant)
        if due < maint:
            en_retard.append(tache)
    if not en_retard:
        return []
    lignes = ", ".join(
        "« {} » (due {})".format(t.description, t.due.isoformat())
        for t in en_retard
    )
    message = "Échéance déjà dépassée pour : {}.".format(lignes)
    return [Anomalie("due-depassee", message,
                      tuple(t.uuid for t in en_retard))]


def verifier_externes_sans_estimated(taches):
    """Taches +external sans `estimated` : delai fournisseur non renseigne."""
    concernees = [t for t in taches if t.externe and t.estimated is None]
    if not concernees:
        return []
    lignes = ", ".join("« {} »".format(t.description) for t in concernees)
    message = "délai fournisseur non renseigné pour : {}.".format(lignes)
    return [Anomalie("externe-sans-estimated", message,
                      tuple(t.uuid for t in concernees))]


def verifier_sans_estimated(taches):
    """Taches ordinaires sans `estimated` : le solveur ne les voit jamais.

    `planif/solveur.py` les saute (`if tache.estimated is None: continue`) en
    annoncant qu'elles sont « signalees par les pre-verifications ». Elles ne
    l'etaient pas : seul le cas `+external` avait sa verification. Une tache
    ordinaire sans duree disparaissait donc du plan sans un mot, et sur une
    base ou la plupart des taches n'ont pas d'estimation, on pouvait regarder
    un calendrier vide en croyant que tout allait bien.

    Les `+external` restent a `verifier_externes_sans_estimated`, qui dit mieux
    les choses : ce n'est pas « une charge inconnue » mais « un delai
    fournisseur non renseigne ». Deux problemes differents, un seul message
    par tache.
    """
    concernees = [t for t in taches if not t.externe and t.estimated is None]
    if not concernees:
        return []
    lignes = ", ".join("« {} »".format(t.description) for t in concernees)
    message = ("Durée estimée absente : ces tâches sont absentes du plan, le "
               "solveur ne les voit pas — {}.".format(lignes))
    return [Anomalie("sans-estimated", message,
                      tuple(t.uuid for t in concernees))]


def verifier_sans_contexte(taches, contextes):
    """Taches sans contexte attribuable (contexte absent ou inconnu).

    Rappel de la consigne du projet : une telle tache est sortie du modele
    et listee ici, c'est le seul role de cette verification.
    """
    concernees = [t for t in taches
                  if t.contexte is None or t.contexte not in contextes]
    if not concernees:
        return []
    lignes = ", ".join("« {} »".format(t.description) for t in concernees)
    message = "Aucun contexte attribuable pour : {}.".format(lignes)
    return [Anomalie("sans-contexte", message,
                      tuple(t.uuid for t in concernees))]


def pre_verifications(taches, contextes, maintenant):
    """Rend la liste des `Anomalie` detectees, vide si rien a signaler.

    Ordre de rendu, stable et deterministe : celui de `CODES`, puis, a code
    egal (seul `cycle-dependances` peut en produire plusieurs), par premier
    uuid de l'anomalie.
    """
    par_code = {
        "insecable-trop-longue": verifier_insecables(taches, contextes),
        "cycle-dependances": verifier_cycles(taches),
        "due-depassee": verifier_dues(taches, maintenant),
        "externe-sans-estimated": verifier_externes_sans_estimated(taches),
        "sans-estimated": verifier_sans_estimated(taches),
        "sans-contexte": verifier_sans_contexte(taches, contextes),
    }
    resultat = []
    for code in CODES:
        anomalies_code = sorted(par_code[code], key=lambda a: a.uuids[0])
        resultat.extend(anomalies_code)
    return resultat
