"""Chaque brique vérifiée sur un cas calculé à la main.

Les valeurs attendues sont écrites en clair avec leur calcul, pour pouvoir
être refaites sur papier ou dans un tableur.
"""

import numpy as np
import pytest

from ecl9 import ead, ecl, staging

# ---------------------------------------------------------------- EAD (D-008)


def test_amortissement_taux_nul():
    # 1 200 sur 12 mois à 0 % : 100 par mois, CRD 1 200, 1 100, …, 100.
    assert ead.mensualite(1200, 0.0, 12) == pytest.approx(100.0)
    np.testing.assert_allclose(ead.echeancier_crd(1200, 0.0, 12), np.arange(1200, 0, -100))


def test_amortissement_deux_mois_a_12_pourcent():
    # i = 1 % par mois. P = 1000 × 0,01 / (1 - 1,01^-2) = 507,512438
    # CRD début mois 2 = 1000 × 1,01 - 507,512438 = 502,487562
    # Contrôle : 502,487562 × 1,01 = 507,512438 = P, le prêt s'éteint.
    assert ead.mensualite(1000, 0.12, 2) == pytest.approx(507.512438, abs=1e-6)
    np.testing.assert_allclose(ead.echeancier_crd(1000, 0.12, 2), [1000, 502.487562], atol=1e-6)


def test_mensualite_refuse_duree_nulle():
    with pytest.raises(ValueError):
        ead.mensualite(1000, 0.05, 0)


# ------------------------------------------------- Formule ECL (D-006, D-007)


def test_pd_marginales():
    # h = (0,1 ; 0,2 ; 0,5) → S(0) = 1, S(1) = 0,9, S(2) = 0,72
    # PDmarg = (0,1 ; 0,9 × 0,2 ; 0,72 × 0,5) = (0,1 ; 0,18 ; 0,36)
    np.testing.assert_allclose(ecl.pd_marginales([0.1, 0.2, 0.5]), [0.1, 0.18, 0.36])


def test_facteurs_actualisation():
    # r = 12 % → 1/1,01 = 0,990099 ; 1/1,0201 = 0,980296
    np.testing.assert_allclose(ecl.facteurs_actualisation(0.12, 2), [0.990099, 0.980296], atol=1e-6)


def test_perte_attendue_deux_mois():
    # h = (0,1 ; 0,2), LGD = 0,5, EAD = (1000 ; 502,487562), r = 12 %
    # mois 1 : 0,10 × 0,5 × 1000       / 1,01   = 49,504950
    # mois 2 : 0,18 × 0,5 × 502,487562 / 1,0201 = 44,332793
    # total                                     = 93,837743
    valeur = ecl.perte_attendue([0.1, 0.2], 0.5, [1000, 502.487562], 0.12)
    assert valeur == pytest.approx(93.837743, abs=1e-5)


def test_ponderation_des_scenarios():
    # Un mois, LGD 1, EAD 100, r = 0 : ECL_s = 100 × h_s
    # 0,5 × 1 + 0,3 × 4 + 0,2 × 0,5 = 0,5 + 1,2 + 0,1 = 1,8
    h = {"central": [0.01], "defavorable": [0.04], "favorable": [0.005]}
    assert ecl.perte_attendue_ponderee(h, 1.0, [100.0], 0.0) == pytest.approx(1.8)


def test_ponderation_incomplete_refusee():
    with pytest.raises(ValueError):
        ecl.perte_attendue_ponderee({"central": [0.1]}, 1.0, [100.0], 0.0)


def test_horizon():
    assert ecl.horizon(1, 300) == 12
    assert ecl.horizon(1, 7) == 7
    assert ecl.horizon(2, 300) == 300
    assert ecl.horizon(3, 300) == 0


def test_ecl_pret_stade3():
    # Stade 3 : LGD × CRD = 0,4 × 150 000 = 60 000
    assert ecl.ecl_pret(3, 150_000, 0.06, 200, 0.4) == pytest.approx(60_000)


def test_ecl_pret_stade1_tronque_a_12_mois():
    # Hasard constant h = 0,01 sur 24 mois fournis, r = 0, prêt de 2 400 sur 24 mois.
    # EAD(t) = 2400 - 100 (t - 1). Stade 1 : 12 mois seulement, LGD = 1.
    # ECL = somme t=1..12 de 0,99^(t-1) × 0,01 × (2500 - 100 t)
    t = np.arange(1, 13)
    attendu = np.sum(0.99 ** (t - 1) * 0.01 * (2500 - 100 * t))
    h = {s: np.full(24, 0.01) for s in ("central", "defavorable", "favorable")}
    assert ecl.ecl_pret(1, 2400, 0.0, 24, 1.0, h) == pytest.approx(attendu)
    # En stade 2, les 24 mois comptent et la provision augmente.
    assert ecl.ecl_pret(2, 2400, 0.0, 24, 1.0, h) > attendu


# ---------------------------------------------------- Stades (D-002 à D-004)


def test_pd_annualisee():
    # 1 - (1 - 0,19)^(12/24) = 1 - 0,9 = 0,1
    assert staging.pd_annualisee(0.19, 24) == pytest.approx(0.1)
    assert staging.pd_annualisee(0.05, 12) == pytest.approx(0.05)


def test_stades():
    # PD à maturité à l'octroi : 0,19 sur 24 mois → 10 % par an.
    # prêt 0 : sain, PD annualisée inchangée                     → stade 1
    # prêt 1 : 1 mensualité de retard                            → stade 2
    # prêt 2 : PD cumulée 0,36 sur 12 mois → 36 % ≥ 2 × 10 %      → stade 2
    # prêt 3 : PD cumulée 0,19 sur 12 mois → 19 % < 20 %          → stade 1
    # prêt 4 : en défaut                                         → stade 3
    # prêt 5 : retard inconnu, PD inchangée                      → stade 1
    resultat = staging.stade(
        en_defaut=[False, False, False, False, True, False],
        retard_mensualites=[0, 1, 0, 0, 3, np.nan],
        pd_vie_arrete=[0.19, 0.19, 0.36, 0.19, 1.0, 0.19],
        mois_restants_arrete=[24, 24, 12, 12, 12, 24],
        pd_vie_octroi=[0.19] * 6,
        mois_restants_octroi=[24] * 6,
    )
    np.testing.assert_array_equal(resultat, [1, 2, 2, 1, 3, 1])


def test_seuil_de_stade2_variable():
    # Ratio de 1,9 : stade 2 avec un seuil de 1,5, stade 1 avec le seuil de 2.
    args = dict(
        en_defaut=[False],
        retard_mensualites=[0],
        pd_vie_arrete=[0.19],
        mois_restants_arrete=[12],
        pd_vie_octroi=[0.10],
        mois_restants_octroi=[12],
    )
    assert staging.stade(**args, seuil=1.5)[0] == 2
    assert staging.stade(**args)[0] == 1
