.PHONY: installer donnees verifier panneau exploration tests lint

installer:
	pip install -e ".[dev,eda]"

donnees:
	ecl9-telecharger

verifier:
	ecl9-telecharger --verifier

panneau: verifier
	python pipeline/etape_01_panneau.py

exploration: panneau
	python pipeline/etape_02_exploration.py

tests:
	pytest -m "not donnees"

lint:
	ruff check .
	ruff format --check .
