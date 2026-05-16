"""Shared review-check query helpers for CLI and review-agent tools."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from felvi_games.db import FeladatRecord, MegoldasRecord


@dataclass(frozen=True)
class ReviewQuery:
    kind: str = "any"
    user: str | None = None
    contains: str = "hibás"
    targy: str | None = None
    szint: str | None = None
    min_hibas: int = 1
    limit: int = 20

    @property
    def normalized_limit(self) -> int:
        return max(0, int(self.limit))

    @property
    def normalized_min_hibas(self) -> int:
        return max(1, int(self.min_hibas))

    @property
    def keyword(self) -> str:
        return (self.contains or "").strip()


def collect_wrong_task_items(
    repo,
    query: ReviewQuery,
    *,
    include_wrong_answers: bool = False,
) -> list[dict[str, Any]]:
    """Return normalized wrong-task items from one or more sources.

    kind: wrong | flagged | keyword | any
    """
    rows: list[dict[str, Any]] = []

    if query.kind in {"wrong", "any"}:
        rows.extend(_collect_wrong_rows(repo, query, include_wrong_answers=include_wrong_answers))
    if query.kind in {"flagged", "any"}:
        rows.extend(_collect_flagged_rows(repo, query))
    if query.kind in {"keyword", "any"} and query.keyword:
        rows.extend(_collect_keyword_rows(repo, query))
    return _merge_wrong_task_items(rows, query.normalized_limit, include_wrong_answers)


def collect_wrong_issue_report(
    repo,
    query: ReviewQuery,
) -> dict[str, Any]:
    """Return flagged+keyword grouped issue report and keyword attempt total."""
    keyword = query.keyword
    if not keyword:
        return {
            "keyword": "",
            "flagged": [],
            "keyword_rows": [],
            "keyword_attempts_total": 0,
        }

    flagged = collect_wrong_task_items(
        repo,
        ReviewQuery(
            kind="flagged",
            user=query.user,
            contains=keyword,
            targy=query.targy,
            szint=query.szint,
            limit=query.limit,
        ),
    )
    keyword_rows = collect_wrong_task_items(
        repo,
        ReviewQuery(
            kind="keyword",
            user=query.user,
            contains=keyword,
            targy=query.targy,
            szint=query.szint,
            limit=query.limit,
        ),
    )

    with Session(repo._engine) as s:
        total_stmt = select(func.count(MegoldasRecord.id)).where(
            func.lower(MegoldasRecord.adott_valasz).contains(keyword.lower())
        )
        if query.user:
            total_stmt = total_stmt.where(MegoldasRecord.felhasznalo_nev == query.user)
        if query.targy or query.szint:
            total_stmt = total_stmt.join(FeladatRecord, FeladatRecord.id == MegoldasRecord.feladat_id)
            if query.targy:
                total_stmt = total_stmt.where(FeladatRecord.targy == query.targy)
            if query.szint:
                total_stmt = total_stmt.where(FeladatRecord.szint == query.szint)
        keyword_attempts_total = int(s.execute(total_stmt).scalar() or 0)

    return {
        "keyword": keyword,
        "flagged": flagged,
        "keyword_rows": keyword_rows,
        "keyword_attempts_total": keyword_attempts_total,
    }


def collect_review_check_candidates(
    repo,
    query: ReviewQuery,
) -> list[tuple[str, str]]:
    """Return unique (feladat_id, first_origin) pairs for review-check selection."""
    items = collect_wrong_task_items(
        repo,
        query,
        include_wrong_answers=False,
    )
    result: list[tuple[str, str]] = []
    for item in items:
        origins = list(item.get("sources") or [])
        origin = origins[0] if origins else query.kind
        result.append((str(item.get("feladat_id", "")), origin))
    return [(fid, origin) for fid, origin in result if fid]


def render_wrong_task_report(
    rows: list[dict[str, Any]],
    *,
    db_path: Path,
    user: str | None,
    detail: bool,
) -> str:
    scope = f"  (user={user})" if user else ""
    lines = [f"\n=== Hibásan megoldott feladatok  (DB: {db_path}){scope} ===\n"]
    if not rows:
        lines.append("  Nincs találat (még senki sem rontott el egy feladatot sem ebben a körben).")
        lines.append("")
        return "\n".join(lines)

    for row in rows:
        metrics = row.get("metrics", {})
        hibas_db = int(metrics.get("hibas_db", 0))
        osszes_db = int(metrics.get("osszes_db", 0))
        rontas_pct = (100.0 * hibas_db / osszes_db) if osszes_db else 0.0
        kerdes = str(row.get("kerdes") or "")
        helyes = str(row.get("helyes_valasz") or "")
        kerdes_short = (kerdes[:90] + "…") if len(kerdes) > 90 else kerdes
        helyes_short = (helyes[:50] + "…") if len(helyes) > 50 else helyes
        ev_label = str(row.get("ev") or "?")
        lines.append(
            f"  [{row.get('targy')}/{row.get('szint')}/{ev_label}] {row.get('feladat_tipus') or '-'}  "
            f"hibás: {hibas_db}/{osszes_db}  ({rontas_pct:.0f}% rontás)"
        )
        lines.append(f"    Kérdés:        {kerdes_short}")
        lines.append(f"    Helyes válasz: {helyes_short}")
        lines.append(f"    ID:            {row.get('feladat_id')}")
        hibas_valaszok = list(metrics.get("hibas_valaszok") or [])
        if detail and hibas_valaszok:
            lines.append(f"    Hibás válaszok: {_format_wrong_answers(hibas_valaszok)}")
        lines.append("")

    lines.append(f"  Összesen: {len(rows)} feladat listázva.\n")
    return "\n".join(lines)


def render_wrong_issue_report(
    report: dict[str, Any],
    *,
    db_path: Path,
    user: str | None,
) -> str:
    flagged_rows = list(report.get("flagged") or [])
    contains_rows = list(report.get("keyword_rows") or [])
    contains_attempts_total = int(report.get("keyword_attempts_total") or 0)
    keyword = str(report.get("keyword") or "")

    scope = f"  (user={user})" if user else ""
    lines = [f"\n=== Vitás feladatok  (DB: {db_path}){scope} ===\n"]
    lines.append("[1] Felhasználó által hibásnak jelölve (hibajelzés):")
    lines.extend(_render_issue_rows(flagged_rows, metric_key="jeloles_db", label="jelölések"))
    lines.append("")
    lines.append(f"[2] Válaszban szerepel: \"{keyword}\"")
    lines.append(f"  - Összes érintett próbálkozás: {contains_attempts_total}")
    lines.append(f"  - Érintett feladatok száma: {len(contains_rows)}")
    lines.extend(_render_issue_rows(contains_rows, metric_key="talalat_db", label="előfordulás"))
    lines.append("")
    return "\n".join(lines)


def write_flagged_ids(report: dict[str, Any], ids_dat: Path) -> int:
    flagged_rows = list(report.get("flagged") or [])
    ids_dat.parent.mkdir(parents=True, exist_ok=True)
    ids_dat.write_text(
        "\n".join(str(row.get("feladat_id", "")) for row in flagged_rows if row.get("feladat_id"))
        + ("\n" if flagged_rows else ""),
        encoding="utf-8",
    )
    return len(flagged_rows)


def _collect_wrong_rows(repo, query: ReviewQuery, *, include_wrong_answers: bool) -> list[dict[str, Any]]:
    wrong_rows = repo.get_wrong_feladatok(
        felhasznalo_nev=query.user,
        targy=query.targy,
        szint=query.szint,
        min_hibas=query.normalized_min_hibas,
        limit=query.normalized_limit,
        include_wrong_answers=include_wrong_answers,
    )
    return [
        {
            "source": "wrong",
            "feladat_id": row.feladat_id,
            "targy": row.targy,
            "szint": row.szint,
            "ev": row.ev,
            "feladat_tipus": row.feladat_tipus,
            "kerdes": row.kerdes,
            "helyes_valasz": row.helyes_valasz,
            "hibas_db": row.hibas_db,
            "osszes_db": row.osszes_db,
            "rontas_pct": row.rontas_pct,
            "hibas_valaszok": row.hibas_valaszok if include_wrong_answers else [],
        }
        for row in wrong_rows
    ]


def _collect_flagged_rows(repo, query: ReviewQuery) -> list[dict[str, Any]]:
    with Session(repo._engine) as session:
        stmt = (
            select(
                MegoldasRecord.feladat_id,
                FeladatRecord.targy,
                FeladatRecord.szint,
                FeladatRecord.ev,
                func.count(MegoldasRecord.id).label("db"),
            )
            .join(FeladatRecord, FeladatRecord.id == MegoldasRecord.feladat_id)
            .where(MegoldasRecord.hibajelezes.is_(True))
            .group_by(
                MegoldasRecord.feladat_id,
                FeladatRecord.targy,
                FeladatRecord.szint,
                FeladatRecord.ev,
            )
            .order_by(func.count(MegoldasRecord.id).desc(), MegoldasRecord.feladat_id.asc())
        )
        stmt = _apply_query_filters(stmt, query)
        rows = session.execute(stmt).all()
    return [
        {
            "source": "flagged",
            "feladat_id": row.feladat_id,
            "targy": row.targy,
            "szint": row.szint,
            "ev": row.ev,
            "jeloles_db": int(row.db),
        }
        for row in rows
    ]


def _collect_keyword_rows(repo, query: ReviewQuery) -> list[dict[str, Any]]:
    with Session(repo._engine) as session:
        stmt = (
            select(
                MegoldasRecord.feladat_id,
                FeladatRecord.targy,
                FeladatRecord.szint,
                FeladatRecord.ev,
                func.count(MegoldasRecord.id).label("db"),
            )
            .join(FeladatRecord, FeladatRecord.id == MegoldasRecord.feladat_id)
            .where(func.lower(MegoldasRecord.adott_valasz).contains(query.keyword.lower()))
            .group_by(
                MegoldasRecord.feladat_id,
                FeladatRecord.targy,
                FeladatRecord.szint,
                FeladatRecord.ev,
            )
            .order_by(func.count(MegoldasRecord.id).desc(), MegoldasRecord.feladat_id.asc())
        )
        stmt = _apply_query_filters(stmt, query)
        rows = session.execute(stmt).all()
    return [
        {
            "source": "keyword",
            "feladat_id": row.feladat_id,
            "targy": row.targy,
            "szint": row.szint,
            "ev": row.ev,
            "talalat_db": int(row.db),
            "contains": query.keyword,
        }
        for row in rows
    ]


def _apply_query_filters(stmt, query: ReviewQuery):
    if query.user:
        stmt = stmt.where(MegoldasRecord.felhasznalo_nev == query.user)
    if query.targy:
        stmt = stmt.where(FeladatRecord.targy == query.targy)
    if query.szint:
        stmt = stmt.where(FeladatRecord.szint == query.szint)
    if query.normalized_limit > 0:
        stmt = stmt.limit(query.normalized_limit)
    return stmt


def _merge_wrong_task_items(
    rows: list[dict[str, Any]],
    limit: int,
    include_wrong_answers: bool,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in rows:
        fid = str(item.get("feladat_id", "")).strip()
        if not fid:
            continue
        bucket = merged.setdefault(
            fid,
            {
                "feladat_id": fid,
                "targy": item.get("targy"),
                "szint": item.get("szint"),
                "ev": item.get("ev"),
                "feladat_tipus": item.get("feladat_tipus"),
                "kerdes": item.get("kerdes"),
                "helyes_valasz": item.get("helyes_valasz"),
                "sources": [],
                "metrics": {},
            },
        )
        _merge_metric_item(bucket, item, include_wrong_answers)

    merged_items = list(merged.values())
    merged_items.sort(key=_wrong_item_sort_key, reverse=True)
    if limit > 0:
        return merged_items[:limit]
    return merged_items


def _merge_metric_item(bucket: dict[str, Any], item: dict[str, Any], include_wrong_answers: bool) -> None:
    source = str(item.get("source", ""))
    if source and source not in bucket["sources"]:
        bucket["sources"].append(source)
    for key in ("hibas_db", "osszes_db", "jeloles_db", "talalat_db"):
        if key in item:
            bucket["metrics"][key] = item[key]
    if include_wrong_answers and item.get("hibas_valaszok"):
        bucket["metrics"]["hibas_valaszok"] = item["hibas_valaszok"]


def _wrong_item_sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
    metrics = row.get("metrics", {})
    return (
        int(metrics.get("hibas_db", 0)),
        int(metrics.get("jeloles_db", 0)),
        int(metrics.get("talalat_db", 0)),
    )


def _format_wrong_answers(values: list[str]) -> str:
    counts = Counter(values)
    return ", ".join(f'"{value}"×{count}' if count > 1 else f'"{value}"' for value, count in counts.most_common())


def _render_issue_rows(rows: list[dict[str, Any]], *, metric_key: str, label: str) -> list[str]:
    if not rows:
        return ["  - Nincs találat."]
    rendered: list[str] = []
    for row in rows:
        ev_label = str(row.get("ev") or "?")
        metric_value = int((row.get("metrics", {}) or {}).get(metric_key, 0))
        rendered.append(
            f"  - {row.get('feladat_id')}  [{row.get('targy')}/{row.get('szint')}/{ev_label}]  {label}: {metric_value}"
        )
    return rendered
