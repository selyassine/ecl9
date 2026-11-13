"""PD à 12 mois sur des données simulées dont on connaît la vraie loi."""

import numpy as np
import pandas as pd
import pytest

from ecl9 import pd as pdm
from ecl9.validation import auc


def _simuler(n: int, graine: int) -> pd.DataFrame:
    rng = np.random.default_rng(graine)
    x = pd.DataFrame(
        {
            "credit_score": rng.normal(720, 50, n),
            "orig_ltv": rng.uniform(40, 95, n),
            "orig_cltv": rng.uniform(40, 95, n),
            "orig_dti": rng.uniform(10, 60, n),
            "orig_interest_rate": rng.uniform(5, 8, n),
            "log_orig_upb": rng.normal(12, 0.4, n),
            "orig_loan_term": rng.choice([180, 360], n),
            "mi_pct": rng.choice([0, 12, 25], n),
            "loan_age": rng.integers(1, 60, n),
            "ratio_crd": rng.uniform(0.7, 1.0, n),
            "ecart_taux": rng.normal(0, 0.5, n),
            "chomage": rng.uniform(4, 6, n),
            "chomage_var12": rng.normal(0, 0.3, n),
            "hpi_var12": rng.normal(0.05, 0.03, n),
            "taux_10a": rng.uniform(3, 5, n),
            "loan_purpose": rng.choice(["P", "C", "N"], n),
            "occupancy_status": rng.choice(["P", "I"], n),
            "channel": rng.choice(["R", "T"], n),
            "property_type": rng.choice(["SF", "CO"], n),
            "first_time_homebuyer": rng.choice(["N", "Y"], n),
            "num_units": rng.choice([1.0, 2.0], n),
            "num_borrowers": rng.choice([1.0, 2.0], n),
            "property_state": rng.choice(["CA", "TX", "FL"], n),
            "retard": rng.choice([0, 1, 2], n, p=[0.95, 0.04, 0.01]),
        }
    )
    x.loc[rng.random(n) < 0.05, "credit_score"] = np.nan
    score = np.nan_to_num(x["credit_score"], nan=720)
    logit = -4.5 - 0.02 * (score - 720) + 0.04 * (x["orig_ltv"] - 70) + 2.0 * x["retard"]
    x[pdm.CIBLE] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return x


@pytest.fixture(scope="module")
def donnees():
    return _simuler(20_000, 1), _simuler(10_000, 2)


def test_logistique_retrouve_le_signal(donnees):
    app, test = donnees
    m = pdm.ajuster_logistique(app, app[pdm.CIBLE])
    p = pdm.predire_logistique(m, test)
    assert p.min() > 0 and p.max() < 1
    assert auc(test[pdm.CIBLE], p) > 0.75
    # Calibration globale : la moyenne des PD colle au taux observé.
    assert p.mean() == pytest.approx(test[pdm.CIBLE].mean(), rel=0.15)


def test_lightgbm_reglage_et_prediction(donnees):
    app, test = donnees
    moitie = len(app) // 2
    grille = {"num_leaves": (7,), "min_child_samples": (50, 200)}
    t = pdm.regler_lightgbm(
        app.iloc[:moitie],
        app[pdm.CIBLE].iloc[:moitie],
        app.iloc[moitie:],
        app[pdm.CIBLE].iloc[moitie:],
        grille,
    )
    assert len(t) == 2 and t["log_loss_validation"].is_monotonic_increasing
    meilleur = t.iloc[0]
    m = pdm.ajuster_lightgbm(
        app, app[pdm.CIBLE], 7, meilleur["min_child_samples"], max(meilleur["iterations"], 10)
    )
    p = m.predire(test)
    assert auc(test[pdm.CIBLE], p) > 0.7


def test_categorie_inconnue_au_test(donnees):
    app, test = donnees
    test = test.copy()
    test.loc[test.index[:5], "property_state"] = "AK"  # absent de l'apprentissage
    m = pdm.ajuster_lightgbm(app, app[pdm.CIBLE], 7, 200, 20)
    assert np.isfinite(m.predire(test)).all()
    lg = pdm.ajuster_logistique(app, app[pdm.CIBLE])
    assert np.isfinite(pdm.predire_logistique(lg, test)).all()


def test_memes_variables_pour_les_deux_modeles(donnees):
    app, _ = donnees
    m = pdm.ajuster_lightgbm(app, app[pdm.CIBLE], 7, 200, 5)
    assert tuple(m.booster.feature_name()) == pdm.VARIABLES
    lg = pdm.ajuster_logistique(app, app[pdm.CIBLE])
    assert tuple(lg.named_steps["preparation"].feature_names_in_) == pdm.VARIABLES


def test_prets_de_validation_disjoints_et_stables():
    ids = pd.Series([f"F{i:06d}" for i in range(20_000)])
    v = pdm.prets_de_validation(ids)
    assert 0.18 < v.mean() < 0.22
    # Même prêt, même côté, quel que soit l'ordre ou le nombre de lignes.
    melange = ids.sample(frac=1, random_state=0)
    assert (pdm.prets_de_validation(melange).sort_index() == v).all()
    double = pd.concat([ids, ids], ignore_index=True)
    assert pdm.prets_de_validation(double).groupby(double).nunique().max() == 1
