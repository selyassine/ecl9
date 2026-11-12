"""Définitions figées le 2026-11-12, miroir de ``docs/decisions.md``.

Ne modifier ces valeurs qu'en ajoutant une entrée datée dans le journal des
décisions. ``tests/test_definitions.py`` vérifie l'alignement des deux.
"""

from types import MappingProxyType

DATE_DECISIONS = "2026-11-12"

# D-001 Défaut
SEUIL_RETARD_DEFAUT = 3  # mensualités de retard, soit 90 jours ou plus
STATUT_SAISIE = "RA"  # bien acquis par saisie (REO acquisition)
STATUT_INCONNU = "XX"
CODES_SOLDE_NUL_DEFAUT = frozenset({"02", "03", "09", "15"})
CODE_REMBOURSEMENT = "01"

# D-003 Stade 2
SEUIL_RETARD_STADE2 = 1  # 30 jours ou plus
SEUIL_RATIO_PD_STADE2 = 2.0
GRILLE_SEUILS_STADE2 = (1.5, 2.0, 2.5, 3.0, 4.0)

# D-005 Horizon
HORIZON_STADE1_MOIS = 12

# D-010 Découpage temporel
ANNEES_ENTRAINEMENT = range(2000, 2006)  # 2000 à 2005 inclus
DERNIER_ARRETE_ENTRAINEMENT = "2005-12-31"
ANNEES_TEST = range(2006, 2009)  # 2006 à 2008 inclus

# D-011 Échantillon PD à 12 mois
MOIS_ARRETES = (3, 6, 9, 12)
FENETRE_PD_MOIS = 12

# D-012 Séries FRED
SERIES_FRED = ("UNRATE", "CSUSHPISA", "MORTGAGE30US", "DGS10")

# D-013 Scénarios
PONDERATIONS_SCENARIOS = MappingProxyType({"central": 0.50, "defavorable": 0.30, "favorable": 0.20})

# D-014 Validation
SEUILS_PSI = (0.10, 0.25)
TIRAGES_BOOTSTRAP = 1000
GRAINE = 20261112
