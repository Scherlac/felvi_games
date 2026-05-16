from __future__ import annotations

from pathlib import Path

from felvi_games.db import FeladatRepository
from felvi_games.models import Ertekeles, Feladat
from felvi_games.review_agent_tools import (
    apply_task_update_with_confirmation,
    get_attempt_detail,
    get_markdown_origin,
    get_source_excerpt,
    get_task_overview,
    list_attempts,
    list_wrong_tasks,
    request_task_update_confirmation,
    summarize_answer_patterns,
    summarize_review_risk,
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
