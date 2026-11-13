# LGD, EAD et moteur de calcul (semaine 4)

Protocole : `docs/decisions.md`, D-027 à D-029. Les chiffres viennent de
`pipeline/etape_05_lgd.py` et `pipeline/etape_06_moteur.py`.

## LGD en deux étapes

| | Défauts résolus | Régularisations | Sévérité des pertes | LGD réalisée (pondérée) | LGD prévue (pondérée) |
| --- | --- | --- | --- | --- | --- |
| Entraînement : défauts ≤ 2005, résolus ≤ 2006 | 2 926 | 71 % | 24 % | 4,9 % | 7,1 % |
| Test : défauts 2006-2010 | 10 610 | 42 % | 55 % | **29,5 %** | **7,6 %** |

| Année du défaut (test) | 2006 | 2007 | 2008 | 2009 | 2010 |
| --- | --- | --- | --- | --- | --- |
| LGD réalisée | 13,9 % | 32,0 % | 39,4 % | 29,2 % | 25,9 % |
| LGD prévue | 5,8 % | 7,0 % | 7,3 % | 7,6 % | 7,8 % |

À l'entraînement, 771 défauts sur 3 697 ne sont pas résolus fin 2006 et sont
exclus (D-027). Avec un suivi complet, ce qui fait entrer la crise, la LGD
réalisée des mêmes défauts monte à 7,9 % : la fenêtre d'un an joue peu.
L'essentiel de l'écart vient de la crise elle-même. Moins de prêts se
régularisent, et les biens saisis se revendent avec une perte deux fois
plus lourde, parce que les prix ont baissé. **La LGD est sous-estimée d'un
facteur 4, comme la PD l'était d'un facteur 3 à 6** : les deux erreurs se
multiplient dans la provision.

## Moteur

Le moteur calcule, pour chaque prêt, la somme sur la durée restante de
PD marginale × LGD × EAD × actualisation. Il est vérifié contre le calcul
prêt par prêt et contre le cas à la main de la semaine 1
(`tests/test_moteur.py`). Pour 86 074 prêts sur 30 ans, il tourne en
environ 100 secondes.

## Premier calcul : portefeuille de test au 31/12/2007

Prêts actifs des millésimes 2006 et 2007, macro figée à l'arrêté. Les stades
ne reposent encore que sur le retard (30 jours ou plus = stade 2) : le
critère de dégradation de la PD viendra en semaine 5.

| | Prêts | Encours | ECL logistique | ECL LightGBM | Écart |
| --- | --- | --- | --- | --- | --- |
| Stade 1 | 84 727 | 14,88 Md$ | 1,76 M$ | 3,72 M$ | +112 % |
| Stade 2 | 1 347 | 0,23 Md$ | 3,23 M$ | 4,47 M$ | +39 % |
| **Total** | **86 074** | **15,11 Md$** | **4,98 M$** | **8,19 M$** | **+64 %** |

À fin 2007, la provision LightGBM dépasse de 64 % la provision logistique.
Les deux restent minuscules : 0,03 % et 0,05 % de l'encours, avec une LGD
moyenne prévue de 6,6 %. Le backtest de la semaine 5 les comparera aux
pertes réellement constatées sur ce portefeuille.
