"""Contrat de test pour `tests/base_realiste.py` (module NON ECRIT).

Ce fichier est la specification de l'interface : le module `tests/base_realiste.py`
n'existe pas encore, et son interface exacte n'est fixee nulle part ailleurs.
Les choix d'interface ci-dessous sont ceux du redacteur de ce contrat, faits pour
rester au plus simple et coller a ce qui existe deja dans le depot
(conftest.py, cas_reference.py, planif/config.py, planif/echeances.py,
planif/taskwarrior.py). Toute implementation qui satisfait ce fichier est valide.

INTERFACE CHOISIE
==================

    generer(aujourdhui: date | None = None) -> Base

    `aujourdhui` par defaut vaut `date.today()`. `Base` est un objet simple
    (namedtuple ou dataclass), avec au moins les attributs :

    - `taches` : liste de dicts au format d'import Taskwarrior, exactement la
      forme utilisee par `tests/test_lot0_socle.py` et `tests/test_ecriture_due.py` :
      cles `uuid`, `description`, `status` (toujours "pending"), `entry`
      (format Taskwarrior UTC `%Y%m%dT%H%M%SZ`, planif/taskwarrior.py), `project`,
      `estTime` (forme acceptee par `planif/duree.py`), `tags` (liste de str),
      `depends` (liste d'uuid, absente si vide), et optionnellement `due` et
      `scheduled` (meme format de date). Aucune tache ne porte `wait`.

    - `echeances` : dict `nom_projet -> chaine ISO`, exactement le format que lit
      `planif.config.charger_echeances` (donc celui de `echeances.json` /
      `echeances.exemple.json`) : `"AAAA-MM-JJ"` (vaut la fin de journee) ou
      `"AAAA-MM-JJTHH:MM:SS"`. Les cles sont des noms de projet "racine" (au sens
      de `planif.echeances.couvre` : elles couvrent leurs sous-projets par
      prefixe sur frontiere de point).

    - `config` : dict au format de `config.json`, au moins les cles
      `timeSlots` (`nom_contexte -> {nom_jour_anglais: ["HH:MM-HH:MM", ...]}`,
      exactement la forme consommee par `planif.config._parse_grille`, cles de
      jour = `planif.modele.JOURS`, jours fermes representes par une liste
      vide) et `freeTimeHours` (marge quotidienne du contexte "pro", meme sens
      que dans `config.json` et `planif/config.py:128`). Au moins les
      contextes "pro" et un contexte non-pro (ex. "perso") y figurent dans
      `timeSlots`, pour couvrir le scenario S8 (echeance perso) et le test
      "non date" (§3). Remplace l'attribut `contextes` d'une version anterieure
      de ce contrat : la grille seule ne suffisait pas a verifier la regle de
      marge, qui doit retirer `freeTimeHours` (contexte pro) ou
      `planif.config.MARGE_PERSO_DEFAUT` (autres contextes) de la capacite
      brute — sinon le test ignore la marge que le planificateur reserve
      reellement.

    `semer(env_ou_taskrc, base: Base) -> None`

    `env_ou_taskrc` est soit le dict d'environnement rendu par la fixture
    `base_jetable` (qui contient `TASKRC`), soit directement un chemin (str ou
    Path) vers un fichier taskrc. Dans les deux cas, `semer` :

    1. lit ce fichier taskrc pour trouver la ligne `data.location=...` ;
    2. verifie que ce dossier de donnees contient un fichier temoin `.jetable`,
       sinon leve une exception (`RuntimeError` ou equivalent) et n'importe RIEN ;
    3. efface completement la base pointee (pending + completed + undo) ;
    4. importe `base.taches` (equivalent d'un `task import` depuis un fichier
       UTF-8, seule voie qui survit aux accents sous Windows, AGENTS.md §5).

    Le fichier `.jetable` n'est PAS cree par `semer` ni par la fixture
    `base_jetable` : c'est au test de le deposer avant d'appeler `semer`, a cote
    du `data.location` lu dans le taskrc de la fixture.

AMBIGUITES TRANCHEES
=====================

- "chaines les plus longues... different d'au moins un facteur 2" (motif meme
  echeance) : la longueur d'une chaine est la somme des `estTime` (en heures,
  taches +externe converties heures->jours*24 pour rester dans la meme unite)
  le long du chemin de poids maximal, calculee ici meme dans le test (fonction
  `_chemin_le_plus_long`), jamais lue dans une sortie du planificateur.
- "capacite de C entre le lendemain et E" (regle de marge) : intervalle
  `[aujourdhui + 1 jour, E.date()]` INCLUS des deux cotes ; un jour est compte
  s'il est ouvre dans la grille du contexte (creneaux non vides). La capacite
  d'un jour ouvre est NETTE de la marge quotidienne du contexte (voir
  ci-dessous), jamais negative (un jour dont la grille est plus courte que la
  marge compte pour 0, pas pour un nombre negatif).
- marge quotidienne d'un contexte : `freeTimeHours` de `base.config` pour le
  contexte "pro" (comme `planif/config.py:128`), `planif.config.MARGE_PERSO_DEFAUT`
  (converti en heures) pour tout autre contexte (comme `planif/config.py:139`).
  Le test importe cette constante, il ne recalcule pas la capacite via une
  fonction de `planif/`.
- "une semaine de capacite" (a soustraire) : somme, sur les 7 jours de la
  semaine (Monday..Sunday), de la capacite NETTE (grille moins marge, jamais
  negative) du contexte, une fois — pas la semaine calendaire de tel ou tel
  lancement, puisque la grille se repete a l'identique chaque semaine.
- "chemin critique ... laisse >= 7 jours calendaires de marge" : simule ici (pas
  dans le planificateur) en avancant un curseur de date jour par jour a partir
  du lendemain d'aujourd'hui, consommant pour chaque tache utilisateur la
  capacite NETTE (grille moins marge) des jours ouverts de son contexte
  jusqu'a epuiser son `estTime`, et pour chaque tache +externe en jours
  calendaires bruts (aucun jour n'est saute). La marge est
  `(E.date() - curseur_final).days`.
- une tache qui porte son propre `due` (hors cle de `base.echeances`) est
  traitee comme une echeance a elle seule, dans les deux tests de marge : son
  "travail" est la somme des `estTime` non-externe de ses predecesseurs
  transitifs (elle incluse), et son "chemin critique" est le chemin de poids
  maximal qui mene a elle (meme fonction `_chemin_le_plus_long` que pour les
  echeances de projet).
- "traverse deux sous-projets" (motif profondeur) : une dependance dont les
  deux taches ont des `project` differents, tous deux sous la racine a >= 3
  niveaux, et differents au niveau du deuxieme segment (donc pas seulement une
  variation de casse ou un sous-sous-projet du meme sous-projet).
- Determinisme des uuid (motif 2) : compare comme un dict
  `{description: uuid}` reconstruit a chaque appel, plutot qu'une liste
  ordonnee, au cas ou l'ordre des taches ne serait pas garanti.
"""
import itertools
from datetime import date, datetime, timedelta

import pytest

from planif.config import MARGE_PERSO_DEFAUT
from planif.duree import parse_duree
from planif.echeances import couvre, taches_terminales
from planif.modele import JOURS

from tests.base_realiste import generer, semer

FORMAT_TW = "%Y%m%dT%H%M%SZ"

LUNDI_FIXE = date(2026, 10, 5)  # lundi, coherent avec tests/cas_reference.py
JOURS_DE_LANCEMENT = [LUNDI_FIXE + timedelta(days=i) for i in range(7)]


# ---------------------------------------------------------------------------
# petits utilitaires locaux au test (ne dependent d'aucun code de solveur)
# ---------------------------------------------------------------------------

def _tw_vers_date(valeur):
    return datetime.strptime(valeur, FORMAT_TW).date()


def _iso_echeance_vers_date(valeur):
    texte = valeur.strip()
    instant = datetime.fromisoformat(texte)
    return instant.date()


def _heures(estTime):
    return parse_duree(estTime).total_seconds() / 3600.0


def _est_externe(tache):
    return "externe" in tache.get("tags", ())


def _est_fige(tache):
    return "fige" in tache.get("tags", ())


def _contexte_de(tache, contextes_connus):
    for tag in tache.get("tags", ()):
        if tag in contextes_connus:
            return tag
    return None


def _index_par_uuid(taches):
    return {t["uuid"]: t for t in taches}


def _predecesseurs(tache):
    return tuple(tache.get("depends", ()))


def _est_acyclique(taches):
    index = _index_par_uuid(taches)
    couleur = {}  # 0 non visite, 1 en cours, 2 fini

    def visiter(uuid):
        etat = couleur.get(uuid, 0)
        if etat == 1:
            return False
        if etat == 2:
            return True
        couleur[uuid] = 1
        for pred in _predecesseurs(index[uuid]):
            if pred in index and not visiter(pred):
                return False
        couleur[uuid] = 2
        return True

    return all(visiter(u) for u in index)


def _parse_plage(texte):
    debut, fin = texte.split("-")

    def minutes(hm):
        h, m = hm.strip().split(":")
        return int(h) * 60 + int(m)

    return minutes(fin) - minutes(debut)


def _heures_grille_jour(config, contexte_nom, jour_date):
    """Heures BRUTES de la grille, sans deduire la marge."""
    grille_contexte = config["timeSlots"][contexte_nom]
    nom_jour = JOURS[jour_date.weekday()]
    plages = grille_contexte.get(nom_jour, [])
    return sum(_parse_plage(p) for p in plages) / 60.0


def _marge_heures(config, contexte_nom):
    """Marge quotidienne du contexte, comme planif/config.py la calcule :
    `freeTimeHours` pour "pro", `MARGE_PERSO_DEFAUT` sinon."""
    if contexte_nom == "pro":
        return float(config.get("freeTimeHours", 2))
    return MARGE_PERSO_DEFAUT.total_seconds() / 3600.0


def _capacite_jour_net(config, contexte_nom, jour_date):
    """Heures de grille moins la marge quotidienne, jamais negatif."""
    brut = _heures_grille_jour(config, contexte_nom, jour_date)
    marge = _marge_heures(config, contexte_nom)
    return max(0.0, brut - marge)


def _jour_ouvre(config, contexte_nom, jour_date):
    return _heures_grille_jour(config, contexte_nom, jour_date) > 0


def _capacite_semaine(config, contexte_nom):
    reference = date(2026, 10, 5)  # un lundi, peu importe lequel
    return sum(_capacite_jour_net(config, contexte_nom, reference + timedelta(days=i))
               for i in range(7))


def _capacite_fenetre(config, contexte_nom, debut_inclus, fin_inclue):
    total = 0.0
    jour = debut_inclus
    while jour <= fin_inclue:
        total += _capacite_jour_net(config, contexte_nom, jour)
        jour += timedelta(days=1)
    return total


def _graphe_successeurs(taches):
    """uuid -> liste des uuid qui en dependent directement."""
    succ = {t["uuid"]: [] for t in taches}
    for t in taches:
        for pred in _predecesseurs(t):
            if pred in succ:
                succ[pred].append(t["uuid"])
    return succ


def _duree_tache_heures(tache):
    """Duree utilisee pour COMPARER des chemins (pas pour la simulation
    calendaire) : tout est ramene a des heures, +externe compris (24 h/jour)."""
    heures = _heures(tache["estTime"])
    return heures


def _chemin_le_plus_long(taches, uuid_cible):
    """Rend (longueur_en_heures, chemin) du chemin de poids maximal qui MENE a
    `uuid_cible`, predecesseurs compris, en remontant `depends`."""
    index = _index_par_uuid(taches)
    memo = {}

    def valeur(uuid):
        if uuid in memo:
            return memo[uuid]
        tache = index[uuid]
        propre = _duree_tache_heures(tache)
        preds = [p for p in _predecesseurs(tache) if p in index]
        if not preds:
            resultat = (propre, [uuid])
        else:
            meilleur = max((valeur(p) for p in preds), key=lambda vc: vc[0])
            resultat = (propre + meilleur[0], [uuid] + meilleur[1])
        memo[uuid] = resultat
        return resultat

    return valeur(uuid_cible)


def _jours_calendaires_pour_tache(tache, contexte_nom, config, depart):
    """Avance `depart` (une date) du temps que prend `tache`, et rend la date
    d'arrivee. Taches +externe : jours calendaires bruts. Taches utilisateur :
    consomme la capacite NETTE (grille moins marge) de chaque jour ouvert du
    contexte."""
    if _est_externe(tache):
        jours = _heures(tache["estTime"]) / 24.0
        import math
        return depart + timedelta(days=math.ceil(jours))

    heures_restantes = _heures(tache["estTime"])
    curseur = depart
    if heures_restantes <= 0:
        return curseur
    while heures_restantes > 0:
        if _jour_ouvre(config, contexte_nom, curseur):
            heures_restantes -= _capacite_jour_net(config, contexte_nom, curseur)
        curseur += timedelta(days=1)
    return curseur


def _predecesseurs_transitifs_non_externes(uuid_depart, index):
    """uuid + tous ses predecesseurs transitifs, filtres sur les non-+externe,
    pour le "travail" d'une tache qui porte son propre `due`."""
    vus = set()
    a_visiter = [uuid_depart]
    resultat = []
    while a_visiter:
        u = a_visiter.pop()
        if u in vus or u not in index:
            continue
        vus.add(u)
        t = index[u]
        if not _est_externe(t):
            resultat.append(t)
        a_visiter.extend(_predecesseurs(t))
    return resultat


def _projet_racine_de(nom_projet, echeances):
    """La cle d'echeance (au sens du prefixe le plus long) qui couvre `nom_projet`,
    ou None."""
    couvrantes = [c for c in echeances if couvre(c, nom_projet)]
    if not couvrantes:
        return None
    return max(couvrantes, key=len)


# ---------------------------------------------------------------------------
# 1. Integrite
# ---------------------------------------------------------------------------

def test_integrite_champs_obligatoires():
    base = generer(LUNDI_FIXE)
    for t in base.taches:
        assert t.get("uuid"), t
        assert t.get("description"), t
        assert t.get("project"), t
        assert _heures(t["estTime"]) > 0, t


def test_integrite_uuid_uniques():
    base = generer(LUNDI_FIXE)
    uuids = [t["uuid"] for t in base.taches]
    assert len(uuids) == len(set(uuids))


def test_integrite_depends_pointent_vers_uuid_existants():
    base = generer(LUNDI_FIXE)
    connus = {t["uuid"] for t in base.taches}
    for t in base.taches:
        for pred in _predecesseurs(t):
            assert pred in connus, (t["uuid"], pred)


def test_integrite_graphe_acyclique():
    base = generer(LUNDI_FIXE)
    assert _est_acyclique(base.taches)


def test_integrite_aucun_champ_wait():
    base = generer(LUNDI_FIXE)
    for t in base.taches:
        assert "wait" not in t, t


# ---------------------------------------------------------------------------
# 2. Determinisme des uuid
# ---------------------------------------------------------------------------

def test_determinisme_uuid_meme_jour():
    b1 = generer(LUNDI_FIXE)
    b2 = generer(LUNDI_FIXE)
    m1 = {t["description"]: t["uuid"] for t in b1.taches}
    m2 = {t["description"]: t["uuid"] for t in b2.taches}
    assert m1 == m2


def test_determinisme_uuid_jours_differents():
    b1 = generer(LUNDI_FIXE)
    b2 = generer(LUNDI_FIXE + timedelta(days=3))
    m1 = {t["description"]: t["uuid"] for t in b1.taches}
    m2 = {t["description"]: t["uuid"] for t in b2.taches}
    assert m1 == m2


# ---------------------------------------------------------------------------
# 3. Motifs exiges
# ---------------------------------------------------------------------------

def test_motif_convergence_avec_externe():
    """Au moins une tache avec >= 3 depends, dont au moins un +externe."""
    base = generer(LUNDI_FIXE)
    index = _index_par_uuid(base.taches)
    trouve = False
    for t in base.taches:
        preds = _predecesseurs(t)
        if len(preds) >= 3 and any(_est_externe(index[p]) for p in preds if p in index):
            trouve = True
            break
    assert trouve


def test_motif_divergence():
    """Au moins une tache dont >= 3 taches dependent."""
    base = generer(LUNDI_FIXE)
    succ = _graphe_successeurs(base.taches)
    assert any(len(s) >= 3 for s in succ.values())


def test_motif_meme_echeance_chaines_de_longueurs_differentes():
    """>= 2 projets racine distincts a la meme echeance, chaines les plus
    longues differant d'un facteur >= 2, l'un des deux avec un +externe."""
    base = generer(LUNDI_FIXE)
    par_date = {}
    for projet, valeur in base.echeances.items():
        par_date.setdefault(_iso_echeance_vers_date(valeur), []).append(projet)

    for projets in par_date.values():
        if len(projets) < 2:
            continue
        for a, b in itertools.combinations(projets, 2):
            taches_a = [t for t in base.taches if couvre(a, t["project"])]
            taches_b = [t for t in base.taches if couvre(b, t["project"])]
            term_a = taches_terminales(
                [_tache_legere(t) for t in taches_a], a)
            term_b = taches_terminales(
                [_tache_legere(t) for t in taches_b], b)
            if not term_a or not term_b:
                continue
            long_a = max(_chemin_le_plus_long(taches_a, u)[0] for u in term_a)
            long_b = max(_chemin_le_plus_long(taches_b, u)[0] for u in term_b)
            court, longue = sorted((long_a, long_b))
            if court <= 0:
                continue
            a_externe = any(_est_externe(t) for t in taches_a)
            b_externe = any(_est_externe(t) for t in taches_b)
            if longue >= 2 * court and (a_externe or b_externe):
                return
    pytest.fail("aucune paire de projets a meme echeance avec chaines x2 et un +externe")


def test_motif_profondeur_trois_niveaux_avec_echeance_racine_seule():
    """Un arbre de projets a >= 3 niveaux, echeance posee sur la racine
    seulement, et au moins une dependance qui traverse deux sous-projets."""
    base = generer(LUNDI_FIXE)
    projets = {t["project"] for t in base.taches}

    candidats = [p for p in projets if p.count(".") >= 2]
    assert candidats, "aucun projet a >= 3 niveaux"

    racines_possibles = set()
    for p in candidats:
        segments = p.split(".")
        for i in range(1, len(segments)):
            racines_possibles.add(".".join(segments[:i]))

    racines_avec_echeance_seule = [
        r for r in racines_possibles
        if r in base.echeances
        and not any(sp != r and couvre(r, sp) and sp in base.echeances
                    for sp in projets)
    ]
    assert racines_avec_echeance_seule, "aucune racine a >= 3 niveaux, echeance seule"

    index = _index_par_uuid(base.taches)
    trouve = False
    for t in base.taches:
        for pred in _predecesseurs(t):
            p_pred = index.get(pred)
            if p_pred is None:
                continue
            for racine in racines_avec_echeance_seule:
                if not (couvre(racine, t["project"]) and couvre(racine, p_pred["project"])):
                    continue
                seg_t = t["project"][len(racine) + 1:].split(".")[0] if len(t["project"]) > len(racine) else ""
                seg_pred = p_pred["project"][len(racine) + 1:].split(".")[0] if len(p_pred["project"]) > len(racine) else ""
                if seg_t and seg_pred and seg_t != seg_pred:
                    trouve = True
    assert trouve, "aucune dependance ne traverse deux sous-projets"


def test_motif_sous_sous_projets():
    """Des projets a 4 niveaux (ex. NPD.X.achats.devis), comme dans le reel :
    - au moins deux sous-sous-projets distincts sous un meme sous-projet ;
    - ce sous-projet porte aussi des taches en propre (niveaux melanges) ;
    - au moins une dependance relie un sous-sous-projet a une tache d'une
      AUTRE branche de la meme racine (hors de son sous-projet)."""
    base = generer(LUNDI_FIXE)
    projets = {t["project"] for t in base.taches}

    quatre = [p for p in projets if p.count(".") >= 3]
    assert quatre, "aucun projet a >= 4 niveaux"

    par_parent = {}
    for p in quatre:
        par_parent.setdefault(".".join(p.split(".")[:3]), set()).add(p)
    parents = [pa for pa, enfants in par_parent.items()
               if len(enfants) >= 2 and pa in projets]
    assert parents, ("aucun sous-projet ne porte a la fois des taches en propre "
                     "et >= 2 sous-sous-projets")

    index = _index_par_uuid(base.taches)
    trouve = False
    for t in base.taches:
        for pred in _predecesseurs(t):
            p_pred = index.get(pred)
            if p_pred is None:
                continue
            for a, b in ((t["project"], p_pred["project"]),
                         (p_pred["project"], t["project"])):
                if a.count(".") < 3:
                    continue
                sa, sb = a.split("."), b.split(".")
                if sa[:2] == sb[:2] and len(sb) >= 3 and sa[2] != sb[2]:
                    trouve = True
    assert trouve, "aucune dependance ne relie un sous-sous-projet a une autre branche"


def test_motif_externe_intercale():
    """Chaine utilisateur -> +externe -> utilisateur -> +externe."""
    base = generer(LUNDI_FIXE)
    index = _index_par_uuid(base.taches)
    for e2 in base.taches:
        if not _est_externe(e2):
            continue
        for u2_uuid in _predecesseurs(e2):
            u2 = index.get(u2_uuid)
            if u2 is None or _est_externe(u2):
                continue
            for e1_uuid in _predecesseurs(u2):
                e1 = index.get(e1_uuid)
                if e1 is None or not _est_externe(e1):
                    continue
                for u1_uuid in _predecesseurs(e1):
                    u1 = index.get(u1_uuid)
                    if u1 is not None and not _est_externe(u1):
                        return
    pytest.fail("aucune chaine utilisateur/externe/utilisateur/externe trouvee")


def test_motif_taches_non_datees_dans_au_moins_deux_contextes():
    """>= 2 contextes differents ont des taches sans due, sans depends, hors
    projet a echeance."""
    base = generer(LUNDI_FIXE)
    contextes_connus = set(base.config["timeSlots"])
    contextes_avec_non_datees = set()
    for t in base.taches:
        if t.get("due"):
            continue
        if _predecesseurs(t):
            continue
        if _projet_racine_de(t["project"], base.echeances) is not None:
            continue
        ctx = _contexte_de(t, contextes_connus)
        if ctx:
            contextes_avec_non_datees.add(ctx)
    assert len(contextes_avec_non_datees) >= 2


def test_motif_echeance_perso():
    """Un projet dont le contexte n'est pas pro porte une echeance."""
    base = generer(LUNDI_FIXE)
    for projet in base.echeances:
        taches_du_projet = [t for t in base.taches if couvre(projet, t["project"])]
        contextes = {_contexte_de(t, set(base.config["timeSlots"])) for t in taches_du_projet}
        contextes.discard(None)
        if contextes and contextes != {"pro"}:
            return
    pytest.fail("aucune echeance sur un projet non-pro")


def test_motif_tache_figee_avec_scheduled_futur():
    """Au moins une tache +fige avec `scheduled` strictement apres aujourd'hui."""
    base = generer(LUNDI_FIXE)
    for t in base.taches:
        if _est_fige(t) and t.get("scheduled"):
            if _tw_vers_date(t["scheduled"]) > LUNDI_FIXE:
                return
    pytest.fail("aucune tache +fige avec scheduled futur")


# ---------------------------------------------------------------------------
# 4. Echeances : vendredi ou lundi, strictement apres aujourd'hui, sur 7 jours
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("jour", JOURS_DE_LANCEMENT)
def test_echeances_tombent_vendredi_ou_lundi_et_apres_aujourdhui(jour):
    base = generer(jour)
    dates = [_iso_echeance_vers_date(v) for v in base.echeances.values()]
    dates += [_tw_vers_date(t["due"]) for t in base.taches if t.get("due")]
    assert dates, "aucune echeance a verifier"
    for d in dates:
        assert d.weekday() in (0, 4), (jour, d)  # lundi=0, vendredi=4
        assert d > jour, (jour, d)


# ---------------------------------------------------------------------------
# 5. Dates de creation
# ---------------------------------------------------------------------------

def test_dates_creation_toutes_avant_aujourdhui():
    base = generer(LUNDI_FIXE)
    for t in base.taches:
        assert _tw_vers_date(t["entry"]) < LUNDI_FIXE, t


def test_dates_creation_variees_anciennes_et_recentes():
    base = generer(LUNDI_FIXE)
    ages = [(LUNDI_FIXE - _tw_vers_date(t["entry"])).days for t in base.taches]
    assert sum(1 for a in ages if a > 365) >= 2
    assert sum(1 for a in ages if a < 60) >= 2


# ---------------------------------------------------------------------------
# 6. Regle de marge (statique, pour les 7 jours de lancement)
# ---------------------------------------------------------------------------

def _tache_legere(t):
    """Objet minimal (uuid, projet, depends) pour reutiliser
    planif.echeances.taches_terminales sans construire un vrai Tache complet."""
    from types import SimpleNamespace
    return SimpleNamespace(uuid=t["uuid"], projet=t["project"],
                            depends=tuple(t.get("depends", ())))


@pytest.mark.parametrize("jour", JOURS_DE_LANCEMENT)
def test_regle_de_marge_travail_utilisateur_sous_capacite(jour):
    base = generer(jour)
    contextes_connus = set(base.config["timeSlots"])
    index = _index_par_uuid(base.taches)
    lendemain = jour + timedelta(days=1)

    # contexte de chaque cle d'echeance : celui de la premiere de ses taches
    # qui porte un tag de contexte connu
    contexte_de_cle = {}
    for cle in base.echeances:
        taches_cle = [t for t in base.taches if couvre(cle, t["project"])]
        for t in taches_cle:
            ctx = _contexte_de(t, contextes_connus)
            if ctx:
                contexte_de_cle[cle] = ctx
                break

    for cle, echeance_str in base.echeances.items():
        contexte = contexte_de_cle.get(cle)
        if contexte is None:
            continue
        E = _iso_echeance_vers_date(echeance_str)
        if E <= jour:
            continue

        # tout le travail utilisateur du meme contexte du a E ou avant
        travail = 0.0
        for autre_cle, autre_val in base.echeances.items():
            if contexte_de_cle.get(autre_cle) != contexte:
                continue
            autre_E = _iso_echeance_vers_date(autre_val)
            if autre_E > E:
                continue
            for t in base.taches:
                if couvre(autre_cle, t["project"]) and not _est_externe(t):
                    travail += _heures(t["estTime"])

        capacite = (_capacite_fenetre(base.config, contexte, lendemain, E)
                    - _capacite_semaine(base.config, contexte))
        assert travail <= capacite, (jour, cle, travail, capacite)

    # une tache qui porte son propre due, hors cle de base.echeances, est une
    # echeance a elle seule : son travail est elle et ses predecesseurs
    # transitifs non-externes
    for t in base.taches:
        if not t.get("due"):
            continue
        if _projet_racine_de(t["project"], base.echeances) is not None:
            continue
        contexte = _contexte_de(t, contextes_connus)
        if contexte is None:
            continue
        E = _tw_vers_date(t["due"])
        if E <= jour:
            continue
        amont = _predecesseurs_transitifs_non_externes(t["uuid"], index)
        travail = sum(_heures(p["estTime"]) for p in amont)
        capacite = (_capacite_fenetre(base.config, contexte, lendemain, E)
                    - _capacite_semaine(base.config, contexte))
        assert travail <= capacite, (jour, t["uuid"], travail, capacite)


def _marge_chemin_critique(base, contextes_connus, index, uuid_cible, E, lendemain):
    """Simule le chemin de poids maximal menant a `uuid_cible` jour par jour, et
    rend la marge calendaire restante avant `E`."""
    _, chemin = _chemin_le_plus_long(base.taches, uuid_cible)
    # le chemin est liste de la cible vers la racine ; on simule dans
    # l'ordre chronologique (racine -> cible)
    curseur = lendemain
    for u in reversed(chemin):
        t = index[u]
        ctx = _contexte_de(t, contextes_connus) or list(base.config["timeSlots"])[0]
        curseur = _jours_calendaires_pour_tache(t, ctx, base.config, curseur)
    return (E - curseur).days


@pytest.mark.parametrize("jour", JOURS_DE_LANCEMENT)
def test_regle_de_marge_chemin_critique_laisse_une_semaine(jour):
    base = generer(jour)
    contextes_connus = set(base.config["timeSlots"])
    index = _index_par_uuid(base.taches)
    lendemain = jour + timedelta(days=1)

    for cle, echeance_str in base.echeances.items():
        E = _iso_echeance_vers_date(echeance_str)
        if E <= jour:
            continue
        taches_cle = [t for t in base.taches if couvre(cle, t["project"])]
        if not taches_cle:
            continue
        legeres = [_tache_legere(t) for t in taches_cle]
        terminales = taches_terminales(legeres, cle)

        for uuid_term in terminales:
            marge = _marge_chemin_critique(base, contextes_connus, index,
                                            uuid_term, E, lendemain)
            assert marge >= 7, (jour, cle, uuid_term, marge)

    # une tache a due propre, hors cle de base.echeances, est une echeance a
    # elle seule : son chemin critique est le plus long chemin qui y mene
    for t in base.taches:
        if not t.get("due"):
            continue
        if _projet_racine_de(t["project"], base.echeances) is not None:
            continue
        E = _tw_vers_date(t["due"])
        if E <= jour:
            continue
        marge = _marge_chemin_critique(base, contextes_connus, index,
                                        t["uuid"], E, lendemain)
        assert marge >= 7, (jour, t["uuid"], marge)


# ---------------------------------------------------------------------------
# 7. Semis (base_jetable)
# ---------------------------------------------------------------------------

def _data_dir_de(taskrc_path):
    for ligne in taskrc_path.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("data.location="):
            from pathlib import Path
            return Path(ligne.split("=", 1)[1])
    raise AssertionError("data.location introuvable dans " + str(taskrc_path))


def test_semer_deux_fois_ne_duplique_rien(base_jetable):
    base = generer(LUNDI_FIXE)
    donnees = _data_dir_de(base_jetable.taskrc)
    (donnees / ".jetable").write_text("test", encoding="utf-8")

    semer(base_jetable.env, base)
    semer(base_jetable.env, base)

    res = base_jetable.task("export")
    assert res.returncode == 0, res.stderr
    import json
    exportees = json.loads(res.stdout)
    pending = [t for t in exportees if t.get("status") == "pending"]
    assert len(pending) == len(base.taches)
    assert {t["uuid"] for t in pending} == {t["uuid"] for t in base.taches}


def test_semer_refuse_sans_fichier_jetable(base_jetable):
    base = generer(LUNDI_FIXE)
    donnees = _data_dir_de(base_jetable.taskrc)
    assert not (donnees / ".jetable").exists()

    with pytest.raises(Exception):
        semer(base_jetable.env, base)

    # Taskwarrior 3.5 rend "[\n]\n" pour une base vide : on lit le JSON au lieu
    # de comparer le texte brut.
    res = base_jetable.task("export")
    assert res.returncode == 0, res.stderr
    import json
    assert json.loads(res.stdout) == []


def test_semer_refuse_sans_rien_effacer(base_jetable):
    # Le test precedent part d'une base vide : un effacement fait AVANT le
    # refus y serait invisible. Ici la base contient une tache ; sans .jetable,
    # semer doit refuser et la tache doit toujours etre la.
    base = generer(LUNDI_FIXE)
    donnees = _data_dir_de(base_jetable.taskrc)
    assert not (donnees / ".jetable").exists()
    assert base_jetable.task("add", "Tache a proteger").returncode == 0

    with pytest.raises(Exception):
        semer(base_jetable.env, base)

    res = base_jetable.task("export")
    assert res.returncode == 0, res.stderr
    import json
    assert [t["description"] for t in json.loads(res.stdout)] == ["Tache a proteger"]


def test_semer_efface_ce_qui_n_est_pas_dans_la_base(base_jetable):
    # Avec des uuid fixes, reimporter la meme base ne duplique rien meme SANS
    # effacement : le test precedent ne voit donc pas un effacement manquant.
    # Celui-ci pose des taches etrangeres (une pending, une completed) et exige
    # qu'il n'en reste rien apres semer.
    base = generer(LUNDI_FIXE)
    donnees = _data_dir_de(base_jetable.taskrc)
    (donnees / ".jetable").write_text("test", encoding="utf-8")

    semer(base_jetable.env, base)
    assert base_jetable.task("add", "Tache etrangere pending").returncode == 0
    assert base_jetable.task("add", "Tache etrangere terminee").returncode == 0
    assert base_jetable.task("description:Tache etrangere terminee", "done").returncode == 0

    semer(base_jetable.env, base)

    res = base_jetable.task("export")
    assert res.returncode == 0, res.stderr
    import json
    exportees = json.loads(res.stdout)
    assert {t["uuid"] for t in exportees} == {t["uuid"] for t in base.taches}
