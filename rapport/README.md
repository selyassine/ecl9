# Note de provisionnement

`note.qmd` est rendue par Quarto et publiée sur GitHub Pages
(<https://selyassine.github.io/ecl9/>) par le workflow `note.yml`. Elle ne lit
que les résultats versionnés de `resultats/`, jamais les données Freddie Mac.

Le tableau de bord interactif (<https://selyassine.github.io/ecl9/tableau.html>)
est une page autonome construite par `tableau_de_bord.py` à partir du modèle
`tableau_modele.html` et des mêmes résultats versionnés, sans serveur ni
bibliothèque externe : `python rapport/tableau_de_bord.py` écrit
`rapport/tableau.html`.

Rendu local :

```bash
pip install -e ".[rapport]"
cd rapport && quarto render note.qmd   # rapport/note.html
```
