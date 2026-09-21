"""Lecture de Taskwarrior.

Deux pieges d'AGENTS.md §5 sont traites ici :
- `encoding='utf-8'` explicite sur `subprocess.run`, sinon les accents se corrompent
  sous Windows ;
- `rc.bulk=0` sur toute modification en masse (ecriture : lot 7, pas encore ecrit,
  mais la constante est posee ici pour qu'on ne l'oublie pas).

Ce module ne pose jamais `TASKRC` lui-meme : c'est a l'appelant de fournir un `env`
isole. Les tests passent systematiquement une base jetable.
"""
import json
import subprocess
from datetime import datetime, timedelta, timezone

from planif.duree import ParseDureeErreur, parse_duree
from planif.modele import Tache

__all__ = ["exporter", "charger_taches", "RC_MASSE"]

# AGENTS.md §5 : rc.confirmation=off ne couvre pas la confirmation de lot.
RC_MASSE = ("rc.confirmation=off", "rc.bulk=0")

_FORMAT_TW = "%Y%m%dT%H%M%SZ"


def _parse_date(valeur):
    if not valeur:
        return None
    return datetime.strptime(valeur, _FORMAT_TW).replace(tzinfo=timezone.utc)


def exporter(filtre=(), env=None):
    """Rend la liste brute de dicts rendue par `task export`.

    `encoding='utf-8'` est explicite : c'est ce qui fait tenir les accents.
    """
    res = subprocess.run(
        ["task", *filtre, "export"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError("task export a echoue ({}) : {}".format(
            res.returncode, res.stderr.strip()))
    sortie = res.stdout.strip()
    if not sortie:
        return []
    return json.loads(sortie)


def _contexte_de(tags, contextes_connus):
    """Le contexte d'une tache est le tag qui porte un nom de contexte configure.

    On ne reinterprete pas le filtre du contexte Taskwarrior (design.md §2) ; quand
    la configuration ne donne rien, on rend None et la tache sera listee par les
    pre-verifications comme « sans contexte attribuable ».
    """
    for tag in tags:
        if tag in contextes_connus:
            return tag
    return None


def charger_taches(filtre=("status:pending",), env=None, contextes_connus=()):
    """Traduit `task export` en objets `Tache`."""
    taches = []
    for brut in exporter(filtre, env=env):
        estimated = None
        est = brut.get("estTime")
        if est:
            try:
                estimated = parse_duree(est)
            except ParseDureeErreur:
                estimated = None  # signale par les pre-verifications, pas devine ici
        tags = tuple(brut.get("tags", ()))
        taches.append(Tache(
            uuid=brut["uuid"],
            description=brut.get("description", ""),
            projet=brut.get("project"),
            estimated=estimated,
            due=_parse_date(brut.get("due")),
            scheduled=_parse_date(brut.get("scheduled")),
            depends=tuple(brut.get("depends", ())),
            tags=tags,
            urgency=float(brut.get("urgency", 0.0)),
            contexte=_contexte_de(tags, set(contextes_connus)),
        ))
    return taches
