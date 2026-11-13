"""Étape 1 : fichiers bruts Freddie Mac → panneau prêt-mois et échantillon PD 12 mois.

Entrées  : data/brut/freddie/sample_{orig,perf}_AAAA.txt
Sorties  : data/intermediaire/octroi.parquet
           data/intermediaire/panneau/millesime_AAAA.parquet (un fichier par millésime)
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

    (SORTIE / "panneau").mkdir(exist_ok=True)
    octrois, echantillons = [], []
    for annee in annees:
        o = donnees.lire_octroi(BRUT / f"sample_orig_{annee}.txt")
        o["annee_octroi"] = annee  # millésime du fichier (D-016)
        p = donnees.construire_panneau(donnees.lire_suivi(BRUT / f"sample_perf_{annee}.txt"))
        p["annee_octroi"] = annee
        echantillons.append(donnees.echantillon_pd12(p))
        octrois.append(o)
        print(
            f"{annee} : {len(o):,} prêts, {len(p):,} prêts-mois, {int(p['defaut'].sum()):,} défauts"
        )
        _parquet(p, SORTIE / "panneau" / f"millesime_{annee}.parquet")
        del p

    _parquet(pd.concat(octrois, ignore_index=True), SORTIE / "octroi.parquet")
    _parquet(pd.concat(echantillons, ignore_index=True), SORTIE / "echantillon_pd12.parquet")


if __name__ == "__main__":
    main()
