"""Le module definitions doit dire la même chose que docs/decisions.md."""

import math
from pathlib import Path

from ecl9 import definitions as d

DECISIONS = (Path(__file__).parents[1] / "docs" / "decisions.md").read_text(encoding="utf-8")


def test_date_du_journal():
    assert f"## {d.DATE_DECISIONS}" in DECISIONS


def test_ponderations_somment_a_un():
    assert math.isclose(sum(d.PONDERATIONS_SCENARIOS.values()), 1.0)
    assert "central 50 %, défavorable 30 %, favorable 20 %" in DECISIONS


def test_codes_de_defaut_documentes():
    for code in d.CODES_SOLDE_NUL_DEFAUT:
        assert f"`{code}`" in DECISIONS


def test_seuils_documentes():
    assert "supérieur ou égal à 3" in DECISIONS
    assert "**2 fois**" in DECISIONS and d.SEUIL_RATIO_PD_STADE2 == 2.0
    assert d.SEUIL_RATIO_PD_STADE2 in d.GRILLE_SEUILS_STADE2
    assert "{1,5 ; 2 ; 2,5 ; 3 ; 4}" in DECISIONS
    assert f"`{d.GRAINE}`" in DECISIONS


def test_series_fred_documentees():
    for serie in d.SERIES_FRED:
        assert f"`{serie}`" in DECISIONS


def test_decoupage():
    assert list(d.ANNEES_ENTRAINEMENT) == [2000, 2001, 2002, 2003, 2004, 2005]
    assert list(d.ANNEES_TEST) == [2006, 2007, 2008]
    assert "31/12/2005" in DECISIONS
