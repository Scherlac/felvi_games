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

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from felvi_games.models import Erem

if TYPE_CHECKING:
    from felvi_games.db import FeladatRepository


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


# Fix typo in the field reference above
CloseModal = CloseMedal   # alias used in the dataclass default_factory annotation


# ---------------------------------------------------------------------------
# First-login-today detection
# ---------------------------------------------------------------------------

def is_first_login_today(user: str, repo: "FeladatRepository") -> bool:
    """True if the user has NOT started a session yet today (UTC)."""
    from felvi_games.db import InterakcioRecord, MenetRecord
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

def get_user_stats(user: str, repo: "FeladatRepository") -> dict:
    """Return a dict of aggregate player statistics for AI / closeness checks."""
    from felvi_games.db import FeladatRecord, InterakcioRecord, MegoldasRecord, MenetRecord

    engine = repo._engine
    now_utc = datetime.now(timezone.utc)
    cutoff_24h = now_utc - timedelta(hours=24)
    cutoff_48h = now_utc - timedelta(hours=48)
    cutoff_7d = now_utc - timedelta(days=7)

    with Session(engine) as s:
        total_attempts = s.scalar(
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.felhasznalo_nev == user)
        ) or 0

        correct = s.scalar(
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.felhasznalo_nev == user,
                   MegoldasRecord.helyes == True)  # noqa: E712
        ) or 0

        total_sessions = s.scalar(
            select(func.count()).select_from(MenetRecord)
            .where(MenetRecord.felhasznalo_nev == user)
        ) or 0

        completed_sessions = s.scalar(
            select(func.count()).select_from(MenetRecord)
            .where(MenetRecord.felhasznalo_nev == user,
                   MenetRecord.ended_at.is_not(None))
        ) or 0

        subject_rows = list(s.scalars(
            select(MenetRecord.targy).where(MenetRecord.felhasznalo_nev == user)
        ).all())
        subjects_used = {value for value in subject_rows if _is_real_dimension_value(value)}

        level_rows = list(s.scalars(
            select(MenetRecord.szint).where(MenetRecord.felhasznalo_nev == user)
        ).all())
        levels_used = {value for value in level_rows if _is_real_dimension_value(value)}

        # last 7 days play days
        recent_sessions = list(s.scalars(
            select(MenetRecord.started_at)
            .where(MenetRecord.felhasznalo_nev == user,
                   MenetRecord.started_at >= cutoff_7d)
        ).all())
        recent_days = len({dt.date() for dt in recent_sessions})

        # current streak
        all_session_dates = sorted({
            dt.date()
            for dt in s.scalars(
                select(MenetRecord.started_at)
                .where(MenetRecord.felhasznalo_nev == user)
            ).all()
        })
        current_streak = _trailing_streak(all_session_dates)

        # current best correct streak
        answer_seq = list(s.scalars(
            select(MegoldasRecord.helyes)
            .where(MegoldasRecord.felhasznalo_nev == user)
            .order_by(MegoldasRecord.created_at)
        ).all())
        best_correct_streak = _max_streak(answer_seq)
        current_correct_streak = _current_correct_streak(answer_seq)

        # hint usage in last 20 correct answers
        last_20_correct_hints = list(s.scalars(
            select(MegoldasRecord.segitseg_kert)
            .where(MegoldasRecord.felhasznalo_nev == user,
                   MegoldasRecord.helyes == True)  # noqa: E712
            .order_by(MegoldasRecord.created_at.desc())
            .limit(20)
        ).all())
        hint_free_correct = sum(1 for h in last_20_correct_hints if not h)

        # average elapsed_sec for correct answers
        avg_elapsed = s.scalar(
            select(func.avg(MegoldasRecord.elapsed_sec))
            .where(MegoldasRecord.felhasznalo_nev == user,
                   MegoldasRecord.helyes == True,  # noqa: E712
                   MegoldasRecord.elapsed_sec.is_not(None))
        )

        attempt_rows_7d = list(s.execute(
            select(
                MegoldasRecord.created_at,
                MegoldasRecord.helyes,
                MegoldasRecord.pont,
                MegoldasRecord.segitseg_kert,
            )
            .where(MegoldasRecord.felhasznalo_nev == user,
                   MegoldasRecord.created_at >= cutoff_7d)
            .order_by(MegoldasRecord.created_at.asc(), MegoldasRecord.id.asc())
        ).all())

        subject_rows_7d = list(s.execute(
            select(MenetRecord.targy)
            .where(MenetRecord.felhasznalo_nev == user,
                   MenetRecord.started_at >= cutoff_7d)
        ).all())
        level_rows_7d = list(s.execute(
            select(MenetRecord.szint)
            .where(MenetRecord.felhasznalo_nev == user,
                   MenetRecord.started_at >= cutoff_7d)
        ).all())
        feladat_tipus_counts = Counter(
            value
            for value in s.scalars(
                select(FeladatRecord.feladat_tipus)
                .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
                .where(MegoldasRecord.felhasznalo_nev == user)
            ).all()
            if _is_real_dimension_value(value)
        )

        event_rows_7d = list(s.execute(
            select(
                InterakcioRecord.tipus,
                InterakcioRecord.created_at,
                InterakcioRecord.targy,
                InterakcioRecord.szint,
                InterakcioRecord.feladat_id,
            )
            .where(InterakcioRecord.felhasznalo_nev == user,
                   InterakcioRecord.created_at >= cutoff_7d)
            .order_by(InterakcioRecord.created_at.desc(), InterakcioRecord.id.desc())
        ).all())

        pending_rewards_count = s.scalar(
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.felhasznalo_nev == user,
                   MegoldasRecord.jutalom_varakozik.is_(True))
        ) or 0

        reevaluation_rows_7d = list(s.execute(
            select(MegoldasRecord.eredeti_pont, MegoldasRecord.pont)
            .where(MegoldasRecord.felhasznalo_nev == user,
                   MegoldasRecord.ujraertekelt.is_(True),
                   MegoldasRecord.ujraertekelt_at.is_not(None),
                   MegoldasRecord.ujraertekelt_at >= cutoff_7d)
        ).all())

    accuracy = round(correct / total_attempts * 100, 1) if total_attempts else 0.0

    attempts_last_24h = 0
    attempts_prev_24h = 0
    correct_last_24h = 0
    correct_prev_24h = 0
    points_last_24h = 0
    points_prev_24h = 0
    hint_uses_last_24h = 0
    hint_uses_prev_24h = 0
    daily_attempts_7d: dict[str, dict[str, int | float | str]] = {}
    answer_outcomes_7d = Counter()

    for created_at, is_correct, points, segitseg_kert in attempt_rows_7d:
        created_utc = _as_utc(created_at)
        day_key = created_utc.date().isoformat()
        if day_key not in daily_attempts_7d:
            daily_attempts_7d[day_key] = {
                "date": day_key,
                "attempts": 0,
                "correct": 0,
                "points": 0,
                "accuracy_pct": 0.0,
            }
        bucket = daily_attempts_7d[day_key]
        bucket["attempts"] = int(bucket["attempts"]) + 1
        bucket["points"] = int(bucket["points"]) + int(points or 0)
        if is_correct:
            bucket["correct"] = int(bucket["correct"]) + 1

        if created_utc >= cutoff_24h:
            attempts_last_24h += 1
            points_last_24h += int(points or 0)
            hint_uses_last_24h += 1 if segitseg_kert else 0
            if is_correct:
                correct_last_24h += 1
        elif created_utc >= cutoff_48h:
            attempts_prev_24h += 1
            points_prev_24h += int(points or 0)
            hint_uses_prev_24h += 1 if segitseg_kert else 0
            if is_correct:
                correct_prev_24h += 1

        if is_correct:
            answer_outcomes_7d["helyes"] += 1
        elif int(points or 0) > 0:
            answer_outcomes_7d["reszleges"] += 1
        else:
            answer_outcomes_7d["helytelen"] += 1

    for bucket in daily_attempts_7d.values():
        attempts = int(bucket["attempts"])
        correct_attempts = int(bucket["correct"])
        bucket["accuracy_pct"] = round(correct_attempts / attempts * 100, 1) if attempts else 0.0

    event_counts_last_24h = Counter()
    event_counts_last_7d = Counter()
    recent_events: list[dict[str, object]] = []
    for tipus, created_at, targy, szint, feladat_id in event_rows_7d:
        created_utc = _as_utc(created_at)
        event_counts_last_7d[str(tipus)] += 1
        if created_utc >= cutoff_24h:
            event_counts_last_24h[str(tipus)] += 1
        if len(recent_events) < 8:
            recent_events.append(
                {
                    "type": str(tipus),
                    "created_at": created_utc.isoformat(),
                    "targy": targy,
                    "szint": szint if _is_real_dimension_value(szint) else None,
                    "feladat_id": feladat_id,
                }
            )

    reevaluation_improved_count = sum(
        1
        for old_points, new_points in reevaluation_rows_7d
        if old_points is not None and int(new_points or 0) > int(old_points or 0)
    )

    subject_session_counts = Counter(value for value in subject_rows if _is_real_dimension_value(value))
    subject_session_counts_7d = Counter(value for (value,) in subject_rows_7d if _is_real_dimension_value(value))
    level_session_counts = Counter(value for value in level_rows if _is_real_dimension_value(value))
    level_session_counts_7d = Counter(value for (value,) in level_rows_7d if _is_real_dimension_value(value))

    accuracy_last_24h = round(correct_last_24h / attempts_last_24h * 100, 1) if attempts_last_24h else None
    accuracy_prev_24h = round(correct_prev_24h / attempts_prev_24h * 100, 1) if attempts_prev_24h else None

    return {
        "total_attempts": total_attempts,
        "correct": correct,
        "accuracy_pct": accuracy,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "subjects_used": sorted(subjects_used),
        "levels_used": sorted(levels_used),
        "recent_days_7d": recent_days,
        "current_streak_days": current_streak,
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
            "daily_attempts_7d": [daily_attempts_7d[key] for key in sorted(daily_attempts_7d)],
            "answer_outcomes_7d": dict(answer_outcomes_7d),
        },
        "patterns": {
            "subject_session_counts": dict(subject_session_counts),
            "subject_session_counts_7d": dict(subject_session_counts_7d),
            "level_session_counts": dict(level_session_counts),
            "level_session_counts_7d": dict(level_session_counts_7d),
            "attempt_task_type_counts": dict(feladat_tipus_counts),
            "help_usage_last20": {
                "hint_free_correct": hint_free_correct,
                "hint_used_correct": max(0, len(last_20_correct_hints) - hint_free_correct),
            },
        },
        "events": {
            "counts_last_24h": dict(event_counts_last_24h),
            "counts_last_7d": dict(event_counts_last_7d),
            "reevaluations_last_7d": len(reevaluation_rows_7d),
            "reevaluation_improved_last_7d": reevaluation_improved_count,
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
    from datetime import date
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
    repo: "FeladatRepository",
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
    days_total = len({
        # we approximate from total_sessions days here
    })
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
    repo: "FeladatRepository",
    *,
    force: bool = False,
) -> "DailyInsight | None":
    """Run the daily insight check.

    Returns ``None`` if it's not the first login today (unless *force=True*).
    Calls the AI — may take a second; call in a background thread or spinner.
    """
    if not force and not is_first_login_today(user, repo):
        return None

    stats = get_user_stats(user, repo)
    close = estimate_close_medals(user, repo, stats)

    earned_count = len(repo.get_eremek(user, include_expired=True))

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
    )
