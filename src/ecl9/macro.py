"""Table macroéconomique mensuelle à partir des séries FRED (D-012, D-019).

Chaque variable est alignée sur ce qui est **connu** à la fin du mois
d'arrêté : chômage décalé d'un mois, Case-Shiller de deux mois, taux en
moyenne du mois.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DECALAGES_PUBLICATION = {"UNRATE": 1, "CSUSHPISA": 2, "MORTGAGE30US": 0, "DGS10": 0}


def lire_serie(chemin: Path) -> pd.Series:
    """Série FRED (CSV ``observation_date,SERIE``) ramenée en moyenne mensuelle."""
    df = pd.read_csv(chemin)
    nom = df.columns[1]
    valeurs = pd.to_numeric(df[nom], errors="coerce")
    mois = pd.to_datetime(df["observation_date"]).dt.to_period("M")
    return valeurs.groupby(mois).mean().rename(nom)


def table_macro(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Variables macro du modèle, indexées par mois d'arrêté.

    - ``chomage`` : taux de chômage connu à l'arrêté ;
    - ``chomage_var12`` : sa variation sur 12 mois, en points ;
    - ``hpi_var12`` : variation relative sur 12 mois de l'indice Case-Shiller ;
    - ``taux_30a`` et ``taux_10a`` : moyennes du mois, en %.
    """
    decalees = {}
    for nom, serie in series.items():
        s = serie.sort_index().asfreq("M")
        decalees[nom] = s.shift(DECALAGES_PUBLICATION[nom])
    m = pd.DataFrame(decalees)
    return pd.DataFrame(
        {
            "chomage": m["UNRATE"],
            "chomage_var12": m["UNRATE"] - m["UNRATE"].shift(12),
            "hpi_var12": m["CSUSHPISA"] / m["CSUSHPISA"].shift(12) - 1,
            "taux_30a": m["MORTGAGE30US"],
            "taux_10a": m["DGS10"],
        }
    )


def charger(dossier: Path) -> pd.DataFrame:
    return table_macro({n: lire_serie(dossier / f"{n}.csv") for n in DECALAGES_PUBLICATION})


def indice_prix(dossier: Path) -> pd.Series:
    """Niveau de l'indice Case-Shiller connu à la fin de chaque mois (décalé de 2 mois)."""
    s = lire_serie(dossier / "CSUSHPISA.csv").sort_index().asfreq("M")
    return s.shift(DECALAGES_PUBLICATION["CSUSHPISA"]).rename("hpi")


# Indices FHFA trimestriels par État (D-041) : la valeur d'un trimestre est
# publiée environ deux mois après sa fin, soit 4 mois après son premier mois.
DECALAGE_FHFA_MOIS = 4


def indices_prix_etats(dossier: Path) -> pd.DataFrame:
    """Niveau connu à la fin de chaque mois de l'indice FHFA de chaque État."""
    series = {}
    for chemin in sorted(dossier.glob("*STHPI.csv")):
        s = lire_serie(chemin)
        connu = s.copy()
        connu.index = s.index + DECALAGE_FHFA_MOIS
        mois = pd.period_range(connu.index.min(), connu.index.max() + 2, freq="M")
        series[chemin.stem.removesuffix("STHPI")] = connu.reindex(mois).ffill()
    return pd.DataFrame(series)
