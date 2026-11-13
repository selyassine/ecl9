"""Panneau prêt-mois sur de petits fichiers fabriqués au format Freddie Mac."""

import pandas as pd
import pytest

from ecl9 import donnees as dn


def _ligne_suivi(pret, periode, upb, statut, code="", taux=6.0, age=1, restant=359):
    champs = [""] * len(dn.COLONNES_SUIVI)
    valeurs = {
        "loan_id": pret,
        "period": periode,
        "current_upb": upb,
        "delinquency_status": statut,
        "loan_age": age,
        "remaining_months_to_maturity": restant,
        "zero_balance_code": code,
        "current_interest_rate": taux,
    }
    for nom, v in valeurs.items():
        champs[dn.COLONNES_SUIVI.index(nom)] = str(v)
    return "|".join(champs)


def _mois(debut, n):
    p = pd.Period(debut, freq="M")
    return [(p + k).strftime("%Y%m") for k in range(n)]


@pytest.fixture
def suivi(tmp_path):
    lignes = []
    # A : sain 2001-01 à 2002-12 (24 mois), jamais en défaut.
    lignes += [_ligne_suivi("A", m, 1000, "0") for m in _mois("2001-01", 24)]
    # B : retard croissant, 90 jours (statut 3) en 2001-09, suivi au-delà.
    statuts_b = ["0"] * 6 + ["1", "2", "3", "4", "5"]
    lignes += [
        _ligne_suivi("B", m, 1000, s) for m, s in zip(_mois("2001-01", 11), statuts_b, strict=True)
    ]
    # C : saisie (RA) en 2001-05 sans passer par 3 mensualités de retard.
    statuts_c = ["0", "0", "1", "2", "RA", "RA"]
    lignes += [
        _ligne_suivi("C", m, 1000, s) for m, s in zip(_mois("2001-01", 6), statuts_c, strict=True)
    ]
    # D : remboursé par anticipation (code 01) en 2001-04 : pas un défaut.
    lignes += [_ligne_suivi("D", m, 1000, "0") for m in _mois("2001-01", 3)]
    lignes += [_ligne_suivi("D", "200104", 0, "0", code="01")]
    # E : vente à découvert (code 03) en 2001-07, statut XX juste avant.
    lignes += [_ligne_suivi("E", m, 1000, "0") for m in _mois("2001-01", 5)]
    lignes += [_ligne_suivi("E", "200106", 1000, "XX"), _ligne_suivi("E", "200107", 0, "2", "03")]
    chemin = tmp_path / "sample_perf_2001.txt"
    chemin.write_text("\n".join(lignes) + "\n")
    return dn.lire_suivi(chemin)


def test_lecture(suivi):
    assert suivi["period"].dtype == "period[M]"
    assert suivi["current_upb"].dtype.kind == "f" or suivi["current_upb"].dtype.kind == "i"
    assert suivi["zero_balance_code"].dropna().unique().tolist() == ["01", "03"]


def test_definition_du_defaut(suivi):
    defaut = dn.marquer_defaut(suivi)
    premier = suivi[defaut].groupby("loan_id")["period"].min().astype(str).to_dict()
    assert premier == {"B": "2001-09", "C": "2001-05", "E": "2001-07"}


def test_panneau_arrete_au_premier_defaut(suivi):
    p = dn.construire_panneau(suivi)
    n = p.groupby("loan_id").size().to_dict()
    assert n == {"A": 24, "B": 9, "C": 5, "D": 4, "E": 7}
    assert p.groupby("loan_id")["defaut"].sum().to_dict() == {
        "A": 0,
        "B": 1,
        "C": 1,
        "D": 0,
        "E": 1,
    }
    assert p["sortie"].sum() == 5
    assert (
        p.loc[p["loan_id"].eq("E") & p["period"].astype(str).eq("2001-06"), "retard"].isna().all()
    )


def test_echantillon_pd12(suivi):
    e = dn.echantillon_pd12(dn.construire_panneau(suivi))
    cible = {(r.loan_id, str(r.period)): r.cible_defaut_12m for r in e.itertuples(index=False)}
    # Dernier mois du jeu : 2002-12. Seuls les arrêtés à fenêtre complète sont retenus.
    assert cible == {
        ("A", "2001-03"): 0,
        ("A", "2001-06"): 0,
        ("A", "2001-09"): 0,
        ("A", "2001-12"): 0,
        ("B", "2001-03"): 1,
        ("B", "2001-06"): 1,
        ("C", "2001-03"): 1,
        ("D", "2001-03"): 0,
        ("E", "2001-03"): 1,
        ("E", "2001-06"): 1,
    }


def test_fichier_trop_large(tmp_path):
    chemin = tmp_path / "large.txt"
    chemin.write_text("|".join(["x"] * (len(dn.COLONNES_SUIVI) + 1)) + "\n")
    with pytest.raises(ValueError, match="schéma connu"):
        dn.lire_suivi(chemin)


def test_sentinelles_octroi(tmp_path):
    champs = [""] * len(dn.COLONNES_OCTROI)
    valeurs = {
        "credit_score": "9999",
        "first_payment_date": "200103",
        "orig_ltv": "80",
        "orig_dti": "999",
        "loan_id": "F101Q1000001",
        "occupancy_status": "9",
    }
    for nom, v in valeurs.items():
        champs[dn.COLONNES_OCTROI.index(nom)] = v
    chemin = tmp_path / "sample_orig_2001.txt"
    chemin.write_text("|".join(champs) + "\n")
    o = dn.lire_octroi(chemin)
    assert o["credit_score"].isna().all() and o["orig_dti"].isna().all()
    assert o["occupancy_status"].isna().all()
    assert o.loc[0, "orig_ltv"] == 80
    assert o.loc[0, "cohorte"] == 2001


def test_fenetre_incomplete_exclue_meme_en_cas_de_defaut():
    # Jeu arrêté en 2002-12 ; prêt en défaut en 2002-09. L'arrêté 2002-06 n'a que
    # 6 mois de recul : il est retiré, sinon seuls les défauts resteraient.
    periodes = pd.period_range("2001-01", "2002-09", freq="M")
    p = pd.DataFrame({"loan_id": "F", "period": periodes, "defaut": 0})
    p.loc[p.index[-1], "defaut"] = 1
    sain = pd.DataFrame(
        {"loan_id": "G", "period": pd.period_range("2001-01", "2002-12", freq="M"), "defaut": 0}
    )
    e = dn.echantillon_pd12(pd.concat([p, sain], ignore_index=True))
    retenus = set(zip(e["loan_id"], e["period"].astype(str), strict=True))
    assert ("F", "2001-12") in retenus  # fenêtre 2002-01..2002-12 complète
    assert ("F", "2002-06") not in retenus
    assert (
        e.loc[
            e["loan_id"].eq("F") & e["period"].astype(str).eq("2001-12"), "cible_defaut_12m"
        ].item()
        == 1
    )
