"""ecl9 : moteur de pertes de crédit attendues (ECL) IFRS 9.

Modules :

- ``donnees``      lecture des fichiers Freddie Mac et construction du panneau prêt-mois
- ``definitions``  définitions figées (défaut, stades, horizons), miroir de docs/decisions.md
- ``staging``      affectation des stades 1, 2 et 3
- ``pd``           PD à 12 mois (logistique, LightGBM) et PD à maturité (survie discrète)
- ``lgd``          LGD en deux étapes (régularisation puis sévérité)
- ``ead``          exposition au défaut selon l'amortissement contractuel
- ``scenarios``    scénarios macro prospectifs pondérés
- ``ecl``          formule centrale de perte attendue
"""

__version__ = "0.1.0"
