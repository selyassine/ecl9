"""Prêts régularisés après un premier défaut (D-053).

Le panneau de survie s'arrête au premier défaut (D-001). Un prêt revenu sous
le seuil de défaut reste pourtant au bilan : il est provisionné en stade 2
avec une table de hasards propre, estimée sur les prêts régularisés de la
période d'entraînement. Les hasards dépendent du seul nombre de mois écoulés
depuis la régularisation, par bandes : c'est une table d'expérience, pas un
modèle à variables.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ecl9.donnees import marquer_defaut

BORNES_BANDES = (3, 6, 12, 24)  # bandes : 1-3, 4-6, 7-12, 13-24, 25 mois et plus
NOMS_BANDES = ("1-3", "4-6", "7-12", "13-24", "25+")


def bande(mois_depuis_regul: np.ndarray) -> np.ndarray:
    """Indice de bande (0 à 4) pour un nombre de mois depuis la régularisation ≥ 1."""
    return np.searchsorted(np.array(BORNES_BANDES), np.asarray(mois_depuis_regul), side="left")


def etats_apres_defaut(suivi: pd.DataFrame) -> pd.DataFrame:
    """Lignes du suivi à partir du premier défaut, avec l'état du prêt chaque mois.

    Colonnes ajoutées : ``en_defaut`` (définition D-001 ce mois-ci) et
    ``mois_depuis_regul`` (nombre de mois consécutifs hors défaut, ce mois
    compris ; 0 en défaut).
    """
    s = suivi.sort_values(["loan_id", "period"]).reset_index(drop=True)
    defaut = marquer_defaut(s)
    deja = defaut.groupby(s["loan_id"]).cumsum() > 0
    s = s[deja].copy()
    s["en_defaut"] = defaut[deja].to_numpy()
    # Compteur remis à zéro à chaque mois en défaut.
    episode = s["en_defaut"].groupby(s["loan_id"]).cumsum()
    s["mois_depuis_regul"] = (~s["en_defaut"]).groupby([s["loan_id"], episode]).cumsum()
    return s


def transitions(etats: pd.DataFrame) -> pd.DataFrame:
    """Un prêt-mois régularisé par ligne, avec ce qui arrive le mois suivant.

    ``redefaut`` : le mois suivant est en défaut ; ``rembt`` : le prêt est
    remboursé (code 01) le mois suivant. Le dernier mois observé d'un prêt
    n'a pas de suite et n'est pas compté.
    """
    e = etats
    suivant_defaut = e.groupby("loan_id")["en_defaut"].shift(-1)
    code = e["zero_balance_code"].astype("string").str.strip().str.zfill(2)
    suivant_code = code.groupby(e["loan_id"]).shift(-1)
    garde = (~e["en_defaut"]) & suivant_defaut.notna() & e["current_upb"].gt(0)
    t = e.loc[garde, ["loan_id", "period", "mois_depuis_regul"]].copy()
    t["redefaut"] = suivant_defaut[garde].astype(bool).to_numpy()
    t["rembt"] = (suivant_code[garde].eq("01").fillna(False) & ~t["redefaut"]).to_numpy()
    return t


def table_hasards(t: pd.DataFrame) -> pd.DataFrame:
    """Hasards mensuels de nouveau défaut et de remboursement, par bande."""
    b = bande(t["mois_depuis_regul"].to_numpy())
    g = t.groupby(b)
    table = pd.DataFrame(
        {
            "prets_mois": g.size(),
            "redefauts": g["redefaut"].sum(),
            "remboursements": g["rembt"].sum(),
        }
    ).reindex(range(len(NOMS_BANDES)), fill_value=0)
    table["hasard_redefaut"] = table["redefauts"] / table["prets_mois"].where(
        table["prets_mois"] > 0
    )
    table["hasard_rembt"] = table["remboursements"] / table["prets_mois"].where(
        table["prets_mois"] > 0
    )
    table.insert(0, "bande", NOMS_BANDES)
    return table.fillna(0.0)


def projeter(table: pd.DataFrame, mois_depuis_regul: np.ndarray, n_mois: int):
    """Hasards (prêts × mois) de nouveau défaut et de remboursement.

    Le mois ``j`` (1 à ``n_mois``) après l'arrêté suit ``mois_depuis_regul + j - 1``
    mois passés hors défaut.
    """
    k = np.asarray(mois_depuis_regul)[:, None] + np.arange(n_mois)[None, :]
    b = bande(np.maximum(k, 1))
    return (
        table["hasard_redefaut"].to_numpy()[b],
        table["hasard_rembt"].to_numpy()[b],
    )
