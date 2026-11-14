.PHONY: installer donnees verifier panneau exploration pd12 survie lgd moteur trimestriel double-calcul sensibilites pipeline note tests lint

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

lgd: panneau
	python pipeline/etape_05_lgd.py

moteur: pd12 survie lgd
	python pipeline/etape_06_moteur.py

trimestriel: moteur
	python pipeline/etape_07_trimestriel.py
	python pipeline/etape_07_trimestriel.py --trajectoire scenarios

double-calcul: moteur
	python pipeline/etape_08_double_calcul_r.py

sensibilites: trimestriel
	python pipeline/etape_09_sensibilites.py

pipeline: exploration sensibilites double-calcul

note:
	cd rapport && quarto render note.qmd --output index.html

tests:
	pytest -m "not donnees"

lint:
	ruff check .
	ruff format --check .
