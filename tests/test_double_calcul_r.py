"""Double calcul : le script R indépendant retrouve les provisions du moteur (D-033)."""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ecl9 import moteur

SCRIPT = Path(__file__).parent / "r" / "double_calcul.R"


def entrees_simulees(n: int = 50, mois: int = 360, graine: int = 20261112) -> pd.DataFrame:
    rng = np.random.default_rng(graine)
    restants = rng.integers(3, mois + 1, n)
    df = pd.DataFrame(
        {
            "id": np.arange(n),
            "stade": rng.choice([1, 2, 3], n, p=[0.6, 0.3, 0.1]),
            "crd": rng.uniform(20_000, 400_000, n),
            "taux": rng.choice([0.0, 0.045, 0.0625, 0.08], n),
            "restants": restants,
            "lgd": rng.uniform(0.05, 0.6, n),
            "pd12": rng.uniform(0.0, 0.4, n),
        }
    )
    df.loc[0, "pd12"] = 0.0
    h = rng.uniform(0.0002, 0.02, (n, mois))
    return pd.concat([df, pd.DataFrame(h, columns=[f"h_{k + 1}" for k in range(mois)])], axis=1)


def comparer(entrees: pd.DataFrame, dossier: Path) -> pd.DataFrame:
    """Provisions du moteur Python et du script R, prêt par prêt."""
    h = entrees.filter(like="h_").to_numpy()
    python = moteur.provisions(
        entrees["stade"].to_numpy(),
        entrees["crd"].to_numpy(),
        entrees["taux"].to_numpy(),
        entrees["restants"].to_numpy(),
        entrees["lgd"].to_numpy(),
        entrees["pd12"].to_numpy(),
        h,
    )
    chemin_e, chemin_s = dossier / "entrees.csv", dossier / "sorties.csv"
    entrees.to_csv(chemin_e, index=False, float_format="%.17g")
    subprocess.run(["Rscript", str(SCRIPT), str(chemin_e), str(chemin_s)], check=True)
    r = pd.read_csv(chemin_s)
    return pd.DataFrame({"id": entrees["id"], "python": python, "r": r["ecl"].to_numpy()})


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R non installé")
def test_double_calcul_r_sur_50_prets_simules(tmp_path):
    c = comparer(entrees_simulees(), tmp_path)
    ecart = np.abs(c["python"] - c["r"]) / np.maximum(np.abs(c["r"]), 1e-12)
    assert (ecart < 1e-8).all(), c[ecart >= 1e-8]
    assert c["python"].sum() > 0
