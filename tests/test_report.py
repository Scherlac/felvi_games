from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from felvi_games.db import FeladatRepository, MenetRecord, WritingPracticeSessionRecord, get_engine
from felvi_games.models import Ertekeles, Feladat
from felvi_games.report import (
    ReportData,
    _build_date_range,
    _calculate_performance_metrics,
    gather_data,
    generate_markdown,
)
from felvi_games.writing_repo import WritingPracticeRepository
from felvi_games.writing_review import ReviewCriterion, ReviewGuide
from felvi_games.writing_tasks import WritingPracticeTask


def test_gather_data_falls_back_to_attempt_time_when_sessions_are_open(tmp_path: Path) -> None:
    db_path = tmp_path / "report_play_time.db"
    repo = FeladatRepository(db_path=db_path)
    repo.get_or_create_felhasznalo("Lackó")

    feladat = Feladat.from_dict(
        {
            "id": "mag_report_1",
            "neh": 2,
            "szint": "4 osztályos",
            "kerdes": "Kérdés?",
            "helyes_valasz": "A",
            "hint": "H",
            "magyarazat": "M",
            "feladat_tipus": "nyilt_valasz",
            "max_pont": 1,
        },
        targy="magyar",
    )
    repo.upsert(feladat)

    menet_id = repo.start_menet("Lackó", "magyar", "4 osztályos", 10)
    repo.save_megoldas(
        feladat,
        "rossz",
        Ertekeles(helyes=False, pont=0, visszajelzes="nem"),
        felhasznalo_nev="Lackó",
        menet_id=menet_id,
        elapsed_sec=120,
    )
    repo.save_megoldas(
        feladat,
        "jó",
        Ertekeles(helyes=True, pont=1, visszajelzes="ok"),
        felhasznalo_nev="Lackó",
        menet_id=menet_id,
        elapsed_sec=180,
    )

    now = datetime.now(timezone.utc)
    with Session(get_engine(db_path)) as session:
        menet = session.get(MenetRecord, menet_id)
        assert menet is not None
        menet.started_at = now - timedelta(minutes=10)
        menet.ended_at = None
        session.commit()

    data = gather_data(get_engine(db_path), days=7)
    user = next(u for u in data.users if u.nev == "Lackó")
    points = sorted(data.attempt_timing, key=lambda row: row.elapsed_sec)
    session_points = data.session_average_points

    assert user.sessions == 1
    assert user.attempts == 2
    assert 9.0 <= user.play_time_min <= 10.5
    assert len(points) == 2
    assert [round(p.elapsed_sec, 1) for p in points] == [120.0, 180.0]
    assert [p.gained_pont for p in points] == [0, 1]
    assert all(p.nev == "Lackó" for p in points)
    assert all(p.targy == "magyar" for p in points)
    assert all(p.max_pont == 1 for p in points)
    assert len(session_points) == 1
    assert session_points[0].nev == "Lackó"
    assert session_points[0].targy == "magyar"
    assert session_points[0].session_date == now.strftime("%Y-%m-%d")
    assert session_points[0].committed_count == 2
    assert round(session_points[0].avg_gained_pont, 2) == 0.5
    assert round(session_points[0].avg_elapsed_sec, 2) == 150.0
    assert round(session_points[0].avg_max_pont, 2) == 1.0


def test_build_date_range_includes_the_last_calendar_day() -> None:
    start = datetime(2026, 9, 26, 10, 52, tzinfo=timezone.utc)
    data = ReportData(
        date_from=start,
        date_to=start + timedelta(days=7),
        days=7,
    )

    assert _build_date_range(data) == [
        "2026-09-26",
        "2026-09-27",
        "2026-09-28",
        "2026-09-29",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
    ]


def test_performance_metrics_use_totals_for_shared_chart_and_table_calculation() -> None:
    metrics = _calculate_performance_metrics(
        achievable_points=100,
        earned_points=80,
        time_sec=240,
        count=10,
    )

    assert metrics.earned_pct == 80.0
    assert metrics.time_per_earned_point == 3.0
    assert metrics.average_achievable_points == 10.0


def test_gather_data_includes_writing_task_reviews_in_report(tmp_path: Path) -> None:
    db_path = tmp_path / "report_writing.db"
    writing_repo = WritingPracticeRepository(db_path)
    task = WritingPracticeTask(
        task_id="A8_2026_2_MNy2_10",
        title="Társasjáték vagy online játék",
        prompt="Írj érvelő fogalmazást.",
        genre="érvelés",
        source_kind="official",
        source_reference="A8_2026_2",
        prompt_source_file="task.txt",
        guide_source_file="guide.txt",
        exam_year=2026,
        variant=2,
        task_number="10",
        min_sentences=6,
        max_sentences=10,
        min_sentences_for_any_points=4,
        suggested_time_min=20,
        suggested_time_max=30,
        guide=ReviewGuide(
            guide_id="writing-report-guide",
            name="Report guide",
            criteria=(
                ReviewCriterion("content", "Tartalom", 5, "Assess content."),
            ),
        ),
    )
    writing_session = writing_repo.create_session("Lackó", task)
    revision = writing_repo.save_revision(writing_session.id, "Lackó", "Egy rövid fogalmazás.")
    writing_repo.save_review(
        writing_session.id,
        revision.id,
        "Lackó",
        json.dumps(
            {
                "total_score": 4,
                "assessable_max_score": 5,
                "learner_sentence_count": 6,
            }
        ),
    )
    writing_repo.submit_session(writing_session.id, "Lackó")

    started_at = datetime.now(timezone.utc) - timedelta(days=2)
    with Session(get_engine(db_path)) as session:
        persisted = session.get(WritingPracticeSessionRecord, writing_session.id)
        assert persisted is not None
        persisted.utc_started_at = started_at
        persisted.utc_submitted_at = started_at + timedelta(minutes=12)
        persisted.active_seconds = 720
        session.commit()

    data = gather_data(get_engine(db_path), days=7)

    assert len(data.writing) == 1
    result = data.writing[0]
    assert result.nev == "Lackó"
    assert result.title == "Társasjáték vagy online játék"
    assert result.source_kind == "official"
    assert result.task_number == "10"
    assert result.status == "submitted"
    assert result.active_seconds == 720
    assert result.total_score == 4
    assert result.max_score == 5
    assert result.learner_sentence_count == 6
    assert [user.nev for user in data.users] == ["Lackó"]

    output_dir = tmp_path / "report"
    output_dir.mkdir()
    report_path = generate_markdown(data, [], output_dir)
    markdown = report_path.read_text(encoding="utf-8")
    assert "## Írásbeli vizsgafeladatok" in markdown
    assert "Társasjáték vagy online játék (2026 / v2 / feladat 10)" in markdown
    assert "| 4 / 5 | 80.0% | 12.0 perc | 6 |" in markdown
