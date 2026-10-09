from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from felvi_games.db import FeladatRepository, MenetRecord, get_engine
from felvi_games.models import Ertekeles, Feladat
from felvi_games.report import (
    ReportData,
    _build_date_range,
    _calculate_performance_metrics,
    gather_data,
)


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


def test_build_date_range_contains_exactly_the_report_days() -> None:
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
