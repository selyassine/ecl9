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

from ecl9 import lgd as lgdm
from ecl9 import macro, moteur, staging, survie
from ecl9 import pd as pdm
from ecl9 import scenarios as sc
from ecl9.definitions import (
    ANNEES_TEST,
    HORIZON_STADE1_MOIS,
    PONDERATIONS_SCENARIOS,
    PROBATION_STADE2_MOIS,
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
# Remboursement anticipé en risque concurrent (D-040) ; désactivé par
# --sans-remboursement pour reproduire la version 1.
REMBOURSEMENT = True
PRIX_ETATS: pd.DataFrame | None = None  # indices FHFA par État (D-041, D-047)
PRIX_NATIONAL: pd.Series | None = None  # indice national, repli des États sans indice


def charger_prix() -> None:
    """Indices de prix nécessaires à la LGD (D-047) et à la surcouche (D-041)."""
    global PRIX_ETATS, PRIX_NATIONAL
    dossier = DOSSIER_DONNEES / "brut" / "fred"
    PRIX_NATIONAL = macro.indice_prix(dossier)
    PRIX_ETATS = macro.indices_prix_etats(dossier / "etats")


def lgd_actifs(modele_lgd, p, octroi, arrete, taux, prix_relatif: float = 1.0) -> np.ndarray:
    """LGD actualisée (D-049) des prêts actifs, CLTV réévaluée à l'arrêté (D-047).

    ``prix_relatif`` : niveau des prix d'un scénario rapporté à celui de
    l'arrêté ; la CLTV est divisée par ce niveau.
    """
    if PRIX_ETATS is None:
        charger_prix()
    x = lgdm.variables_actifs(p, octroi, arrete, PRIX_ETATS, PRIX_NATIONAL)
    x["cltv_reevaluee"] = x["cltv_reevaluee"] / prix_relatif
    return modele_lgd.predire_actualisee(x, taux)


def suffixe_version() -> str:
    return "" if REMBOURSEMENT else "_sans_remboursement"


def charger_modeles():
    with open(SORTIES / "pd12" / "modeles.pkl", "rb") as f:
        pd12 = pickle.load(f)
    with open(SORTIES / "survie" / "modele.pkl", "rb") as f:
        s = pickle.load(f)
    with open(SORTIES / "lgd" / "modele.pkl", "rb") as f:
        lgd = pickle.load(f)
    rembt = None
    if REMBOURSEMENT:
        with open(SORTIES / "remboursement" / "modele.pkl", "rb") as f:
            r = pickle.load(f)
        rembt = r[r["retenu"]]
    return pd12, s[s["retenu"]], lgd, rembt


def hasards_rembt(modele, prets, arrete, traj, n_mois):
    if modele is None:
        return None
    return moteur.projeter_hasards(modele, prets, arrete, traj, n_mois)


def trajectoire_figee(m: pd.DataFrame, arrete: pd.Period, n_mois: int) -> pd.DataFrame:
    t = pd.DataFrame([m.loc[arrete]] * n_mois, columns=m.columns)
    t.index = pd.period_range(arrete + 1, periods=n_mois, freq="M")
    return t


def pd_cumulee_ancree(
    h: np.ndarray, pd12: np.ndarray, n: np.ndarray, hp: np.ndarray | None = None
) -> np.ndarray:
    """PD cumulée sur ``n`` mois après ancrage des 12 premiers mois sur ``pd12``.

    Avec ``hp``, remboursement anticipé concurrent (D-040).
    """
    a = moteur.ancrer_matrice(h, pd12, np.minimum(HORIZON_STADE1_MOIS, n), hp=hp)
    dedans = np.arange(h.shape[1])[None, :] < n[:, None]
    if hp is None:
        return 1 - np.prod(np.where(dedans, 1 - a, 1.0), axis=1)
    return moteur.incidence(np.where(dedans, a, 0.0), np.where(dedans, hp, 0.0))[:, -1]


def pd_vie_octroi(octroi: pd.DataFrame, m: pd.DataFrame, modeles_pd12, modele_survie, rembt):
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
            traj = trajectoire_figee(m, mois, n_max)
            h = moteur.projeter_hasards(modele_survie, lot, mois, traj, n_max)
            hp = hasards_rembt(rembt, lot, mois, traj, n_max)
            n = lot["orig_loan_term"].to_numpy(dtype=int)
            for nom in MODELES:
                sortie.loc[lot.index, f"pd_vie_octroi_{nom}"] = pd_cumulee_ancree(
                    h, pd12[nom][lot.index], n, hp
                )
    return sortie


def actifs(arrete: pd.Period, octroi, m) -> pd.DataFrame:
    morceaux = []
    for a in ANNEES_TEST:
        if a > arrete.year:
            continue
        p = pd.read_parquet(INTER / "panneau" / f"millesime_{a}.parquet")
        p["period"] = pd.PeriodIndex(p["period"], freq="M")
        # Plus fort retard des derniers mois, arrêté compris : probation (D-050).
        fenetre = p[(p["period"] > arrete - PROBATION_STADE2_MOIS) & (p["period"] <= arrete)]
        probation = fenetre.groupby("loan_id")["retard"].max()
        q = p[(p["period"] == arrete) & p["defaut"].eq(0) & p["current_upb"].gt(0)].copy()
        q["retard_probation"] = q["loan_id"].map(probation).to_numpy()
        morceaux.append(q)
    p = survie.preparer(pd.concat(morceaux, ignore_index=True), octroi, m)
    p["remaining_months_to_maturity"] = (
        p["remaining_months_to_maturity"]
        .fillna(p["orig_loan_term"] - p["loan_age"])
        .clip(lower=1)
        .astype(int)
    )
    return p


def estimer_pertes_non_resolues(defauts: pd.DataFrame) -> pd.Series:
    """Perte estimée des défauts sans perte chiffrée, nulle pour les autres (D-044).

    Capital au défaut × sévérité moyenne, pondérée par le capital, des pertes
    chiffrées de la même année de défaut.
    """
    annee = defauts["mois_defaut"].dt.year
    chiffre = defauts[defauts["resolution"].eq("perte")]
    g = chiffre.groupby(chiffre["mois_defaut"].dt.year)
    severite = g["perte_montant"].sum() / g["crd_defaut"].sum()
    globale = chiffre["perte_montant"].sum() / chiffre["crd_defaut"].sum()
    s = annee.map(severite).fillna(globale)
    return (s * defauts["crd_defaut"]).where(defauts["resolution"].eq("non_resolu"), 0.0)


def pertes_constatees(prets: pd.DataFrame, defauts: pd.DataFrame, arrete, horizon_mois):
    """Pertes de chaque prêt actif : défaut après l'arrêté, dans l'horizon.

    Renvoie la perte chiffrée (0 pour une régularisation et, faute de montant,
    pour un défaut non résolu), l'indicatrice des défauts non résolus et leur
    perte estimée (D-044) : la perte chiffrée seule est un minorant.
    """
    d = defauts.set_index("loan_id").reindex(prets["loan_id"])
    dans = ((d["mois_defaut"] > arrete) & (d["mois_defaut"] <= arrete + horizon_mois)).to_numpy()
    chiffree = dans & d["resolution"].eq("perte").to_numpy()
    non_resolu = dans & d["resolution"].eq("non_resolu").to_numpy()
    perte = np.where(chiffree, d["perte_montant"].to_numpy(dtype=float), 0.0)
    estimee = np.where(non_resolu, d["perte_estimee"].to_numpy(dtype=float), 0.0)
    return perte, non_resolu, estimee


def calculer_arrete(
    arrete, octroi, m, pred, pd_octroi, defauts, modeles, hpi=None, crd_defauts=None
):
    """Lignes par modèle et stade ; avec ``hpi``, provision pondérée des scénarios (D-034)."""
    _, modele_survie, modele_lgd, modele_rembt = modeles
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
    lgd = lgd_actifs(modele_lgd, p, octroi, arrete, taux)
    n_max = int(restants.max())
    traj = trajectoire_figee(m, arrete, n_max)
    if hpi is not None:
        trajs = {s: sc.trajectoire(s, m, hpi, arrete, n_max) for s in PONDERATIONS_SCENARIOS}
        # LGD de chaque scénario : prix au bout de 12 mois de la trajectoire (D-047).
        mois_lgd = min(HORIZON_STADE1_MOIS, n_max) - 1
        lgd_scen = {
            s: lgd_actifs(
                modele_lgd, p, octroi, arrete, taux, float(t["hpi_relatif"].iloc[mois_lgd])
            )
            for s, t in trajs.items()
        }
        mois_octroi = pd.PeriodIndex(
            p[["loan_id"]].merge(octroi[["loan_id", "first_payment_date"]], on="loan_id")[
                "first_payment_date"
            ],
            freq="M",
        )
        cltv0 = sc.cltv_arrete(
            p, hpi.reindex(mois_octroi - 1).to_numpy(dtype=float), float(hpi.loc[arrete])
        )
        cltv0_etats = None
        if PRIX_ETATS is not None:
            cltv0_etats = sc.cltv_arrete_etats(p, mois_octroi - 1, arrete, PRIX_ETATS, cltv0)
    resultats = {nom: {"stade": [], "ecl": [], "ecl_maturite": [], "ratio": []} for nom in MODELES}
    for debut in range(0, len(p), TAILLE_LOT):
        sl = slice(debut, debut + TAILLE_LOT)
        h = moteur.projeter_hasards(modele_survie, p.iloc[sl], arrete, traj, n_max)
        hp = hasards_rembt(modele_rembt, p.iloc[sl], arrete, traj, n_max)
        if hpi is not None:
            # Écarts de logit au scénario central, appliqués après l'ancrage (D-036).
            # Le remboursement suit directement la trajectoire du scénario (D-040).
            ecarts, hp_scen = {}, {}
            for s, t in trajs.items():
                hp_s = (
                    hp
                    if s == "central"
                    else hasards_rembt(modele_rembt, p.iloc[sl], arrete, t, n_max)
                )
                hp_scen[s] = hp_scen[f"{s}_surcouche"] = hp_scen[f"{s}_surcouche_etats"] = hp_s
                ecart = 0.0
                if s != "central":
                    hs = moteur.projeter_hasards(modele_survie, p.iloc[sl], arrete, t, n_max)
                    ecart = moteur.logit(hs) - moteur.logit(h)
                u0 = float(m.loc[arrete, "chomage_var12"])
                ecarts[s] = ecart
                ecarts[f"{s}_surcouche"] = ecart + sc.surcouche(cltv0[sl], u0, t)
                if cltv0_etats is not None:
                    ecarts[f"{s}_surcouche_etats"] = ecart + sc.surcouche(cltv0_etats[sl], u0, t)
        for nom in MODELES:
            pd12 = p[f"pd_{nom}"].to_numpy()[sl]
            pd_vie = pd_cumulee_ancree(h, pd12, restants[sl], hp)
            st = staging.stade(
                en_defaut=np.zeros(len(pd12), dtype=bool),
                retard_mensualites=p["retard_probation"].to_numpy()[sl],
                pd_vie_arrete=pd_vie,
                mois_restants_arrete=restants[sl],
                pd_vie_octroi=p[f"pd_vie_octroi_{nom}"].to_numpy()[sl],
                mois_restants_octroi=p["duree_initiale"].to_numpy()[sl],
                seuil=SEUIL_RATIO_PD_STADE2,
            )
            args = (crd[sl], taux[sl], restants[sl], lgd[sl], pd12, h)
            resultats[nom]["stade"].append(st)
            # Rapport des PD à maturité annualisées (D-030), pour la grille de seuils.
            with np.errstate(divide="ignore", invalid="ignore"):
                resultats[nom]["ratio"].append(
                    staging.pd_annualisee(pd_vie, restants[sl])
                    / staging.pd_annualisee(
                        p[f"pd_vie_octroi_{nom}"].to_numpy()[sl],
                        p["duree_initiale"].to_numpy()[sl],
                    )
                )
            resultats[nom]["ecl"].append(moteur.provisions(st, *args, hasards_rembt=hp))
            if hpi is None:
                resultats[nom]["ecl_maturite"].append(
                    moteur.provisions(np.full(len(st), 2), *args, hasards_rembt=hp)
                )
            else:
                for cle, ecart in ecarts.items():
                    args_s = (*args[:3], lgd_scen[cle.split("_")[0]][sl], *args[4:])
                    resultats[nom].setdefault(f"ecl_{cle}", []).append(
                        moteur.provisions(
                            st, *args_s, ecart_logit=ecart, hasards_rembt=hp_scen[cle]
                        )
                    )

    # Stade 3 : défauts survenus avant l'arrêté et pas encore sortis.
    d3 = defauts[
        (defauts["mois_defaut"] <= arrete)
        & (defauts["mois_fin_defaut"].isna() | (defauts["mois_fin_defaut"] > arrete))
        & (defauts["annee_octroi"] <= arrete.year)
    ]
    # LGD actualisée sur le délai de résolution restant, au taux d'octroi (D-049).
    taux3 = (
        d3[["loan_id"]]
        .merge(octroi[["loan_id", "orig_interest_rate"]], on="loan_id", how="left")[
            "orig_interest_rate"
        ]
        .to_numpy(dtype=float)
        / 100
    )
    ecoules = arrete.ordinal - pd.PeriodIndex(d3["mois_defaut"], freq="M").astype("int64")
    lgd3 = modele_lgd.predire_actualisee(d3, taux3, ecoules) if len(d3) else np.zeros(0)
    perte3 = np.where(d3["resolution"].eq("perte"), d3["perte_montant"].astype(float), 0.0)
    # Exposition du stade 3 : capital à l'arrêté, à défaut capital au défaut (D-043).
    crd3 = d3["crd_defaut"].to_numpy(dtype=float)
    if crd_defauts is not None and len(d3):
        a = crd_defauts[crd_defauts["period"] == arrete].set_index("loan_id")["current_upb"]
        a = a.reindex(d3["loan_id"]).to_numpy(dtype=float)
        crd3 = np.where(np.isfinite(a) & (a > 0), a, crd3)

    if hpi is None:
        # Détail par prêt (hors Git) pour le bootstrap et la grille de seuils.
        prets = pd.DataFrame(
            {
                "loan_id": p["loan_id"],
                "crd": crd,
                "retard": p["retard_probation"].fillna(0).to_numpy(),
                **{
                    f"{c}_{nom}": np.concatenate(resultats[nom][c])
                    for nom in MODELES
                    for c in ("stade", "ecl", "ratio")
                },
            }
        )
        e3 = lgd3 * crd3
        stade3 = pd.DataFrame(
            {
                "loan_id": d3["loan_id"].to_numpy(),
                "crd": crd3,
                "retard": np.nan,
                **{f"stade_{nom}": 3 for nom in MODELES},
                **{f"ecl_{nom}": e3 for nom in MODELES},
                **{f"ratio_{nom}": np.nan for nom in MODELES},
            }
        )
        dossier = SORTIES / "trimestriel" / f"prets{suffixe_version()}"
        dossier.mkdir(parents=True, exist_ok=True)
        pd.concat([prets, stade3], ignore_index=True).to_parquet(
            dossier / f"{arrete}.parquet", index=False
        )

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
            for suffixe in ("", "_surcouche", "_surcouche_etats"):
                if f"ecl_central{suffixe}" not in par_scenario:
                    continue
                par_scenario[f"ecl_ponderee{suffixe}"] = sum(
                    w * par_scenario[f"ecl_{s}{suffixe}"] for s, w in PONDERATIONS_SCENARIOS.items()
                )
        horizon = np.where(st == 1, HORIZON_STADE1_MOIS, 10_000)
        perte = np.zeros(len(p))
        non_resolu = np.zeros(len(p), dtype=bool)
        estimee = np.zeros(len(p))
        for h_mois in np.unique(horizon):
            masque = horizon == h_mois
            pr, nr, es = pertes_constatees(p[masque], defauts, arrete, int(h_mois))
            perte[masque], non_resolu[masque], estimee[masque] = pr, nr, es
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
                    "pertes_non_resolus_estimees": estimee[masque].sum(),
                    **{c: v[masque].sum() for c, v in par_scenario.items()},
                }
            )
        lignes.append(
            {
                "arrete": str(arrete),
                "modele": nom,
                "stade": 3,
                "prets": len(d3),
                "encours": crd3.sum(),
                "ecl": float(np.sum(lgd3 * crd3)),
                "pertes_constatees": float(perte3.sum()),
                "defauts_non_resolus": int(d3["resolution"].eq("non_resolu").sum()),
                "pertes_non_resolus_estimees": float(d3["perte_estimee"].sum()),
                **{c: float(np.sum(lgd3 * crd3)) for c in par_scenario},
            }
        )
        # Par génération, à la fin de l'année d'octroi : tout à maturité (D-032).
        if hpi is None and arrete.month == 12 and arrete.year in ANNEES_TEST:
            g = (p["annee_octroi"] == arrete.year).to_numpy()
            perte_vie, nr_vie, es_vie = pertes_constatees(p[g], defauts, arrete, 10_000)
            details.append(
                {
                    "millesime": arrete.year,
                    "modele": nom,
                    "prets": int(g.sum()),
                    "encours": crd[g].sum(),
                    "ecl_maturite": np.concatenate(resultats[nom]["ecl_maturite"])[g].sum(),
                    "pertes_constatees": perte_vie.sum(),
                    "defauts_non_resolus": int(nr_vie.sum()),
                    "pertes_non_resolus_estimees": es_vie.sum(),
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
    charger_prix()
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
    defauts["perte_estimee"] = estimer_pertes_non_resolues(defauts)
    crd_defauts = pd.read_parquet(INTER / "crd_defauts_arretes.parquet")
    crd_defauts["period"] = pd.PeriodIndex(crd_defauts["period"], freq="M")

    sortie = SORTIES / "trimestriel"
    sortie.mkdir(parents=True, exist_ok=True)
    cache = sortie / f"pd_vie_octroi{suffixe_version()}.parquet"
    if cache.exists():
        pd_octroi = pd.read_parquet(cache)
    else:
        pd_octroi = pd_vie_octroi(octroi, m, modeles[0], modeles[1], modeles[3])
        pd_octroi.to_parquet(cache, index=False)
    print(f"PD à maturité à l'octroi : {len(pd_octroi):,} prêts ({time.time() - t0:.0f} s)")

    lignes, generations = [], []
    for arrete in ARRETES:
        fichier = (
            sortie / f"{nom_trajectoire}{suffixe_version()}" / f"{arrete}.pkl"
        )  # reprise après interruption
        if fichier.exists():
            lig, g = pd.read_pickle(fichier)
        else:
            lig, g = calculer_arrete(
                arrete, octroi, m, pred, pd_octroi, defauts, modeles, hpi, crd_defauts
            )
            fichier.parent.mkdir(exist_ok=True)
            pd.to_pickle((lig, g), fichier)
        lignes += lig
        generations += g
        t = pd.DataFrame(lig)
        cols = [c for c in ("ecl", "ecl_ponderee", "ecl_ponderee_surcouche") if c in t]
        resume = t.groupby("modele")[[*cols, "pertes_constatees"]].sum()
        print(f"{arrete} ({time.time() - t0:.0f} s)\n{resume.round(0).to_string()}")

    suffixe = f"_{nom_trajectoire}{suffixe_version()}"
    pd.DataFrame(lignes).to_csv(RESULTATS / f"trimestriel{suffixe}.csv", index=False)
    if generations:
        pd.DataFrame(generations).to_csv(RESULTATS / f"generations{suffixe}.csv", index=False)
    print(f"Terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectoire", default="figee", choices=["figee", "scenarios"])
    parser.add_argument("--sans-remboursement", action="store_true")
    arguments = parser.parse_args()
    REMBOURSEMENT = not arguments.sans_remboursement
    main(arguments.trajectoire)
