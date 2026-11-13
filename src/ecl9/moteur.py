"""Moteur de calcul vectorisé de la provision (D-029).

Pour un portefeuille à une date d'arrêté, toutes les opérations portent sur
des matrices prêts × mois : hasards projetés, ancrage sur la PD à 12 mois,
PD marginales, EAD contractuelle, actualisation. Les résultats sont
identiques à ceux de ``ecl.ecl_pret`` prêt par prêt (vérifié en test).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from ecl9 import survie
from ecl9.definitions import HORIZON_STADE1_MOIS

# ------------------------------------------------- décomposition du hasard


@dataclass
class TermesHasard:
    """Termes additifs du logit du hasard de survie, lus dans le modèle estimé."""

    age: dict[str, float]  # coefficient de chaque bande d'âge (0 si absente)
    macro: dict[str, tuple[float, float]]  # variable → (coefficient, écart-type)

    @classmethod
    def depuis(cls, m: Pipeline) -> TermesHasard:
        prep = m.named_steps["preparation"]
        coef = pd.Series(m.named_steps["logit"].coef_[0], index=prep.get_feature_names_out())
        num = prep.named_transformers_["num"]
        echelle = pd.Series(num[-1].scale_, index=num[:-1].get_feature_names_out())
        age = {
            n.removeprefix("cat__bande_age_"): float(v)
            for n, v in coef.items()
            if n.startswith("cat__bande_age_")
        }
        macro = {
            v: (float(coef[f"num__{v}"]), float(echelle[v]))
            for v in survie.VARIABLES_MACRO
            if f"num__{v}" in coef
        }
        return cls(age, macro)


def logit_hasard(m: Pipeline, lignes: pd.DataFrame) -> np.ndarray:
    return m.decision_function(survie._x(lignes))


def projeter_hasards(
    m: Pipeline,
    prets: pd.DataFrame,
    arrete: pd.Period,
    trajectoire: pd.DataFrame,
    n_mois: int,
) -> np.ndarray:
    """Hasards mensuels des mois 1 à ``n_mois`` après l'arrêté, matrice prêts × mois.

    ``prets`` contient les variables de survie à l'arrêté (``survie.preparer``),
    ``trajectoire`` les variables macro mensuelles (``taux_30a`` compris) à
    partir de ``arrete + 1`` ; sa dernière valeur est prolongée au besoin.
    """
    termes = TermesHasard.depuis(m)
    base = logit_hasard(m, prets)  # logit au mois de l'arrêté
    mois = pd.period_range(arrete + 1, periods=n_mois, freq="M")
    t = trajectoire.reindex(mois).ffill()
    if t.isna().any().any():
        raise ValueError("trajectoire macro absente au début de la projection")

    age0 = prets["loan_age"].to_numpy(dtype=float)
    ages = age0[:, None] + np.arange(1, n_mois + 1)[None, :]
    # Bandes d'âge par recherche dichotomique, même découpage que survie.bande_age.
    etiquettes = ["0-6", "7-12", "13-24", "25-36", "37-48", "49-60", "61+"]
    alpha = np.array([termes.age.get(e, 0.0) for e in etiquettes])
    bornes = np.array(survie.BORNES_AGE[1:], dtype=float)
    delta = alpha[np.searchsorted(bornes, ages, side="left")]
    delta -= alpha[np.searchsorted(bornes, age0, side="left")][:, None]

    for v, (gamma, sigma) in termes.macro.items():
        if v == "ecart_taux":
            # écart(i, k) - écart(i, 0) = taux_30a(0) - taux_30a(k)
            variation = prets["taux_30a"].to_numpy()[:, None] - t["taux_30a"].to_numpy()[None, :]
        else:
            variation = t[v].to_numpy()[None, :] - prets[v].to_numpy()[:, None]
        delta = delta + gamma * variation / sigma
    return 1 / (1 + np.exp(-(base[:, None] + delta)))


# ------------------------------------------------------------- calcul ECL


def logit(h: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return np.log(h) - np.log1p(-h)


def decaler(h: np.ndarray, delta) -> np.ndarray:
    """Applique un écart de logit à une matrice de hasards (0 et 1 restent fixes)."""
    with np.errstate(over="ignore", invalid="ignore"):
        r = 1 / (1 + np.exp(-(logit(h) + delta)))
    return np.where(h <= 0, 0.0, np.where(h >= 1, 1.0, r))


def ancrer_matrice(h: np.ndarray, pd12: np.ndarray, horizon_ancrage: np.ndarray, iterations=80):
    """Version vectorisée de ``survie.ancrer`` : un facteur ``c`` par prêt (dichotomie)."""
    h = h.copy()
    n, m = h.shape
    k = int(min(m, max(horizon_ancrage.max(initial=0), 0)))
    masque = np.arange(k)[None, :] < horizon_ancrage[:, None]
    tete = np.where(masque, h[:, :k], 0.0)  # seules les k premières colonnes comptent

    def pd_tete(c):
        return 1 - np.prod(1 - np.minimum(c[:, None] * tete, 1.0), axis=1)

    bas, haut = np.zeros(n), np.ones(n)
    for _ in range(200):
        trop_bas = pd_tete(haut) < pd12
        if not trop_bas.any():
            break
        haut = np.where(trop_bas, haut * 2, haut)
    for _ in range(iterations):
        milieu = (bas + haut) / 2
        sous = pd_tete(milieu) < pd12
        bas, haut = np.where(sous, milieu, bas), np.where(sous, haut, milieu)
    c = np.where(pd12 > 0, haut, 0.0)
    h[:, :k] = np.where(masque, np.minimum(c[:, None] * h[:, :k], 1.0), h[:, :k])
    return h


def echeancier_matrice(crd: np.ndarray, taux: np.ndarray, restants: np.ndarray, n_mois: int):
    """CRD au début des mois 1..n_mois (D-008), nul au-delà de l'échéance."""
    k = np.arange(n_mois)[None, :]
    i = (taux / 12)[:, None]
    n = restants[:, None].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.where(i > 0, crd[:, None] * i / (1 - (1 + i) ** -n), crd[:, None] / n)
        croissance = (1 + i) ** k
        b = np.where(
            i > 0, crd[:, None] * croissance - p * (croissance - 1) / i, crd[:, None] - p * k
        )
    return np.where(k < n, np.clip(b, 0.0, None), 0.0)


def provisions(
    stade: np.ndarray,
    crd: np.ndarray,
    taux_annuel: np.ndarray,
    mois_restants: np.ndarray,
    lgd: np.ndarray,
    pd12: np.ndarray,
    hasards: np.ndarray,
    ecart_logit: np.ndarray | float | None = None,
) -> np.ndarray:
    """Provision de chaque prêt (D-005 à D-008, D-024), taux en décimal.

    ``hasards`` couvre au moins la plus longue durée restante des stades 2.
    En stade 3, la provision vaut LGD × CRD. ``ecart_logit`` (prêts × mois)
    est ajouté au logit des hasards **après** l'ancrage : c'est l'écart d'un
    scénario au scénario central (D-036).
    """
    stade = np.asarray(stade)
    restants = np.asarray(mois_restants, dtype=int)
    n_mois = hasards.shape[1]
    horizon = np.where(stade == 1, np.minimum(HORIZON_STADE1_MOIS, restants), restants)
    horizon = np.where(stade == 3, 0, horizon)
    if (horizon > n_mois).any():
        raise ValueError("hasards trop courts pour l'horizon des stades 2")
    h = ancrer_matrice(hasards, pd12, np.minimum(HORIZON_STADE1_MOIS, restants))
    if ecart_logit is not None:
        h = decaler(h, ecart_logit)
    survie_avant = np.cumprod(np.concatenate([np.ones((len(h), 1)), 1 - h[:, :-1]], axis=1), 1)
    marginales = survie_avant * h
    ead = echeancier_matrice(crd, taux_annuel, restants, n_mois)
    df = (1 + taux_annuel[:, None] / 12) ** -np.arange(1, n_mois + 1)[None, :]
    dans_horizon = np.arange(n_mois)[None, :] < horizon[:, None]
    pertes = np.sum(np.where(dans_horizon, marginales * ead * df, 0.0), axis=1) * lgd
    return np.where(stade == 3, lgd * crd, pertes)
