# ecl9

[![CI](https://github.com/selyassine/ecl9/actions/workflows/ci.yml/badge.svg)](https://github.com/selyassine/ecl9/actions/workflows/ci.yml)
![Licence MIT](https://img.shields.io/badge/licence-MIT-blue)

> Remplacer la régression logistique par du machine learning change-t-il
> vraiment la provision IFRS 9, et dans quel sens en période de crise ?

> **In English.** Does replacing logistic regression with machine learning
> actually change the IFRS 9 expected credit loss, and in which direction during
> a crisis? This Python package builds a loan-level ECL engine on the Freddie
> Mac single-family sample (US mortgages): 12-month PD (logistic regression vs
> LightGBM on the same features), lifetime PD from a discrete-time survival
> model with macro drivers from FRED, two-stage LGD, contractual EAD, three
> weighted forward-looking scenarios and stage allocation. Models are trained
> on loans originated in 2000-2005 with observation dates up to end-2005, and
> tested on the 2006-2008 vintages so that they cross the crisis without having
> seen it. All definitions were fixed and dated in
> [`docs/decisions.md`](docs/decisions.md) before any model was fitted.
> **Answer:** yes, but the effect is second-order. With everything else equal
> (survival, prepayment, LGD, staging rule), LightGBM raises the allowance by
> 30-51% between end-2006 and end-2008 (+49% at 31/12/2007; 95% interval +27%
> to +80% when both models are re-estimated on bootstrap samples), and by
> 7-10% in 2009-2010. The size of the gap depends on the training window: it
> falls to +25% when the 2005 observation dates, whose labels mature in 2006,
> are dropped. Yet both models, trained before the crisis, cover only 9-13% of
> the losses later booked over the same horizon at end-2007 (7-10% once
> defaults with no published loss are estimated). The LGD model matters more
> than the PD algorithm: revaluing loan-to-value with state house prices
> roughly doubles the allowance. Report and documentation are in
> French.

**Note de provisionnement : <https://selyassine.github.io/ecl9/>**

**Réponse : oui, LightGBM change la provision, toujours à la hausse avant la
crise, mais beaucoup moins que l'erreur commune aux deux modèles.** Avec les
mêmes variables, la même survie, le même remboursement anticipé, la même LGD
et la même règle de stades, LightGBM provisionne 30 à 51 % de plus que la
logistique entre fin 2006 et fin 2008. Au 31/12/2007, c'est 19,0 contre
12,7 M$, soit + 49 % ; l'intervalle à 95 % est de + 45 à + 53 % sur la
composition du portefeuille, et de + 27 à + 80 % en réestimant aussi les deux
modèles (LightGBM au-dessus dans 100 tirages sur 100). L'écart retombe à 7 à
10 % en 2009-2010, quand les défauts déjà survenus dominent. L'ampleur dépend
de la fenêtre d'entraînement : sans les arrêtés de 2005, dont les étiquettes
ne sont connues que fin 2006, l'écart tombe à + 25 % au 31/12/2007
([`coupure_stricte.csv`](rapport/resultats/coupure_stricte.csv), D-046). Mais
entraînés sur 2000-2005, les deux modèles ne voient pas venir la crise : au
31/12/2007, leurs provisions ne couvrent que 9 à 13 % des pertes chiffrées
ensuite sur le même horizon, et 7 à 10 % en estimant les défauts sortis sans
perte publiée (D-044).

- PD à 12 mois : LightGBM classe un peu mieux (AUC 0,815 contre 0,789 sur
  2006-2010) et sous-estime moins les défauts (31 % des défauts prévus contre
  17 %) ([`pd12.md`](rapport/resultats/pd12.md)).
- Survie : aucune sensibilité au chômage ni aux prix n'est identifiable sur
  2000-2005 ([`survie.md`](rapport/resultats/survie.md)).
- LGD : c'est elle qui fixe le niveau de la provision. Avec la LTV d'octroi,
  elle prévoyait 7,6 % pour 29,5 % réalisés sur la crise ; avec le ratio
  prêt / valeur réévalué aux prix de l'État du bien, toujours estimée avant
  2006, elle prévoit 21,9 %, et la provision est multipliée par 1,6 à 3,4
  ([`lgd_specifications.csv`](rapport/resultats/lgd_specifications.csv), D-047).
- Remboursement anticipé : appris sur le boom de refinancement de 2001-2003,
  le modèle prévoit sur 2006-2010 trois fois plus de remboursements qu'il n'y
  en a eu ; il baisse la provision, surtout sur la durée de vie
  ([`remboursement_mesures.csv`](rapport/resultats/remboursement_mesures.csv)).
- Stade 2 : jusqu'à fin 2008, le critère de dégradation (PD à maturité
  doublée) n'ajoute rien au retard de paiement ; en 2009-2010, la baisse des
  taux le fait se déclencher par intermittence, sans dégradation de crédit.
- Scénarios : ils agissent sur la PD par les taux et sur la LGD par les prix.
  Pondérés 50/30/20, ils changent la provision de - 29 % (début 2006, prix en
  hausse) à + 18 % (2008) ; de - 31 % à + 26 % avec une sensibilité chômage
  et prix tirée de la littérature, publiée à part.

La version 1, sans remboursement anticipé, reste publiée
([`stades_backtest.md`](rapport/resultats/stades_backtest.md), fichiers
`*_sans_remboursement.csv`) : la conclusion est la même.

## État d'avancement

| Semaine | Travail | État |
| --- | --- | --- |
| 1 | Téléchargement, panneau prêt-mois, définitions figées, analyse exploratoire | fait |
| 2 | PD à 12 mois : logistique puis LightGBM, validation hors période | [fait](rapport/resultats/pd12.md) |
| 3 | PD à maturité par survie, variables macro | [fait](rapport/resultats/survie.md) |
| 4 | LGD, EAD, moteur de calcul et tests à la main | [fait](rapport/resultats/lgd_moteur.md) |
| 5 | Stades, scénarios, backtest sur la crise, double calcul R | [fait](rapport/resultats/stades_backtest.md) |
| 6 | Bootstrap, note Quarto, README, mise en ligne | [fait](https://selyassine.github.io/ecl9/) |

## Méthode

Pour chaque prêt, la perte attendue est la somme, sur les mois de l'horizon,
de la PD marginale × LGD × EAD × facteur d'actualisation, puis la moyenne
pondérée de trois scénarios macroéconomiques :

```
ECL = Σ_s w_s Σ_{t=1..H} S_s(t-1) h_s(t) × LGD × EAD(t) × (1 + r/12)^(-t)
```

| Brique | Choix |
| --- | --- |
| Défaut (stade 3) | 90 jours de retard ou plus, ou saisie du bien |
| Stade 2 | 30 jours de retard dans les 3 derniers mois, ou PD à maturité annualisée doublée depuis l'octroi |
| Horizon | 12 mois en stade 1, durée de vie restante en stade 2 |
| PD à 12 mois | Régression logistique de référence, LightGBM avec les mêmes variables |
| PD à maturité | Survie en temps discret sur le panneau prêt-mois (table de mortalité du crédit) |
| LGD | Probabilité de régularisation puis sévérité, selon le ratio prêt / valeur réévalué aux prix de l'État ; recouvrement actualisé |
| EAD | Capital restant dû selon l'amortissement contractuel |
| Scénarios | Central 50 %, défavorable 30 %, favorable 20 % |
| Actualisation | Taux contractuel du prêt |

Le détail et la justification de chaque choix sont dans
[`docs/decisions.md`](docs/decisions.md), daté du 12 novembre 2026, avant tout
résultat.

## Validation

- Découpage temporel : entraînement 2000-2005, test 2006-2008.
- PD : AUC, Gini, calibration par classe de risque, PSI.
- Provision : pertes attendues par génération contre pertes constatées.
- Double calcul : la provision de 50 prêts recalculée par un script R
  indépendant, à l'identique.
- Tests : chaque brique vérifiée sur un cas calculé à la main
  ([`tests/test_cas_a_la_main.py`](tests/test_cas_a_la_main.py)).

## Résultats publiés

- L'écart de provision entre logistique et LightGBM, avec un intervalle de
  confiance bootstrap : [`bootstrap_ecart.csv`](rapport/resultats/bootstrap_ecart.csv)
  (portefeuille) et [`bootstrap_modeles.csv`](rapport/resultats/bootstrap_modeles.csv)
  (modèles réestimés).
- La part du portefeuille en stade 2 selon le seuil :
  [`grille_seuils_stade2.csv`](rapport/resultats/grille_seuils_stade2.csv).
- La procyclicité, provision trimestre par trimestre de 2006 à 2010 :
  [`trimestriel_figee.csv`](rapport/resultats/trimestriel_figee.csv) et
  [`trimestriel_scenarios.csv`](rapport/resultats/trimestriel_scenarios.csv).
- La sensibilité aux pondérations des scénarios :
  [`grille_ponderations.csv`](rapport/resultats/grille_ponderations.csv).

## Reproduire

```bash
git clone https://github.com/selyassine/ecl9
cd ecl9
pip install -e ".[dev]"
pytest                      # tests, sans les données

# archives sample_2000.zip à sample_2008.zip déposées dans data/brut/freddie/
# (portail Clarity de Freddie Mac, compte gratuit : voir data/README.md)
make donnees                # FRED, décompression et empreintes SHA-256
make exploration            # panneau prêt-mois et taux de défaut par cohorte
make pipeline               # modèles, provisions 2006-2010, double calcul R, sensibilités
make note                   # note Quarto (Quarto installé à part)
```

Le pipeline complet prend environ quatre heures sur une machine de 4 cœurs et
16 Go, dont deux heures et demie pour le bootstrap avec réestimation des
modèles.

Les données ne sont pas versionnées : la licence Freddie Mac en interdit la
redistribution. Le dépôt contient seulement le
[manifeste](data/manifeste.toml) et, après le premier téléchargement, les
empreintes des fichiers utilisés. Voir [`data/README.md`](data/README.md).

## Structure

```
ecl9/
├── src/ecl9/          donnees, definitions, staging, pd, lgd, ead, scenarios, ecl
├── tests/             cas calculés à la main ; tests/r/ double calcul en R
├── pipeline/          étapes reproductibles
├── rapport/           note de provisionnement Quarto
├── docs/decisions.md  journal daté des définitions
└── data/              hors Git, manifeste seul
```

## Limites

- Prêts immobiliers américains, pas le portefeuille d'une banque.
- Périmètre simplifié de la norme IFRS 9, sans valeur de conseil comptable.
- Scénarios macroéconomiques construits par l'auteur, pas ceux d'un
  établissement.
- Remboursement anticipé modélisé depuis la version 2 (D-040), mais appris
  avant la crise : il surestime fortement les remboursements de 2008-2010.

## Licence

Code sous licence MIT. Les données Freddie Mac et FRED restent soumises aux
conditions de leurs fournisseurs.
