"""Probabilités de défaut.

Semaine 2 : PD à 12 mois, régression logistique de référence puis LightGBM
avec exactement les mêmes variables (D-019, D-020), validées hors période.

Semaine 3 : PD à maturité par un modèle de survie en temps discret.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ecl9.definitions import GRAINE

VARIABLES_NUM = (
    "credit_score",
    "orig_ltv",
    "orig_cltv",
    "orig_dti",
    "orig_interest_rate",
    "log_orig_upb",
    "orig_loan_term",
    "mi_pct",
    "loan_age",
    "ratio_crd",
    "ecart_taux",
    "chomage",
    "chomage_var12",
    "hpi_var12",
    "taux_10a",
)
VARIABLES_CAT = (
    "loan_purpose",
    "occupancy_status",
    "channel",
    "property_type",
    "first_time_homebuyer",
    "num_units",
    "num_borrowers",
    "property_state",
    "retard",
)
VARIABLES = VARIABLES_NUM + VARIABLES_CAT
CIBLE = "cible_defaut_12m"


def construire_variables(
    echantillon: pd.DataFrame, octroi: pd.DataFrame, macro: pd.DataFrame
) -> pd.DataFrame:
    """Joint octroi et macro à l'échantillon et calcule les variables de D-019.

    Renvoie les identifiants (``loan_id``, ``period``, ``annee_octroi``), les
    variables et la cible.
    """
    e = echantillon.copy()
    e["period"] = pd.PeriodIndex(e["period"], freq="M")
    colonnes_octroi = [
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
    ]
    e = e.merge(octroi[colonnes_octroi], on="loan_id", how="left", validate="many_to_one")
    e = e.merge(macro, left_on="period", right_index=True, how="left", validate="many_to_one")
    e["log_orig_upb"] = np.log(e["orig_upb"])
    e["ratio_crd"] = e["current_upb"] / e["orig_upb"]
    e["ecart_taux"] = e["current_interest_rate"] - e["taux_30a"]
    return e[["loan_id", "period", "annee_octroi", *VARIABLES, CIBLE]]


def _categories(x: pd.DataFrame) -> pd.DataFrame:
    x = x.copy()
    for c in VARIABLES_CAT:
        x[c] = x[c].astype("string")
    return x


# ------------------------------------------------------------------ logistique


def modele_logistique(c: float = 1.0) -> Pipeline:
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
    return Pipeline(
        [
            ("preparation", preparation),
            ("logit", LogisticRegression(C=c, max_iter=2000)),
        ]
    )


def _x_logistique(x: pd.DataFrame) -> pd.DataFrame:
    """Catégorielles en objets Python, manquants en ``None`` pour l'imputation."""
    x = x[list(VARIABLES)].copy()
    for c in VARIABLES_CAT:
        texte = x[c].astype("string")
        x[c] = texte.astype(object).where(texte.notna(), None)
    return x


def ajuster_logistique(x: pd.DataFrame, y) -> Pipeline:
    return modele_logistique().fit(_x_logistique(x), np.asarray(y))


def predire_logistique(modele: Pipeline, x: pd.DataFrame) -> np.ndarray:
    return modele.predict_proba(_x_logistique(x))[:, 1]


# -------------------------------------------------------------------- LightGBM

PARAMETRES_FIXES = {
    "objective": "binary",
    "learning_rate": 0.05,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "feature_fraction": 0.8,
    "seed": GRAINE,
    "deterministic": True,
    "verbosity": -1,
    "num_threads": 4,
}
GRILLE = {"num_leaves": (15, 31, 63), "min_child_samples": (200, 1000)}


@dataclass
class ModeleLightGBM:
    booster: lgb.Booster
    categories: dict[str, list[str]] = field(default_factory=dict)

    def preparer(self, x: pd.DataFrame) -> pd.DataFrame:
        return _lgb_preparer(x, self.categories)

    def predire(self, x: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(self.preparer(x))


def _lgb_preparer(x: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    x = _categories(x[list(VARIABLES)])
    for c in VARIABLES_CAT:
        connues = x[c].where(x[c].isin(categories[c]))  # inconnue → manquante
        x[c] = pd.Categorical(connues, categories=categories[c])
    return x


def _categories_apprises(x: pd.DataFrame) -> dict[str, list[str]]:
    x = _categories(x[list(VARIABLES)])
    return {c: sorted(x[c].dropna().unique().tolist()) for c in VARIABLES_CAT}


def prets_de_validation(loan_id: pd.Series, part: float = 0.20) -> pd.Series:
    """Vrai pour environ ``part`` des prêts, par hachage stable de l'identifiant (D-022).

    Le tirage ne dépend ni de l'ordre des lignes ni de la graine : un prêt est
    toujours du même côté, quelle que soit la période.
    """
    h = pd.util.hash_pandas_object(loan_id.astype("string"), index=False).to_numpy()
    return pd.Series((h % 10_000) < part * 10_000, index=loan_id.index)


def regler_lightgbm(
    x_app: pd.DataFrame, y_app, x_val: pd.DataFrame, y_val, grille: dict = GRILLE
) -> pd.DataFrame:
    """Évalue chaque point de la grille sur la validation, avec arrêt précoce."""
    categories = _categories_apprises(x_app)
    d_app = lgb.Dataset(_lgb_preparer(x_app, categories), np.asarray(y_app), free_raw_data=False)
    xv = _lgb_preparer(x_val, categories)
    d_val = lgb.Dataset(xv, np.asarray(y_val), reference=d_app)
    lignes = []
    for valeurs in itertools.product(*grille.values()):
        params = {**PARAMETRES_FIXES, **dict(zip(grille, valeurs, strict=True))}
        b = lgb.train(
            params,
            d_app,
            num_boost_round=3000,
            valid_sets=[d_val],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        p = b.predict(xv, num_iteration=b.best_iteration)
        lignes.append(
            {
                **dict(zip(grille, valeurs, strict=True)),
                "iterations": b.best_iteration,
                "log_loss_validation": log_loss(np.asarray(y_val), p),
            }
        )
    return pd.DataFrame(lignes).sort_values("log_loss_validation").reset_index(drop=True)


def ajuster_lightgbm(x: pd.DataFrame, y, num_leaves: int, min_child_samples: int, iterations: int):
    categories = _categories_apprises(x)
    params = {
        **PARAMETRES_FIXES,
        "num_leaves": int(num_leaves),
        "min_child_samples": int(min_child_samples),
    }
    d = lgb.Dataset(_lgb_preparer(x, categories), np.asarray(y))
    return ModeleLightGBM(lgb.train(params, d, num_boost_round=int(iterations)), categories)
