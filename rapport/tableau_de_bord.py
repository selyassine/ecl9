"""Construit le tableau de bord interactif (`rapport/tableau.html`).

La page est un fichier HTML autonome : les résultats agrégés de
`rapport/resultats/` y sont inscrits en JSON, sans serveur ni dépendance
externe. Aucune donnée Freddie Mac prêt par prêt n'y figure.

    python rapport/tableau_de_bord.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent
RESULTATS = RACINE / "resultats"
MODELE_PAGE = RACINE / "tableau_modele.html"
SORTIE = RACINE / "tableau.html"
BALISE = "__DONNEES__"

MODELES = ("logistique", "lightgbm")
SCENARIOS = ("central", "defavorable", "favorable")
SURCOUCHES = {"sans": "", "nationale": "_surcouche", "etats": "_surcouche_etats"}
# En dessous de ce nombre de défauts résolus, la LGD réalisée d'une année est trop bruitée.
MIN_DEFAUTS_LGD = 100


def _arrondi(serie: pd.Series, chiffres: int = 0) -> list[float]:
    return [round(float(v), chiffres) for v in serie]


def donnees() -> dict:
    """Rassemble les résultats publiés dans un dictionnaire sérialisable."""
    figee = pd.read_csv(RESULTATS / "trimestriel_figee.csv")
    scen = pd.read_csv(RESULTATS / "trimestriel_scenarios.csv")
    arretes = sorted(figee["arrete"].unique())

    par_stade = {}
    for modele in MODELES:
        par_stade[modele] = {}
        for stade in (1, 2, 3):
            d = (
                figee[(figee["modele"] == modele) & (figee["stade"] == stade)]
                .set_index("arrete")
                .loc[arretes]
            )
            par_stade[modele][str(stade)] = {
                "prets": [int(v) for v in d["prets"]],
                "encours": _arrondi(d["encours"]),
                "ecl": _arrondi(d["ecl"]),
                "pertes": _arrondi(d["pertes_constatees"]),
                "pertes_estimees": _arrondi(d["pertes_non_resolus_estimees"]),
            }

    scenarios = {}
    tot = scen.groupby(["modele", "arrete"]).sum(numeric_only=True)
    for modele in MODELES:
        t = tot.loc[modele].loc[arretes]
        scenarios[modele] = {
            nom: {s: _arrondi(t[f"ecl_{s}{suffixe}"]) for s in SCENARIOS}
            for nom, suffixe in SURCOUCHES.items()
        }

    boot = pd.read_csv(RESULTATS / "bootstrap_ecart.csv").set_index("arrete").loc[arretes]
    reest = pd.read_csv(RESULTATS / "bootstrap_modeles.csv")
    stricte = pd.read_csv(RESULTATS / "coupure_stricte.csv").set_index(
        ["dernier_arrete_entrainement", "modele"]
    )
    ecart_strict = {
        coupure: round(
            float(
                stricte.loc[(coupure, "lightgbm"), "ecl_2007-12"]
                / stricte.loc[(coupure, "logistique"), "ecl_2007-12"]
                - 1
            ),
            4,
        )
        for coupure in ("2005-12", "2004-12")
    }

    lgd = pd.concat(
        [
            pd.read_csv(RESULTATS / "lgd_test_par_annee_defaut.csv"),
            pd.read_csv(RESULTATS / "lgd_apres_2010_par_annee_defaut.csv"),
        ]
    )
    lgd = lgd[lgd["defauts_resolus"] >= MIN_DEFAUTS_LGD].sort_values("annee_defaut")

    gen = pd.read_csv(RESULTATS / "generations_figee.csv")
    generations = []
    for millesime, g in gen.groupby("millesime"):
        g = g.set_index("modele")
        generations.append(
            {
                "millesime": int(millesime),
                "prets": int(g.loc["logistique", "prets"]),
                "encours": round(float(g.loc["logistique", "encours"])),
                "ecl": {m: round(float(g.loc[m, "ecl_maturite"])) for m in MODELES},
                "pertes": round(float(g.loc["logistique", "pertes_constatees"])),
                "pertes_estimees": round(float(g.loc["logistique", "pertes_non_resolus_estimees"])),
            }
        )

    return {
        "arretes": arretes,
        "par_stade": par_stade,
        "scenarios": scenarios,
        "bootstrap": {
            "ecart": _arrondi(boot["ecart_relatif"], 4),
            "bas": _arrondi(boot["ecart_relatif_bas"], 4),
            "haut": _arrondi(boot["ecart_relatif_haut"], 4),
        },
        "reestimation": [
            {
                "arrete": r.arrete,
                "tirages": int(r.tirages),
                "bas": round(float(r.ecart_relatif_bas), 4),
                "haut": round(float(r.ecart_relatif_haut), 4),
                "part_superieur": round(float(r.part_lightgbm_superieur), 4),
            }
            for r in reest.itertuples()
        ],
        "coupure_stricte": ecart_strict,
        "lgd": {
            "annees": [int(a) for a in lgd["annee_defaut"]],
            "defauts": [int(n) for n in lgd["defauts_resolus"]],
            "realisee": _arrondi(lgd["lgd_realisee_ponderee"], 4),
            "prevue": _arrondi(lgd["lgd_prevue_ponderee"], 4),
            "min_defauts": MIN_DEFAUTS_LGD,
        },
        "generations": generations,
    }


def construire(sortie: Path = SORTIE) -> Path:
    """Écrit la page autonome et renvoie son chemin."""
    page = MODELE_PAGE.read_text(encoding="utf-8")
    if page.count(BALISE) != 1:
        raise ValueError(f"le modèle doit contenir la balise {BALISE} une seule fois")
    # « </ » est échappé pour que le JSON ne puisse pas fermer la balise <script>.
    contenu = json.dumps(donnees(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    sortie.write_text(page.replace(BALISE, contenu), encoding="utf-8")
    return sortie


if __name__ == "__main__":
    print(construire())
