# PD à maturité par survie discrète (semaine 3)

Protocole : `docs/decisions.md`, D-023 à D-025. Les chiffres viennent de
`pipeline/etape_04_survie.py`, et les tableaux complets sont dans les CSV
`survie_*` de ce dossier.

## Table de mortalité du crédit (entraînement 2000-2005)

| Âge (mois) | Hasard mensuel observé | Ajusté | Annualisé observé |
| --- | --- | --- | --- |
| 0-6 | 0,019 % | 0,023 % | 0,23 % |
| 7-12 | 0,049 % | 0,045 % | 0,59 % |
| 13-24 | 0,070 % | 0,063 % | 0,84 % |
| 25-36 | 0,105 % | 0,094 % | 1,25 % |
| 37-48 | 0,148 % | 0,139 % | 1,76 % |
| 49-60 | 0,209 % | 0,222 % | 2,48 % |
| 61+ | 0,294 % | 0,307 % | 3,47 % |

Le hasard croît régulièrement avec l'âge sur les six premières années. Le
modèle le reproduit, avec 0,95 défaut attendu pour 1 défaut observé à
l'entraînement et une AUC de 0,872 au niveau prêt-mois.

## Validation hors période (millésimes 2006-2008, mois 2006-2010)

| Année | Défauts observés | Attendus, macro réalisée | A/O | Attendus, macro figée à déc. 2005 | A/O |
| --- | --- | --- | --- | --- | --- |
| 2006 | 41 | 45 | 1,11 | 80 | 1,95 |
| 2007 | 477 | 131 | 0,28 | 360 | 0,75 |
| 2008 | 2 024 | 214 | 0,11 | 689 | 0,34 |
| 2009 | 5 336 | 636 | 0,12 | 837 | 0,16 |
| 2010 | 4 244 | 893 | 0,21 | 717 | 0,17 |
| **Total** | **12 122** | **1 919** | **0,16** | **2 683** | **0,22** |

## Lecture

1. **La macro réalisée fait moins bien que la macro figée.** Même en
   connaissant à l'avance le chômage, les prix immobiliers et les taux de
   2006-2010, le modèle prévoit moins de défauts qu'en gelant la macro à son
   niveau de 2005.
2. **La cause est le signe du coefficient des prix immobiliers.** Sur
   2000-2005, la variation de Case-Shiller sur 12 mois a un coefficient
   positif (+0,16 en variable centrée-réduite) : plus les prix montaient,
   plus les prêts faisaient défaut. C'est une corrélation de période. La
   hausse des prix accompagne le vieillissement des prêts et la montée des
   défauts sur 2000-2005, sans lien causal. Appliqué à la baisse des prix
   de 2007-2009, ce coefficient fait baisser le hasard prévu.
3. **Une période calme n'identifie pas la sensibilité à la crise.** Sur
   2000-2005, le chômage varie entre 4 et 6 % et les prix ne baissent jamais.
   Aucune méthode d'estimation, logistique ou non, ne peut en tirer la
   réponse des défauts à un choc qu'elle n'a pas vu.

Cela touche directement la semaine 5. Les scénarios déplacent la PD par la
macro : avec ces coefficients, un scénario défavorable sur les prix
**baisserait** la provision. Le traitement retenu sera consigné dans le
journal des décisions avant la construction des scénarios.

## Après contrainte de signe (D-026)

Les variables retirées, dans l'ordre, sont la variation des prix (+0,16), puis
la variation du chômage et le chômage, devenus négatifs une fois les prix
retirés. Il reste le taux à 10 ans (+0,04) et l'écart entre le taux du prêt
et le taux du marché (+0,29).

| Modèle | A/O entraînement | A/O test, macro réalisée | A/O test, macro figée | AUC test |
| --- | --- | --- | --- | --- |
| Libre | 0,95 | 0,16 | 0,22 | 0,794 |
| Contraint (retenu) | 1,01 | **0,27** | 0,21 | 0,784 |

| Année | Observés | Attendus contraint, macro réalisée | A/O |
| --- | --- | --- | --- |
| 2006 | 41 | 67 | 1,64 |
| 2007 | 477 | 327 | 0,69 |
| 2008 | 2 024 | 670 | 0,33 |
| 2009 | 5 336 | 1 124 | 0,21 |
| 2010 | 4 244 | 1 094 | 0,26 |

Le modèle contraint va désormais dans le bon sens : la macro réalisée
fait mieux que la macro figée, avec 27 % des défauts prévus contre 21 %. Le
gain vient entièrement de l'écart de taux. En 2008-2010, les taux du marché
baissent, mais les emprunteurs fragiles ne peuvent pas refinancer et gardent
un taux supérieur au marché. Les données de 2000-2005 ne donnent **aucune
sensibilité positive au chômage ni aux prix immobiliers**. Les scénarios de
la semaine 5 ne pourront donc pas agir sur la PD par ces deux variables, sauf
à introduire une sensibilité extérieure aux données. Ce choix sera alors
consigné à part.
