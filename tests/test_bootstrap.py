"""Bootstrap de l'écart entre les deux modèles (D-037) sur des provisions simulées."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

CHEMIN = Path(__file__).resolve().parents[1] / "pipeline" / "etape_09_sensibilites.py"


@pytest.fixture(scope="module")
def e9():
    spec = importlib.util.spec_from_file_location("etape_09_sensibilites", CHEMIN)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except FileNotFoundError:  # sorties du pipeline absentes à l'import
        pytest.skip("pipeline non exécuté")
    return module


def test_ecart_proportionnel_intervalle_nul(e9):
    # LightGBM = 1,3 × logistique pour chaque prêt : l'écart relatif vaut 30 %
    # dans tous les tirages, quelle que soit la composition du portefeuille.
    rng = np.random.default_rng(1)
    log = rng.gamma(2.0, 100.0, 500)
    r = e9.bootstrap(log, 1.3 * log, np.random.default_rng(2))
    assert r["ecart_relatif"] == pytest.approx(0.3)
    assert r["ecart_relatif_bas"] == pytest.approx(0.3)
    assert r["ecart_relatif_haut"] == pytest.approx(0.3)
    assert r["ecart_absolu_bas"] < r["ecart_absolu"] < r["ecart_absolu_haut"]


def test_intervalle_encadre_l_estimation_et_reproductible(e9):
    rng = np.random.default_rng(3)
    log = rng.gamma(2.0, 100.0, 2000)
    lgbm = log * rng.lognormal(0.2, 0.5, 2000)
    a = e9.bootstrap(log, lgbm, np.random.default_rng(4))
    b = e9.bootstrap(log, lgbm, np.random.default_rng(4))
    assert a.equals(b)  # même graine, même intervalle
    assert a["ecart_relatif_bas"] < a["ecart_relatif"] < a["ecart_relatif_haut"]
    # Un portefeuille quatre fois plus grand resserre l'intervalle d'environ moitié.
    grand = e9.bootstrap(np.tile(log, 4), np.tile(lgbm, 4), np.random.default_rng(4))
    largeur = a["ecart_relatif_haut"] - a["ecart_relatif_bas"]
    largeur_grand = grand["ecart_relatif_haut"] - grand["ecart_relatif_bas"]
    assert 0.35 < largeur_grand / largeur < 0.65
