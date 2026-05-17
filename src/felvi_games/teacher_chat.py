"""Teacher chat context builder for student-focused analysis."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from felvi_games.db import FeladatRecord, FeladatRepository, FelhasznaloRecord, MegoldasRecord


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return 100.0 * num / den


def build_teacher_chat_context(
    repo: FeladatRepository,
    *,
    user: str,
    targy: str,
    szint: str | None = None,
    attempts_limit: int = 200,
) -> dict[str, Any]:
    """Build context for teacher analysis chat for one user and one subject."""
    user_name = str(user or "").strip()
    subject = str(targy or "").strip().lower()
    level = str(szint or "").strip()
    if not user_name:
        raise ValueError("Missing user name.")
    if not subject:
        raise ValueError("Missing targy.")

    with Session(repo._engine) as session:
        user_rec = session.scalar(
            select(FelhasznaloRecord).where(FelhasznaloRecord.nev == user_name)
        )
        if user_rec is None:
            raise ValueError(f"Unknown user: {user_name}")

        stmt = (
            select(
                MegoldasRecord.id,
                MegoldasRecord.feladat_id,
                MegoldasRecord.felhasznalo_nev,
                MegoldasRecord.adott_valasz,
                MegoldasRecord.helyes,
                MegoldasRecord.pont,
                MegoldasRecord.elapsed_sec,
                MegoldasRecord.segitseg_kert,
                MegoldasRecord.hibajelezes,
                MegoldasRecord.created_at,
                FeladatRecord.targy,
                FeladatRecord.szint,
                FeladatRecord.neh,
                FeladatRecord.max_pont,
                FeladatRecord.feladat_tipus,
                FeladatRecord.kerdes,
                FeladatRecord.hint,
                FeladatRecord.magyarazat,
            )
            .join(FeladatRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
            .where(MegoldasRecord.felhasznalo_nev == user_name)
            .where(FeladatRecord.targy == subject)
            .order_by(MegoldasRecord.created_at.desc(), MegoldasRecord.id.desc())
            .limit(max(1, int(attempts_limit)))
        )
        if level and level != "mind":
            stmt = stmt.where(FeladatRecord.szint == level)

        rows = session.execute(stmt).all()

    attempts: list[dict[str, Any]] = []
    by_task: dict[str, dict[str, Any]] = {}
    daily_points: dict[str, int] = defaultdict(int)

    for row in rows:
        pont = int(row.pont or 0)
        max_pont = int(row.max_pont or 0)
        helyes = bool(row.helyes)
        partial = (not helyes) and pont > 0
        wrong = (not helyes) and pont <= 0
        elapsed = float(row.elapsed_sec) if isinstance(row.elapsed_sec, (int, float)) else None
        created = row.created_at.isoformat() if row.created_at else None
        day = row.created_at.date().isoformat() if row.created_at else "unknown"

        attempt_item = {
            "id": int(row.id),
            "feladat_id": str(row.feladat_id),
            "felhasznalo": str(row.felhasznalo_nev),
            "targy": str(row.targy),
            "szint": str(row.szint),
            "neh": int(row.neh or 0),
            "max_pont": max_pont,
            "pont": pont,
            "helyes": helyes,
            "partial": partial,
            "wrong": wrong,
            "elapsed_sec": elapsed,
            "segitseg_kert": bool(row.segitseg_kert),
            "hibajelezes": bool(row.hibajelezes),
            "created_at": created,
            "adott_valasz": row.adott_valasz,
            "feladat_tipus": row.feladat_tipus,
            "kerdes": (row.kerdes or "")[:240],
        }
        attempts.append(attempt_item)

        task = by_task.setdefault(
            str(row.feladat_id),
            {
                "feladat_id": str(row.feladat_id),
                "targy": str(row.targy),
                "szint": str(row.szint),
                "neh": int(row.neh or 0),
                "max_pont": max_pont,
                "feladat_tipus": row.feladat_tipus,
                "kerdes": (row.kerdes or "")[:240],
                "hint": row.hint,
                "magyarazat": row.magyarazat,
                "attempts": 0,
                "correct": 0,
                "partial": 0,
                "wrong": 0,
                "points": 0,
                "points_possible": 0,
                "elapsed_values": [],
                "last_seen": created,
            },
        )

        task["attempts"] += 1
        task["correct"] += 1 if helyes else 0
        task["partial"] += 1 if partial else 0
        task["wrong"] += 1 if wrong else 0
        task["points"] += pont
        task["points_possible"] += max_pont
        if elapsed is not None:
            task["elapsed_values"].append(elapsed)
        task["last_seen"] = created

        daily_points[day] += pont

    task_items: list[dict[str, Any]] = []
    for item in by_task.values():
        attempts_n = int(item["attempts"])
        points = int(item["points"])
        points_possible = int(item["points_possible"])
        correct = int(item["correct"])
        partial_count = int(item["partial"])
        item["accuracy_pct"] = round(_safe_ratio(correct, attempts_n), 1)
        item["partial_or_better_pct"] = round(_safe_ratio(correct + partial_count, attempts_n), 1)
        item["points_ratio_pct"] = round(_safe_ratio(points, points_possible), 1)
        vals = item.pop("elapsed_values")
        item["avg_elapsed_sec"] = round(mean(vals), 1) if vals else None
        task_items.append(item)

    task_items.sort(key=lambda x: (x["attempts"], x["wrong"], -x["accuracy_pct"]), reverse=True)

    total_attempts = len(attempts)
    total_correct = sum(1 for a in attempts if a["helyes"])
    total_partial = sum(1 for a in attempts if a["partial"])
    total_wrong = sum(1 for a in attempts if a["wrong"])
    total_points = sum(int(a["pont"]) for a in attempts)
    total_possible = sum(int(a["max_pont"]) for a in attempts)
    elapsed_values = [float(a["elapsed_sec"]) for a in attempts if isinstance(a["elapsed_sec"], (int, float))]

    weak_tasks = [
        t
        for t in task_items
        if (int(t["attempts"]) >= 2 and float(t["partial_or_better_pct"]) < 60.0)
        or (int(t["attempts"]) >= 1 and int(t["wrong"]) >= int(t["correct"]) + int(t["partial"]))
    ]
    weak_tasks = sorted(weak_tasks, key=lambda t: (t["partial_or_better_pct"], -t["wrong"], -t["attempts"]))

    strong_tasks = [
        t
        for t in task_items
        if int(t["attempts"]) >= 2 and float(t["partial_or_better_pct"]) >= 80.0 and float(t["points_ratio_pct"]) >= 70.0
    ]
    strong_tasks = sorted(strong_tasks, key=lambda t: (-t["partial_or_better_pct"], -t["points_ratio_pct"], -t["attempts"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "student": {
            "id": int(user_rec.id),
            "name": user_rec.nev,
            "created_at": user_rec.created_at.isoformat() if user_rec.created_at else None,
        },
        "scope": {
            "targy": subject,
            "szint": level or "mind",
            "attempts_limit": max(1, int(attempts_limit)),
        },
        "summary": {
            "attempts_total": total_attempts,
            "correct": total_correct,
            "partial": total_partial,
            "wrong": total_wrong,
            "accuracy_pct": round(_safe_ratio(total_correct, total_attempts), 1),
            "partial_or_better_pct": round(_safe_ratio(total_correct + total_partial, total_attempts), 1),
            "points": total_points,
            "points_possible": total_possible,
            "points_ratio_pct": round(_safe_ratio(total_points, total_possible), 1),
            "avg_elapsed_sec": round(mean(elapsed_values), 1) if elapsed_values else None,
            "distinct_tasks": len(task_items),
        },
        "daily_points": [
            {"day": day, "points": pts}
            for day, pts in sorted(daily_points.items())
        ],
        "attempts": attempts,
        "related_tasks": task_items,
        "derived": {
            "weak_task_ids": [t["feladat_id"] for t in weak_tasks[:20]],
            "strong_task_ids": [t["feladat_id"] for t in strong_tasks[:20]],
        },
    }
