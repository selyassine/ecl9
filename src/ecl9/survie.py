"""PD à maturité par survie en temps discret (D-023, D-024).

Le hasard mensuel de défaut est une régression logistique sur les prêts-mois,
avec une base par bande d'âge (la table de mortalité), les variables d'octroi
et la macro du mois.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ecl9.definitions import GRAINE

BORNES_AGE = (0, 6, 12, 24, 36, 48, 60)
VARIABLES_OCTROI_NUM = (
    "credit_score",
    "orig_ltv",
    "orig_cltv",
    "orig_dti",
    "orig_interest_rate",
    "log_orig_upb",
    "orig_loan_term",
    "mi_pct",
)
VARIABLES_MACRO = ("chomage", "chomage_var12", "hpi_var12", "taux_10a", "ecart_taux")
VARIABLES_CAT = (
    "bande_age",
    "loan_purpose",
    "occupancy_status",
    "channel",
    "property_type",
    "first_time_homebuyer",
    "num_units",
    "num_borrowers",
    "property_state",
)
VARIABLES_NUM = VARIABLES_OCTROI_NUM + VARIABLES_MACRO
VARIABLES = VARIABLES_NUM + VARIABLES_CAT
COLONNES_OCTROI = (
    "loan_id",
    "credit_score",
    "orig_ltv",
    "orig_cltv",
    "orig_dti",
    "orig_interest_rate",
    "orig_upb",
    "orig_loan_term",
    "mi_pct",
    "loan_purpose",
    "occupancy_status",
    "channel",
    "property_type",
    "first_time_homebuyer",
    "num_units",
    "num_borrowers",
    "property_state",
)


def bande_age(age) -> pd.Series:
    """Bande d'âge en mois : 0-6, 7-12, 13-24, 25-36, 37-48, 49-60, 61+."""
    age = pd.Series(np.asarray(age, dtype=float))
    etiquettes = ["0-6", "7-12", "13-24", "25-36", "37-48", "49-60", "61+"]
    bornes = [-np.inf, *BORNES_AGE[1:], np.inf]
    return pd.cut(age, bornes, labels=etiquettes, right=True).astype("string")


def preparer(panneau: pd.DataFrame, octroi: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    """Variables du hasard pour chaque prêt-mois du panneau."""
    p = panneau.copy()
    p["period"] = pd.PeriodIndex(p["period"], freq="M")
    p = p.merge(octroi[list(COLONNES_OCTROI)], on="loan_id", how="left", validate="many_to_one")
    p = p.merge(macro, left_on="period", right_index=True, how="left", validate="many_to_one")
    p["log_orig_upb"] = np.log(p["orig_upb"])
    p["ecart_taux"] = p["current_interest_rate"] - p["taux_30a"]
    p["bande_age"] = bande_age(p["loan_age"]).to_numpy()
    return p


def echantillonner(df: pd.DataFrame, part: float = 0.05, graine: int = GRAINE) -> pd.DataFrame:
    """Tous les défauts, une part des non-défauts pondérée par 1 / part (D-023)."""
    rng = np.random.default_rng(graine)
    garde = df["defaut"].eq(1).to_numpy() | (rng.random(len(df)) < part)
    e = df[garde].copy()
    e["poids"] = np.where(e["defaut"].eq(1), 1.0, 1.0 / part)
    return e


def _x(df: pd.DataFrame) -> pd.DataFrame:
    x = df[list(VARIABLES)].copy()
    for c in VARIABLES_CAT:
        texte = x[c].astype("string")
        x[c] = texte.astype(object).where(texte.notna(), None)
    return x


def modele() -> Pipeline:
    numeriques = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True), StandardScaler()
    )
    categorielles = make_pipeline(
        SimpleImputer(strategy="constant", fill_value="manquant"),
        OneHotEncoder(handle_unknown="ignore"),
    )
    preparation = ColumnTransformer(
        [("num", numeriques, list(VARIABLES_NUM)), ("cat", categorielles, list(VARIABLES_CAT))]
    )
    return Pipeline([("preparation", preparation), ("logit", LogisticRegression(max_iter=2000))])


def ajuster(echantillon: pd.DataFrame) -> Pipeline:
    poids = echantillon["poids"] if "poids" in echantillon else None
    return modele().fit(
        _x(echantillon), echantillon["defaut"].to_numpy(), logit__sample_weight=poids
    )


def hasards(m: Pipeline, df: pd.DataFrame) -> np.ndarray:
    return m.predict_proba(_x(df))[:, 1]


# --------------------------------------------------------- structure par terme


def pd_cumulee(h) -> float:
    """``1 - Π (1 - h)`` : PD cumulée sur la durée des hasards."""
    return float(1 - np.prod(1 - np.asarray(h, dtype=float)))


def ancrer(h, pd_cible: float, horizon: int = 12, tolerance: float = 1e-12) -> np.ndarray:
    """Multiplie les ``horizon`` premiers hasards par ``c`` pour atteindre ``pd_cible`` (D-024).

    ``c`` est trouvé par dichotomie ; les hasards au-delà de l'horizon sont
    inchangés et chaque hasard ancré est plafonné à 1.
    """
    h = np.asarray(h, dtype=float).copy()
    k = min(horizon, len(h))
    tete = h[:k]
    if not 0 <= pd_cible < 1:
        raise ValueError("pd_cible doit être dans [0, 1[")
    if pd_cible == 0 or tete.sum() == 0:
        if pd_cible > 0:
            raise ValueError("hasards nuls : impossible d'atteindre une PD positive")
        h[:k] = 0.0
        return h

    def ecart(c: float) -> float:
        return pd_cumulee(np.minimum(c * tete, 1.0)) - pd_cible

    bas, haut = 0.0, 1.0
    while ecart(haut) < 0:
        haut *= 2
    while haut - bas > tolerance * max(1.0, haut):
        milieu = (bas + haut) / 2
        bas, haut = (milieu, haut) if ecart(milieu) < 0 else (bas, milieu)
    h[:k] = np.minimum(haut * tete, 1.0)
    return h


def projeter(
    m: Pipeline, pret: pd.Series, arrete: pd.Period, macro_future: pd.DataFrame, n_mois: int
) -> np.ndarray:
    """Hasards des ``n_mois`` suivant ``arrete`` pour un prêt, selon une trajectoire macro.

    ``pret`` porte les variables d'octroi, ``loan_age`` et
    ``current_interest_rate`` à l'arrêté. ``macro_future`` est indexée par mois
    et doit couvrir ``arrete + 1`` à ``arrete + n_mois`` ; au-delà de sa
    dernière date, la dernière valeur est prolongée.
    """
    mois = pd.period_range(arrete + 1, periods=n_mois, freq="M")
    trajectoire = macro_future.reindex(mois).ffill()
    if trajectoire.isna().any().any():
        raise ValueError("trajectoire macro absente au début de la projection")
    lignes = pd.DataFrame([pret] * n_mois).reset_index(drop=True)
    for c in trajectoire.columns:
        lignes[c] = trajectoire[c].to_numpy()
    lignes["loan_age"] = pret["loan_age"] + np.arange(1, n_mois + 1)
    lignes["bande_age"] = bande_age(lignes["loan_age"]).to_numpy()
    lignes["ecart_taux"] = pret["current_interest_rate"] - lignes["taux_30a"]
    if "log_orig_upb" not in lignes:
        lignes["log_orig_upb"] = np.log(lignes["orig_upb"])
    return hasards(m, lignes)
