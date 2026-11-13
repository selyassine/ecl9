"""Scénarios macroéconomiques prospectifs et surcouche de sensibilité (D-034).

Trois trajectoires (central, défavorable, favorable) pour le chômage, les prix
immobiliers et les taux, construites à partir des seules valeurs connues à
l'arrêté et pondérées selon ``definitions.PONDERATIONS_SCENARIOS``. Dans le
résultat principal, elles agissent sur la PD par le seul canal que le modèle
de survie a appris : les taux (D-026).

La surcouche, publiée à part, ajoute au logit du hasard l'effet du chômage et
des prix immobiliers estimé par Elul et al. (2010), table 1 : variation du
chômage sur un an et ratio prêt / valeur réévalué (CLTV), par classes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MOIS_CHOC = 12  # durée de la transition vers le niveau choqué
MOIS_PRIX = 36  # au-delà, les prix immobiliers se stabilisent dans tous les scénarios


@dataclass(frozen=True)
class Choc:
    """Écarts au niveau de l'arrêté, atteints linéairement en ``MOIS_CHOC`` mois."""

    chomage: float  # points de chômage, atteints en ``mois_chomage`` mois
    mois_chomage: int
    hpi_var12: float | None  # variation annuelle des prix visée ; None : celle de l'arrêté
    taux: float  # points sur les taux à 30 et 10 ans
    surcroit_prix: float = 0.0  # ajouté à la variation annuelle des prix visée


CHOCS = {
    "central": Choc(chomage=0.0, mois_chomage=MOIS_CHOC, hpi_var12=None, taux=0.0),
    "defavorable": Choc(chomage=3.0, mois_chomage=24, hpi_var12=-0.10, taux=-1.0),
    "favorable": Choc(
        chomage=-0.5, mois_chomage=MOIS_CHOC, hpi_var12=None, taux=0.5, surcroit_prix=0.03
    ),
}


def _rampe(n_mois: int, duree: int) -> np.ndarray:
    return np.minimum(np.arange(1, n_mois + 1) / duree, 1.0)


def trajectoire(
    nom: str, m: pd.DataFrame, hpi: pd.Series, arrete: pd.Period, n_mois: int
) -> pd.DataFrame:
    """Variables macro mensuelles des mois ``arrete + 1`` à ``arrete + n_mois``.

    Colonnes de ``macro.table_macro`` plus ``hpi_relatif``, le niveau des prix
    rapporté à celui connu à l'arrêté.
    """
    c = CHOCS[nom]
    x0 = m.loc[arrete]
    mois = pd.period_range(arrete + 1, periods=n_mois, freq="M")
    k = np.arange(1, n_mois + 1)

    chomage = x0["chomage"] + c.chomage * _rampe(n_mois, c.mois_chomage)
    passe = m["chomage"].reindex(pd.period_range(arrete - 11, arrete, freq="M")).to_numpy()
    serie = np.concatenate([passe, chomage])
    reference = serie[k - 1]  # chômage 12 mois plus tôt
    chomage_var12 = chomage - reference

    g0 = float(x0["hpi_var12"])
    cible = (g0 if c.hpi_var12 is None else c.hpi_var12) + c.surcroit_prix
    g = g0 + (cible - g0) * _rampe(n_mois, MOIS_CHOC)
    g = np.where(k <= MOIS_PRIX, g, 0.0)
    hpi_relatif = np.cumprod((1 + g) ** (1 / 12))

    taux = c.taux * _rampe(n_mois, MOIS_CHOC)
    return pd.DataFrame(
        {
            "chomage": chomage,
            "chomage_var12": chomage_var12,
            "hpi_var12": g,
            "taux_30a": x0["taux_30a"] + taux,
            "taux_10a": x0["taux_10a"] + taux,
            "hpi_relatif": hpi_relatif,
        },
        index=mois,
    )


# --------------------------------------------- surcouche Elul et al. (2010)

# Table 1, colonne de base : logit trimestriel du passage à 60 jours de retard,
# prêts à taux fixe octroyés en 2005-2006 (LPS), classes de référence CLTV < 50
# et variation du chômage < -0,5 point.
BORNES_CLTV = np.array([50, 70, 80, 90, 100, 110, 120], dtype=float)
COEF_CLTV = np.array([0.0, 0.415, 0.718, 0.985, 1.226, 1.361, 1.550, 1.566])
BORNES_CHOMAGE = np.array([-0.5, 0.0, 0.7, 1.25])
COEF_CHOMAGE = np.array([0.0, 0.006, 0.084, 0.183, 0.400])


def effet_cltv(cltv: np.ndarray) -> np.ndarray:
    e = COEF_CLTV[np.searchsorted(BORNES_CLTV, cltv, side="right")]
    return np.where(np.isnan(cltv), 0.0, e)


def effet_chomage(variation: np.ndarray) -> np.ndarray:
    return COEF_CHOMAGE[np.searchsorted(BORNES_CHOMAGE, variation, side="right")]


def cltv_arrete(prets: pd.DataFrame, hpi_octroi: np.ndarray, hpi_arrete: float) -> np.ndarray:
    """CLTV réévaluée à l'arrêté : CLTV d'octroi × part du capital restant × prix."""
    cltv = prets["orig_cltv"].fillna(prets["orig_ltv"]).to_numpy(dtype=float)
    part = (prets["current_upb"] / prets["orig_upb"]).to_numpy(dtype=float)
    return cltv * part * hpi_octroi / hpi_arrete


def surcouche(cltv0: np.ndarray, chomage_var12_0: float, traj: pd.DataFrame) -> np.ndarray:
    """Écart de logit du hasard, prêts × mois, par rapport à la situation à l'arrêté.

    Le capital restant est tenu à son niveau de l'arrêté (l'amortissement
    n'abaisse pas la CLTV projetée), ce qui majore légèrement l'effet.
    """
    cltv = cltv0[:, None] / traj["hpi_relatif"].to_numpy()[None, :]
    d_cltv = effet_cltv(cltv) - effet_cltv(cltv0)[:, None]
    d_chom = effet_chomage(traj["chomage_var12"].to_numpy()) - effet_chomage(
        np.array([chomage_var12_0])
    )
    return d_cltv + d_chom[None, :]


def decaler(h: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """Applique un écart de logit à une matrice de hasards."""
    with np.errstate(divide="ignore"):
        logit = np.log(h) - np.log1p(-h)
    return 1 / (1 + np.exp(-(logit + delta)))
