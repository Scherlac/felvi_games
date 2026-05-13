from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
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
    name="session_items",
    type="item",
    query_fn=_session_query,
    timestamp_fn=_session_timestamp,
    description="Session rows up to upper bound.",
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
