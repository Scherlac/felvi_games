from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from felvi_games import achievements
from felvi_games.achievements import _eval_dynamic_condition
from felvi_games.db import MegoldasRecord
from felvi_games.models import Ertekeles, Feladat, InterakcioTipus


def _make_feladat() -> Feladat:
    return Feladat.from_dict(
        {
            "id": "dyn_cond_test_01",
            "neh": 1,
            "szint": "6 osztályos",
            "kerdes": "Teszt kérdés",
            "helyes_valasz": "42",
            "hint": "tipp",
            "magyarazat": "magyarázat",
        },
        targy="matek",
    )


def _insert_attempt_at(repo, user: str, created_at_utc: datetime, *, helyes: bool = True, pont: int = 1) -> None:
    feladat = _make_feladat()
    repo.upsert(feladat)
    repo.save_megoldas(
        feladat,
        "42",
        Ertekeles(helyes, "ok", pont),
        felhasznalo_nev=user,
        elapsed_sec=5.0,
    )
    latest_id = repo.get_latest_megoldas_id(feladat.id, felhasznalo_nev=user)
    with Session(repo._engine) as session:
        session.execute(
            update(MegoldasRecord)
            .where(MegoldasRecord.id == latest_id)
            .values(created_at=created_at_utc)
        )
        session.commit()


def test_eval_dynamic_condition_unknown_type_returns_false(repo) -> None:
    assert _eval_dynamic_condition("Lori", {"type": "unknown_condition"}, repo._engine) is False


def test_eval_dynamic_condition_feladat_count_respects_valid_from(repo) -> None:
    user = "Lori"
    old_ts = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    new_ts = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
    valid_from = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    _insert_attempt_at(repo, user, old_ts, pont=1)
    _insert_attempt_at(repo, user, new_ts, pont=1)

    assert _eval_dynamic_condition(
        user,
        {"type": "feladat_count", "n": 1, "window_hours": 1},
        repo._engine,
        valid_from=valid_from,
    ) is True
    assert _eval_dynamic_condition(
        user,
        {"type": "feladat_count", "n": 2, "window_hours": 1},
        repo._engine,
        valid_from=valid_from,
    ) is False


def test_eval_dynamic_condition_interakcio_exists_with_enum_and_filters(repo) -> None:
    user = "Lori"
    repo.log_interakcio(
        user,
        InterakcioTipus.HELYES_VALASZ,
        targy="matek",
        szint="6 osztályos",
        feladat_id="dyn_cond_test_01",
        meta={"note": "unit-meta"},
        process_pending_rewards=False,
    )

    condition = {
        "type": "interakcio_exists",
        "event_type": InterakcioTipus.HELYES_VALASZ,
        "window_hours": 24,
        "targy": "matek",
        "szint": "6 osztályos",
        "feladat_id": "dyn_cond_test_01",
        "meta_contains": "unit-meta",
    }
    assert _eval_dynamic_condition(user, condition, repo._engine) is True

    condition["meta_contains"] = "does-not-match"
    assert _eval_dynamic_condition(user, condition, repo._engine) is False


def test_eval_dynamic_condition_respects_simulation_upper_bound(repo) -> None:
    user = "Lori"
    first = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    second = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
    upper = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    _insert_attempt_at(repo, user, first)
    _insert_attempt_at(repo, user, second)

    token = achievements._simulation_as_of.set(upper)
    try:
        assert _eval_dynamic_condition(
            user,
            {"type": "feladat_count", "n": 2, "window_hours": 24 * 365},
            repo._engine,
        ) is False
        assert _eval_dynamic_condition(
            user,
            {"type": "feladat_count", "n": 1, "window_hours": 24 * 365},
            repo._engine,
        ) is True
    finally:
        achievements._simulation_as_of.reset(token)
