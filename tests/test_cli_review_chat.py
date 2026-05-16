from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from felvi_games.cli import app
from felvi_games.db import FeladatRepository
from felvi_games.models import Feladat

runner = CliRunner()


class TestReviewChatCli:
    def test_review_chat_prepare_only_writes_context_json(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_chat.db"
        out_path = tmp_path / "ctx.json"

        repo = FeladatRepository(db_path=db_path)
        feladat = Feladat.from_dict(
            {
                "id": "m_chat_01",
                "neh": 2,
                "szint": "4 osztályos",
                "kerdes": "Mennyi 2+2?",
                "helyes_valasz": "4",
                "hint": "Összeadás",
                "magyarazat": "2+2=4",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="matek",
        )
        repo.upsert(feladat)

        result = runner.invoke(
            app,
            [
                "review-chat",
                "m_chat_01",
                "--db",
                str(db_path),
                "--prepare-only",
                "--no-ai-assessment",
                "--context-out",
                str(out_path),
            ],
        )

        assert result.exit_code == 0
        assert out_path.exists()
        text = out_path.read_text(encoding="utf-8")
        assert '"id": "m_chat_01"' in text
        assert "prepare-only" in result.output
