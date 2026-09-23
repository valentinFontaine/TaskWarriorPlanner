"""Sortie du plan — design.md §7, lot 7.

Deux destinations, pour deux usages :

- **un fichier JSON**, qui est le **contrat avec `../WebTaskManager`**. L'interface
  web ne connait ni `ortools`, ni le modele de contraintes, ni les grilles : elle
  lit ce fichier et rien d'autre. Le format est documente dans `design.md` §7.
- **`scheduled:` dans Taskwarrior**, pour la ligne de commande et pour que
  Syncthing porte le resultat jusqu'au telephone.

Les deux ecritures sont **idempotentes** : relancer sans changement d'entree
n'ecrit rien. Ce n'est pas une coquetterie — sans ca, chaque execution
toucherait les 277 taches de la base et Syncthing repliquerait le bruit sur
trois machines.

## La frontiere des dates, dans l'autre sens

`design.md` §2 : a l'interieur du modele, tout `datetime` naif est en **heure
locale**. `planif/taskwarrior.py` est la frontiere en **lecture** (UTC de
Taskwarrior -> local naif). Ce module est la frontiere en **ecriture** : il
reconvertit le local naif vers l'UTC compact que Taskwarrior attend
(`%Y%m%dT%H%M%SZ`).

Verifie sur base jetable (Taskwarrior 3.5.0), et non suppose : les deux formes
`scheduled:2026-11-20T14:00:00` (ISO locale) et `scheduled:20261120T130000Z`
(UTC compacte) sont acceptees et ressortent toutes deux a `20261120T130000Z`.
On retient la forme **UTC explicite** : elle ne depend pas de la facon dont
Taskwarrior interprete une date sans fuseau.

## Les pieges d'AGENTS.md §5 traites ici

- `rc.confirmation=off` **ne couvre pas** la confirmation de lot : Taskwarrior
  redemande alors tache par tache, ne lit rien sur une entree non interactive,
  et annonce « Deleted 0 tasks » avec un **code de retour nul**. Toute
  modification passe donc par `RC_MASSE`, qui ajoute `rc.bulk=0`.
- `encoding='utf-8'` explicite sur `subprocess.run`, sinon les accents se
  corrompent sous Windows.
- On designe une tache par son **UUID**, jamais par un filtre par motif, qui ne
  matche pas toujours.
"""
import json
import subprocess
from datetime import timezone
from pathlib import Path

from planif.calendrier import instant_creneau
from planif.dues import UDA as UDA_DUE_PLANIF
from planif.dues import dues_calculees, est_calculee
from planif.taskwarrior import RC_MASSE, exporter

__all__ = ["VERSION_FORMAT", "plan_en_dict", "ecrire_json", "ecrire_scheduled",
           "ecrire_due"]

#: Version du contrat JSON. A incrementer des que le format change de facon
#: incompatible, pour que `../WebTaskManager` puisse refuser ce qu'il ne sait
#: pas lire plutot que de l'interpreter de travers.
VERSION_FORMAT = 1

_FORMAT_TW = "%Y%m%dT%H%M%SZ"


def _iso(t0, indice, granularite):
    return instant_creneau(t0, indice, granularite).isoformat()


def _vers_utc_taskwarrior(instant_local_naif):
    """Local naif -> chaine UTC compacte attendue par Taskwarrior.

    C'est la frontiere en ecriture, symetrique de
    `planif/taskwarrior.py::vers_local_naif`.
    """
    return instant_local_naif.astimezone(timezone.utc).strftime(_FORMAT_TW)


def plan_en_dict(plan, taches=None):
    """Le plan sous forme de dict serialisable. C'est le contrat avec l'interface web.

    `taches` est optionnel : quand il est fourni, `description` et `projet` sont
    ajoutes pour que le fichier soit lisible par un humain. Quand il ne l'est
    pas, ces champs sont simplement **absents** — on n'invente jamais une
    description.

    Chaque bloc porte ses trois drapeaux explicitement (`externe`, `agrege`,
    `opportuniste`) : un consommateur ne doit jamais avoir a les recalculer.
    Il porte en plus une `precision` :

    - `"heure"` : le bloc est place au creneau, l'heure est un engagement ;
    - `"jour"`  : le bloc vient du regime agrege (au-dela de l'horizon
      detaille). **Seule la journee est garantie.** Deux blocs agreges d'une
      meme journee peuvent meme se chevaucher dans cette sortie. L'interface ne
      doit pas les afficher comme des rendez-vous a l'heure pres.

    `precision` est redondante avec `agrege`, et c'est voulu : le drapeau dit
    *d'ou vient* le bloc, la precision dit *ce qu'on peut en faire*. C'est la
    seconde qui interesse un afficheur, et la rendre explicite evite qu'il
    invente la regle de conversion.

    Chaque tache porte aussi une `due` : c'est exactement ce que `ecrire_due`
    ecrirait, sans recalcul, pour que Valider (E4, `--appliquer`) applique le
    plan affiche et rien d'autre. Une tache placee par la **passe 1** (au moins
    un bloc non opportuniste) porte la valeur de
    `planif.dues.dues_calculees` -- la fin de son dernier bloc -- en ISO local
    naif ; une tache placee uniquement par la **passe 2** (tous ses blocs
    opportunistes) porte `None`. Le champ est toujours present, que `taches`
    soit fourni ou non : il ne depend que du plan.
    """
    par_uuid = {t.uuid: t for t in (taches or [])}
    taches_json = {}
    dues = dues_calculees(plan, taches or [])

    for bloc in plan.blocs:
        entree = taches_json.setdefault(bloc.uuid, {"blocs": []})
        entree["blocs"].append({
            "indice": bloc.indice,
            "debut": _iso(plan.t0, bloc.debut, plan.granularite),
            "fin": _iso(plan.t0, bloc.fin, plan.granularite),
            "externe": bool(bloc.externe),
            "agrege": bool(bloc.agrege),
            "opportuniste": bool(bloc.opportuniste),
            "precision": "jour" if bloc.agrege else "heure",
        })

    for uuid, entree in taches_json.items():
        entree["blocs"].sort(key=lambda b: (b["debut"], b["indice"]))
        entree["debut"] = entree["blocs"][0]["debut"]
        entree["fin"] = max(b["fin"] for b in entree["blocs"])
        placee_par_passe_1 = any(not b["opportuniste"] for b in entree["blocs"])
        entree["due"] = dues[uuid].isoformat() if placee_par_passe_1 else None
        tache = par_uuid.get(uuid)
        if tache is not None:
            if tache.description:
                entree["description"] = tache.description
            if tache.projet:
                entree["projet"] = tache.projet

    return {
        "version": VERSION_FORMAT,
        "statut": plan.statut,
        "retard_total": plan.retard_total,
        "en_retard": sorted(plan.en_retard),
        "t0": plan.t0.isoformat(),
        "granularite_minutes": int(plan.granularite.total_seconds() // 60),
        "taches": taches_json,
    }


def serialiser(plan, taches=None):
    """Rend la chaine JSON, **stable octet pour octet** pour une meme entree.

    `sort_keys=True` et un `indent` fixe : c'est ce qui rend l'idempotence de
    `ecrire_json` testable autrement que par la parole.
    """
    return json.dumps(plan_en_dict(plan, taches), sort_keys=True, indent=2,
                      ensure_ascii=False) + "\n"


def ecrire_json(plan, chemin, taches=None):
    """Ecrit le plan en JSON. Rend True si le fichier a change, False sinon.

    Idempotent : on compare au contenu existant et on **n'ouvre meme pas le
    fichier en ecriture** s'il est deja a jour, pour que son `mtime` ne bouge
    pas. Un test le verifie sur le `mtime`, pas sur la valeur de retour.
    """
    chemin = Path(chemin)
    contenu = serialiser(plan, taches)
    if chemin.exists():
        try:
            if chemin.read_text(encoding="utf-8") == contenu:
                return False
        except OSError:
            pass   # illisible : on reecrit, c'est le comportement sur
    chemin.write_text(contenu, encoding="utf-8")
    return True


def ecrire_scheduled(plan, env=None, dry_run=False, taches_existantes=None):
    """Ecrit `scheduled:` sur chaque tache planifiee. Rend un compte rendu.

        {'modifiees': [...], 'inchangees': [...], 'ignorees': [...]}

    `scheduled` vaut le **debut du premier bloc** de la tache.

    Sont mises dans `ignorees` :

    - les taches **`+externe`** : un delai fournisseur n'est pas du travail de
      l'utilisateur, ca n'a pas a apparaitre dans son agenda (proposal.md
      decision 10) ;
    - les taches **absentes de la base**, pour qu'un plan un peu vieux ne fasse
      pas echouer toute l'ecriture.

    `dry_run=True` n'ecrit **rien** mais rend le meme compte rendu : on peut
    donc voir ce qui serait fait sans rien toucher. Un test le prouve en
    comparant l'export Taskwarrior complet avant et apres.

    `env` doit porter un `TASKRC` ou un `TASKDATA` isole. Ce module ne le pose
    jamais lui-meme (AGENTS.md §2).
    """
    if taches_existantes is None:
        taches_existantes = exporter(env=env)
    etat = {t["uuid"]: t for t in taches_existantes}

    externes = {b.uuid for b in plan.blocs if b.externe}
    premiers = {}
    for bloc in plan.blocs:
        if bloc.uuid in externes:
            continue
        courant = premiers.get(bloc.uuid)
        if courant is None or bloc.debut < courant:
            premiers[bloc.uuid] = bloc.debut

    modifiees, inchangees, ignorees = [], [], []

    for uuid in sorted(externes):
        ignorees.append(uuid)

    for uuid in sorted(premiers):
        if uuid not in etat:
            ignorees.append(uuid)
            continue
        voulu = _vers_utc_taskwarrior(
            instant_creneau(plan.t0, premiers[uuid], plan.granularite))
        if etat[uuid].get("scheduled") == voulu:
            inchangees.append(uuid)
            continue
        modifiees.append(uuid)
        if dry_run:
            continue
        res = subprocess.run(
            ["task", *RC_MASSE, uuid, "modify", "scheduled:" + voulu],
            capture_output=True, text=True, encoding="utf-8", env=env,
            check=False)
        if res.returncode != 0:
            raise RuntimeError("task modify a echoue pour {} ({}) : {}".format(
                uuid, res.returncode, res.stderr.strip()))

    return {"modifiees": modifiees,
            "inchangees": inchangees,
            "ignorees": sorted(ignorees)}


def ecrire_due(plan, taches, env=None, dry_run=False, taches_existantes=None):
    """Ecrit `due:` ET `duePlanif:` sur chaque tache placee. Rend un compte rendu.

        {'modifiees': [...], 'inchangees': [...], 'ignorees': [...]}

    La valeur vient de `planif.dues.dues_calculees(plan, taches)` : c'est la fin
    du dernier bloc de la tache, la date « au plus tard » que le solveur a
    trouvee. Les deux champs sont ecrits **dans la meme commande** `task
    modify`, pour qu'ils ne puissent jamais diverger par une ecriture
    partielle (une commande qui echoue a moitie laisse alors `due` et
    `duePlanif` egaux tous les deux, ou tous les deux inchanges).

    Sont mises dans `ignorees` :

    - les taches **`+externe`** : comme pour `scheduled` (proposal.md
      decision 10) ;
    - les taches dont le `due` actuel est un **engagement humain** : un `due`
      non nul pour lequel `planif.dues.est_calculee` est faux. Ecraser cette
      date serait ecraser une decision de l'utilisateur ;
    - les taches **absentes de la base**, pour qu'un plan un peu vieux ne fasse
      pas echouer toute l'ecriture.

    `dry_run=True` n'ecrit **rien** mais rend le meme compte rendu.

    `env` doit porter un `TASKRC` ou un `TASKDATA` isole. Ce module ne le pose
    jamais lui-meme (AGENTS.md §2).
    """
    if taches_existantes is None:
        taches_existantes = exporter(env=env)
    etat = {t["uuid"]: t for t in taches_existantes}
    par_uuid_tache = {t.uuid: t for t in taches}

    dues = dues_calculees(plan, taches)
    externes = {b.uuid for b in plan.blocs if b.externe}

    modifiees, inchangees, ignorees = [], [], []

    for uuid in sorted(externes):
        ignorees.append(uuid)

    for uuid in sorted(set(dues) - externes):
        tache = par_uuid_tache.get(uuid)
        if tache is not None and tache.due is not None and not est_calculee(tache):
            ignorees.append(uuid)
            continue
        if uuid not in etat:
            ignorees.append(uuid)
            continue
        voulu = _vers_utc_taskwarrior(dues[uuid])
        if etat[uuid].get("due") == voulu and etat[uuid].get(UDA_DUE_PLANIF) == voulu:
            inchangees.append(uuid)
            continue
        modifiees.append(uuid)
        if dry_run:
            continue
        res = subprocess.run(
            ["task", *RC_MASSE, uuid, "modify",
             "due:" + voulu, UDA_DUE_PLANIF + ":" + voulu],
            capture_output=True, text=True, encoding="utf-8", env=env,
            check=False)
        if res.returncode != 0:
            raise RuntimeError("task modify a echoue pour {} ({}) : {}".format(
                uuid, res.returncode, res.stderr.strip()))

    return {"modifiees": modifiees,
            "inchangees": inchangees,
            "ignorees": sorted(ignorees)}
