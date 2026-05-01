"""CLI tests for `felvi review` command.

Tests invoke the command via typer's CliRunner so no subprocess is spawned.
The service layer (run_feladat_review) is mocked to keep tests fast and
side-effect-free per swe.md CLI-First Testing rules.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from felvi_games.cli import app
from felvi_games.models import Feladat
from felvi_games.review import ReviewResult

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def feladat() -> Feladat:
    return Feladat.from_dict(
        {
            "id": "m_cli_01",
            "neh": 2,
            "szint": "6 osztályos",
            "kerdes": "Mennyi 2 + 2?",
            "helyes_valasz": "4",
            "hint": "Összeadás.",
            "magyarazat": "2 plusz 2 egyenlő 4.",
        },
        targy="matek",
    )


@pytest.fixture
def inplace_result(feladat: Feladat) -> ReviewResult:
    """ReviewResult for an in-place update (no content change, no versioning)."""
    reviewed = dataclasses.replace(feladat, review_elvegezve=True)
    return ReviewResult(
        original_id=feladat.id,
        updated=reviewed,
        changed_fields=[],
        versioned=False,
    )


@pytest.fixture
def db_file(tmp_path: Path, feladat: Feladat) -> Path:
    """Minimal DB with one feladat inserted."""
    db = tmp_path / "test.db"
    from felvi_games.db import FeladatRepository
    FeladatRepository(db_path=db).upsert(feladat)
    return db


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_review_no_id_and_no_wrong_flag_exits_nonzero(db_file: Path) -> None:
    result = runner.invoke(app, ["review", "--db", str(db_file)])
    assert result.exit_code != 0


def test_review_nonexistent_db_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["review", "any_id", "--db", str(tmp_path / "missing.db")])
    assert result.exit_code != 0


def test_review_unknown_feladat_id_exits_nonzero(db_file: Path) -> None:
    result = runner.invoke(app, ["review", "no_such_id", "--db", str(db_file)])
    assert result.exit_code != 0
    assert "nem található" in result.output


def test_review_wrong_no_attempts_prints_message(db_file: Path) -> None:
    result = runner.invoke(app, ["review", "--wrong", "--db", str(db_file)])
    assert result.exit_code == 0
    assert "hibásan" in result.output


# ---------------------------------------------------------------------------
# Happy path – dry-run
# ---------------------------------------------------------------------------


def test_review_dry_run_does_not_persist(
    db_file: Path, feladat: Feladat, inplace_result: ReviewResult
) -> None:
    with patch("felvi_games.review.run_feladat_review", return_value=inplace_result) as mock_svc:
        result = runner.invoke(
            app, ["review", feladat.id, "--db", str(db_file), "--dry-run"]
        )
    assert result.exit_code == 0
    _, kwargs = mock_svc.call_args
    assert kwargs.get("dry_run") is True
    assert "dry-run" in result.output


def test_review_dry_run_shows_feladat_id(
    db_file: Path, feladat: Feladat, inplace_result: ReviewResult
) -> None:
    with patch("felvi_games.review.run_feladat_review", return_value=inplace_result):
        result = runner.invoke(
            app, ["review", feladat.id, "--db", str(db_file), "--dry-run"]
        )
    assert feladat.id in result.output


# ---------------------------------------------------------------------------
# Happy path – in-place update
# ---------------------------------------------------------------------------


def test_review_inplace_calls_service(
    db_file: Path, feladat: Feladat, inplace_result: ReviewResult
) -> None:
    with patch("felvi_games.review.run_feladat_review", return_value=inplace_result) as mock_svc:
        result = runner.invoke(app, ["review", feladat.id, "--db", str(db_file)])
    assert result.exit_code == 0
    mock_svc.assert_called_once()
    assert "In-place" in result.output


# ---------------------------------------------------------------------------
# Happy path – versioned update
# ---------------------------------------------------------------------------


def test_review_versioned_reports_new_id(
    db_file: Path, feladat: Feladat
) -> None:
    new_version = dataclasses.replace(feladat, id=f"{feladat.id}_v2", verzio=2, review_elvegezve=True)
    versioned_result = ReviewResult(
        original_id=feladat.id,
        updated=new_version,
        changed_fields=["kerdes"],
        versioned=True,
    )
    with patch("felvi_games.review.run_feladat_review", return_value=versioned_result):
        result = runner.invoke(app, ["review", feladat.id, "--db", str(db_file)])
    assert result.exit_code == 0
    assert f"{feladat.id}_v2" in result.output


def test_review_diff_shown_for_changed_field(
    db_file: Path, feladat: Feladat
) -> None:
    changed = dataclasses.replace(feladat, kerdes="Javított kérdés?", review_elvegezve=True)
    diff_result = ReviewResult(
        original_id=feladat.id,
        updated=changed,
        changed_fields=["kerdes"],
        versioned=False,
    )
    with patch("felvi_games.review.run_feladat_review", return_value=diff_result):
        result = runner.invoke(app, ["review", feladat.id, "--db", str(db_file)])
    assert "kerdes" in result.output
    assert "Javított kérdés?" in result.output


# ---------------------------------------------------------------------------
# megjegyzes forwarded to service
# ---------------------------------------------------------------------------


def test_review_megjegyzes_forwarded_to_service(
    db_file: Path, feladat: Feladat, inplace_result: ReviewResult
) -> None:
    with patch("felvi_games.review.run_feladat_review", return_value=inplace_result) as mock_svc:
        runner.invoke(
            app,
            ["review", feladat.id, "--db", str(db_file), "--megjegyzes", "fontos megjegyzés"],
        )
    _, kwargs = mock_svc.call_args
    assert kwargs.get("megjegyzes") == "fontos megjegyzés"
