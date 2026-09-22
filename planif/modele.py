"""Modele de donnees — design.md §2.

Aucun UDA nouveau : les marqueurs passent par des tags (proposal.md decision 14).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

__all__ = ["Marqueur", "Creneau", "Contexte", "Reunion", "Projet", "Tache",
           "JOURS", "nom_jour"]

# 0 = lundi, conformement a datetime.date.weekday()
JOURS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
         "Saturday", "Sunday")


def nom_jour(indice):
    return JOURS[indice]


class Marqueur(str, Enum):
    """design.md §2 — marqueurs, par tags."""

    EXTERNE = "externe"      # pas realisee par l'utilisateur : hors non-chevauchement
    INSECABLE = "insecable"  # un seul bloc
    FIGE = "fige"            # debut impose (scheduled courant)
    ASAP = "asap"            # exception au « au plus tard »


@dataclass(frozen=True, order=True)
class Creneau:
    """Une plage d'une journee, en minutes depuis minuit local. Fin exclue."""

    debut_min: int
    fin_min: int

    def __post_init__(self):
        if self.fin_min <= self.debut_min:
            raise ValueError("creneau vide ou inverse : {}".format(self))

    @property
    def duree(self):
        return timedelta(minutes=self.fin_min - self.debut_min)

    def __str__(self):
        def hm(m):
            return "{:02d}:{:02d}".format(m // 60, m % 60)
        return "{}-{}".format(hm(self.debut_min), hm(self.fin_min))


@dataclass(frozen=True)
class Contexte:
    """Un contexte Taskwarrior + sa configuration de grille (design.md §2)."""

    nom: str
    contexte_tw: str
    bloc_min: timedelta
    marge_jour: timedelta
    # cle = weekday() (0 = lundi), valeur = creneaux de la grille, tries
    grille: dict = field(default_factory=dict)

    def creneaux(self, jour):
        """Creneaux bruts de la grille pour une `date` donnee (avant reunions et marge)."""
        return tuple(self.grille.get(jour.weekday(), ()))

    def est_ouvre(self, jour):
        """Un jour ouvre est un jour dont la grille est non vide.

        Aucun calendrier de jours feries n'existe dans le depot : les feries sont
        donc ignores, et c'est signale dans RAPPORT-NUIT.md.
        """
        return bool(self.creneaux(jour))

    def fin_de_journee(self, jour):
        """Minute de fin du dernier creneau de la grille, ou None si jour non ouvre."""
        cr = self.creneaux(jour)
        return cr[-1].fin_min if cr else None


@dataclass(frozen=True)
class Reunion:
    """Intervalle fixe issu d'iCal. Entre dans le non-chevauchement (design.md §2)."""

    titre: str
    debut: datetime
    fin: datetime


@dataclass(frozen=True)
class Projet:
    nom: str
    echeance: datetime = None


@dataclass(frozen=True)
class Tache:
    """Tache lue depuis Taskwarrior (design.md §2)."""

    uuid: str
    description: str
    projet: str = None
    estimated: timedelta = None
    due: datetime = None
    #: Valeur de `due` que la passe 1 a ecrite au run precedent (UDA
    #: `duePlanif`). On stocke la DATE et non un drapeau : un drapeau ne
    #: survit pas a un `task X modify due:...` fait hors de l'outil, alors
    #: qu'une valeur, si. `due == due_planif` veut dire « cette echeance est
    #: notre propre sortie » ; toute divergence veut dire qu'un humain est
    #: passe apres nous, et son engagement prime.
    due_planif: datetime = None
    scheduled: datetime = None
    depends: tuple = ()
    tags: tuple = ()
    urgency: float = 0.0
    contexte: str = None

    @property
    def marqueurs(self):
        connus = {m.value: m for m in Marqueur}
        return frozenset(connus[t] for t in self.tags if t in connus)

    @property
    def externe(self):
        return Marqueur.EXTERNE in self.marqueurs

    @property
    def insecable(self):
        return Marqueur.INSECABLE in self.marqueurs

    @property
    def fige(self):
        return Marqueur.FIGE in self.marqueurs

    @property
    def asap(self):
        return Marqueur.ASAP in self.marqueurs
