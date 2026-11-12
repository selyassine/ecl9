"""Perte en cas de défaut (semaine 4).

Modèle en deux étapes, calibré sur les pertes réalisées à la liquidation :

1. probabilité de régularisation (le prêt redevient sain sans perte) ;
2. sévérité de la perte quand il n'y a pas régularisation.

LGD = (1 - P(régularisation)) × sévérité.
"""
