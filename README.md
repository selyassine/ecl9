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
> **Answer:** yes, but the effect is second-order. With everything else equal,
> LightGBM raises the allowance by 27-41% between end-2006 and end-2008
> (+38% at 31/12/2007, 95% bootstrap interval +35% to +40%), and by 6-8% in
> 2009-2010. Yet both models, trained before the crisis, cover only 6-9% of the
> losses later realised over the same horizon. Report and documentation are in
> French.

**Note de provisionnement : <https://selyassine.github.io/ecl9/>**

**Réponse : oui, LightGBM change la provision, mais beaucoup moins que
l'erreur commune aux deux modèles.** Avec les mêmes variables, la même survie,
la même LGD et les mêmes stades, LightGBM provisionne 27 à 41 % de plus que la
logistique entre fin 2006 et fin 2008 (au 31/12/2007 : 11,7 contre 8,5 M$,
écart + 38 %, intervalle bootstrap à 95 % de + 35 à + 40 %), puis 6 à 8 % de
plus en 2009-2010, quand les défauts déjà survenus dominent. Mais entraînés sur
2000-2005, les deux modèles ne voient pas venir la crise : au 31/12/2007, leurs
provisions ne couvrent que 6 à 9 % des pertes constatées ensuite sur le même
horizon.

- PD à 12 mois : LightGBM classe un peu mieux (AUC 0,815 contre 0,789 sur
  2006-2010) et sous-estime moins les défauts (31 % des défauts prévus contre
  17 %) ([`pd12.md`](rapport/resultats/pd12.md)).
- Survie et LGD : aucune sensibilité au chômage ni aux prix n'est
  identifiable sur 2000-2005 ([`survie.md`](rapport/resultats/survie.md)) ;
  la LGD est sous-estimée d'un facteur 4 sur la crise
  ([`lgd_moteur.md`](rapport/resultats/lgd_moteur.md)).
- Stade 2 : au seuil retenu (PD à maturité doublée), le critère de
  dégradation n'ajoute rien au retard de paiement ; au seuil 1,5, la baisse
  des taux de 2009-2010 fait basculer jusqu'à 82 % de l'encours.
- Scénarios : pondérés 50/30/20, ils ajoutent 0,4 à 3,6 % ; 14 % au plus avec
  une sensibilité chômage et prix tirée de la littérature, publiée à part
  ([`stades_backtest.md`](rapport/resultats/stades_backtest.md)).

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
| Stade 2 | 30 jours de retard, ou PD à maturité annualisée doublée depuis l'octroi |
| Horizon | 12 mois en stade 1, durée de vie restante en stade 2 |
| PD à 12 mois | Régression logistique de référence, LightGBM avec les mêmes variables |
| PD à maturité | Survie en temps discret sur le panneau prêt-mois (table de mortalité du crédit) |
| LGD | Probabilité de régularisation puis sévérité, calibrées sur les pertes réalisées |
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
  confiance bootstrap : [`bootstrap_ecart.csv`](rapport/resultats/bootstrap_ecart.csv).
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

Le pipeline complet prend environ une heure sur une machine de 4 cœurs et
16 Go.

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
- Remboursement anticipé non modélisé en version 1, ce qui allonge la durée
  d'exposition des prêts en stade 2.

## Licence

Code sous licence MIT. Les données Freddie Mac et FRED restent soumises aux
conditions de leurs fournisseurs.
