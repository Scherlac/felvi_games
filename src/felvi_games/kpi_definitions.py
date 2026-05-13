from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from felvi_games.kpi_registry import KPIQueryContext, KPIRegistry
from felvi_games.models import InterakcioTipus


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
    return getattr(row, "created_at", None)


def _attempt_points(row: Any, ctx: KPIQueryContext) -> int | float | None:
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
    ts_local = (ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts).astimezone()
    hour = int(ctx.condition.get("hour", 8))
    return ts_local.hour < hour


def _attempt_after_hour(row: Any, ctx: KPIQueryContext) -> bool:
    ts = _attempt_timestamp(row)
    if ts is None:
        return False
    ts_local = (ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts).astimezone()
    hour = int(ctx.condition.get("hour", 22))
    return ts_local.hour >= hour


def _attempt_on_special_date(row: Any, ctx: KPIQueryContext) -> bool:
    ts = _attempt_timestamp(row)
    if ts is None:
        return False
    date_mmdd = str(ctx.condition.get("date", "")).strip()
    if not date_mmdd:
        return False
    ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    return ts_utc.strftime("%m-%d") == date_mmdd


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


def _session_is_maraton(row: Any, ctx: KPIQueryContext) -> bool:
    sid = ctx.condition.get("session_id")
    if sid is not None:
        try:
            if int(sid) != int(getattr(row, "id", -1)):
                return False
        except (TypeError, ValueError):
            return False
    return (
        getattr(row, "ended_at", None) is not None
        and int(getattr(row, "feladat_limit", 0) or 0) >= 30
        and int(getattr(row, "megoldott", 0) or 0) >= 30
    )


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


def _gate_rows(ok: bool, upper: datetime) -> list[dict[str, datetime]]:
    return [{"created_at": upper}] if ok else []


def _gate_timestamp(row: Any) -> datetime | None:
    if isinstance(row, dict):
        value = row.get("created_at")
        return value if isinstance(value, datetime) else None
    return None


def _recent_n_attempt_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    from felvi_games.db import MegoldasRecord

    n = max(int(ctx.condition.get("n", 1)), 0)
    stmt = (
        select(MegoldasRecord)
        .where(
            MegoldasRecord.felhasznalo_nev == ctx.user,
            MegoldasRecord.created_at <= ctx.upper,
        )
        .order_by(MegoldasRecord.created_at.desc())
        .limit(n)
    )
    return list(s.scalars(stmt).all())


def _attempt_hint_requested(row: Any, ctx: KPIQueryContext) -> int | None:
    return 1 if bool(getattr(row, "segitseg_kert", False)) else None


def _pontossag_gate_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    from felvi_games.db import FeladatRecord, MegoldasRecord

    min_ratio = float(ctx.condition.get("min_ratio", 0.8))
    n = int(ctx.condition.get("n", 1))
    filters = [
        MegoldasRecord.felhasznalo_nev == ctx.user,
        MegoldasRecord.created_at <= ctx.upper,
    ]

    total = s.scalar(select(func.count()).select_from(MegoldasRecord).where(*filters)) or 0
    if total < n:
        return []

    earned = s.scalar(select(func.sum(MegoldasRecord.pont)).where(*filters)) or 0
    max_possible = s.scalar(
        select(func.sum(FeladatRecord.max_pont))
        .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
        .where(*filters)
    ) or 0
    ok = max_possible > 0 and (earned / max_possible) >= min_ratio
    return _gate_rows(ok, ctx.upper)


def _menet_cover_gate_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    from felvi_games.db import MenetRecord

    attr = str(ctx.condition.get("attr", "")).strip()
    values = ctx.condition.get("values", [])
    if not attr or not values:
        return []

    required = set(values)
    col = getattr(MenetRecord, attr, None)
    if col is None:
        return []

    stmt = select(col).where(
        MenetRecord.felhasznalo_nev == ctx.user,
        MenetRecord.started_at <= ctx.upper,
    )
    ok = required.issubset(set(s.scalars(stmt).all()))
    return _gate_rows(ok, ctx.upper)


_FELADAT_TIPUSOK_COVER = frozenset({
    "nyilt_valasz", "tobbvalasztos", "parositas", "igaz_hamis", "fogalmazas", "kitoltes",
})


def _feladattipus_cover_gate_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
    from felvi_games.db import FeladatRecord, MegoldasRecord

    stmt = (
        select(FeladatRecord.feladat_tipus)
        .join(MegoldasRecord, MegoldasRecord.feladat_id == FeladatRecord.id)
        .where(
            MegoldasRecord.felhasznalo_nev == ctx.user,
            MegoldasRecord.created_at <= ctx.upper,
        )
    )
    rows = s.scalars(stmt).all()
    ok = _FELADAT_TIPUSOK_COVER.issubset({r for r in rows if r})
    return _gate_rows(ok, ctx.upper)


def _pentek_matek_gate_query(ctx: KPIQueryContext, s: Session) -> list[Any]:
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
        return []

    rows = s.scalars(
        select(MenetRecord.started_at).where(
            MenetRecord.felhasznalo_nev == ctx.user,
            MenetRecord.targy == "matek",
            MenetRecord.started_at >= first_prev,
            MenetRecord.started_at <= last_prev,
        )
    ).all()

    def _day(dt: datetime) -> datetime:
        x = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        return x.replace(hour=0, minute=0, second=0, microsecond=0)

    played_fridays = {_day(dt).strftime("%Y-%m-%d") for dt in rows if _day(dt).weekday() == 4}
    ok = fridays.issubset(played_fridays)
    return _gate_rows(ok, ctx.upper)


KPI_ENGINE = KPIRegistry()

KPI_ENGINE.register(
    name="attempt_items",
    type="item",
    query_fn=_attempt_query,
    timestamp_fn=_attempt_timestamp,
    description="Attempt rows up to upper bound.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="attempt_points",
    type="value",
    base="attempt_items",
    property_fn=_attempt_points,
    description="Points earned over attempt rows.",
    metric_name="sum",
)

KPI_ENGINE.register(
    name="correct_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_is_correct, ctx),
    description="Correct attempts over attempt rows.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="helyes_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_is_correct, ctx),
    description="Correct attempts over attempt rows (alias).",
    metric_name="count",
)

KPI_ENGINE.register(
    name="fast_correct_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_is_fast_correct, ctx),
    description="Fast correct attempts over attempt rows.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="hint_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(
        row, lambda r, c: bool(getattr(r, "segitseg_kert", False)), ctx
    ),
    description="Attempts where a hint was requested.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="subject_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_matches_subject, ctx),
    description="Subject-filtered attempts over attempt rows.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="before_hour_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_before_hour, ctx),
    description="Attempts before the configured local hour.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="after_hour_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_after_hour, ctx),
    description="Attempts at or after the configured local hour.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="special_date_attempts",
    type="value",
    base="attempt_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _attempt_on_special_date, ctx),
    description="Attempts that happened on the configured MM-DD date.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="session_items",
    type="item",
    query_fn=_session_query,
    timestamp_fn=_session_timestamp,
    description="Session rows up to upper bound.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="maraton_sessions",
    type="value",
    base="session_items",
    property_fn=lambda row, ctx: _attempt_count_if(row, _session_is_maraton, ctx),
    description="Completed sessions with at least 30 tasks solved.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="interaction_items",
    type="item",
    query_fn=_interaction_query,
    timestamp_fn=_interaction_timestamp,
    description="Interaction rows up to upper bound.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="matching_interactions",
    type="value",
    base="interaction_items",
    property_fn=_interaction_matches,
    description="Interaction rows matching the configured filters.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="recent_n_attempt_items",
    type="item",
    query_fn=_recent_n_attempt_query,
    timestamp_fn=_attempt_timestamp,
    description="Most recent N attempt rows up to upper bound.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="recent_n_hint_requests",
    type="value",
    base="recent_n_attempt_items",
    property_fn=_attempt_hint_requested,
    description="Hint-requested attempts among most recent N attempts.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="pontossag_gate",
    type="item",
    query_fn=_pontossag_gate_query,
    timestamp_fn=_gate_timestamp,
    description="Single-row gate when pontossag condition is satisfied.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="menet_cover_gate",
    type="item",
    query_fn=_menet_cover_gate_query,
    timestamp_fn=_gate_timestamp,
    description="Single-row gate when required menet attribute values are covered.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="feladattipus_cover_gate",
    type="item",
    query_fn=_feladattipus_cover_gate_query,
    timestamp_fn=_gate_timestamp,
    description="Single-row gate when all required task types are covered.",
    metric_name="count",
)

KPI_ENGINE.register(
    name="pentek_matek_gate",
    type="item",
    query_fn=_pentek_matek_gate_query,
    timestamp_fn=_gate_timestamp,
    description="Single-row gate when all Fridays of previous month include matek play.",
    metric_name="count",
)
