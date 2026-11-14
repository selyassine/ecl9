# Pipeline

Étapes numérotées, chacune lit les sorties des précédentes. `make pipeline`
enchaîne tout ; les sorties intermédiaires vont dans `sorties/` (hors Git) et
les résultats publiés dans `rapport/resultats/`.

| Étape | Script | Semaine |
| --- | --- | --- |
| 0 | `ecl9-telecharger` : téléchargement et empreintes | 1 |
| 1 | `etape_01_panneau.py` : panneau prêt-mois, échantillon PD 12 mois | 1 |
| 2 | `etape_02_exploration.py` : taux de défaut par cohorte et par année | 1 |
| 3 | `etape_03_pd12.py` : PD à 12 mois, logistique puis LightGBM | 2 |
| 4 | `etape_04_survie.py` : PD à maturité par survie discrète | 3 |
| 4 bis | `etape_04b_remboursement.py` : remboursement anticipé (D-040) | après la v1 |
| 5 | `etape_05_lgd.py` : défauts résolus et LGD | 4 |
| 6 | `etape_06_moteur.py` : provision à une date d'arrêté | 4 |
| 7 | `etape_07_trimestriel.py` : stades, provision 2006-2010, backtest, scénarios | 5 |
| 8 | `etape_08_double_calcul_r.py` : double calcul R sur 50 prêts réels | 5 |
| 9 | `etape_09_sensibilites.py` : bootstrap de l'écart, grilles de sensibilité | 6 |
| 10 | `etape_10_bootstrap_modeles.py` : intervalle avec modèles réestimés (D-042) | après la v1 |
