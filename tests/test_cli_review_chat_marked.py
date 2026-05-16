from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from felvi_games.cli import app
from felvi_games.db import FeladatRepository
from felvi_games.models import Feladat

runner = CliRunner()


class TestReviewChatMarkedCli:
    def test_review_chat_marked_prepare_only_builds_context_files(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_chat_marked.db"
        ids_path = tmp_path / "ids.dat"
        ctx_dir = tmp_path / "ctx"

        repo = FeladatRepository(db_path=db_path)
        f1 = Feladat.from_dict(
            {
                "id": "m_marked_01",
                "neh": 2,
                "szint": "4 osztályos",
                "kerdes": "K1",
                "helyes_valasz": "V1",
                "hint": "H1",
                "magyarazat": "M1",
            },
            targy="matek",
        )
        f2 = Feladat.from_dict(
            {
                "id": "m_marked_02",
                "neh": 1,
                "szint": "4 osztályos",
                "kerdes": "K2",
                "helyes_valasz": "V2",
                "hint": "H2",
                "magyarazat": "M2",
            },
            targy="matek",
        )
        repo.upsert(f1)
        repo.upsert(f2)

        ids_path.write_text("m_marked_01\nm_marked_02\nmissing_x\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "review-chat-marked",
                "--db",
                str(db_path),
                "--ids-dat",
                str(ids_path),
                "--context-dir",
                str(ctx_dir),
                "--prepare-only",
                "--no-ai-assessment",
            ],
        )

        assert result.exit_code == 0
        assert (ctx_dir / "m_marked_01.json").exists()
        assert (ctx_dir / "m_marked_02.json").exists()
        assert "missing_x" in result.output
