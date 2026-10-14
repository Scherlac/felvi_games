"""Verified writing-task sources and their task-specific review guides."""

from __future__ import annotations

import random
import re
from collections.abc import Sequence, Set
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from felvi_games.config import get_exams_dir, resolve_asset
from felvi_games.writing_review import ReviewCriterion, ReviewGuide

REFERENCE_PROMPT_SOURCE = "text/A8_2026_2_fl.txt"
REFERENCE_GUIDE_SOURCE = "text/A8_2026_2_ut.txt"
_TASK_BLOCK_RE = re.compile(r"^\s{0,4}(?P<number>\d{1,2})\.\s{3,}")
_LEGACY_GUIDE_HEADING_RE = re.compile(r"^\s{0,4}10\.\s+\S")
_ANSWER_LINE_RE = re.compile(r"\.{10,}")
_PAGE_FOOTER_RE = re.compile(r"(?i)\s*\[Oldal\s+\d+\].*$")
_PAGE_HEADER_RE = re.compile(
    r"(?i)\s*\d{1,2}\.\s*évfolyam\s*[–—-].*\bfeladatlap\b.*$"
)
_EXAM_DATE_FOOTER_RE = re.compile(
    r"(?i)(?:^|\s)(?:19|20)\d{2}\.\s+[^\W\d_]+\s+\d{1,2}\.\s*$"
)
_EXAM_PDF_SUBDIRECTORY = Path(
    "9_evfolyam",
    "Magyar nyelv felveteli feladatsorok 9. evfolyamra",
)


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
    min_sentences: int | None
    max_sentences: int | None
    min_sentences_for_any_points: int | None
    suggested_time_min: int | None
    suggested_time_max: int | None
    guide: ReviewGuide
    source_guide_text: str = ""
    source_pdf_file: str | None = None

    def metadata(self) -> dict[str, str | int | bool | None]:
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
            "source_guide_text": self.source_guide_text,
            "source_pdf_file": self.source_pdf_file,
        }


def _extract_task_block(
    source_text: str,
    task_number: int,
    *,
    allow_legacy_spacing: bool = False,
) -> tuple[str, str]:
    lines = source_text.splitlines()
    strict_matches = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _TASK_BLOCK_RE.match(line)) is not None
        and int(match.group("number")) == task_number
    ]
    if strict_matches:
        if len(strict_matches) != 1:
            raise ValueError(f"Task {task_number} has multiple main headings in the source.")
        start, heading = strict_matches[0]
    elif allow_legacy_spacing and task_number == 10:
        legacy_matches = [
            (index, _LEGACY_GUIDE_HEADING_RE.match(line))
            for index, line in enumerate(lines)
            if _LEGACY_GUIDE_HEADING_RE.match(line) is not None
        ]
        if not legacy_matches:
            raise ValueError(f"The source does not contain a Task {task_number} heading.")
        start, legacy_heading = legacy_matches[-1]
        if legacy_heading is None:
            raise ValueError(f"The source does not contain a Task {task_number} heading.")
        heading = legacy_heading
    else:
        raise ValueError(f"The source does not contain a main Task {task_number} heading.")

    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if _TASK_BLOCK_RE.match(lines[index]) is not None
        ),
        len(lines),
    )
    block_lines = lines[start:end]
    first_line = block_lines[0]
    body_first_line = first_line[heading.end() :]
    body_lines = [body_first_line, *block_lines[1:]]
    return "\n".join(block_lines).strip(), "\n".join(body_lines).strip()


def extract_task_prompt(source_text: str) -> str:
    """Extract the main Task 10 block using the exam's main-heading spacing."""
    _, task_body = _extract_task_block(source_text, 10)
    warning = re.search(r"(?mi)^\s*Figyelem!", task_body)
    if warning is not None:
        task_body = task_body[: warning.start()]

    lines = task_body.splitlines()
    cleaned_lines = []
    for line in lines:
        line = re.sub(r"\s{2,}[a-e]\s*$", "", line)
        line = _ANSWER_LINE_RE.sub(" ", line)
        line = _PAGE_FOOTER_RE.sub("", line)
        line = _PAGE_HEADER_RE.sub("", line)
        line = _EXAM_DATE_FOOTER_RE.sub("", line).strip()
        if line:
            cleaned_lines.append(line)
    prompt = re.sub(r"\s+", " ", " ".join(line for line in cleaned_lines if line)).strip()
    if not prompt:
        raise ValueError("Task 10 in the official exam source is empty.")
    return prompt


def extract_task_guide(source_text: str) -> str:
    """Extract the matching Task 10 guide, including legacy single-space headings."""
    task_block, _ = _extract_task_block(
        source_text,
        10,
        allow_legacy_spacing=True,
    )
    return task_block


def estimate_sentence_count(draft: str) -> int:
    """Estimate sentence count; learners can correct the result in the workspace."""
    text = draft.strip()
    if not text:
        return 0
    return len(re.findall(r"[.!?]+(?:[\"'»”)]*)?(?=\s|$)", text))


def _sentence_range(prompt: str) -> tuple[int | None, int | None]:
    matches = list(
        re.finditer(
            r"(?i)(?<!\d)(\d{1,2})\s*[-–−]\s*(\d{1,2})\s*mondat(?:ból|os|ot)?",
            prompt,
        )
    )
    if len(matches) == 1:
        return int(matches[0].group(1)), int(matches[0].group(2))

    minimums = list(
        re.finditer(r"(?i)legalább\s+(\d{1,2})\s*(?:egész\s+)?mondat", prompt)
    )
    if len(minimums) == 1:
        return int(minimums[0].group(1)), None
    return None, None


def _source_pdf_file(task_stem: str) -> str | None:
    exams_root = get_exams_dir()
    pdf_path = exams_root / _EXAM_PDF_SUBDIRECTORY / f"{task_stem}_fl.pdf"
    if not pdf_path.is_file():
        return None
    return str(pdf_path.relative_to(exams_root))


def resolve_writing_task_pdf(source_pdf_file: str | None) -> Path | None:
    if source_pdf_file is None:
        return None
    return get_exams_dir() / source_pdf_file


def _modern_source_guide(stem: str, exam_year: int, source_guide_text: str) -> ReviewGuide:
    source_context = (
        "Az eredeti javítási útmutató tartalmi követelményeit és elfogadott megoldásait "
        "használd a feladat teljesítésének ellenőrzéséhez. A benne szereplő történeti "
        "pontszámokat és pontsávokat hagyd figyelmen kívül; a pontozást kizárólag a jelen "
        "útmutató szempontjai és max_points értékei határozzák meg.\n\n"
        f"Eredeti Task 10 javítási útmutató:\n{source_guide_text}"
    )
    return ReviewGuide(
        guide_id=f"{stem}-MNy2-Task10-practice-v1",
        name=f"{exam_year}. évi feladat modern gyakorló értékelése",
        criteria=(
            ReviewCriterion(
                "content",
                "Tartalom és feladatteljesítés",
                3,
                f"{source_context}\n\nÉrtékeld a téma kifejtését és a promptban kért "
                "tartalmi elemeket, például az érvek számát, az összehasonlítást, a választott "
                "álláspontot, a személyes élményt, a megadott címet vagy szövegtípust. Csak "
                "azokat kérd számon, amelyeket ez a konkrét feladat vagy útmutató előír.",
            ),
            ReviewCriterion(
                "structure",
                "A szöveg szerkezete",
                3,
                "Értékeld az átlátható felépítést, a gondolatok sorrendjét, a kapcsolódásokat "
                "és a feladat terjedelméhez illő bevezetést, kifejtést és lezárást. Rövid "
                "funkcionális szövegeknél a műfajnak megfelelő tagolást vedd figyelembe.",
            ),
            ReviewCriterion(
                "style",
                "Stílus és szóhasználat",
                1,
                "Értékeld a korosztálynak, a feladat műfajának és a címzettnek megfelelő, "
                "világos és természetes magyar megfogalmazást.",
            ),
            ReviewCriterion(
                "spelling",
                "Helyesírás és központozás",
                2,
                "Értékeld a magyar helyesírást, nyelvhelyességet és központozást. Idézz "
                "konkrét javítható példákat; ne minősíts választható stílusváltozatot "
                "kategorikus helyesírási hibának.",
            ),
            ReviewCriterion(
                "appearance",
                "Külalak, íráskép",
                1,
                "Kézírás, olvashatóság, margó és vizuális elrendezés gépelt szövegből nem "
                "értékelhető.",
                assessable=False,
            ),
        ),
    )


def _reference_guide() -> ReviewGuide:
    short_text_rule = "Fewer than four sentences means zero points for every criterion."
    return ReviewGuide(
        guide_id="A8-2026-2-MNy2-Task10-v1",
        name="2026-os MNy2, 10. feladat javítási útmutató",
        criteria=(
            ReviewCriterion(
                "content",
                "Tartalom",
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
                "A szöveg szerkezete",
                3,
                f"{short_text_rule} Award 3 for a complete, clearly divided, logical text with "
                "proportional introduction, body, and conclusion at 10 or more sentences; 2 when "
                "one structural requirement is weak; 1 when two are weak but the text has at least "
                "four sentences; 0 below four sentences or for an incoherent list.",
            ),
            ReviewCriterion(
                "style",
                "Stílus és szóhasználat",
                1,
                f"{short_text_rule} Award 1 when wording is topic-appropriate, standard, varied, "
                "and grammatically correct at 10 or more sentences; otherwise 0. Flag informal "
                "register such as 'telómon' as an optional formal-style improvement, not a spelling "
                "error. Do not label the common colloquial 'unatkozok' as categorically incorrect; "
                "you may suggest 'unatkozom' as a more formal alternative.",
            ),
            ReviewCriterion(
                "spelling",
                "Helyesírás",
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
                "Külalak, íráskép",
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
    source_guide_text = extract_task_guide(marking_guide)
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
        title="Társasjáték vagy online játék",
        prompt=extract_task_prompt(source_text),
        genre="argumentative",
        source_kind="official",
        source_reference=(
            "A8_2026_2_fl.txt, 10. feladat; "
            "A8_2026_2_ut.txt, 10. feladat javítási útmutató"
        ),
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
        source_guide_text=source_guide_text,
        source_pdf_file=_source_pdf_file("A8_2026_2"),
    )


def _load_source_writing_task(prompt_path: Path, guide_path: Path) -> WritingPracticeTask:
    prompt_file = prompt_path.name
    match = re.fullmatch(r"A8_(\d{4})_(\d+)_fl\.txt", prompt_file)
    if match is None:
        raise ValueError(f"Unsupported writing-task source filename: {prompt_file}")
    exam_year = int(match.group(1))
    variant = int(match.group(2))
    stem = f"A8_{exam_year}_{variant}"
    prompt = extract_task_prompt(prompt_path.read_text(encoding="utf-8"))
    source_guide_text = extract_task_guide(guide_path.read_text(encoding="utf-8"))
    min_sentences, max_sentences = _sentence_range(prompt)

    return WritingPracticeTask(
        task_id=f"{stem}_MNy2_10",
        title=f"{exam_year}. évi felvételi – {variant}. változat, 10. feladat",
        prompt=prompt,
        genre="writing",
        source_kind="official",
        source_reference=(
            f"{stem}_fl.txt, 10. feladat; "
            f"{stem}_ut.txt, 10. feladat javítási útmutató"
        ),
        prompt_source_file=f"text/{stem}_fl.txt",
        guide_source_file=f"text/{stem}_ut.txt",
        exam_year=exam_year,
        variant=variant,
        task_number="10",
        min_sentences=min_sentences,
        max_sentences=max_sentences,
        min_sentences_for_any_points=None,
        suggested_time_min=None,
        suggested_time_max=None,
        guide=_modern_source_guide(stem, exam_year, source_guide_text),
        source_guide_text=source_guide_text,
        source_pdf_file=_source_pdf_file(stem),
    )


def load_writing_task_bank(source_dir: Path | None = None) -> tuple[WritingPracticeTask, ...]:
    """Load every configured A8 Task 10 prompt with its matching marking guide."""
    if source_dir is None:
        return _load_configured_writing_task_bank()
    return _load_writing_task_bank_from_directory(source_dir)


@lru_cache(maxsize=1)
def _load_configured_writing_task_bank() -> tuple[WritingPracticeTask, ...]:
    """Cache network-backed configured sources for the lifetime of the app process."""
    return _load_writing_task_bank_from_directory(resolve_asset("text"))


def _load_writing_task_bank_from_directory(root: Path) -> tuple[WritingPracticeTask, ...]:
    prompt_paths = sorted(root.glob("A8_*_fl.txt"))
    if not prompt_paths:
        raise FileNotFoundError(f"No A8 writing-task sources were found in {root}.")

    tasks = []
    for prompt_path in prompt_paths:
        stem = prompt_path.name.removesuffix("_fl.txt")
        guide_path = prompt_path.with_name(f"{stem}_ut.txt")
        if not guide_path.is_file():
            raise FileNotFoundError(f"Missing matching marking guide: {guide_path}")
        if stem == "A8_2026_2":
            task = load_reference_writing_task(prompt_path, guide_path)
        else:
            task = _load_source_writing_task(prompt_path, guide_path)
        tasks.append(task)

    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Writing-task source filenames produce duplicate task ids.")
    return tuple(tasks)


def choose_next_writing_task(
    tasks: Sequence[WritingPracticeTask],
    used_task_ids: Set[str],
    previous_task_id: str | None = None,
) -> WritingPracticeTask:
    """Randomly choose an unseen task, restarting the cycle only after all are used."""
    if not tasks:
        raise ValueError("The writing-task bank is empty.")

    available = [task for task in tasks if task.task_id not in used_task_ids]
    if not available:
        available = list(tasks)
        if len(available) > 1:
            next_cycle = [task for task in available if task.task_id != previous_task_id]
            if next_cycle:
                available = next_cycle
    return random.choice(available)
