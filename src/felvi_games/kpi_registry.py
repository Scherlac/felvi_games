from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol, cast

from sqlalchemy.orm import Session

JSONScalar = int | float | str | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class SessionLike(Protocol):
    info: dict[str, Any]


KPIType = Literal["item", "value"]


@dataclass(frozen=True)
class KPIWindow:
    """Named time window [cutoff, upper]."""

    window_id: str
    cutoff: datetime
    upper: datetime


@dataclass(frozen=True)
class KPIQueryContext:
    user: str
    condition: dict[str, Any]
    upper: datetime
    cutoff: datetime | None = None
    custom_hours: int | None = None


KPIQueryFn = Callable[[KPIQueryContext, Any], list[Any]]
KPIPropertyFn = Callable[[Any, KPIQueryContext], int | float | None]
KPITimestampFn = Callable[[Any], datetime | None]


@dataclass(frozen=True)
class KPIDef:
    name: str
    type: KPIType
    description: str = ""
    query_fn: KPIQueryFn | None = None
    base: str | None = None
    property_fn: KPIPropertyFn | None = None
    metric_name: str = "count"
    key_fields: tuple[str, ...] = ()
    timestamp_fn: KPITimestampFn | None = None
    stats_supported: frozenset[str] = frozenset({"values", "cases", "total", "min", "max", "trend", "count"})


@dataclass
class KPIParameter:
    """Accessor object for KPI payload fields.

    Provides dot-access for common convenience names:
      - total_count / total_sum
      - count_24h / sum_24h
      - count_7d / sum_7d
      - count_custom_h / sum_custom_h
    """

    registry: KPIRegistry
    name: str
    user: str
    session: Any
    condition: dict[str, Any]
    cutoff: datetime | None
    upper: datetime
    custom_hours: int | None
    requested_stats: set[str]
    spec: KPIDef | None

    _WINDOW_ATTR_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "24h": "rolling_24h",
            "48h": "rolling_48h",
            "7d": "rolling_7d",
            "custom_h": "rolling_custom_h",
        },
        init=False,
        repr=False,
    )

    def to_dict(self) -> dict[str, JSONValue]:
        if self.spec is None:
            return {"name": self.name, "missing": True}
        return self.registry._resolve_payload(
            spec=self.spec,
            name=self.name,
            user=self.user,
            session=self.session,
            condition=self.condition,
            cutoff=self.cutoff,
            upper=self.upper,
            custom_hours=self.custom_hours,
            requested_stats=self.requested_stats,
            required_window_ids=None,
        )

    def max_streak(self, *, filter_fn: Callable[[Any], bool] | None = None) -> int:
        seq = self._streak_sequence(filter_fn=filter_fn)
        best = cur = 0
        for ok in seq:
            if ok:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    def current_streak(self, *, filter_fn: Callable[[Any], bool] | None = None) -> int:
        seq = self._streak_sequence(filter_fn=filter_fn)
        cur = 0
        for ok in reversed(seq):
            if ok:
                cur += 1
            else:
                break
        return cur

    def _streak_sequence(self, *, filter_fn: Callable[[Any], bool] | None) -> list[bool]:
        if self.spec is None:
            return []
        rows = self.registry.kpi_rows(
            self.name,
            user=self.user,
            session=self.session,
            condition=self.condition,
            cutoff=self.cutoff,
            upper=self.upper,
            custom_hours=self.custom_hours,
        )
        if filter_fn is not None:
            return [bool(filter_fn(row)) for row in rows]

        if self.spec.type == "value" and self.spec.property_fn is not None:
            ctx = KPIQueryContext(
                user=self.user,
                condition=self.condition,
                cutoff=self.cutoff,
                upper=self.upper,
                custom_hours=self.custom_hours,
            )
            out: list[bool] = []
            for row in rows:
                value = self.spec.property_fn(row, ctx)
                if value is None:
                    out.append(False)
                elif isinstance(value, (int, float)):
                    out.append(value > 0)
                else:
                    out.append(True)
            return out
        return [True] * len(rows)

    def __getattr__(self, attr: str) -> Any:
        if self.spec is None:
            raise AttributeError(f"{self.__class__.__name__!s} has no attribute {attr!r}")

        if attr.startswith("total_"):
            metric = attr[len("total_") :]
            payload = self.registry._resolve_payload(
                spec=self.spec,
                name=self.name,
                user=self.user,
                session=self.session,
                condition=self.condition,
                cutoff=self.cutoff,
                upper=self.upper,
                custom_hours=self.custom_hours,
                requested_stats={"total"},
                required_window_ids={"all_time"},
            )
            total = payload.get("total")
            if isinstance(total, dict):
                return total.get(metric)
            raise AttributeError(f"{self.__class__.__name__!s} has no attribute {attr!r}")

        if "_" in attr:
            metric, _, suffix = attr.partition("_")
            if suffix in self._WINDOW_ATTR_MAP:
                window_id = self._WINDOW_ATTR_MAP[suffix]
                payload = self.registry._resolve_payload(
                    spec=self.spec,
                    name=self.name,
                    user=self.user,
                    session=self.session,
                    condition=self.condition,
                    cutoff=self.cutoff,
                    upper=self.upper,
                    custom_hours=self.custom_hours,
                    requested_stats={"values"},
                    required_window_ids={window_id},
                )
                values = payload.get("values")
                if not isinstance(values, dict):
                    raise AttributeError(f"{self.__class__.__name__!s} has no attribute {attr!r}")
                window_map = values.get(window_id)
                if isinstance(window_map, dict):
                    metric_values = window_map.get(metric)
                    if isinstance(metric_values, list):
                        return metric_values
        raise AttributeError(f"{self.__class__.__name__!s} has no attribute {attr!r}")


class KPIRegistry:
    """Reference KPI engine with composable base/value parameters and window-aware caching."""

    def __init__(self) -> None:
        self._defs: dict[str, KPIDef] = {}
        self._local_cache: dict[Any, Any] = {}

    def register(
        self,
        *,
        name: str,
        type: KPIType,
        query_fn: KPIQueryFn | None = None,
        base: str | None = None,
        property_fn: KPIPropertyFn | None = None,
        description: str = "",
        metric_name: str = "count",
        key_fields: tuple[str, ...] = (),
        timestamp_fn: KPITimestampFn | None = None,
        stats_supported: set[str] | frozenset[str] | None = None,
    ) -> KPIDef:
        if type == "item":
            if query_fn is None:
                raise ValueError("item KPI requires query_fn")
            if base is not None or property_fn is not None:
                raise ValueError("item KPI must not define base/property_fn")
        elif type == "value":
            if not base:
                raise ValueError("value KPI requires base")
            if property_fn is None:
                raise ValueError("value KPI requires property_fn")
            if query_fn is not None:
                raise ValueError("value KPI must not define query_fn")
        else:
            raise ValueError(f"Unsupported KPI type: {type!r}")

        spec = KPIDef(
            name=name,
            type=type,
            description=description,
            query_fn=query_fn,
            base=base,
            property_fn=property_fn,
            metric_name=metric_name,
            key_fields=key_fields,
            timestamp_fn=timestamp_fn,
            stats_supported=frozenset(stats_supported) if stats_supported else KPIDef.stats_supported,
        )
        self._defs[name] = spec
        return spec

    def get(self, name: str) -> KPIDef | None:
        return self._defs.get(name)

    def all(self) -> list[KPIDef]:
        return list(self._defs.values())

    def kpi_parameter(
        self,
        name: str,
        *,
        user: str,
        session: Any,
        condition: dict[str, Any] | None = None,
        cutoff: datetime | None = None,
        upper: datetime | None = None,
        custom_hours: int | None = None,
        requested_stats: set[str] | None = None,
    ) -> KPIParameter:
        condition = condition or {}
        cutoff = self._normalize_upper(cutoff) if cutoff is not None else None
        upper = self._normalize_upper(upper)
        stats = requested_stats or {"values", "cases", "total", "min", "max", "trend", "count"}
        spec = self.get(name)
        return KPIParameter(
            registry=self,
            name=name,
            user=user,
            session=session,
            condition=condition,
            cutoff=cutoff,
            upper=upper,
            custom_hours=custom_hours,
            requested_stats=set(stats),
            spec=spec,
        )

    def kpi_rows(
        self,
        name: str,
        *,
        user: str,
        session: Any,
        condition: dict[str, Any] | None = None,
        cutoff: datetime | None = None,
        upper: datetime | None = None,
        custom_hours: int | None = None,
    ) -> list[Any]:
        condition = condition or {}
        normalized_cutoff = self._normalize_upper(cutoff) if cutoff is not None else None
        normalized_upper = self._normalize_upper(upper)
        ctx = KPIQueryContext(
            user=user,
            condition=condition,
            cutoff=normalized_cutoff,
            upper=normalized_upper,
            custom_hours=custom_hours,
        )
        spec = self.get(name)
        if spec is None:
            return []
        base = spec
        if spec.type == "value":
            base = self.get(spec.base or "") or spec
        rows = self._fetch_item_rows(base, ctx, session)
        timestamp_fn = base.timestamp_fn or self._default_timestamp
        lower = normalized_cutoff or datetime(1970, 1, 1, tzinfo=timezone.utc)
        return self._rows_in_window(rows, timestamp_fn, lower, normalized_upper)

    def _resolve_payload(
        self,
        *,
        spec: KPIDef,
        name: str,
        user: str,
        session: Any,
        condition: dict[str, Any],
        cutoff: datetime | None,
        upper: datetime,
        custom_hours: int | None,
        requested_stats: set[str],
        required_window_ids: set[str] | None,
    ) -> dict[str, JSONValue]:
        cache = self._session_cache(session)
        payload_key = (
            "kpi_payload",
            name,
            user,
            self._ts_key(cutoff) if cutoff is not None else None,
            self._ts_key(upper),
            custom_hours,
            tuple(sorted(requested_stats)),
            tuple(sorted(required_window_ids)) if required_window_ids else None,
            tuple((k, self._cache_value(condition.get(k))) for k in spec.key_fields),
        )
        if payload_key in cache:
            return cache[payload_key]

        windows = self._build_windows(upper, custom_hours)
        if cutoff is not None and "all_time" in windows:
            windows["all_time"] = KPIWindow("all_time", cutoff, upper)
        if required_window_ids:
            windows = {wid: windows[wid] for wid in windows if wid in required_window_ids}
        ctx = KPIQueryContext(user=user, condition=condition, cutoff=cutoff, upper=upper, custom_hours=custom_hours)
        values = self._window_values(spec, ctx, windows, session)
        payload = self._compute_payload(name, spec, windows, values, requested_stats)
        cache[payload_key] = payload
        return payload

    def _window_values(
        self,
        spec: KPIDef,
        ctx: KPIQueryContext,
        windows: dict[str, KPIWindow],
        session: Any,
    ) -> dict[str, dict[str, list[int | float | None]]]:
        if spec.type == "item":
            rows = self._fetch_item_rows(spec, ctx, session)
            timestamp_fn = spec.timestamp_fn or self._default_timestamp

            def value_of(row: Any) -> int | float | None:
                return 1

        else:
            base = self.get(spec.base or "")
            if base is None:
                return {}
            rows = self._fetch_item_rows(base, ctx, session)
            timestamp_fn = base.timestamp_fn or self._default_timestamp

            def value_of(row: Any) -> int | float | None:
                assert spec.property_fn is not None
                return spec.property_fn(row, ctx)

        out: dict[str, dict[str, list[int | float | None]]] = {}
        metric = spec.metric_name

        for window_id, window in windows.items():
            selected = self._rows_in_window(rows, timestamp_fn, window.cutoff, window.upper)
            if spec.type == "item":
                metric_value: int | float | None = len(selected)
            else:
                total = 0.0
                seen = False
                for row in selected:
                    val = value_of(row)
                    if val is None:
                        continue
                    total += float(val)
                    seen = True
                metric_value = total if seen else 0.0
            out[window_id] = {metric: [metric_value]}
        return out

    def _compute_payload(
        self,
        name: str,
        spec: KPIDef,
        windows: dict[str, KPIWindow],
        values: dict[str, dict[str, list[int | float | None]]],
        requested_stats: set[str],
    ) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "name": name,
            "metric": spec.metric_name,
            "window_ids": list(windows.keys()),
        }
        metric = spec.metric_name

        if "values" in requested_stats and "values" in spec.stats_supported:
            payload["values"] = cast(JSONValue, values)

        if "total" in requested_stats and "total" in spec.stats_supported:
            total_value = self._safe_metric(values, "all_time", metric)
            payload["total"] = {metric: total_value}

        if "cases" in requested_stats and "cases" in spec.stats_supported:
            payload["cases"] = cast(JSONValue, self._cases_payload(values, metric))

        if "trend" in requested_stats and "trend" in spec.stats_supported:
            payload["trend"] = cast(JSONValue, self._trend_payload(values, metric))

        scalar_values: list[float] = []
        for window_map in values.values():
            v = window_map.get(metric, [None])[-1]
            if isinstance(v, (int, float)):
                scalar_values.append(float(v))

        if "min" in requested_stats and "min" in spec.stats_supported:
            payload["min"] = {metric: min(scalar_values) if scalar_values else None}
        if "max" in requested_stats and "max" in spec.stats_supported:
            payload["max"] = {metric: max(scalar_values) if scalar_values else None}
        if "count" in requested_stats and "count" in spec.stats_supported:
            payload["count"] = {metric: len(scalar_values)}

        return payload

    def _cases_payload(
        self,
        values: dict[str, dict[str, list[int | float | None]]],
        metric: str,
    ) -> dict[str, dict[str, int | float | None]]:
        current_24 = self._safe_metric(values, "rolling_24h", metric)
        current_48 = self._safe_metric(values, "rolling_48h", metric)
        previous = None
        if isinstance(current_24, (int, float)) and isinstance(current_48, (int, float)):
            previous = current_48 - current_24
        return {
            "24<-48": {
                "current": current_24,
                "previous": previous,
            }
        }

    def _trend_payload(
        self,
        values: dict[str, dict[str, list[int | float | None]]],
        metric: str,
    ) -> dict[str, dict[str, int | float | str | None]]:
        prev_case = self._cases_payload(values, metric).get("24<-48", {})
        c = prev_case.get("current")
        p = prev_case.get("previous")
        if not isinstance(c, (int, float)) or not isinstance(p, (int, float)):
            label = "stable"
        elif c > p:
            label = "up"
        elif c < p:
            label = "down"
        else:
            label = "stable"
        return {
            "24<-48": {
                "label": label,
                "delta": (c - p) if isinstance(c, (int, float)) and isinstance(p, (int, float)) else None,
            }
        }

    def _fetch_item_rows(self, spec: KPIDef, ctx: KPIQueryContext, session: Any) -> list[Any]:
        if spec.query_fn is None:
            return []
        cache = self._session_cache(session)
        key = (
            "item_rows",
            spec.name,
            ctx.user,
            self._ts_key(ctx.upper),
            tuple((k, self._cache_value(ctx.condition.get(k))) for k in spec.key_fields),
        )
        if key in cache:
            return cache[key]
        rows = spec.query_fn(ctx, session)
        cache[key] = rows
        return rows

    def _rows_in_window(
        self,
        rows: list[Any],
        timestamp_fn: KPITimestampFn,
        cutoff: datetime,
        upper: datetime,
    ) -> list[Any]:
        out: list[Any] = []
        for row in rows:
            ts = timestamp_fn(row)
            if ts is None:
                continue
            ts_utc = self._normalize_upper(ts)
            if cutoff <= ts_utc <= upper:
                out.append(row)
        return out

    def _build_windows(self, upper: datetime, custom_hours: int | None) -> dict[str, KPIWindow]:
        windows: dict[str, KPIWindow] = {
            "all_time": KPIWindow("all_time", datetime(1970, 1, 1, tzinfo=timezone.utc), upper),
            "rolling_24h": KPIWindow("rolling_24h", upper - timedelta(hours=24), upper),
            "rolling_48h": KPIWindow("rolling_48h", upper - timedelta(hours=48), upper),
            "rolling_7d": KPIWindow("rolling_7d", upper - timedelta(days=7), upper),
        }
        if custom_hours is not None and custom_hours > 0:
            windows["rolling_custom_h"] = KPIWindow("rolling_custom_h", upper - timedelta(hours=custom_hours), upper)
        return windows

    @staticmethod
    def _default_timestamp(row: Any) -> datetime | None:
        if isinstance(row, dict):
            raw = row.get("created_at")
            if isinstance(raw, datetime):
                return raw
            return None
        raw = getattr(row, "created_at", None)
        return raw if isinstance(raw, datetime) else None

    @staticmethod
    def _cache_value(value: Any) -> Any:
        if isinstance(value, list):
            return tuple(KPIRegistry._cache_value(v) for v in value)
        if isinstance(value, dict):
            return tuple(sorted((str(k), KPIRegistry._cache_value(v)) for k, v in value.items()))
        if isinstance(value, set):
            return tuple(sorted(KPIRegistry._cache_value(v) for v in value))
        return value

    def _session_cache(self, session: Any) -> dict[Any, Any]:
        if hasattr(session, "info") and isinstance(session.info, dict):
            return session.info.setdefault("_kpi_registry_cache", {})
        return self._local_cache

    @staticmethod
    def _normalize_upper(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _ts_key(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _safe_metric(
        values: dict[str, dict[str, list[int | float | None]]],
        window_id: str,
        metric: str,
    ) -> int | float | None:
        window_map = values.get(window_id)
        if not isinstance(window_map, dict):
            return None
        metric_values = window_map.get(metric)
        if not isinstance(metric_values, list) or not metric_values:
            return None
        value = metric_values[-1]
        return value if isinstance(value, (int, float)) else None



def _kpi_engine() -> KPIRegistry:
    from felvi_games.kpi_definitions import KPI_ENGINE

    return KPI_ENGINE


def _kpi_total_count(
    kpi_name: str,
    user: str,
    condition: dict,
    cutoff: datetime | None,
    upper: datetime | None,
    s: Session,
) -> int:
    param = _kpi_engine().kpi_parameter(
        kpi_name,
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_count or 0)

def _kpi_total_sum(
    kpi_name: str,
    user: str,
    condition: dict,
    cutoff: datetime | None,
    upper: datetime | None,
    s: Session,
) -> int:
    param = _kpi_engine().kpi_parameter(
        kpi_name,
        user=user,
        session=s,
        condition=condition,
        cutoff=cutoff,
        upper=upper,
        requested_stats={"total"},
    )
    return int(param.total_sum or 0)


def _attempt_rows(
    user: str,
    cutoff: datetime | None,
    upper: datetime | None,
    s: Session,
    *,
    condition: dict[str, Any] | None = None,
) -> list[Any]:
    return _kpi_engine().kpi_rows(
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
    return _kpi_engine().kpi_rows(
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


_FELADAT_TIPUSOK_COVER = frozenset({
    "nyilt_valasz", "tobbvalasztos", "parositas", "igaz_hamis", "fogalmazas", "kitoltes",
})


def _kpi_play_days(user: str, upper: datetime | None, s: Session) -> list[datetime]:
    """Sorted list of distinct play-day datetimes (UTC midnight) for the user."""
    return _play_days(_session_rows(user, None, upper, s))


def _kpi_max_correct_streak(user: str, upper: datetime | None, s: Session) -> int:
    """All-time best consecutive correct answer streak for the user."""
    return _max_streak(_helyes_sequence(_attempt_rows(user, None, upper, s)))


def _kpi_perfect_session_count(
    user: str,
    cutoff: datetime | None,
    upper: datetime | None,
    s: Session,
) -> int:
    """Number of perfect (all-correct) completed sessions within the window."""
    rows = [
        row for row in _session_rows(user, cutoff, upper, s)
        if getattr(row, "ended_at", None) is not None
    ]
    return _perfect_session_count(rows)

