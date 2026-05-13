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
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from felvi_games.kpi_definitions import KPI_ENGINE as _KPI_ENGINE
from felvi_games.kpi_registry import (
    _kpi_total_count,
    _kpi_total_sum,
    _kpi_play_days,
    _kpi_max_correct_streak,
    _kpi_perfect_session_count,
    _day_streak_current,
    _day_streak_max,
)
from felvi_games.models import InterakcioTipus

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# (user, condition_dict, n, cutoff, upper, session) -> bool
CondEvalFn = Callable[[str, dict, int, datetime, "datetime | None", Session], bool]

# (user, condition_dict, cutoff, upper, session) -> int | None
CondCountFn = Callable[[str, dict, datetime, "datetime | None", Session], "int | None"]

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
# Evaluators  (one per condition type)
# ---------------------------------------------------------------------------

def _eval_feladat_count(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("attempt_items", user, condition, cutoff, upper, s) >= n

def _eval_helyes_count(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("correct_attempts", user, condition, cutoff, upper, s) >= n

def _eval_pont_sum(user, condition, n, cutoff, upper, s):
    if n <= 0:
        return True
    total = _kpi_total_sum("attempt_points", user, condition, cutoff, upper, s)
    return total >= n

def _eval_villam(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("fast_correct_attempts", user, condition, cutoff, upper, s) >= n

def _eval_feladat_subject(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("subject_attempts", user, condition, cutoff, upper, s) >= n

def _eval_before_hour(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("before_hour_attempts", user, condition, cutoff, upper, s) >= n

def _eval_after_hour(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("after_hour_attempts", user, condition, cutoff, upper, s) >= n

def _eval_session_count(user, condition, n, cutoff, upper, s):
    return _kpi_total_count("session_items", user, condition, cutoff, upper, s) >= n

def _eval_streak(user, condition, n, cutoff, upper, s):
    return _kpi_max_correct_streak(user, upper, s) >= n

def _eval_tokeletes_session(user, condition, n, cutoff, upper, s):
    return _kpi_perfect_session_count(user, cutoff, upper, s) >= n

def _eval_maraton(user, condition, n, cutoff, upper, s):
    if n < 1:
        return False
    return _kpi_total_count("maraton_sessions", user, condition, cutoff, upper, s) >= n

def _eval_special_date(user, condition, n, cutoff, upper, s):
    target = int(condition.get("feladat_count", 1))
    cnt = _kpi_total_count("special_date_attempts", user, condition, cutoff, upper, s)
    return cnt >= target

def _eval_interakcio_count(user, condition, n, cutoff, upper, s):
    cnt = _kpi_total_count("matching_interactions", user, condition, cutoff, upper, s)
    return (cnt or 0) >= n

def _eval_interakcio_exists(user, condition, n, cutoff, upper, s):
    cnt = _kpi_total_count("matching_interactions", user, condition, cutoff, upper, s)
    return (cnt or 0) >= 1


# ---------------------------------------------------------------------------
# Count functions  (progress display — parallel to evaluators)
# ---------------------------------------------------------------------------

def _count_feladat_count(user, condition, cutoff, upper, s):
    return _kpi_total_count("attempt_items", user, condition, cutoff, upper, s)

def _count_helyes_count(user, condition, cutoff, upper, s):
    return _kpi_total_count("correct_attempts", user, condition, cutoff, upper, s)

def _count_pont_sum(user, condition, cutoff, upper, s):
    return _kpi_total_sum("attempt_points", user, condition, cutoff, upper, s)

def _count_villam(user, condition, cutoff, upper, s):
    return _kpi_total_count("fast_correct_attempts", user, condition, cutoff, upper, s)

def _count_feladat_subject(user, condition, cutoff, upper, s):
    return _kpi_total_count("subject_attempts", user, condition, cutoff, upper, s)

def _count_before_hour(user, condition, cutoff, upper, s):
    return _kpi_total_count("before_hour_attempts", user, condition, cutoff, upper, s)

def _count_after_hour(user, condition, cutoff, upper, s):
    return _kpi_total_count("after_hour_attempts", user, condition, cutoff, upper, s)

def _count_session_count(user, condition, cutoff, upper, s):
    return _kpi_total_count("session_items", user, condition, cutoff, upper, s)

def _count_interakcio(user, condition, cutoff, upper, s):
    return _kpi_total_count("matching_interactions", user, condition, cutoff, upper, s)


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
# New evaluators
# ---------------------------------------------------------------------------

def _eval_play_days(user, condition, n, cutoff, upper, s):
    """Total distinct play days (all-time, ignores cutoff)."""
    return len(_kpi_play_days(user, upper, s)) >= n

def _eval_recent_play_days(user, condition, n, cutoff, upper, s):
    """Distinct play days within the rolling window (uses cutoff)."""
    return sum(1 for d in _kpi_play_days(user, upper, s) if d >= cutoff) >= n

def _eval_day_streak(user, condition, n, cutoff, upper, s):
    """Current trailing consecutive play-day streak >= n."""
    return _day_streak_current(_kpi_play_days(user, upper, s)) >= n

def _eval_day_streak_max(user, condition, n, cutoff, upper, s):
    """All-time longest consecutive play-day streak >= n."""
    return _day_streak_max(_kpi_play_days(user, upper, s)) >= n

def _eval_hint_nelkul(user, condition, n, cutoff, upper, s):
    """Last N answers contain no hint requests."""
    recent = _kpi_total_count("recent_n_attempt_items", user, condition, None, upper, s)
    hinted = _kpi_total_count("recent_n_hint_requests", user, condition, None, upper, s)
    return recent == n and hinted == 0

def _eval_pontossag(user, condition, n, cutoff, upper, s):
    """At least n attempts with accuracy >= min_ratio (all-time, ignores cutoff)."""
    return _kpi_total_count("pontossag_gate", user, condition, None, upper, s) >= 1

def _eval_menet_cover(user, condition, n, cutoff, upper, s):
    """Sessions cover all required values of a menet attribute (all-time)."""
    return _kpi_total_count("menet_cover_gate", user, condition, None, upper, s) >= 1

def _eval_feladattipus_cover(user, condition, n, cutoff, upper, s):
    """All required feladat_tipus values have been encountered (all-time)."""
    return _kpi_total_count("feladattipus_cover_gate", user, condition, None, upper, s) >= 1

def _eval_pentek_matek(user, condition, n, cutoff, upper, s):
    """All Fridays of the previous calendar month were covered with matek sessions."""
    return _kpi_total_count("pentek_matek_gate", user, condition, None, upper, s) >= 1


# ---------------------------------------------------------------------------
# New count functions
# ---------------------------------------------------------------------------

def _count_play_days(user, condition, cutoff, upper, s):
    return len(_kpi_play_days(user, upper, s))

def _count_recent_play_days(user, condition, cutoff, upper, s):
    return sum(1 for d in _kpi_play_days(user, upper, s) if d >= cutoff)

def _count_day_streak(user, condition, cutoff, upper, s):
    return _day_streak_current(_kpi_play_days(user, upper, s))

def _count_day_streak_max(user, condition, cutoff, upper, s):
    return _day_streak_max(_kpi_play_days(user, upper, s))

def _count_hint_nelkul(user, condition, cutoff, upper, s):
    """Returns how many of the last n answers have no hint (for progress display)."""
    recent = _kpi_total_count("recent_n_attempt_items", user, condition, None, upper, s)
    hinted = _kpi_total_count("recent_n_hint_requests", user, condition, None, upper, s)
    return max(recent - hinted, 0)


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
