"""Mesures de validation des PD (D-014, D-021)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def auc(y, pd_estimee) -> float:
    return float(roc_auc_score(y, pd_estimee))


def gini(y, pd_estimee) -> float:
    return 2 * auc(y, pd_estimee) - 1


def brier(y, pd_estimee) -> float:
    y = np.asarray(y, dtype=float)
    return float(np.mean((np.asarray(pd_estimee, dtype=float) - y) ** 2))


def calibration(y, pd_estimee, n_classes: int = 10) -> pd.DataFrame:
    """Défaut observé contre PD moyenne par classe de PD (quantiles)."""
    df = pd.DataFrame({"y": np.asarray(y, float), "pd": np.asarray(pd_estimee, float)})
    df["classe"] = pd.qcut(df["pd"].rank(method="first"), n_classes, labels=False) + 1
    t = df.groupby("classe").agg(n=("y", "size"), pd_moyenne=("pd", "mean"), observe=("y", "mean"))
    t["ecart"] = t["observe"] - t["pd_moyenne"]
    return t


def rapport_attendu_observe(y, pd_estimee) -> float:
    """Somme des PD divisée par le nombre de défauts (1 = calibration globale parfaite)."""
    return float(np.sum(pd_estimee) / np.sum(y))


def psi(reference, comparee, n_classes: int = 10, plancher: float = 1e-6) -> float:
    """Population Stability Index sur les quantiles de la distribution de référence.

    ``PSI = somme (p_c - p_r) ln(p_c / p_r)`` ; les parts nulles sont
    remplacées par ``plancher`` pour éviter un logarithme infini.
    """
    reference = np.asarray(reference, dtype=float)
    comparee = np.asarray(comparee, dtype=float)
    bornes = np.unique(np.quantile(reference, np.linspace(0, 1, n_classes + 1)))
    bornes[0], bornes[-1] = -np.inf, np.inf
    p_r = np.histogram(reference, bornes)[0] / len(reference)
    p_c = np.histogram(comparee, bornes)[0] / len(comparee)
    p_r, p_c = np.maximum(p_r, plancher), np.maximum(p_c, plancher)
    return float(np.sum((p_c - p_r) * np.log(p_c / p_r)))
