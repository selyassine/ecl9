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

from ecl9 import donnees, lgd, macro, regularises
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "sorties" / "lgd"
RESULTATS = RACINE / "rapport" / "resultats"
BRUT = DOSSIER_DONNEES / "brut" / "freddie"
FIN_DEFAUT_APP = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M")
FIN_RESOLUTION_APP = FIN_DEFAUT_APP + 12
FIN_DEFAUT_TEST = pd.Period("2010-12", "M")


COLONNES_ETATS = [
    "loan_id",
    "period",
    "current_upb",
    "en_defaut",
    "mois_depuis_regul",
    "loan_age",
    "remaining_months_to_maturity",
    "current_interest_rate",
]


def defauts_du_millesime(
    annee: int, fin_observation, etats_arretes: list | None = None, trans: list | None = None
):
    """Défauts du millésime et leur résolution.

    ``etats_arretes`` reçoit l'état des prêts déjà passés par le défaut à
    chaque arrêté trimestriel (D-043, D-053) ; ``trans`` reçoit leurs
    transitions mensuelles après régularisation (D-053).
    """
    s = donnees.lire_suivi(BRUT / f"sample_perf_{annee}.txt")
    r = donnees.resolutions_defaut(s, fin_observation)
    if etats_arretes is not None or trans is not None:
        if fin_observation is not None:
            s = s[s["period"] <= fin_observation]
        e = regularises.etats_apres_defaut(s)
        if etats_arretes is not None:
            etats_arretes.append(e.loc[e["period"].dt.month.isin([3, 6, 9, 12]), COLONNES_ETATS])
        if trans is not None:
            trans.append(regularises.transitions(e))
    return r.assign(annee_octroi=annee)


def variables(defauts: pd.DataFrame, octroi: pd.DataFrame, etats, hpi) -> pd.DataFrame:
    d = defauts.merge(
        octroi[
            [
                "loan_id",
                "orig_ltv",
                "orig_cltv",
                "credit_score",
                "mi_pct",
                "orig_upb",
                "property_state",
                "first_payment_date",
            ]
        ],
        on="loan_id",
        how="left",
        validate="one_to_one",
    )
    d["ratio_crd"] = d["crd_defaut"] / d["orig_upb"]
    # CLTV réévaluée à la date du défaut avec l'indice de l'État (D-047).
    d["cltv_reevaluee"] = lgd.cltv_reevaluee(
        d.assign(current_upb=d["crd_defaut"]),
        pd.PeriodIndex(d["first_payment_date"], freq="M") - 1,
        pd.PeriodIndex(d["mois_defaut"], freq="M"),
        etats,
        hpi,
    )
    return d.drop(columns=["orig_cltv", "property_state", "first_payment_date"])


TRANCHES_CLTV = [0, 70, 80, 90, 100, 110, 130, np.inf]


def severite_par_tranche(defauts: pd.DataFrame) -> pd.DataFrame:
    """Sévérité moyenne des pertes par tranche de CLTV réévaluée et échantillon (D-052)."""
    p = defauts[defauts["resolution"].eq("perte")]
    tranche = pd.cut(p["cltv_reevaluee"], TRANCHES_CLTV, right=False)
    t = p.groupby([tranche, "echantillon"], observed=True)["severite"].agg(["size", "mean"])
    t = t.unstack("echantillon")  # noqa: PD010
    t.columns = [f"{'pertes' if a == 'size' else 'severite_moyenne'}_{b}" for a, b in t.columns]
    t.index = t.index.astype(str)
    return t.rename_axis("cltv_reevaluee").reset_index()


def specifications(app: pd.DataFrame, test: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    """LGD prévue et réalisée sur le test pour chaque jeu de variables essayé (D-047)."""
    essais = {
        "D-028 : LTV d'octroi et ratio de capital": lgd.VARIABLES_V1,
        "D-047 retenu : CLTV réévaluée": lgd.VARIABLES,
        "CLTV réévaluée sans l'âge": ("cltv_reevaluee", "credit_score", "mi_pct"),
        "D-028 + CLTV réévaluée": (*lgd.VARIABLES_V1, "cltv_reevaluee"),
        "D-028 + CLTV réévaluée + prix sur un an": (
            *lgd.VARIABLES_V1,
            "cltv_reevaluee",
            "hpi_var12",
        ),
        "D-028 + CLTV réévaluée + prix + chômage sur un an": (
            *lgd.VARIABLES_V1,
            "cltv_reevaluee",
            "hpi_var12",
            "chomage_var12",
        ),
    }
    jeux = {}
    for nom, d in (("entrainement", app), ("test", test)):
        d = d[d["resolution"].isin(["perte", "regularisation"])].copy()
        for c in ("hpi_var12", "chomage_var12"):
            d[c] = m[c].reindex(pd.PeriodIndex(d["mois_defaut"], freq="M")).to_numpy()
        jeux[nom] = d
    lignes = []
    for nom, v in essais.items():
        modele = lgd.ajuster(jeux["entrainement"], v)
        t = jeux["test"]
        pertes = t[t["resolution"].eq("perte")]
        lignes.append(
            {
                "specification": nom,
                "lgd_prevue_ponderee": np.average(modele.predire(t), weights=t["crd_defaut"]),
                "lgd_realisee_ponderee": np.average(lgd.lgd_realisee(t), weights=t["crd_defaut"]),
                "part_regularisation_prevue": modele.p_regularisation(t).mean(),
                "part_regularisation_realisee": t["resolution"].eq("regularisation").mean(),
                "severite_prevue": modele.severite_attendue(pertes).mean(),
                "severite_realisee": pertes["severite"].mean(),
            }
        )
    return pd.DataFrame(lignes)


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
    trans_app: list = []
    app = pd.concat(
        [defauts_du_millesime(a, FIN_RESOLUTION_APP, trans=trans_app) for a in ANNEES_ENTRAINEMENT],
        ignore_index=True,
    )
    app = app[app["mois_defaut"] <= FIN_DEFAUT_APP]
    etats_arretes: list = []
    trans_test: list = []
    test = pd.concat(
        [defauts_du_millesime(a, None, etats_arretes, trans_test) for a in ANNEES_TEST],
        ignore_index=True,
    )
    test = test[test["mois_defaut"].dt.year.between(2006, FIN_DEFAUT_TEST.year)]
    dossier_fred = DOSSIER_DONNEES / "brut" / "fred"
    m = macro.charger(dossier_fred)
    hpi = macro.indice_prix(dossier_fred)
    etats = macro.indices_prix_etats(dossier_fred / "etats")
    app, test = variables(app, octroi, etats, hpi), variables(test, octroi, etats, hpi)
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
    essais = specifications(app, test, m)
    essais.to_csv(RESULTATS / "lgd_specifications.csv", index=False)
    print(essais.round(3).to_string(index=False))
    print(f"Délai médian de résolution des pertes : {modele.delai_resolution_mois:.0f} mois")
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
    # État des prêts passés par le défaut à chaque arrêté trimestriel (D-043, D-053).
    etats = pd.concat(etats_arretes, ignore_index=True)
    etats.assign(period=etats["period"].dt.to_timestamp()).to_parquet(
        DOSSIER_DONNEES / "intermediaire" / "crd_defauts_arretes.parquet", index=False
    )

    # Table des prêts régularisés (D-053) : transitions jusqu'à fin 2005 seulement.
    t_app = pd.concat(trans_app, ignore_index=True)
    t_app = t_app[t_app["period"] < FIN_DEFAUT_APP]
    table = regularises.table_hasards(t_app)
    with open(SORTIE / "regularises.pkl", "wb") as f:
        pickle.dump(table, f)
    table.to_csv(RESULTATS / "regularises_table.csv", index=False)
    print(table.round(4).to_string(index=False))
    t_test = pd.concat(trans_test, ignore_index=True)
    t_test = t_test[
        (t_test["period"] >= pd.Period("2006-01", "M")) & (t_test["period"] < FIN_DEFAUT_TEST)
    ]
    b = regularises.bande(t_test["mois_depuis_regul"].to_numpy())
    controle = pd.DataFrame(
        {
            "annee": t_test["period"].dt.year.to_numpy(),
            "redefaut": t_test["redefaut"].to_numpy(),
            "rembt": t_test["rembt"].to_numpy(),
            "redefaut_attendu": table["hasard_redefaut"].to_numpy()[b],
            "rembt_attendu": table["hasard_rembt"].to_numpy()[b],
        }
    )
    controle = controle.groupby("annee").agg(
        prets_mois=("redefaut", "size"),
        redefauts_observes=("redefaut", "sum"),
        redefauts_attendus=("redefaut_attendu", "sum"),
        remboursements_observes=("rembt", "sum"),
        remboursements_attendus=("rembt_attendu", "sum"),
    )
    controle.to_csv(RESULTATS / "regularises_test.csv")
    print(controle.round(1).to_string())
    severite_par_tranche(toutes).to_csv(RESULTATS / "lgd_severite_par_cltv.csv", index=False)
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
