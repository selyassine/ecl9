# Note de provisionnement

`note.qmd` est rendue par Quarto et publiée sur GitHub Pages
(<https://selyassine.github.io/ecl9/>) par le workflow `note.yml`. Elle ne lit
que les résultats versionnés de `resultats/`, jamais les données Freddie Mac.

Rendu local :

```bash
pip install -e ".[rapport]"
cd rapport && quarto render note.qmd   # rapport/note.html
```
