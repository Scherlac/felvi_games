from __future__ import annotations

from streamlit.testing.v1 import AppTest

from felvi_games.writing_repo import WritingPracticeRepository
from felvi_games.writing_review import CriterionReview, ReviewCriterion, ReviewGuide, WritingReview
from felvi_games.writing_tasks import WritingPracticeTask


def _render_writing_app(user_name: str, db_path: str) -> None:
    from pathlib import Path

    from felvi_games.writing_repo import WritingPracticeRepository
    from felvi_games.writing_ui import render_writing_practice_page

    render_writing_practice_page(user_name, repository=WritingPracticeRepository(Path(db_path)))


def _click_button_key(app: AppTest, key: str) -> None:
    next(button for button in app.button if button.key == key).click().run()


def _task() -> WritingPracticeTask:
    guide = ReviewGuide(
        guide_id="test-official-guide-v1",
        name="Test official marking guide",
        criteria=(
            ReviewCriterion("content", "Content", 3, "Check relevant ideas."),
            ReviewCriterion("structure", "Structure", 3, "Check organization."),
            ReviewCriterion("style", "Style", 1, "Check style."),
            ReviewCriterion("spelling", "Spelling", 2, "Check spelling."),
            ReviewCriterion("appearance", "Appearance", 1, "Typed text only.", assessable=False),
        ),
    )
    return WritingPracticeTask(
        task_id="test-writing-task",
        title="Test writing task",
        prompt="Write about games.",
        genre="argumentative",
        source_kind="official",
        source_reference="A8_2026_2 Task 10 (test fixture)",
        prompt_source_file="text/test-prompt.txt",
        guide_source_file="text/test-guide.txt",
        exam_year=2026,
        variant=2,
        task_number="10",
        min_sentences=10,
        max_sentences=12,
        min_sentences_for_any_points=4,
        suggested_time_min=10,
        suggested_time_max=15,
        guide=guide,
    )


def test_writing_workspace_saves_draft_chat_and_review_for_reopen(tmp_path, monkeypatch) -> None:
    repository = WritingPracticeRepository(tmp_path / "writing-practice.db")
    task = _task()
    review = WritingReview(
        guide_id=task.guide.guide_id,
        criteria=(
            CriterionReview("content", 2, 3, "Mindkét lehetőségről írt.", "Mindkét módon", False),
            CriterionReview("structure", 2, 3, "Világos a szerkezet.", "A végén", False),
            CriterionReview("style", 1, 1, "Megfelelő a stílus.", "Saját álláspontom", False),
            CriterionReview("spelling", 2, 2, "Kevés a helyesírási hiba.", "hasznos", False),
            CriterionReview("appearance", None, 1, "Gépelt szövegből nem értékelhető.", "", False),
        ),
    )
    called = []
    coached = []

    def fake_review(
        task_prompt: str,
        draft: str,
        guide,
        *,
        sentence_count: int | None = None,
        min_sentences_for_any_points: int | None = None,
    ) -> WritingReview:
        called.append(
            (task_prompt, draft, guide.guide_id, sentence_count, min_sentences_for_any_points)
        )
        return review

    def fake_coach(task_prompt: str, draft: str, guide, history, learner_message: str) -> str:
        coached.append((task_prompt, draft, guide.guide_id, history, learner_message))
        if len(coached) == 1:
            raise RuntimeError("temporary provider failure")
        return "Kezdd az álláspontoddal. Melyik érvet írod le először?"

    monkeypatch.setattr("felvi_games.writing_ui.review_writing_submission", fake_review)
    monkeypatch.setattr("felvi_games.writing_ui.coach_writing_chat", fake_coach)
    monkeypatch.setattr("felvi_games.writing_ui.load_reference_writing_task", lambda: task)
    db_path = str(tmp_path / "writing-practice.db")
    app = AppTest.from_function(
        _render_writing_app,
        args=("Local learner", db_path),
    ).run()
    assert called == []
    assert coached == []

    _click_button_key(app, "writing_practice_start")
    session = repository.list_sessions("Local learner")[0]
    draft_key = f"writing_draft_{session.id}"
    draft_text = (
        "Szerintem mindkét játéktípus hasznos. A társasjátékot együtt játszhatjuk. "
        "Közben beszélgetünk egymással. Megtanulunk szabályokat követni. "
        "Az online játékot otthon is elérhetjük. Sokféle játék közül választhatunk. "
        "Néha azonban túl sok időt töltünk a képernyő előtt. A társasjátékhoz barátok kellenek. "
        "Én mindkét formát szeretem. A legjobb, ha változatosan játszunk."
    )
    assert next(widget for widget in app.text_area if widget.key == draft_key).value == ""
    next(widget for widget in app.text_area if widget.key == draft_key).set_value(draft_text).run()

    tutor_input_key = f"writing_tutor_input_{session.id}"
    next(widget for widget in app.text_area if widget.key == tutor_input_key).set_value(
        "Mivel folytassam?"
    )
    _click_button_key(app, f"writing_tutor_send_{session.id}")

    assert len(coached) == 1
    assert coached[0][1] == draft_text
    assert coached[0][4] == "Mivel folytassam?"
    assert any("temporary provider failure" in element.value for element in app.error)
    assert [message.role for message in repository.list_messages(session.id, "Local learner")] == [
        "user"
    ]
    _click_button_key(app, f"writing_tutor_retry_{session.id}")
    assert len(coached) == 2
    saved_messages = repository.list_messages(session.id, "Local learner")
    assert [message.role for message in saved_messages] == ["user", "assistant"]

    submit_key = f"writing_practice_submit_{session.id}"
    _click_button_key(app, submit_key)
    assert len(called) == 1
    assert called[0][1] == draft_text
    assert called[0][3:] == (10, 4)

    saved = repository.list_sessions("Local learner")
    assert len(saved) == 1
    assert saved[0].status == "submitted"
    revisions = repository.list_revisions(saved[0].id, "Local learner")
    assert revisions[-1].draft_text == draft_text
    assert revisions[-1].feedback_json

    reopened = AppTest.from_function(
        _render_writing_app,
        args=("Local learner", db_path),
    ).run()
    open_saved = next(button for button in reopened.button if button.key == f"writing_practice_open_{saved[0].id}")
    open_saved.click().run()

    assert any(
        element.value == "Gyakorló értékelés — nem hivatalos vizsgaeredmény"
        for element in reopened.subheader
    )
    assert any(
        element.value == "Tanuló által megadott mondatszám (cím nélkül): 10"
        for element in reopened.caption
    )
    assert next(widget for widget in reopened.text_area if widget.key == draft_key).value == draft_text
    assert any(element.value == "Mivel folytassam?" for element in reopened.markdown)
    assert any(
        element.value == "Kezdd az álláspontoddal. Melyik érvet írod le először?"
        for element in reopened.markdown
    )
    assert len(called) == 1
