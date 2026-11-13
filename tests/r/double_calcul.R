# Double calcul indépendant de la provision IFRS 9 (D-033).
#
# Usage : Rscript tests/r/double_calcul.R entrees.csv sorties.csv
#
# Entrées, une ligne par prêt : id, stade, crd, taux (décimal), restants (mois),
# lgd, pd12, puis h_1 ... h_N, les hasards mensuels NON ancrés.
# Sortie : id, ecl.
#
# Seule la formule de docs/decisions.md est partagée avec le code Python
# (D-005 à D-008, D-024) ; aucune ligne n'en est reprise.

args <- commandArgs(trailingOnly = TRUE)
entrees <- read.csv(args[1])
colonnes_h <- grep("^h_", names(entrees), value = TRUE)
H <- as.matrix(entrees[, colonnes_h])

pd_cumulee <- function(h) 1 - prod(1 - h)

# Facteur c tel que la PD cumulée des k premiers mois, hasards × c plafonnés
# à 1, égale la cible. Dichotomie jusqu'à la précision machine.
ancrer <- function(h, cible, k) {
  if (cible == 0) { h[seq_len(k)] <- 0; return(h) }
  tete <- h[seq_len(k)]
  f <- function(c) pd_cumulee(pmin(c * tete, 1)) - cible
  bas <- 0; haut <- 1
  while (f(haut) < 0) haut <- 2 * haut
  for (i in 1:200) {
    milieu <- (bas + haut) / 2
    if (f(milieu) < 0) bas <- milieu else haut <- milieu
  }
  h[seq_len(k)] <- pmin(haut * tete, 1)
  h
}

# Capital restant dû au début de chaque mois, annuité constante.
crd_debut_mois <- function(capital, taux, n) {
  i <- taux / 12
  if (i == 0) return(capital - (capital / n) * (0:(n - 1)))
  mensualite <- capital * i / (1 - (1 + i)^(-n))
  solde <- numeric(n)
  solde[1] <- capital
  if (n > 1) for (t in 2:n) solde[t] <- solde[t - 1] * (1 + i) - mensualite
  pmax(solde, 0)
}

ecl <- numeric(nrow(entrees))
for (p in seq_len(nrow(entrees))) {
  e <- entrees[p, ]
  n <- e$restants
  if (e$stade == 3) { ecl[p] <- e$lgd * e$crd; next }
  horizon <- if (e$stade == 1) min(12, n) else n
  h <- ancrer(H[p, ], e$pd12, min(12, n))[seq_len(horizon)]
  survie_avant <- c(1, cumprod(1 - h))[seq_len(horizon)]
  marginale <- survie_avant * h
  ead <- crd_debut_mois(e$crd, e$taux, n)[seq_len(horizon)]
  actualisation <- (1 + e$taux / 12)^(-(seq_len(horizon)))
  ecl[p] <- e$lgd * sum(marginale * ead * actualisation)
}

write.csv(data.frame(id = entrees$id, ecl = ecl), args[2], row.names = FALSE)
