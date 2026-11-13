"""Scénarios et surcouche de sensibilité (D-034), sur des données construites."""

import numpy as np
import pandas as pd
import pytest

from ecl9 import scenarios as sc

ARRETE = pd.Period("2007-12", "M")


@pytest.fixture
def macro_simple():
    mois = pd.period_range("2006-01", "2007-12", freq="M")
    m = pd.DataFrame(
        {
            "chomage": np.linspace(4.0, 5.0, len(mois)),
            "chomage_var12": 0.5,
            "hpi_var12": -0.04,
            "taux_30a": 6.0,
            "taux_10a": 4.0,
        },
        index=mois,
    )
    return m, pd.Series(100.0, index=mois)


def test_central_garde_les_taux_et_la_tendance_des_prix(macro_simple):
    m, hpi = macro_simple
    t = sc.trajectoire("central", m, hpi, ARRETE, 60)
    assert (t["taux_30a"] == 6.0).all() and (t["taux_10a"] == 4.0).all()
    assert (t["chomage"] == 5.0).all()
    assert np.allclose(t["hpi_var12"].iloc[:36], -0.04)
    assert (t["hpi_var12"].iloc[36:] == 0).all()
    # 3 ans à -4 % par an, puis prix stables
    assert t["hpi_relatif"].iloc[35] == pytest.approx(0.96**3)
    assert t["hpi_relatif"].iloc[-1] == pytest.approx(0.96**3)


def test_defavorable_atteint_ses_chocs(macro_simple):
    m, hpi = macro_simple
    t = sc.trajectoire("defavorable", m, hpi, ARRETE, 60)
    assert t["chomage"].iloc[23] == pytest.approx(8.0)
    assert t["chomage_var12"].iloc[23] == pytest.approx(1.5)
    assert t["chomage_var12"].iloc[40] == pytest.approx(0.0)
    assert t["hpi_var12"].iloc[11] == pytest.approx(-0.10)
    assert t["taux_30a"].iloc[11:].eq(5.0).all()


def test_variation_du_chomage_relie_passe_et_projection(macro_simple):
    m, hpi = macro_simple
    t = sc.trajectoire("central", m, hpi, ARRETE, 24)
    # Mois 1 : chômage tenu à 5,0 contre celui de janvier 2007
    assert t["chomage_var12"].iloc[0] == pytest.approx(5.0 - m.loc["2007-01", "chomage"])
    assert t["chomage_var12"].iloc[12:].eq(0).all()


def test_classes_elul():
    assert sc.effet_cltv(np.array([40.0, 50.0, 95.0, 120.0, 300.0, np.nan])).tolist() == [
        0.0,
        0.415,
        1.226,
        1.566,
        1.566,
        0.0,
    ]
    assert sc.effet_chomage(np.array([-1.0, -0.2, 0.3, 1.0, 2.0])).tolist() == [
        0.0,
        0.006,
        0.084,
        0.183,
        0.400,
    ]


def test_surcouche_nulle_sans_mouvement():
    t = pd.DataFrame({"hpi_relatif": [1.0, 1.0], "chomage_var12": [0.2, 0.2]})
    d = sc.surcouche(np.array([75.0, 105.0]), 0.2, t)
    assert np.allclose(d, 0.0)


def test_surcouche_baisse_des_prix():
    # CLTV 95 → 95 / 0,8 = 118,75 : de la classe 90-100 à 110-120
    t = pd.DataFrame({"hpi_relatif": [0.8], "chomage_var12": [1.5]})
    d = sc.surcouche(np.array([95.0]), 0.0, t)
    assert d[0, 0] == pytest.approx((1.550 - 1.226) + (0.400 - 0.084))


def test_decaler():
    h = np.array([[0.001, 0.02, 0.0]])
    assert np.allclose(sc.decaler(h, 0.0), h)
    odds = lambda p: p / (1 - p)  # noqa: E731
    assert odds(sc.decaler(h, np.log(2.0)))[0, 1] == pytest.approx(2 * odds(0.02))
