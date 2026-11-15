"""Le tableau de bord se construit à partir des seuls résultats versionnés."""

import importlib.util
import json
from pathlib import Path

import pytest

RAPPORT = Path(__file__).resolve().parents[1] / "rapport"


@pytest.fixture(scope="module")
def tableau():
    spec = importlib.util.spec_from_file_location("tableau_de_bord", RAPPORT / "tableau_de_bord.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_donnees_coherentes(tableau):
    d = tableau.donnees()
    n = len(d["arretes"])
    assert n == 20
    assert all(len(v) == n for v in d["bootstrap"].values())
    i = d["arretes"].index("2007-12")
    ecl = {m: sum(d["par_stade"][m][s]["ecl"][i] for s in "123") for m in tableau.MODELES}
    assert ecl["lightgbm"] / ecl["logistique"] - 1 == pytest.approx(
        d["bootstrap"]["ecart"][i], abs=1e-3
    )
    # Le stade 3 ne dépend pas du modèle de PD.
    assert d["par_stade"]["lightgbm"]["3"]["ecl"] == d["par_stade"]["logistique"]["3"]["ecl"]


def test_ponderation_de_reference_retrouvee(tableau):
    """La page recombine les scénarios : 50/30/20 doit redonner la provision publiée."""
    import pandas as pd

    d = tableau.donnees()
    publie = pd.read_csv(tableau.RESULTATS / "trimestriel_scenarios.csv")
    publie = publie.groupby(["modele", "arrete"])["ecl_ponderee"].sum()
    for modele in tableau.MODELES:
        s = d["scenarios"][modele]["sans"]
        for i, arrete in enumerate(d["arretes"]):
            recombine = 0.5 * s["central"][i] + 0.3 * s["defavorable"][i] + 0.2 * s["favorable"][i]
            assert recombine == pytest.approx(publie[(modele, arrete)], rel=1e-6)


def test_page_autonome(tableau, tmp_path):
    page = tableau.construire(tmp_path / "tableau.html").read_text(encoding="utf-8")
    assert tableau.BALISE not in page
    debut = page.index('<script id="donnees" type="application/json">') + 45
    json.loads(page[debut : page.index("</script>", debut)])
    assert "http" not in page.replace("https://github.com/selyassine/ecl9", "").replace(
        "http://www.w3.org/2000/svg", ""
    )
