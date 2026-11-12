"""Formule centrale de perte attendue (D-005, D-006, D-007)."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ecl9.definitions import HORIZON_STADE1_MOIS, PONDERATIONS_SCENARIOS
from ecl9.ead import echeancier_crd


def horizon(stade: int, mois_restants: int) -> int:
    """Nombre de mois de pertes à projeter (D-005)."""
    if stade == 1:
        return min(HORIZON_STADE1_MOIS, mois_restants)
    if stade == 2:
        return mois_restants
    if stade == 3:
        return 0
    raise ValueError(f"stade inconnu : {stade}")


def facteurs_actualisation(taux_annuel: float, n_mois: int) -> np.ndarray:
    """``DF(t) = (1 + r/12)^(-t)`` pour t = 1..n_mois."""
    t = np.arange(1, n_mois + 1)
    return (1 + taux_annuel / 12) ** -t


def pd_marginales(hasards: np.ndarray) -> np.ndarray:
    """``PDmarg(t) = S(t-1) h(t)`` avec ``S(0) = 1`` et ``S(t) = prod (1 - h)``."""
    h = np.asarray(hasards, dtype=float)
    if np.any((h < 0) | (h > 1)):
        raise ValueError("les hasards mensuels doivent être dans [0, 1]")
    survie_avant = np.concatenate(([1.0], np.cumprod(1 - h)[:-1]))
    return survie_avant * h


def perte_attendue(hasards: np.ndarray, lgd: float, ead: np.ndarray, taux_annuel: float) -> float:
    """Somme sur t de PDmarg(t) × LGD × EAD(t) × DF(t), pour un scénario."""
    h = np.asarray(hasards, dtype=float)
    ead = np.asarray(ead, dtype=float)
    if h.shape != ead.shape:
        raise ValueError("hasards et EAD doivent couvrir le même horizon")
    df = facteurs_actualisation(taux_annuel, len(h))
    return float(np.sum(pd_marginales(h) * lgd * ead * df))


def perte_attendue_ponderee(
    hasards_par_scenario: Mapping[str, np.ndarray],
    lgd: float,
    ead: np.ndarray,
    taux_annuel: float,
    ponderations: Mapping[str, float] = PONDERATIONS_SCENARIOS,
) -> float:
    """Moyenne des pertes attendues des scénarios, pondérée (D-007, D-013)."""
    if set(hasards_par_scenario) != set(ponderations):
        raise ValueError("un hasard par scénario pondéré est attendu")
    if not np.isclose(sum(ponderations.values()), 1.0):
        raise ValueError("les pondérations doivent sommer à 1")
    return sum(
        w * perte_attendue(hasards_par_scenario[s], lgd, ead, taux_annuel)
        for s, w in ponderations.items()
    )


def ecl_pret(
    stade: int,
    crd: float,
    taux_annuel: float,
    mois_restants: int,
    lgd: float,
    hasards_par_scenario: Mapping[str, np.ndarray] | None = None,
    ponderations: Mapping[str, float] = PONDERATIONS_SCENARIOS,
) -> float:
    """Provision d'un prêt à la date d'arrêté.

    ``hasards_par_scenario`` donne, pour chaque scénario, les hasards mensuels
    sur au moins ``horizon(stade, mois_restants)`` mois ; ils sont tronqués à
    l'horizon. Inutile en stade 3, où ``ECL = LGD × CRD``.
    """
    if stade == 3:
        return lgd * crd
    h_mois = horizon(stade, mois_restants)
    if hasards_par_scenario is None:
        raise ValueError("hasards requis en stades 1 et 2")
    ead = echeancier_crd(crd, taux_annuel, mois_restants)[:h_mois]
    tronques = {s: np.asarray(h)[:h_mois] for s, h in hasards_par_scenario.items()}
    if any(len(h) < h_mois for h in tronques.values()):
        raise ValueError(f"hasards trop courts pour un horizon de {h_mois} mois")
    return perte_attendue_ponderee(tronques, lgd, ead, taux_annuel, ponderations)
