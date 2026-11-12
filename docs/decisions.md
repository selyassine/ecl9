# Journal des décisions

Les définitions ci-dessous sont **figées avant toute modélisation et avant de
regarder le moindre résultat**. Une décision n'est jamais réécrite : si elle
change, on ajoute une nouvelle entrée datée qui la remplace, avec la raison, et
l'historique Git montre que le changement est postérieur.

Le module `src/ecl9/definitions.py` reprend ces valeurs ; un test vérifie que
les deux restent alignés.

---

## 2026-11-12 — Définitions de départ

### Tableau de synthèse

| Notion | Choix |
| --- | --- |
| Défaut (stade 3) | 90 jours de retard ou plus, ou saisie du bien |
| Stade 2 | 30 jours de retard, ou PD à maturité multipliée par le seuil depuis l'octroi (seuil principal : 2) |
| Stade 1 | Tout le reste |
| Horizon | 12 mois en stade 1, durée de vie restante en stades 2 et 3 |
| Actualisation | Taux contractuel du prêt |
| Scénarios | Central 50 %, défavorable 30 %, favorable 20 % |
| Découpage | Entraînement : prêts octroyés 2000-2005, arrêtés jusqu'à fin 2005 ; test : prêts octroyés 2006-2008 |

### D-001 Défaut

Un prêt est en défaut au premier mois où l'une des conditions suivantes est vraie :

- statut de retard (`delinquency_status`) supérieur ou égal à 3, soit 90 jours
  ou plus de retard ;
- statut `RA` (bien acquis par saisie, *REO acquisition*) ;
- code de solde nul (`zero_balance_code`) parmi `02` (vente à un tiers après
  saisie), `03` (vente à découvert), `09` (cession du bien saisi) et `15`
  (cession de créance non performante).

Le défaut est **absorbant** pour la PD : le prêt sort du panneau de survie au
mois du défaut. Le suivi continue pour la LGD jusqu'à la liquidation. Un statut
`XX` (inconnu) est traité comme manquant et ne déclenche pas de défaut.

### D-002 Stade 3

Prêt en défaut au sens de D-001 à la date d'arrêté.

### D-003 Stade 2

Prêt non en défaut à la date d'arrêté et :

- statut de retard supérieur ou égal à 1 (30 jours ou plus), ou
- PD à maturité annualisée à la date d'arrêté supérieure ou égale à
  **2 fois** la PD à maturité annualisée estimée à l'octroi.

Annualisation d'une PD cumulée `p` sur `n` mois : `1 - (1 - p)^(12 / n)`.
Elle rend comparables une PD calculée sur 360 mois à l'octroi et sur 300 mois
cinq ans plus tard.

Le seuil principal est 2 (doublement). La grille de sensibilité publiée est
{1,5 ; 2 ; 2,5 ; 3 ; 4}. Pas de seuil en valeur absolue ni de période
probatoire au retour en stade 1 dans la version 1 : les stades sont recalculés
à chaque arrêté.

### D-004 Stade 1

Tout prêt ni en stade 2 ni en stade 3.

### D-005 Horizon

- Stade 1 : `min(12, mois restants jusqu'à l'échéance contractuelle)`.
- Stade 2 : mois restants jusqu'à l'échéance contractuelle
  (`remaining_months_to_maturity`).
- Stade 3 : le défaut est déjà survenu, la perte est calculée directement
  (D-007).

Le remboursement anticipé n'est pas modélisé en version 1 (extension prévue
comme risque concurrent en version 2), ce qui majore la durée d'exposition des
stades 2.

### D-006 Actualisation

Taux d'intérêt contractuel courant du prêt (`current_interest_rate`), capitalisé
mensuellement. Le facteur du mois `t` après l'arrêté est
`DF(t) = (1 + r / 12)^(-t)`. La perte d'un défaut survenu au mois `t` est
actualisée de `t` mois.

### D-007 Formule centrale

Pour un prêt en stade 1 ou 2, sous le scénario `s` :

```
ECL_s = somme pour t = 1..H de  PDmarg_s(t) × LGD × EAD(t) × DF(t)
PDmarg_s(t) = S_s(t - 1) × h_s(t)          (S survie, h hasard mensuel, S(0) = 1)
ECL = somme sur s de  w_s × ECL_s
```

Pour un prêt en stade 3 : `ECL = LGD × CRD observé à l'arrêté`, la PD vaut 1 et l'actualisation
des recouvrements est incluse dans la LGD réalisée.

### D-008 EAD

Capital restant dû au début du mois `t`, selon l'amortissement contractuel à
annuité constante au taux courant sur la durée restante, en partant du capital
restant dû observé à l'arrêté (`EAD(1)` = capital observé). Ni tirage
supplémentaire ni intérêts courus impayés en version 1.

### D-009 LGD

Sur les prêts en défaut liquidés :

- **régularisation** : retour au statut 0 ou remboursement intégral (code `01`)
  après le défaut, sans perte réalisée ;
- **sévérité** : perte réalisée (`actual_loss`, convention de signe à vérifier
  sur les données) rapportée au capital restant dû au défaut, bornée à [0, 1].

`LGD = (1 - P(régularisation)) × sévérité`. Les prêts en défaut non encore
liquidés à la date d'extraction sont exclus du calibrage de la sévérité.

### D-010 Découpage temporel

- Entraînement : prêts octroyés (premier paiement) de 2000 à 2005, et **seuls
  les arrêtés jusqu'au 31/12/2005**, dont la fenêtre de 12 mois se termine au
  plus tard fin 2006. Sans cette coupure, les prêts 2000-2005 apporteraient au
  modèle leur comportement de 2007-2009 et il aurait « vu » la crise.
- Choix des hyperparamètres de LightGBM : validation interne sur les arrêtés
  de 2005, jamais sur la période de test.
- Test : prêts octroyés de 2006 à 2008, sur tout leur historique.
- Les cohortes 1999 et postérieures à 2008 ne servent pas à l'estimation.

### D-011 Échantillon de modélisation de la PD à 12 mois

Une observation par prêt et par arrêté trimestriel (mars, juin, septembre,
décembre) où le prêt est actif et non en défaut. Cible : défaut au sens de
D-001 dans les 12 mois suivants. Un prêt soldé sans défaut dans la fenêtre
compte comme non-défaut.

### D-012 Variables macroéconomiques (FRED, niveau national)

| Série FRED | Contenu | Transformation |
| --- | --- | --- |
| `UNRATE` | Taux de chômage | niveau et variation sur 12 mois |
| `CSUSHPISA` | Indice Case-Shiller national, CVS | variation sur 12 mois |
| `MORTGAGE30US` | Taux fixe 30 ans (hebdomadaire) | moyenne mensuelle ; écart avec le taux du prêt |
| `DGS10` | Taux à 10 ans (quotidien) | moyenne mensuelle |

Seules les valeurs connues à la date d'arrêté sont utilisées. Les indices par
État sont une extension.

### D-013 Scénarios

Trois scénarios pondérés : central 50 %, défavorable 30 %, favorable 20 %.
Les trajectoires sont construites par l'auteur en semaine 5 ; ce ne sont pas
celles d'un établissement.

### D-014 Mesures de validation

- Discrimination : AUC et Gini (`2 × AUC - 1`).
- Calibration : taux observé contre PD moyenne par décile de PD.
- Stabilité : PSI sur 10 classes, alertes à 0,10 et 0,25.
- Provision : pertes attendues par génération contre pertes constatées.
- Écart logistique / LightGBM : bootstrap par prêt, 1 000 tirages, graine
  `20261112`.

### D-015 Valeurs manquantes

Les codes sentinelles Freddie Mac (score `9999`, LTV/CLTV `999`, DTI `999`,
etc.) sont convertis en valeurs manquantes à la lecture. Leur traitement dans
les modèles (indicatrice et imputation pour la logistique, natif pour
LightGBM) est fixé en semaine 2.
