"""Exposition au défaut selon l'amortissement contractuel (D-008)."""

from __future__ import annotations

import numpy as np


def mensualite(capital: float, taux_annuel: float, n_mois: int) -> float:
    """Annuité constante qui amortit ``capital`` en ``n_mois`` au taux ``taux_annuel``.

    ``taux_annuel`` est en décimal (0,06 pour 6 %), capitalisé mensuellement.
    """
    if n_mois <= 0:
        raise ValueError("n_mois doit être strictement positif")
    i = taux_annuel / 12
    if i == 0:
        return capital / n_mois
    return capital * i / (1 - (1 + i) ** -n_mois)


def echeancier_crd(capital: float, taux_annuel: float, n_mois: int) -> np.ndarray:
    """Capital restant dû au début des mois 1 à ``n_mois`` après l'arrêté.

    Le premier élément est le capital observé à l'arrêté ; le dernier est le
    capital avant la dernière échéance. Formule fermée :
    ``B_k = B_0 (1 + i)^k - P ((1 + i)^k - 1) / i`` après ``k`` échéances.
    """
    k = np.arange(n_mois)
    i = taux_annuel / 12
    p = mensualite(capital, taux_annuel, n_mois)
    if i == 0:
        crd = capital - p * k
    else:
        croissance = (1 + i) ** k
        crd = capital * croissance - p * (croissance - 1) / i
    return np.clip(crd, 0.0, None)
