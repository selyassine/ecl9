"""Probabilités de défaut.

Semaine 2 : PD à 12 mois, régression logistique de référence puis LightGBM
avec exactement les mêmes variables, validées hors période (2006-2008).

Semaine 3 : PD à maturité par un modèle de survie en temps discret sur le
panneau prêt-mois (âge du prêt, variables à l'octroi, macro), c'est-à-dire
une table de mortalité appliquée au crédit.
"""
