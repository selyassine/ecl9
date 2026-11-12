# Double calcul en R (semaine 5)

Script R indépendant qui recalcule la provision de 50 prêts tirés au hasard à
partir des mêmes entrées (PD marginales, LGD, EAD, taux contractuel) et vérifie
l'égalité avec le moteur Python à 1e-8 près. Il ne réutilise aucun code Python :
seule la formule de `docs/decisions.md` est partagée.
