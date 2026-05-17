"""Utility tools for the teacher analytics chat agent."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from felvi_games.db import FeladatRepository
from felvi_games.teacher_chat import build_teacher_chat_context


def get_teacher_scope(context: dict[str, Any]) -> dict[str, Any]:
    student = context.get("student", {})
    scope = context.get("scope", {})
    summary = context.get("summary", {})
    return {
        "student": student,
        "scope": scope,
        "summary": summary,
    }


def list_recent_attempts(
    context: dict[str, Any],
    *,
    kind: str = "all",
    limit: int = 20,
    slow_threshold_sec: float = 180.0,
) -> dict[str, Any]:
    attempts = list(context.get("attempts") or [])

    if kind == "correct":
        selected = [a for a in attempts if bool(a.get("helyes"))]
    elif kind == "partial":
        selected = [a for a in attempts if bool(a.get("partial"))]
    elif kind == "wrong":
        selected = [a for a in attempts if bool(a.get("wrong"))]
    elif kind == "flagged":
        selected = [a for a in attempts if bool(a.get("hibajelezes"))]
    elif kind == "slow":
        selected = [
            a
            for a in attempts
            if isinstance(a.get("elapsed_sec"), (int, float))
            and float(a["elapsed_sec"]) >= float(slow_threshold_sec)
        ]
    else:
        selected = attempts

    capped = selected[: max(1, int(limit))]
    return {
        "kind": kind,
        "count": len(selected),
        "items": capped,
    }


def get_attempt_detail(context: dict[str, Any], *, attempt_id: int) -> dict[str, Any]:
    for item in list(context.get("attempts") or []):
        if int(item.get("id", -1)) == int(attempt_id):
            return item
    return {"error": f"Attempt not found: {attempt_id}"}


def list_related_tasks(
    context: dict[str, Any],
    *,
    kind: str = "all",
    limit: int = 20,
    min_attempts: int = 1,
) -> dict[str, Any]:
    rows = [r for r in list(context.get("related_tasks") or []) if int(r.get("attempts", 0)) >= int(min_attempts)]

    if kind == "weak":
        rows = sorted(rows, key=lambda r: (float(r.get("partial_or_better_pct", 0.0)), -int(r.get("wrong", 0)), -int(r.get("attempts", 0))))
    elif kind == "strong":
        rows = sorted(rows, key=lambda r: (-float(r.get("partial_or_better_pct", 0.0)), -float(r.get("points_ratio_pct", 0.0)), -int(r.get("attempts", 0))))
    elif kind == "frequent":
        rows = sorted(rows, key=lambda r: (-int(r.get("attempts", 0)), -int(r.get("wrong", 0))))
    elif kind == "unreliable":
        rows = sorted(rows, key=lambda r: (-int(r.get("wrong", 0)), float(r.get("partial_or_better_pct", 0.0))))

    return {
        "kind": kind,
        "count": len(rows),
        "items": rows[: max(1, int(limit))],
    }


def summarize_strengths_weaknesses(
    context: dict[str, Any],
    *,
    top_n: int = 6,
) -> dict[str, Any]:
    tasks = list(context.get("related_tasks") or [])
    if not tasks:
        return {
            "strengths": [],
            "weaknesses": [],
            "note": "Nincs elegendő adat az elemzéshez.",
        }

    strengths = [
        t for t in tasks
        if int(t.get("attempts", 0)) >= 2
        and float(t.get("partial_or_better_pct", 0.0)) >= 80.0
    ]
    strengths = sorted(strengths, key=lambda t: (-float(t.get("partial_or_better_pct", 0.0)), -float(t.get("points_ratio_pct", 0.0)), -int(t.get("attempts", 0))))

    weaknesses = [
        t for t in tasks
        if int(t.get("attempts", 0)) >= 1
        and (float(t.get("partial_or_better_pct", 0.0)) < 60.0 or int(t.get("wrong", 0)) > int(t.get("correct", 0)))
    ]
    weaknesses = sorted(weaknesses, key=lambda t: (float(t.get("partial_or_better_pct", 0.0)), -int(t.get("wrong", 0)), -int(t.get("attempts", 0))))

    difficulty_counter = Counter(int(t.get("neh", 0)) for t in weaknesses)
    weak_by_type = Counter((t.get("feladat_tipus") or "ismeretlen") for t in weaknesses)

    return {
        "strengths": strengths[: max(1, int(top_n))],
        "weaknesses": weaknesses[: max(1, int(top_n))],
        "weak_difficulty_distribution": dict(difficulty_counter),
        "weak_task_types": dict(weak_by_type),
    }


def recommend_personalized_training(
    context: dict[str, Any],
    *,
    max_recommendations: int = 8,
) -> dict[str, Any]:
    profile = summarize_strengths_weaknesses(context, top_n=max_recommendations)
    weaknesses = list(profile.get("weaknesses") or [])
    strengths = list(profile.get("strengths") or [])

    recommendations: list[dict[str, Any]] = []
    for item in weaknesses[: max(1, int(max_recommendations))]:
        fid = item.get("feladat_id")
        attempts = int(item.get("attempts", 0))
        wrong = int(item.get("wrong", 0))
        p_or_b = float(item.get("partial_or_better_pct", 0.0))
        difficulty = int(item.get("neh", 0))

        if p_or_b < 35.0:
            drill = "alapok+mintafeladat"
        elif p_or_b < 60.0:
            drill = "celzott gyakorlás"
        else:
            drill = "időzített gyakorlás"

        recommendations.append(
            {
                "feladat_id": fid,
                "priority": "high" if wrong >= 2 else "medium",
                "focus": drill,
                "why": f"attempts={attempts}, wrong={wrong}, partial_or_better={p_or_b:.1f}%, neh={difficulty}",
            }
        )

    if not recommendations and strengths:
        for item in strengths[: max(1, int(max_recommendations // 2 or 1))]:
            recommendations.append(
                {
                    "feladat_id": item.get("feladat_id"),
                    "priority": "maintenance",
                    "focus": "mix and retention",
                    "why": "Stabil erősség, fenntartó ismétlés javasolt.",
                }
            )

    return {
        "student": context.get("student"),
        "scope": context.get("scope"),
        "recommendations": recommendations,
    }


def recommend_exam_assignment_order(
    context: dict[str, Any],
    *,
    strategy: str = "maximize_score",
    limit: int = 15,
) -> dict[str, Any]:
    tasks = list(context.get("related_tasks") or [])
    if not tasks:
        return {"strategy": strategy, "order": [], "note": "Nincs elég feladatadat."}

    scored: list[dict[str, Any]] = []
    for t in tasks:
        p_or_b = float(t.get("partial_or_better_pct", 0.0))
        points_ratio = float(t.get("points_ratio_pct", 0.0))
        attempts = int(t.get("attempts", 0))
        neh = int(t.get("neh", 0))
        avg_elapsed = float(t.get("avg_elapsed_sec") or 0.0)

        if strategy == "confidence_first":
            score = (0.55 * p_or_b) + (0.30 * points_ratio) + (0.10 * min(attempts, 6) * 10) - (0.05 * min(neh, 10) * 10)
        elif strategy == "time_efficient":
            speed_bonus = max(0.0, 100.0 - min(avg_elapsed, 300.0) / 3.0)
            score = (0.45 * p_or_b) + (0.25 * points_ratio) + (0.30 * speed_bonus)
        else:
            score = (0.5 * points_ratio) + (0.35 * p_or_b) + (0.10 * min(attempts, 6) * 10) - (0.05 * min(neh, 10) * 10)

        scored.append(
            {
                "feladat_id": t.get("feladat_id"),
                "priority_score": round(score, 1),
                "neh": neh,
                "attempts": attempts,
                "partial_or_better_pct": round(p_or_b, 1),
                "points_ratio_pct": round(points_ratio, 1),
                "avg_elapsed_sec": t.get("avg_elapsed_sec"),
                "rationale": "High expected yield first" if score >= 65 else "Later in exam order",
            }
        )

    scored = sorted(scored, key=lambda x: x["priority_score"], reverse=True)
    return {
        "strategy": strategy,
        "order": scored[: max(1, int(limit))],
    }


def reload_teacher_context(
    context: dict[str, Any],
    *,
    user: str,
    targy: str,
    szint: str = "mind",
    attempts_limit: int = 200,
) -> dict[str, Any]:
    repo = _repo_from_context(context)
    new_context = build_teacher_chat_context(
        repo,
        user=user,
        targy=targy,
        szint=szint,
        attempts_limit=max(1, int(attempts_limit)),
    )
    new_context["meta"] = dict(context.get("meta") or {})

    context.clear()
    context.update(new_context)

    return {
        "status": "loaded",
        "student": new_context.get("student"),
        "scope": new_context.get("scope"),
        "summary": new_context.get("summary"),
    }


def list_available_students(
    context: dict[str, Any],
    *,
    contains: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    repo = _repo_from_context(context)
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from felvi_games.db import FelhasznaloRecord

    q = (contains or "").strip().lower()
    with Session(repo._engine) as session:
        rows = list(session.scalars(select(FelhasznaloRecord).order_by(FelhasznaloRecord.nev.asc())).all())

    names = [r.nev for r in rows if (not q or q in r.nev.lower())]
    return {
        "count": len(names),
        "items": names[: max(1, int(limit))],
    }


def _repo_from_context(context: dict[str, Any]) -> FeladatRepository:
    meta = context.get("meta") or {}
    db_path = str(meta.get("db_path", "")).strip()
    if not db_path:
        raise ValueError("Missing context.meta.db_path; cannot access repository.")
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"DB path does not exist: {path}")
    return FeladatRepository(path)
