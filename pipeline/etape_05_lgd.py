"""Étape 5 : LGD en deux étapes (D-027, D-028).

Entrées : data/brut/freddie/sample_perf_AAAA.txt, data/intermediaire/octroi.parquet
Sorties : data/intermediaire/defauts.parquet, sorties/lgd/modele.pkl,
          rapport/resultats/lgd_*.csv
"""

import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ecl9 import donnees, lgd
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "sorties" / "lgd"
RESULTATS = RACINE / "rapport" / "resultats"
BRUT = DOSSIER_DONNEES / "brut" / "freddie"
FIN_DEFAUT_APP = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M")
FIN_RESOLUTION_APP = FIN_DEFAUT_APP + 12
FIN_DEFAUT_TEST = pd.Period("2010-12", "M")


def defauts_du_millesime(annee: int, fin_observation) -> pd.DataFrame:
    s = donnees.lire_suivi(BRUT / f"sample_perf_{annee}.txt")
    r = donnees.resolutions_defaut(s, fin_observation)
    return r.assign(annee_octroi=annee)


def variables(defauts: pd.DataFrame, octroi: pd.DataFrame) -> pd.DataFrame:
    d = defauts.merge(
        octroi[["loan_id", "orig_ltv", "credit_score", "mi_pct", "orig_upb"]],
        on="loan_id",
        how="left",
        validate="one_to_one",
    )
    d["ratio_crd"] = d["crd_defaut"] / d["orig_upb"]
    return d


def resume(d: pd.DataFrame, prevue: np.ndarray, groupe: str | None = None) -> pd.DataFrame:
    d = d.assign(
        lgd_prevue=prevue,
        lgd_realisee=lgd.lgd_realisee(d),
        poids=d["crd_defaut"],
        regul=d["resolution"].eq("regularisation"),
    )
    d = d[d["resolution"].isin(["perte", "regularisation"])]
    cles = [groupe] if groupe else [lambda _: "ensemble"]
    return d.groupby(cles).apply(
        lambda g: pd.Series(
            {
                "defauts_resolus": len(g),
                "part_regularisation": g["regul"].mean(),
                "severite_moyenne_pertes": g.loc[~g["regul"], "severite"].mean(),
                "lgd_realisee_ponderee": np.average(g["lgd_realisee"], weights=g["poids"]),
                "lgd_prevue_ponderee": np.average(g["lgd_prevue"], weights=g["poids"]),
            }
        ),
        include_groups=False,
    )


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    octroi = pd.read_parquet(DOSSIER_DONNEES / "intermediaire" / "octroi.parquet")
    app = pd.concat(
        [defauts_du_millesime(a, FIN_RESOLUTION_APP) for a in ANNEES_ENTRAINEMENT],
        ignore_index=True,
    )
    app = app[app["mois_defaut"] <= FIN_DEFAUT_APP]
    test = pd.concat([defauts_du_millesime(a, None) for a in ANNEES_TEST], ignore_index=True)
    test = test[test["mois_defaut"].dt.year.between(2006, FIN_DEFAUT_TEST.year)]
    app, test = variables(app, octroi), variables(test, octroi)
    print(f"Défauts : {len(app):,} entraînement, {len(test):,} test ({time.time() - t0:.0f} s)")
    print(app["resolution"].value_counts().to_string())

    modele = lgd.ajuster(app)
    with open(SORTIE / "modele.pkl", "wb") as f:
        pickle.dump(modele, f)

    tableaux = {
        "entrainement": resume(app, modele.predire(app)),
        "test": resume(test, modele.predire(test)),
        "test_par_annee_defaut": resume(
            test.assign(annee_defaut=test["mois_defaut"].dt.year),
            modele.predire(test),
            "annee_defaut",
        ),
    }
    for nom, t in tableaux.items():
        t.to_csv(RESULTATS / f"lgd_{nom}.csv")
        print(nom)
        print(t.round(3).to_string())

    toutes = pd.concat([app.assign(echantillon="entrainement"), test.assign(echantillon="test")])
    toutes.assign(
        mois_defaut=toutes["mois_defaut"].dt.to_timestamp(),
        mois_resolution=toutes["mois_resolution"].dt.to_timestamp(),
        mois_fin_defaut=toutes["mois_fin_defaut"].dt.to_timestamp(),
    ).to_parquet(DOSSIER_DONNEES / "intermediaire" / "defauts.parquet", index=False)
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
