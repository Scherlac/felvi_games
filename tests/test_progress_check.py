from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from felvi_games.db import InterakcioRecord, MegoldasRecord, MenetRecord
from felvi_games.models import Ertekeles, InterakcioTipus
from felvi_games.progress_check import get_user_stats


def test_get_user_stats_includes_trends_patterns_and_events(repo, feladat_matek, feladat_magyar) -> None:
    user = "Lori"
    matek = dataclasses.replace(feladat_matek, feladat_tipus="kitoltes")
    magyar = dataclasses.replace(
        feladat_magyar,
        id="ny_test_02",
        szint="4 osztályos",
        feladat_tipus="nyilt_valasz",
    )
    repo.upsert_many([matek, magyar])

    matek_menet_id = repo.start_menet(user, "matek", "4 osztályos", 5)
    mixed_level_menet_id = repo.start_menet(user, "magyar", "mind", 5)
    repo.update_menet_progress(matek_menet_id, 2, 5)
    repo.end_menet(matek_menet_id)
    repo.update_menet_progress(mixed_level_menet_id, 1, 3)

    repo.save_megoldas(matek, "42", Ertekeles(True, "OK", 5), felhasznalo_nev=user, menet_id=matek_menet_id)
    first_attempt_id = repo.get_latest_megoldas_id(matek.id, felhasznalo_nev=user)
    repo.save_megoldas(matek, "0", Ertekeles(False, "Nem", 0), felhasznalo_nev=user, menet_id=matek_menet_id, segitseg_kert=True)
    second_attempt_id = repo.get_latest_megoldas_id(matek.id, felhasznalo_nev=user, adott_valasz="0")
    repo.save_megoldas(magyar, "ige", Ertekeles(True, "OK", 3), felhasznalo_nev=user, menet_id=mixed_level_menet_id)
    third_attempt_id = repo.get_latest_megoldas_id(magyar.id, felhasznalo_nev=user)

    now_utc = datetime.now(timezone.utc)
    with Session(repo._engine) as session:
        session.execute(
            update(MegoldasRecord)
            .where(MegoldasRecord.id == first_attempt_id)
            .values(created_at=now_utc - timedelta(hours=30))
        )
        session.execute(
            update(MegoldasRecord)
            .where(MegoldasRecord.id == second_attempt_id)
            .values(created_at=now_utc - timedelta(hours=6))
        )
        session.execute(
            update(MegoldasRecord)
            .where(MegoldasRecord.id == third_attempt_id)
            .values(
                created_at=now_utc - timedelta(hours=2),
                ujraertekelt=True,
                ujraertekelt_at=now_utc - timedelta(hours=3),
                eredeti_pont=1,
                jutalom_varakozik=True,
            )
        )
        session.execute(
            update(MenetRecord)
            .where(MenetRecord.id == matek_menet_id)
            .values(started_at=now_utc - timedelta(hours=8), ended_at=now_utc - timedelta(hours=7, minutes=30))
        )
        session.execute(
            update(MenetRecord)
            .where(MenetRecord.id == mixed_level_menet_id)
            .values(started_at=now_utc - timedelta(hours=2))
        )
        session.commit()

    repo.log_interakcio(user, InterakcioTipus.HELYES_VALASZ, targy="magyar", szint="4 osztályos", feladat_id=magyar.id)
    repo.log_interakcio(user, InterakcioTipus.HIBAJELEZES, targy="matek", szint="4 osztályos", feladat_id=matek.id)
    repo.log_interakcio(user, InterakcioTipus.UJRAERTEKELES, targy="magyar", szint="4 osztályos", feladat_id=magyar.id)

    with Session(repo._engine) as session:
        event_rows = list(
            session.query(InterakcioRecord)
            .filter(InterakcioRecord.felhasznalo_nev == user)
            .order_by(InterakcioRecord.id.asc())
            .all()
        )
        event_rows[0].created_at = now_utc - timedelta(hours=2)
        event_rows[1].created_at = now_utc - timedelta(hours=6)
        event_rows[2].created_at = now_utc - timedelta(hours=3)
        session.commit()

    stats = get_user_stats(user, repo)

    assert stats["levels_used"] == ["4 osztályos"]
    assert stats["trends"]["attempts_last_24h"] == 2
    assert stats["trends"]["attempts_prev_24h"] == 1
    assert stats["trends"]["accuracy_last_24h"] == 50.0
    assert stats["trends"]["activity_trend"] == "javul"
    assert stats["patterns"]["subject_session_counts"] == {"matek": 1, "magyar": 1}
    assert stats["patterns"]["level_session_counts"] == {"4 osztályos": 1}
    assert stats["patterns"]["attempt_task_type_counts"] == {"kitoltes": 2, "nyilt_valasz": 1}
    assert stats["events"]["counts_last_24h"][InterakcioTipus.HELYES_VALASZ.value] == 1
    assert stats["events"]["counts_last_24h"][InterakcioTipus.HIBAJELEZES.value] == 1
    assert stats["events"]["counts_last_24h"][InterakcioTipus.UJRAERTEKELES.value] == 1
    assert stats["events"]["counts_last_24h"][InterakcioTipus.UJRAERTEKELES_JUTALOM.value] == 1
    assert stats["events"]["reevaluations_last_7d"] == 1
    assert stats["events"]["reevaluation_improved_last_7d"] == 1
    assert stats["events"]["pending_reward_attempts"] == 0
    assert InterakcioTipus.HELYES_VALASZ.value in {item["type"] for item in stats["events"]["recent"]}
