from __future__ import annotations

from felvi_games.writing_tasks import (
    _reference_guide,
    estimate_sentence_count,
    load_reference_writing_task,
)


def test_reference_task_loads_prompt_metadata_and_task_specific_guide(tmp_path) -> None:
    prompt_path = tmp_path / "exam-task.txt"
    guide_path = tmp_path / "exam-guide.txt"
    prompt_path.write_text(
        "10. Játékokról írj!       a\n"
        "Mindkét típus mellett fogalmazz meg 2 érvet! 10–12 mondat       b\n"
        "Hivatkozz személyes élményedre!       c\n"
        "Figyelem! Fewer than four sentences cannot be assessed.\n",
        encoding="utf-8",
    )
    guide_path.write_text(
        "10. Tartalom\n"
        "A szöveg szerkezete\n"
        "Stílusa, szóhasználata\n"
        "Helyesírás\n"
        "Külalak, íráskép\n"
        "A 4-nél kevesebb mondatból álló szöveg pontozása.\n",
        encoding="utf-8",
    )

    task = load_reference_writing_task(prompt_path, guide_path)

    assert task.task_id == "A8_2026_2_MNy2_10"
    assert task.source_kind == "official"
    assert task.prompt == (
        "Játékokról írj! Mindkét típus mellett fogalmazz meg 2 érvet! "
        "10–12 mondat Hivatkozz személyes élményedre!"
    )
    assert task.metadata()["source_reference"].startswith("A8_2026_2_fl.txt")
    assert task.metadata()["min_sentences_for_any_points"] == 4
    assert task.metadata()["title_counts_as_sentence"] is False
    assert task.guide.assessable_max_score == 9
    assert task.guide.criteria[-1].criterion_id == "appearance"
    assert not task.guide.criteria[-1].assessable


def test_reference_guide_prompts_for_complete_hungarian_error_scan() -> None:
    instructions = {
        criterion.criterion_id: criterion.instructions
        for criterion in _reference_guide().criteria
    }

    assert "de" in instructions["spelling"]
    assert "ha" in instructions["spelling"]
    assert "mert" in instructions["spelling"]
    assert "mellett" in instructions["spelling"]
    assert "melletük" in instructions["spelling"]
    assert "quotation marks" in instructions["spelling"]
    assert "telómon" in instructions["style"]
    assert "unatkozok" in instructions["style"]


def test_sentence_count_estimate_handles_closing_quotes_and_empty_text() -> None:
    assert estimate_sentence_count("") == 0
    assert estimate_sentence_count('Első mondat. „Második mondat!”') == 2
