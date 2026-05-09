"""
achievements.py
---------------
Medal/achievement catalog and rule engine.

Design:
  - EREM_KATALOGUS   – static dict of all possible medals (id → Erem)
  - check_new_medals – run after every session; returns medals to award
  - Rules are plain functions querying megoldasok / menetek / interakciok

Icon strategy
  Default : emoji  (works in terminal + Streamlit, zero dependencies)
  Better  : SVG from game-icons.net  (CC BY 3.0, pip install requests)
  Premium : AI-generated PNG via DALL-E 3 – hook in ai.py
            ai.generate_medal_ikon(erem_id: str, leiras: str) → bytes

Adding a new medal:
  1. Add an Erem entry to EREM_KATALOGUS
  2. Write a _rule_<id>(user, session_id, engine) → bool function below
  3. Register it in SZABALY_REGISTRY at the bottom of this file
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass as _dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import felvi_games.condition_registry as cr
from felvi_games.medal_catalog import EREM_KATALOGUS, get_bootstrap_repeatable_cooldown_hours
from felvi_games.models import Erem, FelhasznaloErem

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from felvi_games.db import FeladatRepository

logger = logging.getLogger(__name__)

# Context variable used by --simulate to replay history as of a given timestamp.
# Set this to a datetime before calling rule functions to make them behave as if
# that moment is "now" (i.e. only events up to that timestamp are visible).
_simulation_as_of: ContextVar[datetime | None] = ContextVar("_simulation_as_of", default=None)

# Repeatable medals should not trigger back-to-back from historical data.
# Cooldown is in hours. Medal-specific values come from bootstrap policy.
_REPEATABLE_COOLDOWN_DEFAULT_HOURS = 12
# Compatibility override hook (used by tests/experiments); leave empty in prod.
_REPEATABLE_COOLDOWN_HOURS: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SZINTEK_OSSZ = {"4 osztályos", "6 osztályos", "8 osztályos"}
_FELADAT_TIPUSOK_OSSZ = {"nyilt_valasz", "tobbvalasztos", "parositas", "igaz_hamis", "fogalmazas", "kitoltes"}


def _nap(dt: datetime) -> datetime:
    """Truncate to calendar date (UTC)."""
    d = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _sim_now() -> datetime:
    """Return the simulation reference time, or actual now."""
    t = _simulation_as_of.get()
    return t if t is not None else datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _repeatable_cooldown_hours(erem: Erem) -> int:
    override_hours = _REPEATABLE_COOLDOWN_HOURS.get(erem.id)
    if override_hours is not None:
        return override_hours
    bootstrap_hours = get_bootstrap_repeatable_cooldown_hours(erem.id)
    if bootstrap_hours is not None:
        return bootstrap_hours
    condition = erem.condition if isinstance(erem.condition, dict) else {}
    raw = condition.get("cooldown_hours")
    if raw is None:
        return _REPEATABLE_COOLDOWN_DEFAULT_HOURS
    try:
        hours = int(str(raw))
    except (TypeError, ValueError):
        return _REPEATABLE_COOLDOWN_DEFAULT_HOURS
    return hours if hours > 0 else _REPEATABLE_COOLDOWN_DEFAULT_HOURS


def _cooldown_elapsed(erem: Erem, last_award_at: datetime, now: datetime) -> bool:
    hours = _repeatable_cooldown_hours(erem)
    return now >= (_as_utc(last_award_at) + timedelta(hours=hours))


def _has_new_attempt_after(
    user: str,
    engine: Engine,
    since: datetime,
    *,
    hour_cmp: str | None = None,
    hour_val: int | None = None,
    require_fast_correct: bool = False,
) -> bool:
    from felvi_games.db import MegoldasRecord

    since_utc = _as_utc(since)
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (
            select(func.count()).select_from(MegoldasRecord)
            .where(
                MegoldasRecord.felhasznalo_nev == user,
                MegoldasRecord.created_at > since_utc,
            )
        )
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        if require_fast_correct:
            stmt = stmt.where(
                MegoldasRecord.helyes.is_(True),
                MegoldasRecord.elapsed_sec.is_not(None),
                MegoldasRecord.elapsed_sec <= 10.0,
            )
        if hour_cmp is not None and hour_val is not None:
            hh = f"{hour_val:02d}"
            local_h = func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime"))
            if hour_cmp == "lt":
                stmt = stmt.where(local_h < hh)
            elif hour_cmp == "ge":
                stmt = stmt.where(local_h >= hh)
        return (s.scalar(stmt) or 0) > 0


def _has_new_activity_after(user: str, engine: Engine, since: datetime) -> bool:
    from felvi_games.db import InterakcioRecord, MegoldasRecord, MenetRecord

    since_utc = _as_utc(since)
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        m_stmt = (
            select(func.count()).select_from(MegoldasRecord)
            .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at > since_utc)
        )
        n_stmt = (
            select(func.count()).select_from(MenetRecord)
            .where(MenetRecord.felhasznalo_nev == user, MenetRecord.started_at > since_utc)
        )
        i_stmt = (
            select(func.count()).select_from(InterakcioRecord)
            .where(InterakcioRecord.felhasznalo_nev == user, InterakcioRecord.created_at > since_utc)
        )
        if _as_of is not None:
            m_stmt = m_stmt.where(MegoldasRecord.created_at <= _as_of)
            n_stmt = n_stmt.where(MenetRecord.started_at <= _as_of)
            i_stmt = i_stmt.where(InterakcioRecord.created_at <= _as_of)
        return (s.scalar(m_stmt) or 0) > 0 or (s.scalar(n_stmt) or 0) > 0 or (s.scalar(i_stmt) or 0) > 0


def _repeatable_has_fresh_signal(user: str, engine: Engine, last_award_at: datetime) -> bool:
    return _has_new_activity_after(user, engine, last_award_at)


def _distinct_play_days(session: Session, user: str, from_dt: datetime | None = None) -> list[datetime]:
    from felvi_games.db import MenetRecord
    _as_of = _simulation_as_of.get()
    stmt = (
        select(MenetRecord.started_at)
        .where(MenetRecord.felhasznalo_nev == user)
        .order_by(MenetRecord.started_at)
    )
    if from_dt:
        stmt = stmt.where(MenetRecord.started_at >= from_dt)
    if _as_of is not None:
        stmt = stmt.where(MenetRecord.started_at <= _as_of)
    rows = session.scalars(stmt).all()
    seen: set[str] = set()
    days: list[datetime] = []
    for dt in rows:
        key = _nap(dt).strftime("%Y-%m-%d")
        if key not in seen:
            seen.add(key)
            days.append(_nap(dt))
    return sorted(days)


def _consecutive_days(days: list[datetime]) -> int:
    """Return the longest streak of consecutive calendar days."""
    if not days:
        return 0
    best = current = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _current_streak(days: list[datetime]) -> int:
    """Days in the current trailing streak (must include today or yesterday)."""
    if not days:
        return 0
    today = _nap(datetime.now(timezone.utc))
    streak = 0
    prev = today
    for d in reversed(days):
        if (prev - d).days <= 1:
            streak += 1
            prev = d
        else:
            break
    return streak


# ---------------------------------------------------------------------------
# Rules
# (Each rule is: rule_fn(user, session_id, engine) → bool)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Shared query primitives — called by multiple _rule_* factories below
# ---------------------------------------------------------------------------

def _megoldas_count_ge(user: str, engine: Engine, n: int) -> bool:
    """True if the user has solved ≥ n tasks total (simulation-aware)."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        return (s.scalar(stmt) or 0) >= n


def _pont_sum_ge(user: str, engine: Engine, n: int) -> bool:
    """True if the user has accumulated ≥ n total points (simulation-aware)."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.sum(MegoldasRecord.pont))
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        return (s.scalar(stmt) or 0) >= n


def _play_days_count_ge(user: str, engine: Engine, n: int) -> bool:
    """True if the user has played on ≥ n distinct days (simulation-aware)."""
    with Session(engine) as s:
        days = _distinct_play_days(s, user)
    return len(days) >= n


def _hour_any_exists(
    user: str, engine: Engine, *, before: str | None = None, from_hour: str | None = None
) -> bool:
    """True if any answer exists before *before* or from *from_hour* (local time, HH)."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    hour_col = func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime"))
    cond = hour_col < before if before is not None else hour_col >= from_hour
    with Session(engine) as s:
        stmt = (select(MegoldasRecord.created_at)
                .where(MegoldasRecord.felhasznalo_nev == user, cond))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        return s.scalars(stmt).first() is not None


def _menet_distinct_covers(user: str, engine: Engine, col, required: set) -> bool:
    """True if distinct values of *col* in MenetRecord cover all *required* values."""
    from felvi_games.db import MenetRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = select(col).where(MenetRecord.felhasznalo_nev == user)
        if _as_of is not None:
            stmt = stmt.where(MenetRecord.started_at <= _as_of)
        return required.issubset(set(s.scalars(stmt).all()))


# ---------------------------------------------------------------------------
# Rule factories — produce RuleFn callables from a single threshold parameter
# ---------------------------------------------------------------------------

def _make_megoldas_count_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        return _megoldas_count_ge(user, engine, n)
    return _rule


def _make_pont_sum_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        return _pont_sum_ge(user, engine, n)
    return _rule


def _make_play_days_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        return _play_days_count_ge(user, engine, n)
    return _rule


def _make_sorozat_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        return _max_helyes_sorozat(user, engine) >= n
    return _rule


def _make_streak_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        with Session(engine) as s:
            days = _distinct_play_days(s, user)  # _simulation_as_of applied inside
        return _current_streak(days) >= n
    return _rule


def _make_longest_streak_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        with Session(engine) as s:
            days = _distinct_play_days(s, user)  # _simulation_as_of applied inside
        return _consecutive_days(days) >= n
    return _rule


def _make_recent_play_days_rule(n: int):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        with Session(engine) as s:
            cutoff = _sim_now() - timedelta(days=7)
            days = _distinct_play_days(s, user, from_dt=cutoff)
        return len(days) >= n
    return _rule


def _make_hour_rule(*, before: str | None = None, from_hour: str | None = None):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        return _hour_any_exists(user, engine, before=before, from_hour=from_hour)
    return _rule


def _make_menet_cover_rule(required: set[str], attr: str):
    def _rule(user: str, session_id: int | None, engine: Engine) -> bool:
        from felvi_games.db import MenetRecord

        column = getattr(MenetRecord, attr)
        return _menet_distinct_covers(user, engine, column, required)
    return _rule


def _max_helyes_sorozat(user: str, engine: Engine) -> int:
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (
            select(MegoldasRecord.helyes)
            .where(MegoldasRecord.felhasznalo_nev == user)
            .order_by(MegoldasRecord.created_at)
        )
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        rows = s.scalars(stmt).all()
    best = cur = 0
    for h in rows:
        if h:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _rule_villam(user: str, session_id: int | None, engine: Engine) -> bool:
    """Any answer that scored points (including partial) within 10 seconds."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(func.count()).select_from(MegoldasRecord)
                .where(MegoldasRecord.felhasznalo_nev == user,
                       MegoldasRecord.pont > 0,
                       MegoldasRecord.elapsed_sec.is_not(None),
                       MegoldasRecord.elapsed_sec <= 10.0))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        cnt = s.scalar(stmt) or 0
    return cnt >= 1


def _rule_hint_nelkul_20(user: str, session_id: int | None, engine: Engine) -> bool:
    """Last 20 answers (any outcome) without asking for a hint."""
    from felvi_games.db import MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(MegoldasRecord.segitseg_kert)
                .where(MegoldasRecord.felhasznalo_nev == user)
                .order_by(MegoldasRecord.created_at.desc())
                .limit(20))
        if _as_of is not None:
            stmt = (select(MegoldasRecord.segitseg_kert)
                    .where(MegoldasRecord.felhasznalo_nev == user,
                           MegoldasRecord.created_at <= _as_of)
                    .order_by(MegoldasRecord.created_at.desc())
                    .limit(20))
        rows = s.scalars(stmt).all()
    return len(rows) == 20 and not any(rows)


def _rule_magas_pontossag(user: str, session_id: int | None, engine: Engine) -> bool:
    """At least 80% of total possible points earned across 50+ attempts."""
    from felvi_games.db import FeladatRecord, MegoldasRecord
    _as_of = _simulation_as_of.get()
    _f = [MegoldasRecord.felhasznalo_nev == user]
    if _as_of is not None:
        _f.append(MegoldasRecord.created_at <= _as_of)
    with Session(engine) as s:
        total = s.scalar(
            select(func.count()).select_from(MegoldasRecord).where(*_f)
        ) or 0
        if total < 50:
            return False
        earned = s.scalar(
            select(func.sum(MegoldasRecord.pont)).where(*_f)
        ) or 0
        max_possible = s.scalar(
            select(func.sum(FeladatRecord.max_pont))
            .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
            .where(*_f)
        ) or 0
    return max_possible > 0 and (earned / max_possible) >= 0.80


def _rule_pentek_matek_honap(user: str, session_id: int | None, engine: Engine) -> bool:
    """All Fridays of the *previous* calendar month were covered with matek sessions."""
    from felvi_games.db import MenetRecord
    now = datetime.now(timezone.utc)
    # previous month
    first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev = first_this - timedelta(seconds=1)
    first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # find all Fridays in that month
    fridays: set[str] = set()
    d = first_prev
    while d <= last_prev:
        if d.weekday() == 4:  # Friday
            fridays.add(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    if not fridays:
        return False

    with Session(engine) as s:
        rows = s.scalars(
            select(MenetRecord.started_at)
            .where(
                MenetRecord.felhasznalo_nev == user,
                MenetRecord.targy == "matek",
                MenetRecord.started_at >= first_prev,
                MenetRecord.started_at <= last_prev,
            )
        ).all()

    played_fridays = {_nap(dt).strftime("%Y-%m-%d") for dt in rows if _nap(dt).weekday() == 4}
    return fridays.issubset(played_fridays)


def _rule_minden_feladattipus(user: str, session_id: int | None, engine: Engine) -> bool:
    from felvi_games.db import FeladatRecord, MegoldasRecord
    _as_of = _simulation_as_of.get()
    with Session(engine) as s:
        stmt = (select(FeladatRecord.feladat_tipus)
                .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
                .where(MegoldasRecord.felhasznalo_nev == user))
        if _as_of is not None:
            stmt = stmt.where(MegoldasRecord.created_at <= _as_of)
        rows = s.scalars(stmt).all()
    return _FELADAT_TIPUSOK_OSSZ.issubset({r for r in rows if r})


def _rule_heti_bajnok(user: str, session_id: int | None, engine: Engine) -> bool:
    """5+ distinct play days in the current week (Mon–Sun)."""
    now = _sim_now()
    start_of_week = _nap(now) - timedelta(days=now.weekday())
    with Session(engine) as s:
        days = _distinct_play_days(s, user, from_dt=start_of_week)  # upper bound via _simulation_as_of
    return len(days) >= 5


# ---------------------------------------------------------------------------
# Dynamic condition evaluator
# Condition types, parameters, events, and evaluators live in condition_registry.
# See felvi_games.condition_registry.advertise_all() for the full schema.
# ---------------------------------------------------------------------------


def _trigger_bucket(trigger_tipus: str | None, session_id: int | None) -> str | None:
    if trigger_tipus is None:
        return "session" if session_id is not None else None

    trigger = trigger_tipus.strip().lower()
    if not trigger:
        return "session" if session_id is not None else None
    if trigger in {"menet", "session", "menet_indul", "menet_vegzett"}:
        return "session"
    if trigger in {
        "helyes_valasz",
        "reszleges_valasz",
        "helytelen_valasz",
        "segitseg_kert",
        "hibajelezes",
        "tts_lejatszo",
        "feladat_kihagyas",
    }:
        return "answer"
    if trigger in {"ujraertekeles", "ujraertekeles_jutalom"}:
        return "interaction"
    return trigger


def _condition_matches_trigger(condition: dict, trigger_tipus: str | None, session_id: int | None) -> bool:
    trigger_bucket = _trigger_bucket(trigger_tipus, session_id)
    if trigger_bucket is None:
        return True
    return trigger_bucket in cr.effective_events(condition)


def _window_bounds(valid_from: datetime | None, window_h: float) -> tuple[datetime, datetime | None]:
    """Resolve (cutoff, upper) bounds, honoring simulation context."""
    if valid_from is not None:
        cutoff = valid_from if valid_from.tzinfo else valid_from.replace(tzinfo=timezone.utc)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_h)
    _as_of = _simulation_as_of.get()
    upper = _as_of if _as_of is not None else None
    return cutoff, upper


def _eval_dynamic_condition(
    user: str,
    condition: dict | list[dict],
    engine: Engine,
    valid_from: datetime | None = None,
    trigger_tipus: str | None = None,
    session_id: int | None = None,
) -> bool:
    """Evaluate one condition dict or a compound list (AND semantics).

    ``valid_from``: only events AFTER this timestamp count.  When None,
    falls back to the rolling ``now - window_hours`` window.
    """
    items = condition if isinstance(condition, list) else [condition]
    for cond in items:
        spec = cr.from_dict(cond)
        if spec is None:
            return False
        if not _condition_matches_trigger(cond, trigger_tipus, session_id):
            return False
        n = int(cond.get("n", 1))
        window_h = float(cond.get("window_hours", 24))
        cutoff, upper = _window_bounds(valid_from, window_h)
        with Session(engine) as s:
            if not spec.evaluator(user, cond, n, cutoff, upper, s):
                return False
    return True


def _count_dynamic_condition(
    user: str,
    condition: dict | list[dict],
    engine: Engine,
    valid_from: datetime | None = None,
) -> tuple[int | None, int | None]:
    """Return (current_value, target_n) for progress display.

    For compound conditions returns the progress of the first sub-condition.
    Returns (None, None) when the condition type has no countable scalar.
    """
    first = condition[0] if isinstance(condition, list) else condition
    spec = cr.from_dict(first)
    if spec is None or spec.count_fn is None:
        return None, None
    n = int(first.get("n", 1))
    ctype = cr.condition_type(first)
    target = 1 if ctype == "interakcio_exists" else n
    window_h = float(first.get("window_hours", 24))
    cutoff, upper = _window_bounds(valid_from, window_h)
    with Session(engine) as s:
        cnt = spec.count_fn(user, first, cutoff, upper, s)
    if cnt is None:
        return None, None
    return cnt, target


# ---------------------------------------------------------------------------
# Rule registry
# Each entry: (rule_fn, permanent_only=False|True)
# permanent_only=True  → only award once; never re-check once earned
# repeatable medals    → use Erem.ismetelheto flag
# ---------------------------------------------------------------------------

RuleFn = Callable[[str, int | None, "Engine"], bool]

SZABALY_REGISTRY: dict[str, RuleFn] = {
    "tiz_feladat": _make_megoldas_count_rule(10),
    "huszonot_feladat": _make_megoldas_count_rule(25),
    "otven_feladat": _make_megoldas_count_rule(50),
    "szaz_feladat": _make_megoldas_count_rule(100),
    "otszaz_feladat": _make_megoldas_count_rule(500),
    "ezer_feladat": _make_megoldas_count_rule(1000),
    "sorozat_5": _make_sorozat_rule(5),
    "sorozat_10": _make_sorozat_rule(10),
    "sorozat_20": _make_sorozat_rule(20),
    "villam": _rule_villam,
    "hint_nelkul_20": _rule_hint_nelkul_20,
    "magas_pontossag": _rule_magas_pontossag,
    "het_egymas_utan": _make_streak_rule(7),
    "harom_het_egymas_utan": _make_longest_streak_rule(21),
    "pentek_matek_honap": _rule_pentek_matek_honap,
    "heti_haromszor": _make_recent_play_days_rule(3),
    "reggeli_tanulas": _make_hour_rule(before="08"),
    "esti_tanulas": _make_hour_rule(from_hour="22"),
    "mindket_targy": _make_menet_cover_rule({"matek", "magyar"}, "targy"),
    "minden_szint": _make_menet_cover_rule(_SZINTEK_OSSZ, "szint"),
    "minden_feladattipus": _rule_minden_feladattipus,
    "visszatero": _make_play_days_rule(3),
    "visszatero_tiz": _make_play_days_rule(10),
    "szaz_pont": _make_pont_sum_rule(100),
    "otszaz_pont": _make_pont_sum_rule(500),
    "heti_bajnok": _rule_heti_bajnok,
}


def _check_fresh_signal(
    erem_id: str,
    erem: Erem,
    user: str,
    engine: Engine,
    last_award_at: datetime,
    trigger_tipus: str | None = None,
) -> bool:
    """Return True if new qualifying activity exists since the last award.

    Used by check_new_medals() to gate repeatable medal re-grants.
    """
    if erem.condition:
        cond_anchor = erem.condition_valid_from
        cond_anchor_utc = _as_utc(cond_anchor) if cond_anchor is not None else None
        from_anchor = last_award_at + timedelta(microseconds=1)
        if cond_anchor_utc is not None and cond_anchor_utc > from_anchor:
            from_anchor = cond_anchor_utc
        try:
            return _eval_dynamic_condition(
                user,
                erem.condition,
                engine,
                valid_from=from_anchor,
                trigger_tipus=trigger_tipus,
            )
        except Exception:  # noqa: BLE001
            return False
    return _repeatable_has_fresh_signal(user, engine, last_award_at)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_new_medals(
    user: str,
    session_id: int | None,
    repo: FeladatRepository,
    trigger_tipus: str | None = None,
) -> list[Erem]:
    """Evaluate all rules and grant any newly earned medals.

    Loads the catalog from DB (global medals + private medals targeted at
    *user*) so new medals can be added mid-game without a restart.
    Returns the list of Erem objects that were freshly awarded this call.
    """
    engine = repo._engine
    newly_earned: list[Erem] = []
    now = _sim_now()

    catalog = repo.get_erem_katalogus(user)
    earned_any_ids = {fe.erem_id for fe in repo.get_eremek(user, include_expired=True)}
    szerzes_map = repo.get_erem_szerzesek_map(user)
    latest_award_by_id = {
        erem_id: _as_utc(stamps[0])
        for erem_id, stamps in szerzes_map.items()
        if stamps
    }

    logger.info(
        "check_new_medals start | user=%s session=%s catalog_size=%d",
        user, session_id, len(catalog),
    )

    skipped_already_has = 0
    skipped_cooldown = 0
    skipped_no_new_signal = 0
    skipped_no_rule = 0
    rule_errors: list[str] = []

    for erem_id, erem in catalog.items():
        last_award_at = latest_award_by_id.get(erem_id)

        # Non-repeatable + already earned → skip
        if not erem.ismetelheto and erem_id in earned_any_ids:
            skipped_already_has += 1
            logger.debug("skip already_earned | user=%s medal=%s", user, erem_id)
            continue

        # Repeatable medals need a cooldown so historical truth does not re-fire instantly.
        if erem.ismetelheto and last_award_at is not None and not _cooldown_elapsed(erem, last_award_at, now):
            skipped_cooldown += 1
            logger.debug(
                "skip cooldown | user=%s medal=%s last_award=%s now=%s",
                user,
                erem_id,
                last_award_at.isoformat(),
                now.isoformat(),
            )
            continue

        # No rule registered → check for dynamic condition, else manual-grant only
        rule_fn = SZABALY_REGISTRY.get(erem_id)
        if rule_fn is None:
            if erem.condition:
                # Dynamic LLM-generated condition: use creation timestamp as anchor
                # so only events AFTER the medal was created count towards the goal.
                try:
                    earned = _eval_dynamic_condition(
                        user, erem.condition, engine,
                        valid_from=erem.condition_valid_from,
                        trigger_tipus=trigger_tipus,
                        session_id=session_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    rule_errors.append(erem_id)
                    logger.warning(
                        "dynamic_rule_error | user=%s medal=%s error=%s",
                        user, erem_id, exc, exc_info=True,
                    )
                    continue
            else:
                skipped_no_rule += 1
                logger.debug("skip no_rule | user=%s medal=%s", user, erem_id)
                continue
        else:
            try:
                earned = rule_fn(user, session_id, engine)
            except Exception as exc:  # noqa: BLE001 – rules must not crash the game
                rule_errors.append(erem_id)
                logger.warning(
                    "rule_error | user=%s medal=%s error=%s",
                    user, erem_id, exc, exc_info=True,
                )
                continue

        logger.debug(
            "rule_result | user=%s medal=%s session=%s result=%s",
            user, erem_id, session_id, earned,
        )

        if earned:
            if erem.ismetelheto and last_award_at is not None:
                if not _check_fresh_signal(
                    erem_id,
                    erem,
                    user,
                    engine,
                    last_award_at,
                    trigger_tipus=trigger_tipus,
                ):
                    skipped_no_new_signal += 1
                    logger.debug(
                        "skip no_new_signal | user=%s medal=%s last_award=%s",
                        user,
                        erem_id,
                        last_award_at.isoformat(),
                    )
                    continue

            expires_at: datetime | None = None
            # Expiry is only used for repeatable medals; one-time medals stay in history forever.
            if erem.ideiglenes and erem.ismetelheto and erem.ervenyes_napig:
                expires_at = now + timedelta(days=erem.ervenyes_napig)
            repo.grant_erem(user, erem_id, lejarat_at=expires_at)
            newly_earned.append(erem)
            logger.info(
                "medal_granted | user=%s medal=%s nev=%r session=%s expires=%s",
                user, erem_id, erem.nev, session_id,
                expires_at.isoformat() if expires_at else None,
            )

    logger.info(
        "check_new_medals done | user=%s session=%s granted=%d "
        "skipped_owned=%d skipped_cooldown=%d skipped_no_new_signal=%d "
        "skipped_no_rule=%d errors=%d",
        user, session_id, len(newly_earned),
        skipped_already_has, skipped_cooldown, skipped_no_new_signal,
        skipped_no_rule, len(rule_errors),
    )
    if rule_errors:
        logger.warning("rule_errors detail | user=%s medals=%s", user, rule_errors)

    return newly_earned


def get_all_medals_for_user(
    user: str,
    repo: FeladatRepository,
    include_expired: bool = False,
) -> list[tuple[Erem, FelhasznaloErem]]:
    """Return (catalog_entry, earned_record) pairs for a user.

    Catalog is loaded from DB so it reflects any runtime additions.
    """
    earned = repo.get_eremek(user, include_expired=include_expired)
    catalog = repo.get_erem_katalogus(user)
    result: list[tuple[Erem, FelhasznaloErem]] = []
    for fe in earned:
        erem = catalog.get(fe.erem_id)
        if erem is not None:
            result.append((erem, fe))
    return result


# ---------------------------------------------------------------------------
# Rule simulation (dry-run, no DB writes)
# ---------------------------------------------------------------------------


@_dataclass
class RuleSimResult:
    erem_id: str
    nev: str
    ikon: str
    result: bool
    already_earned: bool
    ismetelheto: bool
    error: str | None = None


def simulate_medal_rules(
    user: str,
    engine: Engine,
    earned_erem_ids: set[str],
) -> list[RuleSimResult]:
    """Evaluate every registered rule for *user* without awarding anything.

    Returns one RuleSimResult per registered rule (static) plus any dynamic
    medals in the catalog that have a condition but no registered rule.
    """
    results: list[RuleSimResult] = []

    # Static rules
    for erem_id, rule_fn in SZABALY_REGISTRY.items():
        erem = EREM_KATALOGUS.get(erem_id)
        nev = erem.nev if erem else erem_id
        ikon = erem.ikon if erem else "🏅"
        ismetelheto = erem.ismetelheto if erem else False
        try:
            rule_result = rule_fn(user, None, engine)
            error = None
        except Exception as exc:
            rule_result = False
            error = str(exc)
        results.append(RuleSimResult(
            erem_id=erem_id,
            nev=nev,
            ikon=ikon,
            result=bool(rule_result),
            already_earned=erem_id in earned_erem_ids,
            ismetelheto=ismetelheto,
            error=error,
        ))

    # Dynamic medals (not in static registry but have a condition)
    for erem_id, erem in EREM_KATALOGUS.items():
        if erem_id in SZABALY_REGISTRY:
            continue
        if not erem.condition:
            continue
        try:
            rule_result = _eval_dynamic_condition(user, erem.condition, engine)
            error = None
        except Exception as exc:
            rule_result = False
            error = str(exc)
        results.append(RuleSimResult(
            erem_id=erem_id,
            nev=erem.nev,
            ikon=erem.ikon,
            result=bool(rule_result),
            already_earned=erem_id in earned_erem_ids,
            ismetelheto=erem.ismetelheto,
            error=error,
        ))

    return results
