"""Moteur vectorisé : identique au calcul prêt par prêt et aux cas à la main."""

import numpy as np
import pandas as pd
import pytest

from ecl9 import ecl, moteur, survie
from tests.test_survie import _panneau


def test_echeancier_matrice_cas_a_la_main():
    # 1 000 à 12 % sur 2 mois : CRD 1 000 puis 502,487562 ; 1 200 à 0 % sur 12 mois.
    b = moteur.echeancier_matrice(
        np.array([1000.0, 1200.0]), np.array([0.12, 0.0]), np.array([2, 12]), 4
    )
    np.testing.assert_allclose(b[0], [1000, 502.487562, 0, 0], atol=1e-6)
    np.testing.assert_allclose(b[1], [1200, 1100, 1000, 900])


def test_ancrage_matrice_egal_ancrage_scalaire():
    rng = np.random.default_rng(0)
    h = rng.uniform(0.001, 0.02, (5, 30))
    pd12 = np.array([0.05, 0.10, 0.0, 0.30, 0.01])
    horizon = np.array([12, 12, 12, 6, 12])
    a = moteur.ancrer_matrice(h, pd12, horizon)
    for i in range(5):
        attendu = survie.ancrer(h[i], pd12[i], horizon=horizon[i])
        np.testing.assert_allclose(a[i], attendu, atol=1e-10)


def test_provisions_egales_au_calcul_pret_par_pret():
    rng = np.random.default_rng(1)
    n, m = 6, 40
    h = rng.uniform(0.001, 0.01, (n, m))
    stade = np.array([1, 2, 3, 1, 2, 1])
    crd = rng.uniform(50_000, 200_000, n)
    taux = rng.uniform(0.03, 0.08, n)
    restants = np.array([40, 40, 40, 7, 25, 40])
    lgd = rng.uniform(0.1, 0.5, n)
    # PD 12 mois égale à celle des hasards : l'ancrage ne change rien (c = 1).
    pd12 = np.array([survie.pd_cumulee(h[i, : min(12, restants[i])]) for i in range(n)])
    v = moteur.provisions(stade, crd, taux, restants, lgd, pd12, h)
    for i in range(n):
        scen = {"central": h[i], "defavorable": h[i], "favorable": h[i]}
        attendu = ecl.ecl_pret(int(stade[i]), crd[i], taux[i], int(restants[i]), lgd[i], scen)
        assert v[i] == pytest.approx(attendu, rel=1e-9)


def test_provision_cas_a_la_main():
    # Repris de tests/test_cas_a_la_main.py : stade 2, 2 mois restants, 1 000 à 12 %,
    # h = (0,1 ; 0,2), LGD 0,5 → 93,837743.
    # PD 12 mois sur 2 mois = 1 - 0,9 × 0,8 = 0,28 (ancrage neutre).
    v = moteur.provisions(
        np.array([2]),
        np.array([1000.0]),
        np.array([0.12]),
        np.array([2]),
        np.array([0.5]),
        np.array([0.28]),
        np.array([[0.1, 0.2]]),
    )
    assert v[0] == pytest.approx(93.837743, abs=1e-5)


def test_projection_vectorisee_egale_projection_ligne_a_ligne():
    df = _panneau(800, 7)
    m = survie.ajuster(survie.echantillonner(df, part=0.5, graine=3))
    prets = df.groupby("loan_id").head(1).head(4).copy()
    prets["loan_age"] = [3, 10, 30, 70]
    prets["bande_age"] = survie.bande_age(prets["loan_age"]).to_numpy()
    prets["current_interest_rate"] = [6.0, 7.0, 5.5, 8.0]
    prets["taux_30a"] = 6.2
    prets["ecart_taux"] = prets["current_interest_rate"] - prets["taux_30a"]
    prets["orig_upb"] = np.exp(prets["log_orig_upb"])
    mois = pd.period_range("2006-01", periods=24, freq="M")
    trajectoire = pd.DataFrame(
        {
            "chomage": np.linspace(4.5, 7.5, 24),
            "chomage_var12": np.linspace(0, 2, 24),
            "hpi_var12": np.linspace(0.05, -0.1, 24),
            "taux_10a": np.linspace(4.5, 3.0, 24),
            "taux_30a": np.linspace(6.2, 5.0, 24),
        },
        index=mois,
    )
    arrete = pd.Period("2005-12", "M")
    h = moteur.projeter_hasards(m, prets, arrete, trajectoire, 30)
    for i, (_, pret) in enumerate(prets.iterrows()):
        attendu = survie.projeter(m, pret.drop(["loan_id", "defaut"]), arrete, trajectoire, 30)
        np.testing.assert_allclose(h[i], attendu, rtol=1e-10, atol=1e-14)


def test_ecart_de_scenario_applique_apres_ancrage():
    """D-036 : l'écart de logit d'un scénario déplace aussi la PD des 12 premiers mois."""
    rng = np.random.default_rng(3)
    n, mois = 4, 60
    args = (
        np.array([1, 1, 2, 2]),
        np.full(n, 100_000.0),
        np.full(n, 0.06),
        np.array([60, 30, 60, 45]),
        np.full(n, 0.3),
        np.full(n, 0.02),
        rng.uniform(0.001, 0.01, (n, mois)),
    )
    base = moteur.provisions(*args)
    assert np.allclose(moteur.provisions(*args, ecart_logit=0.0), base)
    choc = moteur.provisions(*args, ecart_logit=np.log(2.0))
    assert (choc > base).all()
