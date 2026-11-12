# Pipeline

Étapes numérotées, chacune lit les sorties de la précédente. `make exploration`
enchaîne tout ce qui existe à ce stade.

| Étape | Script | Semaine |
| --- | --- | --- |
| 0 | `ecl9-telecharger` (téléchargement et empreintes) | 1 |
| 1 | `etape_01_panneau.py` : panneau prêt-mois, échantillon PD 12 mois | 1 |
| 2 | `etape_02_exploration.py` : taux de défaut par cohorte et par année | 1 |
| 3 | PD à 12 mois, logistique puis LightGBM | 2 |
| 4 | PD à maturité par survie discrète | 3 |
| 5 | LGD, EAD et moteur de calcul | 4 |
| 6 | Stades, scénarios, backtest, double calcul R | 5 |
| 7 | Bootstrap et chiffres de la note | 6 |
