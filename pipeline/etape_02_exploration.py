"""Étape 2 : analyse exploratoire descriptive, sans aucun modèle.

Taux de défaut à 12 mois par année d'octroi et par année d'arrêté, pour voir
la crise arriver dans les données avant d'écrire le moindre modèle.

Sortie : sorties/exploration/taux_defaut_12m.csv
"""

from pathlib import Path

import pandas as pd

from ecl9.telechargement import DOSSIER_DONNEES

ENTREE = DOSSIER_DONNEES / "intermediaire"
SORTIE = Path(__file__).resolve().parents[1] / "sorties" / "exploration"


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    e = pd.read_parquet(ENTREE / "echantillon_pd12.parquet")
    o = pd.read_parquet(ENTREE / "octroi.parquet", columns=["loan_id", "cohorte"])
    e = e.merge(o, on="loan_id", how="left", validate="many_to_one")
    e["annee_arrete"] = e["period"].dt.year
    table = (
        e.pivot_table(
            index="cohorte",
            columns="annee_arrete",
            values="cible_defaut_12m",
            aggfunc="mean",
        )
        .mul(100)
        .round(2)
    )
    table.to_csv(SORTIE / "taux_defaut_12m.csv")
    print("Taux de défaut à 12 mois (%), cohorte × année d'arrêté")
    print(table.to_string())


if __name__ == "__main__":
    main()
