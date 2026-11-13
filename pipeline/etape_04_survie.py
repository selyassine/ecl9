"""Étape 4 : PD à maturité par survie discrète (D-023, D-025).

Entrées : data/intermediaire/panneau/, octroi.parquet, data/brut/fred/
Sorties : sorties/survie/modele.pkl
          rapport/resultats/survie_*.csv (agrégats publiables)
"""

import pickle
import time
from pathlib import Path

import pandas as pd

from ecl9 import macro, survie, validation
from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, DERNIER_ARRETE_ENTRAINEMENT
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "sorties" / "survie"
RESULTATS = RACINE / "rapport" / "resultats"
COLONNES = [
    "loan_id",
    "period",
    "loan_age",
    "current_interest_rate",
    "defaut",
    "annee_octroi",
]
FIN_TEST = pd.Period("2010-12", "M")


def lire(annees, debut: pd.Period | None, fin: pd.Period, octroi, m) -> pd.DataFrame:
    morceaux = []
    for a in annees:
        p = pd.read_parquet(
            DOSSIER_DONNEES / "intermediaire" / "panneau" / f"millesime_{a}.parquet",
            columns=COLONNES,
        )
        p["period"] = pd.PeriodIndex(p["period"], freq="M")
        garde = p["period"] <= fin
        if debut is not None:
            garde &= p["period"] >= debut
        morceaux.append(survie.preparer(p[garde], octroi, m))
    return pd.concat(morceaux, ignore_index=True)


def attendus_observes(d: pd.DataFrame, colonne: str, par: str) -> pd.DataFrame:
    t = d.groupby(par).agg(
        prets_mois=("defaut", "size"), observes=("defaut", "sum"), attendus=(colonne, "sum")
    )
    t["attendu_sur_observe"] = t["attendus"] / t["observes"]
    return t


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    RESULTATS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    octroi = pd.read_parquet(DOSSIER_DONNEES / "intermediaire" / "octroi.parquet")
    m = macro.charger(DOSSIER_DONNEES / "brut" / "fred")
    fin_app = pd.Period(DERNIER_ARRETE_ENTRAINEMENT, "M")

    app = lire(ANNEES_ENTRAINEMENT, None, fin_app, octroi, m)
    ech = survie.echantillonner(app)
    print(
        f"Entraînement : {len(app):,} prêts-mois, {int(app['defaut'].sum()):,} défauts, "
        f"échantillon pondéré {len(ech):,} ({time.time() - t0:.0f} s)"
    )
    modele = survie.ajuster(ech)
    with open(SORTIE / "modele.pkl", "wb") as f:
        pickle.dump(modele, f)
    app["h"] = survie.hasards(modele, app)
    print(f"Modèle estimé ({time.time() - t0:.0f} s)")

    test = lire(ANNEES_TEST, pd.Period("2006-01", "M"), FIN_TEST, octroi, m)
    test["h_macro_realisee"] = survie.hasards(modele, test)
    figee = test.copy()
    decembre_2005 = m.loc[fin_app]
    for c in decembre_2005.index:
        figee[c] = decembre_2005[c]
    figee["ecart_taux"] = figee["current_interest_rate"] - decembre_2005["taux_30a"]
    test["h_macro_figee"] = survie.hasards(modele, figee)
    del figee
    test["annee"] = test["period"].dt.year
    print(f"Test : {len(test):,} prêts-mois ({time.time() - t0:.0f} s)")

    lignes = []
    for nom, d, col in [
        ("entrainement", app, "h"),
        ("test, macro réalisée", test, "h_macro_realisee"),
        ("test, macro figée à déc. 2005", test, "h_macro_figee"),
    ]:
        lignes.append(
            {
                "perimetre": nom,
                "prets_mois": len(d),
                "observes": int(d["defaut"].sum()),
                "attendus": float(d[col].sum()),
                "attendu_sur_observe": float(d[col].sum() / d["defaut"].sum()),
                "auc": validation.auc(d["defaut"], d[col]),
            }
        )
    mesures = pd.DataFrame(lignes)
    mesures.to_csv(RESULTATS / "survie_mesures.csv", index=False)

    par_annee = attendus_observes(test, "h_macro_realisee", "annee").join(
        attendus_observes(test, "h_macro_figee", "annee")[["attendus", "attendu_sur_observe"]],
        rsuffix="_macro_figee",
    )
    par_annee.to_csv(RESULTATS / "survie_par_annee.csv")
    par_millesime = attendus_observes(test, "h_macro_realisee", "annee_octroi")
    par_millesime.to_csv(RESULTATS / "survie_par_millesime.csv")

    # Table de mortalité : hasard moyen observé et ajusté par bande d'âge (entraînement).
    table = app.groupby("bande_age").agg(
        prets_mois=("defaut", "size"), observe=("defaut", "mean"), ajuste=("h", "mean")
    )
    table["observe_annualise"] = 1 - (1 - table["observe"]) ** 12
    table.to_csv(RESULTATS / "survie_table_age.csv")

    # Coefficients standardisés de la macro.
    noms = modele.named_steps["preparation"].get_feature_names_out()
    coef = pd.Series(modele.named_steps["logit"].coef_[0], index=noms)
    coef_macro = coef[[f"num__{v}" for v in survie.VARIABLES_MACRO]]
    coef_macro.rename("coefficient_standardise").to_csv(RESULTATS / "survie_coef_macro.csv")

    print(mesures.round(4).to_string(index=False))
    print(par_annee.round(3).to_string())
    print(par_millesime.round(3).to_string())
    print(table.round(5).to_string())
    print(coef_macro.round(3).to_string())
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
