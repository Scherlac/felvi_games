from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from felvi_games import achievements
from felvi_games.achievements import check_new_medals
from felvi_games.db import MegoldasRecord
from felvi_games.models import Ertekeles, Feladat


def _make_feladat() -> Feladat:
    return Feladat.from_dict(
        {
            "id": "gating_test_01",
            "neh": 1,
            "szint": "6 osztályos",
            "kerdes": "Teszt kérdés",
            "helyes_valasz": "42",
            "hint": "tipp",
            "magyarazat": "magyarázat",
        },
        targy="matek",
    )


def _insert_attempt_at(repo, user: str, created_at_utc: datetime, elapsed_sec: float = 12.0) -> None:
    f = _make_feladat()
    repo.upsert(f)
    repo.save_megoldas(
        f,
        "42",
        Ertekeles(True, "ok", 1),
        felhasznalo_nev=user,
        elapsed_sec=elapsed_sec,
    )
    latest_id = repo.get_latest_megoldas_id(f.id, felhasznalo_nev=user)
    with Session(repo._engine) as s:
        s.execute(
            update(MegoldasRecord)
            .where(MegoldasRecord.id == latest_id)
            .values(created_at=created_at_utc)
        )
        s.commit()


def _utc_for_local_time(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Build a UTC timestamp that corresponds to a specific local wall-clock time."""
    local_tz = datetime.now().astimezone().tzinfo
    assert local_tz is not None
    local_dt = datetime(year, month, day, hour, minute, tzinfo=local_tz)
    return local_dt.astimezone(timezone.utc)


def test_bootstrap_conditions_seeded_and_villam_awardable(repo):
    user = "Lori"
    catalog = repo.get_erem_katalogus(user)

    assert catalog["villam"].condition is not None
    assert catalog["villam"].condition.get("type") == "villam"
    assert catalog["esti_tanulas"].condition is not None
    assert catalog["esti_tanulas"].condition.get("type") == "after_hour"

    # Keep timestamp near "now" so this test detects logic regressions, not date drift.
    _insert_attempt_at(repo, user, datetime.now(timezone.utc) - timedelta(minutes=1), elapsed_sec=5.0)

    with Session(repo._engine) as s:
        fast_count = s.scalar(
            select(func.count()).select_from(MegoldasRecord).where(
                MegoldasRecord.felhasznalo_nev == user,
                MegoldasRecord.pont > 0,
                MegoldasRecord.elapsed_sec.is_not(None),
                MegoldasRecord.elapsed_sec <= 10.0,
            )
        ) or 0
    assert fast_count >= 1
    assert achievements._eval_dynamic_condition(
        user,
        catalog["villam"].condition,
        repo._engine,
        valid_from=catalog["villam"].condition_valid_from,
    )

    awarded = check_new_medals(user, None, repo)
    assert any(e.id == "villam" for e in awarded)


def test_esti_tanulas_requires_new_night_signal(repo, monkeypatch):
    user = "Lori"

    # Disable cooldown to isolate the "new qualifying evidence" gate.
    monkeypatch.setitem(achievements._REPEATABLE_COOLDOWN_HOURS, "esti_tanulas", 0)

    today_local = datetime.now().astimezone()
    yesterday_local = today_local - timedelta(days=1)
    first_night_utc = _utc_for_local_time(
        yesterday_local.year,
        yesterday_local.month,
        yesterday_local.day,
        23,
        0,
    )
    _insert_attempt_at(repo, user, first_night_utc)
    first = check_new_medals(user, None, repo)
    assert any(e.id == "esti_tanulas" for e in first)

    # No new attempts -> should not re-award.
    second = check_new_medals(user, None, repo)
    assert all(e.id != "esti_tanulas" for e in second)

    # Daytime attempt after the first award is not enough.
    next_day_local = today_local + timedelta(days=1)
    daytime_utc = _utc_for_local_time(
        next_day_local.year,
        next_day_local.month,
        next_day_local.day,
        12,
        0,
    )
    _insert_attempt_at(repo, user, daytime_utc)
    third = check_new_medals(user, None, repo)
    assert all(e.id != "esti_tanulas" for e in third)

    # New night attempt after first award allows re-award.
    second_night_utc = _utc_for_local_time(
        next_day_local.year,
        next_day_local.month,
        next_day_local.day,
        23,
        0,
    )
    _insert_attempt_at(repo, user, second_night_utc)
    fourth = check_new_medals(user, None, repo)
    assert any(e.id == "esti_tanulas" for e in fourth)


def test_villam_repeatable_respects_cooldown(repo, monkeypatch):
    user = "Lori"

    # Long cooldown: second immediate award should be blocked.
    monkeypatch.setitem(achievements._REPEATABLE_COOLDOWN_HOURS, "villam", 999)

    base = datetime.now(timezone.utc)
    _insert_attempt_at(repo, user, base - timedelta(minutes=2), elapsed_sec=5.0)
    first = check_new_medals(user, None, repo)
    assert any(e.id == "villam" for e in first)

    # New qualifying fast answer exists, but cooldown should block re-award now.
    _insert_attempt_at(repo, user, base - timedelta(minutes=1), elapsed_sec=4.0)
    second = check_new_medals(user, None, repo)
    assert all(e.id != "villam" for e in second)
