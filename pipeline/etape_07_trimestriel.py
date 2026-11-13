"""Étape 7 : provision trimestrielle 2006-2010, stades complets et backtest (D-030 à D-032).

Pour chaque arrêté trimestriel et chaque modèle de PD à 12 mois (logistique,
LightGBM) : stades 1 et 2 par retard et dégradation de la PD à maturité depuis
l'octroi, stade 3 pour les défauts en cours, provision, puis pertes
réellement constatées sur le même périmètre et le même horizon.

Usage : python pipeline/etape_07_trimestriel.py [--trajectoire figee|scenarios]
Sorties : sorties/trimestriel/, rapport/resultats/trimestriel_*.csv
"""

import argparse
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ecl9 import macro, moteur, staging, survie
from ecl9 import pd as pdm
from ecl9 import scenarios as sc
from ecl9.definitions import (
    ANNEES_TEST,
    HORIZON_STADE1_MOIS,
    PONDERATIONS_SCENARIOS,
    SEUIL_RATIO_PD_STADE2,
)
from ecl9.telechargement import DOSSIER_DONNEES

RACINE = Path(__file__).resolve().parents[1]
SORTIES = RACINE / "sorties"
RESULTATS = RACINE / "rapport" / "resultats"
INTER = DOSSIER_DONNEES / "intermediaire"
MODELES = ("logistique", "lightgbm")
ARRETES = pd.period_range("2006-03", "2010-12", freq="Q-DEC").asfreq("M", "end")
TAILLE_LOT = 20_000


def charger_modeles():
    with open(SORTIES / "pd12" / "modeles.pkl", "rb") as f:
        pd12 = pickle.load(f)
    with open(SORTIES / "survie" / "modele.pkl", "rb") as f:
        s = pickle.load(f)
    with open(SORTIES / "lgd" / "modele.pkl", "rb") as f:
        lgd = pickle.load(f)
    return pd12, s[s["retenu"]], lgd


def trajectoire_figee(m: pd.DataFrame, arrete: pd.Period, n_mois: int) -> pd.DataFrame:
    t = pd.DataFrame([m.loc[arrete]] * n_mois, columns=m.columns)
    t.index = pd.period_range(arrete + 1, periods=n_mois, freq="M")
    return t


def pd_cumulee_ancree(h: np.ndarray, pd12: np.ndarray, n: np.ndarray) -> np.ndarray:
    """PD cumulée sur ``n`` mois après ancrage des 12 premiers mois sur ``pd12``."""
    a = moteur.ancrer_matrice(h, pd12, np.minimum(HORIZON_STADE1_MOIS, n))
    dedans = np.arange(h.shape[1])[None, :] < n[:, None]
    return 1 - np.prod(np.where(dedans, 1 - a, 1.0), axis=1)


def pd_vie_octroi(octroi: pd.DataFrame, m: pd.DataFrame, modeles_pd12, modele_survie):
    """PD à maturité à l'octroi, pour chaque prêt de test et chaque modèle (D-030)."""
    o = octroi[octroi["annee_octroi"].isin(ANNEES_TEST)].reset_index(drop=True)
    o["period"] = pd.PeriodIndex(o["first_payment_date"], freq="M") - 1
    base = o[["loan_id", "period", "annee_octroi"]].assign(
        current_upb=o["orig_upb"],
        current_interest_rate=o["orig_interest_rate"],
        loan_age=0,
        retard=0,
        **{pdm.CIBLE: 0},
    )
    x = pdm.construire_variables(base, octroi, m)
    sortie = o[["loan_id"]].copy()
    sortie["duree_initiale"] = o["orig_loan_term"].astype(int).to_numpy()
    pd12 = {
        "logistique": pdm.predire_logistique(modeles_pd12["logistique"], x),
        "lightgbm": modeles_pd12["lightgbm"].predire(x),
    }
    prets = survie.preparer(base.drop(columns=[pdm.CIBLE, "retard"]), octroi, m)
    for nom in MODELES:
        sortie[f"pd_vie_octroi_{nom}"] = np.nan
    for mois, groupe in prets.groupby("period"):
        n_max = int(groupe["orig_loan_term"].max())
        for debut in range(0, len(groupe), TAILLE_LOT):
            lot = groupe.iloc[debut : debut + TAILLE_LOT]
            h = moteur.projeter_hasards(
                modele_survie, lot, mois, trajectoire_figee(m, mois, n_max), n_max
            )
            n = lot["orig_loan_term"].to_numpy(dtype=int)
            for nom in MODELES:
                sortie.loc[lot.index, f"pd_vie_octroi_{nom}"] = pd_cumulee_ancree(
                    h, pd12[nom][lot.index], n
                )
    return sortie


def actifs(arrete: pd.Period, octroi, m) -> pd.DataFrame:
    morceaux = []
    for a in ANNEES_TEST:
        if a > arrete.year:
            continue
        p = pd.read_parquet(INTER / "panneau" / f"millesime_{a}.parquet")
        p["period"] = pd.PeriodIndex(p["period"], freq="M")
        morceaux.append(p[(p["period"] == arrete) & p["defaut"].eq(0) & p["current_upb"].gt(0)])
    p = survie.preparer(pd.concat(morceaux, ignore_index=True), octroi, m)
    p["remaining_months_to_maturity"] = (
        p["remaining_months_to_maturity"]
        .fillna(p["orig_loan_term"] - p["loan_age"])
        .clip(lower=1)
        .astype(int)
    )
    return p


def pertes_constatees(prets: pd.DataFrame, defauts: pd.DataFrame, arrete, horizon_mois):
    """Perte constatée de chaque prêt actif : défaut après l'arrêté, dans l'horizon."""
    d = defauts.set_index("loan_id").reindex(prets["loan_id"])
    dans = (d["mois_defaut"] > arrete) & (d["mois_defaut"] <= arrete + horizon_mois)
    perte = np.where(dans & d["resolution"].eq("regularisation"), 0.0, d["perte_montant"])
    perte = np.where(dans, perte, 0.0)
    non_resolu = (dans & d["resolution"].eq("non_resolu")).to_numpy()
    return np.nan_to_num(perte), non_resolu


def calculer_arrete(arrete, octroi, m, pred, pd_octroi, defauts, modeles, hpi=None):
    """Lignes par modèle et stade ; avec ``hpi``, provision pondérée des scénarios (D-034)."""
    _, modele_survie, modele_lgd = modeles
    p = actifs(arrete, octroi, m)
    p = p.merge(
        pred[pred["period"] == arrete].drop(columns="period"),
        on="loan_id",
        how="inner",
        validate="1:1",
    )
    p = p.merge(pd_octroi, on="loan_id", how="left", validate="1:1")
    restants = p["remaining_months_to_maturity"].to_numpy(dtype=int)
    crd = p["current_upb"].to_numpy(dtype=float)
    taux = p["current_interest_rate"].to_numpy(dtype=float) / 100
    lgd = modele_lgd.predire(
        pd.DataFrame(
            {
                "orig_ltv": p["orig_ltv"],
                "credit_score": p["credit_score"],
                "ratio_crd": p["current_upb"] / p["orig_upb"],
                "mi_pct": p["mi_pct"],
                "age_defaut": p["loan_age"],
            }
        )
    )
    n_max = int(restants.max())
    traj = trajectoire_figee(m, arrete, n_max)
    if hpi is not None:
        trajs = {s: sc.trajectoire(s, m, hpi, arrete, n_max) for s in PONDERATIONS_SCENARIOS}
        mois_octroi = pd.PeriodIndex(
            p[["loan_id"]].merge(octroi[["loan_id", "first_payment_date"]], on="loan_id")[
                "first_payment_date"
            ],
            freq="M",
        )
        cltv0 = sc.cltv_arrete(
            p, hpi.reindex(mois_octroi - 1).to_numpy(dtype=float), float(hpi.loc[arrete])
        )
    resultats = {nom: {"stade": [], "ecl": [], "ecl_maturite": []} for nom in MODELES}
    for debut in range(0, len(p), TAILLE_LOT):
        sl = slice(debut, debut + TAILLE_LOT)
        h = moteur.projeter_hasards(modele_survie, p.iloc[sl], arrete, traj, n_max)
        if hpi is not None:
            # Écarts de logit au scénario central, appliqués après l'ancrage (D-036).
            ecarts = {}
            for s, t in trajs.items():
                ecart = 0.0
                if s != "central":
                    hs = moteur.projeter_hasards(modele_survie, p.iloc[sl], arrete, t, n_max)
                    ecart = moteur.logit(hs) - moteur.logit(h)
                surcouche = sc.surcouche(cltv0[sl], float(m.loc[arrete, "chomage_var12"]), t)
                ecarts[s] = ecart
                ecarts[f"{s}_surcouche"] = ecart + surcouche
        for nom in MODELES:
            pd12 = p[f"pd_{nom}"].to_numpy()[sl]
            pd_vie = pd_cumulee_ancree(h, pd12, restants[sl])
            st = staging.stade(
                en_defaut=np.zeros(len(pd12), dtype=bool),
                retard_mensualites=p["retard"].to_numpy()[sl],
                pd_vie_arrete=pd_vie,
                mois_restants_arrete=restants[sl],
                pd_vie_octroi=p[f"pd_vie_octroi_{nom}"].to_numpy()[sl],
                mois_restants_octroi=p["duree_initiale"].to_numpy()[sl],
                seuil=SEUIL_RATIO_PD_STADE2,
            )
            args = (crd[sl], taux[sl], restants[sl], lgd[sl], pd12, h)
            resultats[nom]["stade"].append(st)
            resultats[nom]["ecl"].append(moteur.provisions(st, *args))
            if hpi is None:
                resultats[nom]["ecl_maturite"].append(moteur.provisions(np.full(len(st), 2), *args))
            else:
                for cle, ecart in ecarts.items():
                    resultats[nom].setdefault(f"ecl_{cle}", []).append(
                        moteur.provisions(st, *args, ecart_logit=ecart)
                    )

    # Stade 3 : défauts survenus avant l'arrêté et pas encore sortis.
    d3 = defauts[
        (defauts["mois_defaut"] <= arrete)
        & (defauts["mois_fin_defaut"].isna() | (defauts["mois_fin_defaut"] > arrete))
        & (defauts["annee_octroi"] <= arrete.year)
    ]
    lgd3 = modele_lgd.predire(d3) if len(d3) else np.zeros(0)
    perte3 = np.where(d3["resolution"].eq("regularisation"), 0.0, d3["perte_montant"])

    lignes, details = [], []
    for nom in MODELES:
        st = np.concatenate(resultats[nom]["stade"])
        ecl = np.concatenate(resultats[nom]["ecl"])
        par_scenario = {
            c: np.concatenate(v)
            for c, v in resultats[nom].items()
            if c.startswith("ecl_") and c != "ecl_maturite"
        }
        if par_scenario:
            for suffixe in ("", "_surcouche"):
                par_scenario[f"ecl_ponderee{suffixe}"] = sum(
                    w * par_scenario[f"ecl_{s}{suffixe}"] for s, w in PONDERATIONS_SCENARIOS.items()
                )
        horizon = np.where(st == 1, HORIZON_STADE1_MOIS, 10_000)
        perte = np.zeros(len(p))
        non_resolu = np.zeros(len(p), dtype=bool)
        for h_mois in np.unique(horizon):
            masque = horizon == h_mois
            pr, nr = pertes_constatees(p[masque], defauts, arrete, int(h_mois))
            perte[masque], non_resolu[masque] = pr, nr
        for s in (1, 2):
            masque = st == s
            lignes.append(
                {
                    "arrete": str(arrete),
                    "modele": nom,
                    "stade": s,
                    "prets": int(masque.sum()),
                    "encours": crd[masque].sum(),
                    "ecl": ecl[masque].sum(),
                    "pertes_constatees": perte[masque].sum(),
                    "defauts_non_resolus": int(non_resolu[masque].sum()),
                    **{c: v[masque].sum() for c, v in par_scenario.items()},
                }
            )
        lignes.append(
            {
                "arrete": str(arrete),
                "modele": nom,
                "stade": 3,
                "prets": len(d3),
                "encours": d3["crd_defaut"].sum(),
                "ecl": float(np.sum(lgd3 * d3["crd_defaut"])),
                "pertes_constatees": float(np.nansum(perte3)),
                "defauts_non_resolus": int(d3["resolution"].eq("non_resolu").sum()),
                **{c: float(np.sum(lgd3 * d3["crd_defaut"])) for c in par_scenario},
            }
        )
        # Par génération, à la fin de l'année d'octroi : tout à maturité (D-032).
        if hpi is None and arrete.month == 12 and arrete.year in ANNEES_TEST:
            g = (p["annee_octroi"] == arrete.year).to_numpy()
            perte_vie, nr_vie = pertes_constatees(p[g], defauts, arrete, 10_000)
            details.append(
                {
                    "millesime": arrete.year,
                    "modele": nom,
                    "prets": int(g.sum()),
                    "encours": crd[g].sum(),
                    "ecl_maturite": np.concatenate(resultats[nom]["ecl_maturite"])[g].sum(),
                    "pertes_constatees": perte_vie.sum(),
                    "defauts_non_resolus": int(nr_vie.sum()),
                }
            )
    return lignes, details


def main(nom_trajectoire: str) -> None:
    t0 = time.time()
    hpi = (
        macro.indice_prix(DOSSIER_DONNEES / "brut" / "fred")
        if nom_trajectoire == "scenarios"
        else None
    )
    octroi = pd.read_parquet(INTER / "octroi.parquet")
    m = macro.charger(DOSSIER_DONNEES / "brut" / "fred")
    modeles = charger_modeles()
    pred = pd.read_parquet(SORTIES / "pd12" / "predictions_test.parquet")
    pred["period"] = pd.PeriodIndex(pred["period"], freq="M")
    pred = pred[["loan_id", "period", "pd_logistique", "pd_lightgbm"]]
    defauts = pd.read_parquet(INTER / "defauts.parquet")
    defauts = defauts[defauts["echantillon"].eq("test")]
    for c in ("mois_defaut", "mois_fin_defaut"):
        defauts[c] = pd.PeriodIndex(defauts[c], freq="M")

    sortie = SORTIES / "trimestriel"
    sortie.mkdir(parents=True, exist_ok=True)
    cache = sortie / "pd_vie_octroi.parquet"
    if cache.exists():
        pd_octroi = pd.read_parquet(cache)
    else:
        pd_octroi = pd_vie_octroi(octroi, m, modeles[0], modeles[1])
        pd_octroi.to_parquet(cache, index=False)
    print(f"PD à maturité à l'octroi : {len(pd_octroi):,} prêts ({time.time() - t0:.0f} s)")

    lignes, generations = [], []
    for arrete in ARRETES:
        fichier = sortie / nom_trajectoire / f"{arrete}.pkl"  # reprise après interruption
        if fichier.exists():
            lig, g = pd.read_pickle(fichier)
        else:
            lig, g = calculer_arrete(arrete, octroi, m, pred, pd_octroi, defauts, modeles, hpi)
            fichier.parent.mkdir(exist_ok=True)
            pd.to_pickle((lig, g), fichier)
        lignes += lig
        generations += g
        t = pd.DataFrame(lig)
        cols = [c for c in ("ecl", "ecl_ponderee", "ecl_ponderee_surcouche") if c in t]
        resume = t.groupby("modele")[[*cols, "pertes_constatees"]].sum()
        print(f"{arrete} ({time.time() - t0:.0f} s)\n{resume.round(0).to_string()}")

    suffixe = f"_{nom_trajectoire}"
    pd.DataFrame(lignes).to_csv(RESULTATS / f"trimestriel{suffixe}.csv", index=False)
    if generations:
        pd.DataFrame(generations).to_csv(RESULTATS / f"generations{suffixe}.csv", index=False)
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectoire", default="figee", choices=["figee", "scenarios"])
    main(parser.parse_args().trajectoire)
