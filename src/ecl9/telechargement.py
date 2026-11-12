"""Téléchargement des données décrites dans ``data/manifeste.toml``.

Les identifiants Freddie Mac sont lus dans les variables d'environnement
``FREDDIE_USER`` et ``FREDDIE_PASSWORD`` et ne sont jamais écrits sur disque.
Chaque fichier obtenu est consigné avec son empreinte SHA-256 dans
``data/manifeste.lock.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_DONNEES = RACINE / "data"
NOM_VERROU = "manifeste.lock.json"
DELAI = 120  # secondes
TAILLE_BLOC = 1 << 20


class ErreurTelechargement(RuntimeError):
    """Échec de connexion ou de téléchargement."""


def lire_manifeste(dossier: Path = DOSSIER_DONNEES) -> dict:
    with open(dossier / "manifeste.toml", "rb") as f:
        return tomllib.load(f)


def sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(TAILLE_BLOC), b""):
            h.update(bloc)
    return h.hexdigest()


def lire_verrou(dossier: Path = DOSSIER_DONNEES) -> dict:
    chemin = dossier / NOM_VERROU
    if not chemin.exists():
        return {"fichiers": {}}
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecrire_verrou(verrou: dict, dossier: Path = DOSSIER_DONNEES) -> None:
    verrou["fichiers"] = dict(sorted(verrou["fichiers"].items()))
    texte = json.dumps(verrou, indent=2, ensure_ascii=False) + "\n"
    (dossier / NOM_VERROU).write_text(texte, encoding="utf-8")


def consigner(chemin: Path, source: str, verrou: dict, dossier: Path = DOSSIER_DONNEES) -> None:
    """Ajoute un fichier au verrou. Refuse si l'empreinte a changé."""
    cle = chemin.relative_to(dossier).as_posix()
    empreinte = sha256(chemin)
    ancien = verrou["fichiers"].get(cle)
    if ancien and ancien["sha256"] != empreinte:
        raise ErreurTelechargement(
            f"{cle} : empreinte différente de celle du verrou "
            f"({empreinte[:12]}… au lieu de {ancien['sha256'][:12]}…). "
            "Si la source a été mise à jour, supprime l'entrée du verrou "
            "et note le changement dans docs/decisions.md."
        )
    verrou["fichiers"][cle] = {
        "sha256": empreinte,
        "octets": chemin.stat().st_size,
        "source": source,
        "obtenu_le": ancien["obtenu_le"] if ancien else datetime.now(UTC).date().isoformat(),
    }


def verifier(dossier: Path = DOSSIER_DONNEES) -> list[str]:
    """Renvoie la liste des problèmes (fichier absent ou modifié)."""
    problemes = []
    for cle, info in lire_verrou(dossier)["fichiers"].items():
        chemin = dossier / cle
        if not chemin.exists():
            problemes.append(f"absent : {cle}")
        elif sha256(chemin) != info["sha256"]:
            problemes.append(f"modifié : {cle}")
    return problemes


def _telecharger(session: requests.Session, url: str, cible: Path) -> None:
    cible.parent.mkdir(parents=True, exist_ok=True)
    temporaire = cible.with_suffix(cible.suffix + ".partiel")
    with session.get(url, stream=True, timeout=DELAI) as r:
        r.raise_for_status()
        type_contenu = r.headers.get("Content-Type", "")
        if "text/html" in type_contenu:
            raise ErreurTelechargement(
                f"{url} a renvoyé une page HTML au lieu d'un fichier : "
                "connexion refusée ou conditions d'utilisation non acceptées."
            )
        with open(temporaire, "wb") as f:
            for bloc in r.iter_content(TAILLE_BLOC):
                f.write(bloc)
    temporaire.replace(cible)


def connexion_freddie(conf: dict) -> requests.Session:
    utilisateur = os.environ.get("FREDDIE_USER")
    mot_de_passe = os.environ.get("FREDDIE_PASSWORD")
    if not utilisateur or not mot_de_passe:
        raise ErreurTelechargement(
            "Définis FREDDIE_USER et FREDDIE_PASSWORD (voir data/README.md), "
            "ou dépose les archives à la main dans data/brut/freddie/."
        )
    session = requests.Session()
    r = session.post(
        conf["connexion"],
        data={"username": utilisateur, "password": mot_de_passe},
        timeout=DELAI,
    )
    r.raise_for_status()
    r = session.post(
        conf["acceptation"],
        data={"accept": "Yes", "action": "acceptTandC", "acceptSubmit": "Continue"},
        timeout=DELAI,
    )
    r.raise_for_status()
    return session


def decompresser(archive: Path) -> list[Path]:
    with zipfile.ZipFile(archive) as z:
        noms = [n for n in z.namelist() if not n.endswith("/")]
        for nom in noms:
            if Path(nom).name != nom:
                raise ErreurTelechargement(f"{archive.name} : chemin inattendu {nom!r}")
        z.extractall(archive.parent, members=noms)
    return [archive.parent / n for n in noms]


def obtenir_freddie(manifeste: dict, verrou: dict, dossier: Path = DOSSIER_DONNEES) -> None:
    conf = manifeste["freddie_mac"]
    cible_dossier = dossier / conf["dossier"]
    manquantes = [a for a in conf["annees"] if not (cible_dossier / f"sample_{a}.zip").exists()]
    session = connexion_freddie(conf) if manquantes else None
    for annee in conf["annees"]:
        archive = cible_dossier / f"sample_{annee}.zip"
        url = conf["url_modele"].format(annee=annee)
        if not archive.exists():
            print(f"Freddie Mac {annee} : téléchargement…")
            _telecharger(session, url, archive)
        consigner(archive, url, verrou, dossier)
        for fichier in decompresser(archive):
            consigner(fichier, f"{archive.name}!{fichier.name}", verrou, dossier)
        print(f"Freddie Mac {annee} : prêt.")


def obtenir_fred(manifeste: dict, verrou: dict, dossier: Path = DOSSIER_DONNEES) -> None:
    """Les séries FRED sont révisées : un fichier déjà présent n'est pas retéléchargé."""
    conf = manifeste["fred"]
    session = requests.Session()
    for serie in conf["series"]:
        cible = dossier / conf["dossier"] / f"{serie}.csv"
        url = conf["url_modele"].format(serie=serie)
        if not cible.exists():
            print(f"FRED {serie} : téléchargement…")
            _telecharger(session, url, cible)
        consigner(cible, url, verrou, dossier)
        print(f"FRED {serie} : prêt.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    groupe = parser.add_mutually_exclusive_group()
    groupe.add_argument("--fred", action="store_true", help="FRED seulement")
    groupe.add_argument("--freddie", action="store_true", help="Freddie Mac seulement")
    groupe.add_argument("--verifier", action="store_true", help="contrôler les empreintes")
    args = parser.parse_args(argv)

    if args.verifier:
        problemes = verifier()
        for p in problemes:
            print(p)
        print("Données conformes au verrou." if not problemes else f"{len(problemes)} problème(s).")
        return 1 if problemes else 0

    manifeste = lire_manifeste()
    verrou = lire_verrou()
    verrou["manifeste_sha256"] = sha256(DOSSIER_DONNEES / "manifeste.toml")
    try:
        if not args.freddie:
            obtenir_fred(manifeste, verrou)
        if not args.fred:
            obtenir_freddie(manifeste, verrou)
    except (ErreurTelechargement, requests.RequestException) as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1
    finally:
        ecrire_verrou(verrou)
    print(f"Empreintes consignées dans data/{NOM_VERROU}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
