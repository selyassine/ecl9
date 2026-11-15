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
    assert r.loc["P", "perte_montant"] == pytest.approx(30_000)
    assert np.isnan(r.loc["R", "perte_montant"])
    assert str(r.loc["P", "mois_defaut"]) == "2001-03"
    assert r.loc["P", "crd_defaut"] == 100_000
    assert r.loc["R", "resolution"] == "regularisation"
    assert str(r.loc["R", "mois_fin_defaut"]) == "2001-03"  # retour à jour
    assert str(r.loc["P", "mois_fin_defaut"]) == "2002-01"  # liquidation
    assert pd.isna(r.loc["N", "mois_fin_defaut"])
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
            "cltv_reevaluee": rng.uniform(50, 95, n),
            "credit_score": rng.normal(700, 50, n),
            "mi_pct": rng.choice([0, 25], n),
            "age_defaut": rng.integers(6, 60, n),
        }
    )
    p_regul = 1 / (1 + np.exp(-(1 - 0.05 * (x["cltv_reevaluee"] - 70))))
    regul = rng.random(n) < p_regul
    sev = np.clip(0.2 + 0.01 * (x["cltv_reevaluee"] - 70) + rng.normal(0, 0.1, n), 0, 1)
    d = x.assign(
        resolution=np.where(regul, "regularisation", "perte"),
        severite=np.where(regul, np.nan, sev),
    )
    m = lgd.ajuster(d)
    prevue = m.predire(d)
    assert prevue.min() >= 0 and prevue.max() <= 1
    assert prevue.mean() == pytest.approx(lgd.lgd_realisee(d).mean(), rel=0.05)
    # La LGD croît avec la CLTV réévaluée.
    assert np.corrcoef(x["cltv_reevaluee"], prevue)[0, 1] > 0.5


def test_cltv_reevaluee_a_la_main():
    prets = pd.DataFrame(
        {
            "orig_cltv": [80.0, np.nan, 90.0],
            "orig_ltv": [80.0, 70.0, 90.0],
            "orig_upb": [100_000.0, 200_000.0, 100_000.0],
            "current_upb": [90_000.0, 200_000.0, 100_000.0],
            "property_state": ["CA", "TX", "PR"],
        }
    )
    mois = pd.period_range("2006-01", "2008-12", freq="M")
    etats = pd.DataFrame({"CA": np.linspace(200, 130, len(mois)), "TX": 100.0}, index=mois)
    national = pd.Series(np.linspace(100, 80, len(mois)), index=mois)
    octroi = pd.PeriodIndex(["2006-01"] * 3, freq="M")
    valeur = pd.PeriodIndex(["2008-12", "2008-12", "2008-12"], freq="M")
    c = lgd.cltv_reevaluee(prets, octroi, valeur, etats, national)
    # CA : 80 × 0,9 × 200 / 130 ; TX : LTV faute de CLTV, prix stables ;
    # PR : pas d'indice d'État, indice national 100 / 80.
    np.testing.assert_allclose(c, [80 * 0.9 * 200 / 130, 70.0, 90 * 100 / 80])


def test_lgd_actualisee_a_la_main():
    class Fixe:
        def predict_proba(self, x):
            return np.tile([0.6, 0.4], (len(x), 1))  # P(régularisation) = 0,4

        def predict(self, x):
            return np.full(len(x), 0.5)  # sévérité

    m = lgd.ModeleLGD(Fixe(), Fixe(), ("a",), delai_resolution_mois=12.0)
    x = pd.DataFrame({"a": [0.0, 0.0, 0.0]})
    np.testing.assert_allclose(m.predire(x), 0.6 * 0.5)
    taux = np.array([0.0, 0.12, 0.12])
    ecoules = np.array([0.0, 0.0, 20.0])
    attendu = [
        0.6 * 0.5,  # taux nul : pas d'effet
        0.6 * (1 - 0.5 * 1.01**-12),  # 12 mois à 1 % par mois
        0.6 * 0.5,  # délai déjà écoulé : recouvrement immédiat
    ]
    np.testing.assert_allclose(m.predire_actualisee(x, taux, ecoules), attendu)
    # L'actualisation ne peut qu'augmenter la LGD.
    assert (m.predire_actualisee(x, taux, ecoules) >= m.predire(x) - 1e-12).all()


def test_regularises_etats_transitions_et_table():
    from ecl9 import regularises as rg

    na = None
    s = _suivi(
        [
            # A : défaut en 2001-03, régularisé 2001-04 à 2001-06, nouveau défaut en 2001-07.
            ("A", "2001-02", 100, "02", 1, na, na, na),
            ("A", "2001-03", 100, "03", 2, na, na, na),
            ("A", "2001-04", 100, "00", 3, na, na, na),
            ("A", "2001-05", 100, "01", 4, na, na, na),
            ("A", "2001-06", 100, "02", 5, na, na, na),
            ("A", "2001-07", 100, "03", 6, na, na, na),
            # B : défaut en 2001-03, régularisé, remboursé (01) en 2001-06.
            ("B", "2001-03", 100, "03", 2, na, na, na),
            ("B", "2001-04", 100, "00", 3, na, na, na),
            ("B", "2001-05", 100, "00", 4, na, na, na),
            ("B", "2001-06", 0, "00", 5, "01", na, 100),
            # C : jamais en défaut, ignoré.
            ("C", "2001-03", 100, "00", 2, na, na, na),
        ]
    )
    e = rg.etats_apres_defaut(s)
    assert set(e["loan_id"]) == {"A", "B"}
    a = e[e["loan_id"] == "A"]
    assert a["en_defaut"].tolist() == [True, False, False, False, True]
    assert a["mois_depuis_regul"].tolist() == [0, 1, 2, 3, 0]
    t = rg.transitions(e)
    # A : 3 mois régularisés dont le dernier suivi d'un défaut ; B : 2 mois, le
    # second suivi d'un remboursement (le mois du remboursement n'a pas de suite).
    assert len(t) == 5
    assert t["redefaut"].sum() == 1 and t["rembt"].sum() == 1
    table = rg.table_hasards(t)
    assert table["bande"].tolist() == list(rg.NOMS_BANDES)
    # Bande 1-3 : 5 prêts-mois, 1 nouveau défaut, 1 remboursement.
    assert table.loc[0, ["prets_mois", "redefauts", "remboursements"]].tolist() == [5, 1, 1]
    assert table.loc[0, "hasard_redefaut"] == pytest.approx(0.2)
    assert table.loc[1, "hasard_redefaut"] == 0.0


def test_regularises_projection_suit_les_bandes():
    from ecl9 import regularises as rg

    table = pd.DataFrame(
        {
            "bande": rg.NOMS_BANDES,
            "hasard_redefaut": [0.05, 0.04, 0.03, 0.02, 0.01],
            "hasard_rembt": [0.0, 0.001, 0.002, 0.003, 0.004],
        }
    )
    hd, hp = rg.projeter(table, np.array([2, 24]), 4)
    # Prêt régularisé depuis 2 mois : mois 2, 3 (bande 1-3) puis 4, 5 (bande 4-6).
    np.testing.assert_allclose(hd[0], [0.05, 0.05, 0.04, 0.04])
    # Depuis 24 mois : mois 24 (bande 13-24) puis 25 et plus.
    np.testing.assert_allclose(hd[1], [0.02, 0.01, 0.01, 0.01])
    np.testing.assert_allclose(hp[1], [0.003, 0.004, 0.004, 0.004])
