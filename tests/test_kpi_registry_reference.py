from __future__ import annotations

from datetime import datetime, timedelta, timezone

from felvi_games.kpi_registry import KPIQueryContext, KPIRegistry


class DummySession:
    def __init__(self) -> None:
        self.info: dict = {}


def _ts(hours_ago: int, *, upper: datetime) -> datetime:
    return upper - timedelta(hours=hours_ago)


def test_kpi_registry_item_and_value_share_base_query_cache() -> None:
    upper = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"created_at": _ts(2, upper=upper), "points": 5},
        {"created_at": _ts(8, upper=upper), "points": 3},
        {"created_at": _ts(30, upper=upper), "points": 2},
    ]

    calls = {"query": 0}

    def query_fn(ctx: KPIQueryContext, session: DummySession):
        calls["query"] += 1
        return rows

    registry = KPIRegistry()
    registry.register(
        name="kpi_name",
        type="item",
        query_fn=query_fn,
        description="Reference item KPI",
        metric_name="count",
    )
    registry.register(
        name="kpi_name_point",
        type="value",
        base="kpi_name",
        property_fn=lambda row, ctx: float(row.get("points", 0)),
        description="Points over base rows",
        metric_name="sum",
    )

    session = DummySession()

    kpi_name = registry.kpi_parameter("kpi_name", user="Lori", session=session, upper=upper)
    kpi_name_point = registry.kpi_parameter("kpi_name_point", user="Lori", session=session, upper=upper)

    # Lazy behavior: object creation should not trigger any query.
    assert calls["query"] == 0

    assert kpi_name.total_count == 3
    assert kpi_name.count_24h[-1] == 2

    assert kpi_name_point.total_sum == 10.0
    assert kpi_name_point.sum_24h[-1] == 8.0

    assert calls["query"] == 1


def test_kpi_registry_cases_derive_previous_bucket_from_24h_and_48h() -> None:
    upper = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"created_at": _ts(1, upper=upper), "points": 1},
        {"created_at": _ts(6, upper=upper), "points": 1},
        {"created_at": _ts(26, upper=upper), "points": 1},
        {"created_at": _ts(40, upper=upper), "points": 1},
    ]

    registry = KPIRegistry()
    registry.register(
        name="kpi_name",
        type="item",
        query_fn=lambda ctx, s: rows,
        metric_name="count",
    )

    param = registry.kpi_parameter("kpi_name", user="Lori", session=DummySession(), upper=upper)
    payload = param.to_dict()

    cases = payload.get("cases")
    assert isinstance(cases, dict)
    prev_case = cases.get("24<-48")
    assert isinstance(prev_case, dict)

    assert prev_case.get("current") == 2
    assert prev_case.get("previous") == 2


def test_kpi_registry_missing_kpi_fails_soft() -> None:
    registry = KPIRegistry()
    param = registry.kpi_parameter("does_not_exist", user="Lori", session=DummySession())
    payload = param.to_dict()

    assert payload.get("missing") is True
    assert payload.get("name") == "does_not_exist"
