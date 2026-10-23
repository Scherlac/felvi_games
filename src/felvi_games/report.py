"""report.py
-----------
Heti (és tetszőleges időtartamú) használati riport.

Kimenet: egy mappa, benne:
  report.md               – Markdown összefoglaló táblákkal és írásfeladat-eredményekkel
  overall_summary.png     – Kísérletek / pontosság / pontszám / játékidő összefoglaló
  accuracy_targy.png      – Pontosság tárgyak szerint (csoportos oszlopdiagram)
  daily_activity.png      – Napi aktivitás (vonaldiagram felhasználónként)
    attempt_time_points.png – Szerzett pont vs. próbálkozási idő (user × tárgy × max pont)
    session_average_points.png – Menet-átlag: szerzett pont vs. próbálkozási idő (user × tárgy × átlag max pont)
        session_average_delta_points.png – Menet-átlag eltérés a célhoz képest
  szint_distribution.png  – Kísérletek szint szerint (halmozott oszlopdiagram)

Usage:
  from felvi_games.report import run
  out_dir = run(db_path, days=7)
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


class AccuracyPctMixin:
    """Shared percentage helper for rows with attempts/correct counters."""

    attempts: int
    correct: int

    @property
    def accuracy_pct(self) -> float:
        return (self.correct / self.attempts * 100) if self.attempts > 0 else 0.0

@dataclass
class UserSummary(AccuracyPctMixin):
    nev: str
    sessions: int = 0
    play_time_min: float = 0.0
    attempt_time_min: float = 0.0
    attempts: int = 0
    correct: int = 0
    partial: int = 0
    points: int = 0
    new_achievements: int = 0


@dataclass
class UserTargySzintRow(AccuracyPctMixin):
    nev: str
    targy: str
    szint: str
    attempts: int = 0
    correct: int = 0
    partial: int = 0
    points: int = 0


@dataclass
class AchievementRow:
    nev: str
    erem_id: str
    erem_nev: str
    ikon: str
    szerzett_at: datetime


@dataclass
class DailyActivity:
    datum: str   # YYYY-MM-DD
    nev: str
    attempts: int


@dataclass
class DailyDetail(AccuracyPctMixin):
    """Per-day, per-user, per-tárgy breakdown for points and accuracy charts."""
    datum: str   # YYYY-MM-DD
    nev: str
    targy: str
    attempts: int = 0
    correct: int = 0
    partial: int = 0
    points: int = 0
    max_points: int = 0
    elapsed_sec: float = 0.0


@dataclass
class AttemptTimingPoint:
    nev: str
    targy: str
    max_pont: int
    gained_pont: int
    elapsed_sec: float
    correct: bool = False
    partial: bool = False


@dataclass
class SessionAveragePoint:
    nev: str
    targy: str
    menet_id: int
    session_date: str
    committed_count: int
    avg_gained_pont: float
    avg_elapsed_sec: float
    avg_max_pont: float


@dataclass
class WritingTaskResult:
    nev: str
    task_id: str
    title: str
    source_kind: str
    exam_year: int | None
    variant: int | None
    task_number: str | None
    status: str
    started_at: datetime
    submitted_at: datetime | None
    active_seconds: int
    total_score: int | None = None
    max_score: int | None = None
    learner_sentence_count: int | None = None


@dataclass(frozen=True)
class PerformanceMetrics:
    achievable_points: float
    earned_points: float
    time_sec: float
    earned_pct: float
    time_per_earned_point: float
    average_achievable_points: float


def _calculate_performance_metrics(
    achievable_points: float,
    earned_points: float,
    time_sec: float,
    count: int,
) -> PerformanceMetrics:
    safe_count = max(count, 1)
    return PerformanceMetrics(
        achievable_points=achievable_points,
        earned_points=earned_points,
        time_sec=time_sec,
        earned_pct=(earned_points / achievable_points * 100) if achievable_points > 0 else 0.0,
        time_per_earned_point=(time_sec / earned_points) if earned_points > 0 else 0.0,
        average_achievable_points=achievable_points / safe_count,
    )


@dataclass
class SessionAverageAccumulator:
    nev: str
    targy: str
    committed_count: int = 0
    gained_pont_sum: float = 0.0
    elapsed_sec_sum: float = 0.0
    max_pont_sum: float = 0.0


@dataclass
class ReportData:
    date_from: datetime
    date_to: datetime
    days: int
    users: list[UserSummary] = field(default_factory=list)
    targy_szint: list[UserTargySzintRow] = field(default_factory=list)
    achievements: list[AchievementRow] = field(default_factory=list)
    daily: list[DailyActivity] = field(default_factory=list)
    daily_detail: list[DailyDetail] = field(default_factory=list)
    attempt_timing: list[AttemptTimingPoint] = field(default_factory=list)
    session_average_points: list[SessionAveragePoint] = field(default_factory=list)
    writing: list[WritingTaskResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def gather_data(engine, days: int, user_filter: str | None = None) -> ReportData:
    from collections import defaultdict

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from felvi_games.db import (
        EremRecord,
        FeladatRecord,
        FelhasznaloRecord,
        FelhasznaloEremRecord,
        MegoldasRecord,
        MenetRecord,
        WritingDraftRevisionRecord,
        WritingPracticeSessionRecord,
    )
    from felvi_games.usage_metrics import classify_attempt

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=days)
    data = ReportData(date_from=date_from, date_to=date_to, days=days)

    with Session(engine) as s:
        # sessions in window
        q_sessions = (
            select(
                MenetRecord.id.label("menet_id"),
                func.coalesce(FelhasznaloRecord.nev, MenetRecord.felhasznalo_nev).label("felhasznalo_nev"),
                MenetRecord.targy,
                MenetRecord.szint,
                MenetRecord.megoldott,
                MenetRecord.pont,
                MenetRecord.started_at,
                MenetRecord.ended_at,
            )
            .outerjoin(FelhasznaloRecord, MenetRecord.felhasznalo_id == FelhasznaloRecord.id)
            .where(MenetRecord.started_at >= date_from)
        )
        if user_filter:
            q_sessions = q_sessions.where(
                func.coalesce(FelhasznaloRecord.nev, MenetRecord.felhasznalo_nev) == user_filter
            )
        sessions = s.execute(q_sessions).all()

        # Answers in window. Subject/level come from session when present,
        # otherwise from the task row so orphan attempts are still counted.
        q_answers = (
            select(
                func.coalesce(FelhasznaloRecord.nev, MegoldasRecord.felhasznalo_nev).label("felhasznalo_nev"),
                MegoldasRecord.menet_id,
                MenetRecord.targy,
                MenetRecord.szint,
                FeladatRecord.targy.label("feladat_targy"),
                FeladatRecord.szint.label("feladat_szint"),
                FeladatRecord.max_pont,
                MegoldasRecord.helyes,
                MegoldasRecord.pont,
                MegoldasRecord.elapsed_sec,
                MegoldasRecord.created_at,
            )
            .outerjoin(FelhasznaloRecord, MegoldasRecord.felhasznalo_id == FelhasznaloRecord.id)
            .outerjoin(MenetRecord, MenetRecord.id == MegoldasRecord.menet_id)
            .outerjoin(FeladatRecord, FeladatRecord.id == MegoldasRecord.feladat_id)
            .where(MegoldasRecord.created_at >= date_from)
        )
        if user_filter:
            q_answers = q_answers.where(
                func.coalesce(FelhasznaloRecord.nev, MegoldasRecord.felhasznalo_nev) == user_filter
            )
        answers = s.execute(q_answers).all()

        # Writing-practice sessions use a separate persistence model. Keep the
        # latest reviewed revision per session so the report reflects the
        # submitted task result rather than an earlier draft.
        q_writing_sessions = (
            select(
                WritingPracticeSessionRecord.id,
                WritingPracticeSessionRecord.felhasznalo_nev,
                WritingPracticeSessionRecord.feladat_id,
                WritingPracticeSessionRecord.task_metadata_json,
                WritingPracticeSessionRecord.status,
                WritingPracticeSessionRecord.utc_started_at,
                WritingPracticeSessionRecord.utc_submitted_at,
                WritingPracticeSessionRecord.active_seconds,
            )
            .where(WritingPracticeSessionRecord.utc_started_at >= date_from)
        )
        if user_filter:
            q_writing_sessions = q_writing_sessions.where(
                WritingPracticeSessionRecord.felhasznalo_nev == user_filter
            )
        writing_sessions = s.execute(q_writing_sessions).all()
        writing_reviews: dict[int, str] = {}
        if writing_sessions:
            writing_session_ids = [row.id for row in writing_sessions]
            q_writing_revisions = (
                select(
                    WritingDraftRevisionRecord.session_id,
                    WritingDraftRevisionRecord.revision_no,
                    WritingDraftRevisionRecord.feedback_json,
                )
                .where(WritingDraftRevisionRecord.session_id.in_(writing_session_ids))
                .where(WritingDraftRevisionRecord.feedback_json.is_not(None))
                .order_by(
                    WritingDraftRevisionRecord.session_id,
                    WritingDraftRevisionRecord.revision_no,
                )
            )
            for revision in s.execute(q_writing_revisions).all():
                if revision.feedback_json is not None:
                    writing_reviews[revision.session_id] = revision.feedback_json

        # achievements earned in window
        q_ach = (
            select(
                func.coalesce(FelhasznaloRecord.nev, FelhasznaloEremRecord.felhasznalo_nev).label("felhasznalo_nev"),
                FelhasznaloEremRecord.erem_id,
                FelhasznaloEremRecord.szerzett_at,
                EremRecord.nev,
                EremRecord.ikon,
            )
            .join(EremRecord, EremRecord.id == FelhasznaloEremRecord.erem_id)
            .outerjoin(FelhasznaloRecord, FelhasznaloRecord.id == FelhasznaloEremRecord.felhasznalo_id)
            .where(FelhasznaloEremRecord.szerzett_at >= date_from)
        )
        if user_filter:
            q_ach = q_ach.where(
                func.coalesce(FelhasznaloRecord.nev, FelhasznaloEremRecord.felhasznalo_nev) == user_filter
            )
        achievements = s.execute(q_ach).all()

    # --- aggregate ---
    user_data: dict[str, UserSummary] = {}
    targy_szint_data: dict[tuple, UserTargySzintRow] = {}
    session_last_attempt: dict[int, datetime] = {}
    session_dates: dict[int, str] = {}
    session_average_acc: dict[int, SessionAverageAccumulator] = {}

    for row in writing_sessions:
        user_data.setdefault(row.felhasznalo_nev, UserSummary(nev=row.felhasznalo_nev))

    for row in sessions:
        u = row.felhasznalo_nev
        if u not in user_data:
            user_data[u] = UserSummary(nev=u)
        user_data[u].sessions += 1
        if row.menet_id is not None and row.started_at is not None:
            session_dates[int(row.menet_id)] = row.started_at.strftime("%Y-%m-%d")

    daily_dict: dict[tuple[str, str], int] = defaultdict(int)
    daily_detail_dict: dict[tuple[str, str, str], dict] = defaultdict(dict)
    for row in answers:
        u = row.felhasznalo_nev
        if u not in user_data:
            user_data[u] = UserSummary(nev=u)
        outcome = classify_attempt(helyes=bool(row.helyes), pont=row.pont)
        user_data[u].attempts += 1
        elapsed_sec = getattr(row, "elapsed_sec", None)
        if isinstance(elapsed_sec, (int, float)) and elapsed_sec > 0:
            user_data[u].attempt_time_min += float(elapsed_sec) / 60
        menet_id = getattr(row, "menet_id", None)
        if isinstance(menet_id, int) and row.created_at is not None:
            prev = session_last_attempt.get(menet_id)
            if prev is None or row.created_at > prev:
                session_last_attempt[menet_id] = row.created_at
        if outcome.full_correct:
            user_data[u].correct += 1
        elif outcome.partial_correct:
            user_data[u].partial += 1
        user_data[u].points += outcome.points

        # Attempt-level subject/level should come from the attempted task itself.
        # Session metadata can be broader/mixed and would skew per-subject charts.
        targy = row.feladat_targy or row.targy or "ismeretlen"
        szint = row.feladat_szint or row.szint or "ismeretlen"
        if isinstance(elapsed_sec, (int, float)) and elapsed_sec > 0:
            data.attempt_timing.append(
                AttemptTimingPoint(
                    nev=u,
                    targy=targy,
                    max_pont=int(row.max_pont or 0),
                    gained_pont=outcome.points,
                    elapsed_sec=float(elapsed_sec),
                    correct=outcome.full_correct,
                    partial=outcome.partial_correct,
                )
            )
        if isinstance(menet_id, int):
            acc = session_average_acc.setdefault(
                menet_id,
                SessionAverageAccumulator(
                    nev=u,
                    targy=targy,
                ),
            )
            acc.committed_count += 1
            acc.gained_pont_sum += float(outcome.points)
            acc.max_pont_sum += float(int(row.max_pont or 0))
            if isinstance(elapsed_sec, (int, float)) and elapsed_sec > 0:
                acc.elapsed_sec_sum += float(elapsed_sec)

        key = (u, targy, szint)
        if key not in targy_szint_data:
            targy_szint_data[key] = UserTargySzintRow(nev=u, targy=targy, szint=szint)
        targy_szint_data[key].attempts += 1
        if outcome.full_correct:
            targy_szint_data[key].correct += 1
        elif outcome.partial_correct:
            targy_szint_data[key].partial += 1
        targy_szint_data[key].points += outcome.points

        datum = row.created_at.strftime("%Y-%m-%d")
        daily_dict[(datum, u)] += 1

        # per-day × user × tárgy breakdown
        daily_detail_dict[(datum, u, targy)].setdefault("attempts", 0)
        daily_detail_dict[(datum, u, targy)]["attempts"] += 1
        daily_detail_dict[(datum, u, targy)].setdefault("correct", 0)
        if outcome.full_correct:
            daily_detail_dict[(datum, u, targy)]["correct"] += 1
        daily_detail_dict[(datum, u, targy)].setdefault("partial", 0)
        if outcome.partial_correct:
            daily_detail_dict[(datum, u, targy)]["partial"] += 1
        daily_detail_dict[(datum, u, targy)].setdefault("points", 0)
        daily_detail_dict[(datum, u, targy)]["points"] += outcome.points
        daily_detail_dict[(datum, u, targy)].setdefault("max_points", 0)
        daily_detail_dict[(datum, u, targy)]["max_points"] += int(row.max_pont or 0)
        daily_detail_dict[(datum, u, targy)].setdefault("elapsed_sec", 0.0)
        if isinstance(elapsed_sec, (int, float)) and elapsed_sec > 0:
            daily_detail_dict[(datum, u, targy)]["elapsed_sec"] += float(elapsed_sec)

    for row in achievements:
        user_data.setdefault(row.felhasznalo_nev, UserSummary(nev=row.felhasznalo_nev))
        user_data[row.felhasznalo_nev].new_achievements += 1
        data.achievements.append(AchievementRow(
            nev=row.felhasznalo_nev,
            erem_id=row.erem_id,
            erem_nev=row.nev,
            ikon=row.ikon,
            szerzett_at=row.szerzett_at,
        ))

    for row in writing_sessions:
        metadata: dict[str, object] = {}
        try:
            parsed_metadata = json.loads(row.task_metadata_json)
        except json.JSONDecodeError:
            logger.warning(
                "report: invalid writing task metadata for session %s",
                row.id,
            )
        else:
            if isinstance(parsed_metadata, dict):
                metadata = parsed_metadata
            else:
                logger.warning(
                    "report: writing task metadata is not an object for session %s",
                    row.id,
                )

        title_value = metadata.get("title")
        title = (
            title_value.strip()
            if isinstance(title_value, str) and title_value.strip()
            else row.feladat_id
        )
        source_kind_value = metadata.get("source_kind")
        source_kind = source_kind_value if isinstance(source_kind_value, str) else "unknown"
        exam_year_value = metadata.get("exam_year")
        exam_year = (
            exam_year_value
            if isinstance(exam_year_value, int) and not isinstance(exam_year_value, bool)
            else None
        )
        variant_value = metadata.get("variant")
        variant = (
            variant_value
            if isinstance(variant_value, int) and not isinstance(variant_value, bool)
            else None
        )
        task_number_value = metadata.get("task_number")
        task_number = task_number_value if isinstance(task_number_value, str) else None

        total_score: int | None = None
        max_score: int | None = None
        learner_sentence_count: int | None = None
        feedback_json = writing_reviews.get(row.id)
        if feedback_json is not None:
            try:
                parsed_feedback = json.loads(feedback_json)
            except json.JSONDecodeError:
                logger.warning(
                    "report: invalid writing review for session %s",
                    row.id,
                )
            else:
                if isinstance(parsed_feedback, dict):
                    total_value = parsed_feedback.get("total_score")
                    max_value = parsed_feedback.get("assessable_max_score")
                    sentence_value = parsed_feedback.get("learner_sentence_count")
                    if isinstance(total_value, int) and not isinstance(total_value, bool):
                        total_score = total_value
                    if isinstance(max_value, int) and not isinstance(max_value, bool):
                        max_score = max_value
                    if isinstance(sentence_value, int) and not isinstance(sentence_value, bool):
                        learner_sentence_count = sentence_value
                else:
                    logger.warning(
                        "report: writing review is not an object for session %s",
                        row.id,
                    )

        data.writing.append(
            WritingTaskResult(
                nev=row.felhasznalo_nev,
                task_id=row.feladat_id,
                title=title,
                source_kind=source_kind,
                exam_year=exam_year,
                variant=variant,
                task_number=task_number,
                status=row.status,
                started_at=row.utc_started_at,
                submitted_at=row.utc_submitted_at,
                active_seconds=max(0, int(row.active_seconds)),
                total_score=total_score,
                max_score=max_score,
                learner_sentence_count=learner_sentence_count,
            )
        )

    for row in sessions:
        summary = user_data[row.felhasznalo_nev]
        delta_min = 0.0
        if row.ended_at and row.started_at:
            delta_min = (row.ended_at - row.started_at).total_seconds() / 60
        else:
            last_attempt_at = session_last_attempt.get(int(row.menet_id)) if row.menet_id is not None else None
            if last_attempt_at and row.started_at:
                delta_min = (last_attempt_at - row.started_at).total_seconds() / 60
        if 0 < delta_min < 300:
            summary.play_time_min += delta_min

    for summary in user_data.values():
        if summary.play_time_min <= 0 and summary.attempt_time_min > 0:
            summary.play_time_min = summary.attempt_time_min

    for menet_id, acc in sorted(session_average_acc.items()):
        committed_count = acc.committed_count
        if committed_count <= 0:
            continue
        data.session_average_points.append(
            SessionAveragePoint(
                nev=acc.nev,
                targy=acc.targy,
                menet_id=menet_id,
                session_date=session_dates.get(menet_id, "ismeretlen dátum"),
                committed_count=committed_count,
                avg_gained_pont=acc.gained_pont_sum / committed_count,
                avg_elapsed_sec=acc.elapsed_sec_sum / committed_count,
                avg_max_pont=acc.max_pont_sum / committed_count,
            )
        )

    for (datum, nev), cnt in sorted(daily_dict.items()):
        data.daily.append(DailyActivity(datum=datum, nev=nev, attempts=cnt))

    for (datum, nev, targy), vals in sorted(daily_detail_dict.items()):
        data.daily_detail.append(DailyDetail(
            datum=datum, nev=nev, targy=targy,
            attempts=vals.get("attempts", 0),
            correct=vals.get("correct", 0),
            partial=vals.get("partial", 0),
            points=vals.get("points", 0),
            max_points=vals.get("max_points", 0),
            elapsed_sec=vals.get("elapsed_sec", 0.0),
        ))

    data.users = sorted(user_data.values(), key=lambda u: u.nev)
    data.targy_szint = sorted(targy_szint_data.values(), key=lambda r: (r.nev, r.targy, r.szint))
    return data


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

_USER_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B2", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
]

_TARGY_COLORS = {"matek": "#4C72B0", "magyar": "#DD8452"}
_SZINT_COLORS = {
    "4 osztályos": "#4C72B0",
    "6 osztályos": "#55A868",
    "8 osztályos": "#DD8452",
}


def _user_colors(user_names: list[str]) -> dict[str, str]:
    return {u: _USER_PALETTE[i % len(_USER_PALETTE)] for i, u in enumerate(user_names)}


def _daily_performance_rows(
    data: ReportData,
) -> list[tuple[str, str, str, int, PerformanceMetrics]]:
    return [
        (
            row.nev,
            f"{row.datum} / {row.targy}",
            row.targy,
            row.attempts,
            _calculate_performance_metrics(
                row.max_points,
                row.points,
                row.elapsed_sec,
                row.attempts,
            ),
        )
        for row in data.daily_detail
    ]


def _session_performance_rows(
    data: ReportData,
) -> list[tuple[str, str, str, int, PerformanceMetrics, SessionAveragePoint]]:
    rows = []
    for row in data.session_average_points:
        metrics = _calculate_performance_metrics(
            row.avg_max_pont * row.committed_count,
            row.avg_gained_pont * row.committed_count,
            row.avg_elapsed_sec * row.committed_count,
            row.committed_count,
        )
        rows.append((
            row.nev,
            f"{row.session_date} / {row.menet_id}",
            row.targy,
            row.committed_count,
            metrics,
            row,
        ))
    return rows


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _build_date_range(data: ReportData) -> list[str]:
    start = data.date_from.replace(hour=0, minute=0, second=0, microsecond=0)
    end = data.date_to.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range((end - start).days + 1)
    ]


def _build_daily_detail_context(
    data: ReportData, user_names: list[str]
) -> tuple[list[tuple[str, str]], dict[str, str], dict[str, str], dict]:
    ut_pairs = sorted({(r.nev, r.targy) for r in data.daily_detail if r.nev in user_names})
    _LINESTYLES = ["-", "--", "-.", ":"]
    _MARKERS = ["o", "s", "^", "D", "P", "X"]
    targy_list = sorted({t for _, t in ut_pairs})
    ls_map = {t: _LINESTYLES[i % len(_LINESTYLES)] for i, t in enumerate(targy_list)}
    marker_map = {t: _MARKERS[i % len(_MARKERS)] for i, t in enumerate(targy_list)}
    detail_idx = {(r.datum, r.nev, r.targy): r for r in data.daily_detail}
    return ut_pairs, ls_map, marker_map, detail_idx


def _chart_overall_summary(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str, user_names: list[str]
) -> str:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from matplotlib.patches import Patch

    metrics = [
        ("Kísérletek", [u.attempts for u in data.users]),
        ("Pontosság (%)", [round(u.accuracy_pct, 1) for u in data.users]),
        ("Pontszám", [u.points for u in data.users]),
        ("Játékidő (perc)", [round(u.play_time_min, 1) for u in data.users]),
    ]
    colors = [cmap[u] for u in user_names]

    fig, axes = plt.subplots(1, 4, figsize=(16, 5))
    fig.suptitle(f"Összefoglaló áttekintés  |  {subtitle}", fontsize=13, fontweight="bold")

    for ax, (title, values) in zip(axes, metrics, strict=False):
        bars = ax.bar(user_names, values, color=colors, edgecolor="white", linewidth=0.6)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Felhasználó", fontsize=9)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=(title != "Pontosság (%)")))
        top = max(values) if values else 1
        ax.set_ylim(0, top * 1.25 + 0.5)
        for bar, val in zip(bars, values, strict=False):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + top * 0.02,
                str(val), ha="center", va="bottom", fontsize=9,
            )
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.spines[["top", "right"]].set_visible(False)

    legend_handles = [Patch(color=cmap[u], label=u) for u in user_names]
    fig.legend(handles=legend_handles, loc="lower center", ncol=len(user_names),
               bbox_to_anchor=(0.5, -0.04), fontsize=9, title="Felhasználó")
    plt.tight_layout()

    fname = "overall_summary.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_accuracy_targy(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str, user_names: list[str]
) -> str | None:
    targyak = sorted({r.targy for r in data.targy_szint})
    if not targyak:
        return None

    import matplotlib.pyplot as plt
    import numpy as np

    acc: dict[str, dict[str, float]] = {u: {} for u in user_names}
    cnt_mat: dict[str, dict[str, int]] = {u: {} for u in user_names}
    for row in data.targy_szint:
        if row.nev in acc:
            acc[row.nev][row.targy] = row.accuracy_pct
            cnt_mat[row.nev][row.targy] = row.attempts

    x = np.arange(len(user_names))
    width = 0.75 / max(len(targyak), 1)

    fig, ax = plt.subplots(figsize=(max(8, len(user_names) * 2.5), 5))
    fig.suptitle(f"Pontosság tárgyak szerint (%)  |  {subtitle}", fontsize=13, fontweight="bold")

    for i, targy in enumerate(targyak):
        vals = [acc[u].get(targy, 0.0) for u in user_names]
        cnts = [cnt_mat[u].get(targy, 0) for u in user_names]
        offset = (i - (len(targyak) - 1) / 2) * width
        bars = ax.bar(
            x + offset, vals, width * 0.88,
            label=targy.capitalize(),
            color=_TARGY_COLORS.get(targy, _USER_PALETTE[i]),
            edgecolor="white",
        )
        for bar, val, n in zip(bars, vals, cnts, strict=False):
            if n > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.8,
                    f"{val:.0f}%\n(n={n})", ha="center", va="bottom", fontsize=8,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(user_names, rotation=15, ha="right")
    ax.set_ylabel("Pontosság (%)", fontsize=10)
    ax.set_xlabel("Felhasználó", fontsize=10)
    ax.set_ylim(0, 120)
    ax.axhline(80, color="#555", linestyle=":", linewidth=1.2, label="80% cél")
    ax.legend(title="Tárgy", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    fname = "accuracy_targy.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_daily_activity(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str,
    user_names: list[str], all_dates: list[str],
) -> str | None:
    if not data.daily and not data.daily_detail:
        return None

    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    daily_by_user: dict[str, dict[str, int]] = {
        u: {d: 0 for d in all_dates} for u in user_names
    }
    for row in data.daily:
        if row.nev in daily_by_user and row.datum in daily_by_user[row.nev]:
            daily_by_user[row.nev][row.datum] = row.attempts

    fig, ax = plt.subplots(figsize=(max(10, len(all_dates) * 1.4), 5))
    fig.suptitle(f"Napi aktivitás – kísérletek száma  |  {subtitle}", fontsize=13, fontweight="bold")
    xs = list(range(len(all_dates)))
    for u in user_names:
        vals = [daily_by_user[u][d] for d in all_dates]
        ax.plot(xs, vals, marker="o", label=u, color=cmap[u], linewidth=2.2, markersize=6)
        for xi, v in zip(xs, vals, strict=False):
            if v > 0:
                ax.annotate(str(v), (float(xi), float(v)), textcoords="offset points", xytext=(0, 7),
                            ha="center", fontsize=8, color=cmap[u])
    ax.set_xlabel("Dátum", fontsize=10)
    ax.set_ylabel("Kísérletek száma", fontsize=10)
    ax.set_xticks(range(len(all_dates)))
    ax.set_xticklabels(all_dates, rotation=30, ha="right")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)
    ax.legend(title="Felhasználó", fontsize=9)
    ax.grid(linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    fname = "daily_activity.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_daily_points(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str,
    user_names: list[str], all_dates: list[str],
) -> str | None:
    if not data.daily_detail:
        return None

    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from matplotlib.lines import Line2D

    ut_pairs, ls_map, marker_map, detail_idx = _build_daily_detail_context(data, user_names)

    fig, ax = plt.subplots(figsize=(max(10, len(all_dates) * 1.4), 5))
    fig.suptitle(f"Napi pontszám (user × tárgy)  |  {subtitle}", fontsize=13, fontweight="bold")
    xs = list(range(len(all_dates)))
    for (u, t) in ut_pairs:
        series_color = cmap[u]
        vals = [getattr(detail_idx.get((d, u, t)), "points", 0) for d in all_dates]
        ax.plot(
            xs,
            vals,
            marker=marker_map[t],
            color=series_color,
            linestyle=ls_map[t],
            linewidth=2,
            markersize=5,
        )
        for xi, v in zip(xs, vals, strict=False):
            if v > 0:
                ax.annotate(str(v), (float(xi), float(v)), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=7.5, color=series_color)
        if any(v > 0 for v in vals):
            avg = sum(vals) / len(vals)
            ax.axhline(avg, color=series_color, linestyle=":", linewidth=1.2, alpha=0.7)
            ax.text(len(all_dates) - 0.5, avg, f"∅{avg:.1f} ({t})",
                va="bottom", ha="right", fontsize=7.5, color=series_color, alpha=0.85)
    ax.set_xlabel("Dátum", fontsize=10)
    ax.set_ylabel("Pontszám", fontsize=10)
    ax.set_xticks(range(len(all_dates)))
    ax.set_xticklabels(all_dates, rotation=30, ha="right")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)

    user_handles = [
        Line2D([0], [0], color=cmap[u], lw=2.5, label=u) for u in user_names
    ]
    targy_handles = [
        Line2D(
            [0],
            [0],
            color="#444444",
            lw=2.5,
            linestyle=ls_map[t],
            marker=marker_map[t],
            markersize=6,
            label=t,
        )
        for t in sorted(marker_map)
    ]
    user_legend = ax.legend(
        handles=user_handles,
        title="Felhasználó (szín)",
        fontsize=9,
        loc="upper left",
    )
    ax.add_artist(user_legend)
    ax.legend(
        handles=targy_handles,
        title="Tárgy (vonal + marker)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(0.0, 0.72),
    )
    ax.grid(linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    fname = "daily_points.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_daily_accuracy(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str,
    user_names: list[str], all_dates: list[str],
) -> str | None:
    if not data.daily_detail:
        return None

    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    ut_pairs, ls_map, marker_map, detail_idx = _build_daily_detail_context(data, user_names)

    fig, ax = plt.subplots(figsize=(max(10, len(all_dates) * 1.4), 5))
    fig.suptitle(f"Napi pontosság (user × tárgy)  |  {subtitle}", fontsize=13, fontweight="bold")
    for (u, t) in ut_pairs:
        series_color = cmap[u]
        vals: list[float | None] = []
        for d in all_dates:
            row = detail_idx.get((d, u, t))
            vals.append(row.accuracy_pct if (row and row.attempts > 0) else None)
        xs_idx = [i for i, v in enumerate(vals) if v is not None]
        ys = [vals[i] for i in xs_idx]  # type: ignore[index]
        ys_float = [float(v) for v in ys if v is not None]
        ax.plot(
            xs_idx,
            ys_float,
            marker=marker_map[t],
            color=series_color,
            linestyle=ls_map[t],
            linewidth=2,
            markersize=5,
        )
        for xi, v in zip(xs_idx, ys_float, strict=False):
            ax.annotate(f"{v:.0f}%", (float(xi), float(v)), textcoords="offset points", xytext=(0, 7),
                ha="center", fontsize=7.5, color=series_color)
    ax.axhline(80, color="#555", linestyle=":", linewidth=1.2, label="80% cél")
    ax.set_xlabel("Dátum", fontsize=10)
    ax.set_ylabel("Pontosság (%)", fontsize=10)
    ax.set_xticks(range(len(all_dates)))
    ax.set_xticklabels(all_dates, rotation=30, ha="right")
    ax.set_ylim(0, 115)

    user_handles = [
        Line2D([0], [0], color=cmap[u], lw=2.5, label=u) for u in user_names
    ]
    targy_handles = [
        Line2D(
            [0],
            [0],
            color="#444444",
            lw=2.5,
            linestyle=ls_map[t],
            marker=marker_map[t],
            markersize=6,
            label=t,
        )
        for t in sorted(marker_map)
    ]
    user_legend = ax.legend(
        handles=user_handles,
        title="Felhasználó (szín)",
        fontsize=9,
        loc="upper left",
    )
    ax.add_artist(user_legend)
    ax.legend(
        handles=targy_handles,
        title="Tárgy (vonal + marker)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(0.0, 0.72),
    )
    ax.grid(linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    fname = "daily_accuracy.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_szint_distribution(
    data: ReportData, output_dir: Path, subtitle: str, user_names: list[str]
) -> str | None:
    if not data.targy_szint:
        return None

    import matplotlib.pyplot as plt
    import numpy as np

    szintek = sorted({r.szint for r in data.targy_szint})
    szint_mat: dict[str, dict[str, int]] = {u: {} for u in user_names}
    for row in data.targy_szint:
        if row.nev in szint_mat:
            szint_mat[row.nev][row.szint] = szint_mat[row.nev].get(row.szint, 0) + row.attempts

    x = np.arange(len(user_names))
    fig, ax = plt.subplots(figsize=(max(7, len(user_names) * 2.2), 5))
    fig.suptitle(f"Kísérletek szint szerint  |  {subtitle}", fontsize=13, fontweight="bold")

    bottoms = np.zeros(len(user_names))
    for sz in szintek:
        vals = np.array([szint_mat[u].get(sz, 0) for u in user_names], dtype=float)
        color = _SZINT_COLORS.get(sz, "#8C8C8C")
        ax.bar(x, vals, bottom=bottoms, label=sz, color=color, edgecolor="white", linewidth=0.6)
        for xi, (v, b) in enumerate(zip(vals, bottoms, strict=False)):
            if v > 0:
                ax.text(xi, b + v / 2, str(int(v)),
                        ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(user_names, rotation=15, ha="right")
    ax.set_ylabel("Kísérletek száma", fontsize=10)
    ax.set_xlabel("Felhasználó", fontsize=10)
    ax.legend(title="Szint", fontsize=9, loc="upper right")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    fname = "szint_distribution.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_attempt_time_points(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str, user_names: list[str]
) -> str | None:
    if not data.attempt_timing:
        return None

    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    marker_map = {
        "matek": "o",
        "magyar": "s",
        "ismeretlen": "^",
    }
    max_ponts = sorted({max(0, row.max_pont) for row in data.attempt_timing})
    size_map = {
        max_pont: 30 + (max_pont * 22)
        for max_pont in max_ponts
    }

    fig, ax = plt.subplots(figsize=(11, 6))
    fig.suptitle(
        f"Szerzett pont vs. próbálkozási idő (user × tárgy × max pont)  |  {subtitle}",
        fontsize=13,
        fontweight="bold",
    )

    x_limit_min = 8.0
    visible_max_point = max((row.gained_pont for row in data.attempt_timing), default=0)
    optimal_x = [0.0, x_limit_min]
    optimal_y = [0.0, x_limit_min / 0.9]
    ax.plot(
        optimal_x,
        optimal_y,
        linestyle=":",
        linewidth=2.0,
        color="#C44E52",
        alpha=0.9,
        label="Optimális limit",
    )
    ax.text(
        x_limit_min,
        min(optimal_y[-1], max(visible_max_point, 1) + 0.35),
        "0.9 perc / pont",
        color="#C44E52",
        fontsize=9,
        ha="right",
        va="bottom",
    )

    for row in data.attempt_timing:
        marker = marker_map.get(row.targy, "^")
        color = cmap.get(row.nev, "#666666")
        size = size_map.get(max(0, row.max_pont), 30)
        edge = "#111111" if row.correct else ("#555555" if row.partial else "white")
        ax.scatter(
            row.elapsed_sec / 60,
            row.gained_pont,
            s=size,
            c=color,
            marker=marker,
            alpha=0.75,
            edgecolors=edge,
            linewidths=0.8,
        )

    ax.set_xlabel("Próbálkozási idő (perc)", fontsize=10)
    ax.set_ylabel("Szerzett pont", fontsize=10)
    ax.set_xlim(0, x_limit_min)
    ax.set_ylim(bottom=0)
    ax.grid(linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

    user_handles = [
        Line2D([0], [0], marker="o", color="w", label=u, markerfacecolor=cmap[u],
               markeredgecolor=cmap[u], markersize=8)
        for u in user_names
    ]
    targy_handles = [
        Line2D([0], [0], marker=marker_map[t], color="#444444", label=t,
               linestyle="None", markersize=8)
        for t in sorted({row.targy for row in data.attempt_timing})
    ]
    size_handles = [
        plt.scatter([], [], s=size_map[max_pont], color="#999999", alpha=0.6, label=f"max {max_pont}p")
        for max_pont in max_ponts
    ]

    user_legend = ax.legend(
        handles=user_handles,
        title="Felhasználó (szín)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
    )
    ax.add_artist(user_legend)
    targy_legend = ax.legend(
        handles=targy_handles,
        title="Tárgy (marker)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 0.72),
        borderaxespad=0.0,
    )
    ax.add_artist(targy_legend)
    ax.legend(
        handles=size_handles,
        title="Max pont (méret)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 0.42),
        borderaxespad=0.0,
    )
    plt.tight_layout(rect=(0, 0, 0.78, 1))

    fname = "attempt_time_points.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_session_average_points(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str, user_names: list[str]
) -> str | None:
    if not data.session_average_points:
        return None

    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    marker_map = {
        "matek": "o",
        "magyar": "s",
        "ismeretlen": "^",
    }
    avg_max_values = sorted({round(max(0.0, row.avg_max_pont), 1) for row in data.session_average_points})
    size_map = {
        avg_max: 35 + (avg_max * 28)
        for avg_max in avg_max_values
    }

    fig, ax = plt.subplots(figsize=(11, 6))
    fig.suptitle(
        f"Menet-átlag: szerzett pont vs. próbálkozási idő  |  {subtitle}",
        fontsize=13,
        fontweight="bold",
    )

    x_limit_min = 8.0
    visible_max_point = max((row.avg_gained_pont for row in data.session_average_points), default=0.0)
    optimal_x = [0.0, x_limit_min]
    optimal_y = [0.0, x_limit_min / 0.9]
    ax.plot(
        optimal_x,
        optimal_y,
        linestyle=":",
        linewidth=2.0,
        color="#C44E52",
        alpha=0.9,
        label="Optimális limit",
    )
    ax.text(
        x_limit_min,
        min(optimal_y[-1], max(visible_max_point, 1.0) + 0.35),
        "0.9 perc / pont",
        color="#C44E52",
        fontsize=9,
        ha="right",
        va="bottom",
    )

    for row in data.session_average_points:
        marker = marker_map.get(row.targy, "^")
        color = cmap.get(row.nev, "#666666")
        avg_max_key = round(max(0.0, row.avg_max_pont), 1)
        size = size_map.get(avg_max_key, 35)
        x_value = row.avg_elapsed_sec / 60
        y_value = row.avg_gained_pont
        ax.scatter(
            x_value,
            y_value,
            s=size,
            c=color,
            marker=marker,
            alpha=0.78,
            edgecolors="#222222",
            linewidths=0.8,
        )
        ax.annotate(
            row.session_date,
            (x_value, y_value),
            textcoords="offset points",
            xytext=(6, 6),
            ha="left",
            va="bottom",
            fontsize=8,
            color="#333333",
        )

    ax.set_xlabel("Átlag próbálkozási idő (perc)", fontsize=10)
    ax.set_ylabel("Átlag szerzett pont", fontsize=10)
    ax.set_xlim(0, x_limit_min)
    ax.set_ylim(bottom=0)
    ax.grid(linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

    user_handles = [
        Line2D([0], [0], marker="o", color="w", label=u, markerfacecolor=cmap[u],
               markeredgecolor=cmap[u], markersize=8)
        for u in user_names
    ]
    targy_handles = [
        Line2D([0], [0], marker=marker_map[t], color="#444444", label=t,
               linestyle="None", markersize=8)
        for t in sorted({row.targy for row in data.session_average_points})
    ]
    size_handles = [
        plt.scatter([], [], s=size_map[avg_max], color="#999999", alpha=0.6, label=f"átlag max {avg_max:.1f}p")
        for avg_max in avg_max_values
    ]

    user_legend = ax.legend(
        handles=user_handles,
        title="Felhasználó (szín)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
    )
    ax.add_artist(user_legend)
    targy_legend = ax.legend(
        handles=targy_handles,
        title="Tárgy (marker)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 0.72),
        borderaxespad=0.0,
    )
    ax.add_artist(targy_legend)
    ax.legend(
        handles=size_handles,
        title="Átlag max pont (méret)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 0.42),
        borderaxespad=0.0,
    )
    plt.tight_layout(rect=(0, 0, 0.78, 1))

    fname = "session_average_points.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


def _chart_session_average_delta_points(
    data: ReportData, output_dir: Path, cmap: dict, subtitle: str, user_names: list[str]
) -> str | None:
    if not data.session_average_points:
        return None

    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    marker_map = {
        "matek": "o",
        "magyar": "s",
        "ismeretlen": "^",
    }
    avg_max_values = sorted({round(max(0.0, row.avg_max_pont), 1) for row in data.session_average_points})
    size_map = {
        avg_max: 35 + (avg_max * 28)
        for avg_max in avg_max_values
    }

    fig, ax = plt.subplots(figsize=(11, 6))
    fig.suptitle(
        f"Menet-átlag eltérés a célhoz képest  |  {subtitle}",
        fontsize=13,
        fontweight="bold",
    )

    for _, _, _, _, metrics, row in _session_performance_rows(data):
        marker = marker_map.get(row.targy, "^")
        color = cmap.get(row.nev, "#666666")
        avg_max_key = round(max(0.0, metrics.average_achievable_points), 1)
        size = size_map.get(avg_max_key, 35)
        x_value = (0.9 * metrics.average_achievable_points) - (
            metrics.time_sec / row.committed_count / 60
        )
        y_value = (
            metrics.earned_points / row.committed_count
            - (0.8 * metrics.average_achievable_points)
        )
        ax.scatter(
            x_value,
            y_value,
            s=size,
            c=color,
            marker=marker,
            alpha=0.78,
            edgecolors="#222222",
            linewidths=0.8,
        )
        ax.annotate(
            row.session_date,
            (x_value, y_value),
            textcoords="offset points",
            xytext=(6, 6),
            ha="left",
            va="bottom",
            fontsize=8,
            color="#333333",
        )

    ax.axvline(0, color="#666666", linestyle=":", linewidth=1.5)
    ax.axhline(0, color="#666666", linestyle=":", linewidth=1.5)
    ax.text(3.9, 2.85, "jobb mint cél", fontsize=9, color="#444444", ha="right", va="top")
    ax.set_xlabel("Időeltérés a 0.9 perc/pont célhoz képest (perc)", fontsize=10)
    ax.set_ylabel("Ponteltérés a 80% célhoz képest", fontsize=10)
    ax.set_xlim(-4, 4)
    ax.set_ylim(-2, 3)
    ax.grid(linestyle="--", alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

    user_handles = [
        Line2D([0], [0], marker="o", color="w", label=u, markerfacecolor=cmap[u],
               markeredgecolor=cmap[u], markersize=8)
        for u in user_names
    ]
    targy_handles = [
        Line2D([0], [0], marker=marker_map[t], color="#444444", label=t,
               linestyle="None", markersize=8)
        for t in sorted({row.targy for row in data.session_average_points})
    ]
    size_handles = [
        plt.scatter([], [], s=size_map[avg_max], color="#999999", alpha=0.6, label=f"átlag max {avg_max:.1f}p")
        for avg_max in avg_max_values
    ]

    user_legend = ax.legend(
        handles=user_handles,
        title="Felhasználó (szín)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
    )
    ax.add_artist(user_legend)
    targy_legend = ax.legend(
        handles=targy_handles,
        title="Tárgy (marker)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 0.72),
        borderaxespad=0.0,
    )
    ax.add_artist(targy_legend)
    ax.legend(
        handles=size_handles,
        title="Átlag max pont (méret)",
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(1.02, 0.42),
        borderaxespad=0.0,
    )
    plt.tight_layout(rect=(0, 0, 0.78, 1))

    fname = "session_average_delta_points.png"
    fig.savefig(output_dir / fname, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info("report: chart saved %s", fname)
    return fname


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

def generate_charts(data: ReportData, output_dir: Path) -> list[str]:
    """Generate all PNG charts into output_dir. Returns list of filenames."""
    import matplotlib
    matplotlib.use("Agg")

    output_dir.mkdir(parents=True, exist_ok=True)

    user_names = [u.nev for u in data.users]
    if not user_names:
        logger.warning("report: no users in data, skipping charts")
        return []

    cmap = _user_colors(user_names)
    fmt_from = data.date_from.strftime("%Y-%m-%d")
    fmt_to = (data.date_to - timedelta(seconds=1)).strftime("%Y-%m-%d")
    subtitle = f"{fmt_from} – {fmt_to}"
    all_dates = _build_date_range(data)

    chart_files: list[str] = []
    for fname in [
        _chart_overall_summary(data, output_dir, cmap, subtitle, user_names),
        _chart_accuracy_targy(data, output_dir, cmap, subtitle, user_names),
        _chart_daily_activity(data, output_dir, cmap, subtitle, user_names, all_dates),
        _chart_daily_points(data, output_dir, cmap, subtitle, user_names, all_dates),
        _chart_daily_accuracy(data, output_dir, cmap, subtitle, user_names, all_dates),
        _chart_attempt_time_points(data, output_dir, cmap, subtitle, user_names),
        _chart_session_average_points(data, output_dir, cmap, subtitle, user_names),
        _chart_session_average_delta_points(data, output_dir, cmap, subtitle, user_names),
        _chart_szint_distribution(data, output_dir, subtitle, user_names),
    ]:
        if fname:
            chart_files.append(fname)
    return chart_files


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

_CHART_TITLES = {
    "overall_summary.png":   "Összefoglaló áttekintés",
    "accuracy_targy.png":    "Pontosság tárgyak szerint",
    "daily_activity.png":    "Napi aktivitás – kísérletek száma",
    "daily_points.png":      "Napi aktivitás – pontszám (user × tárgy)",
    "daily_accuracy.png":    "Napi aktivitás – pontosság (user × tárgy)",
    "attempt_time_points.png": "Szerzett pont vs. próbálkozási idő",
    "session_average_points.png": "Menet-átlag: szerzett pont vs. próbálkozási idő",
    "session_average_delta_points.png": "Menet-átlag eltérés a célhoz képest",
    "szint_distribution.png": "Kísérletek szint szerint",
}

_CHART_SECTIONS = {
    "overall_summary.png":   "Összefoglaló",
    "accuracy_targy.png":    "Pontosság tárgyak szerint",
    "daily_activity.png":    "Napi aktivitás",
    "daily_points.png":      "Napi aktivitás",
    "daily_accuracy.png":    "Napi aktivitás",
    "attempt_time_points.png": "Próbálkozási idő vs pont",
    "session_average_points.png": "Menet-átlagok",
    "session_average_delta_points.png": "Menet-átlag eltérések",
    "szint_distribution.png": "Kísérletek szint szerint",
}


def _append_performance_table(
    lines: list[str],
    title: str,
    rows: list[tuple[str, str, str, int, PerformanceMetrics]],
) -> None:
    lines += [
        f"### {title}",
        "",
        "| Felhasználó | Tény | Feladatok száma | Elérhető pont összesen | Szerzett pont összesen | Idő összesen | Szerzett / elérhető átlag [%] | Idő / szerzett pont átlag (perc/pont) | Elérhető pont átlag |",
        "|-------------|------|-----------------|------------------------|------------------------|--------------|-------------------------------|----------------------------------------|---------------------|",
    ]
    for user, fact, _, task_count, metrics in rows:
        lines.append(
            f"| {user} | {fact} | {task_count} | {metrics.achievable_points:.1f} | "
            f"{metrics.earned_points:.1f} | {metrics.time_sec / 60:.1f} perc | "
            f"{metrics.earned_pct:.1f}% | {metrics.time_per_earned_point / 60:.2f} | "
            f"{metrics.average_achievable_points:.1f} |"
        )
    lines.append("")


def _writing_task_label(row: WritingTaskResult) -> str:
    identifiers: list[str] = []
    if row.exam_year is not None:
        identifiers.append(str(row.exam_year))
    if row.variant is not None:
        identifiers.append(f"v{row.variant}")
    if row.task_number:
        identifiers.append(f"feladat {row.task_number}")
    identifier = " / ".join(identifiers)
    return f"{row.title} ({identifier})" if identifier else row.title


def _writing_status_label(row: WritingTaskResult) -> str:
    if row.total_score is not None:
        return "Értékelve"
    return {
        "active": "Folyamatban",
        "paused": "Szüneteltetve",
        "submitted": "Beküldve",
    }.get(row.status, row.status)


def _writing_source_label(source_kind: str) -> str:
    return {
        "official": "hivatalos",
        "practice": "gyakorló",
    }.get(source_kind, source_kind)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _append_writing_table(lines: list[str], data: ReportData) -> None:
    if not data.writing:
        return

    lines += [
        "---",
        "",
        "## Írásbeli vizsgafeladatok",
        "",
        "_Az írásfeladatok pontozása külön szerepel a kvízfeladatok pontszámától, "
        "mert más értékelési skálát használnak._",
        "",
        "| Felhasználó | Kezdés | Feladat | Forrás | Állapot | Pont | Pontosság | Aktív idő | Mondatok |",
        "|-------------|---------|---------|--------|---------|------|-----------|-----------|----------|",
    ]
    for row in sorted(data.writing, key=lambda item: (item.started_at, item.nev, item.task_id)):
        if row.total_score is not None and row.max_score is not None:
            score = f"{row.total_score} / {row.max_score}"
            accuracy = (
                f"{row.total_score / row.max_score * 100:.1f}%"
                if row.max_score > 0
                else "–"
            )
        elif row.total_score is not None:
            score = str(row.total_score)
            accuracy = "–"
        else:
            score = "–"
            accuracy = "–"
        sentence_count = (
            str(row.learner_sentence_count)
            if row.learner_sentence_count is not None
            else "–"
        )
        lines.append(
            f"| {_markdown_cell(row.nev)} | {row.started_at.strftime('%Y-%m-%d')} | "
            f"{_markdown_cell(_writing_task_label(row))} | "
            f"{_markdown_cell(_writing_source_label(row.source_kind))} | "
            f"{_markdown_cell(_writing_status_label(row))} | {score} | {accuracy} | "
            f"{row.active_seconds / 60:.1f} perc | {sentence_count} |"
        )
    lines.append("")


def generate_markdown(data: ReportData, chart_files: list[str], output_dir: Path) -> Path:
    fmt_from = data.date_from.strftime("%Y-%m-%d")
    fmt_to = (data.date_to - timedelta(seconds=1)).strftime("%Y-%m-%d")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        f"# Tanulási riport: {fmt_from} – {fmt_to}",
        "",
        f"_Generálva: {generated_at}  |  Időszak: {data.days} nap_",
        "",
        "---",
        "",
        "## Összefoglaló",
        "",
        "| Felhasználó | Menetek | Kísérletek | Helyes | Részleges | Pontosság | Pont(+részleges) | Pontszám | Játékidő | Új érmek |",
        "|-------------|---------|-----------|--------|-----------|-----------|------------------|----------|----------|----------|",
    ]

    for u in data.users:
        play = f"{u.play_time_min:.0f} perc" if u.play_time_min >= 1 else "<1 perc"
        acc_with_partial = ((u.correct + u.partial) / u.attempts * 100) if u.attempts else 0.0
        lines.append(
            f"| {u.nev} | {u.sessions} | {u.attempts} | {u.correct} | {u.partial} "
            f"| {u.accuracy_pct:.1f}% | {acc_with_partial:.1f}% | {u.points} | {play} | {u.new_achievements} |"
        )

    lines += ["", "---", "", "## Részletes bontás: tárgy × szint", ""]

    for u in data.users:
        rows = [r for r in data.targy_szint if r.nev == u.nev]
        if not rows:
            continue
        lines += [
            f"### {u.nev}",
            "",
            "| Tárgy | Szint | Kísérletek | Helyes | Részleges | Pontosság | Pont(+részleges) | Pontszám |",
            "|-------|-------|-----------|--------|-----------|-----------|------------------|----------|",
        ]
        for r in sorted(rows, key=lambda x: (x.targy, x.szint)):
            acc_with_partial = ((r.correct + r.partial) / r.attempts * 100) if r.attempts else 0.0
            lines.append(
                f"| {r.targy} | {r.szint} | {r.attempts} | {r.correct} | {r.partial} "
                f"| {r.accuracy_pct:.1f}% | {acc_with_partial:.1f}% | {r.points} |"
            )
        lines.append("")

    _append_writing_table(lines, data)

    lines += ["---", "", "## Érmek kiosztva az időszakban", ""]

    if data.achievements:
        lines += [
            "",
            "_Megjegyzés: az alábbi időpontok a kiosztás/rögzítés idejét mutatják UTC-ben. "
            "Nem feltétlenül egyeznek meg a feltételt kiváltó tanulási esemény pontos idejével, "
            "mert több érem egy menet végén vagy egy későbbi ellenőrzés során együtt kerülhet kiosztásra._",
            "",
        ]
        for ach in sorted(data.achievements, key=lambda a: (a.szerzett_at, a.nev)):
            dt_str = ach.szerzett_at.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"- {ach.ikon} **{ach.nev}** → {ach.erem_nev}  _{dt_str} UTC_")

        # Diagnostics: same-minute award clusters often come from one evaluation pass.
        minute_groups: dict[tuple[str, str], list[AchievementRow]] = defaultdict(list)
        for ach in data.achievements:
            minute_key = ach.szerzett_at.strftime("%Y-%m-%d %H:%M")
            minute_groups[(ach.nev, minute_key)].append(ach)

        clusters = [
            (nev, minute, rows)
            for (nev, minute), rows in sorted(minute_groups.items(), key=lambda item: item[0])
            if len(rows) >= 2
        ]
        if clusters:
            lines += ["", "### Időbélyeg-cluster diagnosztika", ""]
            for nev, minute, rows in clusters:
                medal_list = ", ".join(f"{r.ikon} {r.erem_nev}" for r in rows)
                lines.append(
                    f"- **{nev}** · {minute} percben {len(rows)} érem: {medal_list}"
                )
            lines += [
                "",
                "_Megjegyzés: a riport perces csoportosítása egyetlen érem-ellenőrzési futásból származó tömeges kiosztást is jelezhet._",
            ]
    else:
        lines.append("_(Ebben az időszakban nem szerzett senki új érmet.)_")

    lines += ["", "---", "", "## Célhoz viszonyított teljesítmény táblázatok", ""]
    _append_performance_table(lines, "Napi aggregáció", _daily_performance_rows(data))
    _append_performance_table(
        lines,
        "Menet alapú aggregáció",
        [
            (user, fact, subject, task_count, metrics)
            for user, fact, subject, task_count, metrics, _ in _session_performance_rows(data)
        ],
    )

    lines += ["---", "", "## Grafikonok", ""]

    _DAILY_CHARTS = {"daily_activity.png", "daily_points.png", "daily_accuracy.png"}
    daily_printed = False

    for fname in chart_files:
        if fname in _DAILY_CHARTS:
            if not daily_printed:
                lines += ["### Napi aktivitás", ""]
                daily_printed = True
            title = _CHART_TITLES.get(fname, fname)
            lines += [f"**{title}**", "", f"![{title}]({fname})", ""]
        else:
            title = _CHART_TITLES.get(fname, fname)
            lines += [f"### {title}", "", f"![{title}]({fname})", ""]

    out_path = output_dir / "report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report: markdown saved %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    db_path: Path,
    days: int = 7,
    output_dir: Path | None = None,
    user_filter: str | None = None,
) -> Path:
    """Generate report. Returns path to the output folder."""
    from felvi_games.db import get_engine

    if output_dir is None:
        date_tag = datetime.now().strftime("%Y%m%d")
        output_dir = Path("reports") / f"{date_tag}_{days}d"

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("report: generating into %s  (days=%d)", output_dir, days)

    engine = get_engine(db_path)
    data = gather_data(engine, days=days, user_filter=user_filter)
    chart_files = generate_charts(data, output_dir)
    generate_markdown(data, chart_files, output_dir)

    return output_dir
