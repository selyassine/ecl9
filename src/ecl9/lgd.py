"""Perte en cas de défaut en deux étapes (D-009, D-027, D-028, D-047, D-049).

1. probabilité de régularisation (le prêt redevient sain sans perte) ;
2. sévérité de la perte quand il n'y a pas régularisation.

LGD = (1 - P(régularisation)) × sévérité.

Depuis D-047, le ratio prêt / valeur **réévalué** avec l'indice de prix de
l'État du bien remplace la LTV d'octroi et le ratio de capital restant, dont
il est le produit corrigé des prix. Depuis D-049, la LGD peut être
actualisée : le recouvrement n'arrive qu'après un délai de résolution.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

VARIABLES = ("cltv_reevaluee", "credit_score", "mi_pct", "age_defaut")
VARIABLES_V1 = ("orig_ltv", "credit_score", "ratio_crd", "mi_pct", "age_defaut")  # D-028


def _pipeline(estimateur) -> Pipeline:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), estimateur
    )


def cltv_reevaluee(
    prets: pd.DataFrame,
    mois_octroi: pd.PeriodIndex,
    mois_valeur: pd.PeriodIndex,
    indices_etats: pd.DataFrame,
    indice_national: pd.Series,
) -> np.ndarray:
    """CLTV d'octroi × part du capital restant × prix à l'octroi / prix à ``mois_valeur``.

    Les prix sont ceux de l'État du bien (indice FHFA, D-041) ; à défaut
    (territoire sans indice, date hors de l'indice), l'indice national.
    ``mois_valeur`` est propre à chaque prêt : la date du défaut ou l'arrêté.
    Colonnes lues : ``orig_cltv``, ``orig_ltv``, ``orig_upb``, ``current_upb``,
    ``property_state``.
    """
    cltv = prets["orig_cltv"].fillna(prets["orig_ltv"]).to_numpy(dtype=float)
    part = (prets["current_upb"] / prets["orig_upb"]).to_numpy(dtype=float)
    national = indice_national.reindex(mois_octroi).to_numpy(dtype=float) / indice_national.reindex(
        mois_valeur
    ).to_numpy(dtype=float)
    colonnes = {e: i for i, e in enumerate(indices_etats.columns)}
    j = np.array([colonnes.get(e, -1) for e in prets["property_state"].astype("string")])
    ligne_o = indices_etats.index.get_indexer(mois_octroi)
    ligne_v = indices_etats.index.get_indexer(mois_valeur)
    ok = (j >= 0) & (ligne_o >= 0) & (ligne_v >= 0)
    valeurs = indices_etats.to_numpy(dtype=float)
    etat = np.full(len(prets), np.nan)
    etat[ok] = valeurs[ligne_o[ok], j[ok]] / valeurs[ligne_v[ok], j[ok]]
    return cltv * part * np.where(np.isfinite(etat), etat, national)


def variables_actifs(
    prets: pd.DataFrame,
    octroi: pd.DataFrame,
    arrete: pd.Period,
    indices_etats: pd.DataFrame,
    indice_national: pd.Series,
) -> pd.DataFrame:
    """Variables de la LGD d'un prêt actif à l'arrêté, s'il faisait défaut maintenant."""
    o = prets[["loan_id", "current_upb", "loan_age"]].merge(
        octroi[
            [
                "loan_id",
                "orig_cltv",
                "orig_ltv",
                "orig_upb",
                "property_state",
                "first_payment_date",
                "credit_score",
                "mi_pct",
            ]
        ],
        on="loan_id",
        how="left",
        validate="one_to_one",
    )
    mois_octroi = pd.PeriodIndex(o["first_payment_date"], freq="M") - 1
    mois_valeur = pd.PeriodIndex([arrete] * len(o), freq="M")
    return pd.DataFrame(
        {
            "cltv_reevaluee": cltv_reevaluee(
                o, mois_octroi, mois_valeur, indices_etats, indice_national
            ),
            "credit_score": o["credit_score"].to_numpy(),
            "mi_pct": o["mi_pct"].to_numpy(),
            "age_defaut": o["loan_age"].to_numpy(),
            # Variables de la version 1 (D-028), pour la comparaison.
            "orig_ltv": o["orig_ltv"].to_numpy(),
            "ratio_crd": (o["current_upb"] / o["orig_upb"]).to_numpy(),
        }
    )


@dataclass
class ModeleLGD:
    regularisation: Pipeline
    severite: Pipeline
    variables: tuple[str, ...] = VARIABLES
    delai_resolution_mois: float = 0.0  # délai médian défaut → perte, à l'entraînement

    def p_regularisation(self, x: pd.DataFrame) -> np.ndarray:
        return self.regularisation.predict_proba(x[list(self.variables)])[:, 1]

    def severite_attendue(self, x: pd.DataFrame) -> np.ndarray:
        return np.clip(self.severite.predict(x[list(self.variables)]), 0.0, 1.0)

    def predire(self, x: pd.DataFrame) -> np.ndarray:
        """LGD non actualisée : (1 - P(régularisation)) × sévérité."""
        return (1 - self.p_regularisation(x)) * self.severite_attendue(x)

    def predire_actualisee(
        self, x: pd.DataFrame, taux_annuel: np.ndarray, mois_ecoules: np.ndarray | float = 0.0
    ) -> np.ndarray:
        """LGD actualisée à la date du défaut, ou à l'arrêté en stade 3 (D-049).

        En cas de perte, le recouvrement ``1 - sévérité`` n'est encaissé
        qu'après le délai de résolution restant, actualisé au taux du prêt :
        ``(1 - P(régul.)) × [1 - (1 - sévérité) × (1 + taux / 12)^-délai]``.
        ``mois_ecoules`` (mois déjà passés en défaut) réduit le délai restant,
        borné à zéro. Une régularisation ne coûte rien.
        """
        delai = np.maximum(self.delai_resolution_mois - np.asarray(mois_ecoules, dtype=float), 0.0)
        v = (1 + np.asarray(taux_annuel, dtype=float) / 12) ** -delai
        return (1 - self.p_regularisation(x)) * (1 - (1 - self.severite_attendue(x)) * v)


def ajuster(defauts: pd.DataFrame, variables: tuple[str, ...] = VARIABLES) -> ModeleLGD:
    """``defauts`` : une ligne par défaut résolu, avec ``resolution`` et ``severite``.

    Si ``mois_defaut`` et ``mois_resolution`` sont présents, le délai médian
    de résolution des pertes est retenu pour l'actualisation (D-049).
    """
    v = list(variables)
    resolus = defauts[defauts["resolution"].isin(["perte", "regularisation"])]
    y_regul = resolus["resolution"].eq("regularisation").astype(int)
    regul = _pipeline(LogisticRegression(max_iter=1000)).fit(resolus[v], y_regul)
    pertes = resolus[resolus["resolution"].eq("perte")]
    sev = _pipeline(LinearRegression()).fit(pertes[v], pertes["severite"])
    delai = 0.0
    if {"mois_defaut", "mois_resolution"} <= set(pertes.columns):
        ecart = pd.PeriodIndex(pertes["mois_resolution"], freq="M").astype(
            "int64"
        ) - pd.PeriodIndex(pertes["mois_defaut"], freq="M").astype("int64")
        delai = float(np.median(ecart))
    return ModeleLGD(regul, sev, tuple(variables), delai)


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
