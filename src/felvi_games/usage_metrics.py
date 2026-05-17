from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AttemptOutcome:
    full_correct: bool
    partial_correct: bool
    points: int


@dataclass(frozen=True)
class AttemptAggregate:
    attempts: int
    correct: int
    partial: int
    points: int
    avg_sec: float | None


@dataclass(frozen=True)
class StreakStats:
    current: int
    best: int


def classify_attempt(*, helyes: bool, pont: int | float | None) -> AttemptOutcome:
    pts = int(pont or 0)
    full = bool(helyes)
    partial = (not full) and pts > 0
    return AttemptOutcome(full_correct=full, partial_correct=partial, points=pts)


def aggregate_attempt_rows(rows: list[Any]) -> AttemptAggregate:
    attempts = len(rows)
    correct = 0
    partial = 0
    points = 0
    elapsed_sum = 0.0
    elapsed_count = 0

    for row in rows:
        outcome = classify_attempt(
            helyes=bool(getattr(row, "helyes", False)),
            pont=getattr(row, "pont", 0),
        )
        points += outcome.points
        if outcome.full_correct:
            correct += 1
        elif outcome.partial_correct:
            partial += 1

        elapsed = getattr(row, "elapsed_sec", None)
        if isinstance(elapsed, (int, float)):
            elapsed_sum += float(elapsed)
            elapsed_count += 1

    avg_sec = (elapsed_sum / elapsed_count) if elapsed_count else None
    return AttemptAggregate(
        attempts=attempts,
        correct=correct,
        partial=partial,
        points=points,
        avg_sec=avg_sec,
    )


def compute_attempt_streak(rows: list[Any]) -> StreakStats:
    streak = 0
    best = 0
    for row in rows:
        outcome = classify_attempt(
            helyes=bool(getattr(row, "helyes", False)),
            pont=getattr(row, "pont", 0),
        )
        if outcome.full_correct:
            streak += 1
        elif outcome.points == 0:
            streak = 0
        best = max(best, streak)

    return StreakStats(current=streak, best=best)


def is_same_local_day(*, ts: datetime, local_day: datetime.date, local_tz: Any) -> bool:
    ts_local = (
        ts.replace(tzinfo=timezone.utc).astimezone(local_tz)
        if ts.tzinfo is None
        else ts.astimezone(local_tz)
    )
    return ts_local.date() == local_day


def is_ghost_session(*, megoldott: int | None, ended_at: datetime | None) -> bool:
    return int(megoldott or 0) == 0 and ended_at is None
