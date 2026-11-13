"""Étape 3 : PD à 12 mois, logistique contre LightGBM (D-019 à D-021).

Entrées : data/intermediaire/{echantillon_pd12,octroi}.parquet, data/brut/fred/
Sorties : sorties/pd12/predictions_test.parquet (PD des deux modèles sur le test)
          sorties/pd12/modeles.pkl
          rapport/resultats/pd12.md et pd12_*.csv (agrégats publiables)
"""

import pickle
import time
from pathlib import Path

import pandas as pd

from ecl9 import macro, validation
from ecl9 import pd as pdm
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "sorties" / "pd12"
RESULTATS = RACINE / "rapport" / "resultats"


def charger() -> pd.DataFrame:
    inter = DOSSIER_DONNEES / "intermediaire"
    e = pd.read_parquet(inter / "echantillon_pd12.parquet")
    o = pd.read_parquet(inter / "octroi.parquet")
    m = macro.charger(DOSSIER_DONNEES / "brut" / "fred")
    return pdm.construire_variables(e, o, m)


def mesures(y, p, reference) -> dict:
    return {
        "n": len(y),
        "defauts": int(y.sum()),
        "taux_observe": float(y.mean()),
        "pd_moyenne": float(p.mean()),
        "attendu_sur_observe": validation.rapport_attendu_observe(y, p),
        "auc": validation.auc(y, p),
        "gini": validation.gini(y, p),
        "brier": validation.brier(y, p),
        "psi_vs_entrainement": validation.psi(reference, p),
    }


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    RESULTATS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    d = charger()
    fin = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M")
    app = d[d["annee_octroi"].isin(ANNEES_ENTRAINEMENT) & (d["period"] <= fin)]
    test = d[d["annee_octroi"].isin(ANNEES_TEST)]
    print(f"Entraînement {len(app):,} lignes, test {len(test):,} ({time.time() - t0:.0f} s)")

    # Réglage : prêts séparés (D-022), arrêtés jusqu'à fin 2004 contre arrêtés 2005.
    en_validation = pdm.prets_de_validation(app["loan_id"])
    sous_app = app[~en_validation & (app["period"] <= pd.Period("2004-12", "M"))]
    val = app[en_validation & (app["period"].dt.year == 2005)]
    print(f"Réglage : {len(sous_app):,} lignes d'apprentissage, {len(val):,} de validation")
    grille = pdm.regler_lightgbm(sous_app, sous_app[pdm.CIBLE], val, val[pdm.CIBLE])
    grille.to_csv(RESULTATS / "pd12_reglage_lightgbm.csv", index=False)
    meilleur = grille.iloc[0]
    print(grille.to_string(index=False), f"({time.time() - t0:.0f} s)")

    logit = pdm.ajuster_logistique(app, app[pdm.CIBLE])
    gbm = pdm.ajuster_lightgbm(
        app,
        app[pdm.CIBLE],
        meilleur["num_leaves"],
        meilleur["min_child_samples"],
        meilleur["iterations"],
    )
    print(f"Modèles estimés ({time.time() - t0:.0f} s)")
    with open(SORTIE / "modeles.pkl", "wb") as f:
        pickle.dump({"logistique": logit, "lightgbm": gbm}, f)

    pd_app = {
        "logistique": pdm.predire_logistique(logit, app),
        "lightgbm": gbm.predire(app),
    }
    pred = test[["loan_id", "period", "annee_octroi", pdm.CIBLE]].copy()
    pred["pd_logistique"] = pdm.predire_logistique(logit, test)
    pred["pd_lightgbm"] = gbm.predire(test)
    pred.assign(period=pred["period"].dt.to_timestamp()).to_parquet(
        SORTIE / "predictions_test.parquet", index=False
    )

    crise = pred[pred["period"].dt.year.between(2006, 2010)]
    lignes, calibrations = [], []
    for modele in ("logistique", "lightgbm"):
        perimetres = {
            "entrainement": (app[pdm.CIBLE], pd_app[modele]),
            "test 2006-2025": (pred[pdm.CIBLE], pred[f"pd_{modele}"]),
            "test arrêtés 2006-2010": (crise[pdm.CIBLE], crise[f"pd_{modele}"]),
        }
        for perimetre, (y, p) in perimetres.items():
            lignes.append(
                {"modele": modele, "perimetre": perimetre, **mesures(y, p, pd_app[modele])}
            )
            if perimetre != "entrainement":
                c = validation.calibration(y, p).reset_index()
                c.insert(0, "perimetre", perimetre)
                c.insert(0, "modele", modele)
                calibrations.append(c)
    tableau = pd.DataFrame(lignes)
    tableau.to_csv(RESULTATS / "pd12_mesures.csv", index=False)
    pd.concat(calibrations).to_csv(RESULTATS / "pd12_calibration.csv", index=False)

    par_annee = (
        pred.assign(annee_arrete=pred["period"].dt.year)
        .groupby("annee_arrete")
        .agg(
            n=(pdm.CIBLE, "size"),
            observe=(pdm.CIBLE, "mean"),
            pd_logistique=("pd_logistique", "mean"),
            pd_lightgbm=("pd_lightgbm", "mean"),
        )
    )
    par_annee.to_csv(RESULTATS / "pd12_par_annee.csv")

    importance = pd.Series(
        gbm.booster.feature_importance("gain"), index=gbm.booster.feature_name()
    ).sort_values(ascending=False)
    importance.div(importance.sum()).rename("part_du_gain").to_csv(
        RESULTATS / "pd12_importance_lightgbm.csv"
    )
    print(tableau.round(4).to_string(index=False))
    print(par_annee.loc[2006:2012].round(4).to_string())
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
