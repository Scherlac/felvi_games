"""Verified writing-task sources and their task-specific review guides."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from felvi_games.config import resolve_asset
from felvi_games.writing_review import ReviewCriterion, ReviewGuide

REFERENCE_PROMPT_SOURCE = "text/A8_2026_2_fl.txt"
REFERENCE_GUIDE_SOURCE = "text/A8_2026_2_ut.txt"


@dataclass(frozen=True)
class WritingPracticeTask:
    task_id: str
    title: str
    prompt: str
    genre: str
    source_kind: Literal["official", "practice"]
    source_reference: str
    prompt_source_file: str
    guide_source_file: str
    exam_year: int
    variant: int
    task_number: str
    min_sentences: int
    max_sentences: int
    min_sentences_for_any_points: int
    suggested_time_min: int
    suggested_time_max: int
    guide: ReviewGuide

    def metadata(self) -> dict[str, str | int | bool]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "genre": self.genre,
            "source_kind": self.source_kind,
            "source_reference": self.source_reference,
            "prompt_source_file": self.prompt_source_file,
            "guide_source_file": self.guide_source_file,
            "exam_year": self.exam_year,
            "variant": self.variant,
            "task_number": self.task_number,
            "min_sentences": self.min_sentences,
            "max_sentences": self.max_sentences,
            "min_sentences_for_any_points": self.min_sentences_for_any_points,
            "title_counts_as_sentence": False,
            "suggested_time_min": self.suggested_time_min,
            "suggested_time_max": self.suggested_time_max,
        }


def extract_task_prompt(source_text: str) -> str:
    """Extract Task 10 without copying the rest of the exam page."""
    start = re.search(r"(?m)^\s*10\.\s+", source_text)
    if start is None:
        raise ValueError("The official exam source does not contain a Task 10 heading.")
    body_start = start.end()
    warning = re.search(r"(?mi)^\s*Figyelem!", source_text[body_start:])
    if warning is None:
        raise ValueError("Task 10 in the official exam source has no closing instruction marker.")

    lines = source_text[body_start : body_start + warning.start()].splitlines()
    cleaned_lines = [
        re.sub(r"\s{2,}[a-e]\s*$", "", line).strip()
        for line in lines
    ]
    prompt = re.sub(r"\s+", " ", " ".join(line for line in cleaned_lines if line)).strip()
    required_phrases = ("2 érvet", "10–12 mondat", "személyes élmény")
    if not all(phrase in prompt for phrase in required_phrases):
        raise ValueError("Task 10 source does not match the reviewed 2026 MNy2 requirements.")
    return prompt


def estimate_sentence_count(draft: str) -> int:
    """Estimate sentence count; learners can correct the result in the workspace."""
    text = draft.strip()
    if not text:
        return 0
    return len(re.findall(r"[.!?]+(?:[\"'»”)]*)?(?=\s|$)", text))


def _reference_guide() -> ReviewGuide:
    short_text_rule = "Fewer than four sentences means zero points for every criterion."
    return ReviewGuide(
        guide_id="A8-2026-2-MNy2-Task10-v1",
        name="2026 MNy2 Task 10 marking guide",
        criteria=(
            ReviewCriterion(
                "content",
                "Content",
                3,
                f"{short_text_rule} Assess topic relevance, thoughtful development, a personal "
                "experience, two valid arguments for each game type, and the required 10-sentence "
                "minimum. Award 3 when all full-credit requirements are met; 2 for a relevant "
                "response with one weaker/inconsistent idea, only 2+1 arguments, no personal "
                "experience, or 8–9 sentences; 1 for an underdeveloped relevant response with "
                "only one argument for each side or 5–7 sentences; otherwise 0. The learner's "
                "opinion must not affect the score.",
            ),
            ReviewCriterion(
                "structure",
                "Structure",
                3,
                f"{short_text_rule} Award 3 for a complete, clearly divided, logical text with "
                "proportional introduction, body, and conclusion at 10 or more sentences; 2 when "
                "one structural requirement is weak; 1 when two are weak but the text has at least "
                "four sentences; 0 below four sentences or for an incoherent list.",
            ),
            ReviewCriterion(
                "style",
                "Style and word choice",
                1,
                f"{short_text_rule} Award 1 when wording is topic-appropriate, standard, varied, "
                "and grammatically correct at 10 or more sentences; otherwise 0. Flag informal "
                "register such as 'telómon' as an optional formal-style improvement, not a spelling "
                "error. Do not label the common colloquial 'unatkozok' as categorically incorrect; "
                "you may suggest 'unatkozom' as a more formal alternative.",
            ),
            ReviewCriterion(
                "spelling",
                "Spelling",
                2,
                f"{short_text_rule} Apply the source guide's Hungarian spelling categories: 2 "
                "points for at most one minor listed error and at most two punctuation errors at "
                "10 or more sentences; 1 point for at most two listed errors, one isolated severe "
                "error, or three to five punctuation errors when at least four sentences are "
                "present; otherwise 0. Check the complete text for missing commas before "
                "contrastive 'de' and clause-introducing 'ha', 'mert', and 'hogy'; check doubled "
                "consonants and inflected word forms (for example, 'mellet'/'mellett' and "
                "'melletük'/'mellettük'); and review capitalization, quotation marks, and suffix "
                "attachment for named games. Explain concrete comma improvements as formative "
                "advice, but do not count complex-sentence punctuation errors toward points when "
                "the source guide excludes them.",
            ),
            ReviewCriterion(
                "appearance",
                "Appearance",
                1,
                "Handwriting, legibility, margins, and correction layout cannot be assessed from "
                "typed text.",
                assessable=False,
            ),
        ),
    )


def load_reference_writing_task(
    prompt_path: Path | None = None,
    guide_path: Path | None = None,
) -> WritingPracticeTask:
    """Load the verified exam prompt from configured assets and bind its own guide."""
    prompt_source = prompt_path or resolve_asset(REFERENCE_PROMPT_SOURCE)
    guide_source = guide_path or resolve_asset(REFERENCE_GUIDE_SOURCE)
    source_text = prompt_source.read_text(encoding="utf-8")
    marking_guide = guide_source.read_text(encoding="utf-8")
    required_guide_markers = (
        "10.",
        "Tartalom",
        "A szöveg szerkezete",
        "Stílusa, szóhasználata",
        "Helyesírás",
        "Külalak, íráskép",
        "4-nél kevesebb mondatból",
    )
    if not all(marker in marking_guide for marker in required_guide_markers):
        raise ValueError("The marking-guide source does not contain the reviewed Task 10 criteria.")

    return WritingPracticeTask(
        task_id="A8_2026_2_MNy2_10",
        title="Traditional board games and online games",
        prompt=extract_task_prompt(source_text),
        genre="argumentative",
        source_kind="official",
        source_reference="A8_2026_2_fl.txt Task 10; A8_2026_2_ut.txt Item 10",
        prompt_source_file=REFERENCE_PROMPT_SOURCE,
        guide_source_file=REFERENCE_GUIDE_SOURCE,
        exam_year=2026,
        variant=2,
        task_number="10",
        min_sentences=10,
        max_sentences=12,
        min_sentences_for_any_points=4,
        suggested_time_min=10,
        suggested_time_max=15,
        guide=_reference_guide(),
    )
