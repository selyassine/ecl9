"""Tests du téléchargement sans réseau : archives déposées à la main."""

import shutil
import zipfile
from pathlib import Path

import pytest

from ecl9 import telechargement as t

MANIFESTE = Path(__file__).parents[1] / "data" / "manifeste.toml"


@pytest.fixture
def dossier(tmp_path):
    shutil.copy(MANIFESTE, tmp_path / "manifeste.toml")
    return tmp_path


def _deposer_archive(dossier: Path, annee: int) -> Path:
    cible = dossier / "brut" / "freddie"
    cible.mkdir(parents=True, exist_ok=True)
    archive = cible / f"sample_{annee}.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(f"sample_orig_{annee}.txt", "750|200001|N\n")
        z.writestr(f"sample_svcg_{annee}.txt", "F100Q1000001|200002|100000|0\n")
    return archive


def test_manifeste_couvre_les_annees_du_decoupage():
    from ecl9.definitions import ANNEES_ENTRAINEMENT, ANNEES_TEST, SERIES_FRED

    m = t.lire_manifeste(MANIFESTE.parent)
    assert set(ANNEES_ENTRAINEMENT) | set(ANNEES_TEST) <= set(m["freddie_mac"]["annees"])
    assert tuple(m["fred"]["series"]) == SERIES_FRED


def test_archives_deposees_a_la_main(dossier):
    m = t.lire_manifeste(dossier)
    m["freddie_mac"]["annees"] = [2005]
    _deposer_archive(dossier, 2005)
    verrou = t.lire_verrou(dossier)

    t.obtenir_freddie(m, verrou, dossier)  # archive déposée à la main
    t.ecrire_verrou(verrou, dossier)

    assert set(t.lire_verrou(dossier)["fichiers"]) == {
        "brut/freddie/sample_2005.zip",
        "brut/freddie/sample_orig_2005.txt",
        "brut/freddie/sample_svcg_2005.txt",
    }
    assert t.verifier(dossier) == []


def test_fichier_modifie_detecte(dossier):
    m = t.lire_manifeste(dossier)
    m["freddie_mac"]["annees"] = [2006]
    _deposer_archive(dossier, 2006)
    verrou = t.lire_verrou(dossier)
    t.obtenir_freddie(m, verrou, dossier)
    t.ecrire_verrou(verrou, dossier)

    (dossier / "brut/freddie/sample_orig_2006.txt").write_text("altéré\n")
    assert t.verifier(dossier) == ["modifié : brut/freddie/sample_orig_2006.txt"]
    with pytest.raises(t.ErreurTelechargement, match="empreinte différente"):
        t.consigner(dossier / "brut/freddie/sample_orig_2006.txt", "x", verrou, dossier)


def test_archives_absentes(dossier):
    m = t.lire_manifeste(dossier)
    with pytest.raises(t.ErreurTelechargement, match="claritydownload"):
        t.obtenir_freddie(m, t.lire_verrou(dossier), dossier)


def test_archive_avec_chemin_suspect_refusee(tmp_path):
    archive = tmp_path / "sample_2000.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../evasion.txt", "x")
    with pytest.raises(t.ErreurTelechargement, match="chemin inattendu"):
        t.decompresser(archive)
