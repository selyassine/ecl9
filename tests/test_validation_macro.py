"""Mesures de validation et table macro, sur des cas calculés à la main."""

import math

import numpy as np
import pandas as pd
import pytest

from ecl9 import macro, validation


def test_auc_et_gini():
    # y = [0, 0, 1, 1], pd = [0,1 ; 0,4 ; 0,35 ; 0,8]. Paires (défaut, sain) bien ordonnées :
    # 0,35 > 0,1 oui ; 0,35 > 0,4 non ; 0,8 > 0,1 oui ; 0,8 > 0,4 oui.
    # AUC = 3/4, Gini = 2 × 0,75 - 1 = 0,5.
    y, p = [0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]
    assert validation.auc(y, p) == pytest.approx(0.75)
    assert validation.gini(y, p) == pytest.approx(0.5)


def test_brier_et_rapport():
    # ((0,2)² + (0,4)²) / 2 = (0,04 + 0,16) / 2 = 0,10 ; somme des PD 0,8 pour 1 défaut.
    assert validation.brier([0, 1], [0.2, 0.6]) == pytest.approx(0.10)
    assert validation.rapport_attendu_observe([0, 1], [0.2, 0.6]) == pytest.approx(0.8)


def test_psi_a_la_main():
    # Référence : 4 classes de 25 %. Comparée : 10 %, 20 %, 30 %, 40 %.
    # PSI = (0,10-0,25) ln(0,4) + (0,20-0,25) ln(0,8) + (0,30-0,25) ln(1,2) + (0,40-0,25) ln(1,6)
    attendu = (
        -0.15 * math.log(0.4) - 0.05 * math.log(0.8) + 0.05 * math.log(1.2) + 0.15 * math.log(1.6)
    )
    reference = np.repeat([0.5, 1.5, 2.5, 3.5], 25)
    comparee = np.repeat([0.5, 1.5, 2.5, 3.5], [10, 20, 30, 40])
    assert validation.psi(reference, comparee, n_classes=4) == pytest.approx(attendu)
    assert validation.psi(reference, reference, n_classes=4) == pytest.approx(0.0)


def test_calibration_par_classe():
    p = np.linspace(0.01, 0.10, 10)
    y = np.array([0] * 9 + [1])
    t = validation.calibration(y, p, n_classes=2)
    assert t["n"].tolist() == [5, 5]
    assert t["observe"].tolist() == [0.0, 0.2]
    assert t["pd_moyenne"].tolist() == pytest.approx([0.03, 0.08])


def test_table_macro_decalages():
    mois = pd.period_range("2000-01", "2001-06", freq="M")
    chomage = pd.Series(np.arange(len(mois), dtype=float), index=mois, name="UNRATE")
    hpi = pd.Series(100 * 1.01 ** np.arange(len(mois)), index=mois, name="CSUSHPISA")
    taux = pd.Series(7.0, index=mois)
    t = macro.table_macro(
        {"UNRATE": chomage, "CSUSHPISA": hpi, "MORTGAGE30US": taux, "DGS10": taux - 2}
    )
    juin = pd.Period("2001-06", "M")
    # Chômage connu en juin 2001 = valeur de mai 2001 = 16 ; un an plus tôt 4 → +12.
    assert t.loc[juin, "chomage"] == 16
    assert t.loc[juin, "chomage_var12"] == 12
    # Indice décalé de 2 mois, croissance 1 % par mois → 1,01^12 - 1.
    assert t.loc[juin, "hpi_var12"] == pytest.approx(1.01**12 - 1)
    assert t.loc[juin, "taux_10a"] == 5.0


def test_lecture_fred_hebdomadaire(tmp_path):
    chemin = tmp_path / "MORTGAGE30US.csv"
    chemin.write_text(
        "observation_date,MORTGAGE30US\n2001-01-04,7.0\n2001-01-11,7.2\n2001-02-01,6.9\n"
    )
    s = macro.lire_serie(chemin)
    assert s[pd.Period("2001-01", "M")] == pytest.approx(7.1)
    assert s[pd.Period("2001-02", "M")] == pytest.approx(6.9)
