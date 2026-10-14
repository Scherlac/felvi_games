from __future__ import annotations

import pytest

from felvi_games.writing_tasks import (
    WritingPracticeTask,
    _reference_guide,
    choose_next_writing_task,
    estimate_sentence_count,
    load_reference_writing_task,
    load_writing_task_bank,
)


def test_reference_task_loads_prompt_metadata_and_task_specific_guide(tmp_path) -> None:
    prompt_path = tmp_path / "exam-task.txt"
    guide_path = tmp_path / "exam-guide.txt"
    prompt_path.write_text(
        "10.   Játékokról írj!       a\n"
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
    assert task.title == "Társasjáték vagy online játék"
    assert task.prompt == (
        "Játékokról írj! Mindkét típus mellett fogalmazz meg 2 érvet! "
        "10–12 mondat Hivatkozz személyes élményedre!"
    )
    assert task.metadata()["source_reference"].startswith("A8_2026_2_fl.txt")
    assert task.metadata()["min_sentences_for_any_points"] == 4
    assert "A 4-nél kevesebb mondatból álló szöveg" in task.source_guide_text
    assert [criterion.max_points for criterion in task.guide.criteria] == [3, 3, 1, 2, 1]
    assert task.metadata()["title_counts_as_sentence"] is False
    assert task.guide.assessable_max_score == 9
    assert task.guide.criteria[-1].criterion_id == "appearance"
    assert not task.guide.criteria[-1].assessable


def test_task_bank_pairs_main_task_blocks_and_uses_recent_rubric(tmp_path) -> None:
    prompt_2023_1 = tmp_path / "A8_2023_1_fl.txt"
    guide_2023_1 = tmp_path / "A8_2023_1_ut.txt"
    prompt_2023_1.write_text(
        "9.   Korábbi szövegértési feladat.\n"
        "10. Belső számozott részfeladat, nem a fő feladat.\n"
        "10.   Valódi múzeumos téma. Írj 10–12 mondatban!\n"
        "Figyelem! A feladatlapot ne lapozd vissza.\n",
        encoding="utf-8",
    )
    guide_2023_1.write_text(
        "9.   Előző javítási útmutató.\n"
        "10. Tartalom és elfogadható megoldások\n"
        "A régi pontsávokat kizárólag forrásként őrizzük meg.\n",
        encoding="utf-8",
    )

    prompt_2024_2 = tmp_path / "A8_2024_2_fl.txt"
    guide_2024_2 = tmp_path / "A8_2024_2_ut.txt"
    prompt_2024_2.write_text(
        "10.   Beszélgetés online vagy személyesen. Legalább 8 mondat.\n",
        encoding="utf-8",
    )
    guide_2024_2.write_text(
        "10.   Tartalom és feladatteljesítés\n"
        "A válasz foglalkozzon mindkét kommunikációs formával.\n",
        encoding="utf-8",
    )

    tasks = load_writing_task_bank(tmp_path)

    assert [task.task_id for task in tasks] == [
        "A8_2023_1_MNy2_10",
        "A8_2024_2_MNy2_10",
    ]
    assert tasks[0].prompt == "Valódi múzeumos téma. Írj 10–12 mondatban!"
    assert (tasks[0].min_sentences, tasks[0].max_sentences) == (10, 12)
    assert (tasks[1].min_sentences, tasks[1].max_sentences) == (8, None)
    assert "A régi pontsávokat" in tasks[0].source_guide_text
    assert [criterion.max_points for criterion in tasks[0].guide.criteria] == [3, 3, 1, 2, 1]
    assert tasks[0].guide.assessable_max_score == 9
    assert all(criterion.name for task in tasks for criterion in task.guide.criteria)


def test_task_bank_requires_a_matching_guide(tmp_path) -> None:
    (tmp_path / "A8_2024_1_fl.txt").write_text(
        "10.   Írj a témáról!\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="A8_2024_1_ut.txt"):
        load_writing_task_bank(tmp_path)


def test_task_selection_avoids_repeats_until_the_pool_is_exhausted(monkeypatch) -> None:
    guide = _reference_guide()
    bank = tuple(
        WritingPracticeTask(
            task_id=task_id,
            title=task_id,
            prompt="Prompt.",
            genre="writing",
            source_kind="official",
            source_reference="test source",
            prompt_source_file="test-fl.txt",
            guide_source_file="test-ut.txt",
            exam_year=2026,
            variant=index,
            task_number="10",
            min_sentences=None,
            max_sentences=None,
            min_sentences_for_any_points=None,
            suggested_time_min=None,
            suggested_time_max=None,
            guide=guide,
        )
        for index, task_id in enumerate(("one", "two", "three"), start=1)
    )
    monkeypatch.setattr("felvi_games.writing_tasks.random.choice", lambda choices: choices[0])

    used: set[str] = set()
    previous = None
    for _ in bank:
        task = choose_next_writing_task(bank, used, previous)
        assert task.task_id not in used
        used.add(task.task_id)
        previous = task.task_id

    next_cycle_task = choose_next_writing_task(bank, used, previous)
    assert next_cycle_task.task_id != previous


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
