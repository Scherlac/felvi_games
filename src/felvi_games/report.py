"""report.py
-----------
Heti (és tetszőleges időtartamú) használati riport.

Kimenet: egy mappa, benne:
  report.md               – Markdown összefoglaló táblákkal
  overall_summary.png     – Kísérletek / pontosság / pontszám / játékidő összefoglaló
  accuracy_targy.png      – Pontosság tárgyak szerint (csoportos oszlopdiagram)
  daily_activity.png      – Napi aktivitás (vonaldiagram felhasználónként)
  szint_distribution.png  – Kísérletek szint szerint (halmozott oszlopdiagram)

Usage:
  from felvi_games.report import run
  out_dir = run(db_path, days=7)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class UserSummary:
    nev: str
    sessions: int = 0
    play_time_min: float = 0.0
    attempts: int = 0
    correct: int = 0
    points: int = 0
    new_achievements: int = 0

    @property
    def accuracy_pct(self) -> float:
        return (self.correct / self.attempts * 100) if self.attempts > 0 else 0.0


@dataclass
class UserTargySzintRow:
    nev: str
    targy: str
    szint: str
    attempts: int = 0
    correct: int = 0
    points: int = 0

    @property
    def accuracy_pct(self) -> float:
        return (self.correct / self.attempts * 100) if self.attempts > 0 else 0.0


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
class DailyDetail:
    """Per-day, per-user, per-tárgy breakdown for points and accuracy charts."""
    datum: str   # YYYY-MM-DD
    nev: str
    targy: str
    attempts: int = 0
    correct: int = 0
    points: int = 0

    @property
    def accuracy_pct(self) -> float:
        return (self.correct / self.attempts * 100) if self.attempts > 0 else 0.0


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


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def gather_data(engine, days: int, user_filter: str | None = None) -> ReportData:
    from collections import defaultdict

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from felvi_games.db import (
        EremRecord,
        FelhasznaloEremRecord,
        MegoldasRecord,
        MenetRecord,
    )

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=days)
    data = ReportData(date_from=date_from, date_to=date_to, days=days)

    with Session(engine) as s:
        # sessions in window
        q_sessions = (
            select(
                MenetRecord.felhasznalo_nev,
                MenetRecord.targy,
                MenetRecord.szint,
                MenetRecord.megoldott,
                MenetRecord.pont,
                MenetRecord.started_at,
                MenetRecord.ended_at,
            )
            .where(MenetRecord.started_at >= date_from)
        )
        if user_filter:
            q_sessions = q_sessions.where(MenetRecord.felhasznalo_nev == user_filter)
        sessions = s.execute(q_sessions).all()

        # answers in window (joined to menetek for targy/szint)
        q_answers = (
            select(
                MegoldasRecord.felhasznalo_nev,
                MenetRecord.targy,
                MenetRecord.szint,
                MegoldasRecord.helyes,
                MegoldasRecord.pont,
                MegoldasRecord.created_at,
            )
            .join(MenetRecord, MenetRecord.id == MegoldasRecord.menet_id)
            .where(MegoldasRecord.created_at >= date_from)
        )
        if user_filter:
            q_answers = q_answers.where(MegoldasRecord.felhasznalo_nev == user_filter)
        answers = s.execute(q_answers).all()

        # achievements earned in window
        q_ach = (
            select(
                FelhasznaloEremRecord.felhasznalo_nev,
                FelhasznaloEremRecord.erem_id,
                FelhasznaloEremRecord.szerzett_at,
                EremRecord.nev,
                EremRecord.ikon,
            )
            .join(EremRecord, EremRecord.id == FelhasznaloEremRecord.erem_id)
            .where(FelhasznaloEremRecord.szerzett_at >= date_from)
        )
        if user_filter:
            q_ach = q_ach.where(FelhasznaloEremRecord.felhasznalo_nev == user_filter)
        achievements = s.execute(q_ach).all()

    # --- aggregate ---
    user_data: dict[str, UserSummary] = {}
    targy_szint_data: dict[tuple, UserTargySzintRow] = {}

    for row in sessions:
        u = row.felhasznalo_nev
        if u not in user_data:
            user_data[u] = UserSummary(nev=u)
        user_data[u].sessions += 1
        if row.ended_at and row.started_at:
            delta_min = (row.ended_at - row.started_at).total_seconds() / 60
            if 0 < delta_min < 300:  # sanity cap: 5h
                user_data[u].play_time_min += delta_min

    daily_dict: dict[tuple[str, str], int] = defaultdict(int)
    daily_detail_dict: dict[tuple[str, str, str], dict] = defaultdict(dict)
    for row in answers:
        u = row.felhasznalo_nev
        if u not in user_data:
            user_data[u] = UserSummary(nev=u)
        user_data[u].attempts += 1
        if row.helyes:
            user_data[u].correct += 1
        user_data[u].points += row.pont or 0

        key = (u, row.targy, row.szint)
        if key not in targy_szint_data:
            targy_szint_data[key] = UserTargySzintRow(nev=u, targy=row.targy, szint=row.szint)
        targy_szint_data[key].attempts += 1
        if row.helyes:
            targy_szint_data[key].correct += 1
        targy_szint_data[key].points += row.pont or 0

        datum = row.created_at.strftime("%Y-%m-%d")
        daily_dict[(datum, u)] += 1

        # per-day × user × tárgy breakdown
        targy = row.targy or "ismeretlen"
        daily_detail_dict[(datum, u, targy)].setdefault("attempts", 0)
        daily_detail_dict[(datum, u, targy)]["attempts"] += 1
        daily_detail_dict[(datum, u, targy)].setdefault("correct", 0)
        if row.helyes:
            daily_detail_dict[(datum, u, targy)]["correct"] += 1
        daily_detail_dict[(datum, u, targy)].setdefault("points", 0)
        daily_detail_dict[(datum, u, targy)]["points"] += row.pont or 0

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

    for (datum, nev), cnt in sorted(daily_dict.items()):
        data.daily.append(DailyActivity(datum=datum, nev=nev, attempts=cnt))

    for (datum, nev, targy), vals in sorted(daily_detail_dict.items()):
        data.daily_detail.append(DailyDetail(
            datum=datum, nev=nev, targy=targy,
            attempts=vals.get("attempts", 0),
            correct=vals.get("correct", 0),
            points=vals.get("points", 0),
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


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _build_date_range(data: ReportData) -> list[str]:
    all_dates: list[str] = []
    cur = data.date_from.replace(hour=0, minute=0, second=0, microsecond=0)
    while cur <= data.date_to:
        all_dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return all_dates


def _build_daily_detail_context(
    data: ReportData, user_names: list[str]
) -> tuple[list[tuple[str, str]], dict[str, str], dict]:
    ut_pairs = sorted({(r.nev, r.targy) for r in data.daily_detail if r.nev in user_names})
    targy_list = sorted({t for _, t in ut_pairs})
    _LINESTYLES = ["-", "--", "-.", ":"]
    ls_map = {t: _LINESTYLES[i % len(_LINESTYLES)] for i, t in enumerate(targy_list)}
    detail_idx = {(r.datum, r.nev, r.targy): r for r in data.daily_detail}
    return ut_pairs, ls_map, detail_idx


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
    for u in user_names:
        vals = [daily_by_user[u][d] for d in all_dates]
        ax.plot(all_dates, vals, marker="o", label=u, color=cmap[u], linewidth=2.2, markersize=6)
        for d, v in zip(all_dates, vals, strict=False):
            if v > 0:
                ax.annotate(str(v), (d, v), textcoords="offset points", xytext=(0, 7),
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

    ut_pairs, ls_map, detail_idx = _build_daily_detail_context(data, user_names)

    fig, ax = plt.subplots(figsize=(max(10, len(all_dates) * 1.4), 5))
    fig.suptitle(f"Napi pontszám (user × tárgy)  |  {subtitle}", fontsize=13, fontweight="bold")
    for (u, t) in ut_pairs:
        vals = [getattr(detail_idx.get((d, u, t)), "points", 0) for d in all_dates]
        ax.plot(all_dates, vals, marker="o", label=f"{u} – {t}",
                color=cmap[u], linestyle=ls_map[t], linewidth=2, markersize=5)
        for d, v in zip(all_dates, vals, strict=False):
            if v > 0:
                ax.annotate(str(v), (d, v), textcoords="offset points", xytext=(0, 7),
                            ha="center", fontsize=7.5, color=cmap[u])
        if any(v > 0 for v in vals):
            avg = sum(vals) / len(vals)
            ax.axhline(avg, color=cmap[u], linestyle=":", linewidth=1.2, alpha=0.7)
            ax.text(len(all_dates) - 0.5, avg, f"∅{avg:.1f} ({t})",
                    va="bottom", ha="right", fontsize=7.5, color=cmap[u], alpha=0.85)
    ax.set_xlabel("Dátum", fontsize=10)
    ax.set_ylabel("Pontszám", fontsize=10)
    ax.set_xticks(range(len(all_dates)))
    ax.set_xticklabels(all_dates, rotation=30, ha="right")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.set_ylim(bottom=0)
    ax.legend(title="Felhasználó – tárgy", fontsize=9, loc="upper left")
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

    ut_pairs, ls_map, detail_idx = _build_daily_detail_context(data, user_names)

    fig, ax = plt.subplots(figsize=(max(10, len(all_dates) * 1.4), 5))
    fig.suptitle(f"Napi pontosság (user × tárgy)  |  {subtitle}", fontsize=13, fontweight="bold")
    for (u, t) in ut_pairs:
        vals: list[float | None] = []
        for d in all_dates:
            row = detail_idx.get((d, u, t))
            vals.append(row.accuracy_pct if (row and row.attempts > 0) else None)
        xs_idx = [i for i, v in enumerate(vals) if v is not None]
        ys = [vals[i] for i in xs_idx]  # type: ignore[index]
        ax.plot(xs_idx, ys, marker="o", label=f"{u} – {t}",
                color=cmap[u], linestyle=ls_map[t], linewidth=2, markersize=5)
        for xi, v in zip(xs_idx, ys, strict=False):
            ax.annotate(f"{v:.0f}%", (xi, v), textcoords="offset points", xytext=(0, 7),
                        ha="center", fontsize=7.5, color=cmap[u])
    ax.axhline(80, color="#555", linestyle=":", linewidth=1.2, label="80% cél")
    ax.set_xlabel("Dátum", fontsize=10)
    ax.set_ylabel("Pontosság (%)", fontsize=10)
    ax.set_xticks(range(len(all_dates)))
    ax.set_xticklabels(all_dates, rotation=30, ha="right")
    ax.set_ylim(0, 115)
    ax.legend(title="Felhasználó – tárgy", fontsize=9, loc="upper left")
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
    "szint_distribution.png": "Kísérletek szint szerint",
}

_CHART_SECTIONS = {
    "overall_summary.png":   "Összefoglaló",
    "accuracy_targy.png":    "Pontosság tárgyak szerint",
    "daily_activity.png":    "Napi aktivitás",
    "daily_points.png":      "Napi aktivitás",
    "daily_accuracy.png":    "Napi aktivitás",
    "szint_distribution.png": "Kísérletek szint szerint",
}


def generate_markdown(data: ReportData, chart_files: list[str], output_dir: Path) -> Path:
    fmt_from = data.date_from.strftime("%Y-%m-%d")
    fmt_to = (data.date_to - timedelta(seconds=1)).strftime("%Y-%m-%d")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = [
        f"# Tanulási riport: {fmt_from} – {fmt_to}",
        "",
        f"_Generálva: {generated_at}  |  Időszak: {data.days} nap_",
        "",
        "---",
        "",
        "## Összefoglaló",
        "",
        "| Felhasználó | Menetek | Kísérletek | Helyes | Pontosság | Pontszám | Játékidő | Új érmek |",
        "|-------------|---------|-----------|--------|-----------|----------|----------|----------|",
    ]

    for u in data.users:
        play = f"{u.play_time_min:.0f} perc" if u.play_time_min >= 1 else "<1 perc"
        lines.append(
            f"| {u.nev} | {u.sessions} | {u.attempts} | {u.correct} "
            f"| {u.accuracy_pct:.1f}% | {u.points} | {play} | {u.new_achievements} |"
        )

    lines += ["", "---", "", "## Részletes bontás: tárgy × szint", ""]

    for u in data.users:
        rows = [r for r in data.targy_szint if r.nev == u.nev]
        if not rows:
            continue
        lines += [
            f"### {u.nev}",
            "",
            "| Tárgy | Szint | Kísérletek | Helyes | Pontosság | Pontszám |",
            "|-------|-------|-----------|--------|-----------|----------|",
        ]
        for r in sorted(rows, key=lambda x: (x.targy, x.szint)):
            lines.append(
                f"| {r.targy} | {r.szint} | {r.attempts} | {r.correct} "
                f"| {r.accuracy_pct:.1f}% | {r.points} |"
            )
        lines.append("")

    lines += ["---", "", "## Új érmek az időszakban", ""]

    if data.achievements:
        for ach in sorted(data.achievements, key=lambda a: (a.szerzett_at, a.nev)):
            dt_str = ach.szerzett_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"- {ach.ikon} **{ach.nev}** → {ach.erem_nev}  _{dt_str}_")
    else:
        lines.append("_(Ebben az időszakban nem szerzett senki új érmet.)_")

    lines += ["", "---", "", "## Grafikonok", ""]

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
