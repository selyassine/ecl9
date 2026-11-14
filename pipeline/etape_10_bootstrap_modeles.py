"""Étape 10 : intervalle de l'écart avec réestimation des PD à 12 mois (D-042).

Chaque tirage réestime la logistique et LightGBM sur les prêts d'entraînement
tirés avec remise, tire le portefeuille avec remise, et recalcule la
provision ; la survie, le remboursement, la LGD et les stades restent ceux du
résultat principal. Les tirages sont sauvés un à un (reprise possible).

Usage : python pipeline/etape_10_bootstrap_modeles.py   (après les étapes 3 et 7)
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import etape_03_pd12 as e3
import etape_07_trimestriel as e7
from ecl9 import macro, moteur
from ecl9 import pd as pdm
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "sorties" / "bootstrap_modeles"
RESULTATS = RACINE / "rapport" / "resultats"
ARRETES = [pd.Period("2007-12", "M"), pd.Period("2008-12", "M")]
TIRAGES = 100
GRAINE = 20261112


def portefeuille(arrete, octroi, m, modeles, test):
    """Entrées fixes de la provision à l'arrêté, alignées sur le détail de l'étape 7."""
    _, survie_, lgd_, rembt = modeles
    detail = pd.read_parquet(e7.SORTIES / "trimestriel" / "prets" / f"{arrete}.parquet")
    p = e7.actifs(arrete, octroi, m)
    p = p.merge(detail[["loan_id", "stade_logistique", "stade_lightgbm"]], on="loan_id")
    x = test[test["period"] == arrete].drop_duplicates("loan_id")
    p = p.merge(x[["loan_id"]], on="loan_id")
    x = x.set_index("loan_id").loc[p["loan_id"]].reset_index()
    restants = p["remaining_months_to_maturity"].to_numpy(dtype=int)
    n = int(restants.max())
    traj = e7.trajectoire_figee(m, arrete, n)
    lgd = lgd_.predire(
        pd.DataFrame(
            {
                "orig_ltv": p["orig_ltv"],
                "credit_score": p["credit_score"],
                "ratio_crd": p["current_upb"] / p["orig_upb"],
                "mi_pct": p["mi_pct"],
                "age_defaut": p["loan_age"],
            }
        )
    )
    stade3 = detail[detail["stade_logistique"] == 3]["ecl_logistique"].to_numpy()
    return {
        "x": x,
        "stades": {nom: p[f"stade_{nom}"].to_numpy() for nom in e7.MODELES},
        "crd": p["current_upb"].to_numpy(dtype=float),
        "taux": p["current_interest_rate"].to_numpy(dtype=float) / 100,
        "restants": restants,
        "lgd": lgd,
        "h": moteur.projeter_hasards(survie_, p, arrete, traj, n),
        "hp": moteur.projeter_hasards(rembt, p, arrete, traj, n),
        "stade3": stade3,
    }


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    octroi = pd.read_parquet(e7.INTER / "octroi.parquet")
    m = macro.charger(e7.DOSSIER_DONNEES / "brut" / "fred")
    modeles = e7.charger_modeles()
    d = e3.charger()
    fin = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M")
    app = d[d["annee_octroi"].isin(ANNEES_ENTRAINEMENT) & (d["period"] <= fin)].reset_index(
        drop=True
    )
    test = d[d["annee_octroi"].isin(ANNEES_TEST)]
    reglage = pd.read_csv(RESULTATS / "pd12_reglage_lightgbm.csv").iloc[0]
    prets = {a: portefeuille(a, octroi, m, modeles, test) for a in ARRETES}
    print(f"Portefeuilles prêts ({time.time() - t0:.0f} s)")

    ids = app["loan_id"].to_numpy()
    uniques, inverse = np.unique(ids, return_inverse=True)
    lignes_par_pret = pd.Series(np.arange(len(app))).groupby(inverse).apply(np.array)

    for b in range(TIRAGES):
        fichier = SORTIE / f"tirage_{b:03d}.pkl"
        if fichier.exists():
            continue
        rng = np.random.default_rng([GRAINE, b])
        tires = rng.integers(0, len(uniques), len(uniques))
        lignes = np.concatenate(lignes_par_pret.iloc[tires].to_numpy())
        a = app.iloc[lignes]
        logit = pdm.ajuster_logistique(a, a[pdm.CIBLE])
        gbm = pdm.ajuster_lightgbm(
            a,
            a[pdm.CIBLE],
            reglage["num_leaves"],
            reglage["min_child_samples"],
            reglage["iterations"],
        )
        res = {}
        for arrete, q in prets.items():
            poids = rng.multinomial(len(q["crd"]), np.full(len(q["crd"]), 1 / len(q["crd"])))
            poids3 = rng.multinomial(
                len(q["stade3"]), np.full(len(q["stade3"]), 1 / len(q["stade3"]))
            )
            garde = poids > 0
            ecl3 = float(poids3 @ q["stade3"])
            for nom, pd12 in (
                ("logistique", pdm.predire_logistique(logit, q["x"])),
                ("lightgbm", gbm.predire(q["x"])),
            ):
                e = moteur.provisions(
                    q["stades"][nom][garde],
                    q["crd"][garde],
                    q["taux"][garde],
                    q["restants"][garde],
                    q["lgd"][garde],
                    pd12[garde],
                    q["h"][garde],
                    hasards_rembt=q["hp"][garde],
                )
                res[(str(arrete), nom)] = float(poids[garde] @ e) + ecl3
        pd.to_pickle(res, fichier)
        print(f"Tirage {b + 1}/{TIRAGES} ({time.time() - t0:.0f} s)", flush=True)

    tirages = pd.DataFrame([pd.read_pickle(f) for f in sorted(SORTIE.glob("tirage_*.pkl"))])
    lignes = []
    for arrete in ARRETES:
        a = str(arrete)
        rel = tirages[(a, "lightgbm")] / tirages[(a, "logistique")] - 1
        lignes.append(
            {
                "arrete": a,
                "tirages": len(rel),
                "ecart_relatif_median": rel.median(),
                "ecart_relatif_bas": rel.quantile(0.025),
                "ecart_relatif_haut": rel.quantile(0.975),
                "ecl_logistique_bas": tirages[(a, "logistique")].quantile(0.025),
                "ecl_logistique_haut": tirages[(a, "logistique")].quantile(0.975),
                "ecl_lightgbm_bas": tirages[(a, "lightgbm")].quantile(0.025),
                "ecl_lightgbm_haut": tirages[(a, "lightgbm")].quantile(0.975),
                "part_lightgbm_superieur": (rel > 0).mean(),
            }
        )
    t = pd.DataFrame(lignes)
    t.to_csv(RESULTATS / "bootstrap_modeles.csv", index=False)
    print(t.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
