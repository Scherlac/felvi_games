from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from felvi_games.db import FeladatRepository
from felvi_games.db import MegoldasRecord
from felvi_games.models import Ertekeles, Feladat
from felvi_games.models import InterakcioTipus
from felvi_games.review_agent_tools import (
    apply_task_update_with_confirmation,
    get_attempt_detail,
    get_markdown_origin,
    get_source_excerpt,
    get_source_window,
    get_task_overview,
    list_attempts,
    list_wrong_tasks,
    load_task_context,
    locate_task_in_sources,
    request_task_update_confirmation,
    resolve_task_flag,
    search_source_text,
    summarize_answer_patterns,
    summarize_review_risk,
    validate_guide_excerpt,
)


class TestReviewAgentTools:
    def test_review_agent_tools_expose_context(self, repo, tmp_path) -> None:
        context = {
            "feladat": {
                "id": "m_tool_01",
                "targy": "matek",
                "szint": "4 osztályos",
                "ev": 2021,
                "valtozat": 1,
                "feladat_sorszam": "1",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 2,
                "kerdes": "Q?",
                "helyes_valasz": "A",
                "elfogadott_valaszok": ["A", "B"],
                "magyarazat": "M",
            },
            "sources": {
                "feladatlap_kivonat": "TASK EXCERPT",
                "utmutato_kivonat": "GUIDE EXCERPT",
            },
            "attempts": {
                "total": 3,
                "good_count": 1,
                "bad_count": 2,
                "good_recent": [
                    {
                        "id": 1,
                        "helyes": True,
                        "pont": 2,
                        "adott_valasz": "A",
                        "visszajelzes": "ok",
                        "hibajelezes": False,
                    }
                ],
                "bad_recent": [
                    {
                        "id": 2,
                        "helyes": False,
                        "pont": 0,
                        "adott_valasz": "hibás",
                        "visszajelzes": "no",
                        "hibajelezes": True,
                    },
                    {
                        "id": 3,
                        "helyes": False,
                        "pont": 0,
                        "adott_valasz": "rossz",
                        "visszajelzes": "no",
                        "hibajelezes": False,
                    },
                ],
            },
            "ai_assessment": "AI ok.",
        }

        overview = get_task_overview(context)
        assert overview["id"] == "m_tool_01"
        assert overview["stats"]["bad_count"] == 2

        sources = get_source_excerpt(context, source="both")
        assert sources["feladatlap_kivonat"] == "TASK EXCERPT"
        assert sources["utmutato_kivonat"] == "GUIDE EXCERPT"

        attempts = list_attempts(context, kind="bad", limit=1)
        assert attempts["count"] == 2
        assert len(attempts["items"]) == 1

        detail = get_attempt_detail(context, 2)
        assert detail["adott_valasz"] == "hibás"

        patterns = summarize_answer_patterns(context, limit=2)
        assert patterns["bad_attempt_count"] == 2
        assert patterns["top_wrong_answers"][0]["answer"] == "hibás"

        risk = summarize_review_risk(context)
        assert risk["overview"]["id"] == "m_tool_01"
        assert "likely_issue" in risk

        md = get_markdown_origin(context)
        assert md["csoport_kontextus"] == ""

    def test_review_agent_tools_confirmed_update_creates_new_version(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_tools_update.db"
        repo = FeladatRepository(db_path=db_path)
        feladat = Feladat.from_dict(
            {
                "id": "m_tools_update_1",
                "neh": 2,
                "szint": "4 osztályos",
                "kerdes": "Régi kérdés?",
                "helyes_valasz": "A",
                "hint": "régi hint",
                "magyarazat": "régi magyarázat",
                "reszpontozas": "régi",
                "ertekeles_megjegyzes": "régi guide",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="matek",
        )
        repo.upsert(feladat)
        repo.save_megoldas(
            feladat,
            "hibás válasz",
            Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
            felhasznalo_nev="teszt",
            hibajelezes=True,
        )

        context = {
            "meta": {"db_path": str(db_path)},
            "feladat": {"id": feladat.id},
            "sources": {},
            "attempts": {},
        }

        wrong = list_wrong_tasks(context, kind="any", user="teszt", limit=10)
        assert wrong["count"] == 1
        assert wrong["items"][0]["feladat_id"] == feladat.id

        pending = request_task_update_confirmation(
            context,
            updates={
                "kerdes": "Új kérdés?",
                "magyarazat": "új magyarázat",
                "reszpontozas": "új értékelés",
                "ertekeles_megjegyzes": "új guide",
            },
            review_note="chat update",
        )
        assert pending["status"] == "pending_confirmation"
        code = pending["confirmation_code"]

        bad_apply = apply_task_update_with_confirmation(
            context,
            confirmation_code="confirm-000000000000",
        )
        assert "error" in bad_apply

        ok_apply = apply_task_update_with_confirmation(context, confirmation_code=code)
        assert ok_apply["status"] == "updated"
        assert ok_apply["versioned"] is True
        assert ok_apply["original_id"] != ok_apply["updated_id"]

    def test_load_task_context_switches_active_task(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_tools_switch.db"
        repo = FeladatRepository(db_path=db_path)

        first = Feladat.from_dict(
            {
                "id": "m_ctx_1",
                "neh": 1,
                "szint": "4 osztályos",
                "kerdes": "Első?",
                "helyes_valasz": "A",
                "hint": "h1",
                "magyarazat": "m1",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="matek",
        )
        second = Feladat.from_dict(
            {
                "id": "m_ctx_2",
                "neh": 2,
                "szint": "4 osztályos",
                "kerdes": "Második?",
                "helyes_valasz": "B",
                "hint": "h2",
                "magyarazat": "m2",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="magyar",
        )
        repo.upsert(first)
        repo.upsert(second)
        repo.save_megoldas(
            second,
            "rossz",
            Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
            felhasznalo_nev="teszt",
            hibajelezes=True,
        )

        context = {
            "meta": {"db_path": str(db_path)},
            "feladat": {"id": first.id},
            "sources": {},
            "attempts": {},
            "ai_assessment": "",
        }

        loaded = load_task_context(
            context,
            feladat_id=second.id,
            include_ai_assessment=False,
        )
        assert loaded["status"] == "loaded"
        assert loaded["feladat_id"] == second.id
        assert context["feladat"]["id"] == second.id
        assert context["attempts"]["total"] >= 1

    def test_request_task_update_confirmation_requires_updates_payload(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_tools_validation.db"
        repo = FeladatRepository(db_path=db_path)
        feladat = Feladat.from_dict(
            {
                "id": "m_validation_1",
                "neh": 1,
                "szint": "4 osztalyos",
                "kerdes": "K?",
                "helyes_valasz": "V",
                "hint": "H",
                "magyarazat": "M",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="matek",
        )
        repo.upsert(feladat)

        context = {
            "meta": {"db_path": str(db_path)},
            "feladat": {"id": feladat.id},
            "sources": {},
            "attempts": {},
        }

        result = request_task_update_confirmation(
            context,
            review_note="only note, no updates",
        )
        assert "error" in result
        assert result.get("required") == ["updates"]

    def test_resolve_task_flag_clears_flags_without_versioned_update(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_tools_flag_resolution.db"
        repo = FeladatRepository(db_path=db_path)
        feladat = Feladat.from_dict(
            {
                "id": "m_flag_resolution_1",
                "neh": 2,
                "szint": "4 osztályos",
                "kerdes": "Kérdés?",
                "helyes_valasz": "A",
                "hint": "h",
                "magyarazat": "m",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="matek",
        )
        repo.upsert(feladat)

        repo.save_megoldas(
            feladat,
            "rossz #1",
            Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
            felhasznalo_nev="diak",
            hibajelezes=True,
        )
        first_attempt_id = repo.get_latest_megoldas_id(feladat.id, felhasznalo_nev="diak", adott_valasz="rossz #1")
        assert first_attempt_id is not None

        repo.save_megoldas(
            feladat,
            "rossz #2",
            Ertekeles(helyes=False, pont=0, visszajelzes="nem jó"),
            felhasznalo_nev="diak",
            hibajelezes=True,
        )
        second_attempt_id = repo.get_latest_megoldas_id(feladat.id, felhasznalo_nev="diak", adott_valasz="rossz #2")
        assert second_attempt_id is not None

        context = {
            "meta": {"db_path": str(db_path)},
            "feladat": {"id": feladat.id},
            "sources": {},
            "attempts": {
                "total": 2,
                "good_count": 0,
                "bad_count": 2,
                "good_recent": [],
                "bad_recent": [
                    {"id": first_attempt_id, "hibajelezes": True},
                    {"id": second_attempt_id, "hibajelezes": True},
                ],
            },
        }

        result = resolve_task_flag(
            context,
            reviewer="ReviewerA",
            resolution_note="false positive",
            attempt_ids=[first_attempt_id],
        )

        assert result["status"] == "resolved"
        assert result["scope"] == "selected"
        assert result["cleared_count"] == 1
        assert result["cleared_attempt_ids"] == [first_attempt_id]

        with Session(repo._engine) as sess:
            rec_first = sess.get(MegoldasRecord, first_attempt_id)
            rec_second = sess.get(MegoldasRecord, second_attempt_id)
            assert rec_first is not None and rec_first.hibajelezes is False
            assert rec_second is not None and rec_second.hibajelezes is True

        assert len(repo.all(include_archivalt=True)) == 1
        saved = repo.get(feladat.id)
        assert saved is not None
        assert saved.review_elvegezve is True
        assert saved.review_megjegyzes == "false positive"

        events = repo.get_interakciok("ReviewerA", tipus=InterakcioTipus.HIBAJELEZES_FELOLDVA)
        assert events
        meta = json.loads(events[0].meta or "{}")
        assert meta["source"] == "review_chat_tool"
        assert meta["cleared_count"] == 1

    def test_resolve_task_flag_requires_reviewer(self, tmp_path: Path) -> None:
        db_path = tmp_path / "review_tools_flag_validation.db"
        repo = FeladatRepository(db_path=db_path)
        feladat = Feladat.from_dict(
            {
                "id": "m_flag_resolution_validation_1",
                "neh": 1,
                "szint": "4 osztályos",
                "kerdes": "Kérdés?",
                "helyes_valasz": "A",
                "hint": "h",
                "magyarazat": "m",
                "feladat_tipus": "nyilt_valasz",
                "max_pont": 1,
            },
            targy="matek",
        )
        repo.upsert(feladat)

        context = {
            "meta": {"db_path": str(db_path)},
            "feladat": {"id": feladat.id},
            "sources": {},
            "attempts": {},
        }

        result = resolve_task_flag(context, reviewer="   ")
        assert "error" in result
        assert result.get("required") == ["reviewer"]


class TestSourceSearchTools:
    """Test source search and retrieval tools in review context."""

    def test_search_source_text_missing_params(self) -> None:
        """Test search_source_text validation."""
        context = {
            "meta": {},
            "feladat": {},
            "sources": {},
            "attempts": {},
        }

        # Empty file_path
        result = search_source_text(context, file_path="", query="test")
        assert "error" in result

        # Empty query
        result = search_source_text(context, file_path="text/A8_2020_2_ut.txt", query="")
        assert "error" in result

    def test_search_source_text_works(self) -> None:
        """Test search_source_text with valid parameters."""
        context = {"meta": {}, "feladat": {}, "sources": {}, "attempts": {}}

        # Search for task 8
        result = search_source_text(
            context,
            file_path="text/A8_2020_2_ut.txt",
            query="8.",
            max_hits=5,
        )

        assert "status" in result
        assert "file_path" in result
        assert "match_count" in result
        assert "matches" in result

    def test_get_source_window_missing_params(self) -> None:
        """Test get_source_window validation."""
        context = {"meta": {}, "feladat": {}, "sources": {}, "attempts": {}}

        # Empty file_path
        result = get_source_window(context, file_path="", start_line=1, end_line=5)
        assert "error" in result

        # Invalid line numbers
        result = get_source_window(
            context, file_path="text/A8_2020_2_ut.txt", start_line=5, end_line=1
        )
        assert "error" in result

    def test_get_source_window_works(self) -> None:
        """Test get_source_window retrieval."""
        context = {"meta": {}, "feladat": {}, "sources": {}, "attempts": {}}

        result = get_source_window(
            context, file_path="text/A8_2020_2_ut.txt", start_line=1, end_line=10
        )

        assert "status" in result
        assert "lines" in result or "error" in result

    def test_locate_task_in_sources_missing_context(self, tmp_path: Path) -> None:
        """Test locate_task_in_sources without source paths."""
        context = {
            "meta": {"db_path": str(tmp_path / "test.db")},
            "feladat": {"id": "mag4_2020_2_8_a"},
            "sources": {},
            "attempts": {},
        }

        result = locate_task_in_sources(context, feladat_id="mag4_2020_2_8_a")

        assert "error" in result
        assert "source file paths" in result.get("error", "").lower()

    def test_locate_task_in_sources_invalid_id(self) -> None:
        """Test locate_task_in_sources with invalid feladat_id."""
        context = {
            "meta": {},
            "feladat": {
                "fl_szoveg_path": "text/A8_2020_2_fl.txt",
                "ut_szoveg_path": "text/A8_2020_2_ut.txt",
            },
            "sources": {},
            "attempts": {},
        }

        result = locate_task_in_sources(context, feladat_id="invalid_id")

        assert result["status"] == "error"
        assert "parse" in result.get("error", "").lower()

    def test_locate_task_in_sources_valid(self) -> None:
        """Test locate_task_in_sources with valid task ID."""
        context = {
            "meta": {},
            "feladat": {
                "fl_szoveg_path": "text/A8_2020_2_fl.txt",
                "ut_szoveg_path": "text/A8_2020_2_ut.txt",
            },
            "sources": {},
            "attempts": {},
        }

        result = locate_task_in_sources(context, feladat_id="mag4_2020_2_8_a")

        assert result["status"] == "ok"
        assert result["task_number"] == "8"
        assert result["subtask_letter"] == "a"
        assert "task_sheet" in result
        assert "guide" in result

    def test_validate_guide_excerpt_missing_excerpt(self, tmp_path: Path) -> None:
        """Test validate_guide_excerpt without stored excerpt."""
        context = {
            "meta": {"db_path": str(tmp_path / "test.db")},
            "feladat": {"ut_szoveg_path": "text/A8_2020_2_ut.txt"},
            "sources": {},
            "attempts": {},
        }

        result = validate_guide_excerpt(context)

        assert "error" in result
        assert "excerpt" in result.get("error", "").lower()

    def test_validate_guide_excerpt_with_excerpt(self) -> None:
        """Test validate_guide_excerpt with stored excerpt."""
        context = {
            "meta": {},
            "feladat": {"ut_szoveg_path": "text/A8_2020_2_ut.txt"},
            "sources": {"utmutato_kivonat": "8. Feladat"},  # Sample excerpt
            "attempts": {},
        }

        result = validate_guide_excerpt(context)

        assert "status" in result
        assert "confidence" in result
        assert "stored_excerpt_preview" in result
