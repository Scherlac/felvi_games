from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
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


def test_esti_tanulas_requires_new_night_signal(repo, monkeypatch):
    user = "Lori"

    # Disable cooldown to isolate the "new qualifying evidence" gate.
    monkeypatch.setitem(achievements._REPEATABLE_COOLDOWN_HOURS, "esti_tanulas", 0)

    # 22:30 local in UTC+2 -> 20:30 UTC
    _insert_attempt_at(repo, user, datetime(2026, 5, 1, 20, 30, tzinfo=timezone.utc))
    first = check_new_medals(user, None, repo)
    assert any(e.id == "esti_tanulas" for e in first)

    # No new attempts -> should not re-award.
    second = check_new_medals(user, None, repo)
    assert all(e.id != "esti_tanulas" for e in second)

    # Daytime attempt (12:00 local -> 10:00 UTC) after the first award is not enough.
    _insert_attempt_at(repo, user, datetime(2099, 5, 2, 10, 0, tzinfo=timezone.utc))
    third = check_new_medals(user, None, repo)
    assert all(e.id != "esti_tanulas" for e in third)

    # New night attempt (23:00 local -> 21:00 UTC) after first award allows re-award.
    _insert_attempt_at(repo, user, datetime(2099, 5, 2, 21, 0, tzinfo=timezone.utc))
    fourth = check_new_medals(user, None, repo)
    assert any(e.id == "esti_tanulas" for e in fourth)


def test_villam_repeatable_respects_cooldown(repo, monkeypatch):
    user = "Lori"

    # Long cooldown: second immediate award should be blocked.
    monkeypatch.setitem(achievements._REPEATABLE_COOLDOWN_HOURS, "villam", 999)

    _insert_attempt_at(repo, user, datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc), elapsed_sec=5.0)
    first = check_new_medals(user, None, repo)
    assert any(e.id == "villam" for e in first)

    # New qualifying fast answer exists, but cooldown should block re-award now.
    _insert_attempt_at(repo, user, datetime(2026, 5, 1, 8, 5, tzinfo=timezone.utc), elapsed_sec=4.0)
    second = check_new_medals(user, None, repo)
    assert all(e.id != "villam" for e in second)
