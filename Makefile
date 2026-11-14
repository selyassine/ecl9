.PHONY: installer donnees verifier panneau exploration pd12 survie remboursement lgd moteur trimestriel double-calcul sensibilites bootstrap-modeles coupure-stricte pipeline note tests lint

installer:
	pip install -e ".[dev,eda,rapport]"

donnees:
	ecl9-telecharger

verifier:
	ecl9-telecharger --verifier

panneau: verifier
	python pipeline/etape_01_panneau.py

exploration: panneau
	python pipeline/etape_02_exploration.py

pd12: panneau
	python pipeline/etape_03_pd12.py

survie: panneau
	python pipeline/etape_04_survie.py

remboursement: panneau
	python pipeline/etape_04b_remboursement.py

lgd: panneau
	python pipeline/etape_05_lgd.py

moteur: pd12 survie remboursement lgd
	python pipeline/etape_06_moteur.py

trimestriel: moteur
	python pipeline/etape_07_trimestriel.py
	python pipeline/etape_07_trimestriel.py --trajectoire scenarios
	python pipeline/etape_07_trimestriel.py --sans-remboursement
	python pipeline/etape_07_trimestriel.py --trajectoire scenarios --sans-remboursement

double-calcul: moteur
	python pipeline/etape_08_double_calcul_r.py

sensibilites: trimestriel
	python pipeline/etape_09_sensibilites.py
	python pipeline/etape_09_sensibilites.py --sans-remboursement

bootstrap-modeles: trimestriel
	python pipeline/etape_10_bootstrap_modeles.py

coupure-stricte: trimestriel
	python pipeline/etape_11_coupure_stricte.py

pipeline: exploration sensibilites double-calcul bootstrap-modeles coupure-stricte

note:
	cd rapport && quarto render note.qmd

tests:
	pytest -m "not donnees"

lint:
	ruff check .
	ruff format --check .
