"""
condition_registry.py
---------------------
Self-describing condition type registry for medal evaluation.

Each ConditionDef captures everything about one condition type:
  name        – unique type string  (condition["type"])
  description – plain language for LLM prompt generation
  params      – validated parameter schema  (ParamSpec per field)
  events      – default trigger buckets {"answer","session","interaction"}
  evaluator   – (user, condition, n, cutoff, upper, session) -> bool
  count_fn    – (user, condition, cutoff, upper, session) -> int | None
                optional; returns current progress value for display

Compound conditions
  A medal condition may be a single dict OR a list of dicts.
  When a list is given, all sub-conditions must pass (AND semantics).
  Example:
    [{"type": "feladat_count", "n": 5, "window_hours": 2},
     {"type": "after_hour",    "hour": 18}]

Public API
  register(spec)        – add a ConditionDef to the registry
  get(name)             – look up by type string
  all_conditions()      – ordered list of registered ConditionDef
  from_dict(d)          – look up the ConditionDef for a condition dict
  effective_events(d)   – trigger buckets for a condition dict
  advertise_all()       – structured text block for LLM prompt generation
  eval_condition(...)   – evaluate one condition dict
  eval_conditions(...)  – evaluate a single dict or a list (AND compound)
  condition_count(...)  – raw progress count for one condition dict
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from felvi_games.models import InterakcioTipus

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# (user, condition_dict, cutoff, upper, session) -> bool
CondEvalFn = Callable[[str, dict, int, datetime, "datetime | None", Session], bool]

# (user, condition_dict, cutoff, upper, session) -> int | float | None
CondCountFn = Callable[[str, dict, datetime, "datetime | None", Session], "int | float | None"]

# (user, condition_dict, cutoff, upper, session) -> scalar or collection value
KPICalcFn = Callable[[str, dict, datetime, "datetime | None", Session], "Any"]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _is_real_dimension_value(value: object) -> bool:
    """Check if a value is a real, non-empty dimension value (not 'all', '*', etc.)."""
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return bool(normalized) and normalized not in {"mind", "osszes", "összes", "all", "*"}


# ---------------------------------------------------------------------------
# ParamSpec — single parameter schema with validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParamSpec:
    type: type
    required: bool = False
    default: Any = None
    description: str = ""
    choices: list[Any] | None = None
    min_val: Any = None
    max_val: Any = None

    def validate(self, name: str, value: Any) -> Any:
        """Coerce and validate *value*. Returns coerced value or raises ValueError."""
        if value is None:
            if self.required:
                raise ValueError(f"Required param '{name}' is missing")
            return self.default
        if self.type is list:
            if not isinstance(value, list):
                raise ValueError(f"Param '{name}' must be a list, got {value!r}")
            return value
        try:
            value = self.type(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Param '{name}' must be {self.type.__name__}, got {value!r}"
            ) from None
        if self.choices is not None and value not in self.choices:
            raise ValueError(
                f"Param '{name}' must be one of {self.choices}, got {value!r}"
            )
        if self.min_val is not None and value < self.min_val:
            raise ValueError(f"Param '{name}' must be >= {self.min_val}, got {value!r}")
        if self.max_val is not None and value > self.max_val:
            raise ValueError(f"Param '{name}' must be <= {self.max_val}, got {value!r}")
        return value


# ---------------------------------------------------------------------------
# ConditionDef — one condition type definition
# ---------------------------------------------------------------------------

@dataclass
class ConditionDef:
    name: str
    description: str
    params: dict[str, ParamSpec]
    events: set[str]         # default trigger buckets; overridable via condition["events"]
    evaluator: CondEvalFn
    count_fn: CondCountFn | None = None   # None → not countable (progress display unavailable)

    def validate_params(self, condition: dict) -> dict:
        """Validate all params from *condition*. Returns cleaned dict with defaults applied."""
        result: dict = {"type": self.name}
        for pname, pspec in self.params.items():
            result[pname] = pspec.validate(pname, condition.get(pname))
        return result

    def serialize(self, **kwargs: Any) -> dict:
        """Build a minimal valid condition dict from keyword arguments."""
        result: dict = {"type": self.name}
        for pname, pspec in self.params.items():
            val = kwargs.get(pname, pspec.default)
            if val is not None:
                result[pname] = val
        return result

    def advertise(self) -> str:
        """Structured description for LLM prompt generation."""
        lines = [
            f"type: {self.name!r}  |  triggers: {sorted(self.events)}",
            f"  {self.description}",
            "  params:",
        ]
        for pname, pspec in self.params.items():
            req = " *(required)*" if pspec.required else f" [default={pspec.default!r}]"
            extras: list[str] = []
            if pspec.choices:
                extras.append(f"one of {pspec.choices}")
            if pspec.min_val is not None or pspec.max_val is not None:
                extras.append(f"range {pspec.min_val}..{pspec.max_val}")
            suffix = f"  ({', '.join(extras)})" if extras else ""
            lines.append(
                f"    {pname} ({pspec.type.__name__}){req}: {pspec.description}{suffix}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# KPI parameter registry (condition building blocks)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KPIParamDef:
    name: str
    description: str
    calc_fn: KPICalcFn
    key_fields: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()  # e.g., ("window", "total", "daily") - modes this KPI supports
    # When modes is non-empty, condition dict can include "mode" key to select behavior


_KPI_REGISTRY: dict[str, KPIParamDef] = {}


def register_kpi_param(spec: KPIParamDef) -> KPIParamDef:
    """Register one KPI calculator. Returns spec (allows chaining)."""
    _KPI_REGISTRY[spec.name] = spec
    return spec


def get_kpi_param(name: str) -> KPIParamDef | None:
    return _KPI_REGISTRY.get(name)


def _cache_value_normalized(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_cache_value_normalized(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), _cache_value_normalized(v)) for k, v in value.items()))
    if isinstance(value, set):
        return tuple(sorted(_cache_value_normalized(v) for v in value))
    return value


def _cache_ts_key(value: datetime | None) -> str:
    if value is None:
        return "none"
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def kpi_parameter_value(
    user: str,
    kpi_name: str,
    condition: dict,
    cutoff: datetime,
    upper: datetime | None,
    s: Session,
) -> int | float | None:
    """Return one KPI value, cached per-session and parameterized by condition fields."""
    spec = get_kpi_param(kpi_name)
    if spec is None:
        return None

    cache = s.info.setdefault("_kpi_param_cache", {})
    key = (
        "kpi",
        kpi_name,
        user,
        _cache_ts_key(cutoff),
        _cache_ts_key(upper),
        tuple(
            (name, _cache_value_normalized(condition.get(name)))
            for name in spec.key_fields
        ),
    )
    if key in cache:
        return cache[key]

    value = spec.calc_fn(user, condition, cutoff, upper, s)
    cache[key] = value
    return value


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ConditionDef] = {}


def register(spec: ConditionDef) -> ConditionDef:
    """Register a ConditionDef. Returns spec (allows chaining)."""
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ConditionDef | None:
    return _REGISTRY.get(name)


def all_conditions() -> list[ConditionDef]:
    return list(_REGISTRY.values())


def from_dict(d: dict) -> ConditionDef | None:
    return _REGISTRY.get(condition_type(d))


def condition_type(d: dict) -> str:
    return str(d.get("type", "")).strip()


def effective_events(condition: dict) -> set[str]:
    """Return trigger buckets for *condition*, respecting any 'events' override."""
    raw = condition.get("events")
    if isinstance(raw, str) and raw.strip():
        return {raw.strip().lower()}
    if isinstance(raw, (list, tuple, set)):
        evs = {str(e).strip().lower() for e in raw if str(e).strip()}
        if evs:
            return evs
    spec = from_dict(condition)
    return spec.events if spec else {"answer", "session", "interaction"}


def advertise_all() -> str:
    """Structured description of all condition types — for LLM prompt generation."""
    lines = ["=== Supported medal condition types ===", ""]
    for spec in _REGISTRY.values():
        lines.append(spec.advertise())
        lines.append("")
    lines += [
        "--- Compound conditions ---",
        "Set medal condition to a JSON list to AND multiple types together.",
        '  Example: [{"type": "feladat_count", "n": 5, "window_hours": 2},',
        '            {"type": "after_hour", "hour": 18}]',
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compound evaluation helpers
# ---------------------------------------------------------------------------

def eval_condition(
    user: str,
    condition: dict,
    engine: Any,
    *,
    cutoff: datetime,
    upper: datetime | None,
    session_id: int | None = None,
    trigger_tipus: str | None = None,
) -> bool:
    """Evaluate a single condition dict. Returns False for unknown types."""
    from felvi_games.achievements import _condition_matches_trigger  # avoid top-level cycle
    spec = from_dict(condition)
    if spec is None:
        return False
    if not _condition_matches_trigger(condition, trigger_tipus, session_id):
        return False
    n = int(condition.get("n", 1))
    with Session(engine) as s:
        return spec.evaluator(user, condition, n, cutoff, upper, s)


def eval_conditions(
    user: str,
    condition: dict | list[dict],
    engine: Any,
    *,
    cutoff: datetime,
    upper: datetime | None,
    session_id: int | None = None,
    trigger_tipus: str | None = None,
) -> bool:
    """Evaluate a single condition or a compound list (AND semantics)."""
    items = condition if isinstance(condition, list) else [condition]
    return all(
        eval_condition(
            user, c, engine,
            cutoff=cutoff, upper=upper,
            session_id=session_id, trigger_tipus=trigger_tipus,
        )
        for c in items
    )


def condition_count(
    user: str,
    condition: dict,
    *,
    cutoff: datetime,
    upper: datetime | None,
) -> tuple[int | None, int | None]:
    """Return (current, target) for progress display. Both None if not countable."""
    spec = from_dict(condition)
    if spec is None or spec.count_fn is None:
        return None, None
    n = int(condition.get("n", 1))
    target = 1 if condition_type(condition) == "interakcio_exists" else n
    # count_fn needs a session; caller doesn't pass engine here, so we return
    # None — actual counting is done inside _count_dynamic_condition in achievements.py
    # which passes a Session directly. This function is a schema-level helper only.
    return None, target   # counting must go through session-aware path in achievements.py


# ---------------------------------------------------------------------------
# Shared query helpers (used only by condition evaluators below)
# ---------------------------------------------------------------------------

def _q_megoldas_count(
    user: str,
    cutoff: datetime,
    upper: datetime | None,
    s: Session,
    *,
    extra: tuple = (),
) -> int:
    from felvi_games.db import MegoldasRecord  # lazy — avoids import cycle at module load
    stmt = (
        select(func.count()).select_from(MegoldasRecord)
        .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff)
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    if extra:
        stmt = stmt.where(*extra)
    return s.scalar(stmt) or 0


def _q_megoldas_sum(
    user: str, cutoff: datetime, upper: datetime | None, s: Session
) -> int:
    from felvi_games.db import MegoldasRecord
    stmt = (
        select(func.sum(MegoldasRecord.pont))
        .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff)
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    return s.scalar(stmt) or 0


def _q_menet_count(
    user: str, cutoff: datetime, upper: datetime | None, s: Session, *, extra: tuple = ()
) -> int:
    from felvi_games.db import MenetRecord
    stmt = (
        select(func.count()).select_from(MenetRecord)
        .where(MenetRecord.felhasznalo_nev == user, MenetRecord.started_at >= cutoff)
    )
    if upper:
        stmt = stmt.where(MenetRecord.started_at <= upper)
    if extra:
        stmt = stmt.where(*extra)
    return s.scalar(stmt) or 0


def _q_hour_count(
    user: str,
    cutoff: datetime,
    upper: datetime | None,
    s: Session,
    *,
    before_hh: str | None = None,
    from_hh: str | None = None,
) -> int:
    from felvi_games.db import MegoldasRecord
    hh = before_hh if before_hh is not None else from_hh
    assert hh is not None
    hour_col = func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime"))
    predicate = hour_col < hh if before_hh is not None else hour_col >= hh
    stmt = (
        select(func.count()).select_from(MegoldasRecord)
        .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff, predicate)
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    return s.scalar(stmt) or 0


def _q_subject_count(
    user: str, subject: str, cutoff: datetime, upper: datetime | None, s: Session
) -> int:
    from felvi_games.db import MegoldasRecord, MenetRecord
    stmt = (
        select(func.count()).select_from(MegoldasRecord)
        .join(MenetRecord, MenetRecord.id == MegoldasRecord.menet_id)
        .where(
            MegoldasRecord.felhasznalo_nev == user,
            MenetRecord.targy == subject,
            MegoldasRecord.created_at >= cutoff,
        )
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    return s.scalar(stmt) or 0


def _q_interakcio_count(
    user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session
) -> int | None:
    from felvi_games.db import InterakcioRecord
    from felvi_games.models import InterakcioTipus
    raw = condition.get("event_type", "")
    event_type = raw.value if isinstance(raw, InterakcioTipus) else str(raw).strip()
    if not event_type:
        return None
    stmt = (
        select(func.count()).select_from(InterakcioRecord)
        .where(
            InterakcioRecord.felhasznalo_nev == user,
            InterakcioRecord.tipus == event_type,
            InterakcioRecord.created_at >= cutoff,
        )
    )
    if upper:
        stmt = stmt.where(InterakcioRecord.created_at <= upper)
    for col in ("targy", "szint", "feladat_id"):
        val = condition.get(col)
        if isinstance(val, str) and val.strip():
            stmt = stmt.where(getattr(InterakcioRecord, col) == val.strip())
    meta = condition.get("meta_contains")
    if isinstance(meta, str) and meta.strip():
        stmt = stmt.where(InterakcioRecord.meta.contains(meta.strip()))
    return s.scalar(stmt) or 0


def _kpi_points_sum(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    return _q_megoldas_sum(user, cutoff, upper, s)


def _kpi_fast_correct_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    from felvi_games.db import MegoldasRecord

    return _q_megoldas_count(
        user,
        cutoff,
        upper,
        s,
        extra=(
            MegoldasRecord.pont > 0,
            MegoldasRecord.elapsed_sec.is_not(None),
            MegoldasRecord.elapsed_sec <= 10.0,
        ),
    )


def _kpi_subject_attempt_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    return _q_subject_count(user, str(condition.get("subject", "")), cutoff, upper, s)


def _kpi_interakcio_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int | None:
    return _q_interakcio_count(user, condition, cutoff, upper, s)


# ---------------------------------------------------------------------------
# Unified KPI calculators (supporting multiple modes via condition["mode"])
# ---------------------------------------------------------------------------

def _kpi_attempt_count_unified(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int | list[dict]:
    """
    Unified attempt count calculator supporting three modes:
    - "window" (default): attempts in active window
    - "total": all-time attempt count
    - "daily": daily breakdown for last 7 days (returns list[dict])
    """
    from felvi_games.db import MegoldasRecord
    mode = condition.get("mode", "window")
    
    if mode == "total":
        return s.scalar(select(func.count()).select_from(MegoldasRecord)
                       .where(MegoldasRecord.felhasznalo_nev == user)) or 0
    
    elif mode == "daily":
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        rows = s.execute(
            select(MegoldasRecord.created_at, MegoldasRecord.helyes, MegoldasRecord.pont)
            .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff_7d)
            .order_by(MegoldasRecord.created_at.asc())
        ).all()
        daily: dict[str, dict] = {}
        for created_at, is_correct, points in rows:
            created_utc = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            day_key = created_utc.date().isoformat()
            if day_key not in daily:
                daily[day_key] = {"date": day_key, "attempts": 0, "correct": 0, "points": 0, "accuracy_pct": 0.0}
            daily[day_key]["attempts"] += 1
            daily[day_key]["points"] += int(points or 0)
            if is_correct:
                daily[day_key]["correct"] += 1
        for bucket in daily.values():
            attempts = int(bucket["attempts"])
            bucket["accuracy_pct"] = round(int(bucket["correct"]) / attempts * 100, 1) if attempts else 0.0
        return [daily[key] for key in sorted(daily)]
    
    else:  # "window" (default)
        return _q_megoldas_count(user, cutoff, upper, s)


def _kpi_correct_count_unified(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int | dict:
    """
    Unified correct count supporting:
    - "window" (default): correct in window
    - "total": all-time correct
    - "outcomes": outcome breakdown (helyes/reszleges/helytelen) for last 7d (returns dict)
    """
    from felvi_games.db import MegoldasRecord
    from collections import Counter
    mode = condition.get("mode", "window")
    
    if mode == "total":
        return s.scalar(select(func.count()).select_from(MegoldasRecord)
                       .where(MegoldasRecord.felhasznalo_nev == user,
                              MegoldasRecord.helyes == True)) or 0  # noqa: E712
    
    elif mode == "outcomes":
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        rows = s.execute(
            select(MegoldasRecord.helyes, MegoldasRecord.pont)
            .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff_7d)
        ).all()
        outcomes = Counter()
        for is_correct, points in rows:
            if is_correct:
                outcomes["helyes"] += 1
            elif int(points or 0) > 0:
                outcomes["reszleges"] += 1
            else:
                outcomes["helytelen"] += 1
        return dict(outcomes)
    
    else:  # "window" (default)
        return _q_megoldas_count(
            user, cutoff, upper, s,
            extra=(MegoldasRecord.helyes == True,))  # noqa: E712


def _kpi_session_count_unified(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """
    Unified session count supporting:
    - "window" (default): sessions in active window
    - "total": all-time sessions
    - "completed": completed sessions (all-time)
    """
    from felvi_games.db import MenetRecord
    mode = condition.get("mode", "window")
    
    if mode == "total":
        return s.scalar(select(func.count()).select_from(MenetRecord)
                       .where(MenetRecord.felhasznalo_nev == user)) or 0
    
    elif mode == "completed":
        return s.scalar(select(func.count()).select_from(MenetRecord)
                       .where(MenetRecord.felhasznalo_nev == user,
                              MenetRecord.ended_at.is_not(None))) or 0
    
    else:  # "window" (default)
        return _q_menet_count(user, cutoff, upper, s)


def _kpi_hour_count_unified(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """
    Unified hour-based count supporting:
    - "before" (default): before local hour (hour param required; default 8)
    - "after": after local hour (hour param required; default 22)
    """
    mode = condition.get("mode", "before")
    h = int(condition.get("hour", 8 if mode == "before" else 22))
    
    if mode == "before":
        return _q_hour_count(user, cutoff, upper, s, before_hh=f"{h:02d}")
    else:  # "after"
        return _q_hour_count(user, cutoff, upper, s, from_hh=f"{h:02d}")


def _kpi_dimension_session_counts_unified(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> dict:
    """
    Unified dimension (subject/level) session counts supporting:
    - "dimension" (required in condition): "subject" or "level"
    - "all_time" (default) vs "window": whether to include all sessions or just in window
    """
    from felvi_games.db import MenetRecord
    from collections import Counter
    
    dimension = condition.get("dimension", "subject")  # "subject" or "level"
    time_scope = condition.get("time_scope", "all_time")  # "all_time" or "window"
    
    col = MenetRecord.targy if dimension == "subject" else MenetRecord.szint
    stmt = select(col).where(MenetRecord.felhasznalo_nev == user)
    
    if time_scope == "window":
        stmt = stmt.where(MenetRecord.started_at >= cutoff)
        if upper:
            stmt = stmt.where(MenetRecord.started_at <= upper)
    
    values = s.scalars(stmt).all()
    filtered = [v for v in values if _is_real_dimension_value(v)]
    return dict(Counter(filtered))


def _kpi_streak_unified(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """
    Unified streak supporting:
    - "correct_current" (default): current trailing correct answer streak
    - "correct_best": all-time best correct answer streak
    - "play_day_current": current trailing play-day streak
    - "play_day_best": all-time best play-day streak
    """
    mode = condition.get("mode", "correct_current")
    
    if mode == "correct_best":
        from felvi_games.db import MegoldasRecord
        seq = s.scalars(
            select(MegoldasRecord.helyes)
            .where(MegoldasRecord.felhasznalo_nev == user)
            .order_by(MegoldasRecord.created_at)
        ).all()
        return _max_streak(list(seq))
    
    elif mode == "correct_current":
        from felvi_games.db import MegoldasRecord
        seq = s.scalars(
            select(MegoldasRecord.helyes)
            .where(MegoldasRecord.felhasznalo_nev == user)
            .order_by(MegoldasRecord.created_at)
        ).all()
        if not seq:
            return 0
        cur = 0
        for v in reversed(seq):
            if v:
                cur += 1
            else:
                break
        return cur
    
    elif mode == "play_day_best":
        days = _q_all_play_days(user, upper, s)
        return _day_streak_max(days)
    
    else:  # "play_day_current" (default)
        days = _q_all_play_days(user, upper, s)
        return _day_streak_current(days)


# ---------------------------------------------------------------------------
# KPI calculators for get_user_stats aggregations
# ---------------------------------------------------------------------------


def _kpi_avg_elapsed_sec(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> float | None:
    """Average elapsed seconds for correct answers (all-time, ignores window)."""
    from felvi_games.db import MegoldasRecord
    return s.scalar(
        select(func.avg(MegoldasRecord.elapsed_sec))
        .where(MegoldasRecord.felhasznalo_nev == user,
               MegoldasRecord.helyes == True,  # noqa: E712
               MegoldasRecord.elapsed_sec.is_not(None))
    )


def _kpi_subjects_used_all_time(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> list[str]:
    """Distinct subjects used (all-time)."""
    from felvi_games.db import MenetRecord
    subjects = s.scalars(
        select(MenetRecord.targy).where(MenetRecord.felhasznalo_nev == user).distinct()
    ).all()
    return sorted({s for s in subjects if _is_real_dimension_value(s)})


def _kpi_levels_used_all_time(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> list[str]:
    """Distinct levels used (all-time)."""
    from felvi_games.db import MenetRecord
    levels = s.scalars(
        select(MenetRecord.szint).where(MenetRecord.felhasznalo_nev == user).distinct()
    ).all()
    return sorted({l for l in levels if _is_real_dimension_value(l)})


def _kpi_hints_last_20_correct(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> dict:
    """Hint statistics from last 20 correct answers (all-time)."""
    from felvi_games.db import MegoldasRecord
    hints = s.scalars(
        select(MegoldasRecord.segitseg_kert)
        .where(MegoldasRecord.felhasznalo_nev == user,
               MegoldasRecord.helyes == True)  # noqa: E712
        .order_by(MegoldasRecord.created_at.desc())
        .limit(20)
    ).all()
    hint_free = sum(1 for h in hints if not h)
    return {"hint_free": hint_free, "hint_used": max(0, len(hints) - hint_free), "total": len(hints)}


def _kpi_play_days_7d(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """Distinct play days in last 7 days."""
    from felvi_games.db import MenetRecord
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    sessions = s.scalars(
        select(MenetRecord.started_at)
        .where(MenetRecord.felhasznalo_nev == user, MenetRecord.started_at >= cutoff_7d)
    ).all()
    return len({dt.date() for dt in sessions})


def _kpi_hint_uses_window(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """Hint uses in the specified window."""
    from felvi_games.db import MegoldasRecord
    stmt = (
        select(func.count()).select_from(MegoldasRecord)
        .where(MegoldasRecord.felhasznalo_nev == user,
               MegoldasRecord.segitseg_kert == True,  # noqa: E712
               MegoldasRecord.created_at >= cutoff)
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    return s.scalar(stmt) or 0


def _kpi_event_count_by_type(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> dict:
    """Event counts by type in the specified window."""
    from felvi_games.db import InterakcioRecord
    from collections import Counter
    stmt = (
        select(InterakcioRecord.tipus)
        .where(InterakcioRecord.felhasznalo_nev == user,
               InterakcioRecord.created_at >= cutoff)
    )
    if upper:
        stmt = stmt.where(InterakcioRecord.created_at <= upper)
    rows = s.scalars(stmt).all()
    return dict(Counter(rows))


def _kpi_task_type_counts_all_time(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> dict:
    """Attempt counts by task type (all-time)."""
    from felvi_games.db import FeladatRecord, MegoldasRecord
    from collections import Counter
    types = s.scalars(
        select(FeladatRecord.feladat_tipus)
        .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
        .where(MegoldasRecord.felhasznalo_nev == user)
    ).all()
    filtered = [t for t in types if _is_real_dimension_value(t)]
    return dict(Counter(filtered))


def _kpi_reevaluations_7d(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """Reevaluations in last 7 days."""
    from felvi_games.db import MegoldasRecord
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    return s.scalar(
        select(func.count()).select_from(MegoldasRecord)
        .where(MegoldasRecord.felhasznalo_nev == user,
               MegoldasRecord.ujraertekelt.is_(True),
               MegoldasRecord.ujraertekelt_at.is_not(None),
               MegoldasRecord.ujraertekelt_at >= cutoff_7d)
    ) or 0


def _kpi_reevaluations_improved_7d(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """Reevaluations with improvement in last 7 days."""
    from felvi_games.db import MegoldasRecord
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    rows = s.execute(
        select(MegoldasRecord.eredeti_pont, MegoldasRecord.pont)
        .where(MegoldasRecord.felhasznalo_nev == user,
               MegoldasRecord.ujraertekelt.is_(True),
               MegoldasRecord.ujraertekelt_at.is_not(None),
               MegoldasRecord.ujraertekelt_at >= cutoff_7d)
    ).all()
    return sum(1 for old_points, new_points in rows 
               if old_points is not None and int(new_points or 0) > int(old_points or 0))


def _kpi_pending_rewards(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """Attempts pending rewards (all-time)."""
    from felvi_games.db import MegoldasRecord
    return s.scalar(
        select(func.count()).select_from(MegoldasRecord)
        .where(MegoldasRecord.felhasznalo_nev == user,
               MegoldasRecord.jutalom_varakozik.is_(True))
    ) or 0


def _kpi_daily_attempts_7d(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> list[dict]:
    """Daily attempt breakdown for last 7 days."""
    from felvi_games.db import MegoldasRecord
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    rows = s.execute(
        select(MegoldasRecord.created_at, MegoldasRecord.helyes, MegoldasRecord.pont)
        .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff_7d)
        .order_by(MegoldasRecord.created_at.asc())
    ).all()
    daily: dict[str, dict] = {}
    for created_at, is_correct, points in rows:
        created_utc = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        day_key = created_utc.date().isoformat()
        if day_key not in daily:
            daily[day_key] = {"date": day_key, "attempts": 0, "correct": 0, "points": 0, "accuracy_pct": 0.0}
        daily[day_key]["attempts"] += 1
        daily[day_key]["points"] += int(points or 0)
        if is_correct:
            daily[day_key]["correct"] += 1
    for bucket in daily.values():
        attempts = int(bucket["attempts"])
        bucket["accuracy_pct"] = round(int(bucket["correct"]) / attempts * 100, 1) if attempts else 0.0
    return [daily[key] for key in sorted(daily)]


def _kpi_answer_outcomes_7d(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> dict:
    """Answer outcome counts (helyes/reszleges/helytelen) for last 7 days."""
    from felvi_games.db import MegoldasRecord
    from collections import Counter
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    rows = s.execute(
        select(MegoldasRecord.helyes, MegoldasRecord.pont)
        .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at >= cutoff_7d)
    ).all()
    outcomes = Counter()
    for is_correct, points in rows:
        if is_correct:
            outcomes["helyes"] += 1
        elif int(points or 0) > 0:
            outcomes["reszleges"] += 1
        else:
            outcomes["helytelen"] += 1
    return dict(outcomes)


def _kpi_recent_events_7d(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> list[dict]:
    """Last 8 events from last 7 days."""
    from felvi_games.db import InterakcioRecord
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    rows = s.execute(
        select(InterakcioRecord.tipus, InterakcioRecord.created_at,
               InterakcioRecord.targy, InterakcioRecord.szint, InterakcioRecord.feladat_id)
        .where(InterakcioRecord.felhasznalo_nev == user, InterakcioRecord.created_at >= cutoff_7d)
        .order_by(InterakcioRecord.created_at.desc())
        .limit(8)
    ).all()
    return [
        {
            "type": str(tipus),
            "created_at": (created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)).isoformat(),
            "targy": targy,
            "szint": szint if _is_real_dimension_value(szint) else None,
            "feladat_id": feladat_id,
        }
        for tipus, created_at, targy, szint, feladat_id in rows
    ]


def _q_helyes_sequence(user: str, upper: datetime | None, s: Session) -> list[bool]:
    from felvi_games.db import MegoldasRecord
    stmt = (
        select(MegoldasRecord.helyes)
        .where(MegoldasRecord.felhasznalo_nev == user)
        .order_by(MegoldasRecord.created_at)
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    return list(s.scalars(stmt).all())


def _q_menet_ids(user: str, cutoff: datetime, upper: datetime | None, s: Session) -> list[int]:
    from felvi_games.db import MenetRecord
    stmt = (
        select(MenetRecord.id)
        .where(
            MenetRecord.felhasznalo_nev == user,
            MenetRecord.ended_at.is_not(None),
            MenetRecord.started_at >= cutoff,
        )
    )
    if upper:
        stmt = stmt.where(MenetRecord.started_at <= upper)
    return list(s.scalars(stmt).all())


def _max_streak(seq: list[bool]) -> int:
    best = cur = 0
    for h in seq:
        if h:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _perfect_session_count(menet_ids: list[int], s: Session) -> int:
    from felvi_games.db import MegoldasRecord, MenetRecord
    perfect = 0
    for mid in menet_ids:
        rec = s.get(MenetRecord, mid)
        if rec is None or rec.feladat_limit <= 0 or rec.megoldott < rec.feladat_limit:
            continue
        total = s.scalar(
            select(func.count()).select_from(MegoldasRecord).where(MegoldasRecord.menet_id == mid)
        ) or 0
        helyes = s.scalar(
            select(func.count()).select_from(MegoldasRecord).where(
                MegoldasRecord.menet_id == mid, MegoldasRecord.helyes == True  # noqa: E712
            )
        ) or 0
        if total > 0 and total == helyes == rec.feladat_limit:
            perfect += 1
    return perfect


# ---------------------------------------------------------------------------
# Evaluators  (one per condition type)
# ---------------------------------------------------------------------------

def _eval_feladat_count(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "attempt_count", condition, cutoff, upper, s) or 0) >= n

def _eval_helyes_count(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "correct_count", condition, cutoff, upper, s) or 0) >= n

def _eval_pont_sum(user, condition, n, cutoff, upper, s):
    if n <= 0:
        return True
    total = int(kpi_parameter_value(user, "points_sum", condition, cutoff, upper, s) or 0)
    return total >= n

def _eval_villam(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "fast_correct_count", condition, cutoff, upper, s) or 0) >= n

def _eval_feladat_subject(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "subject_attempt_count", condition, cutoff, upper, s) or 0) >= n

def _eval_before_hour(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "before_hour_count", condition, cutoff, upper, s) or 0) >= n

def _eval_after_hour(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "after_hour_count", condition, cutoff, upper, s) or 0) >= n

def _eval_session_count(user, condition, n, cutoff, upper, s):
    return int(kpi_parameter_value(user, "session_count", condition, cutoff, upper, s) or 0) >= n

def _eval_streak(user, condition, n, cutoff, upper, s):
    return _max_streak(_q_helyes_sequence(user, upper, s)) >= n

def _eval_tokeletes_session(user, condition, n, cutoff, upper, s):
    return _perfect_session_count(_q_menet_ids(user, cutoff, upper, s), s) >= n

def _eval_maraton(user, condition, n, cutoff, upper, s):
    from felvi_games.db import MenetRecord
    if n < 1:
        return False
    sid = condition.get("session_id")
    if sid is not None:
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return False
        rec = s.get(MenetRecord, sid)
        return bool(rec and rec.feladat_limit >= 30 and rec.megoldott >= 30)
    stmt = (
        select(MenetRecord.feladat_limit, MenetRecord.megoldott)
        .where(
            MenetRecord.felhasznalo_nev == user,
            MenetRecord.started_at >= cutoff,
            MenetRecord.ended_at.is_not(None),
            MenetRecord.feladat_limit >= 30,
            MenetRecord.megoldott >= 30,
        )
    )
    if upper:
        stmt = stmt.where(MenetRecord.started_at <= upper)
    cnt = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return cnt >= n

def _eval_special_date(user, condition, n, cutoff, upper, s):
    from felvi_games.db import MegoldasRecord
    date_mmdd = condition.get("date", "")
    target = int(condition.get("feladat_count", 1))
    cnt = s.scalar(
        select(func.count()).select_from(MegoldasRecord)
        .where(
            MegoldasRecord.felhasznalo_nev == user,
            func.strftime("%m-%d", MegoldasRecord.created_at) == date_mmdd,
        )
    ) or 0
    return cnt >= target

def _eval_interakcio_count(user, condition, n, cutoff, upper, s):
    cnt = kpi_parameter_value(user, "interaction_count", condition, cutoff, upper, s)
    return (cnt or 0) >= n

def _eval_interakcio_exists(user, condition, n, cutoff, upper, s):
    cnt = kpi_parameter_value(user, "interaction_count", condition, cutoff, upper, s)
    return (cnt or 0) >= 1


# ---------------------------------------------------------------------------
# Count functions  (progress display — parallel to evaluators)
# ---------------------------------------------------------------------------

def _count_feladat_count(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "attempt_count", condition, cutoff, upper, s)

def _count_helyes_count(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "correct_count", condition, cutoff, upper, s)

def _count_pont_sum(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "points_sum", condition, cutoff, upper, s)

def _count_villam(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "fast_correct_count", condition, cutoff, upper, s)

def _count_feladat_subject(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "subject_attempt_count", condition, cutoff, upper, s)

def _count_before_hour(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "before_hour_count", condition, cutoff, upper, s)

def _count_after_hour(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "after_hour_count", condition, cutoff, upper, s)

def _count_session_count(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "session_count", condition, cutoff, upper, s)

def _count_interakcio(user, condition, cutoff, upper, s):
    return kpi_parameter_value(user, "interaction_count", condition, cutoff, upper, s)


# ---------------------------------------------------------------------------
# Built-in KPI registrations (reused by evaluators and count_fn paths)
# ---------------------------------------------------------------------------

# Unified attempt_count supporting modes: "window" (default), "total", "daily"
register_kpi_param(KPIParamDef(
    name="attempt_count",
    description="Attempt count with mode support: 'window' (default), 'total' (all-time), 'daily' (7d breakdown).",
    calc_fn=_kpi_attempt_count_unified,
    modes=("window", "total", "daily"),
    key_fields=(),  # mode is implicit in function, not part of external cache key
))

register_kpi_param(KPIParamDef(
    name="correct_count",
    description="Correct count with mode support: 'window' (default), 'total' (all-time), 'outcomes' (7d breakdown).",
    calc_fn=_kpi_correct_count_unified,
    modes=("window", "total", "outcomes"),
    key_fields=(),  # mode is implicit in function, not part of external cache key
))

register_kpi_param(KPIParamDef(
    name="points_sum",
    description="Total earned points in the active window.",
    calc_fn=_kpi_points_sum,
))

register_kpi_param(KPIParamDef(
    name="fast_correct_count",
    description="Fast correct attempts (elapsed<=10s, pont>0) in the active window.",
    calc_fn=_kpi_fast_correct_count,
))

register_kpi_param(KPIParamDef(
    name="subject_attempt_count",
    description="Attempts in a selected subject in the active window.",
    calc_fn=_kpi_subject_attempt_count,
    key_fields=("subject",),
))

# Unified hour_count supporting modes: "before" (default, hour=8), "after" (hour=22)
register_kpi_param(KPIParamDef(
    name="hour_count",
    description="Hour-based attempt count with mode: 'before' (default, hour param), 'after' (hour param).",
    calc_fn=_kpi_hour_count_unified,
    modes=("before", "after"),
    key_fields=("hour",),  # mode defaults based on params, but hour distinguishes calls
))

# Backward compatibility: old evaluators still call before_hour_count/after_hour_count
register_kpi_param(KPIParamDef(
    name="before_hour_count",
    description="Attempts before local hour in the active window (alias for hour_count mode='before').",
    calc_fn=lambda u, c, co, up, s: _kpi_hour_count_unified(u, {**c, "mode": "before"}, co, up, s),
    key_fields=("hour",),
))

register_kpi_param(KPIParamDef(
    name="after_hour_count",
    description="Attempts after local hour in the active window (alias for hour_count mode='after').",
    calc_fn=lambda u, c, co, up, s: _kpi_hour_count_unified(u, {**c, "mode": "after"}, co, up, s),
    key_fields=("hour",),
))

register_kpi_param(KPIParamDef(
    name="session_count",
    description="Session count with mode support: 'window' (default), 'total' (all-time), 'completed' (finished sessions).",
    calc_fn=_kpi_session_count_unified,
    modes=("window", "total", "completed"),
    key_fields=(),  # mode is implicit in function, not part of external cache key
))

register_kpi_param(KPIParamDef(
    name="interaction_count",
    description="Interaction event count in the active window with optional filters.",
    calc_fn=_kpi_interakcio_count,
    key_fields=("event_type", "targy", "szint", "feladat_id", "meta_contains"),
))

# Unified dimension session counts (subject/level with time scope)
register_kpi_param(KPIParamDef(
    name="dimension_session_counts",
    description="Session counts by dimension (subject/level) with time_scope (all_time/window).",
    calc_fn=_kpi_dimension_session_counts_unified,
    modes=("subject_all_time", "subject_window", "level_all_time", "level_window"),
    key_fields=("dimension", "time_scope"),  # these are explicit params
))

# Unified streak counter
register_kpi_param(KPIParamDef(
    name="streak_count",
    description="Streak counters with modes: correct_current, correct_best, play_day_current, play_day_best.",
    calc_fn=_kpi_streak_unified,
    modes=("correct_current", "correct_best", "play_day_current", "play_day_best"),
    key_fields=(),  # mode is implicit in function, not part of external cache key
))

# Wrapper registrations for backward compatibility with get_user_stats
# These route to unified KPIs with specific modes hardcoded

register_kpi_param(KPIParamDef(
    name="total_attempts",
    description="All-time attempt count.",
    calc_fn=lambda u, c, co, up, s: _kpi_attempt_count_unified(u, {**c, "mode": "total"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="total_correct",
    description="All-time correct count.",
    calc_fn=lambda u, c, co, up, s: _kpi_correct_count_unified(u, {**c, "mode": "total"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="total_sessions",
    description="All-time sessions started.",
    calc_fn=lambda u, c, co, up, s: _kpi_session_count_unified(u, {**c, "mode": "total"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="completed_sessions",
    description="All-time sessions completed.",
    calc_fn=lambda u, c, co, up, s: _kpi_session_count_unified(u, {**c, "mode": "completed"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="avg_elapsed_sec",
    description="Average elapsed seconds for correct answers.",
    calc_fn=_kpi_avg_elapsed_sec,
))

register_kpi_param(KPIParamDef(
    name="subjects_used",
    description="Distinct subjects used (all-time).",
    calc_fn=_kpi_subjects_used_all_time,
))

register_kpi_param(KPIParamDef(
    name="levels_used",
    description="Distinct levels used (all-time).",
    calc_fn=_kpi_levels_used_all_time,
))

register_kpi_param(KPIParamDef(
    name="hints_last_20_correct",
    description="Hint statistics from last 20 correct answers.",
    calc_fn=_kpi_hints_last_20_correct,
))

register_kpi_param(KPIParamDef(
    name="correct_streak_best",
    description="All-time best correct answer streak.",
    calc_fn=lambda u, c, co, up, s: _kpi_streak_unified(u, {**c, "mode": "correct_best"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="correct_streak_current",
    description="Current trailing correct answer streak.",
    calc_fn=lambda u, c, co, up, s: _kpi_streak_unified(u, {**c, "mode": "correct_current"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="play_days_7d",
    description="Distinct play days in last 7 days.",
    calc_fn=_kpi_play_days_7d,
))

register_kpi_param(KPIParamDef(
    name="play_day_streak_current",
    description="Current trailing play-day streak.",
    calc_fn=lambda u, c, co, up, s: _kpi_streak_unified(u, {**c, "mode": "play_day_current"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="play_day_streak_best",
    description="All-time best play-day streak.",
    calc_fn=lambda u, c, co, up, s: _kpi_streak_unified(u, {**c, "mode": "play_day_best"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="hint_uses_window",
    description="Hint uses in the specified window.",
    calc_fn=_kpi_hint_uses_window,
))

register_kpi_param(KPIParamDef(
    name="event_count_by_type",
    description="Event counts by type in the specified window.",
    calc_fn=_kpi_event_count_by_type,
))

register_kpi_param(KPIParamDef(
    name="subject_session_counts",
    description="Session counts by subject (all-time).",
    calc_fn=lambda u, c, co, up, s: _kpi_dimension_session_counts_unified(u, {**c, "dimension": "subject", "time_scope": "all_time"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="level_session_counts",
    description="Session counts by level (all-time).",
    calc_fn=lambda u, c, co, up, s: _kpi_dimension_session_counts_unified(u, {**c, "dimension": "level", "time_scope": "all_time"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="subject_session_counts_window",
    description="Session counts by subject within window.",
    calc_fn=lambda u, c, co, up, s: _kpi_dimension_session_counts_unified(u, {**c, "dimension": "subject", "time_scope": "window"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="level_session_counts_window",
    description="Session counts by level within window.",
    calc_fn=lambda u, c, co, up, s: _kpi_dimension_session_counts_unified(u, {**c, "dimension": "level", "time_scope": "window"}, co, up, s),
))

register_kpi_param(KPIParamDef(
    name="task_type_counts",
    description="Attempt counts by task type (all-time).",
    calc_fn=_kpi_task_type_counts_all_time,
))

register_kpi_param(KPIParamDef(
    name="reevaluations_7d",
    description="Reevaluations in last 7 days.",
    calc_fn=_kpi_reevaluations_7d,
))

register_kpi_param(KPIParamDef(
    name="reevaluations_improved_7d",
    description="Reevaluations with improvement in last 7 days.",
    calc_fn=_kpi_reevaluations_improved_7d,
))

register_kpi_param(KPIParamDef(
    name="pending_rewards",
    description="Attempts pending rewards (all-time).",
    calc_fn=_kpi_pending_rewards,
))

register_kpi_param(KPIParamDef(
    name="daily_attempts_7d",
    description="Daily attempt breakdown for last 7 days.",
    calc_fn=_kpi_daily_attempts_7d,
))

register_kpi_param(KPIParamDef(
    name="answer_outcomes_7d",
    description="Answer outcome counts for last 7 days.",
    calc_fn=_kpi_answer_outcomes_7d,
))

register_kpi_param(KPIParamDef(
    name="recent_events_7d",
    description="Last 8 events from last 7 days.",
    calc_fn=_kpi_recent_events_7d,
))


# ---------------------------------------------------------------------------
# Common param specs (reused across multiple conditions)
# ---------------------------------------------------------------------------

_P_N = ParamSpec(int, required=False, default=1, description="Threshold count", min_val=1)
_P_WH = ParamSpec(float, required=False, default=24.0, description="Time window in hours", min_val=0.1)
_P_HOUR_BEFORE = ParamSpec(
    int, required=False, default=8, description="Before this local hour (0-23)",
    min_val=0, max_val=23,
)
_P_HOUR_AFTER = ParamSpec(
    int, required=False, default=22, description="From this local hour (0-23)",
    min_val=0, max_val=23,
)
_P_SUBJECT = ParamSpec(str, required=True, description="Subject: 'matek' or 'magyar'", choices=["matek", "magyar"])
_P_EVENT_TYPE = ParamSpec(str, required=True, description="InterakcioTipus value", 
        choices=[e.value for e in InterakcioTipus]
)
_P_DATE = ParamSpec(str, required=True, description="Calendar date as MM-DD, e.g. '03-15'")
_P_FELADAT_N = ParamSpec(int, required=False, default=1, description="Minimum tasks on the date", min_val=1)
_P_SESSION_ID = ParamSpec(int, required=False, default=None, description="Specific session id (optional)")

# Optional interaction filters
_P_TARGY = ParamSpec(str, required=False, default=None, description="Filter by subject (optional)")
_P_SZINT = ParamSpec(str, required=False, default=None, description="Filter by level (optional)")
_P_FELADAT_ID = ParamSpec(str, required=False, default=None, description="Filter by feladat id (optional)")
_P_META = ParamSpec(str, required=False, default=None, description="Filter by meta substring (optional)")

_INTERAKCIO_PARAMS = {
    "event_type": _P_EVENT_TYPE,
    "window_hours": _P_WH,
    "targy": _P_TARGY,
    "szint": _P_SZINT,
    "feladat_id": _P_FELADAT_ID,
    "meta_contains": _P_META,
}


# ---------------------------------------------------------------------------
# Built-in condition registrations
# ---------------------------------------------------------------------------

register(ConditionDef(
    name="feladat_count",
    description="User solves at least N tasks within the time window.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_feladat_count,
    count_fn=_count_feladat_count,
))

register(ConditionDef(
    name="helyes_count",
    description="User answers at least N tasks correctly within the time window.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_helyes_count,
    count_fn=_count_helyes_count,
))

register(ConditionDef(
    name="pont_sum",
    description="User earns at least N total points within the time window.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_pont_sum,
    count_fn=_count_pont_sum,
))

register(ConditionDef(
    name="villam",
    description="User submits at least N fast correct answers (pont>0 and elapsed<=10s) within the window.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_villam,
    count_fn=_count_villam,
))

register(ConditionDef(
    name="feladat_subject",
    description="User solves at least N tasks of a given subject within the time window.",
    params={"subject": _P_SUBJECT, "n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_feladat_subject,
    count_fn=_count_feladat_subject,
))

register(ConditionDef(
    name="before_hour",
    description="User submits at least N answers before the given local hour within the window.",
    params={"hour": _P_HOUR_BEFORE, "n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_before_hour,
    count_fn=_count_before_hour,
))

register(ConditionDef(
    name="after_hour",
    description="User submits at least N answers at or after the given local hour within the window.",
    params={"hour": _P_HOUR_AFTER, "n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_after_hour,
    count_fn=_count_after_hour,
))

register(ConditionDef(
    name="session_count",
    description="User starts at least N sessions within the time window.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"session"},
    evaluator=_eval_session_count,
    count_fn=_count_session_count,
))

register(ConditionDef(
    name="tokeletes_session",
    description="User completes at least N perfect sessions within the window (all tasks answered correctly).",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"session"},
    evaluator=_eval_tokeletes_session,
    count_fn=None,  # session-level, not a simple count
))

register(ConditionDef(
    name="streak",
    description="User's all-time best streak of consecutive correct answers reaches at least N.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"answer"},
    evaluator=_eval_streak,
    count_fn=None,  # streak is a max, not a sum
))

register(ConditionDef(
    name="maraton",
    description=(
        "User completes at least N sessions of 30+ tasks within the window."
        " Optionally pin to a specific session_id."
    ),
    params={"n": _P_N, "window_hours": _P_WH, "session_id": _P_SESSION_ID},
    events={"session"},
    evaluator=_eval_maraton,
    count_fn=None,
))

register(ConditionDef(
    name="special_date",
    description="User solves at least feladat_count tasks on a specific calendar date (MM-DD, any year).",
    params={"date": _P_DATE, "feladat_count": _P_FELADAT_N},
    events={"answer"},
    evaluator=_eval_special_date,
    count_fn=None,
))

register(ConditionDef(
    name="interakcio_count",
    description="User generates at least N interaction events of a given type within the window.",
    params={"n": _P_N, **_INTERAKCIO_PARAMS},
    events={"interaction"},
    evaluator=_eval_interakcio_count,
    count_fn=_count_interakcio,
))

# ---------------------------------------------------------------------------
# Shared helpers for play-day and streak computation
# ---------------------------------------------------------------------------

def _q_all_play_days(user: str, upper: datetime | None, s: Session) -> list[datetime]:
    """Sorted list of distinct play-day datetimes (UTC midnight), all-time."""
    from felvi_games.db import MenetRecord
    stmt = (
        select(MenetRecord.started_at)
        .where(MenetRecord.felhasznalo_nev == user)
        .order_by(MenetRecord.started_at)
    )
    if upper:
        stmt = stmt.where(MenetRecord.started_at <= upper)
    rows = s.scalars(stmt).all()
    seen: set[str] = set()
    days: list[datetime] = []
    for dt in rows:
        d = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        d = d.replace(hour=0, minute=0, second=0, microsecond=0)
        key = d.strftime("%Y-%m-%d")
        if key not in seen:
            seen.add(key)
            days.append(d)
    return days


def _day_streak_current(days: list[datetime]) -> int:
    """Current trailing streak of consecutive play days (must include today or yesterday)."""
    if not days:
        return 0
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    streak = 0
    prev = today
    for d in reversed(days):
        if (prev - d).days <= 1:
            streak += 1
            prev = d
        else:
            break
    return streak


def _day_streak_max(days: list[datetime]) -> int:
    """All-time longest consecutive play day streak."""
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


# Task types that must all be covered for feladattipus_cover
_FELADAT_TIPUSOK_COVER = frozenset({
    "nyilt_valasz", "tobbvalasztos", "parositas", "igaz_hamis", "fogalmazas", "kitoltes",
})


# ---------------------------------------------------------------------------
# New evaluators
# ---------------------------------------------------------------------------

def _eval_play_days(user, condition, n, cutoff, upper, s):
    """Total distinct play days (all-time, ignores cutoff)."""
    return len(_q_all_play_days(user, upper, s)) >= n

def _eval_recent_play_days(user, condition, n, cutoff, upper, s):
    """Distinct play days within the rolling window (uses cutoff)."""
    days = _q_all_play_days(user, upper, s)
    return sum(1 for d in days if d >= cutoff) >= n

def _eval_day_streak(user, condition, n, cutoff, upper, s):
    """Current trailing consecutive play-day streak >= n."""
    days = _q_all_play_days(user, upper, s)
    if not days:
        return False
    streak = _day_streak_current(days)
    return streak >= n

def _eval_day_streak_max(user, condition, n, cutoff, upper, s):
    """All-time longest consecutive play-day streak >= n."""
    return _day_streak_max(_q_all_play_days(user, upper, s)) >= n

def _eval_hint_nelkul(user, condition, n, cutoff, upper, s):
    """Last N answers contain no hint requests."""
    from felvi_games.db import MegoldasRecord
    stmt = (
        select(MegoldasRecord.segitseg_kert)
        .where(MegoldasRecord.felhasznalo_nev == user)
        .order_by(MegoldasRecord.created_at.desc())
        .limit(n)
    )
    if upper:
        stmt = (
            select(MegoldasRecord.segitseg_kert)
            .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at <= upper)
            .order_by(MegoldasRecord.created_at.desc())
            .limit(n)
        )
    rows = s.scalars(stmt).all()
    return len(rows) == n and not any(rows)

def _eval_pontossag(user, condition, n, cutoff, upper, s):
    """At least n attempts with accuracy >= min_ratio (all-time, ignores cutoff)."""
    from felvi_games.db import FeladatRecord, MegoldasRecord
    min_ratio = float(condition.get("min_ratio", 0.8))
    filters = [MegoldasRecord.felhasznalo_nev == user]
    if upper:
        filters.append(MegoldasRecord.created_at <= upper)
    total = s.scalar(select(func.count()).select_from(MegoldasRecord).where(*filters)) or 0
    if total < n:
        return False
    earned = s.scalar(select(func.sum(MegoldasRecord.pont)).where(*filters)) or 0
    max_possible = s.scalar(
        select(func.sum(FeladatRecord.max_pont))
        .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
        .where(*filters)
    ) or 0
    return max_possible > 0 and (earned / max_possible) >= min_ratio

def _eval_menet_cover(user, condition, n, cutoff, upper, s):
    """Sessions cover all required values of a menet attribute (all-time)."""
    from felvi_games.db import MenetRecord
    attr = str(condition.get("attr", ""))
    values = condition.get("values", [])
    if not attr or not values:
        return False
    required = set(values)
    col = getattr(MenetRecord, attr, None)
    if col is None:
        return False
    stmt = select(col).where(MenetRecord.felhasznalo_nev == user)
    if upper:
        stmt = stmt.where(MenetRecord.started_at <= upper)
    return required.issubset(set(s.scalars(stmt).all()))

def _eval_feladattipus_cover(user, condition, n, cutoff, upper, s):
    """All required feladat_tipus values have been encountered (all-time)."""
    from felvi_games.db import FeladatRecord, MegoldasRecord
    stmt = (
        select(FeladatRecord.feladat_tipus)
        .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
        .where(MegoldasRecord.felhasznalo_nev == user)
    )
    if upper:
        stmt = stmt.where(MegoldasRecord.created_at <= upper)
    rows = s.scalars(stmt).all()
    return _FELADAT_TIPUSOK_COVER.issubset({r for r in rows if r})

def _eval_pentek_matek(user, condition, n, cutoff, upper, s):
    """All Fridays of the previous calendar month were covered with matek sessions."""
    from felvi_games.db import MenetRecord
    now = datetime.now(timezone.utc)
    first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev = first_this - timedelta(seconds=1)
    first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fridays: set[str] = set()
    d = first_prev
    while d <= last_prev:
        if d.weekday() == 4:
            fridays.add(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    if not fridays:
        return False
    rows = s.scalars(
        select(MenetRecord.started_at).where(
            MenetRecord.felhasznalo_nev == user,
            MenetRecord.targy == "matek",
            MenetRecord.started_at >= first_prev,
            MenetRecord.started_at <= last_prev,
        )
    ).all()
    def _day(dt: datetime) -> datetime:
        x = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        return x.replace(hour=0, minute=0, second=0, microsecond=0)
    played_fridays = {_day(dt).strftime("%Y-%m-%d") for dt in rows if _day(dt).weekday() == 4}
    return fridays.issubset(played_fridays)


# ---------------------------------------------------------------------------
# New count functions
# ---------------------------------------------------------------------------

def _count_play_days(user, condition, cutoff, upper, s):
    return len(_q_all_play_days(user, upper, s))

def _count_recent_play_days(user, condition, cutoff, upper, s):
    days = _q_all_play_days(user, upper, s)
    return sum(1 for d in days if d >= cutoff)

def _count_day_streak(user, condition, cutoff, upper, s):
    days = _q_all_play_days(user, upper, s)
    if not days:
        return 0
    return _day_streak_current(days)

def _count_day_streak_max(user, condition, cutoff, upper, s):
    return _day_streak_max(_q_all_play_days(user, upper, s))

def _count_hint_nelkul(user, condition, cutoff, upper, s):
    """Returns how many of the last n answers have no hint (for progress display)."""
    from felvi_games.db import MegoldasRecord
    n = int(condition.get("n", 20))
    stmt = (
        select(MegoldasRecord.segitseg_kert)
        .where(MegoldasRecord.felhasznalo_nev == user)
        .order_by(MegoldasRecord.created_at.desc())
        .limit(n)
    )
    if upper:
        stmt = (
            select(MegoldasRecord.segitseg_kert)
            .where(MegoldasRecord.felhasznalo_nev == user, MegoldasRecord.created_at <= upper)
            .order_by(MegoldasRecord.created_at.desc())
            .limit(n)
        )
    rows = s.scalars(stmt).all()
    return sum(1 for h in rows if not h)


# ---------------------------------------------------------------------------
# New param specs and registrations
# ---------------------------------------------------------------------------

_P_MIN_RATIO = ParamSpec(
    float, required=False, default=0.8,
    description="Minimum accuracy ratio (0.0–1.0)", min_val=0.0, max_val=1.0,
)
_P_ATTR = ParamSpec(
    str, required=True, description="Menet attribute to check: 'targy' or 'szint'",
    choices=["targy", "szint"],
)
_P_VALUES = ParamSpec(list, required=True, description="List of required values")

register(ConditionDef(
    name="play_days",
    description="User has played on at least N distinct calendar days (all-time).",
    params={"n": _P_N},
    events={"session"},
    evaluator=_eval_play_days,
    count_fn=_count_play_days,
))

register(ConditionDef(
    name="recent_play_days",
    description="User has played on at least N distinct days within the rolling window.",
    params={"n": _P_N, "window_hours": _P_WH},
    events={"session"},
    evaluator=_eval_recent_play_days,
    count_fn=_count_recent_play_days,
))

register(ConditionDef(
    name="day_streak",
    description="User's current trailing consecutive play-day streak is at least N.",
    params={"n": _P_N},
    events={"session"},
    evaluator=_eval_day_streak,
    count_fn=_count_day_streak,
))

register(ConditionDef(
    name="day_streak_max",
    description="User's all-time longest consecutive play-day streak is at least N.",
    params={"n": _P_N},
    events={"session"},
    evaluator=_eval_day_streak_max,
    count_fn=_count_day_streak_max,
))

register(ConditionDef(
    name="hint_nelkul",
    description="The last N answers were all submitted without requesting a hint.",
    params={"n": _P_N},
    events={"answer"},
    evaluator=_eval_hint_nelkul,
    count_fn=_count_hint_nelkul,
))

register(ConditionDef(
    name="pontossag",
    description=(
        "User has at least n total attempts and earned >= min_ratio of maximum"
        " possible points (all-time accuracy gate)."
    ),
    params={"n": _P_N, "min_ratio": _P_MIN_RATIO},
    events={"answer"},
    evaluator=_eval_pontossag,
    count_fn=None,
))

register(ConditionDef(
    name="menet_cover",
    description=(
        "User's sessions cover all required values of a menet attribute"
        " ('targy' or 'szint')."
    ),
    params={"attr": _P_ATTR, "values": _P_VALUES},
    events={"session"},
    evaluator=_eval_menet_cover,
    count_fn=None,
))

register(ConditionDef(
    name="feladattipus_cover",
    description="User has solved at least one task of every feladat_tipus.",
    params={},
    events={"answer"},
    evaluator=_eval_feladattipus_cover,
    count_fn=None,
))

register(ConditionDef(
    name="pentek_matek",
    description=(
        "User covered every Friday of the previous calendar month"
        " with at least one matek session."
    ),
    params={},
    events={"session"},
    evaluator=_eval_pentek_matek,
    count_fn=None,
))

register(ConditionDef(
    name="interakcio_exists",
    description="At least one interaction event of a given type exists within the window. n is ignored.",
    params=_INTERAKCIO_PARAMS,
    events={"interaction"},
    evaluator=_eval_interakcio_exists,
    count_fn=_count_interakcio,
))
