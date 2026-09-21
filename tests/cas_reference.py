"""Le cas de reference — entierement specifie par l'utilisateur, rien d'invente ici.

Toutes les valeurs de ce fichier viennent du prompt du run, qui les donne
explicitement. Elles ne sont PAS lues dans `config.json` : la grille du cas de
reference (`09:00-12:00` / `14:00-17:00`) differe volontairement de la grille reelle
de l'utilisateur (`08:30-12:00` / `14:00-18:30`). Les deux coexistent — la grille
reelle vit dans `planif/config.py`, celle-ci vit dans les tests.

Horloge FIGEE : aucun appel a `datetime.now()` nulle part dans la chaine testee.
L'instant courant est injecte. C'est ce qui rend les tests deterministes.

    - instant courant : lundi 2026-10-05 a 08:00
    - grille `pro`    : lun-ven 09:00-12:00 et 14:00-17:00 ; samedi et dimanche vides
    - marge `pro`     : 2 h par jour  -> 4 h utiles par jour
    - bloc minimum    : 2 h
    - aucune reunion
    - echeance projet : mardi 2026-11-24 a 17:00

La chaine :

    | Tache               | estimated | depend de | marqueur  |
    | A - Faire le plan   | 4 h       | -         | -         |
    | B - Commander       | 30 min    | A         | -         |
    | C - Fabrication     | 28 jours  | B         | +externe  |
    | D - Tester          | 3 h       | C         | -         |
"""
from datetime import datetime, timedelta

from planif.modele import Contexte, Creneau, Tache

# --- instants ------------------------------------------------------------

MAINTENANT = datetime(2026, 10, 5, 8, 0)      # lundi
T0 = datetime(2026, 10, 5, 0, 0)              # minuit du jour courant (design.md §1)
HORIZON_FIN = datetime(2026, 12, 1, 0, 0)     # couvre l'echeance du 24/11
ECHEANCE_PROJET = datetime(2026, 11, 24, 17, 0)   # mardi
GRANULARITE = timedelta(minutes=30)           # proposal.md decision 1

# --- le contexte du cas de reference -------------------------------------

_MATIN = Creneau(9 * 60, 12 * 60)      # 09:00-12:00
_APRES_MIDI = Creneau(14 * 60, 17 * 60)  # 14:00-17:00

CONTEXTE_PRO = Contexte(
    nom="pro",
    contexte_tw="pro",
    bloc_min=timedelta(hours=2),
    marge_jour=timedelta(hours=2),
    grille={
        0: (_MATIN, _APRES_MIDI),   # lundi
        1: (_MATIN, _APRES_MIDI),
        2: (_MATIN, _APRES_MIDI),
        3: (_MATIN, _APRES_MIDI),
        4: (_MATIN, _APRES_MIDI),   # vendredi
        5: (),                      # samedi
        6: (),                      # dimanche
    },
)

CONTEXTES = {"pro": CONTEXTE_PRO}

# --- la chaine -----------------------------------------------------------

UUID_A = "aaaaaaaa-0000-0000-0000-000000000001"
UUID_B = "bbbbbbbb-0000-0000-0000-000000000002"
UUID_C = "cccccccc-0000-0000-0000-000000000003"
UUID_D = "dddddddd-0000-0000-0000-000000000004"

PROJET = "NPD.helisides"


def chaine():
    """Rend les quatre taches du cas de reference, dans l'ordre A, B, C, D."""
    return [
        Tache(uuid=UUID_A, description="Faire le plan", projet=PROJET,
              estimated=timedelta(hours=4), tags=("pro",), contexte="pro"),
        Tache(uuid=UUID_B, description="Commander", projet=PROJET,
              estimated=timedelta(minutes=30), depends=(UUID_A,),
              tags=("pro",), contexte="pro"),
        Tache(uuid=UUID_C, description="Fabrication fournisseur", projet=PROJET,
              estimated=timedelta(days=28), depends=(UUID_B,),
              tags=("pro", "externe"), contexte="pro"),
        Tache(uuid=UUID_D, description="Tester", projet=PROJET,
              estimated=timedelta(hours=3), depends=(UUID_C,),
              tags=("pro",), contexte="pro"),
    ]


def taches_de_remplissage(nombre=3, heures=30):
    """Les trois taches de 30 h du controle 2.

    Le prompt les decrit « sans echeance ». Le regime des taches non datees est la
    passe 2 (lot 6), qui n'est pas ecrite : on leur donne donc l'echeance du projet
    pour qu'elles entrent dans la passe 1. C'est une INTERPRETATION, declaree dans
    RAPPORT-NUIT.md. Elle ne change rien a ce que le controle mesure : la question
    est de savoir si la fabrication `+externe` mange de la capacite, pas de savoir
    par quel regime ces taches sont placees.
    """
    return [
        Tache(uuid="ffffffff-0000-0000-0000-{:012d}".format(i),
              description="Remplissage {}".format(i),
              projet=PROJET,
              estimated=timedelta(hours=heures),
              due=ECHEANCE_PROJET,
              tags=("pro",), contexte="pro")
        for i in range(1, nombre + 1)
    ]
