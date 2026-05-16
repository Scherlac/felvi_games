from __future__ import annotations

from unittest.mock import patch

from sqlalchemy.orm import Session
from typer.testing import CliRunner

from felvi_games.cli import app
from felvi_games.db import FeladatRepository, MegoldasRecord
from felvi_games.models import Ertekeles

runner = CliRunner()


def _seed_open_answer_attempt(tmp_path):
    db_path = tmp_path / "test_reeval.db"
    repo = FeladatRepository(db_path=db_path)

    from felvi_games.models import Feladat

    feladat = Feladat.from_dict(
        {
            "id": "mag4_test_open_1",
            "neh": 2,
            "szint": "4 osztályos",
            "kerdes": "Írj két -ka/-ke végű állatnevet, ami nem szerepel a versben.",
            "helyes_valasz": "pl. béka, bika",
            "hint": "Bármelyik megfelelő állatnév jó lehet.",
            "magyarazat": "A formai feltétel számít, nem egyetlen fix pár.",
            "feladat_tipus": "nyilt_valasz",
            "elfogadott_valaszok": ["béka, bika"],
            "max_pont": 1,
        },
        targy="magyar",
    )
    repo.upsert(feladat)
    repo.save_megoldas(
        feladat,
        "macska, kecske",
        Ertekeles(helyes=False, pont=0, visszajelzes="Első körben hibás"),
        felhasznalo_nev="Lóri",
    )
    megoldas_id = repo.get_latest_megoldas_id(feladat.id, felhasznalo_nev="Lóri")
    assert megoldas_id is not None
    return db_path, int(megoldas_id)


def test_reeval_lenient_open_can_upgrade_score(tmp_path):
    db_path, megoldas_id = _seed_open_answer_attempt(tmp_path)

    strict = Ertekeles(helyes=False, pont=0, visszajelzes="Nincs az elfogadott listában")
    lenient = Ertekeles(helyes=True, pont=1, visszajelzes="Elfogadható általános válasz")

    with patch("felvi_games.ai.check_answer", side_effect=[strict, lenient]) as mock_check:
        result = runner.invoke(
            app,
            [
                "reeval",
                "--db",
                str(db_path),
                "--id",
                str(megoldas_id),
                "--lenient-open",
            ],
        )

    assert result.exit_code == 0
    assert "lenient-upgrade" in result.output
    assert mock_check.call_count == 2

    first_kwargs = mock_check.call_args_list[0].kwargs
    second_kwargs = mock_check.call_args_list[1].kwargs
    assert first_kwargs["elfogadott_valaszok"] == ["béka, bika"]
    assert second_kwargs["elfogadott_valaszok"] is None

    repo = FeladatRepository(db_path=db_path)
    with Session(repo._engine) as s:
        rec = s.get(MegoldasRecord, megoldas_id)
        assert rec is not None
        assert rec.pont == 1
        assert rec.helyes is True


def test_reeval_without_lenient_open_keeps_strict_score(tmp_path):
    db_path, megoldas_id = _seed_open_answer_attempt(tmp_path)

    strict = Ertekeles(helyes=False, pont=0, visszajelzes="Nincs az elfogadott listában")

    with patch("felvi_games.ai.check_answer", return_value=strict) as mock_check:
        result = runner.invoke(
            app,
            [
                "reeval",
                "--db",
                str(db_path),
                "--id",
                str(megoldas_id),
            ],
        )

    assert result.exit_code == 0
    assert "[strict]" in result.output
    assert mock_check.call_count == 1

    repo = FeladatRepository(db_path=db_path)
    with Session(repo._engine) as s:
        rec = s.get(MegoldasRecord, megoldas_id)
        assert rec is not None
        assert rec.pont == 0
        assert rec.helyes is False
