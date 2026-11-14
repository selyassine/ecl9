"""Étape 11 : sensibilité à la maturation des étiquettes (D-046).

Le résultat principal entraîne les PD à 12 mois sur les arrêtés jusqu'au
31/12/2005, dont les étiquettes ne sont connues que fin 2006. Ici, les deux
modèles sont réestimés sur les seuls arrêtés jusqu'au 31/12/2004, dont
l'étiquette est connue au 31/12/2005, et l'écart de provision est recalculé.
La survie, le remboursement, la LGD et les stades restent ceux du résultat
principal, comme pour le bootstrap de l'étape 10.

Usage : python pipeline/etape_11_coupure_stricte.py   (après les étapes 3 et 7)
"""

import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import etape_03_pd12 as e3
import etape_07_trimestriel as e7
import etape_10_bootstrap_modeles as e10
from ecl9 import macro, moteur, validation
from ecl9 import pd as pdm
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT

COUPURE_STRICTE = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M") - 12


def main() -> pd.DataFrame:
    octroi = pd.read_parquet(e7.INTER / "octroi.parquet")
    m = macro.charger(e7.DOSSIER_DONNEES / "brut" / "fred")
    modeles = e7.charger_modeles()
    d = e3.charger()
    app = d[d["annee_octroi"].isin(ANNEES_ENTRAINEMENT) & (d["period"] <= COUPURE_STRICTE)]
    test = d[d["annee_octroi"].isin(ANNEES_TEST)]
    crise = test[test["period"].dt.year.between(2006, 2010)]
    reglage = pd.read_csv(e10.RESULTATS / "pd12_reglage_lightgbm.csv").iloc[0]

    with open(e3.SORTIE / "modeles.pkl", "rb") as f:
        reference = pickle.load(f)
    stricts = {
        "logistique": pdm.ajuster_logistique(app, app[pdm.CIBLE]),
        "lightgbm": pdm.ajuster_lightgbm(
            app,
            app[pdm.CIBLE],
            reglage["num_leaves"],
            reglage["min_child_samples"],
            reglage["iterations"],
        ),
    }

    def predire(jeu, nom, x):
        if nom == "logistique":
            return pdm.predire_logistique(jeu[nom], x)
        return jeu[nom].predire(x)

    prets = {a: e10.portefeuille(a, octroi, m, modeles, test) for a in e10.ARRETES}
    lignes = []
    for coupure, jeu in (
        (DERNIER_ARRETE_ENTRAINEMENT[:7], reference),
        (str(COUPURE_STRICTE), stricts),
    ):
        for nom in e7.MODELES:
            p = predire(jeu, nom, crise)
            ligne = {
                "dernier_arrete_entrainement": coupure,
                "modele": nom,
                "auc": validation.auc(crise[pdm.CIBLE], p),
                "attendu_sur_observe": validation.rapport_attendu_observe(crise[pdm.CIBLE], p),
            }
            for arrete, q in prets.items():
                e = moteur.provisions(
                    q["stades"][nom],
                    q["crd"],
                    q["taux"],
                    q["restants"],
                    q["lgd"],
                    predire(jeu, nom, q["x"]),
                    q["h"],
                    hasards_rembt=q["hp"],
                )
                ligne[f"ecl_{arrete}"] = float(e.sum() + q["stade3"].sum())
            lignes.append(ligne)
    return pd.DataFrame(lignes)


if __name__ == "__main__":
    t = main()
    t.to_csv(e10.RESULTATS / "coupure_stricte.csv", index=False)
    print(t.round(4).to_string(index=False))
    for coupure, g in t.groupby("dernier_arrete_entrainement"):
        g = g.set_index("modele")
        for c in [c for c in t if c.startswith("ecl_")]:
            ecart = g.loc["lightgbm", c] / g.loc["logistique", c] - 1
            print(f"Coupure {coupure}, {c} : écart {ecart:+.1%}")
