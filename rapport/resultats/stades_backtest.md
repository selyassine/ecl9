# Semaine 5 : stades, scénarios, backtest et double calcul

Portefeuille de test (millésimes 2006-2008), provision trimestrielle de mars
2006 à décembre 2010 (D-030 à D-036). Pipeline :
`pipeline/etape_07_trimestriel.py` (macro figée puis `--trajectoire scenarios`)
et `pipeline/etape_08_double_calcul_r.py`. Montants en millions de dollars.

## Résultat principal

| Arrêté | Encours (Md$) | Provision logistique | Provision LightGBM | Écart LightGBM | Pertes constatées | Part en stade 2 |
| --- | --- | --- | --- | --- | --- | --- |
| 31/12/2006 | 7,2 | 2,4 | 3,3 | + 34 % | 21,0 | 1,0 % |
| 31/12/2007 | 15,2 | 8,5 | 11,7 | + 38 % | 135,5 | 1,5 % |
| 31/12/2008 | 22,9 | 32,1 | 41,5 | + 29 % | 398,0 | 2,4 % |
| 31/12/2009 | 17,4 | 91,3 | 98,9 | + 8 % | 500,9 | 4,1 % |
| 31/12/2010 | 12,2 | 80,9 | 86,1 | + 6 % | 340,9 | 3,7 % |

Provision avec la macro figée à l'arrêté, stades 1 à 3 compris. Les pertes
constatées portent sur le même périmètre et le même horizon (D-032) : 12 mois
en stade 1, jusqu'à la fin des données en stade 2, résolution du défaut en
cours en stade 3. Détail par stade :
[`trimestriel_figee.csv`](trimestriel_figee.csv).

1. **La provision ne couvre qu'une petite part des pertes.** Au 31/12/2007,
   juste avant la crise, elle représente 6 % (logistique) à 9 % (LightGBM) des
   pertes constatées ensuite sur le même horizon. En stade 1 seul, c'est 2 à
   4 %.
2. **LightGBM provisionne davantage avant la crise, puis l'écart se referme.**
   + 34 à + 38 % fin 2006 et fin 2007, + 6 à + 8 % en 2009-2010, quand les
   défauts constatés (stade 3, même LGD pour les deux modèles) dominent la
   provision.
3. **La provision réagit, elle n'anticipe pas.** Elle est multipliée par 8 à 11
   entre fin 2007 et fin 2009, mais surtout par le stade 3 : 3,5 M$ fin 2007,
   74,7 M$ fin 2009, une fois les défauts survenus.

## Le critère de dégradation ne classe aucun prêt en stade 2

Le stade 2 vient presque uniquement du retard de paiement. Au 31/12/2008, sur
un échantillon de 20 000 prêts actifs, aucun prêt sans retard n'atteint un
doublement de la PD à maturité annualisée depuis l'octroi (rapport médian
1,2 ; 99e centile 1,35 pour la logistique, 1,83 pour LightGBM). Les rares
prêts au-dessus du seuil sont déjà en retard. Les stades sont donc presque
identiques pour les deux modèles.

La raison : la PD à maturité est dominée par les hasards de survie au-delà
de 12 mois, et le modèle de survie n'a appris aucune sensibilité au chômage
ni aux prix (D-026). Seule la PD à 12 mois, ancrée sur les 12 premiers mois,
bouge avec l'état du prêt. La grille de seuils (1,5 à 4) sera publiée en
semaine 6.

## Scénarios et surcouche (D-034, D-036)

| Arrêté | Logistique : pondérée | avec surcouche | LightGBM : pondérée | avec surcouche |
| --- | --- | --- | --- | --- |
| 31/12/2006 | + 3,1 % | + 12,6 % | + 3,1 % | + 12,2 % |
| 31/12/2007 | + 2,0 % | + 9,4 % | + 2,1 % | + 9,0 % |
| 31/12/2008 | + 1,1 % | + 2,6 % | + 1,3 % | + 2,7 % |
| 31/12/2009 | + 0,5 % | - 0,3 % | + 0,6 % | - 0,6 % |
| 31/12/2010 | + 0,4 % | + 2,6 % | + 0,5 % | + 3,2 % |

Écart à la provision en macro figée. Le scénario défavorable seul, avec la
surcouche, ajoute 27 à 28 % au 31/12/2007. Pondérés 50/30/20, les scénarios
ne changent la provision que de quelques pourcents : ils ne comblent pas un
écart de 1 à 10 avec les pertes. Détail par scénario :
[`trimestriel_scenarios.csv`](trimestriel_scenarios.csv).

Un premier calcul ancrait chaque scénario sur la PD à 12 mois, ce qui
annulait leur effet en stade 1. Il est conservé dans
[`v1_trimestriel_scenarios.csv`](v1_trimestriel_scenarios.csv) et corrigé
par D-036.

## Backtest par génération

| Millésime | Encours fin d'année (Md$) | Perte attendue à maturité, logistique | LightGBM | Pertes constatées jusqu'en 2026 |
| --- | --- | --- | --- | --- |
| 2006 | 7,2 | 33,5 | 34,3 | 219,7 |
| 2007 | 7,6 | 35,4 | 36,6 | 226,2 |
| 2008 | 8,6 | 39,2 | 40,7 | 95,8 |

Tous les prêts traités à maturité, macro figée à la fin de l'année d'octroi
([`generations_figee.csv`](generations_figee.csv)). La perte attendue couvre
15 à 16 % des pertes constatées pour 2006 et 2007, 41 à 42 % pour 2008, octroyé
après le début de la baisse des prix. Sur la durée de vie, les deux modèles
sont presque identiques (+ 2 à + 4 %), puisque seule la première année
diffère.

## Double calcul R (D-033, D-035)

50 prêts réels du portefeuille au 31/12/2007 (25 en stade 1, 25 en stade 2)
recalculés par `tests/r/double_calcul.R` : écart relatif maximal de 1e-12
avec le moteur Python ([`double_calcul_r_2007-12.csv`](double_calcul_r_2007-12.csv)).
Le contrôle sur 50 prêts simulés, stade 3 compris, tourne en intégration
continue.
