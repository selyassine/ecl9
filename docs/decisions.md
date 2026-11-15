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

---

## 2026-11-13 — Précisions après lecture des fichiers réels

Ces précisions viennent du format des fichiers (guide utilisateur Freddie Mac
de juillet 2026) et de la construction du panneau. Aucun modèle n'a encore été
estimé.

### D-016 Format, millésime et perte réalisée

- Les archives `sample_AAAA.zip` contiennent `sample_orig_AAAA.txt`
  (31 champs) et `sample_perf_AAAA.txt` (35 champs). Le champ « Servicer
  Name » est passé du fichier d'octroi au fichier de suivi, et un score
  VantageScore 4.0 (vide sur 2000-2008) a été ajouté.
- **Millésime** : l'année d'octroi retenue pour le découpage de D-010 est
  l'année du fichier échantillon, pas l'année du premier paiement. Dans le
  fichier 2005, 16 % des prêts ont un premier paiement en 2006 ou après.
- **Perte réalisée** : `actual_loss` est positive pour une perte et négative
  pour un gain. Elle n'est calculée que pour les codes de solde nul 02, 03, 09
  et 15, ce qui confirme la liste de D-001. Cela tranche la convention de
  signe laissée ouverte en D-009.
- **Code 96** (défaut de souscription ou de gestion confirmé avant tout
  incident de crédit, rachat par le vendeur) : ce n'est pas un défaut. Le
  prêt sort du panneau sans événement, comme un remboursement.
- **Code 16** (titrisation de prêts redevenus performants) : ce n'est pas un
  défaut, le prêt sort sans événement.

### D-017 Arrêtés sans recul complet

Un arrêté dont la fenêtre de 12 mois dépasse la dernière date observée du jeu
(juin 2026) est retiré de l'échantillon PD à 12 mois **dans tous les cas**,
y compris si le défaut est déjà observé : ne garder que les défauts
biaiserait la cible vers 1.

### D-018 Moratoires de 2020-2021

Les retards liés aux moratoires COVID apparaissent comme des défauts de
90 jours en 2020-2021. Ils sont hors de la période étudiée (arrêtés de 2000 à
2010) et ne sont pas retraités.

---

## 2026-11-13 — PD à 12 mois : variables et protocole, avant estimation

### D-019 Variables communes aux deux modèles

La régression logistique et LightGBM reçoivent **exactement** les mêmes
variables. Seule leur préparation diffère (D-020).

| Groupe | Variables |
| --- | --- |
| Octroi, numériques | score de crédit, LTV, CLTV, DTI, taux d'origine, log du capital initial, durée initiale, taux d'assurance hypothécaire (MI %) |
| Octroi, catégorielles | objet du prêt, occupation, canal, type de bien, primo-accédant, nombre de logements, nombre d'emprunteurs, État |
| Dynamiques à l'arrêté | âge du prêt, retard en mensualités (0, 1 ou 2), capital restant / capital initial, écart entre le taux du prêt et le taux fixe 30 ans du marché |
| Macro nationales (FRED) | chômage, variation du chômage sur 12 mois, variation sur 12 mois de l'indice Case-Shiller, taux à 10 ans |

Variables écartées : celles qui sont constantes sur 2000-2008 (type
d'amortissement, prêt in fine, programme, méthode d'évaluation, VantageScore),
la MSA (34 % de valeurs manquantes) et la LTV estimée (non renseignée avant
2013).

**Valeurs connues à l'arrêté** : le chômage du mois `m` est publié début
`m + 1`, et l'indice Case-Shiller avec deux mois de retard. Le chômage est
donc pris avec 1 mois de décalage, l'indice avec 2 mois, et les taux en
moyenne du mois de l'arrêté.

### D-020 Préparation et réglage

- **Logistique** : variables numériques centrées-réduites ; valeurs
  manquantes remplacées par la médiane d'entraînement, avec une indicatrice ;
  catégorielles et retard en indicatrices ; pénalité L2 faible (`C = 1`).
  Aucune transformation non linéaire : c'est le modèle de référence.
- **LightGBM** : valeurs manquantes et catégorielles gérées nativement.
  Grille : `num_leaves` ∈ {15, 31, 63}, `min_child_samples` ∈ {200, 1 000},
  taux d'apprentissage 0,05, sous-échantillonnage de 80 % des lignes et
  des variables, arrêt précoce après 100 itérations sans gain.
- **Réglage** : apprentissage sur les arrêtés jusqu'à fin 2004, validation sur
  les arrêtés de 2005 (millésimes 2000-2005). Le modèle final est réestimé
  sur tout l'échantillon d'entraînement avec le nombre d'itérations retenu.
  La période de test n'intervient jamais dans un choix.
- Graine `20261112`.

### D-021 Mesures publiées

Sur le test (millésimes 2006-2008, tous leurs arrêtés de 2006 à 2025), et
séparément sur les arrêtés de 2006 à 2010 :

- AUC et Gini ;
- calibration : défaut observé contre PD moyenne par décile de PD, et rapport
  de la somme des PD au nombre de défauts ;
- PSI de la distribution des PD entre l'entraînement et le test ;
- score de Brier.

---

## 2026-11-13 — Correction du réglage de LightGBM après une fuite détectée

### D-022 Validation de réglage séparée par prêt

**Constat (première estimation, résultats conservés dans
`rapport/resultats/v1_pd12_*.csv`).** LightGBM, réglé selon D-020, atteint une
AUC de 0,998 sur l'entraînement contre 0,789 sur le test : il a mémorisé des
prêts. La cause est dans D-020 : un même prêt figure dans l'apprentissage
(arrêtés jusqu'à fin 2004) et dans la validation (arrêtés de 2005), et les
fenêtres de 12 mois se chevauchent. Un défaut de 2005 est donc déjà dans la
cible de l'arrêté de décembre 2004 du même prêt. L'arrêt précoce récompense
alors la mémorisation (1 062 itérations à 63 feuilles), et des variables
quasi identifiantes comme le capital initial prennent 8 % du gain.

Ce défaut a été repéré par l'écart entre l'entraînement et la validation. Les
mesures de test de cette première version ont toutefois été vues, et elles
sont publiées telles quelles :

| Modèle (v1) | AUC test | AUC arrêtés 2006-2010 | Attendu / observé 2006-2010 |
| --- | --- | --- | --- |
| Logistique | 0,779 | 0,789 | 0,17 |
| LightGBM | 0,789 | 0,799 | 0,19 |

**Correction.** 20 % des prêts d'entraînement, tirés par un hachage stable de
leur identifiant, forment la validation (leurs arrêtés de 2005). Les 80 %
restants forment l'apprentissage (leurs arrêtés jusqu'à fin 2004). Aucun prêt
n'est des deux côtés. Le reste de D-020 est inchangé : grille, arrêt précoce
et réestimation finale sur tout l'entraînement. La logistique n'est pas
concernée, car elle n'a pas de réglage.

---

## 2026-11-13 — PD à maturité : protocole, avant estimation

### D-023 Modèle de survie en temps discret

- **Unité** : le mois de vie d'un prêt dans le panneau (D-001). L'événement
  est le défaut. Le remboursement anticipé et les autres sorties sont des
  censures, ce qui donne un hasard spécifique au défaut. Cohérent avec D-005,
  le remboursement anticipé n'est pas projeté.
- **Hasard** : `h(t) = logit⁻¹(α(âge) + β·x + γ·macro(t))`, régression
  logistique sur les prêts-mois. C'est une table de mortalité du crédit :
  - `α(âge)` est une bande d'âge en mois : 0-6, 7-12, 13-24, 25-36, 37-48,
    49-60, 61 et plus. Au-delà de l'âge maximal vu à l'entraînement
    (environ 72 mois), le hasard de base reste celui de la dernière bande ;
  - `x` regroupe les variables d'octroi de D-019, numériques et catégorielles,
    préparées comme la logistique de D-020 ;
  - `macro(t)` regroupe le chômage, sa variation sur 12 mois, la variation sur
    12 mois de Case-Shiller, le taux à 10 ans et l'écart entre le taux du prêt
    et le taux fixe 30 ans, au mois `t`, avec les décalages de D-019.
- **Pas de retard en cours dans le hasard** : il faudrait projeter le retard
  mois par mois, ce qui demanderait un modèle de transitions. Le retard en
  cours entre dans la provision par le stade (D-003) et par l'ancrage
  ci-dessous.
- **Entraînement** : millésimes 2000-2005, mois jusqu'au 31/12/2005 (D-010).
  Tous les défauts sont gardés, avec 5 % des prêts-mois sans défaut tirés au
  hasard (graine `20261112`) et pondérés par 20. Ce sous-échantillonnage ne
  biaise pas les coefficients pondérés.

### D-024 Ancrage de la structure par terme sur la PD à 12 mois

C'est le point où la question du projet (logistique contre LightGBM) passe
à la PD à maturité. Pour un prêt à la date d'arrêté :

1. le modèle de survie donne les hasards `h(1..n)` sur la durée restante ;
2. on cherche `c ≥ 0` tel que `1 - Π_{k=1..12} (1 - min(c·h(k), 1))` soit égal
   à la PD à 12 mois du modèle retenu (logistique ou LightGBM) ;
3. les hasards des mois 1 à 12 sont multipliés par `c`, et ceux des mois 13 et
   au-delà sont laissés tels quels.

La PD à 12 mois porte donc l'information propre au prêt (retard, score,
interactions), et le modèle de survie porte la forme dans le temps et la
sensibilité au scénario macro au-delà d'un an. Si la durée restante est
inférieure à 12 mois, l'ancrage porte sur cette durée.

### D-025 Validation de la survie

Sur les millésimes 2006-2008, mois de 2006 à 2010 :

- défauts attendus (somme des hasards) contre défauts observés, par année
  calendaire et par millésime, d'abord avec la **macro réalisée** (prévision
  parfaite du scénario), puis avec la **macro figée** à sa valeur de
  décembre 2005. L'écart entre les deux mesure ce que la macro du modèle
  explique de la crise ;
- AUC au niveau prêt-mois.

---

## 2026-11-13 — Sensibilité macro de la survie (choix de l'auteur)

### D-026 Contrainte de signe sur les coefficients macro

**Constat (D-025, `rapport/resultats/survie.md`)** : estimé sur 2000-2005, le
coefficient de la variation des prix immobiliers est positif. Avec la macro
réalisée, le modèle prévoit alors moins de défauts en 2006-2010 qu'avec une
macro figée. Une période sans baisse des prix ne permet pas d'apprendre
l'effet d'une baisse.

**Choix** : chaque variable macro a un signe attendu. Le chômage, sa variation
et l'écart de taux augmentent le hasard ; la variation des prix le diminue.
Le taux à 10 ans n'est pas contraint. Les variables de signe contraire sont
retirées une à une, en commençant par la plus fautive, et le modèle est
réestimé jusqu'à ce que tous les signes soient conformes. Retirer une
variable revient à fixer son coefficient à zéro, sans rien inventer.

**Conséquences** :
- le modèle contraint devient le modèle de survie utilisé par le moteur ;
- le modèle libre reste estimé, et ses résultats restent publiés à côté ;
- la contrainte empêche une sensibilité de mauvais signe, mais elle
  n'apporte aucune sensibilité que les données n'ont pas montrée. Si la
  variable des prix est retirée, les scénarios ne pourront agir sur la PD
  que par le chômage et les taux.

---

## 2026-11-13 — LGD, EAD et moteur : protocole, avant estimation

### D-027 Résolution d'un défaut

Pour chaque prêt en défaut au sens de D-001 (premier mois de défaut `d`), le
suivi complet après `d` donne sa résolution :

- **perte** : sortie avec un code 02, 03, 09 ou 15. La sévérité vaut
  `actual_loss / zero_balance_removal_upb`, bornée à [0, 1]. Le dénominateur
  est le capital retiré à la sortie, celui sur lequel Freddie Mac calcule la
  perte ;
- **régularisation** : remboursement (code 01), cession d'un prêt redevenu
  performant (code 16), ou prêt encore actif avec moins de 3 mensualités de
  retard à la fin de la fenêtre d'observation ;
- **non résolu** : encore en retard de 3 mensualités ou plus à la fin de la
  fenêtre, ou code 96. Exclu du calibrage.

Un prêt régularisé puis de nouveau en défaut et liquidé compte comme une
perte : c'est la sortie finale qui décide.

### D-028 LGD en deux étapes : données et modèles

- **Entraînement** : défauts survenus jusqu'à fin 2005 (millésimes
  2000-2005), avec une résolution observée jusqu'à fin 2006. C'est la même
  année de recul que la PD (D-010). Des résolutions plus tardives feraient
  entrer dans la LGD les ventes de biens de la crise.
- **Régularisation** : régression logistique de `P(régularisation)` sur la
  LTV et le score à l'octroi, le ratio capital restant / capital initial, le
  taux d'assurance hypothécaire et l'âge du prêt au défaut.
- **Sévérité** : régression linéaire bornée à [0, 1] sur les mêmes variables,
  estimée sur les seules pertes.
- `LGD = (1 - P(régularisation)) × sévérité`.
- **Validation** : défauts des millésimes 2006-2008 survenus de 2006 à 2010,
  résolution observée sur tout l'historique disponible. On compare la LGD
  moyenne prévue à la LGD réalisée, pondérée par le capital.

### D-029 Moteur vectorisé

Le hasard de survie est logistique, donc additif dans le logit :
`logit h(i, k) = a_i + α(bande d'âge) + Σ γ_m·macro_m(t + k) + δ·écart_i(t + k)`.
Le moteur calcule une fois le terme propre au prêt `a_i`, puis ajoute les
termes d'âge et de macro mois par mois. Le résultat est identique à une
prédiction ligne par ligne, et un test le vérifie à 1e-10 près. Pour chaque
prêt, la suite du calcul est : ancrage (D-024), EAD (D-008), LGD (D-028),
actualisation (D-006), puis la formule de D-007.

Tant que les scénarios ne sont pas construits (semaine 5), la trajectoire
macro est **figée** à sa valeur de l'arrêté.

---

## 2026-11-13 — Stades, procyclicité, backtest et double calcul : protocole, avant calcul

### D-030 Critère de dégradation du stade 2, en pratique

La comparaison de D-003 se fait **avec la même chaîne de modèles** à l'octroi
et à l'arrêté. Chaque modèle de PD à 12 mois a donc ses propres stades :

- **à l'octroi** : PD à 12 mois du modèle calculée sur les variables
  d'octroi (âge 0, aucun retard, capital restant = capital initial, macro du
  mois précédant le premier paiement). Hasards de survie depuis l'âge 0 sur la
  durée initiale, macro figée à ce mois, ancrés sur cette PD (D-024). On en
  tire la PD cumulée sur la durée initiale, puis annualisée ;
- **à l'arrêté** : PD à 12 mois du modèle à l'arrêté, hasards projetés sur la
  durée restante avec la trajectoire macro de l'arrêté, ancrés. On en tire la
  PD cumulée sur la durée restante, puis annualisée ;
- stade 2 si le rapport des deux PD annualisées atteint 2, ou en cas de
  retard d'au moins une mensualité.

### D-031 Provision trimestrielle 2006-2010 (procyclicité)

- Arrêtés de fin mars 2006 à fin décembre 2010, soit 20 trimestres.
- Portefeuille : prêts des millésimes 2006-2008 présents à l'arrêté,
  c'est-à-dire actifs ou en défaut non encore résolu. Les prêts en défaut sont
  en stade 3, avec la LGD du modèle (D-028) appliquée à leur capital au
  défaut.
- La trajectoire macro est figée à l'arrêté tant que les scénarios ne sont
  pas construits. Elle sera remplacée par la moyenne pondérée des scénarios
  (D-013), et les deux versions seront publiées.

### D-032 Backtest

- **Par arrêté** : la provision est comparée aux pertes réellement constatées
  sur le même périmètre et le même horizon. Pour un prêt en stade 1, on
  compte les défauts dans les 12 mois ; pour un prêt en stade 2, les défauts
  jusqu'à la fin des données ; pour un prêt en stade 3, la résolution de son
  défaut en cours. La perte constatée d'un défaut vaut 0 en cas de
  régularisation, et `actual_loss` (plafonnée au capital) en cas de perte.
  Les défauts non résolus sont comptés à part. Les pertes ne sont pas
  actualisées.
- **Par génération** : à la fin de l'année d'octroi, la perte attendue sur
  toute la durée de vie (tous les prêts traités à maturité, macro figée) est
  comparée aux pertes constatées sur ces prêts jusqu'en juin 2026.

### D-033 Double calcul en R

`tests/r/double_calcul.R` recalcule la provision à partir des seules entrées
de la formule (stade, capital, taux, durée restante, LGD, PD à 12 mois,
hasards non ancrés), sans aucun code Python : ancrage par dichotomie,
échéancier, PD marginales, actualisation. Deux contrôles sont faits :

- en intégration continue, sur 50 prêts simulés dont les entrées sont
  générées par le test Python ;
- sur 50 prêts réels tirés au hasard (graine `20261112`) dans le portefeuille
  au 31/12/2007. Les entrées réelles ne sont pas versionnées (D-016) ; le
  résultat de la comparaison l'est.

Tolérance : écart relatif inférieur à 1e-8 par prêt.

---

## 2026-11-13 — Scénarios et surcouche de sensibilité : protocole, avant calcul

### D-034 Scénarios prospectifs

Les trajectoires sont construites à chaque arrêté à partir des seules valeurs
connues à cette date. Les chocs sont atteints linéairement en 12 mois (24 mois
pour le chômage du scénario défavorable), puis tenus. Au-delà de 36 mois, les
prix immobiliers se stabilisent dans les trois scénarios.

| Scénario | Poids | Chômage | Prix immobiliers (variation annuelle) | Taux 30 et 10 ans |
| --- | --- | --- | --- | --- |
| Central | 50 % | niveau de l'arrêté | celle de l'arrêté | niveau de l'arrêté |
| Défavorable | 30 % | + 3 points | - 10 % | - 1 point |
| Favorable | 20 % | - 0,5 point | celle de l'arrêté + 3 points | + 0,5 point |

Le choc défavorable reprend l'ordre de grandeur des récessions américaines
connues avant 2006 (chômage + 2,6 points en 1990-1992, + 2,5 points en
2000-2003) ; une baisse nationale des prix de 10 % par an n'avait pas
d'équivalent depuis les années 1930 et constitue donc un choc sévère. Les taux
baissent en récession. La variation du chômage sur 12 mois est recalculée sur
la trajectoire, en reliant historique et projection.

La provision est la moyenne pondérée des provisions de chaque scénario. Les
stades restent ceux de D-030, calculés avec la trajectoire figée (identique au
scénario central pour le modèle de survie retenu).

**Résultat principal, purement statistique.** Le modèle de survie retenu
(D-026) ne connaît que les taux ; les scénarios n'agissent que par ce canal.

**Surcouche, en sensibilité seulement** (choix de l'auteur, 2026-11-13). Le
logit du hasard mensuel reçoit un écart tiré d'Elul, Souleles,
Chomsisengphet, Glennon et Hunt, « What "Triggers" Mortgage Default? »,
Federal Reserve Bank of Philadelphia, document de travail 10-13, avril 2010,
table 1 (logit trimestriel du passage à 60 jours de retard, prêts à taux fixe
octroyés en 2005-2006, données LPS) :

- variation du chômage sur un an, classes < -0,5 / [-0,5 ; 0) / [0 ; 0,7) /
  [0,7 ; 1,25) / ≥ 1,25 point : 0 ; 0,006 ; 0,084 ; 0,183 ; 0,400 ;
- CLTV réévaluée, classes < 50 / [50 ; 70) / [70 ; 80) / [80 ; 90) /
  [90 ; 100) / [100 ; 110) / [110 ; 120) / ≥ 120 : 0 ; 0,415 ; 0,718 ; 0,985 ;
  1,226 ; 1,361 ; 1,550 ; 1,566.

L'écart est la différence entre la classe projetée et la classe à l'arrêté.
La CLTV réévaluée vaut CLTV d'octroi (LTV à défaut) × capital restant / capital
initial × indice Case-Shiller national à l'octroi / indice projeté ; le
capital est tenu à son niveau de l'arrêté. Limites assumées : coefficients
estimés sur un autre échantillon, à fréquence trimestrielle et pour un défaut
à 60 jours, appliqués tels quels au logit mensuel du défaut à 90 jours ; étude
publiée après la crise qu'elle couvre. La provision avec surcouche est publiée
à côté du résultat principal, jamais à sa place.

### D-035 Double calcul sur prêts réels, tirage

Le tirage de D-033 est stratifié : 25 prêts en stade 1 et 25 en stade 2
(critère de retard de l'étape 6), sans quoi presque tous seraient en stade 1.
Le stade 3 (LGD × capital) est couvert par le contrôle sur prêts simulés.

---

## 2026-11-13 — Correction après le premier calcul des scénarios

### D-036 Les scénarios s'appliquent après l'ancrage

Premier calcul (publié dans `rapport/resultats/v1_trimestriel_scenarios.csv`) :
les hasards de chaque scénario étaient ancrés sur la PD à 12 mois (D-024),
qui ne dépend pas du scénario. L'ancrage effaçait donc tout effet des
scénarios, et de la surcouche, sur les 12 premiers mois : la provision des
prêts en stade 1 était identique dans les trois scénarios.

Correction : les hasards du scénario central sont ancrés comme avant ; chaque
scénario ajoute ensuite au logit ancré son écart au central, mois par mois
(`logit h_s - logit h_central` pour le modèle de survie, plus l'écart de la
surcouche le cas échéant). La PD à 12 mois du modèle reste la prévision du
scénario central. Rien d'autre ne change.

---

## 2026-11-14 — Semaine 6 : intervalle de confiance, grilles de sensibilité, note : protocole, avant calcul

### D-037 Intervalle de confiance de l'écart logistique / LightGBM

À chaque arrêté trimestriel (macro figée, D-031), les prêts du portefeuille,
stade 3 compris, sont tirés avec remise, 1 000 fois, graine `20261112`
(D-014). Pour chaque tirage : écart relatif `Σ ECL LightGBM / Σ ECL
logistique - 1` et écart absolu. L'intervalle publié est celui des centiles
2,5 et 97,5. Les modèles sont tenus fixes : l'intervalle mesure
l'incertitude due à la composition du portefeuille, pas celle de
l'estimation des modèles, qui demanderait de les réestimer à chaque tirage.

### D-038 Grilles de sensibilité

- **Seuil du stade 2** : part de l'encours en stade 2 pour un rapport des PD
  annualisées de 1,5 ; 2 ; 2,5 ; 3 ; 4, et avec le seul critère de retard,
  par modèle et par arrêté (D-003).
- **Pondérations des scénarios** : provision pondérée pour 50/30/20
  (référence), 60/20/20, 40/40/20, 1/3 chacun, et chaque scénario seul, avec
  et sans surcouche (D-034). Les provisions par scénario étant déjà
  calculées, seule la moyenne change.

### D-039 Note de provisionnement

`rapport/note.qmd`, rendue par Quarto et publiée sur GitHub Pages par
l'intégration continue. Elle ne lit que les fichiers de `rapport/resultats/`,
versionnés ; elle ne touche jamais aux données Freddie Mac.

---

## 2026-11-14 — Améliorations après la version 1 : protocole, avant calcul

Les résultats de la version 1 (D-001 à D-039) restent publiés tels quels,
renommés avec le suffixe `_sans_remboursement` ; ceux qui suivent les
complètent sans les réécrire.

### D-040 Remboursement anticipé en risque concurrent

- **Événement** : solde nul de code `01` (remboursement intégral) alors qu'il
  reste plus d'une mensualité, hors défaut. L'échéance naturelle n'est pas un
  remboursement anticipé.
- **Modèle** : hasard mensuel de remboursement en temps discret, même forme
  et mêmes variables que le hasard de défaut (D-023), estimé sur les prêts
  2000-2005 et les mois jusqu'au 31/12/2005, sur un tirage uniforme de 5 %
  des lignes prêt-mois (graine `20261112`).
- **Signes** : même procédure que D-026, avec les signes attendus pour un
  remboursement : écart de taux +, variation des prix +, chômage et sa
  variation -.
- **Moteur** : survie `S(t) = Π (1 - h_défaut - h_remboursement)` ; PD
  marginale `S(t-1) × h_défaut(t)`. L'EAD reste l'amortissement contractuel
  d'un prêt encore en vie. L'ancrage (D-024) vise désormais la probabilité de
  défaut dans les 12 mois **en présence** du remboursement, qui est ce que le
  modèle de PD à 12 mois a appris. La PD à maturité des stades (D-030) est
  calculée de la même façon, à l'octroi comme à l'arrêté. Le hasard de
  remboursement n'est pas ancré ; dans les scénarios, il suit la trajectoire
  du scénario.
- **Validation** : remboursements attendus contre observés sur 2006-2010,
  macro réalisée et figée, comme pour le défaut (D-025).

### D-041 Prix immobiliers par État dans la surcouche

La CLTV réévaluée de la surcouche (D-034) utilise, en plus de l'indice
national, l'indice FHFA « toutes transactions » de l'État du bien (séries
FRED `<État>STHPI`, trimestrielles, 50 États et Washington). La valeur d'un
trimestre est tenue pour connue 4 mois après son premier mois (publication
environ deux mois après la fin du trimestre). La trajectoire des scénarios
reste nationale : seul le point de départ, la CLTV à l'arrêté, devient propre
à l'État. Les territoires sans indice (Guam, Porto Rico, îles Vierges)
gardent l'indice national. Les deux versions de la surcouche sont publiées ;
la version par État ne remplace pas la version nationale.

### D-042 Intervalle de confiance avec réestimation des modèles

L'intervalle de D-037 tient les modèles fixes. Celui-ci ajoute l'incertitude
d'estimation des deux modèles de PD à 12 mois :

- 100 tirages (et non 1 000, pour un temps de calcul de quelques heures),
  graine `20261112` ;
- à chaque tirage, les **prêts** d'entraînement (2000-2005) sont tirés avec
  remise, avec toutes leurs observations trimestrielles ; la logistique et
  LightGBM sont réestimés, LightGBM avec les hyperparamètres retenus en
  semaine 2 (pas de nouveau réglage) ;
- le portefeuille de l'arrêté est tiré avec remise dans le même tirage ;
- la survie, le remboursement anticipé, la LGD et les stades sont tenus à
  ceux du résultat principal ; seule la PD à 12 mois change ;
- arrêtés 31/12/2007 et 31/12/2008, macro figée, remboursement anticipé
  inclus (D-040). Intervalle : centiles 2,5 et 97,5 de l'écart relatif.

## 2026-11-15 — Revue corrective : stade 3, backtest, ancrage, étiquettes

Quatre points relevés par une relecture critique du dépôt. Chacun a été
vérifié dans le code puis chiffré sur les données avant correction.

### D-043 Exposition du stade 3 à la date d'arrêté

**Corrige D-031.** La provision d'un prêt en stade 3 utilisait le capital au
moment du défaut. Elle utilise désormais le capital restant dû **à l'arrêté**
(`current_upb` du suivi mensuel), et à défaut seulement le capital au défaut
(prêt absent du suivi à cette date, ou capital nul). L'étape 5 écrit pour
cela `data/intermediaire/crd_defauts_arretes.parquet`.

Effet mesuré : l'encours et la provision du stade 3 baissent de 0 à 0,18 %
selon l'arrêté, parce qu'un prêt en défaut ne s'amortit presque plus. Les
stades 1 et 2 sont inchangés. La LGD garde ses variables au moment du défaut,
telles qu'elle a été estimée (D-028). Le stade 3 reste LGD × capital : ni
flux de recouvrement actualisés, ni intérêts courus.

Le bootstrap avec réestimation (D-042, 2 h 30 de calcul) n'a pas été relancé :
il reprend la provision du stade 3 d'avant cette correction, commune aux deux
modèles, et l'effet sur l'écart relatif est inférieur à 0,1 point.

### D-044 Défauts sans perte publiée dans le backtest

**Complète D-032.** Parmi les 12 122 défauts du test, 1 512 n'ont pas de perte
exploitable : 1 492 sont sortis des données avec un code de défaut mais sans
`actual_loss`, 20 sont encore ouverts. Ils étaient comptés à part, mais leur
perte valait zéro dans `pertes_constatees`, qui est donc un **minorant**.

- `pertes_constatees` garde sa définition (pertes chiffrées) pour rester
  comparable aux versions précédentes ;
- une colonne `pertes_non_resolus_estimees` s'y ajoute : capital au défaut ×
  sévérité moyenne, pondérée par le capital, des pertes chiffrées de la même
  année de défaut. C'est une estimation rétrospective, utilisée seulement
  pour le backtest, jamais par les modèles ;
- la note publie les deux mesures.

Effet mesuré : les pertes du backtest augmentent de 15 à 37 % aux arrêtés de
fin d'année (31 % au 31/12/2007 : 177 M$ au lieu de 135 M$). La couverture au
31/12/2007 passe de 5-8 % à 4-6 %. Le constat de sous-provisionnement en sort
renforcé ; l'écart entre les deux modèles n'est pas concerné.

### D-045 Faisabilité de l'ancrage en présence du remboursement

**Complète D-024 et D-040.** Avec un remboursement concurrent, la PD à 12 mois
visée peut être inatteignable : en multipliant les hasards de défaut, on ne
dépasse pas la probabilité de ne pas avoir remboursé avant le premier mois où
le hasard est positif. `moteur.pd12_maximale` calcule cette borne ;
`ancrer_matrice` sature les hasards des prêts concernés et émet un
`AvertissementAncrage` avec leur nombre, au lieu de converger en silence.

Effet mesuré : le cas se produit réellement, pour quelques prêts par arrêté
(1 à 9 par lot de 20 000). Ce sont des prêts à deux mensualités de retard,
avec une PD à 12 mois de 75 à 90 % et un hasard de remboursement de 11 à 27 %
le premier mois : leur PD ancrée est plafonnée à 73-89 %. Les montants
publiés ne changent pas, l'ancien code saturait déjà ces prêts sans le dire.
La cause de fond est le modèle de remboursement, qui ignore le retard de
paiement.

### D-046 Maturation des étiquettes à la coupure d'entraînement

**Précise D-010.** Les PD à 12 mois sont entraînées sur les arrêtés jusqu'au
31/12/2005. L'étiquette d'un arrêté n'est connue que 12 mois plus tard : ces
modèles n'auraient pu être estimés qu'à partir du 31/12/2006, et ils ont vu
les défauts de 2006 des prêts 2000-2005. Aucun prêt de test n'est concerné
(millésimes disjoints), mais les arrêtés de test de 2006 ne sont pas
strictement hors période. D-010 le disait (« fenêtre de 12 mois se terminant
au plus tard fin 2006 ») sans en tirer la conséquence. La même remarque vaut
pour la LGD, dont les résolutions sont observées jusqu'à fin 2006 (D-028).

Le résultat principal n'est pas modifié. Une sensibilité est ajoutée
(`pipeline/etape_11_coupure_stricte.py`, `rapport/resultats/coupure_stricte.csv`) :
les deux modèles sont réestimés sur les seuls arrêtés jusqu'au 31/12/2004,
dont l'étiquette est connue au 31/12/2005, avec les hyperparamètres de
LightGBM déjà retenus ; survie, remboursement, LGD et stades sont ceux du
résultat principal, comme en D-042.

Résultat : l'écart LightGBM / logistique au 31/12/2007 tombe de + 47 % à
+ 25 % (+ 38 % à + 24 % au 31/12/2008). LightGBM bouge peu (10,0 M$ contre
10,5 M$) ; c'est la logistique qui provisionne davantage (8,1 M$ contre
7,1 M$) et sous-estime moins les défauts de 2006-2010 (23,5 % des défauts
prévus contre 16,5 %, AUC 0,803 contre 0,789). Le sens de l'écart est
conservé, son ampleur dépend donc de l'année d'entraînement retirée : + 25 %
est sous la borne basse de l'intervalle de D-042 (+ 27 %), qui ne mesure que
l'incertitude d'échantillonnage à fenêtre d'entraînement donnée. La réponse
publiée donne désormais les deux chiffres.

## 2026-11-15 — Revue des modèles : LGD, remboursement, actualisation, probation

Suite de la revue critique : après les corrections de calcul (D-043 à D-046),
les limites de modèle. Chaque point est testé sur les données avant d'être
retenu ou écarté, et les essais non retenus sont publiés.

### D-047 LGD selon le ratio prêt / valeur réévalué

**Remplace les variables de D-028.** La LGD de D-028 prévoyait 7,6 % sur les
défauts de 2006-2010 pour 29,5 % réalisés. Ses variables (LTV d'octroi, ratio
de capital restant) ne portent aucune information sur les prix.

- **Variable nouvelle** : la CLTV réévaluée à la date du défaut, soit CLTV
  d'octroi × capital restant / capital initial × prix à l'octroi / prix au
  défaut, avec l'indice FHFA de l'État du bien et ses délais de publication
  (D-041), à défaut l'indice national. Elle remplace la LTV d'octroi et le
  ratio de capital, dont elle est le produit corrigé des prix.
- **Variables retenues** : CLTV réévaluée, score à l'octroi, taux d'assurance
  hypothécaire, âge du prêt au défaut. Mêmes deux étapes, même échantillon
  d'entraînement (défauts jusqu'à fin 2005) que D-028.
- **Pour un prêt actif**, la LGD est celle qu'il aurait s'il faisait défaut à
  l'arrêté : CLTV réévaluée aux prix connus à l'arrêté. **Dans un scénario**,
  la CLTV est réévaluée au niveau de prix atteint après 12 mois de la
  trajectoire (D-034) : les scénarios agissent désormais sur la LGD par les
  prix, dans le résultat principal, puisque ce lien est estimé sur les
  données du projet et non emprunté à une étude extérieure.

Résultat (`rapport/resultats/lgd_specifications.csv`) : LGD prévue de 21,9 %
sur le test pour 29,5 % réalisés ; régularisations prévues 36 % (réalisées
42 %), sévérité prévue 31 % (réalisée 55 %). Par année de défaut, la LGD
prévue passe de 10 % (2007) à 25 % (2010), pour 32 % et 26 % réalisés : elle
suit les prix avec retard.

**Réserve de méthode.** Six jeux de variables ont été comparés sur la période
de test avant ce choix, ce qui est une forme de sélection sur le test. Le jeu
retenu l'a été pour sa logique (une seule variable de prix, pas de doublon
avec ses composantes) et non pour son score : la variante « D-028 + CLTV
réévaluée » fait un peu mieux (23,7 %) mais inverse le signe de la LTV
d'octroi. Ajouter la variation annuelle des prix ou du chômage dégrade la
prévision (15,8 % et 10,6 %) : comme pour la survie (D-026), leurs
coefficients appris sur 2000-2005 ont le mauvais signe. Tous les essais sont
publiés.

### D-048 Remboursement anticipé et retard de paiement : essai non retenu

D-045 attribuait les ancrages impossibles à un modèle de remboursement qui
ignore le retard de paiement. Essai : un écart de logit pour les prêts ayant
au moins une mensualité de retard le mois précédent, estimé par maximum de
vraisemblance sur l'entraînement, le hasard du modèle servant de terme fixe.

Résultat (`rapport/resultats/remboursement_retard.csv`) : l'écart estimé vaut
+0,02, c'est-à-dire rien. Sur 2000-2005, un prêt en retard se remboursait
autant qu'un autre (135 remboursements observés pour 133 attendus). Sur
2006-2010, les prêts en retard se sont remboursés dix fois moins que prévu
(129 pour 1 356), mais cette information n'existe pas avant la crise.
**L'effet n'est pas appliqué** ; il est estimé et publié par l'étape 4 bis.
La borne de D-045 reste donc utile.

### D-049 Actualisation du recouvrement

**Complète D-006 et D-043.** La LGD était une perte nominale. En cas de
perte, le recouvrement n'est encaissé qu'à la résolution du défaut :

`LGD actualisée = (1 − P(régularisation)) × [1 − (1 − sévérité) × (1 + r/12)^(−d)]`

- `r` : taux du prêt (taux courant pour un prêt actif, taux d'octroi en
  stade 3) ;
- `d` : délai médian entre le défaut et la perte sur l'échantillon
  d'entraînement, soit 14 mois ; en stade 3, diminué des mois déjà passés en
  défaut, avec un plancher à zéro ;
- une régularisation ne coûte rien.

Limites : un seul délai pour tous les prêts, mesuré avant la crise et sur des
résolutions observées jusqu'à fin 2006 seulement, donc trop court ; pas
d'intérêts courus. `actual_loss` de Freddie Mac inclut déjà les frais et les
intérêts de retard, pas la valeur temps. La LGD réalisée du backtest reste
nominale.

### D-050 Probation avant le retour en stade 1

**Complète D-003.** Un prêt reste en stade 2 tant qu'il a eu au moins une
mensualité de retard à l'un des 3 derniers mois, arrêté compris
(`PROBATION_STADE2_MOIS = 3`). Auparavant, seul le retard du mois de l'arrêté
comptait. Le critère de dégradation de la PD est inchangé.

Effet : la part de l'encours en stade 2 passe de 1,5 % à 2,3 % au 31/12/2007
et de 10,1 % à 11,5 % au 31/12/2009 (modèle LightGBM).

### D-051 Prêts régularisés après un défaut : limite de périmètre

Constat fait pendant cette revue. Le panneau s'arrête au premier défaut
(D-001) ; un prêt en défaut est en stade 3 jusqu'à sa sortie ou jusqu'à son
retour sous 3 mensualités de retard (D-027). Après ce retour, il n'est plus
dans le portefeuille provisionné, alors qu'il porte encore un encours :
30 M$ fin 2007 (0,2 % de l'encours), 130 M$ fin 2008 (0,6 %), 367 M$ fin 2009
(2,1 %), 897 M$ fin 2010 (7,4 %).

Non corrigé : aucun modèle du projet n'est estimé sur des prêts déjà passés
par le défaut, et leur appliquer la PD des prêts sains serait une hypothèse
sans support. Les pertes du backtest sont comptées au premier défaut, sur
le même périmètre : provisions et pertes restent comparables. La limite est
publiée dans la note.

### Effet d'ensemble de D-047, D-049 et D-050

Provision au 31/12/2007 : 12,7 M$ (logistique) et 19,0 M$ (LightGBM), contre
7,1 et 10,5 M$ avant cette revue ; elle est multipliée par 1,6 à 3,4 selon
l'arrêté. Couverture des pertes chiffrées sur le même horizon : 9 à 13 % au
31/12/2007 (5 à 8 % avant), 53 à 59 % au 31/12/2009, 76 à 82 % au 31/12/2010.
L'écart LightGBM / logistique change peu : + 49 % au 31/12/2007 (+ 47 %
avant), + 25 % avec la coupure stricte de D-046. Les provisions d'avant cette
revue restent publiées dans
`rapport/resultats/trimestriel_figee_avant_revue_modeles.csv`.

## 2026-11-15 — Points restés ouverts : sévérité de la LGD, prêts régularisés

### D-052 Sévérité selon le ratio prêt / valeur : essai non retenu

Après D-047, la sévérité des pertes reste sous-estimée de moitié (31 %
prévue, 55 % réalisée). Essai : une forme structurelle, où la sévérité croît
avec la part du capital non couverte par la valeur du bien,
`a + b × (1 − 100 / CLTV réévaluée) − c × assurance`, ajustée sur les pertes
d'avant 2006.

Résultat : rien à apprendre. Sur l'entraînement, la sévérité ne croît pas
avec la CLTV réévaluée, elle baisse (31 % sous 70, 14 % entre 90 et 100),
parce que les prêts à forte LTV sont assurés ; aucune perte n'y a de CLTV
réévaluée supérieure à 100. Sur la crise, la sévérité vaut 50 à 60 % dans
**toutes** les tranches, y compris sous 70
(`rapport/resultats/lgd_severite_par_cltv.csv`). L'écart est un changement de
niveau commun à tous les prêts, pas un effet de la CLTV : la forme
structurelle prévoit 31 % sur le test, comme la régression de D-047. La
sévérité de D-047 est conservée et la limite reste publiée.

### D-053 Prêts régularisés après un défaut : remis au bilan

**Corrige la limite constatée en D-051.** Un prêt sorti de son premier défaut
et encore au bilan à l'arrêté est désormais provisionné :

- **hors défaut à l'arrêté** : stade 2, perte attendue sur la durée de vie
  restante ;
- **de nouveau en défaut** : stade 3, LGD actualisée × capital à l'arrêté,
  avec le délai de résolution entier (D-049).

Pour le stade 2, les modèles de PD et de survie ne s'appliquent pas : ils
sont estimés sur des prêts jamais passés par le défaut. Une **table
d'expérience** les remplace (`src/ecl9/regularises.py`) : hasards mensuels de
nouveau défaut et de remboursement selon le nombre de mois écoulés depuis la
régularisation, par bandes (1-3, 4-6, 7-12, 13-24, 25 et plus), estimés sur
les prêts régularisés des millésimes 2000-2005 jusqu'à fin 2005. Le hasard de
nouveau défaut va de 9,6 % par mois les trois premiers mois à 1,5 % après
deux ans (`rapport/resultats/regularises_table.csv`). La LGD est celle de
D-047 et D-049, à la CLTV de l'arrêté.

Ces provisions sont identiques pour les deux modèles de PD et dans tous les
scénarios, comme le stade 3. Les colonnes `dont_regularises_*` des résultats
trimestriels les isolent. Pertes du backtest : la perte finale du prêt
(D-027), chiffrée ou estimée (D-044).

Contrôle hors période (`rapport/resultats/regularises_test.csv`) : sur
2006-2010, la table prévoit 2 783 nouveaux défauts pour 2 795 observés ; elle
en prévoit trop peu en 2008-2009 (985 pour 1 364) et trop en 2010 (1 733 pour
1 366). Elle prévoit en revanche huit fois trop de remboursements (600 pour
73), comme le modèle de remboursement des prêts sains.

Effet : au 31/12/2007, 177 prêts et 30 M$ d'encours ajoutés, 2,4 M$ de
provision ; au 31/12/2010, 4 428 prêts, 897 M$ d'encours (6,9 % du total) et
148 M$ de provision. La provision totale au 31/12/2007 devient 15,1 M$
(logistique) et 21,4 M$ (LightGBM). L'écart absolu entre les deux modèles
est inchangé (6,2 M$) ; l'écart **relatif** baisse mécaniquement, de + 49 % à
+ 41 %, puisqu'une provision commune s'ajoute aux deux (+ 21 % avec la
coupure stricte de D-046). Couverture des pertes chiffrées : 10 à 14 % au
31/12/2007, 88 à 93 % au 31/12/2010.

L'intervalle de D-042 est recalculé avec ces changements.

Recalcul de D-042 (100 tirages, même graine) : au 31/12/2007, écart médian
+ 41 %, intervalle à 95 % de + 24 % à + 64 % ; au 31/12/2008, + 23 % à
+ 39 %. LightGBM provisionne plus que la logistique dans les 100 tirages.
L'intervalle publié avant cette revue (+ 27 % à + 80 %) portait sur des
provisions sans prêts régularisés ni nouvelle LGD. L'écart de la coupure
stricte (+ 21 %, D-046) reste sous la borne basse.

## 2026-11-15 — Deuxième revue : ancrage des scénarios, fenêtre du backtest, contrôles

Une seconde relecture critique, après le commit `219dbb4`, relève trois
points de calcul. Chacun est vérifié dans le code avant d'être traité.

### D-054 Ancrage au remboursement central dans les scénarios

**Corrige l'application de D-036 au remboursement (D-040).** Dans un
scénario, `moteur.provisions` recevait le remboursement du scénario et s'en
servait aussi pour l'ancrage : la PD à 12 mois était ramenée à la cible sous
le remboursement du scénario, ce qui gommait son effet sur les 12 premiers
mois. C'est le défaut que D-036 avait corrigé pour les écarts de logit, resté
pour le remboursement.

`provisions` accepte désormais `hasards_rembt_ancrage`. Dans un scénario,
l'ancrage se fait avec le remboursement central (macro figée), puis l'écart
de logit et le remboursement du scénario s'appliquent. Hors scénario, rien ne
change : le résultat principal, le double calcul R et les bootstraps sont
identiques. Un test compare les deux ordres et vérifie à la main la PD à
12 mois d'un scénario.

Effet : au 31/12/2007, le scénario défavorable ajoute + 20 % à la provision
au lieu de + 25 % (la baisse des taux y accroît les remboursements, ce qui
réduit maintenant aussi la PD à 12 mois) ; l'effet pondéré va de − 30 % à
+ 15 % selon l'arrêté (− 29 % à + 16 % avant).

### D-055 Pertes du backtest : défauts postérieurs à 2010

**Corrige l'application de D-032.** D-032 compte, pour un prêt en stade 2,
les défauts « jusqu'à la fin des données », et pour une génération les pertes
« jusqu'en juin 2026 ». Or l'étape 5 ne conservait que les défauts survenus
de 2006 à 2010 (fenêtre de validation de la LGD, D-028), et l'étape 7 lisait
ce fichier : les 8 029 premiers défauts postérieurs à 2010 des millésimes de
test n'entraient dans aucune perte constatée. Trois conséquences :

- les pertes à maturité (stade 2, générations) étaient tronquées à 2010 ;
- pour un arrêté de 2010, la fenêtre de 12 mois du stade 1 était amputée :
  au 31/12/2010, les pertes constatées du stade 1 valaient zéro ;
- la couverture de fin de période était donc surestimée.

Tous les défauts des millésimes de test sont désormais conservés
(`echantillon = test_apres_2010` pour ceux d'après 2010) et lus par le
backtest. La validation de la LGD garde sa fenêtre 2006-2010.

Effet : pertes par génération de 296, 309 et 147 M$ pour 2006, 2007 et 2008
(220, 226 et 96 M$ avant) ; au 31/12/2010, pertes constatées de 602 M$ au lieu
de 462 M$, et couverture de 68 à 71 % au lieu de 88 à 93 %. Au 31/12/2007, la
couverture passe de 10-14 % à 9,8-13,9 %. Les provisions ne changent pas.

Le suivi reste censuré en juin 2026 : pour des prêts à 30 ans octroyés en
2006-2008, les pertes « à maturité » couvrent 18 à 20 ans d'observation, pas
toute la durée contractuelle. La note le dit.

### D-056 Contrôles ajoutés

- **Frontières des bandes des prêts régularisés (D-053)** : la relecture
  soupçonnait un décalage d'un mois. Vérification faite, il n'y en a pas : la
  table est indexée par le nombre de mois hors défaut au début de la
  transition, mois courant compris, et la projection suit la même convention
  (un prêt hors défaut depuis 3 mois à l'arrêté est encore dans la bande 1-3
  pour le mois suivant). Un test l'établit sur un cas à la main, de
  l'estimation à la projection.
- **LGD sur une période indépendante du choix des variables (D-047)** : les
  défauts de 2011 et après n'ont pas servi à comparer les jeux de variables.
  Sur ces 7 622 défauts résolus, la LGD prévue est de 28,2 % pour 20,5 %
  réalisés : proche en 2011 (28 % prévus, 26 % réalisés), puis trop haute à
  mesure que les régularisations remontent (29 % pour 18 % en 2013). La LGD
  de D-047 n'est donc pas biaisée vers le bas par construction ; elle suit
  mal les changements de régime, dans les deux sens
  (`rapport/resultats/lgd_apres_2010_par_annee_defaut.csv`).
- **Remboursement anticipé par année et par millésime**
  (`rapport/resultats/remboursement_par_cohorte.csv`) : la surestimation
  touche tous les millésimes de test et culmine en 2008-2009.
- **Tests du bootstrap** (`tests/test_bootstrap.py`) : intervalle nul quand
  l'écart est proportionnel prêt par prêt, reproductibilité à graine donnée,
  largeur qui diminue de moitié quand le portefeuille quadruple.
