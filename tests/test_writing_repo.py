from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from felvi_games.writing_repo import WritingPracticeRepository
from felvi_games.writing_review import ReviewCriterion, ReviewGuide
from felvi_games.writing_tasks import WritingPracticeTask


def _guide() -> ReviewGuide:
    return ReviewGuide(
        guide_id="test-guide-v1",
        name="Test review guide",
        criteria=(ReviewCriterion("content", "Content", 3, "Assess relevant ideas."),),
    )


def _task() -> WritingPracticeTask:
    return WritingPracticeTask(
        task_id="test-writing-task",
        title="Test writing task",
        prompt="Test prompt.",
        genre="argumentative",
        source_kind="practice",
        source_reference="test source",
        prompt_source_file="test-prompt.txt",
        guide_source_file="test-guide.txt",
        exam_year=2026,
        variant=2,
        task_number="10",
        min_sentences=2,
        max_sentences=5,
        min_sentences_for_any_points=4,
        suggested_time_min=10,
        suggested_time_max=15,
        guide=_guide(),
    )


def test_writing_practice_session_persists_revisions_and_review(tmp_path) -> None:
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    task = _task()
    session = repo.create_session("Learner A", task)

    first = repo.save_revision(session.id, "Learner A", "First synthetic draft.")
    second = repo.save_revision(session.id, "Learner A", "Revised synthetic draft.")
    reviewed = repo.save_review(
        session.id,
        second.id,
        "Learner A",
        json.dumps({"total_score": 2}),
    )
    revisions = repo.list_revisions(session.id, "Learner A")

    assert session.status == "active"
    assert json.loads(session.guide_json)["guide_id"] == task.guide.guide_id
    assert json.loads(session.task_metadata_json)["source_reference"] == "test source"
    assert [revision.id for revision in revisions] == [first.id, second.id]
    assert [revision.draft_text for revision in revisions] == [
        "First synthetic draft.",
        "Revised synthetic draft.",
    ]
    assert reviewed.feedback_json is not None
    assert json.loads(revisions[1].feedback_json or "{}") == {"total_score": 2}


def test_writing_practice_session_pause_resume_excludes_paused_time(tmp_path, monkeypatch) -> None:
    import felvi_games.writing_repo as writing_repo

    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(writing_repo, "_utc_now", lambda: now)
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    session = repo.create_session("Learner A", _task())

    for _ in range(40):
        now += timedelta(seconds=1)
        repo.checkpoint_active_time(session.id, "Learner A")
    repo.pause_session(session.id, "Learner A")
    paused = repo.get_session(session.id, "Learner A")
    assert paused is not None
    assert paused.status == "paused"
    assert paused.active_seconds == 40

    now += timedelta(minutes=5)
    repo.resume_session(session.id, "Learner A")
    for _ in range(60):
        now += timedelta(seconds=1)
        repo.checkpoint_active_time(session.id, "Learner A")
    repo.submit_session(session.id, "Learner A")
    submitted = repo.get_session(session.id, "Learner A")

    assert submitted is not None
    assert submitted.status == "submitted"
    assert submitted.active_seconds == 100


def test_writing_practice_timer_caps_unobserved_gaps(tmp_path, monkeypatch) -> None:
    import felvi_games.writing_repo as writing_repo

    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(writing_repo, "_utc_now", lambda: now)
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    session = repo.create_session("Learner A", _task())

    now += timedelta(hours=2)

    assert repo.elapsed_seconds(session.id, "Learner A") == 2
    assert repo.checkpoint_active_time(session.id, "Learner A") == 2
    paused = repo.pause_session(session.id, "Learner A")
    assert paused.active_seconds == 2


def test_writing_practice_sessions_are_scoped_to_local_profile(tmp_path) -> None:
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    session = repo.create_session("Learner A", _task())

    assert repo.get_session(session.id, "Learner B") is None
    assert repo.list_sessions("Learner B") == []
    assert repo.list_messages(session.id, "Learner B") == []


def test_used_task_ids_include_all_sessions_for_one_profile(tmp_path) -> None:
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    tasks = [replace(_task(), task_id=f"task-{index}") for index in range(25)]
    for task in tasks:
        repo.create_session("Learner A", task)
    repo.create_session("Learner B", tasks[0])

    assert repo.used_task_ids("Learner A") == {task.task_id for task in tasks}
    assert repo.used_task_ids("Learner B") == {tasks[0].task_id}


def test_writing_practice_chat_messages_persist_in_order_and_are_profile_scoped(tmp_path) -> None:
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    session = repo.create_session("Learner A", _task())

    user_message = repo.save_chat_message(session.id, "Learner A", "user", "Mivel kezdjem?")
    assistant_message = repo.save_chat_message(
        session.id,
        "Learner A",
        "assistant",
        "Kezdd az álláspontoddal. Melyik érvet választod?",
    )
    saved = repo.list_messages(session.id, "Learner A")

    assert [message.id for message in saved] == [user_message.id, assistant_message.id]
    assert [message.role for message in saved] == ["user", "assistant"]
    assert saved[1].content.startswith("Kezdd az álláspontoddal")
    assert repo.list_messages(session.id, "Learner B") == []


def test_writing_practice_chat_rejects_invalid_role_or_empty_message(tmp_path) -> None:
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    session = repo.create_session("Learner A", _task())

    with pytest.raises(ValueError, match="role"):
        repo.save_chat_message(session.id, "Learner A", "system", "Invalid role")
    with pytest.raises(ValueError, match="empty"):
        repo.save_chat_message(session.id, "Learner A", "user", "  ")


def test_unchanged_draft_is_not_added_as_a_duplicate_revision(tmp_path) -> None:
    repo = WritingPracticeRepository(tmp_path / "writing-practice.db")
    session = repo.create_session("Learner A", _task())

    first = repo.save_revision(session.id, "Learner A", "Same draft.")
    repeated = repo.save_revision(session.id, "Learner A", "Same draft.")

    assert repeated.id == first.id
    assert len(repo.list_revisions(session.id, "Learner A")) == 1
