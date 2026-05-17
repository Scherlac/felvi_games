from __future__ import annotations

from pathlib import Path

from felvi_games.db import FeladatRepository
from felvi_games.models import Ertekeles, Feladat
from felvi_games.teacher_agent_tools import (
    get_attempt_detail,
    get_teacher_scope,
    list_available_students,
    list_recent_attempts,
    list_related_tasks,
    recommend_exam_assignment_order,
    recommend_personalized_training,
    reload_teacher_context,
    summarize_strengths_weaknesses,
)
from felvi_games.teacher_chat import build_teacher_chat_context


def _seed_teacher_data(repo: FeladatRepository, *, user: str = "Lóri") -> None:
    repo.get_or_create_felhasznalo(user)

    task_a = Feladat.from_dict(
        {
            "id": "mat_teacher_1",
            "neh": 2,
            "szint": "4 osztályos",
            "kerdes": "2+2?",
            "helyes_valasz": "4",
            "hint": "alap",
            "magyarazat": "összeadás",
            "feladat_tipus": "nyilt_valasz",
            "max_pont": 1,
        },
        targy="matek",
    )
    task_b = Feladat.from_dict(
        {
            "id": "mat_teacher_2",
            "neh": 6,
            "szint": "4 osztályos",
            "kerdes": "7*8?",
            "helyes_valasz": "56",
            "hint": "szorzótábla",
            "magyarazat": "szorzás",
            "feladat_tipus": "nyilt_valasz",
            "max_pont": 2,
        },
        targy="matek",
    )
    task_c = Feladat.from_dict(
        {
            "id": "mag_teacher_1",
            "neh": 3,
            "szint": "4 osztályos",
            "kerdes": "Melyik szó főnév?",
            "helyes_valasz": "asztal",
            "hint": "szófaj",
            "magyarazat": "főnév",
            "feladat_tipus": "tobbvalasztos",
            "max_pont": 1,
        },
        targy="magyar",
    )

    repo.upsert(task_a)
    repo.upsert(task_b)
    repo.upsert(task_c)

    repo.save_megoldas(
        task_a,
        "4",
        Ertekeles(helyes=True, pont=1, visszajelzes="ok"),
        felhasznalo_nev=user,
        elapsed_sec=45,
    )
    repo.save_megoldas(
        task_a,
        "5",
        Ertekeles(helyes=False, pont=0, visszajelzes="nem"),
        felhasznalo_nev=user,
        elapsed_sec=61,
    )
    repo.save_megoldas(
        task_b,
        "50",
        Ertekeles(helyes=False, pont=1, visszajelzes="részleges"),
        felhasznalo_nev=user,
        elapsed_sec=210,
        hibajelezes=True,
    )
    repo.save_megoldas(
        task_b,
        "49",
        Ertekeles(helyes=False, pont=0, visszajelzes="nem"),
        felhasznalo_nev=user,
        elapsed_sec=240,
    )

    repo.save_megoldas(
        task_c,
        "asztal",
        Ertekeles(helyes=True, pont=1, visszajelzes="ok"),
        felhasznalo_nev=user,
        elapsed_sec=30,
    )


def test_build_teacher_chat_context_and_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "teacher_chat.db"
    repo = FeladatRepository(db_path=db_path)
    _seed_teacher_data(repo)

    context = build_teacher_chat_context(
        repo,
        user="Lóri",
        targy="matek",
        szint="4 osztályos",
        attempts_limit=50,
    )

    assert context["student"]["name"] == "Lóri"
    assert context["scope"]["targy"] == "matek"
    assert context["summary"]["attempts_total"] == 4
    assert context["summary"]["correct"] == 1
    assert context["summary"]["partial"] == 1
    assert context["summary"]["wrong"] == 2

    scope = get_teacher_scope(context)
    assert scope["summary"]["distinct_tasks"] == 2


def test_teacher_agent_tools_attempts_tasks_and_recommendations(tmp_path: Path) -> None:
    db_path = tmp_path / "teacher_tools.db"
    repo = FeladatRepository(db_path=db_path)
    _seed_teacher_data(repo)

    context = build_teacher_chat_context(repo, user="Lóri", targy="matek", attempts_limit=50)

    attempts_wrong = list_recent_attempts(context, kind="wrong", limit=10)
    assert attempts_wrong["count"] == 2

    attempts_slow = list_recent_attempts(context, kind="slow", limit=10, slow_threshold_sec=200)
    assert attempts_slow["count"] >= 2

    first_attempt_id = int(context["attempts"][0]["id"])
    detail = get_attempt_detail(context, attempt_id=first_attempt_id)
    assert detail["id"] == first_attempt_id

    weak_tasks = list_related_tasks(context, kind="weak", limit=5)
    assert weak_tasks["count"] >= 1

    profile = summarize_strengths_weaknesses(context, top_n=5)
    assert "weaknesses" in profile

    training = recommend_personalized_training(context, max_recommendations=5)
    assert len(training["recommendations"]) >= 1

    order = recommend_exam_assignment_order(context, strategy="maximize_score", limit=5)
    assert len(order["order"]) >= 1


def test_teacher_agent_tools_reload_context_and_list_students(tmp_path: Path) -> None:
    db_path = tmp_path / "teacher_reload.db"
    repo = FeladatRepository(db_path=db_path)
    _seed_teacher_data(repo, user="Lóri")
    _seed_teacher_data(repo, user="Lackó")

    context = build_teacher_chat_context(repo, user="Lóri", targy="matek", attempts_limit=50)
    context["meta"] = {"db_path": str(db_path)}

    students = list_available_students(context, contains="ló", limit=10)
    assert students["count"] >= 1

    loaded = reload_teacher_context(
        context,
        user="Lóri",
        targy="magyar",
        szint="4 osztályos",
        attempts_limit=50,
    )
    assert loaded["status"] == "loaded"
    assert loaded["scope"]["targy"] == "magyar"
    assert int(loaded["summary"]["attempts_total"]) == 1
