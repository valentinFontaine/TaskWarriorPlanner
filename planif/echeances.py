"""Comment une echeance de PROJET descend sur les taches.

**C'est le seul endroit du depot ou cette regle est ecrite.**

## La regle, tranchee le 22/09/2026

> L'echeance d'un projet se pose comme `due` sur les taches **terminales** de ce
> projet -- celles qui n'ont aucun successeur a l'interieur du projet.

L'utilisateur a tranche : ce sont bien les terminales, pas toutes les taches du
projet. L'argument tient toujours : finir le projet avant le X, c'est finir son
dernier maillon avant le X ; les maillons anterieurs heritent de la contrainte
par les precedences, que le solveur propage deja. Poser l'echeance sur *toutes*
les taches donnerait le meme resultat sur une chaine simple, mais serait faux des
qu'une branche courte cotoie une branche longue : la branche courte se
retrouverait contrainte sans raison.

## La hierarchie des projets

Taskwarrior voit une hierarchie dans `NPD.Heliside.US.plans` ; la comparaison a
l'identique n'en voyait aucune. Sur les donnees reelles, **149 taches
entierement estimees** vivaient dans les sous-projets de `NPD.Heliside.US` et
`NPD.Heliside.MRIS` sans recevoir la moindre echeance.

Trois regles :

- **prefixe sur frontiere de point** : `NPD.Heliside.US` couvre
  `NPD.Heliside.US.plans`, jamais `NPD.Heliside.USA` ;
- **le prefixe le plus long gagne** : entre une echeance sur `NPD.Heliside` et
  une sur `NPD.Heliside.US`, les plans prennent celle de `US` ;
- **comparaison insensible a la casse**, parce que les donnees reelles portent
  `NPD.Heliside.MRE` et `NPD.heliside.MRE` comme deux projets distincts alors
  que c'est le meme. C'est un pansement sur des donnees a nettoyer, et il est
  assume comme tel.

## Le piege que la hierarchie introduit

Des qu'une echeance couvre un sous-arbre, **les terminales se calculent sur
l'arbre entier**, pas sous-projet par sous-projet. Sinon les plans de
`NPD.Heliside.US.plans` sont terminaux de *leur* sous-projet et recoivent
l'echeance finale -- alors qu'ils alimentent le montage de
`NPD.Heliside.US.montage` et doivent etre finis bien avant. C'est exactement la
panne que la regle des terminales existe pour eviter, et elle ne se voit que sur
un cas a deux sous-projets chaines.
"""
from dataclasses import replace

__all__ = ["taches_terminales", "appliquer_echeances_projet", "couvre"]


def couvre(cle, projet):
    """Vrai si `projet` est `cle` elle-meme, ou l'un de ses sous-projets.

    La frontiere est le point : `NPD.Heliside.US` couvre `NPD.Heliside.US.plans`
    mais pas `NPD.Heliside.USA`. Comparaison insensible a la casse.
    """
    if not projet or not cle:
        return False
    p, c = projet.lower(), cle.lower()
    return p == c or p.startswith(c + ".")


def _terminales(du_groupe):
    """Les uuids du groupe qui n'ont aucun successeur DANS ce groupe.

    `tache.depends` porte les **predecesseurs** (convention Taskwarrior) : le
    graphe des successeurs est son inverse.
    """
    uuids = {t.uuid for t in du_groupe}
    avec_successeur = set()
    for tache in du_groupe:
        for predecesseur in tache.depends:
            if predecesseur in uuids:
                avec_successeur.add(predecesseur)
    return {t.uuid for t in du_groupe if t.uuid not in avec_successeur}


def taches_terminales(taches, projet):
    """Les uuids des taches terminales de `projet`, sous-projets compris."""
    return _terminales([t for t in taches if couvre(projet, t.projet)])


def _par_echeance(taches, echeances_projet):
    """Repartit les taches : chacune va a la cle la PLUS LONGUE qui la couvre.

    La repartition est une partition -- une tache appartient a un seul groupe --
    et c'est ce qui donne son sens a « le prefixe le plus long gagne » : une
    tache de `.US` ne compte plus dans le groupe de `NPD.Heliside`, donc elle
    n'y est pas terminale et n'y recoit rien.
    """
    groupes = {}
    for tache in taches:
        couvrantes = [c for c in echeances_projet if couvre(c, tache.projet)]
        if not couvrantes:
            continue
        groupes.setdefault(max(couvrantes, key=len), []).append(tache)
    return groupes


def appliquer_echeances_projet(taches, echeances_projet):
    """Rend une nouvelle liste de taches, avec les echeances de projet posees.

    `echeances_projet` : dict nom_projet -> datetime (naif local, design.md §2),
    lu depuis `echeances.json` (voir `planif.config.charger_echeances`).

    Une tache qui porte **deja** un `due` propre le garde : un engagement
    explicite prime sur une echeance heritee du projet.
    """
    if not echeances_projet:
        return list(taches)

    cibles = {}
    for cle, du_groupe in _par_echeance(taches, echeances_projet).items():
        for uuid in _terminales(du_groupe):
            cibles[uuid] = echeances_projet[cle]

    return [replace(t, due=cibles[t.uuid])
            if t.uuid in cibles and t.due is None else t
            for t in taches]
