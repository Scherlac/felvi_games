"""Utility tools for the interactive review agent.

These helpers are intentionally pure and context-driven so the Chainlit agent
can request focused slices of the loaded review context on demand.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def get_task_overview(context: dict[str, Any]) -> dict[str, Any]:
    feladat = context.get("feladat", {})
    attempts = context.get("attempts", {})
    return {
        "id": feladat.get("id"),
        "targy": feladat.get("targy"),
        "szint": feladat.get("szint"),
        "ev": feladat.get("ev"),
        "valtozat": feladat.get("valtozat"),
        "feladat_sorszam": feladat.get("feladat_sorszam"),
        "feladat_tipus": feladat.get("feladat_tipus"),
        "max_pont": feladat.get("max_pont"),
        "kerdes": feladat.get("kerdes"),
        "helyes_valasz": feladat.get("helyes_valasz"),
        "elfogadott_valaszok": feladat.get("elfogadott_valaszok"),
        "magyarazat": feladat.get("magyarazat"),
        "stats": {
            "total": attempts.get("total", 0),
            "good_count": attempts.get("good_count", 0),
            "bad_count": attempts.get("bad_count", 0),
        },
        "ai_assessment": context.get("ai_assessment", ""),
    }


def get_source_excerpt(context: dict[str, Any], *, source: str = "both") -> dict[str, str]:
    sources = context.get("sources", {})
    if source == "task":
        return {"feladatlap_kivonat": str(sources.get("feladatlap_kivonat", ""))}
    if source == "guide":
        return {"utmutato_kivonat": str(sources.get("utmutato_kivonat", ""))}
    return {
        "feladatlap_kivonat": str(sources.get("feladatlap_kivonat", "")),
        "utmutato_kivonat": str(sources.get("utmutato_kivonat", "")),
    }


def _select_attempts(context: dict[str, Any], *, kind: str) -> list[dict[str, Any]]:
    attempts = context.get("attempts", {})
    if kind == "good":
        return list(attempts.get("good_recent", []))
    if kind == "bad":
        return list(attempts.get("bad_recent", []))
    if kind == "flagged":
        return [a for a in attempts.get("bad_recent", []) if a.get("hibajelezes")]
    return list(attempts.get("good_recent", [])) + list(attempts.get("bad_recent", []))


def list_attempts(context: dict[str, Any], *, kind: str = "all", limit: int = 10) -> dict[str, Any]:
    selected = _select_attempts(context, kind=kind)
    limited = selected[: max(0, limit)]
    return {
        "kind": kind,
        "limit": limit,
        "count": len(selected),
        "items": limited,
    }


def get_attempt_detail(context: dict[str, Any], attempt_id: int) -> dict[str, Any]:
    for attempt in _select_attempts(context, kind="all"):
        if int(attempt.get("id", -1)) == int(attempt_id):
            return attempt
    return {"error": f"Attempt not found: {attempt_id}"}


def summarize_answer_patterns(context: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    bad_attempts = _select_attempts(context, kind="bad")
    answers = [str(a.get("adott_valasz", "")).strip() for a in bad_attempts if a.get("adott_valasz")]
    counter = Counter(answers)
    return {
        "bad_attempt_count": len(bad_attempts),
        "top_wrong_answers": [
            {"answer": answer, "count": count}
            for answer, count in counter.most_common(max(0, limit))
        ],
    }


def summarize_review_risk(context: dict[str, Any]) -> dict[str, Any]:
    overview = get_task_overview(context)
    patterns = summarize_answer_patterns(context, limit=3)
    flagged = list_attempts(context, kind="flagged", limit=10)
    return {
        "overview": overview,
        "flagged_attempts": flagged,
        "common_wrong_answers": patterns,
        "likely_issue": (
            "The task may be too narrow or the accepted answers may not capture a valid variant."
            if flagged.get("count", 0) > 0
            else "No flagged attempts; focus on wording, guide alignment, and scoring clarity."
        ),
    }


def get_markdown_origin(context: dict[str, Any]) -> dict[str, Any]:
    """Return original markdown-like context and source extracts used for task creation."""
    feladat = context.get("feladat", {})
    sources = context.get("sources", {})
    return {
        "feladat_id": feladat.get("id"),
        "csoport_kontextus": feladat.get("kontextus", ""),
        "feladat_oldal": feladat.get("feladat_oldal"),
        "fl_szoveg_path": sources.get("fl_szoveg_path", ""),
        "ut_szoveg_path": sources.get("ut_szoveg_path", ""),
        "feladatlap_kivonat": str(sources.get("feladatlap_kivonat", "")),
        "utmutato_kivonat": str(sources.get("utmutato_kivonat", "")),
    }


def list_wrong_tasks(
    context: dict[str, Any],
    *,
    kind: str = "any",
    user: str | None = None,
    contains: str = "hibás",
    min_hibas: int = 1,
    limit: int = 20,
    include_wrong_answers: bool = False,
) -> dict[str, Any]:
    """List wrong tasks using the same DB-backed logic as CLI wrong/wrong-issues commands."""
    from felvi_games.review_check_shared import ReviewQuery, collect_wrong_task_items

    repo = _repo_from_context(context)
    merged_items = collect_wrong_task_items(
        repo,
        ReviewQuery(
            kind=kind,
            user=user,
            contains=contains,
            min_hibas=min_hibas,
            limit=limit,
        ),
        include_wrong_answers=include_wrong_answers,
    )

    return {
        "kind": kind,
        "count": len(merged_items),
        "items": merged_items,
    }


def request_task_update_confirmation(
    context: dict[str, Any],
    *,
    updates: dict[str, Any],
    review_note: str | None = None,
) -> dict[str, Any]:
    """Prepare a versioned task update and generate confirmation code.

    The update is not persisted until apply_task_update_with_confirmation() is
    called with the exact confirmation code.
    """
    repo = _repo_from_context(context)
    current = _current_feladat(context, repo)
    normalized = _normalize_updates(updates)
    if not normalized:
        return {"error": "No valid update fields were provided."}

    changed_fields = [k for k, v in normalized.items() if getattr(current, k) != v]
    if not changed_fields:
        return {"error": "The update does not change any field."}

    payload_text = json.dumps(
        {
            "feladat_id": current.id,
            "updates": normalized,
            "review_note": review_note or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    code = f"confirm-{hashlib.sha256(payload_text.encode('utf-8')).hexdigest()[:12]}"
    context["_pending_update"] = {
        "feladat_id": current.id,
        "updates": normalized,
        "review_note": review_note,
        "confirmation_code": code,
    }
    return {
        "status": "pending_confirmation",
        "feladat_id": current.id,
        "changed_fields": changed_fields,
        "updates": normalized,
        "confirmation_code": code,
        "instruction": (
            f'Ha a frissítés helyes, válaszolj pontosan ezzel: "{code}".'
        ),
    }


def apply_task_update_with_confirmation(
    context: dict[str, Any],
    *,
    confirmation_code: str,
) -> dict[str, Any]:
    """Persist the pending update only when confirmation code matches exactly."""
    pending = context.get("_pending_update")
    if not isinstance(pending, dict):
        return {"error": "No pending update. Request confirmation first."}

    expected = str(pending.get("confirmation_code", ""))
    if confirmation_code.strip() != expected:
        return {
            "error": "Invalid confirmation code.",
            "expected_pattern": "confirm-<12hex>",
        }

    repo = _repo_from_context(context)
    current = _current_feladat(context, repo)
    updates = dict(pending.get("updates") or {})
    review_note = pending.get("review_note")

    reviewed = dataclasses.replace(
        current,
        **updates,
        review_elvegezve=True,
        review_megjegyzes=(str(review_note).strip() if review_note else current.review_megjegyzes),
    )
    saved = repo.save_review(reviewed, str(review_note).strip() if review_note else None)
    changed_fields = [k for k, v in updates.items() if getattr(current, k) != v]

    # Keep chat context synced after a successful persist.
    feladat_ctx = context.setdefault("feladat", {})
    for k in (
        "id",
        "kerdes",
        "helyes_valasz",
        "elfogadott_valaszok",
        "hint",
        "magyarazat",
        "neh",
        "szint",
        "feladat_tipus",
        "max_pont",
        "abra_van",
        "reszpontozas",
        "ertekeles_megjegyzes",
    ):
        feladat_ctx[k] = getattr(saved, k)

    context.pop("_pending_update", None)
    return {
        "status": "updated",
        "original_id": current.id,
        "updated_id": saved.id,
        "versioned": saved.id != current.id,
        "changed_fields": changed_fields,
        "review_megjegyzes": saved.review_megjegyzes,
    }


def _repo_from_context(context: dict[str, Any]):
    from felvi_games.db import FeladatRepository

    meta = context.get("meta") or {}
    db_path = str(meta.get("db_path", "")).strip()
    if not db_path:
        raise ValueError("Missing context.meta.db_path; cannot access repository.")
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"DB path does not exist: {path}")
    return FeladatRepository(path)


def _current_feladat(context: dict[str, Any], repo):
    feladat_ctx = context.get("feladat") or {}
    fid = str(feladat_ctx.get("id", "")).strip()
    if not fid:
        raise ValueError("Missing context.feladat.id")
    feladat = repo.get(fid)
    if feladat is None:
        raise ValueError(f"Task not found: {fid}")
    return feladat


def _normalize_updates(updates: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(updates, dict):
        return {}

    normalized: dict[str, Any] = {}

    str_fields = (
        "kerdes",
        "helyes_valasz",
        "hint",
        "magyarazat",
        "szint",
        "feladat_tipus",
        "reszpontozas",
        "ertekeles_megjegyzes",
    )
    for field in str_fields:
        if field in updates and updates[field] is not None:
            normalized[field] = str(updates[field]).strip()

    if "elfogadott_valaszok" in updates:
        raw = updates.get("elfogadott_valaszok")
        if isinstance(raw, list):
            vals = [str(v).strip() for v in raw if str(v).strip()]
            normalized["elfogadott_valaszok"] = vals
        elif isinstance(raw, str):
            vals = [v.strip() for v in raw.split(",") if v.strip()]
            normalized["elfogadott_valaszok"] = vals

    if "max_pont" in updates:
        try:
            mp = int(updates["max_pont"])
            if mp >= 1:
                normalized["max_pont"] = mp
        except (TypeError, ValueError):
            pass

    if "neh" in updates:
        try:
            neh = int(updates["neh"])
            if neh in {1, 2, 3}:
                normalized["neh"] = neh
        except (TypeError, ValueError):
            pass

    if "abra_van" in updates:
        normalized["abra_van"] = bool(updates["abra_van"])

    return normalized