"""Étape 1 : fichiers bruts Freddie Mac → panneau prêt-mois et échantillon PD 12 mois.

Entrées  : data/brut/freddie/sample_{orig,svcg}_AAAA.txt
Sorties  : data/intermediaire/octroi.parquet
           data/intermediaire/panneau.parquet
           data/intermediaire/echantillon_pd12.parquet
"""

from pathlib import Path

import pandas as pd

from ecl9 import donnees
from ecl9.telechargement import DOSSIER_DONNEES, lire_manifeste, verifier

BRUT = DOSSIER_DONNEES / "brut" / "freddie"
SORTIE = DOSSIER_DONNEES / "intermediaire"


def _parquet(df: pd.DataFrame, chemin: Path) -> None:
    df = df.copy()
    for col in df.columns:
        if isinstance(df[col].dtype, pd.PeriodDtype):
            df[col] = df[col].dt.to_timestamp()
    df.to_parquet(chemin, index=False)
    print(f"{chemin.relative_to(DOSSIER_DONNEES.parent)} : {len(df):,} lignes")


def main() -> None:
    problemes = verifier()
    if problemes:
        raise SystemExit("Données non conformes au verrou :\n" + "\n".join(problemes))
    annees = lire_manifeste()["freddie_mac"]["annees"]
    SORTIE.mkdir(parents=True, exist_ok=True)

    octroi = pd.concat(
        [donnees.lire_octroi(BRUT / f"sample_orig_{a}.txt") for a in annees], ignore_index=True
    )
    panneaux = [
        donnees.construire_panneau(donnees.lire_suivi(BRUT / f"sample_svcg_{a}.txt"))
        for a in annees
    ]
    panneau = pd.concat(panneaux, ignore_index=True)
    echantillon = donnees.echantillon_pd12(panneau)

    _parquet(octroi, SORTIE / "octroi.parquet")
    _parquet(panneau, SORTIE / "panneau.parquet")
    _parquet(echantillon, SORTIE / "echantillon_pd12.parquet")


if __name__ == "__main__":
    main()
