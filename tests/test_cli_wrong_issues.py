from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from felvi_games.cli import app
from felvi_games.db import FeladatRepository
from felvi_games.models import Ertekeles, Feladat

runner = CliRunner()


def _seed_issue_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_wrong_issues.db"
    repo = FeladatRepository(db_path=db_path)

    feladat = Feladat.from_dict(
        {
            "id": "mag4_issue_1",
            "neh": 1,
            "szint": "4 osztályos",
            "kerdes": "Teszt kérdés?",
            "helyes_valasz": "jó válasz",
            "hint": "tipp",
            "magyarazat": "magyarázat",
            "feladat_tipus": "nyilt_valasz",
            "max_pont": 1,
        },
        targy="magyar",
    )
    repo.upsert(feladat)

    repo.save_megoldas(
        feladat,
        "ez hibás feladat",
        Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
        felhasznalo_nev="Lóri",
        hibajelezes=True,
    )
    repo.save_megoldas(
        feladat,
        "másik hibás válasz",
        Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
        felhasznalo_nev="Lóri",
        hibajelezes=False,
    )

    return db_path


def test_wrong_issues_lists_flagged_and_keyword_counts(tmp_path: Path) -> None:
    db_path = _seed_issue_db(tmp_path)

    result = runner.invoke(app, ["wrong-issues", "--db", str(db_path), "--user", "Lóri"])

    assert result.exit_code == 0
    assert "Felhasználó által hibásnak jelölve" in result.output
    assert "mag4_issue_1" in result.output
    assert "jelölések: 1" in result.output
    assert "Összes érintett próbálkozás: 2" in result.output
    assert "Érintett feladatok száma: 1" in result.output


def test_wrong_issues_contains_filter_changes_counts(tmp_path: Path) -> None:
    db_path = _seed_issue_db(tmp_path)

    result = runner.invoke(
        app,
        ["wrong-issues", "--db", str(db_path), "--user", "Lóri", "--contains", "másik"],
    )

    assert result.exit_code == 0
    assert "Összes érintett próbálkozás: 1" in result.output
    assert "Érintett feladatok száma: 1" in result.output


def test_wrong_issues_writes_ids_dat_file(tmp_path: Path) -> None:
    db_path = _seed_issue_db(tmp_path)
    out_dat = tmp_path / "issue_task_ids.dat"

    result = runner.invoke(
        app,
        [
            "wrong-issues",
            "--db",
            str(db_path),
            "--user",
            "Lóri",
            "--ids-dat",
            str(out_dat),
        ],
    )

    assert result.exit_code == 0
    assert out_dat.exists()
    assert out_dat.read_text(encoding="utf-8") == "mag4_issue_1\n"
    assert "ID-k kiírva" in result.output
