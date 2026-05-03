from __future__ import annotations

from pathlib import Path

from felvi_games import status


def test_pdf_summary_empty_dir_prints_hint(tmp_path: Path, capsys) -> None:
    status._pdf_summary(tmp_path, szint_filter=None)
    out = capsys.readouterr().out
    assert "nincs PDF" in out


def test_pdf_summary_groups_known_files(tmp_path: Path, capsys) -> None:
    (tmp_path / "A8_2023_1_fl.pdf").write_bytes(b"x")
    (tmp_path / "A8_2023_1_ut.pdf").write_bytes(b"x")
    (tmp_path / "M8_2023_2_fl.pdf").write_bytes(b"x")

    status._pdf_summary(tmp_path, szint_filter=None)
    out = capsys.readouterr().out

    assert "4 osztályos" in out
    assert "2023" in out
    assert "magyar" in out
    assert "matek" in out
    assert "fl" in out


def test_pdf_summary_unrecognized_names_are_reported(tmp_path: Path, capsys) -> None:
    (tmp_path / "random_name.pdf").write_bytes(b"x")

    status._pdf_summary(tmp_path, szint_filter=None)
    out = capsys.readouterr().out

    assert "ismeretlen nev" in out


def test_run_missing_paths_prints_missing_hints(tmp_path: Path, monkeypatch, capsys) -> None:
    missing_db = tmp_path / "missing.db"
    missing_exams = tmp_path / "missing_exams"
    missing_assets = tmp_path / "missing_assets"

    monkeypatch.setattr("felvi_games.config.get_db_path", lambda: missing_db)
    monkeypatch.setattr("felvi_games.config.get_exams_dir", lambda: missing_exams)
    monkeypatch.setattr("felvi_games.config.get_assets_dir", lambda: missing_assets)

    status.run()
    out = capsys.readouterr().out

    assert "NINCS" in out
    assert "futtasd: felvi scrape" in out
    assert "futtasd: felvi parse" in out


def test_run_calls_pdf_and_db_summaries_when_paths_exist(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "ok.db"
    exams = tmp_path / "exams"
    assets = tmp_path / "assets"
    exams.mkdir()
    assets.mkdir()
    db.write_text("x", encoding="utf-8")

    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr("felvi_games.config.get_db_path", lambda: db)
    monkeypatch.setattr("felvi_games.config.get_exams_dir", lambda: exams)
    monkeypatch.setattr("felvi_games.config.get_assets_dir", lambda: assets)
    monkeypatch.setattr("felvi_games.status._pdf_summary", lambda p, s: calls.append(("pdf", s)))
    monkeypatch.setattr("felvi_games.status._db_summary", lambda p, s: calls.append(("db", s)))

    status.run(szint="4")

    assert calls == [("pdf", "4"), ("db", "4")]
