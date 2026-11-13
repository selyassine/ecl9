# Données

Rien de ce dossier n'est versionné, sauf ce README, `manifeste.toml` et
`manifeste.lock.json`.

## Téléchargement

**FRED** (sans compte) :

```bash
ecl9-telecharger --fred
```

**Freddie Mac** : le jeu est servi par le portail Clarity, derrière une
connexion dans le navigateur, donc à la main.

1. Crée un compte gratuit Clarity Data Intelligence et connecte-toi sur
   https://claritydownload.fmapps.freddiemac.com/CRT/ (lien « Access Historical
   Data » de https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset).
2. Dans les *sample files*, télécharge `sample_2000.zip` à `sample_2008.zip`.
3. Dépose-les dans `data/brut/freddie/`, puis lance :

   ```bash
   ecl9-telecharger --freddie   # décompresse et consigne les empreintes
   ecl9-telecharger --verifier  # contrôle les empreintes sans rien télécharger
   ```

## Arborescence produite

```
data/
├── brut/
│   ├── freddie/   sample_AAAA.zip, sample_orig_AAAA.txt, sample_perf_AAAA.txt
│   └── fred/      UNRATE.csv, CSUSHPISA.csv, MORTGAGE30US.csv, DGS10.csv
└── intermediaire/ panneau prêt-mois au format Parquet (pipeline)
```
