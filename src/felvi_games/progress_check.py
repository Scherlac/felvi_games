"""
progress_check.py
-----------------
Daily login check: evaluate recent progress, identify close medals, optionally
create a private AI-generated teaser medal, and produce a motivational greeting.

Triggered once per calendar day per user (first login / first session start).

Public API
----------
::

    insight = daily_check(user, repo)    # → DailyInsight | None
    # None  →  not the first login today (skip)

    # insight fields:
    #   greeting          str          – AI motivational message
    #   close_medals      list         – medals within reach with progress hint
    #   teaser_medal      Erem | None  – existing/new medal to show as "next goal"
    #   new_medal_created bool         – True when a fresh private medal was added
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from felvi_games.models import Erem

if TYPE_CHECKING:
    from felvi_games.db import FeladatRepository


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CloseMedal:
    erem: Erem
    progress: float          # 0.0 – 1.0  (1.0 = just earned)
    hint: str                # human-readable "X of Y done" style hint


@dataclass
class DailyInsight:
    greeting: str
    close_medals: list[CloseModal] = field(default_factory=list)
    teaser_medal: Erem | None = None
    new_medal_created: bool = False
    awardable_now: list[Erem] = field(default_factory=list)
    would_repeat_now: list[Erem] = field(default_factory=list)


# Fix typo in the field reference above
CloseModal = CloseMedal   # alias used in the dataclass default_factory annotation


_DYNAMIC_CONDITION_DIMENSION_KEYS: dict[str, tuple[str, ...]] = {
    "feladat_count": (),
    "helyes_count": (),
    "pont_sum": (),
    "streak": (),
    "session_count": (),
    "tokeletes_session": (),
    "feladat_subject": ("subject",),
    "before_hour": ("hour",),
    "after_hour": ("hour",),
    "special_date": ("date",),
    "interakcio_count": ("event_type", "targy", "szint", "feladat_id", "meta_contains"),
    "interakcio_exists": ("event_type", "targy", "szint", "feladat_id", "meta_contains"),
}

_TIME_GATE_RULES: list[tuple[tuple[str, ...], str, int, str]] = [
    (("reggeli", "hajnali", "korai", "delelott", "délelőtt"), "before_hour", 10, "morning"),
    (("delutani", "délutáni", "delutan", "délután"), "after_hour", 12, "afternoon"),
    (("esti", "keso esti", "késő esti"), "after_hour", 18, "evening"),
    (("ejjeli", "éjjeli", "ejszakai", "éjszakai"), "after_hour", 22, "night"),
]


def _expected_time_gate(nev: str | None, leiras: str | None) -> tuple[str, int, str] | None:
    text = f"{nev or ''} {leiras or ''}".lower()
    for keywords, gate_type, hour, label in _TIME_GATE_RULES:
        if any(k in text for k in keywords):
            return gate_type, hour, label
    return None


def _condition_items(condition: Any) -> list[dict]:
    if isinstance(condition, list):
        return [c for c in condition if isinstance(c, dict)]
    if isinstance(condition, dict):
        return [condition]
    return []


def _normalize_time_gate_condition(condition: Any, expected_type: str, expected_hour: int) -> Any:
    items = _condition_items(condition)
    if not items:
        return condition

    filtered = [
        c for c in items
        if str(c.get("type", "")) not in {"before_hour", "after_hour"}
    ]
    filtered.append({"type": expected_type, "hour": expected_hour})

    if isinstance(condition, dict) and len(filtered) == 1:
        return filtered[0]
    return filtered


def normalize_medal_candidate_time_gate(medal_data: dict | None) -> tuple[dict | None, dict | None]:
    """Ensure time-of-day medal names carry matching before/after gating.

    Returns (possibly_updated_medal_data, review_note_or_none).
    """
    if not isinstance(medal_data, dict):
        return None, None
    condition = medal_data.get("condition")
    if not isinstance(condition, (dict, list)):
        return medal_data, None

    expected = _expected_time_gate(medal_data.get("nev"), medal_data.get("leiras"))
    if expected is None:
        return medal_data, None

    expected_type, expected_hour, label = expected
    items = _condition_items(condition)
    has_expected = any(str(c.get("type", "")) == expected_type for c in items)
    has_opposite = any(
        str(c.get("type", "")) in {"before_hour", "after_hour"}
        and str(c.get("type", "")) != expected_type
        for c in items
    )
    if has_expected and not has_opposite:
        return medal_data, {
            "time_gate_status": "ok",
            "expected_type": expected_type,
            "expected_hour": expected_hour,
            "label": label,
        }

    updated = dict(medal_data)
    updated["condition"] = _normalize_time_gate_condition(condition, expected_type, expected_hour)
    return updated, {
        "time_gate_status": "normalized",
        "expected_type": expected_type,
        "expected_hour": expected_hour,
        "label": label,
    }


def review_time_gate_alignment(user: str, repo: FeladatRepository) -> list[dict]:
    """Review user-visible medal conditions for name/description time-gate alignment."""
    findings: list[dict] = []
    for erem in repo.get_erem_katalogus(user).values():
        if not isinstance(erem.condition, (dict, list)):
            continue
        expected = _expected_time_gate(erem.nev, erem.leiras)
        if expected is None:
            continue
        expected_type, expected_hour, label = expected
        items = _condition_items(erem.condition)
        has_expected = any(str(c.get("type", "")) == expected_type for c in items)
        has_before = any(str(c.get("type", "")) == "before_hour" for c in items)
        has_after = any(str(c.get("type", "")) == "after_hour" for c in items)

        if has_expected and (
            (expected_type == "before_hour" and not has_after)
            or (expected_type == "after_hour" and not has_before)
        ):
            status = "ok"
            recommendation = "none"
        elif has_expected:
            status = "conflicting"
            recommendation = f"keep only {expected_type}(hour={expected_hour})"
        else:
            status = "missing"
            recommendation = f"add {expected_type}(hour={expected_hour})"

        findings.append(
            {
                "id": erem.id,
                "nev": erem.nev,
                "cel_felhasznalo": erem.cel_felhasznalo,
                "expected_type": expected_type,
                "expected_hour": expected_hour,
                "label": label,
                "status": status,
                "recommendation": recommendation,
                "condition": erem.condition,
            }
        )
    return findings


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_condition_value(value: object) -> object:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _normalize_dynamic_condition(condition: dict | list[dict]) -> dict | list[dict]:
    if isinstance(condition, list):
        normalized_items: list[dict] = []
        for item in condition:
            if not isinstance(item, dict):
                continue
            normalized_item: dict[str, object] = {}
            for key, value in item.items():
                normalized_item[str(key)] = _normalize_condition_value(value)
            normalized_items.append(normalized_item)
        normalized_items.sort(key=lambda x: str(x.get("type", "")))
        return normalized_items

    normalized: dict[str, object] = {}
    for key, value in condition.items():
        normalized[str(key)] = _normalize_condition_value(value)
    return normalized


def _window_ratio(left: float, right: float) -> float:
    if left <= 0 or right <= 0:
        return 0.0
    return min(left, right) / max(left, right)


def _target_ratio(candidate: dict, existing: dict) -> float:
    if candidate.get("type") == "special_date":
        left = _safe_int(candidate.get("feladat_count", 1), 1)
        right = _safe_int(existing.get("feladat_count", 1), 1)
    else:
        left = _safe_int(candidate.get("n", 1), 1)
        right = _safe_int(existing.get("n", 1), 1)
    return _window_ratio(float(left), float(right))


def _dynamic_overlap_reason(candidate: dict | list[dict], existing: dict | list[dict]) -> str | None:
    cand = _normalize_dynamic_condition(candidate)
    prev = _normalize_dynamic_condition(existing)

    if isinstance(cand, list) or isinstance(prev, list):
        if cand == prev:
            return "compound exact overlap"
        return None

    ctype = str(cand.get("type", "")).strip()
    if not ctype or ctype != str(prev.get("type", "")).strip():
        return None

    for key in _DYNAMIC_CONDITION_DIMENSION_KEYS.get(ctype, ()): 
        if cand.get(key) != prev.get(key):
            return None

    window_ratio = _window_ratio(
        _safe_float(cand.get("window_hours", 24), 24.0),
        _safe_float(prev.get("window_hours", 24), 24.0),
    )
    target_ratio = _target_ratio(cand, prev)
    if window_ratio >= 0.6 and target_ratio >= 0.7:
        return f"{ctype} structural overlap"
    if cand == prev:
        return f"{ctype} exact overlap"
    return None


def _dynamic_medal_expiry(erem: Erem) -> datetime | None:
    if not erem.ideiglenes or not erem.ervenyes_napig or erem.condition_valid_from is None:
        return None
    anchor = erem.condition_valid_from
    anchor_utc = anchor if anchor.tzinfo else anchor.replace(tzinfo=timezone.utc)
    return anchor_utc + timedelta(days=erem.ervenyes_napig)


def _conflicting_dynamic_medals(user: str, repo: FeladatRepository, candidate: dict | list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    conflicts: list[dict] = []
    for erem in repo.get_erem_katalogus(user).values():
        if not erem.privat or erem.cel_felhasznalo != user or not erem.condition:
            continue
        if not erem.id.startswith("daily_"):
            continue
        if repo.has_erem(user, erem.id):
            continue
        expiry = _dynamic_medal_expiry(erem)
        if expiry is not None and expiry <= now:
            continue
        reason = _dynamic_overlap_reason(candidate, erem.condition)
        if reason is None:
            continue
        conflicts.append(
            {
                "id": erem.id,
                "nev": erem.nev,
                "leiras": erem.leiras,
                "kategoria": erem.kategoria,
                "condition": erem.condition,
                "reason": reason,
            }
        )
    return conflicts


def _find_cross_user_private_match(user: str, repo: FeladatRepository, candidate: dict | list[dict]) -> dict | None:
    """Return one matching private medal from another user, if any."""
    for erem in repo.get_all_private_dynamic_medals():
        if not isinstance(erem.condition, dict):
            continue
        if erem.cel_felhasznalo == user:
            continue
        reason = _dynamic_overlap_reason(candidate, erem.condition)
        if reason is None:
            continue
        return {
            "source_erem_id": erem.id,
            "source_user": erem.cel_felhasznalo,
            "source_nev": erem.nev,
            "reason": reason,
            "source_condition": erem.condition,
        }
    return None


def _screen_dynamic_medal_candidate(
    user: str,
    repo: FeladatRepository,
    stats: dict,
    close_medals: list[CloseMedal],
    earned_count: int,
    medal_data: dict | None,
    *,
    window_hours: int,
) -> dict | None:
    if not isinstance(medal_data, dict):
        return None
    if not isinstance(medal_data.get("condition"), (dict, list)):
        return None

    medal_data, _ = normalize_medal_candidate_time_gate(medal_data)
    if not isinstance(medal_data, dict):
        return None

    cross_user_match = _find_cross_user_private_match(user, repo, medal_data["condition"])
    if cross_user_match is not None:
        # Signal for product review: this idea already exists privately for another user
        # and should be considered for promotion to public instead of cloning privately.
        repo.log_interakcio(
            user,
            "medal_public_candidate_hit",
            meta={
                "candidate": {
                    "nev": medal_data.get("nev"),
                    "kategoria": medal_data.get("kategoria"),
                    "condition": medal_data.get("condition"),
                },
                "match": cross_user_match,
            },
            process_pending_rewards=False,
        )
        logger.info(
            "dynamic_medal_blocked_cross_user_match | user=%s source_erem=%s source_user=%s reason=%s",
            user,
            cross_user_match.get("source_erem_id"),
            cross_user_match.get("source_user"),
            cross_user_match.get("reason"),
        )
        return None

    conflicts = _conflicting_dynamic_medals(user, repo, medal_data["condition"])
    if not conflicts:
        return medal_data

    try:
        from felvi_games.ai import judge_medal_novelty, refine_daily_medal
    except Exception:
        logger.warning("dynamic_medal_quality_gate_import_failed", exc_info=True)
        return None

    try:
        novelty = judge_medal_novelty(medal_data, conflicts)
    except Exception:
        logger.warning("dynamic_medal_novelty_check_failed", exc_info=True)
        return None

    if novelty.get("reasonably_different"):
        return medal_data

    rejection_reason = str(novelty.get("reason", "too_similar")).strip() or "too_similar"
    try:
        refined = refine_daily_medal(
            user,
            stats,
            close_medals,
            earned_count,
            window_hours=window_hours,
            candidate=medal_data,
            conflicting_medals=conflicts,
            rejection_reason=rejection_reason,
        )
    except Exception:
        logger.warning("dynamic_medal_refine_failed", exc_info=True)
        return None

    if not isinstance(refined, dict) or not isinstance(refined.get("condition"), (dict, list)):
        return None

    refined, _ = normalize_medal_candidate_time_gate(refined)
    if not isinstance(refined, dict):
        return None

    refined_conflicts = _conflicting_dynamic_medals(user, repo, refined["condition"])
    if not refined_conflicts:
        return refined

    try:
        refined_novelty = judge_medal_novelty(refined, refined_conflicts)
    except Exception:
        logger.warning("dynamic_medal_refined_novelty_check_failed", exc_info=True)
        return None
    if refined_novelty.get("reasonably_different"):
        return refined
    return None


# ---------------------------------------------------------------------------
# Cross-user private medal cluster detection
# ---------------------------------------------------------------------------

@dataclass
class DynamicMedalCluster:
    """A group of structurally similar private dynamic medals from different users."""
    representative: Erem                  # one representative medal from the cluster
    members: list[Erem]                   # all medals in the cluster (includes representative)
    overlap_reason: str                   # e.g. "after_hour structural overlap"
    user_count: int                       # distinct users covered


def find_cross_user_medal_clusters(
    repo: FeladatRepository,
    *,
    min_users: int = 2,
) -> list[DynamicMedalCluster]:
    """Find private dynamic medals with overlapping conditions across multiple users.

    Uses the same deterministic overlap logic as the single-user screening gate.
    Returns clusters that appeared for at least *min_users* distinct users,
    sorted by user count descending.
    """
    all_medals = repo.get_all_private_dynamic_medals()
    # Index: erem_id → Erem
    # Group into clusters using a union-find-like greedy approach:
    # compare each medal against existing cluster representatives.
    clusters: list[list[Erem]] = []
    cluster_reasons: list[str] = []

    for medal in all_medals:
        if not isinstance(medal.condition, dict):
            continue
        placed = False
        for _idx, cluster in enumerate(clusters):
            rep = cluster[0]
            if not isinstance(rep.condition, dict):
                continue
            reason = _dynamic_overlap_reason(medal.condition, rep.condition)
            if reason is not None:
                cluster.append(medal)
                placed = True
                break
        if not placed:
            clusters.append([medal])
            cluster_reasons.append("")

    results: list[DynamicMedalCluster] = []
    for _idx, cluster in enumerate(clusters):
        distinct_users = {m.cel_felhasznalo for m in cluster if m.cel_felhasznalo}
        if len(distinct_users) < min_users:
            continue
        rep = cluster[0]
        reason = ""
        for m in cluster[1:]:
            r = (
                _dynamic_overlap_reason(m.condition, rep.condition)
                if isinstance(m.condition, dict) and isinstance(rep.condition, dict)
                else None
            )
            if r:
                reason = r
                break
        results.append(
            DynamicMedalCluster(
                representative=rep,
                members=list(cluster),
                overlap_reason=reason,
                user_count=len(distinct_users),
            )
        )
    results.sort(key=lambda c: c.user_count, reverse=True)
    return results


# ---------------------------------------------------------------------------
# First-login-today detection
# ---------------------------------------------------------------------------

def is_first_login_today(user: str, repo: FeladatRepository) -> bool:
    """True if the user has NOT started a session yet today (UTC)."""
    from felvi_games.db import InterakcioRecord
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with Session(repo._engine) as s:
        cnt = s.scalar(
            select(func.count()).select_from(InterakcioRecord).where(
                InterakcioRecord.felhasznalo_nev == user,
                InterakcioRecord.tipus == "menet_indul",
                InterakcioRecord.created_at >= today_start,
            )
        ) or 0
    return cnt == 0


# ---------------------------------------------------------------------------
# Aggregate stats collector
# ---------------------------------------------------------------------------

def get_user_stats(user: str, repo: FeladatRepository) -> dict:
    """Return a dict of aggregate player statistics for AI / closeness checks.
    
    Now powered by KPI registry for unified calculation and caching.
    """
    from felvi_games import condition_registry as cr
    
    engine = repo._engine
    now_utc = datetime.now(timezone.utc)
    cutoff_24h = now_utc - timedelta(hours=24)
    cutoff_48h = now_utc - timedelta(hours=48)
    cutoff_7d = now_utc - timedelta(days=7)

    # Use a shared session to enable cache hits across multiple KPI calls
    with Session(engine) as s:
        # All-time aggregate counts
        total_attempts = cr.kpi_parameter_value(user, "total_attempts", {}, now_utc, None, s) or 0
        correct = cr.kpi_parameter_value(user, "total_correct", {}, now_utc, None, s) or 0
        total_sessions = cr.kpi_parameter_value(user, "total_sessions", {}, now_utc, None, s) or 0
        completed_sessions = cr.kpi_parameter_value(user, "completed_sessions", {}, now_utc, None, s) or 0

        # Metadata (subjects, levels)
        subjects_used = cr.kpi_parameter_value(user, "subjects_used", {}, now_utc, None, s) or []
        levels_used = cr.kpi_parameter_value(user, "levels_used", {}, now_utc, None, s) or []
        avg_elapsed = cr.kpi_parameter_value(user, "avg_elapsed_sec", {}, now_utc, None, s)

        # Streaks
        best_correct_streak = cr.kpi_parameter_value(user, "correct_streak_best", {}, now_utc, None, s) or 0
        current_correct_streak = cr.kpi_parameter_value(user, "correct_streak_current", {}, now_utc, None, s) or 0
        play_day_streak_current = cr.kpi_parameter_value(user, "play_day_streak_current", {}, now_utc, None, s) or 0
        recent_days_7d = cr.kpi_parameter_value(user, "play_days_7d", {}, now_utc, None, s) or 0

        # Hint statistics
        hints_stats = cr.kpi_parameter_value(user, "hints_last_20_correct", {}, now_utc, None, s) or {}
        hint_free_correct = hints_stats.get("hint_free", 0) if isinstance(hints_stats, dict) else 0

        # Time-windowed aggregates (last 24h)
        attempts_last_24h = cr.kpi_parameter_value(user, "attempt_count", {}, cutoff_24h, now_utc, s) or 0
        correct_last_24h = cr.kpi_parameter_value(user, "correct_count", {}, cutoff_24h, now_utc, s) or 0
        points_last_24h = cr.kpi_parameter_value(user, "points_sum", {}, cutoff_24h, now_utc, s) or 0
        hint_uses_last_24h = cr.kpi_parameter_value(user, "hint_uses_window", {}, cutoff_24h, now_utc, s) or 0

        # Time-windowed aggregates (prev 24h-48h)
        attempts_prev_24h = cr.kpi_parameter_value(user, "attempt_count", {}, cutoff_48h, cutoff_24h, s) or 0
        correct_prev_24h = cr.kpi_parameter_value(user, "correct_count", {}, cutoff_48h, cutoff_24h, s) or 0
        points_prev_24h = cr.kpi_parameter_value(user, "points_sum", {}, cutoff_48h, cutoff_24h, s) or 0
        hint_uses_prev_24h = cr.kpi_parameter_value(user, "hint_uses_window", {}, cutoff_48h, cutoff_24h, s) or 0

        # Dimension aggregations (all-time)
        subject_session_counts = cr.kpi_parameter_value(user, "subject_session_counts", {}, now_utc, None, s) or {}
        level_session_counts = cr.kpi_parameter_value(user, "level_session_counts", {}, now_utc, None, s) or {}
        task_type_counts = cr.kpi_parameter_value(user, "task_type_counts", {}, now_utc, None, s) or {}

        # Dimension aggregations (7d window)
        subject_session_counts_7d = cr.kpi_parameter_value(user, "subject_session_counts_window", {}, cutoff_7d, now_utc, s) or {}
        level_session_counts_7d = cr.kpi_parameter_value(user, "level_session_counts_window", {}, cutoff_7d, now_utc, s) or {}

        # Event aggregations (last 24h and 7d)
        event_counts_last_24h = cr.kpi_parameter_value(user, "event_count_by_type", {}, cutoff_24h, now_utc, s) or {}
        event_counts_last_7d = cr.kpi_parameter_value(user, "event_count_by_type", {}, cutoff_7d, now_utc, s) or {}

        # Reevaluations
        reevaluations_7d = cr.kpi_parameter_value(user, "reevaluations_7d", {}, cutoff_7d, now_utc, s) or 0
        reevaluation_improved_7d = cr.kpi_parameter_value(user, "reevaluations_improved_7d", {}, cutoff_7d, now_utc, s) or 0

        # Pending rewards
        pending_rewards_count = cr.kpi_parameter_value(user, "pending_rewards", {}, now_utc, None, s) or 0

        # Complex 7d aggregations
        daily_attempts_7d = cr.kpi_parameter_value(user, "daily_attempts_7d", {}, cutoff_7d, now_utc, s) or []
        answer_outcomes_7d = cr.kpi_parameter_value(user, "answer_outcomes_7d", {}, cutoff_7d, now_utc, s) or {}
        recent_events = cr.kpi_parameter_value(user, "recent_events_7d", {}, cutoff_7d, now_utc, s) or []

    # Compute derived values
    accuracy = round(correct / total_attempts * 100, 1) if total_attempts else 0.0
    accuracy_last_24h = round(correct_last_24h / attempts_last_24h * 100, 1) if attempts_last_24h else None
    accuracy_prev_24h = round(correct_prev_24h / attempts_prev_24h * 100, 1) if attempts_prev_24h else None

    return {
        "total_attempts": total_attempts,
        "correct": correct,
        "accuracy_pct": accuracy,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "subjects_used": subjects_used,
        "levels_used": levels_used,
        "recent_days_7d": recent_days_7d,
        "current_streak_days": play_day_streak_current,
        "best_correct_streak": best_correct_streak,
        "current_correct_streak": current_correct_streak,
        "hint_free_correct_last20": hint_free_correct,
        "avg_elapsed_sec": round(float(avg_elapsed), 1) if avg_elapsed else None,
        "trends": {
            "attempts_last_24h": attempts_last_24h,
            "attempts_prev_24h": attempts_prev_24h,
            "correct_last_24h": correct_last_24h,
            "correct_prev_24h": correct_prev_24h,
            "points_last_24h": points_last_24h,
            "points_prev_24h": points_prev_24h,
            "accuracy_last_24h": accuracy_last_24h,
            "accuracy_prev_24h": accuracy_prev_24h,
            "hint_uses_last_24h": hint_uses_last_24h,
            "hint_uses_prev_24h": hint_uses_prev_24h,
            "activity_trend": _trend_label(attempts_last_24h, attempts_prev_24h),
            "accuracy_trend": _trend_label(accuracy_last_24h, accuracy_prev_24h),
            "daily_attempts_7d": daily_attempts_7d,
            "answer_outcomes_7d": answer_outcomes_7d,
        },
        "patterns": {
            "subject_session_counts": subject_session_counts,
            "subject_session_counts_7d": subject_session_counts_7d,
            "level_session_counts": level_session_counts,
            "level_session_counts_7d": level_session_counts_7d,
            "attempt_task_type_counts": task_type_counts,
            "help_usage_last20": {
                "hint_free_correct": hint_free_correct,
                "hint_used_correct": hints_stats.get("hint_used", 0) if isinstance(hints_stats, dict) else 0,
            },
        },
        "events": {
            "counts_last_24h": event_counts_last_24h,
            "counts_last_7d": event_counts_last_7d,
            "reevaluations_last_7d": reevaluations_7d,
            "reevaluation_improved_last_7d": reevaluation_improved_7d,
            "pending_reward_attempts": int(pending_rewards_count),
            "recent": recent_events,
        },
    }



def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_real_dimension_value(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return bool(normalized) and normalized not in {"mind", "osszes", "összes", "all", "*"}


def _trend_label(current: float | int | None, previous: float | int | None) -> str:
    if current is None and previous is None:
        return "nincs adat"
    current_value = float(current or 0)
    previous_value = float(previous or 0)
    if current_value == previous_value:
        return "stabil"
    if current_value > previous_value:
        return "javul"
    return "csökken"


def _trailing_streak(dates: list) -> int:
    """How many consecutive days ending today-or-yesterday."""
    if not dates:
        return 0
    today = datetime.now(timezone.utc).date()
    streak = 0
    prev = today
    for d in reversed(dates):
        if isinstance(d, datetime):
            d = d.date()
        if (prev - d).days <= 1:
            streak += 1
            prev = d
        else:
            break
    return streak


def _max_streak(seq: list[bool]) -> int:
    best = cur = 0
    for v in seq:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _current_correct_streak(seq: list[bool]) -> int:
    cur = 0
    for v in reversed(seq):
        if v:
            cur += 1
        else:
            break
    return cur


# ---------------------------------------------------------------------------
# Medal closeness estimator
# ---------------------------------------------------------------------------

def estimate_close_medals(
    user: str,
    repo: FeladatRepository,
    stats: dict,
    threshold: float = 0.50,
) -> list[CloseModal]:
    """Return medals the user is at least *threshold* of the way towards earning.

    Only checks medals the user hasn't yet earned (or repeatable ones).
    """
    catalog = repo.get_erem_katalogus(user)
    earned_ids = {fe.erem_id for fe in repo.get_eremek(user)}

    close: list[CloseModal] = []

    def _add(erem_id: str, progress: float, hint: str) -> None:
        erem = catalog.get(erem_id)
        if erem is None:
            return
        if not erem.ismetelheto and erem_id in earned_ids:
            return
        if progress >= threshold:
            close.append(CloseModal(erem=erem, progress=min(progress, 1.0), hint=hint))

    n = stats["total_attempts"]
    # milestone medals
    _add("szaz_feladat",    n / 100,   f"{n} / 100 feladat")
    _add("otszaz_feladat",  n / 500,   f"{n} / 500 feladat")
    _add("ezer_feladat",    n / 1000,  f"{n} / 1000 feladat")

    # correct-answer streak
    bcs = stats["best_correct_streak"]
    _add("sorozat_5",  bcs / 5,   f"legjobb sorozat: {bcs} / 5")
    _add("sorozat_10", bcs / 10,  f"legjobb sorozat: {bcs} / 10")
    _add("sorozat_20", bcs / 20,  f"legjobb sorozat: {bcs} / 20")

    # hint-free
    hf = stats["hint_free_correct_last20"]
    _add("hint_nelkul_20", hf / 20, f"utolsó 20 helyes közül {hf} segítség nélkül")

    # accuracy
    if n >= 20:
        _add("magas_pontossag", min(n, 50) / 50 * (stats["accuracy_pct"] / 80),
             f"pontosság: {stats['accuracy_pct']}% (cél: 80%+, min 50 feladat)")

    # daily streak
    cs = stats["current_streak_days"]
    _add("het_egymas_utan",      cs / 7,   f"jelenlegi sorozat: {cs} / 7 nap")
    _add("harom_het_egymas_utan", cs / 21, f"jelenlegi sorozat: {cs} / 21 nap")

    # weekly activity
    rd = stats["recent_days_7d"]
    _add("heti_haromszor", rd / 3, f"elmúlt 7 napból: {rd} / 3 nap")
    _add("heti_bajnok",    rd / 5, f"elmúlt 7 napból: {rd} / 5 nap")

    # subject / level exploration
    subj = set(stats["subjects_used"])
    if "matek" not in subj or "magyar" not in subj:
        covered = len(subj & {"matek", "magyar"})
        _add("mindket_targy", covered / 2, f"tárgyak: {', '.join(subj or ['–'])} (mindkettő kell)")

    lvls = set(stats["levels_used"])
    covered_lvl = len(lvls & {"4 osztályos", "6 osztályos", "8 osztályos"})
    _add("minden_szint", covered_lvl / 3, f"szintek: {covered_lvl} / 3")

    # visited at least 3 different days
    # use a simpler proxy: completed_sessions / 3 as days approximation
    approx_days = min(stats["completed_sessions"], stats["total_sessions"])
    _add("visszatero", min(approx_days, 3) / 3, f"visszatérések: {approx_days} nap (cél: 3)")

    # sort: closest to earning first
    close.sort(key=lambda c: c.progress, reverse=True)
    return close[:5]  # top 5


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def daily_check(
    user: str,
    repo: FeladatRepository,
    *,
    force: bool = False,
) -> DailyInsight | None:
    """Run the daily insight check.

    Returns ``None`` if it's not the first login today (unless *force=True*).
    Calls the AI — may take a second; call in a background thread or spinner.
    """
    if not force and not is_first_login_today(user, repo):
        return None

    from felvi_games.achievements import get_awardability_now, get_next_award_basis

    basis = get_next_award_basis(user, repo)
    stats = basis.stats
    close = basis.close_medals
    earned_count = basis.earned_count
    awardability = get_awardability_now(user, repo)

    # 40% random gate: only sometimes introduce a new dynamic challenge medal
    introduce_new_medal = random.random() < 0.40
    window_hours = random.choice([1, 2, 3, 4, 6, 8, 10, 12, 18]) if introduce_new_medal else 18

    # Ask AI for a greeting + optional new private medal
    try:
        from felvi_games.ai import generate_daily_insight
        ai_result = generate_daily_insight(
            user, stats, close, earned_count, window_hours=window_hours
        )
    except Exception:  # noqa: BLE001
        ai_result = {"greeting": f"Helló {user}! Üdv vissza a játékban! 🎉", "new_medal": None}

    greeting: str = ai_result.get("greeting", f"Üdv, {user}!")

    # Create new private medal if AI suggested one AND the 40% gate fired
    new_medal: Erem | None = None
    new_medal_created = False
    medal_data = ai_result.get("new_medal") if introduce_new_medal else None
    medal_data = _screen_dynamic_medal_candidate(
        user,
        repo,
        stats,
        close,
        earned_count,
        medal_data,
        window_hours=window_hours,
    ) if introduce_new_medal else None
    if medal_data and isinstance(medal_data, dict):
        try:
            import re
            erem_id = f"daily_{user.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
            erem_id = re.sub(r"[^a-z0-9_]", "_", erem_id)
            existing = repo.get_erem_katalogus(user)
            # Don't stack more than 2 active dynamic medals per user
            active_dynamic = [
                eid for eid in existing
                if eid.startswith("daily_") and not repo.has_erem(user, eid)
            ]
            if len(active_dynamic) < 2 and erem_id not in existing:
                condition = medal_data.get("condition")
                ervenyes_napig = medal_data.get("ervenyes_napig", 1)
                # Clamp to at most ceil(window_hours/24) days so expiry matches the window
                import math
                ervenyes_napig = max(1, min(ervenyes_napig, math.ceil(window_hours / 24)))
                new_medal = Erem(
                    id=erem_id,
                    nev=medal_data.get("nev", "Napi kihívás"),
                    leiras=medal_data.get("leiras", ""),
                    ikon=medal_data.get("ikon", "🌟"),
                    kategoria=medal_data.get("kategoria", "teljesitmeny"),
                    ideiglenes=True,
                    ervenyes_napig=ervenyes_napig,
                    ismetelheto=True,
                    privat=True,
                    cel_felhasznalo=user,
                    condition=condition if isinstance(condition, dict) else None,
                )
                repo.upsert_erem(new_medal)
                new_medal_created = True
        except Exception:  # noqa: BLE001
            new_medal = None

    # Teaser: prefer the closest not-yet-earned medal
    teaser: Erem | None = new_medal or (close[0].erem if close else None)

    return DailyInsight(
        greeting=greeting,
        close_medals=close,
        teaser_medal=teaser,
        new_medal_created=new_medal_created,
        awardable_now=awardability.awardable_now,
        would_repeat_now=awardability.would_repeat_now,
    )
