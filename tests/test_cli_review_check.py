from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from felvi_games.cli import app
from felvi_games.db import FeladatRepository
from felvi_games.models import Ertekeles, Feladat

runner = CliRunner()


class TestReviewCheckCli:
    def test_review_check_prepare_only_from_any_wrong_source(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_check.db"
        ctx_dir = tmp_path / "ctx"

        repo = FeladatRepository(db_path=db_path)
        feladat = Feladat.from_dict(
            {
                "id": "m_review_check_1",
                "neh": 2,
                "szint": "4 osztályos",
                "kerdes": "Kérdés?",
                "helyes_valasz": "jó",
                "hint": "tipp",
                "magyarazat": "magyarázat",
            },
            targy="matek",
        )
        repo.upsert(feladat)
        repo.save_megoldas(
            feladat,
            "hibás",
            Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
            felhasznalo_nev="Lóri",
            hibajelezes=True,
        )

        result = runner.invoke(
            app,
            [
                "review-check",
                "--db",
                str(db_path),
                "--source",
                "any",
                "--user",
                "Lóri",
                "--prepare-only",
                "--no-ai-assessment",
                "--context-dir",
                str(ctx_dir),
            ],
        )

        assert result.exit_code == 0
        out = ctx_dir / "m_review_check_1.json"
        assert out.exists()
        text = out.read_text(encoding="utf-8")
        assert '"id": "m_review_check_1"' in text
        assert '"db_path":' in text
