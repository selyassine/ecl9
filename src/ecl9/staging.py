"""Affectation des stades IFRS 9 (D-002 à D-004)."""

from __future__ import annotations

import numpy as np

from ecl9.definitions import SEUIL_RATIO_PD_STADE2, SEUIL_RETARD_STADE2


def pd_annualisee(pd_cumulee, n_mois):
    """``1 - (1 - p)^(12 / n)`` : PD cumulée sur ``n`` mois ramenée à un an."""
    p = np.asarray(pd_cumulee, dtype=float)
    n = np.asarray(n_mois, dtype=float)
    if np.any(n <= 0):
        raise ValueError("n_mois doit être strictement positif")
    return 1 - (1 - p) ** (12 / n)


def stade(
    en_defaut,
    retard_mensualites,
    pd_vie_arrete,
    mois_restants_arrete,
    pd_vie_octroi,
    mois_restants_octroi,
    seuil: float = SEUIL_RATIO_PD_STADE2,
):
    """Stade de chaque prêt (tableaux de même longueur).

    - 3 si en défaut ;
    - 2 si retard d'au moins une mensualité (30 jours) ou si la PD à maturité
      annualisée a été multipliée par ``seuil`` ou plus depuis l'octroi ;
    - 1 sinon.

    Un retard manquant ne déclenche pas le critère de retard.
    """
    defaut = np.asarray(en_defaut, dtype=bool)
    retard = np.asarray(retard_mensualites, dtype=float)
    pd_a = pd_annualisee(pd_vie_arrete, mois_restants_arrete)
    pd_o = pd_annualisee(pd_vie_octroi, mois_restants_octroi)
    with np.errstate(divide="ignore", invalid="ignore"):
        degradation = np.where(pd_o > 0, pd_a / pd_o >= seuil, pd_a > 0)
    retard_30 = np.nan_to_num(retard, nan=0.0) >= SEUIL_RETARD_STADE2
    return np.where(defaut, 3, np.where(retard_30 | degradation, 2, 1)).astype(int)
