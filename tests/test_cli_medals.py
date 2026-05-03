"""CLI tests for the `felvi medals` command."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from typer.testing import CliRunner
from sqlalchemy import update
from sqlalchemy.orm import Session

from felvi_games.cli import app
from felvi_games.db import FeladatRepository, FelhasznaloEremSzerzesRecord
from felvi_games.models import Erem
from felvi_games.progress_check import CloseMedal

runner = CliRunner()


def _empty_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    from felvi_games.db import FeladatRepository

    FeladatRepository(db_path=db)
    return db


def test_medals_generator_inputs_shows_payload(tmp_path: Path) -> None:
    db_file = _empty_db(tmp_path)
    stats = {
        "total_attempts": 86,
        "correct": 71,
        "accuracy_pct": 82.6,
        "total_sessions": 12,
        "completed_sessions": 9,
        "subjects_used": ["magyar", "matek"],
        "levels_used": ["4 osztályos"],
        "recent_days_7d": 4,
        "current_streak_days": 3,
        "best_correct_streak": 16,
        "current_correct_streak": 5,
        "hint_free_correct_last20": 14,
        "avg_elapsed_sec": 11.2,
    }
    close_medals = [
        CloseMedal(
            erem=Erem(
                id="szaz_feladat",
                nev="Centurion",
                leiras="100 feladatot oldottál meg.",
                ikon="💯",
                kategoria="merfoldko",
            ),
            progress=0.86,
            hint="86 / 100 feladat",
        )
    ]

    with (
        patch("felvi_games.progress_check.get_user_stats", return_value=stats),
        patch("felvi_games.progress_check.estimate_close_medals", return_value=close_medals),
    ):
        result = runner.invoke(
            app,
            [
                "medals",
                "--db",
                str(db_file),
                "--user",
                "Lóri",
                "--generator-inputs",
                "--window-hours",
                "12",
            ],
        )

    assert result.exit_code == 0
    assert '"user": "Lóri"' in result.output
    assert '"window_hours": 12' in result.output
    assert '"earned_count": 0' in result.output
    assert '"total_attempts": 86' in result.output
    assert '"best_correct_streak": 16' in result.output
    assert '"id": "szaz_feladat"' in result.output
    assert '"progress_pct": 86' in result.output


def test_medals_generator_inputs_requires_user(tmp_path: Path) -> None:
    db_file = _empty_db(tmp_path)

    result = runner.invoke(app, ["medals", "--db", str(db_file), "--generator-inputs"])

    assert result.exit_code != 0
    assert "--user" in result.output


def test_medals_shows_all_earned_dates_for_repeated_medal(tmp_path: Path) -> None:
    db_file = _empty_db(tmp_path)
    repo = FeladatRepository(db_path=db_file)

    repo.grant_erem("Lóri", "elso_menet")
    repo.grant_erem("Lóri", "elso_menet")

    first_dt = datetime(2026, 5, 1, 7, 20, tzinfo=timezone.utc)
    second_dt = datetime(2026, 5, 3, 8, 10, tzinfo=timezone.utc)

    with Session(repo._engine) as session:
        ids = [
            row[0]
            for row in session.query(FelhasznaloEremSzerzesRecord.id)
            .filter_by(felhasznalo_nev="Lóri", erem_id="elso_menet")
            .order_by(FelhasznaloEremSzerzesRecord.id.asc())
            .all()
        ]
        session.execute(
            update(FelhasznaloEremSzerzesRecord)
            .where(FelhasznaloEremSzerzesRecord.id == ids[0])
            .values(szerzett_at=first_dt)
        )
        session.execute(
            update(FelhasznaloEremSzerzesRecord)
            .where(FelhasznaloEremSzerzesRecord.id == ids[1])
            .values(szerzett_at=second_dt)
        )
        session.commit()

    result = runner.invoke(app, ["medals", "--db", str(db_file), "--user", "Lóri"])

    assert result.exit_code == 0
    assert "×2" in result.output
    assert "Szerezve: 2026-05-03 08:10; 2026-05-01 07:20" in result.output