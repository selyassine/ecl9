"""Résolution des défauts et LGD en deux étapes."""

import numpy as np
import pandas as pd
import pytest

from ecl9 import donnees as dn
from ecl9 import lgd


def _suivi(lignes):
    df = pd.DataFrame(
        lignes,
        columns=[
            "loan_id",
            "period",
            "current_upb",
            "delinquency_status",
            "loan_age",
            "zero_balance_code",
            "actual_loss",
            "zero_balance_removal_upb",
        ],
    )
    df["period"] = pd.PeriodIndex(df["period"], freq="M")
    return df


@pytest.fixture
def suivi():
    na = None
    return _suivi(
        [
            # P : défaut en 2001-03, liquidé (09) en 2002-01, perte 30 000 sur 100 000.
            ("P", "2001-01", 100_000, "01", 10, na, na, na),
            ("P", "2001-02", 100_000, "02", 11, na, na, na),
            ("P", "2001-03", 100_000, "03", 12, na, na, na),
            ("P", "2001-04", 100_000, "RA", 13, na, na, na),
            ("P", "2002-01", 0, "RA", 22, "09", 30_000, 100_000),
            # R : défaut en 2001-02 puis retour à jour : régularisation.
            ("R", "2001-01", 80_000, "02", 5, na, na, na),
            ("R", "2001-02", 80_000, "03", 6, na, na, na),
            ("R", "2001-03", 79_000, "00", 7, na, na, na),
            # N : défaut en 2001-02, toujours en retard à la fin : non résolu.
            ("N", "2001-01", 50_000, "02", 5, na, na, na),
            ("N", "2001-02", 50_000, "03", 6, na, na, na),
            ("N", "2001-03", 50_000, "04", 7, na, na, na),
            # G : vente à découvert avec gain (perte négative) : sévérité bornée à 0.
            ("G", "2001-01", 60_000, "03", 5, na, na, na),
            ("G", "2001-05", 0, "03", 9, "03", -2_000, 60_000),
            # S : jamais en défaut.
            ("S", "2001-01", 90_000, "00", 5, na, na, na),
        ]
    )


def test_resolutions(suivi):
    r = dn.resolutions_defaut(suivi).set_index("loan_id")
    assert set(r.index) == {"P", "R", "N", "G"}
    assert r.loc["P", "resolution"] == "perte"
    assert r.loc["P", "severite"] == pytest.approx(0.30)
    assert str(r.loc["P", "mois_defaut"]) == "2001-03"
    assert r.loc["P", "crd_defaut"] == 100_000
    assert r.loc["R", "resolution"] == "regularisation"
    assert r.loc["N", "resolution"] == "non_resolu"
    assert r.loc["G", "resolution"] == "perte" and r.loc["G", "severite"] == 0.0


def test_fenetre_d_observation(suivi):
    # Observation arrêtée fin 2001 : la liquidation de P (2002-01) n'est pas encore vue.
    r = dn.resolutions_defaut(suivi, pd.Period("2001-12", "M")).set_index("loan_id")
    assert r.loc["P", "resolution"] == "non_resolu"


def test_lgd_realisee():
    d = pd.DataFrame(
        {"resolution": ["perte", "regularisation", "non_resolu"], "severite": [0.4, np.nan, np.nan]}
    )
    r = lgd.lgd_realisee(d)
    assert r.iloc[0] == 0.4 and r.iloc[1] == 0.0 and np.isnan(r.iloc[2])


def test_lgd_deux_etapes_retrouve_les_moyennes():
    rng = np.random.default_rng(5)
    n = 4000
    x = pd.DataFrame(
        {
            "orig_ltv": rng.uniform(50, 95, n),
            "credit_score": rng.normal(700, 50, n),
            "ratio_crd": rng.uniform(0.8, 1.0, n),
            "mi_pct": rng.choice([0, 25], n),
            "age_defaut": rng.integers(6, 60, n),
        }
    )
    p_regul = 1 / (1 + np.exp(-(1 - 0.05 * (x["orig_ltv"] - 70))))
    regul = rng.random(n) < p_regul
    sev = np.clip(0.2 + 0.01 * (x["orig_ltv"] - 70) + rng.normal(0, 0.1, n), 0, 1)
    d = x.assign(
        resolution=np.where(regul, "regularisation", "perte"),
        severite=np.where(regul, np.nan, sev),
    )
    m = lgd.ajuster(d)
    prevue = m.predire(d)
    assert prevue.min() >= 0 and prevue.max() <= 1
    assert prevue.mean() == pytest.approx(lgd.lgd_realisee(d).mean(), rel=0.05)
    # La LGD croît avec la LTV.
    assert np.corrcoef(x["orig_ltv"], prevue)[0, 1] > 0.5
