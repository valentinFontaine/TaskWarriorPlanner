"""Imprime le plan obtenu sur le cas de reference, en face des valeurs attendues.

Ce n'est pas un test : c'est l'instrument de mesure dont RAPPORT-NUIT.md cite la
sortie brute. Il ne valide rien, il constate.

    ./venv/Scripts/python.exe -m tests.mesures_cas_reference
"""
from dataclasses import replace
from datetime import datetime, timedelta

from planif.calendrier import instant_creneau
from planif.solveur import resoudre
from planif.tampon import limites_effectives
from tests.cas_reference import (CONTEXTE_PRO, CONTEXTES, ECHEANCE_PROJET,
                                 GRANULARITE, HORIZON_FIN, MAINTENANT, T0,
                                 UUID_A, UUID_B, UUID_C, UUID_D, chaine,
                                 taches_de_remplissage)

NOMS = {UUID_A: "A - Faire le plan (4 h)",
        UUID_B: "B - Commander (30 min)",
        UUID_C: "C - Fabrication (28 j, +externe)",
        UUID_D: "D - Tester (3 h)"}

JOURS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def fr(instant):
    if instant is None:
        return "(non planifie)"
    return "{} {} a {:02d}:{:02d}".format(
        JOURS_FR[instant.weekday()], instant.strftime("%Y-%m-%d"),
        instant.hour, instant.minute)


def avec_due_sur_d(taches):
    return [replace(t, due=ECHEANCE_PROJET) if t.uuid == UUID_D else t
            for t in taches]


def main():
    taches = avec_due_sur_d(chaine())

    print("=" * 74)
    print("CAS DE REFERENCE — horloge figee au", fr(MAINTENANT))
    print("grille pro : lun-ven 09:00-12:00 et 14:00-17:00 ; marge 2 h ;")
    print("bloc min 2 h ; aucune reunion ; echeance projet", fr(ECHEANCE_PROJET))
    print("=" * 74)

    limites = limites_effectives(taches, CONTEXTES)
    print("\n-- echeance effective (tampon applique une seule fois) --")
    for uuid in (UUID_A, UUID_B, UUID_C, UUID_D):
        print("  {:34s} {}".format(NOMS[uuid], fr(limites[uuid])))

    plan = resoudre(taches, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    print("\n-- statut du solveur --")
    print("  statut        :", plan.statut)
    print("  retard total  :", plan.retard_total, "creneaux")
    print("  en retard     :", plan.en_retard or "(aucune)")

    print("\n-- plan obtenu, bloc par bloc --")
    for bloc in plan.blocs:
        d = instant_creneau(T0, bloc.debut, GRANULARITE)
        f = instant_creneau(T0, bloc.fin, GRANULARITE)
        print("  {:34s} bloc {} : {} -> {}{}".format(
            NOMS.get(bloc.uuid, bloc.uuid[:8]), bloc.indice, fr(d),
            fr(f), "   [EXTERNE, hors capacite]" if bloc.externe else ""))

    print("\n-- mesures, en face des attendus --")
    lignes = [
        ("fin de D", fr(plan.fin(UUID_D)), "vendredi 2026-11-20 a 17:00"),
        ("duree de C", str(plan.fin(UUID_C) - plan.debut(UUID_C)),
         "28 days, 0:00:00"),
        ("C finit quand D commence",
         "oui" if plan.fin(UUID_C) == plan.debut(UUID_D) else "NON",
         "oui"),
        ("debut de B", fr(plan.debut(UUID_B)),
         "vendredi 2026-10-23, avant 14:00"),
        ("jours de A",
         str(sorted({instant_creneau(T0, b.debut, GRANULARITE).date()
                     for b in plan.blocs_de(UUID_A)})),
         "[2026-10-22, 2026-10-23]"),
    ]
    for nom, obtenu, attendu in lignes:
        marque = "OK " if attendu.split(",")[0] in obtenu or obtenu in attendu else "?? "
        print("  {} {:26s} obtenu : {:32s} attendu : {}".format(
            marque, nom, obtenu, attendu))

    # ------------------------------------------------------------------
    print("\n" + "=" * 74)
    print("CONTROLE 2 — trois taches de 30 h ajoutees pendant la fabrication")
    print("=" * 74)
    taches2 = taches + taches_de_remplissage(3, 30)
    plan2 = resoudre(taches2, CONTEXTES, T0, MAINTENANT, HORIZON_FIN, GRANULARITE)
    print("  statut :", plan2.statut, "| retard :", plan2.retard_total,
          "| en retard :", plan2.en_retard or "(aucune)")

    for t in taches_de_remplissage(3, 30):
        total = sum(b.fin - b.debut for b in plan2.blocs_de(t.uuid)) * GRANULARITE
        print("  {} : {} blocs, {} au total (attendu 30:00:00)".format(
            t.description, len(plan2.blocs_de(t.uuid)), total))

    debut_c, fin_c = plan2.debut(UUID_C), plan2.fin(UUID_C)
    par_jour = plan2.creneaux_par_jour()
    print("\n  fabrication : {} -> {}".format(fr(debut_c), fr(fin_c)))
    print("  capacite utilisee par jour ouvre PENDANT la fabrication")
    print("  (8 creneaux = 4 h = la journee utile entiere) :\n")
    pleins = partiels = vides = 0
    jour = debut_c.date() + timedelta(days=1)
    while jour < fin_c.date():
        if CONTEXTE_PRO.est_ouvre(jour):
            occupe = par_jour.get(jour, 0)
            etat = "PLEIN" if occupe == 8 else ("vide" if occupe == 0 else "partiel")
            if occupe == 8:
                pleins += 1
            elif occupe == 0:
                vides += 1
            else:
                partiels += 1
            print("    {} {:9s} : {} creneaux  {}".format(
                JOURS_FR[jour.weekday()][:3], str(jour), occupe, etat))
        jour += timedelta(days=1)
    print("\n  -> {} jours pleins, {} partiels, {} vides".format(
        pleins, partiels, vides))
    print("  Si C etait entre dans AddNoOverlap, ces jours seraient tous vides.")

    depassements = [(j, n) for j, n in par_jour.items() if n > 8]
    print("  jours depassant la capacite de 4 h :", depassements or "(aucun)")


if __name__ == "__main__":
    main()
