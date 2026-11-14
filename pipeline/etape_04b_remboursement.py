"""Étape 4 bis : hasard de remboursement anticipé, risque concurrent du défaut (D-040).

Entrées : data/intermediaire/panneau/, octroi.parquet, data/brut/fred/
Sorties : sorties/remboursement/modele.pkl
          rapport/resultats/remboursement_*.csv (agrégats publiables)
"""

import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ecl9 import macro, survie, validation
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "sorties" / "remboursement"
RESULTATS = RACINE / "rapport" / "resultats"
COLONNES = [
    "loan_id",
    "period",
    "loan_age",
    "current_interest_rate",
    "defaut",
    "annee_octroi",
    "zero_balance_code",
    "remaining_months_to_maturity",
]
FIN_TEST = pd.Period("2010-12", "M")
PART = 0.05
GRAINE = 20261112


def lire(annees, debut, fin, octroi, m, part, rng) -> pd.DataFrame:
    morceaux = []
    for a in annees:
        p = pd.read_parquet(
            DOSSIER_DONNEES / "intermediaire" / "panneau" / f"millesime_{a}.parquet",
            columns=COLONNES,
        )
        p["period"] = pd.PeriodIndex(p["period"], freq="M")
        garde = (p["period"] <= fin).to_numpy().copy()
        if debut is not None:
            garde &= (p["period"] >= debut).to_numpy()
        garde &= rng.random(len(p)) < part
        p = p[garde].copy()
        p["rembt"] = survie.marquer_remboursement(p)
        morceaux.append(survie.preparer(p, octroi, m))
    return pd.concat(morceaux, ignore_index=True)


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rng = np.random.default_rng(GRAINE)
    octroi = pd.read_parquet(DOSSIER_DONNEES / "intermediaire" / "octroi.parquet")
    m = macro.charger(DOSSIER_DONNEES / "brut" / "fred")
    fin_app = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M")

    app = lire(ANNEES_ENTRAINEMENT, None, fin_app, octroi, m, PART, rng)
    print(
        f"Entraînement : {len(app):,} prêts-mois tirés, "
        f"{int(app['rembt'].sum()):,} remboursements ({time.time() - t0:.0f} s)"
    )
    libre = survie.ajuster(app, cible="rembt")
    contraint, retirees = survie.ajuster_avec_signes(
        app, survie.SIGNES_REMBOURSEMENT, cible="rembt"
    )
    print(f"Variables macro retirées par la contrainte de signe : {retirees or 'aucune'}")
    modeles = {"libre": libre, "contraint": contraint}
    with open(SORTIE / "modele.pkl", "wb") as f:
        pickle.dump({**modeles, "retenu": "contraint", "retirees": retirees}, f)

    # Test : 20 % des prêts-mois 2006-2010 suffisent pour des agrégats stables.
    test = lire(ANNEES_TEST, pd.Period("2006-01", "M"), FIN_TEST, octroi, m, 0.20, rng)
    test["annee"] = test["period"].dt.year
    figee = test.copy()
    decembre_2005 = m.loc[fin_app]
    for c in decembre_2005.index:
        figee[c] = decembre_2005[c]
    figee["ecart_taux"] = figee["current_interest_rate"] - decembre_2005["taux_30a"]

    lignes, annees, coefs = [], [], []
    for nom, modele in modeles.items():
        app["h"] = survie.hasards(modele, app)
        test["h_realisee"] = survie.hasards(modele, test)
        test["h_figee"] = survie.hasards(modele, figee)
        for perimetre, d, col in [
            ("entrainement", app, "h"),
            ("test, macro réalisée", test, "h_realisee"),
            ("test, macro figée à déc. 2005", test, "h_figee"),
        ]:
            lignes.append(
                {
                    "modele": nom,
                    "perimetre": perimetre,
                    "prets_mois": len(d),
                    "observes": int(d["rembt"].sum()),
                    "attendus": float(d[col].sum()),
                    "attendu_sur_observe": float(d[col].sum() / d["rembt"].sum()),
                    "auc": validation.auc(d["rembt"], d[col]),
                }
            )
        a = test.groupby("annee").agg(
            prets_mois=("rembt", "size"),
            taux_observe=("rembt", "mean"),
            taux_attendu_realisee=("h_realisee", "mean"),
            taux_attendu_figee=("h_figee", "mean"),
        )
        annees.append(a.assign(modele=nom))
        coefs.append(survie.coefficients_macro(modele).rename(nom))

    mesures = pd.DataFrame(lignes)
    mesures.to_csv(RESULTATS / "remboursement_mesures.csv", index=False)
    par_annee = pd.concat(annees)
    par_annee.to_csv(RESULTATS / "remboursement_par_annee.csv")
    coef = pd.concat(coefs, axis=1)
    coef.to_csv(RESULTATS / "remboursement_coef_macro.csv")
    print(mesures.round(4).to_string(index=False))
    print(par_annee.round(4).to_string())
    print(coef.round(3).to_string())
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
