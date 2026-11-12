# Données

Rien de ce dossier n'est versionné, sauf ce README, `manifeste.toml` et
`manifeste.lock.json`.

## Téléchargement

1. Crée un compte gratuit sur le portail Freddie Mac
   (https://freddiemac.embs.com/FLoan/) et accepte les conditions d'utilisation.
2. Exporte tes identifiants dans le terminal (jamais dans un fichier versionné) :

   ```bash
   export FREDDIE_USER="ton.email@exemple.com"
   export FREDDIE_PASSWORD="..."
   ```

3. Lance :

   ```bash
   ecl9-telecharger            # Freddie Mac + FRED
   ecl9-telecharger --fred     # FRED seulement, sans compte
   ecl9-telecharger --verifier # contrôle les empreintes sans rien télécharger
   ```

Si la connexion automatique échoue (le portail change parfois), télécharge à
la main les archives `sample_AAAA.zip` dans `data/brut/freddie/`, puis relance
`ecl9-telecharger` : il décompresse ce qui est présent et enregistre les
empreintes.

## Arborescence produite

```
data/
├── brut/
│   ├── freddie/   sample_AAAA.zip, sample_orig_AAAA.txt, sample_svcg_AAAA.txt
│   └── fred/      UNRATE.csv, CSUSHPISA.csv, MORTGAGE30US.csv, DGS10.csv
└── intermediaire/ panneau prêt-mois au format Parquet (pipeline)
```
