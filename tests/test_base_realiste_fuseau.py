"""Contrat de test : chaque date ecrite par `tests/base_realiste.py::generer()` dans un
champ Taskwarrior represente une heure LOCALE VOULUE, serialisee en UTC (au format
FORMAT_TW, `.astimezone(timezone.utc).strftime(...)`). Relue par Taskwarrior (`task
export`) et reconvertie en local, elle doit redonner l'heure voulue.

DEFAUT SIGNALE (RESTE-A-FAIRE.md / commit 5326d20) : `scheduled` (via `scheduled_offset`,
generer(), construction de `planifie`) est ecrit par
`datetime.combine(...).strftime(FORMAT_TW)`, SANS passer par
`.astimezone(timezone.utc)` : l'heure locale voulue (9h) est ecrite telle quelle, avec
le suffixe Z, comme si elle etait deja en UTC. En France (UTC+1 hiver / UTC+2 ete), une
tache voulue a 09:00 local apparait donc a 10:00 ou 11:00.

AUTRE CHAMP TROUVE PAR LECTURE AVEC LE MEME DEFAUT : `entry` (generer(), construction de
`entree` : `datetime.combine(aujourdhui, dtime(8, 0)) - timedelta(days=spec["age"])`
puis `.strftime(FORMAT_TW)` -- meme construction naive-directe, sans conversion). L'heure
locale voulue (08:00) est ecrite comme si elle etait deja en UTC.

CHAMPS VERIFIES CORRECTS PAR LECTURE (aucune regression attendue) :
- `due` (via `_due_tw_18h_local`) : deja correct, utilise
  `instant_local_naif.astimezone(timezone.utc).strftime(FORMAT_TW)` -- meme convention
  que `tests/test_ecriture_due.py`.
- pas de `wait` ni de `until` dans ce module : `generer()` n'ecrit que `entry`,
  `scheduled` et `due` comme champs-date Taskwarrior (grep sur tests/base_realiste.py).
  `_echeances()` ecrit des dates ISO pures (`.isoformat()`, sans heure) pour
  `echeances.json` : hors du champ d'application de FORMAT_TW (pas d'heure a fausser).

PROPRIETE "scheduled tombe dans une plage de grille" : aucune propriete de ce type
n'existe dans `tests/test_base_realiste.py` (grep sans resultat sur grille/creneau/
plage/slot en lien avec `scheduled`) -- rien a reverifier post-correctif de ce cote.

FUSEAU FORCE : `time.tzset()` n'existe pas sous Windows -- aucun moyen portable de
forcer, DANS CE PROCESS, le fuseau SYSTEME dont depend `datetime.astimezone()` sans
argument (celui dont depend `_due_tw_18h_local`, et dont devra dependre le correctif de
`entry`/`scheduled`). A la place, le test force le fuseau cote ATTENTE via
`zoneinfo.ZoneInfo("Europe/Paris")` (independant du parametrage systeme). Hypothese
assumee : le fuseau REEL de cette machine est Europe/Paris, confirme par lecture --
`time.tzname() == ('Paris, Madrid', 'Paris, Madrid (heure d ete)')` et
`datetime.now().astimezone()` rend un offset `+02:00` fin septembre 2026 (heure d'ete
d'Europe/Paris). Limitation assumee : si cette machine changeait de fuseau systeme, ce
fichier devrait etre adapte -- il n'est pas isole du systeme pour le controle negatif
sur `due`, qui suit `.astimezone()` systeme.

Test 1 (pur, ci-dessous) ne serait trivialement vert que si le fuseau machine etait UTC
-- `test_fuseau_machine_non_utc` verifie que ce n'est pas le cas (garde-fou
d'instrument).
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tests.base_realiste import FORMAT_TW, generer, semer

LUNDI_FIXE = date(2026, 10, 5)  # meme date fixe que tests/test_base_realiste.py

FUSEAU_ATTENDU = ZoneInfo("Europe/Paris")

# Heures locales VOULUES telles que SPECIFIEES dans tests/base_realiste.py (pas lues
# dans sa sortie) :
#   - entry     : dtime(8, 0)  (generer(), construction de `entree`)
#   - scheduled : dtime(9, 0)  (generer(), construction de `planifie`, spec S9)
#   - due       : dtime(18, 0) (_due_tw_18h_local)
HEURE_LOCALE_VOULUE_ENTRY = (8, 0)
HEURE_LOCALE_VOULUE_SCHEDULED = (9, 0)
HEURE_LOCALE_VOULUE_DUE = (18, 0)


def _heure_locale_paris(valeur_tw):
    """Relit un champ-date Taskwarrior (FORMAT_TW) comme un instant UTC, le convertit
    dans le fuseau FORCE Europe/Paris (independant du systeme), rend (heure, minute)."""
    aware_utc = datetime.strptime(valeur_tw, FORMAT_TW).replace(tzinfo=timezone.utc)
    local = aware_utc.astimezone(FUSEAU_ATTENDU)
    return (local.hour, local.minute)


def _data_dir_de(taskrc_path):
    for ligne in taskrc_path.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("data.location="):
            return Path(ligne.split("=", 1)[1])
    raise AssertionError("data.location introuvable dans " + str(taskrc_path))


def test_fuseau_machine_non_utc():
    """Garde-fou d'instrument (AGENTS.md / CLAUDE.md general §3) : si la machine etait
    en UTC, le test pur ci-dessous serait trivialement vert (aucune conversion ne
    changerait rien) -- ce n'est pas le cas ici."""
    decalage = datetime.now().astimezone().utcoffset()
    assert decalage is not None and decalage.total_seconds() != 0, (
        "machine en UTC : ce fichier ne peut pas mettre en evidence le defaut de "
        "fuseau (voir docstring du module, hypothese Europe/Paris)"
    )


def test_entry_est_a_lheure_locale_voulue():
    """Pur : chaque `entry` de generer(), relu comme UTC puis reconverti dans le
    fuseau FORCE Europe/Paris, doit redonner 08:00 (heure SPECIFIEE dans generer(),
    pas lue dans sa sortie)."""
    base = generer(LUNDI_FIXE)
    en_defaut = []
    for tache in base.taches:
        heure_minute = _heure_locale_paris(tache["entry"])
        if heure_minute != HEURE_LOCALE_VOULUE_ENTRY:
            en_defaut.append((tache["description"],) + heure_minute)
    assert not en_defaut, (
        "entry pas a l'heure locale voulue 08:00 (heure, minute obtenues) pour : "
        "{}".format(en_defaut)
    )


def test_scheduled_est_a_lheure_locale_voulue():
    """Pur : meme verification pour `scheduled` (seule porteuse : spec S9, "Preparer
    salle reunion client", heure SPECIFIEE 09:00)."""
    base = generer(LUNDI_FIXE)
    porteuses = [t for t in base.taches if t.get("scheduled")]
    assert porteuses, "aucune tache avec scheduled dans generer() : contrat casse"
    en_defaut = []
    for tache in porteuses:
        heure_minute = _heure_locale_paris(tache["scheduled"])
        if heure_minute != HEURE_LOCALE_VOULUE_SCHEDULED:
            en_defaut.append((tache["description"],) + heure_minute)
    assert not en_defaut, (
        "scheduled pas a l'heure locale voulue 09:00 (heure, minute obtenues) pour : "
        "{}".format(en_defaut)
    )


def test_due_deja_correct_pas_de_regression():
    """Controle negatif : `due` (_due_tw_18h_local) est deja correct par lecture -- ne
    doit pas regresser pendant la correction de `entry`/`scheduled`."""
    base = generer(LUNDI_FIXE)
    porteuses = [t for t in base.taches if t.get("due")]
    assert porteuses, "aucune tache avec due dans generer() : contrat casse"
    for tache in porteuses:
        heure_minute = _heure_locale_paris(tache["due"])
        assert heure_minute == HEURE_LOCALE_VOULUE_DUE, (
            tache["description"],) + heure_minute


def test_bout_en_bout_scheduled_heure_locale_apres_export(base_jetable):
    """Bout en bout : seme la base sur base_jetable, relit avec `task export` (pas
    `base.taches` directement) -- la tache de reference S9 doit apparaitre a 09:00
    local une fois reconvertie."""
    base = generer(LUNDI_FIXE)
    donnees = _data_dir_de(base_jetable.taskrc)
    (donnees / ".jetable").write_text("test", encoding="utf-8")
    semer(base_jetable.env, base)

    res = base_jetable.task("export")
    assert res.returncode == 0, res.stderr
    exportees = json.loads(res.stdout)

    reference = [t for t in exportees
                 if t["description"] == "Preparer salle reunion client"]
    assert len(reference) == 1, reference
    heure, minute = _heure_locale_paris(reference[0]["scheduled"])
    assert (heure, minute) == HEURE_LOCALE_VOULUE_SCHEDULED, (
        "task export rend scheduled a {:02d}:{:02d} local, attendu 09:00"
        .format(heure, minute)
    )
