"""Étape 9 : intervalle bootstrap de l'écart et grilles de sensibilité (D-037, D-038).

Lit le détail par prêt de l'étape 7 (``sorties/trimestriel/prets/``, hors Git)
et les provisions par scénario (``rapport/resultats/trimestriel_scenarios.csv``).

Usage : python pipeline/etape_09_sensibilites.py   (après l'étape 7, deux modes)
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ecl9.definitions import SEUIL_RETARD_STADE2

RACINE = Path(__file__).resolve().parents[1]
DETAIL = RACINE / "sorties" / "trimestriel" / "prets"
RESULTATS = RACINE / "rapport" / "resultats"
GRAINE = 20261112
TIRAGES = 1_000
PAQUET = 50
SEUILS = (1.5, 2.0, 2.5, 3.0, 4.0)
PONDERATIONS = {
    "50/30/20 (référence)": (0.50, 0.30, 0.20),
    "60/20/20": (0.60, 0.20, 0.20),
    "40/40/20": (0.40, 0.40, 0.20),
    "1/3 chacun": (1 / 3, 1 / 3, 1 / 3),
    "central seul": (1.0, 0.0, 0.0),
    "défavorable seul": (0.0, 1.0, 0.0),
    "favorable seul": (0.0, 0.0, 1.0),
}


def bootstrap(log: np.ndarray, lgbm: np.ndarray, rng: np.random.Generator) -> pd.Series:
    """Centiles de l'écart sur ``TIRAGES`` tirages des prêts avec remise."""
    n = len(log)
    rel, abs_ = [], []
    for _ in range(TIRAGES // PAQUET):
        poids = rng.multinomial(n, np.full(n, 1 / n), size=PAQUET).astype(float)
        a, b = poids @ log, poids @ lgbm
        rel.append(b / a - 1)
        abs_.append(b - a)
    rel, abs_ = np.concatenate(rel), np.concatenate(abs_)
    return pd.Series(
        {
            "ecl_logistique": log.sum(),
            "ecl_lightgbm": lgbm.sum(),
            "ecart_relatif": lgbm.sum() / log.sum() - 1,
            "ecart_relatif_bas": np.quantile(rel, 0.025),
            "ecart_relatif_haut": np.quantile(rel, 0.975),
            "ecart_absolu": lgbm.sum() - log.sum(),
            "ecart_absolu_bas": np.quantile(abs_, 0.025),
            "ecart_absolu_haut": np.quantile(abs_, 0.975),
        }
    )


def grille_seuils(d: pd.DataFrame) -> list[dict]:
    lignes = []
    actifs = d[d["stade_logistique"] < 3]
    encours = d["crd"].sum()
    retard = actifs["retard"] >= SEUIL_RETARD_STADE2
    for nom in ("logistique", "lightgbm"):
        lignes.append(
            {
                "modele": nom,
                "seuil": "retard seul",
                "part_encours_stade2": actifs.loc[retard, "crd"].sum() / encours,
            }
        )
        for s in SEUILS:
            dans = retard | (actifs[f"ratio_{nom}"] >= s)
            lignes.append(
                {
                    "modele": nom,
                    "seuil": str(s),
                    "part_encours_stade2": actifs.loc[dans, "crd"].sum() / encours,
                }
            )
    return lignes


def grille_ponderations() -> pd.DataFrame:
    t = pd.read_csv(RESULTATS / "trimestriel_scenarios.csv")
    g = t.groupby(["arrete", "modele"]).sum(numeric_only=True)
    lignes = []
    for (arrete, modele), x in g.iterrows():
        for nom, (wc, wd, wf) in PONDERATIONS.items():
            for suffixe in ("", "_surcouche"):
                ecl = (
                    wc * x[f"ecl_central{suffixe}"]
                    + wd * x[f"ecl_defavorable{suffixe}"]
                    + wf * x[f"ecl_favorable{suffixe}"]
                )
                lignes.append(
                    {
                        "arrete": arrete,
                        "modele": modele,
                        "ponderations": nom,
                        "surcouche": bool(suffixe),
                        "ecl": ecl,
                        "ecart_a_figee": ecl / x["ecl"] - 1,
                    }
                )
    return pd.DataFrame(lignes)


def main() -> None:
    rng = np.random.default_rng(GRAINE)
    boot, seuils = [], []
    for fichier in sorted(DETAIL.glob("*.parquet")):
        arrete = fichier.stem
        d = pd.read_parquet(fichier)
        b = bootstrap(d["ecl_logistique"].to_numpy(), d["ecl_lightgbm"].to_numpy(), rng)
        boot.append(b.rename(arrete))
        seuils += [{"arrete": arrete, **ligne} for ligne in grille_seuils(d)]
        print(
            f"{arrete} : écart {b['ecart_relatif']:+.1%} "
            f"[{b['ecart_relatif_bas']:+.1%} ; {b['ecart_relatif_haut']:+.1%}]"
        )
    pd.DataFrame(boot).rename_axis("arrete").to_csv(RESULTATS / "bootstrap_ecart.csv")
    s = pd.DataFrame(seuils)
    s.to_csv(RESULTATS / "grille_seuils_stade2.csv", index=False)
    print(s.pivot_table(index="arrete", columns=["modele", "seuil"]).round(4).iloc[::4])
    p = grille_ponderations()
    p.to_csv(RESULTATS / "grille_ponderations.csv", index=False)
    print(p[p["arrete"] == "2007-12"].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
