"""Lecture des fichiers Freddie Mac et construction du panneau prêt-mois.

Les noms de colonnes suivent le guide utilisateur du *Single-Family Loan-Level
Dataset*, version de juillet 2026 : 31 champs à l'octroi, 35 au suivi mensuel
(fichiers séparés par « | », sans en-tête). Le nombre de colonnes a
augmenté au fil des versions : la lecture nomme les colonnes présentes dans
l'ordre et signale un fichier plus large que le schéma connu.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ecl9.definitions import (
    CODES_SOLDE_NUL_DEFAUT,
    FENETRE_PD_MOIS,
    MOIS_ARRETES,
    SEUIL_RETARD_DEFAUT,
    STATUT_INCONNU,
    STATUT_SAISIE,
)

COLONNES_OCTROI = (
    "credit_score",
    "first_payment_date",
    "first_time_homebuyer",
    "maturity_date",
    "msa",
    "mi_pct",
    "num_units",
    "occupancy_status",
    "orig_cltv",
    "orig_dti",
    "orig_upb",
    "orig_ltv",
    "orig_interest_rate",
    "channel",
    "ppm_flag",
    "amortization_type",
    "property_state",
    "property_type",
    "postal_code",
    "loan_id",
    "loan_purpose",
    "orig_loan_term",
    "num_borrowers",
    "seller_name",
    "super_conforming",
    "pre_harp_loan_id",
    "program_indicator",
    "harp_indicator",
    "property_valuation_method",
    "interest_only",
    "vantage_score",
)

COLONNES_SUIVI = (
    "loan_id",
    "period",
    "current_upb",
    "delinquency_status",
    "loan_age",
    "remaining_months_to_maturity",
    "defect_settlement_date",
    "modification_flag",
    "zero_balance_code",
    "zero_balance_date",
    "current_interest_rate",
    "current_non_interest_bearing_upb",
    "ddlpi",
    "mi_recoveries",
    "net_sale_proceeds",
    "non_mi_recoveries",
    "expenses",
    "legal_costs",
    "maintenance_costs",
    "taxes_insurance",
    "misc_expenses",
    "actual_loss",
    "modification_cost",
    "step_modification",
    "payment_deferral",
    "eltv",
    "zero_balance_removal_upb",
    "delinquent_accrued_interest",
    "disaster_delinquency",
    "borrower_assistance_status",
    "current_month_modification_cost",
    "interest_bearing_upb",
    "mi_cancellation",
    "servicer_name",
    "bankruptcy_cramdown_costs",
)

# Codes sentinelles convertis en valeurs manquantes (D-015).
SENTINELLES_OCTROI = {
    "credit_score": 9999,
    "vantage_score": 9999,
    "mi_pct": 999,
    "orig_cltv": 999,
    "orig_dti": 999,
    "orig_ltv": 999,
    "num_units": 99,
    "num_borrowers": 99,
}
CODES_INCONNUS_OCTROI = {
    "first_time_homebuyer": "9",
    "occupancy_status": "9",
    "channel": "9",
    "property_type": "99",
    "loan_purpose": "9",
}

# Colonnes lues comme texte : identifiants, codes à zéros significatifs, dates.
_TEXTE = {
    "loan_id",
    "pre_harp_loan_id",
    "postal_code",
    "msa",
    "zero_balance_code",
    "delinquency_status",
    "first_payment_date",
    "maturity_date",
    "period",
    "zero_balance_date",
    "defect_settlement_date",
    "ddlpi",
}


COLONNES_SUIVI_UTILES = (
    "loan_id",
    "period",
    "current_upb",
    "delinquency_status",
    "loan_age",
    "remaining_months_to_maturity",
    "modification_flag",
    "zero_balance_code",
    "zero_balance_date",
    "current_interest_rate",
    "net_sale_proceeds",
    "expenses",
    "actual_loss",
    "eltv",
    "zero_balance_removal_upb",
)


def _largeur(chemin: Path) -> int:
    with open(chemin, encoding="latin-1") as f:
        return f.readline().rstrip("\n").count("|") + 1


def _lire(
    chemin: Path, colonnes: tuple[str, ...], utiles: tuple[str, ...] | None = None
) -> pd.DataFrame:
    largeur = _largeur(chemin)
    if largeur > len(colonnes):
        raise ValueError(
            f"{Path(chemin).name} : {largeur} colonnes, schéma connu de "
            f"{len(colonnes)}. Mettre à jour le schéma d'après le guide Freddie Mac."
        )
    noms = list(colonnes[:largeur])
    retenues = [n for n in noms if utiles is None or n in utiles]
    brut = pd.read_csv(
        chemin,
        sep="|",
        header=None,
        names=noms,
        usecols=retenues,
        dtype=str,
        keep_default_na=False,
        encoding="latin-1",
    )
    brut = brut.replace({"": pd.NA})
    for col in brut.columns:
        if col not in _TEXTE and not col.endswith(("_name", "_flag")):
            converti = pd.to_numeric(brut[col], errors="coerce")
            if converti.notna().sum() >= brut[col].notna().sum() * 0.99:
                brut[col] = converti
    return brut


def _mois(serie: pd.Series) -> pd.Series:
    """Date AAAAMM en période mensuelle pandas."""
    return pd.to_datetime(serie.astype("string"), format="%Y%m").dt.to_period("M")


def lire_octroi(chemin: Path) -> pd.DataFrame:
    """Caractéristiques à l'octroi, une ligne par prêt."""
    df = _lire(chemin, COLONNES_OCTROI)
    for col, code in SENTINELLES_OCTROI.items():
        if col in df:
            df[col] = df[col].mask(df[col] == code)
    for col, code in CODES_INCONNUS_OCTROI.items():
        if col in df:
            df[col] = df[col].mask(df[col].astype("string") == code)
    df["first_payment_date"] = _mois(df["first_payment_date"])
    df["cohorte"] = df["first_payment_date"].dt.year
    return df


def lire_suivi(
    chemin: Path, utiles: tuple[str, ...] | None = COLONNES_SUIVI_UTILES
) -> pd.DataFrame:
    """Suivi mensuel, une ligne par prêt et par mois.

    Par défaut, seules les colonnes utiles au modèle sont chargées (le fichier
    complet d'une année dépasse 400 Mo) ; ``utiles=None`` charge tout.
    """
    df = _lire(chemin, COLONNES_SUIVI, utiles)
    df["period"] = _mois(df["period"])
    return df


def statut_retard(statut: pd.Series) -> pd.Series:
    """Nombre de mensualités de retard ; manquant pour ``RA`` et ``XX``."""
    s = statut.astype("string").str.strip()
    return pd.to_numeric(s.mask(s.isin([STATUT_SAISIE, STATUT_INCONNU])), errors="coerce")


def marquer_defaut(suivi: pd.DataFrame) -> pd.Series:
    """Vrai pour chaque ligne prêt-mois qui remplit la définition D-001."""
    statut = suivi["delinquency_status"].astype("string").str.strip()
    retard = statut_retard(statut)
    code = suivi["zero_balance_code"].astype("string").str.strip().str.zfill(2)
    return (
        (retard >= SEUIL_RETARD_DEFAUT).fillna(False)
        | (statut == STATUT_SAISIE).fillna(False)
        | code.isin(CODES_SOLDE_NUL_DEFAUT).fillna(False)
    ).astype(bool)


def construire_panneau(suivi: pd.DataFrame) -> pd.DataFrame:
    """Panneau prêt-mois pour la survie : chaque prêt s'arrête à son premier défaut.

    Colonnes ajoutées :
    ``retard`` (mensualités), ``defaut`` (événement ce mois-ci, 0/1) et
    ``sortie`` (dernier mois observé du prêt dans le panneau, 0/1).
    """
    df = suivi.sort_values(["loan_id", "period"]).reset_index(drop=True)
    df["retard"] = statut_retard(df["delinquency_status"])
    evenement = marquer_defaut(df)
    deja_en_defaut = evenement.groupby(df["loan_id"]).cumsum() - evenement.astype(int)
    df = df[deja_en_defaut.eq(0)].copy()
    df["defaut"] = evenement[df.index].astype(int)
    df["sortie"] = (~df["loan_id"].duplicated(keep="last")).astype(int)
    return df.reset_index(drop=True)


def echantillon_pd12(
    panneau: pd.DataFrame, fenetre: int = FENETRE_PD_MOIS, mois_arretes=MOIS_ARRETES
) -> pd.DataFrame:
    """Observations trimestrielles et cible « défaut dans les 12 mois » (D-011).

    Une ligne par prêt et par arrêté de fin de trimestre où il est actif et
    non en défaut. Un prêt soldé sans défaut dans la fenêtre vaut 0. Les
    arrêtés dont la fenêtre dépasse la dernière date observée du jeu de
    données sont tous retirés, faute de recul suffisant.
    """
    rang = panneau["period"].map(lambda p: p.ordinal)
    mois_defaut = rang.where(panneau["defaut"].eq(1)).groupby(panneau["loan_id"]).transform("max")
    dernier_mois_jeu = rang.max()

    arretes = panneau[
        panneau["period"].dt.month.isin(mois_arretes) & panneau["defaut"].eq(0)
    ].copy()
    r = rang[arretes.index]
    d = mois_defaut[arretes.index]
    arretes["cible_defaut_12m"] = ((d > r) & (d <= r + fenetre)).astype(int)
    # Pas d'exception pour les défauts observés : garder un arrêté incomplet
    # seulement s'il a fait défaut biaiserait la cible vers 1.
    assez_de_recul = r + fenetre <= dernier_mois_jeu
    return arretes[assez_de_recul].reset_index(drop=True)


CODES_REGULARISATION = frozenset({"01", "16"})


def resolutions_defaut(suivi: pd.DataFrame, fin_observation: pd.Period | None = None):
    """Premier défaut de chaque prêt et sa résolution (D-027).

    Renvoie une ligne par prêt en défaut : ``mois_defaut``, ``age_defaut``,
    ``crd_defaut`` (capital au défaut, à défaut le capital retiré),
    ``resolution`` (``perte``, ``regularisation`` ou ``non_resolu``),
    ``mois_resolution``, ``mois_fin_defaut`` (sortie définitive ou premier
    retour sous 3 mensualités de retard), ``severite`` (perte / capital retiré, bornée à
    [0, 1]) et ``perte_montant`` (perte réalisée bornée au capital retiré),
    ces deux dernières pour les pertes seulement. Seuls les mois jusqu'à
    ``fin_observation`` sont pris en compte.
    """
    s = suivi.sort_values(["loan_id", "period"]).reset_index(drop=True)
    if fin_observation is not None:
        s = s[s["period"] <= fin_observation]
    defaut = marquer_defaut(s)
    premier = s[defaut].groupby("loan_id", sort=False).head(1).set_index("loan_id")
    apres = s[s["loan_id"].isin(premier.index)]
    apres = apres[apres["period"] >= apres["loan_id"].map(premier["period"])]
    dernier = apres.groupby("loan_id").tail(1).set_index("loan_id")
    # Premier mois après le défaut où le retard repasse sous 3 mensualités.
    retard_apres = statut_retard(apres["delinquency_status"])
    sous_seuil = apres[(retard_apres < SEUIL_RETARD_DEFAUT).fillna(False)]
    sous_seuil = sous_seuil[sous_seuil["period"] > sous_seuil["loan_id"].map(premier["period"])]
    premier_retour = sous_seuil.groupby("loan_id")["period"].min()

    code = dernier["zero_balance_code"].astype("string").str.zfill(2)
    statut = dernier["delinquency_status"].astype("string").str.strip()
    retard = statut_retard(statut)
    perte = code.isin(CODES_SOLDE_NUL_DEFAUT).fillna(False)
    regul = code.isin(CODES_REGULARISATION).fillna(False) | (
        code.isna() & (retard < SEUIL_RETARD_DEFAUT).fillna(False)
    )
    resolution = pd.Series("non_resolu", index=dernier.index, dtype="string")
    resolution[regul] = "regularisation"
    resolution[perte] = "perte"

    retire = dernier["zero_balance_removal_upb"]
    severite = (dernier["actual_loss"] / retire).clip(0, 1).where(perte & retire.gt(0))
    resolution[perte & severite.isna()] = "non_resolu"  # perte non chiffrée

    crd = premier["current_upb"].where(premier["current_upb"] > 0, retire.reindex(premier.index))
    return pd.DataFrame(
        {
            "mois_defaut": premier["period"],
            "age_defaut": premier["loan_age"],
            "crd_defaut": crd,
            "resolution": resolution.reindex(premier.index),
            "mois_resolution": dernier["period"].where(perte | code.notna()),
            # Fin du stade 3 : sortie définitive, ou retour sous 90 jours de retard.
            "mois_fin_defaut": pd.concat(
                [dernier["period"].where(code.notna()), premier_retour.reindex(dernier.index)],
                axis=1,
            ).min(axis=1),
            "severite": severite.reindex(premier.index),
            "perte_montant": (
                dernier["actual_loss"].clip(lower=0).clip(upper=retire).where(perte)
            ).reindex(premier.index),
        }
    ).reset_index()
