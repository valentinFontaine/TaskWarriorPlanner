"""Tampon de securite et derivation des echeances effectives — design.md §4.

Regle (design.md §4, proposal.md decision 8) :

    echeance_effective(due) :
        t = due - 24 h
        reculer jusqu'a la fin du dernier jour ouvre strictement anterieur a t

Le tampon est applique UNE SEULE FOIS, sur les `due` reelles des taches. Les
dates derivees le long du graphe de dependances (limite d'une tache sans `due`
propre, heritee de ses successeurs) ne sont PAS re-tamponnees : sinon le
tampon se cumulerait le long d'une chaine de taches et une chaine de cinq
taches accumulerait des jours ouvres de rembourrage invisible.

Un jour ouvre est un jour dont la grille du contexte est non vide
(`Contexte.est_ouvre`). Aucun calendrier de jours feries n'existe dans le
depot : les feries sont donc ignores ici, comme deja signale dans
`planif/modele.py` (`Contexte.est_ouvre`) et dans RAPPORT-NUIT.md. Ce n'est
pas invente pour ce lot, c'est une limite deja actee du depot.

Convention sur les `datetime` naifs (design.md §2) : tout naif est suppose
deja en heure locale. La conversion depuis l'UTC aware de Taskwarrior se
fait a la frontiere, dans `planif/taskwarrior.py::vers_local_naif`, importee
telle quelle ici plutot que redefinie.
"""
from datetime import datetime, timedelta

from planif.taskwarrior import vers_local_naif

__all__ = ["CycleDependances", "echeance_effective", "limites_effectives",
           "separer_passe1_passe2"]

# Tampon fixe du cahier des charges : 24 heures avant l'echeance reelle.
TAMPON = timedelta(hours=24)


class CycleDependances(Exception):
    """Levee quand le graphe des successeurs contient un cycle.

    Le diagnostic complet des cycles (chaine complete, etc.) est le travail
    d'un autre lot : ici on se contente de ne pas boucler a l'infini et de
    signaler les uuids en cause.
    """


def echeance_effective(due, contexte, tampon=TAMPON):
    """design.md §4 : applique le tampon de securite a une echeance reelle.

    `due` : datetime naif en heure locale (ou aware, auquel cas il est
    converti en heure locale naive avant calcul, voir `vers_local_naif`).

    Avec tampon (comportement historique, decision 8) : rend la fin du dernier
    jour ouvre strictement anterieur a `due - tampon`.

    Avec `tampon=timedelta(0)` : rend la date VRAIE, simplement ramenee au
    dernier instant ouvrable qui ne la depasse pas. C'est le regime de la passe
    1 depuis que l'utilisateur a tranche : une `due` calculee doit dire quand il
    est reellement trop tard, pas quand on aimerait avoir fini. Un coussin
    melange a une limite donne une limite fausse, et personne ne peut plus dire
    de combien.
    """
    due = vers_local_naif(due)

    if tampon:
        jour = (due - tampon).date() - timedelta(days=1)
    else:
        jour = due.date()

    while not contexte.est_ouvre(jour):
        jour -= timedelta(days=1)

    fin_min = contexte.fin_de_journee(jour)
    fin = datetime(jour.year, jour.month, jour.day) + timedelta(minutes=fin_min)
    return fin if tampon else min(due, fin)


def _contexte_de(tache, contextes):
    """Rend le `Contexte` d'une tache. Choix : si `tache.contexte` ne
    correspond a aucune entree de `contextes`, ou est None, on retombe sur le
    contexte `pro` s'il existe, sinon sur le premier contexte disponible.
    Ce point n'est pas precise par le cahier des charges pour ce lot (les
    exemples de test fournissent toujours un contexte explicite) ; c'est une
    interpretation a signaler.
    """
    if tache.contexte in contextes:
        return contextes[tache.contexte]
    if "pro" in contextes:
        return contextes["pro"]
    return next(iter(contextes.values()))


def limites_effectives(taches, contextes, tampon=TAMPON):
    """Rend uuid -> datetime (ou None) : la date de fin au plus tard de chaque tache.

    - Une tache qui porte un `due` reel recoit `echeance_effective(due)`.
    - Une tache sans `due` herite de la limite de ses successeurs, SANS
      re-tamponner : limite(i) = min sur les successeurs j de limite(j).
    - Quand une tache a les deux (un `due` propre ET des successeurs dates),
      on prend le min des deux.
    - Une tache sans `due` et sans successeur date recoit None.

    `tache.depends` contient les uuids des PREDECESSEURS de la tache (ce
    dont elle depend). Le graphe des successeurs est donc l'inverse de
    `depends` : si B.depends contient A.uuid, alors A precede B, et B est un
    successeur de A.

    Leve `CycleDependances` si le graphe des successeurs contient un cycle
    (evite une recursion infinie).
    """
    par_uuid = {t.uuid: t for t in taches}

    successeurs = {uuid: [] for uuid in par_uuid}
    for t in taches:
        for predecesseur in t.depends:
            if predecesseur in successeurs:
                successeurs[predecesseur].append(t.uuid)

    resultats = {}
    en_cours = set()

    def limite_de(uuid):
        if uuid in resultats:
            return resultats[uuid]
        if uuid in en_cours:
            raise CycleDependances(
                "cycle de dependances detecte impliquant : {}".format(uuid)
            )
        en_cours.add(uuid)

        tache = par_uuid[uuid]
        candidats = []

        if tache.due is not None:
            candidats.append(
                echeance_effective(tache.due, _contexte_de(tache, contextes),
                                   tampon)
            )

        for succ in successeurs[uuid]:
            limite_succ = limite_de(succ)
            if limite_succ is not None:
                candidats.append(limite_succ)

        resultat = min(candidats) if candidats else None

        en_cours.discard(uuid)
        resultats[uuid] = resultat
        return resultat

    for uuid in par_uuid:
        limite_de(uuid)

    return resultats


def separer_passe1_passe2(taches):
    """Rend `(passe1, passe2)` : la passe 1 est les taches DATEES UNION leurs
    predecesseurs transitifs (`tache.depends`, uuids presents dans `taches`).

    Le defaut corrige ici : ne mettre en passe 1 que `t.due is not None`
    laisse un predecesseur non date d'une tache datee partir en passe 2, qui
    ne le contraint jamais a finir avant son successeur (`planif/solveur.py`
    pose la precedence uniquement entre candidates d'une meme passe). Pire,
    une tache `+externe` non datee est en plus explicitement ecartee de la
    passe 2 et n'apparaissait alors dans aucune des deux.

    En remontant `depends` transitivement, tout predecesseur d'une tache
    datee est planifie COMME une tache datee : `limites_effectives` (appelee
    par `resoudre` quand on ne lui fournit pas `limites`) sait deja lui
    heriter une limite depuis ses successeurs, il suffit de le lui donner en
    entree.

    Une tache non datee sans successeur date (direct ou transitif) reste en
    passe 2, en regime opportuniste : ce n'est pas ce defaut-la qui est
    corrige.
    """
    par_uuid = {t.uuid: t for t in taches}
    retenus = set()
    pile = [t.uuid for t in taches if t.due is not None]
    while pile:
        uuid = pile.pop()
        if uuid in retenus:
            continue
        retenus.add(uuid)
        tache = par_uuid.get(uuid)
        if tache is None:
            continue
        for predecesseur in tache.depends:
            if predecesseur in par_uuid and predecesseur not in retenus:
                pile.append(predecesseur)

    passe1 = [t for t in taches if t.uuid in retenus]
    passe2 = [t for t in taches if t.uuid not in retenus]
    return passe1, passe2
