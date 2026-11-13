"""Étape 8 : double calcul R sur 50 prêts réels du portefeuille au 31/12/2007 (D-033).

Tire 25 prêts en stade 1 et 25 en stade 2 parmi les provisions de l'étape 6,
reconstitue leurs entrées (CRD, taux, durée restante, LGD, PD à 12 mois de
LightGBM, hasards de survie non ancrés), fait recalculer la provision par le
script R indépendant ``tests/r/double_calcul.R`` et compare prêt par prêt.

Les entrées restent dans ``sorties/`` (données Freddie Mac, non versionnées) ;
seule la comparaison, sans identifiant de prêt, est publiée.

Usage : python pipeline/etape_08_double_calcul_r.py   (après l'étape 6)
"""

import pickle
import subprocess
import sys

import numpy as np
import pandas as pd

from ecl9 import macro, moteur

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import etape_06_moteur as e6

ARRETE = pd.Period("2007-12", "M")
GRAINE = 20261112
SCRIPT_R = e6.RACINE / "tests" / "r" / "double_calcul.R"


def main() -> pd.DataFrame:
    prov = pd.read_parquet(e6.SORTIES / "moteur" / f"provisions_{ARRETE}.parquet")
    rng = np.random.default_rng(GRAINE)
    tirage = pd.concat(
        [prov[prov["stade"] == s].sample(25, random_state=rng.integers(2**31)) for s in (1, 2)]
    )

    octroi = pd.read_parquet(e6.INTER / "octroi.parquet")
    m = macro.charger(e6.DOSSIER_DONNEES / "brut" / "fred")
    with open(e6.SORTIES / "survie" / "modele.pkl", "rb") as f:
        s = pickle.load(f)
    p = e6.portefeuille(ARRETE, octroi, m)
    p = p.set_index("loan_id").loc[tirage["loan_id"]].reset_index()

    restants = p["remaining_months_to_maturity"].to_numpy(dtype=int)
    n_mois = int(restants.max())
    figee = pd.DataFrame([m.loc[ARRETE]] * n_mois, columns=m.columns)
    figee.index = pd.period_range(ARRETE + 1, periods=n_mois, freq="M")
    h = moteur.projeter_hasards(s[s["retenu"]], p, ARRETE, figee, n_mois)

    entrees = pd.DataFrame(
        {
            "id": np.arange(1, len(p) + 1),
            "stade": tirage["stade"].to_numpy(),
            "crd": p["current_upb"].to_numpy(dtype=float),
            "taux": p["current_interest_rate"].to_numpy(dtype=float) / 100,
            "restants": restants,
            "lgd": tirage["lgd"].to_numpy(),
            "pd12": tirage["pd12_lightgbm"].to_numpy(),
        }
    )
    entrees = pd.concat(
        [entrees, pd.DataFrame(h, columns=[f"h_{k + 1}" for k in range(n_mois)])], axis=1
    )

    dossier = e6.SORTIES / "double_calcul_r"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin_e, chemin_s = dossier / "entrees.csv", dossier / "sorties_r.csv"
    entrees.to_csv(chemin_e, index=False, float_format="%.17g")
    subprocess.run(["Rscript", str(SCRIPT_R), str(chemin_e), str(chemin_s)], check=True)

    python = moteur.provisions(
        entrees["stade"].to_numpy(),
        entrees["crd"].to_numpy(),
        entrees["taux"].to_numpy(),
        restants,
        entrees["lgd"].to_numpy(),
        entrees["pd12"].to_numpy(),
        h,
    )
    r = pd.read_csv(chemin_s)["ecl"].to_numpy()
    c = pd.DataFrame(
        {
            "id": entrees["id"],
            "stade": entrees["stade"],
            "ecl_python": python,
            "ecl_r": r,
            "ecart_relatif": np.abs(python - r) / np.maximum(np.abs(r), 1e-12),
            "ecl_etape_6": tirage["ecl_lightgbm"].to_numpy(),
        }
    )
    return c


if __name__ == "__main__":
    c = main()
    c.to_csv(e6.RESULTATS / f"double_calcul_r_{ARRETE}.csv", index=False, float_format="%.10g")
    print(c.round(6).to_string(index=False))
    print(f"Écart relatif maximal Python / R : {c['ecart_relatif'].max():.2e}")
    print(
        f"Écart maximal avec l'étape 6 : {(c['ecl_python'] / c['ecl_etape_6'] - 1).abs().max():.2e}"
    )
    if c["ecart_relatif"].max() >= 1e-8:
        sys.exit("Double calcul en échec")
