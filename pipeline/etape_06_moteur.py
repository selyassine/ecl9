"""Étape 6 : provision du portefeuille de test à une date d'arrêté (D-029).

Calcule la provision de chaque prêt actif des millésimes de test, avec la PD
à 12 mois de la logistique puis celle de LightGBM, la même survie, la même
LGD et une macro figée à l'arrêté. Les stades sont, à ce stade du projet,
déterminés par le seul critère de retard (le critère de dégradation de la
PD vient en semaine 5).

Usage : python pipeline/etape_06_moteur.py [AAAA-MM]   (défaut : 2007-12)
"""

import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ecl9 import macro, moteur, survie
from ecl9.definitions import ANNEES_TEST, SEUIL_RETARD_STADE2
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIES = RACINE / "sorties"
RESULTATS = RACINE / "rapport" / "resultats"
INTER = DOSSIER_DONNEES / "intermediaire"


def portefeuille(arrete: pd.Period, octroi: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    """Prêts actifs et non en défaut à l'arrêté, avec leurs variables de survie."""
    morceaux = []
    for a in ANNEES_TEST:
        if a > arrete.year:
            continue
        p = pd.read_parquet(INTER / "panneau" / f"millesime_{a}.parquet")
        p["period"] = pd.PeriodIndex(p["period"], freq="M")
        p = p[(p["period"] == arrete) & p["defaut"].eq(0) & p["current_upb"].gt(0)]
        morceaux.append(p)
    p = pd.concat(morceaux, ignore_index=True)
    p = survie.preparer(p, octroi, m)
    # Durée restante manquante (rare) : durée initiale moins l'âge.
    p["remaining_months_to_maturity"] = (
        p["remaining_months_to_maturity"]
        .fillna(p["orig_loan_term"] - p["loan_age"])
        .clip(lower=1)
        .astype(int)
    )
    return p


def main(arrete: pd.Period) -> pd.DataFrame:
    t0 = time.time()
    octroi = pd.read_parquet(INTER / "octroi.parquet")
    m = macro.charger(DOSSIER_DONNEES / "brut" / "fred")
    with open(SORTIES / "survie" / "modele.pkl", "rb") as f:
        modeles_survie = pickle.load(f)
    modele_survie = modeles_survie[modeles_survie["retenu"]]
    with open(SORTIES / "lgd" / "modele.pkl", "rb") as f:
        modele_lgd = pickle.load(f)

    p = portefeuille(arrete, octroi, m)
    pred = pd.read_parquet(SORTIES / "pd12" / "predictions_test.parquet")
    pred["period"] = pd.PeriodIndex(pred["period"], freq="M")
    p = p.merge(
        pred[pred["period"] == arrete][["loan_id", "pd_logistique", "pd_lightgbm"]],
        on="loan_id",
        how="inner",
        validate="one_to_one",
    )
    print(f"{arrete} : {len(p):,} prêts actifs ({time.time() - t0:.0f} s)")

    restants = p["remaining_months_to_maturity"].to_numpy(dtype=int)
    stade = np.where(p["retard"].fillna(0).to_numpy() >= SEUIL_RETARD_STADE2, 2, 1)
    figee = pd.DataFrame([m.loc[arrete]] * restants.max(), columns=m.columns)
    figee.index = pd.period_range(arrete + 1, periods=len(figee), freq="M")
    h = moteur.projeter_hasards(modele_survie, p, arrete, figee, int(restants.max()))

    x_lgd = pd.DataFrame(
        {
            "orig_ltv": p["orig_ltv"],
            "credit_score": p["credit_score"],
            "ratio_crd": p["current_upb"] / p["orig_upb"],
            "mi_pct": p["mi_pct"],
            "age_defaut": p["loan_age"],
        }
    )
    lgd = modele_lgd.predire(x_lgd)
    crd = p["current_upb"].to_numpy(dtype=float)
    taux = p["current_interest_rate"].to_numpy(dtype=float) / 100

    resultats = p[["loan_id", "annee_octroi", "current_upb"]].assign(stade=stade, lgd=lgd)
    for nom in ("logistique", "lightgbm"):
        pd12 = p[f"pd_{nom}"].to_numpy()
        resultats[f"ecl_{nom}"] = moteur.provisions(stade, crd, taux, restants, lgd, pd12, h)
        resultats[f"pd12_{nom}"] = pd12
    print(f"Provisions calculées ({time.time() - t0:.0f} s)")
    return resultats


def synthese(r: pd.DataFrame) -> pd.DataFrame:
    def agreger(g):
        return pd.Series(
            {
                "prets": len(g),
                "encours": g["current_upb"].sum(),
                "ecl_logistique": g["ecl_logistique"].sum(),
                "ecl_lightgbm": g["ecl_lightgbm"].sum(),
                "taux_couverture_logistique": g["ecl_logistique"].sum() / g["current_upb"].sum(),
                "taux_couverture_lightgbm": g["ecl_lightgbm"].sum() / g["current_upb"].sum(),
                "lgd_moyenne_ponderee": np.average(g["lgd"], weights=g["current_upb"]),
            }
        )

    par_stade = r.groupby("stade").apply(agreger, include_groups=False)
    total = agreger(r).to_frame("total").T
    t = pd.concat([par_stade.rename(index=lambda s: f"stade {s}"), total])
    t["ecart_lightgbm_vs_logistique"] = t["ecl_lightgbm"] / t["ecl_logistique"] - 1
    return t


if __name__ == "__main__":
    arrete = pd.Period(sys.argv[1] if len(sys.argv) > 1 else "2007-12", "M")
    r = main(arrete)
    (SORTIES / "moteur").mkdir(parents=True, exist_ok=True)
    r.to_parquet(SORTIES / "moteur" / f"provisions_{arrete}.parquet", index=False)
    t = synthese(r)
    t.to_csv(RESULTATS / f"moteur_{arrete}.csv")
    print(t.round(4).to_string())
