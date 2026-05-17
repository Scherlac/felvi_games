from __future__ import annotations

from dataclasses import dataclass

from felvi_games.usage_metrics import (
    aggregate_attempt_rows,
    classify_attempt,
    compute_attempt_streak,
)


@dataclass
class _Row:
    helyes: bool
    pont: int
    elapsed_sec: float | None = None


def test_classify_attempt_full_partial_wrong() -> None:
    full = classify_attempt(helyes=True, pont=2)
    partial = classify_attempt(helyes=False, pont=1)
    wrong = classify_attempt(helyes=False, pont=0)

    assert full.full_correct is True
    assert full.partial_correct is False

    assert partial.full_correct is False
    assert partial.partial_correct is True

    assert wrong.full_correct is False
    assert wrong.partial_correct is False


def test_aggregate_attempt_rows_counts_partial_and_avg() -> None:
    rows = [
        _Row(helyes=True, pont=2, elapsed_sec=20.0),
        _Row(helyes=False, pont=1, elapsed_sec=40.0),
        _Row(helyes=False, pont=0, elapsed_sec=None),
    ]

    agg = aggregate_attempt_rows(rows)

    assert agg.attempts == 3
    assert agg.correct == 1
    assert agg.partial == 1
    assert agg.points == 3
    assert agg.avg_sec == 30.0


def test_compute_attempt_streak_keeps_partial_breaks_on_zero_point() -> None:
    rows = [
        _Row(helyes=True, pont=1),
        _Row(helyes=False, pont=1),  # partial keeps streak
        _Row(helyes=True, pont=1),
        _Row(helyes=False, pont=0),  # zero-point wrong breaks streak
        _Row(helyes=True, pont=1),
    ]

    streak = compute_attempt_streak(rows)
    assert streak.best == 2
    assert streak.current == 1
