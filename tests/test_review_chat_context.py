from __future__ import annotations

import dataclasses

from felvi_games.config import get_assets_dir
from felvi_games.models import Ertekeles, Feladat
from felvi_games.review import build_review_chat_context


def test_build_review_chat_context_includes_attempt_buckets(repo, tmp_path):
    feladat = Feladat.from_dict(
        {
            "id": "mag4_chat_1",
            "neh": 2,
            "szint": "4 osztályos",
            "kerdes": "Mi a keresett szó?",
            "helyes_valasz": "szarka",
            "hint": "Lopós madár",
            "magyarazat": "A versben utalt madár a szarka.",
            "feladat_tipus": "nyilt_valasz",
            "max_pont": 1,
            "feladat_oldal": 1,
        },
        targy="magyar",
    )

    assets_dir = get_assets_dir()
    text_dir = assets_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    fl = text_dir / "chat_fl.txt"
    ut = text_dir / "chat_ut.txt"
    fl.write_text("[Oldal 1]\nFeladatlap tartalom.", encoding="utf-8")
    ut.write_text("[Oldal 1]\nÚtmutató tartalom.", encoding="utf-8")

    feladat = dataclasses.replace(
        feladat,
        fl_szoveg_path="text/chat_fl.txt",
        ut_szoveg_path="text/chat_ut.txt",
    )

    repo.upsert(feladat)
    repo.save_megoldas(
        feladat,
        "rossz válasz",
        Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
        felhasznalo_nev="Lóri",
        hibajelezes=True,
    )
    repo.save_megoldas(
        feladat,
        "szarka",
        Ertekeles(helyes=True, pont=1, visszajelzes="jó"),
        felhasznalo_nev="Lóri",
    )

    loaded = repo.get(feladat.id)
    assert loaded is not None

    ctx = build_review_chat_context(loaded, repo, include_ai_assessment=False)

    assert ctx["feladat"]["id"] == "mag4_chat_1"
    assert "Feladatlap tartalom" in ctx["sources"]["feladatlap_kivonat"]
    assert "Útmutató tartalom" in ctx["sources"]["utmutato_kivonat"]
    assert ctx["attempts"]["total"] == 2
    assert ctx["attempts"]["good_count"] == 1
    assert ctx["attempts"]["bad_count"] == 1
    assert len(ctx["attempts"]["good_recent"]) == 1
    assert len(ctx["attempts"]["bad_recent"]) == 1
