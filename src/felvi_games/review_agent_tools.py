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
    include_wrong_answers: bool = False,
    **filters: Any,
) -> dict[str, Any]:
    """List wrong tasks using the same DB-backed logic as CLI wrong/wrong-issues commands."""
    from felvi_games.review_check_shared import ReviewQuery, collect_wrong_task_items

    kind = str(filters.get("kind", "any"))
    user_raw = filters.get("user")
    user = str(user_raw).strip() if user_raw is not None else None
    contains = str(filters.get("contains", "hibás"))
    min_hibas = max(0, int(filters.get("min_hibas", 1) or 1))
    limit = max(1, int(filters.get("limit", 20) or 20))

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


def load_task_context(
    context: dict[str, Any],
    *,
    feladat_id: str,
    attempts_limit: int = 12,
    include_ai_assessment: bool = False,
    model: str | None = None,
) -> dict[str, Any]:
    """Reload the in-chat review context for another task ID from the same DB."""
    from felvi_games.review import build_review_chat_context

    target_id = str(feladat_id or "").strip()
    if not target_id:
        return {"error": "Missing feladat_id."}

    repo = _repo_from_context(context)
    target = repo.get(target_id)
    if target is None:
        return {"error": f"Task not found: {target_id}"}

    new_context = build_review_chat_context(
        target,
        repo,
        attempts_limit=max(1, int(attempts_limit)),
        model=model,
        include_ai_assessment=bool(include_ai_assessment),
    )
    new_context["meta"] = dict(context.get("meta") or {})

    context.clear()
    context.update(new_context)

    return {
        "status": "loaded",
        "feladat_id": target.id,
        "targy": target.targy,
        "szint": target.szint,
        "attempts_total": int((new_context.get("attempts") or {}).get("total", 0)),
    }


def request_task_update_confirmation(
    context: dict[str, Any],
    *,
    updates: dict[str, Any] | None = None,
    review_note: str | None = None,
) -> dict[str, Any]:
    """Prepare a versioned task update and generate confirmation code.

    The update is not persisted until apply_task_update_with_confirmation() is
    called with the exact confirmation code.
    """
    if not isinstance(updates, dict) or not updates:
        return {
            "error": "Missing required field: updates.",
            "required": ["updates"],
            "updates_format": {
                "type": "object",
                "allowed_fields": [
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
                ],
            },
            "example": {
                "updates": {"magyarazat": "uj magyarazat"},
                "review_note": "opcionális indoklás",
            },
        }

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


def resolve_task_flag(
    context: dict[str, Any],
    *,
    reviewer: str,
    resolution_note: str | None = None,
    attempt_ids: list[int] | None = None,
    mark_reviewed: bool = True,
) -> dict[str, Any]:
    """Clear erroneous task-level or attempt-level flags without content edits."""
    reviewer_name = str(reviewer or "").strip()
    if not reviewer_name:
        return {
            "error": "Missing required field: reviewer.",
            "required": ["reviewer"],
            "example": {
                "reviewer": "moderator_nev",
                "resolution_note": "false positive flag",
                "attempt_ids": [123],
            },
        }

    repo = _repo_from_context(context)
    current = _current_feladat(context, repo)
    result = repo.resolve_hibajelezes(
        feladat_id=current.id,
        reviewer=reviewer_name,
        resolution_note=resolution_note,
        attempt_ids=attempt_ids,
        mark_reviewed=mark_reviewed,
        source="review_chat_tool",
    )

    # Keep chat context synced after moderation-only resolution.
    raw_cleared_ids = result.get("cleared_attempt_ids")
    cleared_ids = {
        int(i)
        for i in (raw_cleared_ids if isinstance(raw_cleared_ids, list) else [])
    }
    attempts_ctx = context.get("attempts")
    if isinstance(attempts_ctx, dict):
        bad_recent = attempts_ctx.get("bad_recent")
        if isinstance(bad_recent, list):
            clear_all = bool(result.get("scope") == "task")
            for item in bad_recent:
                if not isinstance(item, dict):
                    continue
                if not item.get("hibajelezes"):
                    continue
                if clear_all or int(item.get("id", -1)) in cleared_ids:
                    item["hibajelezes"] = False

    feladat_ctx = context.get("feladat")
    if isinstance(feladat_ctx, dict):
        if mark_reviewed:
            feladat_ctx["review_elvegezve"] = True
        if result.get("review_megjegyzes"):
            feladat_ctx["review_megjegyzes"] = result["review_megjegyzes"]

    return {
        "status": "resolved",
        **result,
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


def search_source_text(
    context: dict[str, Any],
    *,
    file_path: str,
    query: str,
    **search_options: Any,
) -> dict[str, Any]:
    """Search for text in original source files (task sheet or guide).
    
    Use this to verify official wording, find task sections, or check guide content.
    
    Example queries:
    - "8." to find task 8
    - "a)" to find subtask a
    - "Tavaszi felhők" to find poem title
    - "indokold" to find justification requirement
    """
    from felvi_games.source_search import search_source_text as _search_impl
    
    file_path_clean = str(file_path or "").strip()
    if not file_path_clean:
        return {
            "error": "Missing required field: file_path",
            "example": {
                "file_path": "text/A8_2020_2_ut.txt",
                "query": "8.",
            },
        }
    
    query_clean = str(query or "").strip()
    if not query_clean:
        return {
            "error": "Missing required field: query",
        }

    max_hits = max(1, int(search_options.get("max_hits", 20) or 20))
    case_sensitive = bool(search_options.get("case_sensitive", False) or False)
    context_lines = max(0, int(search_options.get("context_lines", 2) or 2))
    
    return _search_impl(
        file_path_clean,
        query_clean,
        max_hits=max_hits,
        case_sensitive=case_sensitive,
        context_lines=context_lines,
    )


def get_source_window(
    context: dict[str, Any],
    *,
    file_path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    """Retrieve a span of lines from original source files.
    
    Use this to read complete sections or verify context around search hits.
    Line numbers are 1-indexed.
    """
    from felvi_games.source_search import get_source_window as _window_impl
    
    file_path_clean = str(file_path or "").strip()
    if not file_path_clean:
        return {
            "error": "Missing required field: file_path",
        }
    
    try:
        start = int(start_line)
        end = int(end_line)
    except (TypeError, ValueError):
        return {
            "error": "start_line and end_line must be integers",
        }
    
    if start < 1 or end < 1 or start > end:
        return {
            "error": "Invalid line range; start and end must be >= 1, and start <= end",
        }
    
    return _window_impl(file_path_clean, start, end)


def locate_task_in_sources(
    context: dict[str, Any],
    *,
    feladat_id: str,
    context_lines: int = 3,
) -> dict[str, Any]:
    """Locate a task in the original source files by task/subtask ID.
    
    Attempts to find the task heading in both task sheet and guide,
    using patterns like "8." for task 8, "a)" for subtask a, etc.
    
    Use this to verify whether the current source file links are correct.
    """
    from felvi_games.source_search import find_task_in_sources as _locate_impl
    
    feladat_id_clean = str(feladat_id or "").strip()
    if not feladat_id_clean:
        return {
            "error": "Missing required field: feladat_id",
        }
    
    feladat_ctx = context.get("feladat") or {}
    fl_path = str(feladat_ctx.get("fl_szoveg_path") or "").strip()
    ut_path = str(feladat_ctx.get("ut_szoveg_path") or "").strip()
    
    if not fl_path and not ut_path:
        return {
            "error": "No source file paths in current task context",
            "hint": "Load a task using load_task_context first",
        }
    
    return _locate_impl(
        feladat_id_clean,
        task_sheet_path=fl_path or None,
        guide_path=ut_path or None,
        context_lines=max(1, int(context_lines)),
    )


def validate_guide_excerpt(
    context: dict[str, Any],
    *,
    source_path: str | None = None,
    context_lines: int = 2,
) -> dict[str, Any]:
    """Compare the currently stored guide excerpt to the original source.
    
    Use this to detect whether the attached excerpt is:
    - correct (found in source),
    - partially correct (similar match),
    - or wrong (excerpt not found, may belong to different task or guide version).
    """
    from felvi_games.source_search import compare_excerpt_to_source as _compare_impl
    
    sources_ctx = context.get("sources") or {}
    guide_excerpt = str(sources_ctx.get("utmutato_kivonat") or "").strip()
    
    if not guide_excerpt:
        return {
            "error": "No guide excerpt in current task context",
        }
    
    # Use explicit path or fall back to ut_szoveg_path
    feladat_ctx = context.get("feladat") or {}
    guide_file = (
        str(source_path or "").strip()
        or str(feladat_ctx.get("ut_szoveg_path") or "").strip()
    )
    
    if not guide_file:
        return {
            "error": "No source file path provided; cannot validate excerpt",
            "hint": "Provide source_path or load a task with source references",
        }
    
    result = _compare_impl(
        guide_excerpt,
        guide_file,
        context_lines=max(1, int(context_lines)),
    )
    
    return {
        **result,
        "stored_excerpt_length": len(guide_excerpt),
        "stored_excerpt_preview": guide_excerpt[:200],
    }