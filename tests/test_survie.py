"""Survie discrète : bandes d'âge, ancrage et projection, sur des cas à la main."""

import numpy as np
import pandas as pd
import pytest

from ecl9 import survie


def test_bandes_age():
    b = survie.bande_age([0, 6, 7, 12, 13, 60, 61, 300])
    assert b.tolist() == ["0-6", "0-6", "7-12", "7-12", "13-24", "49-60", "61+", "61+"]


def test_pd_cumulee():
    # 1 - 0,9 × 0,8 = 0,28
    assert survie.pd_cumulee([0.1, 0.2]) == pytest.approx(0.28)


def test_ancrage_hasard_constant():
    # h = 0,01 pendant 24 mois, cible 20 % à 12 mois :
    # 1 - (1 - 0,01 c)^12 = 0,2  →  0,01 c = 1 - 0,8^(1/12) = 0,018423  →  c = 1,8423
    h = np.full(24, 0.01)
    a = survie.ancrer(h, 0.20)
    assert a[0] == pytest.approx(1 - 0.8 ** (1 / 12), rel=1e-9)
    assert survie.pd_cumulee(a[:12]) == pytest.approx(0.20, abs=1e-10)
    np.testing.assert_array_equal(a[12:], h[12:])  # au-delà d'un an, inchangés


def test_ancrage_duree_courte_et_cas_limites():
    # Durée restante de 6 mois : l'ancrage porte sur 6 mois.
    a = survie.ancrer(np.full(6, 0.02), 0.10)
    assert survie.pd_cumulee(a) == pytest.approx(0.10, abs=1e-10)
    # Cible nulle : hasards de la première année mis à zéro.
    assert survie.ancrer([0.1, 0.2], 0.0).tolist() == [0.0, 0.0]
    with pytest.raises(ValueError):
        survie.ancrer([0.1], 1.0)


def _panneau(n_prets: int, graine: int) -> pd.DataFrame:
    rng = np.random.default_rng(graine)
    lignes = []
    for i in range(n_prets):
        score = rng.normal(720, 50)
        for age in range(1, 49):
            chomage = 4 + 2 * rng.random()
            logit = -6 - 0.02 * (score - 720) + 0.6 * (chomage - 5) + (0.8 if age > 12 else 0)
            d = rng.random() < 1 / (1 + np.exp(-logit))
            lignes.append((f"P{i}", age, score, chomage, int(d)))
            if d:
                break
    df = pd.DataFrame(lignes, columns=["loan_id", "loan_age", "credit_score", "chomage", "defaut"])
    constantes = {
        "orig_ltv": 75.0,
        "orig_cltv": 75.0,
        "orig_dti": 35.0,
        "orig_interest_rate": 6.0,
        "log_orig_upb": 12.0,
        "orig_loan_term": 360,
        "mi_pct": 0.0,
        "chomage_var12": 0.0,
        "hpi_var12": 0.05,
        "taux_10a": 4.0,
        "ecart_taux": 0.0,
        "loan_purpose": "P",
        "occupancy_status": "P",
        "channel": "R",
        "property_type": "SF",
        "first_time_homebuyer": "N",
        "num_units": 1.0,
        "num_borrowers": 2.0,
        "property_state": "CA",
    }
    for c, v in constantes.items():
        df[c] = v
    df["bande_age"] = survie.bande_age(df["loan_age"]).to_numpy()
    return df


def test_estimation_ponderee_et_projection():
    df = _panneau(3000, 3)
    e = survie.echantillonner(df, part=0.2, graine=1)
    assert e["defaut"].sum() == df["defaut"].sum()  # tous les défauts gardés
    assert e["poids"].sum() == pytest.approx(len(df), rel=0.05)
    m = survie.ajuster(e)
    h = survie.hasards(m, df)
    # Défauts attendus ≈ observés malgré le sous-échantillonnage pondéré.
    assert h.sum() == pytest.approx(df["defaut"].sum(), rel=0.15)

    pret = df.iloc[0].drop(["loan_id", "defaut", "bande_age"]).copy()
    pret["loan_age"] = 6
    pret["current_interest_rate"] = 6.0
    pret["orig_upb"] = np.exp(12.0)
    mois = pd.period_range("2006-01", "2007-12", freq="M")
    calme = pd.DataFrame(
        {"chomage": 4.0, "chomage_var12": 0.0, "hpi_var12": 0.05, "taux_10a": 4.0, "taux_30a": 6.0},
        index=mois,
    )
    crise = calme.assign(chomage=6.0)
    arrete = pd.Period("2005-12", "M")
    h_calme = survie.projeter(m, pret, arrete, calme, 30)  # prolongée au-delà de 2007-12
    h_crise = survie.projeter(m, pret, arrete, crise, 30)
    assert len(h_calme) == 30
    assert (h_crise > h_calme).all()  # plus de chômage, plus de défauts
    assert h_calme[10] > h_calme[3]  # passage à la bande 13-24 mois
