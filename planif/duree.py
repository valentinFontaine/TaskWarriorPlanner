"""Lecture des durees.

L'UDA `estTime` de Taskwarrior accepte plusieurs ecritures. AGENTS.md §5 en releve
une qui est *rejetee* par Taskwarrior lui-meme (`1h30`, code retour 2) : on la rejette
ici aussi, plutot que de deviner ce que l'utilisateur voulait dire.
"""
import re
from datetime import timedelta

__all__ = ["parse_duree", "ParseDureeErreur"]


class ParseDureeErreur(ValueError):
    """Duree illisible. On ne devine jamais : on refuse et on nomme la valeur."""


# ISO-8601 : P[nW][nD][T[nH][nM][nS]]
_ISO = re.compile(
    r"^P(?!$)(?:(?P<semaines>\d+(?:\.\d+)?)W)?(?:(?P<jours>\d+(?:\.\d+)?)D)?"
    r"(?:T(?!$)(?:(?P<heures>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<secondes>\d+(?:\.\d+)?)S)?)?$",
    re.IGNORECASE,
)

# forme courte Taskwarrior : un nombre suivi d'une unite, et rien d'autre
_COURT = re.compile(r"^(?P<valeur>\d+(?:\.\d+)?)\s*(?P<unite>[a-z]+)$", re.IGNORECASE)

_UNITES = {
    "min": "minutes", "mins": "minutes", "minute": "minutes", "minutes": "minutes",
    "h": "hours", "hr": "hours", "hrs": "hours", "hour": "hours", "hours": "hours",
    "d": "days", "day": "days", "days": "days",
    "w": "weeks", "wk": "weeks", "wks": "weeks", "week": "weeks", "weeks": "weeks",
    "s": "seconds", "sec": "seconds", "secs": "seconds",
    "second": "seconds", "seconds": "seconds",
}


def parse_duree(texte):
    """Rend un `timedelta`. Leve `ParseDureeErreur` si la forme n'est pas reconnue."""
    if texte is None:
        raise ParseDureeErreur("duree absente")
    brut = str(texte).strip()
    if not brut:
        raise ParseDureeErreur("duree vide")

    iso = _ISO.match(brut)
    if iso and any(iso.groupdict().values()):
        p = {k: float(v) for k, v in iso.groupdict().items() if v is not None}
        return timedelta(
            weeks=p.get("semaines", 0.0),
            days=p.get("jours", 0.0),
            hours=p.get("heures", 0.0),
            minutes=p.get("minutes", 0.0),
            seconds=p.get("secondes", 0.0),
        )

    court = _COURT.match(brut)
    if court:
        unite = _UNITES.get(court.group("unite").lower())
        if unite is not None:
            return timedelta(**{unite: float(court.group("valeur"))})

    raise ParseDureeErreur(
        "duree illisible : {!r}. Formes acceptees : PT1H30M, 90min, 1.5h, 28d, P28D. "
        "Taskwarrior rejette lui-meme `1h30`.".format(brut)
    )
