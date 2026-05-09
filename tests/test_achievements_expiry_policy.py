from __future__ import annotations

from felvi_games.achievements import check_new_medals
from felvi_games.models import Erem, Ertekeles, Feladat


def _ensure_one_megoldas(repo, user: str) -> None:
    """Insert one correct answer so feladat_count=1 condition is satisfied."""
    f = Feladat.from_dict(
        {
            "id": "expiry_policy_test_feladat",
            "neh": 1,
            "szint": "6 osztályos",
            "kerdes": "Teszt?",
            "helyes_valasz": "x",
            "hint": "",
            "magyarazat": "",
        },
        targy="matek",
    )
    repo.upsert(f)
    repo.save_megoldas(f, "x", Ertekeles(True, "ok", 1), felhasznalo_nev=user, elapsed_sec=10.0)


def _make_test_erem(erem_id: str, user: str, *, ismetelheto: bool) -> Erem:
    return Erem(
        id=erem_id,
        nev="Teszt érem",
        leiras="Teszt",
        ikon="🎯",
        kategoria="teljesitmeny",
        ideiglenes=True,
        ervenyes_napig=2,
        ismetelheto=ismetelheto,
        privat=True,
        cel_felhasznalo=user,
        condition={"type": "feladat_count", "n": 1},
    )


def test_non_repeatable_temporary_medal_does_not_get_expiry(repo):
    user = "Lori"
    erem_id = "tmp_one_time"
    repo.upsert_erem(_make_test_erem(erem_id, user, ismetelheto=False))
    _ensure_one_megoldas(repo, user)
    check_new_medals(user, None, repo)

    earned = [e for e in repo.get_eremek(user, include_expired=True) if e.erem_id == erem_id]
    assert len(earned) == 1
    assert earned[0].lejarat is None


def test_repeatable_temporary_medal_gets_expiry(repo):
    user = "Lori"
    erem_id = "tmp_repeatable"
    repo.upsert_erem(_make_test_erem(erem_id, user, ismetelheto=True))
    _ensure_one_megoldas(repo, user)
    check_new_medals(user, None, repo)

    earned = [e for e in repo.get_eremek(user, include_expired=True) if e.erem_id == erem_id]
    assert len(earned) == 1
    assert earned[0].lejarat is not None
