"""Calendrier disponible — design.md §3.

    disponibilite(contexte, jour) = grille(contexte, jour) - reunions(jour) - marge_jour(contexte)

Granularite `g` (design.md §1) : toutes les positions et durees exposees par ce
module sont des entiers en nombre de creneaux, jamais des flottants d'heures.

Convention temporelle : `t0`, `jour` et les datetimes de `Reunion` sont tous
**naifs** et exprimes en heure locale (pas de fuseau horaire, pas d'UTC). C'est
l'appelant qui garantit la coherence des fuseaux avant d'appeler ce module.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

__all__ = ["Plage", "Disponibilite", "indice_creneau", "instant_creneau",
           "disponibilite", "plus_grande_plage"]


@dataclass(frozen=True)
class Plage:
    """Une fenetre contigue de creneaux libres, en indices absolus depuis t0."""

    debut: int   # inclus
    fin: int     # exclu

    @property
    def longueur(self):
        return self.fin - self.debut


@dataclass(frozen=True)
class Disponibilite:
    """Disponibilite d'un contexte pour un jour donne."""

    jour: date
    plages: tuple            # tuple[Plage, ...], triees, disjointes, non vides
    capacite: int            # nombre de creneaux reellement planifiables ce jour-la


def _diviser_plancher(delta, granularite):
    """Division entiere plancher de deux timedelta (arrondi vers -infini)."""
    return delta // granularite


def _diviser_plafond(delta, granularite):
    """Division entiere plafond de deux timedelta (arrondi vers +infini)."""
    quotient, reste = divmod(delta, granularite)
    return quotient if reste == timedelta(0) else quotient + 1


def indice_creneau(t0, instant, granularite):
    """Indice du creneau contenant `instant`. Division entiere plancher."""
    return _diviser_plancher(instant - t0, granularite)


def instant_creneau(t0, indice, granularite):
    """Instant de debut du creneau d'indice donne."""
    return t0 + indice * granularite


def disponibilite(contexte, jour, t0, granularite, reunions=()):
    """Calcule la disponibilite d'un contexte pour un jour donne (design.md §3).

    Etapes :
    1. La grille brute du jour est convertie en indices de creneaux absolus
       (depuis `t0`), en retrecissant vers l'interieur : debut arrondi au
       creneau superieur, fin arrondie au creneau inferieur. Une plage qui
       devient vide ou negative est supprimee.
    2. Chaque reunion occupe entierement tout creneau qu'elle touche, meme
       partiellement (regle de prudence) : ses bornes sont donc etendues vers
       l'exterieur (debut plancher, fin plafond) avant soustraction.
    3. La marge du contexte est un volume, retire uniquement de `capacite` :
       les `plages` rendues ne sont jamais amputees par la marge.
    """
    creneaux_grille = contexte.creneaux(jour)
    if not creneaux_grille:
        return Disponibilite(jour=jour, plages=(), capacite=0)

    minuit_jour = datetime.combine(jour, time.min)

    # 1. grille brute -> plages d'indices alignees sur la granularite
    plages_brutes = []
    for creneau in creneaux_grille:
        debut_dt = minuit_jour + timedelta(minutes=creneau.debut_min)
        fin_dt = minuit_jour + timedelta(minutes=creneau.fin_min)
        debut_idx = _diviser_plafond(debut_dt - t0, granularite)
        fin_idx = _diviser_plancher(fin_dt - t0, granularite)
        if fin_idx > debut_idx:
            plages_brutes.append((debut_idx, fin_idx))

    # 2. creneaux occupes par les reunions (bornes etendues vers l'exterieur)
    occupes = set()
    for reunion in reunions:
        debut_idx = _diviser_plancher(reunion.debut - t0, granularite)
        fin_idx = _diviser_plafond(reunion.fin - t0, granularite)
        occupes.update(range(debut_idx, fin_idx))

    # 3. soustraction des creneaux occupes, plage brute par plage brute
    plages_finales = []
    for debut_idx, fin_idx in plages_brutes:
        debut_courant = None
        for indice in range(debut_idx, fin_idx):
            if indice in occupes:
                if debut_courant is not None:
                    plages_finales.append(Plage(debut_courant, indice))
                    debut_courant = None
            elif debut_courant is None:
                debut_courant = indice
        if debut_courant is not None:
            plages_finales.append(Plage(debut_courant, fin_idx))

    plages_finales.sort(key=lambda plage: plage.debut)

    total_creneaux = sum(plage.longueur for plage in plages_finales)
    marge_creneaux = _diviser_plafond(contexte.marge_jour, granularite)
    capacite = max(0, total_creneaux - marge_creneaux)

    return Disponibilite(jour=jour, plages=tuple(plages_finales), capacite=capacite)


def plus_grande_plage(contexte, jour, t0, granularite, reunions=()):
    """Longueur, en creneaux, de la plus longue plage libre du jour. 0 si aucune."""
    disp = disponibilite(contexte, jour, t0, granularite, reunions)
    return max((plage.longueur for plage in disp.plages), default=0)
