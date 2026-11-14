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
