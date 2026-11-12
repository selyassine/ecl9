"""Lecture des fichiers Freddie Mac et construction du panneau prêt-mois.

Les noms de colonnes suivent le guide utilisateur du *Single-Family Loan-Level
Dataset* (fichiers séparés par « | », sans en-tête). Le nombre de colonnes a
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
    "servicer_name",
    "super_conforming",
    "pre_harp_loan_id",
    "program_indicator",
    "harp_indicator",
    "property_valuation_method",
    "interest_only",
    "mi_cancellation",
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
)

# Codes sentinelles convertis en valeurs manquantes (D-015).
SENTINELLES_OCTROI = {
    "credit_score": 9999,
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


def _lire(chemin: Path, colonnes: tuple[str, ...]) -> pd.DataFrame:
    brut = pd.read_csv(chemin, sep="|", header=None, dtype=str, keep_default_na=False)
    if brut.shape[1] > len(colonnes):
        raise ValueError(
            f"{Path(chemin).name} : {brut.shape[1]} colonnes, schéma connu de "
            f"{len(colonnes)}. Mettre à jour le schéma d'après le guide Freddie Mac."
        )
    brut.columns = list(colonnes[: brut.shape[1]])
    brut = brut.replace({"": pd.NA})
    for col in brut.columns:
        if col not in _TEXTE and not col.endswith(("_name", "_flag")):
            converti = pd.to_numeric(brut[col], errors="coerce")
            if converti.notna().sum() >= brut[col].notna().sum() * 0.99:
                brut[col] = converti
    return brut


def _mois(serie: pd.Series) -> pd.Series:
    """Date AAAAMM en période mensuelle pandas."""
    return pd.PeriodIndex(serie.astype("string"), freq="M").to_series(index=serie.index)


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


def lire_suivi(chemin: Path) -> pd.DataFrame:
    """Suivi mensuel, une ligne par prêt et par mois."""
    df = _lire(chemin, COLONNES_SUIVI)
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
    données sont retirés, faute de recul suffisant.
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
    assez_de_recul = (r + fenetre <= dernier_mois_jeu) | arretes["cible_defaut_12m"].eq(1)
    return arretes[assez_de_recul].reset_index(drop=True)
