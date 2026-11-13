"""Perte en cas de défaut en deux étapes (D-009, D-027, D-028).

1. probabilité de régularisation (le prêt redevient sain sans perte) ;
2. sévérité de la perte quand il n'y a pas régularisation.

LGD = (1 - P(régularisation)) × sévérité.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

VARIABLES = ("orig_ltv", "credit_score", "ratio_crd", "mi_pct", "age_defaut")


def _pipeline(estimateur) -> Pipeline:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), estimateur
    )


@dataclass
class ModeleLGD:
    regularisation: Pipeline
    severite: Pipeline

    def p_regularisation(self, x: pd.DataFrame) -> np.ndarray:
        return self.regularisation.predict_proba(x[list(VARIABLES)])[:, 1]

    def severite_attendue(self, x: pd.DataFrame) -> np.ndarray:
        return np.clip(self.severite.predict(x[list(VARIABLES)]), 0.0, 1.0)

    def predire(self, x: pd.DataFrame) -> np.ndarray:
        return (1 - self.p_regularisation(x)) * self.severite_attendue(x)


def ajuster(defauts: pd.DataFrame) -> ModeleLGD:
    """``defauts`` : une ligne par défaut résolu, avec ``resolution`` et ``severite``."""
    resolus = defauts[defauts["resolution"].isin(["perte", "regularisation"])]
    y_regul = resolus["resolution"].eq("regularisation").astype(int)
    regul = _pipeline(LogisticRegression(max_iter=1000)).fit(resolus[list(VARIABLES)], y_regul)
    pertes = resolus[resolus["resolution"].eq("perte")]
    sev = _pipeline(LinearRegression()).fit(pertes[list(VARIABLES)], pertes["severite"])
    return ModeleLGD(regul, sev)


def lgd_realisee(defauts: pd.DataFrame) -> pd.Series:
    """0 pour une régularisation, la sévérité pour une perte, manquante sinon."""
    return pd.Series(
        np.where(
            defauts["resolution"].eq("regularisation"),
            0.0,
            np.where(defauts["resolution"].eq("perte"), defauts["severite"], np.nan),
        ),
        index=defauts.index,
    )
