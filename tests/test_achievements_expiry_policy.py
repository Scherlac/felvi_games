from __future__ import annotations

from felvi_games import achievements
from felvi_games.achievements import check_new_medals
from felvi_games.models import Erem


def test_non_repeatable_temporary_medal_does_not_get_expiry(repo, monkeypatch):
    user = "Lori"
    erem_id = "tmp_one_time"

    repo.upsert_erem(
        Erem(
            id=erem_id,
            nev="Egyszeri ideiglenes",
            leiras="Teszt érem",
            ikon="🎯",
            kategoria="teljesitmeny",
            ideiglenes=True,
            ervenyes_napig=2,
            ismetelheto=False,
            privat=True,
            cel_felhasznalo=user,
        )
    )

    monkeypatch.setitem(achievements.SZABALY_REGISTRY, erem_id, lambda _u, _s, _e: True)
    try:
        check_new_medals(user, None, repo)
    finally:
        achievements.SZABALY_REGISTRY.pop(erem_id, None)

    earned = [e for e in repo.get_eremek(user, include_expired=True) if e.erem_id == erem_id]
    assert len(earned) == 1
    assert earned[0].lejarat is None


def test_repeatable_temporary_medal_gets_expiry(repo, monkeypatch):
    user = "Lori"
    erem_id = "tmp_repeatable"

    repo.upsert_erem(
        Erem(
            id=erem_id,
            nev="Ismetelheto ideiglenes",
            leiras="Teszt érem",
            ikon="🔁",
            kategoria="teljesitmeny",
            ideiglenes=True,
            ervenyes_napig=2,
            ismetelheto=True,
            privat=True,
            cel_felhasznalo=user,
        )
    )

    monkeypatch.setitem(achievements.SZABALY_REGISTRY, erem_id, lambda _u, _s, _e: True)
    try:
        check_new_medals(user, None, repo)
    finally:
        achievements.SZABALY_REGISTRY.pop(erem_id, None)

    earned = [e for e in repo.get_eremek(user, include_expired=True) if e.erem_id == erem_id]
    assert len(earned) == 1
    assert earned[0].lejarat is not None
