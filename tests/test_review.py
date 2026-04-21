"""Tests for the review module."""

from __future__ import annotations

import dataclasses

import pytest

from felvi_games.models import Feladat
from felvi_games.review import (
    _extract_page,
    edit_feladat_cli,
    review_feladatok,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def feladat() -> Feladat:
    return Feladat.from_dict(
        {
            "id": "test_rev_01",
            "neh": 2,
            "szint": "6 osztályos",
            "kerdes": "Mi az 5 × 9?",
            "helyes_valasz": "45",
            "hint": "Szorzótábla.",
            "magyarazat": "5 × 9 = 45",
        },
        targy="matek",
    )


# ---------------------------------------------------------------------------
# _extract_page
# ---------------------------------------------------------------------------


def test_extract_page_no_markers_returns_truncated():
    text = "a" * 5000
    result = _extract_page(text, page_no=None)
    assert result == "a" * 3000


def test_extract_page_known_page():
    text = "[Oldal 1]\nElső oldal tartalma.\n[Oldal 2]\nMásodik oldal.\n[Oldal 3]\nHarmadik."
    result = _extract_page(text, page_no=2)
    assert "Második oldal." in result
    assert "Harmadik" not in result


def test_extract_page_last_page_no_trailing_marker():
    text = "[Oldal 1]\nElső oldal.\n[Oldal 2]\nUtolsó oldal."
    result = _extract_page(text, page_no=2)
    assert "Utolsó oldal." in result


def test_extract_page_missing_page_returns_fallback():
    text = "[Oldal 1]\nEgyetlen oldal."
    result = _extract_page(text, page_no=99)
    assert result == "[Oldal 1]\nEgyetlen oldal."  # first 3000 chars


def test_extract_page_none_page_no():
    text = "[Oldal 1]\nTartalom."
    result = _extract_page(text, page_no=None)
    # should return up to 3000 chars of the full text
    assert result.startswith("[Oldal 1]")


# ---------------------------------------------------------------------------
# review_feladatok (interactive – monkeypatched input)
# ---------------------------------------------------------------------------


def test_review_feladatok_accept(feladat, monkeypatch):
    """Pressing Enter (accept) keeps the feladat and marks review_elvegezve."""
    inputs = iter(["a"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    result = review_feladatok([feladat])
    assert len(result) == 1
    assert result[0].id == feladat.id
    assert result[0].review_elvegezve is True


def test_review_feladatok_skip(feladat, monkeypatch):
    """Pressing 's' discards the feladat."""
    monkeypatch.setattr("builtins.input", lambda _: "s")
    result = review_feladatok([feladat])
    assert result == []


def test_review_feladatok_quit_early(monkeypatch):
    """Pressing 'q' stops processing and returns already-accepted items."""
    f1 = Feladat.from_dict(
        {"id": "r1", "neh": 1, "szint": "4 osztályos", "kerdes": "K1",
         "helyes_valasz": "V1", "hint": "H1", "magyarazat": "M1"},
        targy="matek",
    )
    f2 = dataclasses.replace(f1, id="r2")
    inputs = iter(["a", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    result = review_feladatok([f1, f2])
    assert len(result) == 1
    assert result[0].id == "r1"


def test_review_feladatok_empty():
    result = review_feladatok([])
    assert result == []


# ---------------------------------------------------------------------------
# edit_feladat_cli
# ---------------------------------------------------------------------------


def test_edit_feladat_cli_no_changes(feladat, monkeypatch):
    """All empty inputs → original feladat unchanged."""
    monkeypatch.setattr("builtins.input", lambda _: "")
    result = edit_feladat_cli(feladat)
    assert result.kerdes == feladat.kerdes
    assert result.helyes_valasz == feladat.helyes_valasz


def test_edit_feladat_cli_changes_kerdes(feladat, monkeypatch):
    """Non-empty input for 'kerdes' → field updated; others unchanged."""
    responses = {
        "kerdes": "Módosított kérdés?",
        "helyes_valasz": "",
        "hint": "",
        "magyarazat": "",
        "neh": "",
        "szint": "",
        "feladat_tipus": "",
        "max_pont": "",
    }
    call_count = [0]

    def fake_input(prompt: str) -> str:
        call_count[0] += 1
        for field, val in responses.items():
            if field in prompt:
                return val
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    result = edit_feladat_cli(feladat)
    assert result.kerdes == "Módosított kérdés?"
    assert result.helyes_valasz == feladat.helyes_valasz


def test_edit_feladat_cli_invalid_neh_keeps_original(feladat, monkeypatch):
    """Invalid neh value → original neh kept."""
    def fake_input(prompt: str) -> str:
        if "neh" in prompt:
            return "bogus"
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    result = edit_feladat_cli(feladat)
    assert result.neh == feladat.neh


# ---------------------------------------------------------------------------
# DB integration: save_review
# ---------------------------------------------------------------------------


def test_save_review_sets_review_elvegezve(repo, feladat):
    repo.upsert(feladat)
    updated = repo.save_review(feladat, megjegyzes="Minden rendben.")
    assert updated.review_elvegezve is True
    assert updated.review_megjegyzes == "Minden rendben."


def test_save_review_clears_megoldas_hibajelezes(repo, feladat):
    from felvi_games.models import Ertekeles
    from felvi_games.db import MegoldasRecord
    from sqlalchemy.orm import Session

    repo.upsert(feladat)
    ert = Ertekeles(helyes=False, pont=0, visszajelzes="Nem helyes.")
    repo.save_megoldas(feladat, "rossz", ert, hibajelezes=True)

    # Verify hibajelezes was recorded
    with Session(repo._engine) as s:
        recs = s.query(MegoldasRecord).filter_by(feladat_id=feladat.id).all()
        assert any(r.hibajelezes for r in recs)

    repo.save_review(feladat)

    # All hibajelezes should be cleared
    with Session(repo._engine) as s:
        recs = s.query(MegoldasRecord).filter_by(feladat_id=feladat.id).all()
        assert all(not r.hibajelezes for r in recs)


def test_save_review_unknown_feladat_raises(repo, feladat):
    with pytest.raises(KeyError):
        repo.save_review(feladat)  # never upserted → KeyError


def test_review_elvegezve_roundtrips_via_upsert(repo, feladat):
    """review_elvegezve=True is persisted and loaded back correctly."""
    reviewed = dataclasses.replace(feladat, review_elvegezve=True, review_megjegyzes="OK")
    repo.upsert(reviewed)
    loaded = repo.get(reviewed.id)
    assert loaded.review_elvegezve is True
    assert loaded.review_megjegyzes == "OK"
