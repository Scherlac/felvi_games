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
from sqlalchemy.orm import Session, selectinload

from felvi_games.kpi_registry import KPIRegistry, KPIQueryContext
from felvi_games.models import InterakcioTipus

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# (user, condition_dict, n, cutoff, upper, session) -> bool
CondEvalFn = Callable[[str, dict, int, datetime, "datetime | None", Session], bool]

# (user, condition_dict, cutoff, upper, session) -> int | None
CondCountFn = Callable[[str, dict, datetime, "datetime | None", Session], "int | None"]

# (user, condition_dict, cutoff, upper, session) -> scalar value
KPICalcFn = Callable[[str, dict, datetime, "datetime | None", Session], "int | float | None"]


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


_KPI_REGISTRY: dict[str, KPIParamDef] = {}
_KPI_ENGINE = KPIRegistry()


def _attempt_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    """Return attempt rows for the user up to upper bound; KPIRegistry applies windows."""
    from felvi_games.db import MegoldasRecord

    stmt = (
        select(MegoldasRecord)
        .options(selectinload(MegoldasRecord.menet))
        .where(
            MegoldasRecord.felhasznalo_nev == ctx.user,
            MegoldasRecord.created_at <= ctx.upper,
        )
        .order_by(MegoldasRecord.created_at)
    )
    return list(s.scalars(stmt).all())


def _attempt_timestamp(row: Any) -> datetime | None:
    """Extract created_at from an attempt row for KPI window filtering."""
    return getattr(row, "created_at", None)


def _attempt_points(row: Any, ctx: KPIQueryContext) -> int | float | None:
    """Return earned points for one attempt row."""
    value = getattr(row, "pont", None)
    return float(value) if isinstance(value, (int, float)) else None


def _attempt_count_if(row: Any, predicate: Callable[[Any, KPIQueryContext], bool], ctx: KPIQueryContext) -> int | None:
    return 1 if predicate(row, ctx) else None


def _attempt_is_correct(row: Any, ctx: KPIQueryContext) -> bool:
    return bool(getattr(row, "helyes", False))


def _attempt_is_fast_correct(row: Any, ctx: KPIQueryContext) -> bool:
    points = getattr(row, "pont", None)
    elapsed = getattr(row, "elapsed_sec", None)
    return isinstance(points, (int, float)) and points > 0 and isinstance(elapsed, (int, float)) and elapsed <= 10.0


def _attempt_matches_subject(row: Any, ctx: KPIQueryContext) -> bool:
    subject = str(ctx.condition.get("subject", "")).strip()
    menet = getattr(row, "menet", None)
    return bool(subject) and getattr(menet, "targy", None) == subject


def _attempt_before_hour(row: Any, ctx: KPIQueryContext) -> bool:
    ts = _attempt_timestamp(row)
    if ts is None:
        return False
    hour = int(ctx.condition.get("hour", 8))
    return ts.astimezone().hour < hour


def _attempt_after_hour(row: Any, ctx: KPIQueryContext) -> bool:
    ts = _attempt_timestamp(row)
    if ts is None:
        return False
    hour = int(ctx.condition.get("hour", 22))
    return ts.astimezone().hour >= hour


def _session_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    """Return session rows for the user up to upper bound; KPIRegistry applies windows."""
    from felvi_games.db import MenetRecord

    stmt = (
        select(MenetRecord)
        .options(selectinload(MenetRecord.megoldasok))
        .where(
            MenetRecord.felhasznalo_nev == ctx.user,
            MenetRecord.started_at <= ctx.upper,
        )
        .order_by(MenetRecord.started_at)
    )
    return list(s.scalars(stmt).all())


def _session_timestamp(row: Any) -> datetime | None:
    return getattr(row, "started_at", None)


def _interaction_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    """Return interaction rows for the user up to upper bound; KPIRegistry applies windows."""
    from felvi_games.db import InterakcioRecord

    stmt = (
        select(InterakcioRecord)
        .where(
            InterakcioRecord.felhasznalo_nev == ctx.user,
            InterakcioRecord.created_at <= ctx.upper,
        )
        .order_by(InterakcioRecord.created_at)
    )
    return list(s.scalars(stmt).all())


def _interaction_timestamp(row: Any) -> datetime | None:
    return getattr(row, "created_at", None)


def _interaction_matches(row: Any, ctx: KPIQueryContext) -> int | None:
    from felvi_games.models import InterakcioTipus

    raw = ctx.condition.get("event_type", "")
    event_type = raw.value if isinstance(raw, InterakcioTipus) else str(raw).strip()
    if not event_type or getattr(row, "tipus", None) != event_type:
        return None

    for col in ("targy", "szint", "feladat_id"):
        val = ctx.condition.get(col)
        if isinstance(val, str) and val.strip() and getattr(row, col, None) != val.strip():
            return None

    meta_filter = ctx.condition.get("meta_contains")
    if isinstance(meta_filter, str) and meta_filter.strip():
        meta_value = getattr(row, "meta", None)
        if not isinstance(meta_value, str) or meta_filter.strip() not in meta_value:
            return None
    return 1


_KPI_ENGINE.register(
    name="attempt_items",
    type="item",
    query_fn=_attempt_query,
    timestamp_fn=_attempt_timestamp,
    description="Attempt rows up to upper bound.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="attempt_points",
    type="value",
    base="attempt_items",
    property_fn=_attempt_points,
    description="Points earned over attempt rows.",
    metric_name="sum",
)

_KPI_ENGINE.register(
    name="correct_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_is_correct, ctx),
    description="Correct attempts over attempt rows.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="helyes_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_is_correct, ctx),
    description="Correct attempts over attempt rows (alias).",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="fast_correct_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_is_fast_correct, ctx),
    description="Fast correct attempts over attempt rows.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="subject_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_matches_subject, ctx),
    description="Subject-filtered attempts over attempt rows.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="before_hour_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_before_hour, ctx),
    description="Attempts before the configured local hour.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="after_hour_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_after_hour, ctx),
    description="Attempts at or after the configured local hour.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="session_items",
    type="item",
    query_fn=_session_query,
    timestamp_fn=_session_timestamp,
    description="Session rows up to upper bound.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="interaction_items",
    type="item",
    query_fn=_interaction_query,
    timestamp_fn=_interaction_timestamp,
    description="Interaction rows up to upper bound.",
    metric_name="count",
)

_KPI_ENGINE.register(
    name="matching_interactions",
    type="value",
    base="interaction_items",
    property_fn=_interaction_matches,
    description="Interaction rows matching the configured filters.",
    metric_name="count",
)


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


def _kpi_attempt_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    """Use KPIRegistry for attempt_count decomposition."""
    param = _KPI_ENGINE.kpi_parameter(
        "attempt_items",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    # Access total_count property to trigger lazy evaluation
    return int(param.total_count or 0)


def _kpi_correct_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "correct_attempts",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _kpi_points_sum(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "attempt_points",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_sum or 0)


def _kpi_fast_correct_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "fast_correct_attempts",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _kpi_subject_attempt_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "subject_attempts",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _kpi_before_hour_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "before_hour_attempts",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _kpi_after_hour_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "after_hour_attempts",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _kpi_session_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int:
    param = _KPI_ENGINE.kpi_parameter(
        "session_items",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _kpi_interakcio_count(user: str, condition: dict, cutoff: datetime, upper: datetime | None, s: Session) -> int | None:
    param = _KPI_ENGINE.kpi_parameter(
        "matching_interactions",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)


def _attempt_rows(
    user: str,
    cutoff: datetime | None,
    upper: datetime | None,
    s: Session,
    *,
    condition: dict[str, Any] | None = None,
) -> list[Any]:
    return _KPI_ENGINE.kpi_rows(
        "attempt_items",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
    )


def _session_rows(
    user: str,
    cutoff: datetime | None,
    upper: datetime | None,
    s: Session,
    *,
    condition: dict[str, Any] | None = None,
) -> list[Any]:
    return _KPI_ENGINE.kpi_rows(
        "session_items",
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
    )


def _helyes_sequence(rows: list[Any]) -> list[bool]:
    return [bool(getattr(row, "helyes", False)) for row in rows]


def _max_streak(seq: list[bool]) -> int:
    best = cur = 0
    for h in seq:
        if h:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _perfect_session_count(session_rows: list[Any]) -> int:
    perfect = 0
    for rec in session_rows:
        if rec is None or rec.ended_at is None or rec.feladat_limit <= 0 or rec.megoldott < rec.feladat_limit:
            continue
        rows = list(getattr(rec, "megoldasok", []) or [])
        total = len(rows)
        helyes = sum(1 for row in rows if getattr(row, "helyes", False))
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
    return _max_streak(_helyes_sequence(_attempt_rows(user, None, upper, s))) >= n

def _eval_tokeletes_session(user, condition, n, cutoff, upper, s):
    session_rows = [row for row in _session_rows(user, cutoff, upper, s) if getattr(row, "ended_at", None) is not None]
    return _perfect_session_count(session_rows) >= n

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

register_kpi_param(KPIParamDef(
    name="attempt_count",
    description="Total attempts in the active window.",
    calc_fn=_kpi_attempt_count,
))

register_kpi_param(KPIParamDef(
    name="correct_count",
    description="Correct attempts in the active window.",
    calc_fn=_kpi_correct_count,
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

register_kpi_param(KPIParamDef(
    name="before_hour_count",
    description="Attempts before local hour in the active window.",
    calc_fn=_kpi_before_hour_count,
    key_fields=("hour",),
))

register_kpi_param(KPIParamDef(
    name="after_hour_count",
    description="Attempts after local hour in the active window.",
    calc_fn=_kpi_after_hour_count,
    key_fields=("hour",),
))

register_kpi_param(KPIParamDef(
    name="session_count",
    description="Started sessions in the active window.",
    calc_fn=_kpi_session_count,
))

register_kpi_param(KPIParamDef(
    name="interaction_count",
    description="Interaction event count in the active window with optional filters.",
    calc_fn=_kpi_interakcio_count,
    key_fields=("event_type", "targy", "szint", "feladat_id", "meta_contains"),
))

_KPI_BOOTSTRAP_DONE = True


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

def _play_days(session_rows: list[Any]) -> list[datetime]:
    """Sorted list of distinct play-day datetimes (UTC midnight)."""
    seen: set[str] = set()
    days: list[datetime] = []
    for row in session_rows:
        dt = getattr(row, "started_at", None)
        if not isinstance(dt, datetime):
            continue
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
    return len(_play_days(_session_rows(user, None, upper, s))) >= n

def _eval_recent_play_days(user, condition, n, cutoff, upper, s):
    """Distinct play days within the rolling window (uses cutoff)."""
    days = _play_days(_session_rows(user, None, upper, s))
    return sum(1 for d in days if d >= cutoff) >= n

def _eval_day_streak(user, condition, n, cutoff, upper, s):
    """Current trailing consecutive play-day streak >= n."""
    days = _play_days(_session_rows(user, None, upper, s))
    if not days:
        return False
    streak = _day_streak_current(days)
    return streak >= n

def _eval_day_streak_max(user, condition, n, cutoff, upper, s):
    """All-time longest consecutive play-day streak >= n."""
    return _day_streak_max(_play_days(_session_rows(user, None, upper, s))) >= n

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
    return len(_play_days(_session_rows(user, None, upper, s)))

def _count_recent_play_days(user, condition, cutoff, upper, s):
    days = _play_days(_session_rows(user, None, upper, s))
    return sum(1 for d in days if d >= cutoff)

def _count_day_streak(user, condition, cutoff, upper, s):
    days = _play_days(_session_rows(user, None, upper, s))
    if not days:
        return 0
    return _day_streak_current(days)

def _count_day_streak_max(user, condition, cutoff, upper, s):
    return _day_streak_max(_play_days(_session_rows(user, None, upper, s)))

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
