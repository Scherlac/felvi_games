#!/usr/bin/env python3
"""Generate a Copilot-friendly code quality report with a regression-aware gate.

The script focuses on complexity regressions relative to a repository baseline.
It allows improvements and small fluctuations, but fails on significant regressions.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze


def cc_rank(score: float) -> str:
    if score <= 5:
        return "A"
    if score <= 10:
        return "B"
    if score <= 20:
        return "C"
    if score <= 30:
        return "D"
    if score <= 40:
        return "E"
    return "F"


def _rank_value(rank: str) -> int:
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    return order.get(rank, 99)


@dataclass
class GateThresholds:
    # FAIL thresholds — exceeding any of these causes QUALITY_GATE: FAIL.
    # Any regression that stays *within* tolerance triggers a WARNING note instead.
    max_avg_cc_increase: float = 0.35
    max_p95_cc_increase: float = 1.25
    max_d_or_worse_increase: int = 3
    max_f_increase: int = 0
    max_block_cc_increase: float = 4.0
    max_significant_block_regressions: int = 1
    min_coverage_pct: float = 0.0
    max_coverage_drop: float = 1.0


@dataclass
class BlockStat:
    file: str
    name: str
    line: int
    complexity: float
    rank: str


@dataclass
class Snapshot:
    schema_version: int
    generated_at_utc: str
    paths: list[str]
    python_files: int
    total_loc: int
    total_sloc: int
    total_blank: int
    avg_mi: float
    avg_cc: float
    p95_cc: float
    counts_by_rank: dict[str, int]
    d_or_worse_blocks: int
    f_blocks: int
    parse_error_files: list[str]
    blocks: list[dict[str, object]]
    top_blocks: list[dict[str, object]]
    coverage_pct: float | None = None
    coverage_files: int = 0
    low_coverage_files: list[dict[str, object]] = field(default_factory=list)
    coverage_error: str | None = None
    coverage_source: str | None = None


@dataclass
class GateDecision:
    status: str
    reasons: list[str]
    deltas: dict[str, float | int]
    significant_regressions: list[dict[str, object]]
    notes: list[str]


def _iter_py_files(paths: Iterable[Path]) -> Iterable[Path]:
    skip_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    seen: set[Path] = set()
    for root in paths:
        if root.is_file() and root.suffix == ".py":
            rp = root.resolve()
            if rp not in seen:
                seen.add(rp)
                yield rp
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in skip_dirs for part in path.parts):
                continue
            rp = path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            yield rp


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((q / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


def build_snapshot(repo_root: Path, scan_paths: list[Path], top_n: int = 15) -> Snapshot:
    blocks: list[BlockStat] = []
    mi_values: list[float] = []
    parse_error_files: list[str] = []

    total_loc = 0
    total_sloc = 0
    total_blank = 0
    py_files = list(_iter_py_files(scan_paths))

    for py_file in py_files:
        code = py_file.read_text(encoding="utf-8", errors="replace")
        rel = _rel(py_file, repo_root)

        raw = analyze(code)
        total_loc += raw.loc
        total_sloc += raw.sloc
        total_blank += raw.blank

        try:
            mi_values.append(float(mi_visit(code, multi=True)))
            for item in cc_visit(code):
                score = float(item.complexity)
                blocks.append(
                    BlockStat(
                        file=rel,
                        name=item.fullname,
                        line=int(item.lineno),
                        complexity=score,
                        rank=cc_rank(score),
                    )
                )
        except Exception:
            parse_error_files.append(rel)

    cc_values = [b.complexity for b in blocks]
    rank_counts = {k: 0 for k in ["A", "B", "C", "D", "E", "F"]}
    for b in blocks:
        rank_counts[b.rank] += 1

    top_blocks = sorted(blocks, key=lambda b: b.complexity, reverse=True)[:top_n]

    return Snapshot(
        schema_version=2,
        generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        paths=[_rel(p, repo_root) for p in scan_paths],
        python_files=len(py_files),
        total_loc=total_loc,
        total_sloc=total_sloc,
        total_blank=total_blank,
        avg_mi=round(statistics.mean(mi_values), 3) if mi_values else 0.0,
        avg_cc=round(statistics.mean(cc_values), 3) if cc_values else 0.0,
        p95_cc=round(_percentile(cc_values, 95), 3),
        counts_by_rank=rank_counts,
        d_or_worse_blocks=rank_counts["D"] + rank_counts["E"] + rank_counts["F"],
        f_blocks=rank_counts["F"],
        parse_error_files=sorted(parse_error_files),
        blocks=[asdict(b) for b in blocks],
        top_blocks=[asdict(tb) for tb in top_blocks],
        coverage_pct=None,
        coverage_files=0,
        low_coverage_files=[],
        coverage_error=None,
        coverage_source=None,
    )


def _run_coverage_command(repo_root: Path, coverage_command: str) -> str | None:
    if not coverage_command.strip():
        return "Coverage command is empty."
    result = subprocess.run(  # noqa: S603
        coverage_command,
        cwd=repo_root,
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return None
    tail_lines = [line for line in (result.stderr or result.stdout).splitlines() if line][-8:]
    details = " | ".join(tail_lines) if tail_lines else "No stderr/stdout details."
    return f"Coverage command failed (exit={result.returncode}). {details}"


def _coverage_age_minutes(coverage_data_path: Path) -> float | None:
    if not coverage_data_path.exists():
        return None
    modified = datetime.fromtimestamp(coverage_data_path.stat().st_mtime, tz=UTC)
    now = datetime.now(UTC)
    delta = now - modified
    return round(delta.total_seconds() / 60.0, 3)


def _coverage_json_from_data_file(
    repo_root: Path,
    coverage_data_path: Path,
    coverage_json_path: Path,
) -> str | None:
    coverage_json_path.parent.mkdir(parents=True, exist_ok=True)
    command = (
        f"coverage json --data-file \"{coverage_data_path}\" "
        f"-o \"{coverage_json_path}\" --quiet"
    )
    result = subprocess.run(  # noqa: S603
        command,
        cwd=repo_root,
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return None
    tail_lines = [line for line in (result.stderr or result.stdout).splitlines() if line][-8:]
    details = " | ".join(tail_lines) if tail_lines else "No stderr/stdout details."
    return f"coverage json failed (exit={result.returncode}). {details}"


def _load_coverage_snapshot(
    coverage_json_path: Path,
    repo_root: Path,
    low_n: int = 10,
) -> tuple[float, int, list[dict[str, object]]] | None:
    if not coverage_json_path.exists():
        return None
    payload = json.loads(coverage_json_path.read_text(encoding="utf-8"))
    totals = dict(payload.get("totals", {}))
    files_payload = dict(payload.get("files", {}))

    pct_raw = totals.get("percent_covered")
    if pct_raw is None:
        return None
    coverage_pct = round(float(pct_raw), 3)

    rows: list[dict[str, object]] = []
    for file_path, raw in files_payload.items():
        item = dict(raw)
        summary = dict(item.get("summary", {}))
        file_pct = float(summary.get("percent_covered", 0.0))
        num_statements = int(summary.get("num_statements", 0))
        covered_lines = int(summary.get("covered_lines", 0))
        if num_statements <= 0:
            continue
        rel = _rel(Path(str(file_path)), repo_root)
        rows.append(
            {
                "file": rel,
                "coverage_pct": round(file_pct, 3),
                "covered_lines": covered_lines,
                "num_statements": num_statements,
            }
        )

    rows.sort(key=lambda r: (float(r["coverage_pct"]), str(r["file"])))
    return coverage_pct, len(rows), rows[:low_n]


def decide_gate(
    current: Snapshot,
    baseline: Snapshot,
    thresholds: GateThresholds,
    coverage_required: bool,
) -> GateDecision:
    notes: list[str] = []

    deltas = {
        "avg_cc": round(current.avg_cc - baseline.avg_cc, 3),
        "p95_cc": round(current.p95_cc - baseline.p95_cc, 3),
        "d_or_worse_blocks": current.d_or_worse_blocks - baseline.d_or_worse_blocks,
        "f_blocks": current.f_blocks - baseline.f_blocks,
        "parse_error_files": len(current.parse_error_files) - len(baseline.parse_error_files),
    }
    if current.coverage_pct is not None and baseline.coverage_pct is not None:
        deltas["coverage_pct"] = round(current.coverage_pct - baseline.coverage_pct, 3)
    elif current.coverage_pct is not None and baseline.coverage_pct is None:
        notes.append("Coverage baseline is missing; run with --refresh-baseline to start coverage regression tracking.")

    base_blocks = {
        (str(b["file"]), str(b["name"]), int(b["line"])): (float(b["complexity"]), str(b["rank"]))
        for b in baseline.blocks
    }
    current_blocks = {
        (str(b["file"]), str(b["name"]), int(b["line"])): (float(b["complexity"]), str(b["rank"]))
        for b in current.blocks
    }

    significant_regressions: list[dict[str, object]] = []
    if base_blocks and current_blocks:
        for key, (cur_cc, cur_rank) in current_blocks.items():
            if key not in base_blocks:
                continue
            base_cc, base_rank = base_blocks[key]
            cc_delta = round(cur_cc - base_cc, 3)
            rank_worsened = _rank_value(cur_rank) > _rank_value(base_rank)
            if cc_delta >= thresholds.max_block_cc_increase and rank_worsened:
                significant_regressions.append(
                    {
                        "file": key[0],
                        "name": key[1],
                        "line": key[2],
                        "baseline_cc": base_cc,
                        "current_cc": cur_cc,
                        "delta_cc": cc_delta,
                        "baseline_rank": base_rank,
                        "current_rank": cur_rank,
                    }
                )
    else:
        notes.append("Block-level regression check skipped (baseline lacks block detail).")

    reasons: list[str] = []
    warnings: list[str] = []

    if deltas["avg_cc"] > thresholds.max_avg_cc_increase:
        reasons.append(
            f"Average CC increased by {deltas['avg_cc']} (> {thresholds.max_avg_cc_increase})."
        )
    elif deltas["avg_cc"] > 0:
        warnings.append(f"Avg CC +{deltas['avg_cc']} (within tolerance {thresholds.max_avg_cc_increase}).")

    if deltas["p95_cc"] > thresholds.max_p95_cc_increase:
        reasons.append(
            f"P95 CC increased by {deltas['p95_cc']} (> {thresholds.max_p95_cc_increase})."
        )
    elif deltas["p95_cc"] > 0:
        warnings.append(f"P95 CC +{deltas['p95_cc']} (within tolerance {thresholds.max_p95_cc_increase}).")

    if deltas["d_or_worse_blocks"] > thresholds.max_d_or_worse_increase:
        reasons.append(
            "Count of D/E/F blocks increased by "
            f"{deltas['d_or_worse_blocks']} (> {thresholds.max_d_or_worse_increase})."
        )
    elif deltas["d_or_worse_blocks"] > 0:
        warnings.append(f"D/E/F block count +{deltas['d_or_worse_blocks']} (within tolerance {thresholds.max_d_or_worse_increase}).")

    if deltas["f_blocks"] > thresholds.max_f_increase:
        reasons.append(
            f"Count of F blocks increased by {deltas['f_blocks']} (> {thresholds.max_f_increase})."
        )
    elif deltas["f_blocks"] > 0:
        warnings.append(f"F block count +{deltas['f_blocks']} (within tolerance {thresholds.max_f_increase}).")

    if len(significant_regressions) > thresholds.max_significant_block_regressions:
        reasons.append(
            "Significant per-block regressions: "
            f"{len(significant_regressions)} (> {thresholds.max_significant_block_regressions})."
        )
    elif significant_regressions:
        warnings.append(f"Per-block regressions: {len(significant_regressions)} (within tolerance {thresholds.max_significant_block_regressions}).")

    if deltas["parse_error_files"] > 0:
        reasons.append(
            f"Parse-error files increased by {deltas['parse_error_files']} (baseline comparison)."
        )
    if coverage_required and current.coverage_pct is None:
        reasons.append("Coverage data missing in current run.")
    if current.coverage_error:
        reasons.append(current.coverage_error)
    if current.coverage_pct is not None and current.coverage_pct < thresholds.min_coverage_pct:
        reasons.append(
            f"Coverage is {current.coverage_pct}% (< min {thresholds.min_coverage_pct}%)."
        )
    if current.coverage_pct is None and baseline.coverage_pct is not None:
        reasons.append("Coverage baseline exists, but current coverage is unavailable.")
    if (
        current.coverage_pct is not None
        and baseline.coverage_pct is not None
    ):
        drop = round(baseline.coverage_pct - current.coverage_pct, 3)
        if drop > thresholds.max_coverage_drop:
            reasons.append(
                f"Coverage dropped by {drop} (> {thresholds.max_coverage_drop})."
            )
        elif drop > 0:
            warnings.append(f"Coverage -0{drop}% (within tolerance {thresholds.max_coverage_drop}%).")

    notes.extend(f"⚠️ WARNING: {w}" for w in warnings)

    return GateDecision(
        status="FAIL" if reasons else "PASS",
        reasons=reasons,
        deltas=deltas,
        significant_regressions=sorted(
            significant_regressions,
            key=lambda r: (float(r["delta_cc"]), str(r["file"]), int(r["line"])),
            reverse=True,
        )[:20],
        notes=notes,
    )


def _snapshot_from_json(payload: dict[str, object]) -> Snapshot:
    return Snapshot(
        schema_version=int(payload.get("schema_version", 1)),
        generated_at_utc=str(payload["generated_at_utc"]),
        paths=[str(x) for x in payload.get("paths", [])],
        python_files=int(payload["python_files"]),
        total_loc=int(payload["total_loc"]),
        total_sloc=int(payload["total_sloc"]),
        total_blank=int(payload["total_blank"]),
        avg_mi=float(payload["avg_mi"]),
        avg_cc=float(payload["avg_cc"]),
        p95_cc=float(payload["p95_cc"]),
        counts_by_rank={k: int(v) for k, v in dict(payload["counts_by_rank"]).items()},
        d_or_worse_blocks=int(payload["d_or_worse_blocks"]),
        f_blocks=int(payload["f_blocks"]),
        parse_error_files=[str(x) for x in payload.get("parse_error_files", [])],
        blocks=[dict(x) for x in list(payload.get("blocks", []))],
        top_blocks=[dict(x) for x in list(payload.get("top_blocks", []))],
        coverage_pct=float(payload["coverage_pct"]) if payload.get("coverage_pct") is not None else None,
        coverage_files=int(payload.get("coverage_files", 0)),
        low_coverage_files=[dict(x) for x in list(payload.get("low_coverage_files", []))],
        coverage_error=str(payload["coverage_error"]) if payload.get("coverage_error") else None,
        coverage_source=str(payload["coverage_source"]) if payload.get("coverage_source") else None,
    )


def render_report(current: Snapshot, baseline: Snapshot | None, gate: GateDecision | None, thresholds: GateThresholds) -> str:
    gate_status = gate.status if gate else "NO_BASELINE"
    lines: list[str] = []
    lines.append("# Code Quality Gate Report")
    lines.append("")
    lines.append(f"Generated at (UTC): {current.generated_at_utc}")
    lines.append(f"Scope: {', '.join(current.paths)}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(f"QUALITY_GATE: {gate_status}")
    if gate:
        if gate.reasons:
            lines.append("")
            lines.append("Reasons:")
            for reason in gate.reasons:
                lines.append(f"- {reason}")
        else:
            lines.append("")
            lines.append("Reasons:")
            lines.append("- No significant regression vs baseline.")
    else:
        lines.append("")
        lines.append("Reasons:")
        lines.append("- Baseline not found. Run with --refresh-baseline once.")
    lines.append("")

    lines.append("## Current Snapshot")
    lines.append("")
    lines.append(f"- Python files: {current.python_files}")
    lines.append(f"- LOC: {current.total_loc} (SLOC: {current.total_sloc}, Blank: {current.total_blank})")
    lines.append(f"- Avg MI: {current.avg_mi}")
    lines.append(f"- Avg CC: {current.avg_cc}")
    lines.append(f"- P95 CC: {current.p95_cc}")
    lines.append(
        "- Rank counts: "
        + ", ".join(f"{k}={v}" for k, v in current.counts_by_rank.items())
    )
    lines.append(f"- D/E/F blocks: {current.d_or_worse_blocks}")
    lines.append(f"- F blocks: {current.f_blocks}")
    lines.append(f"- Parse-error files: {len(current.parse_error_files)}")
    lines.append(
        f"- Coverage: {current.coverage_pct if current.coverage_pct is not None else 'N/A'}%"
    )
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append(
        f"- Total line coverage: {current.coverage_pct if current.coverage_pct is not None else 'N/A'}%"
    )
    lines.append(f"- Files measured: {current.coverage_files}")
    if current.coverage_source:
        lines.append(f"- Coverage source: {current.coverage_source}")
    if current.coverage_error:
        lines.append(f"- Coverage status: ERROR ({current.coverage_error})")
    else:
        lines.append("- Coverage status: OK")
    lines.append("")

    if current.low_coverage_files:
        lines.append("### Lowest Coverage Files")
        lines.append("")
        lines.append("| Coverage % | Covered/Statements | File |")
        lines.append("|---:|---:|---|")
        for row in current.low_coverage_files:
            lines.append(
                f"| {row['coverage_pct']} | {row['covered_lines']}/{row['num_statements']} | {row['file']} |"
            )
        lines.append("")

    if current.parse_error_files:
        lines.append("## Parse Errors")
        lines.append("")
        for path in current.parse_error_files[:20]:
            lines.append(f"- {path}")
        if len(current.parse_error_files) > 20:
            lines.append(f"- ... and {len(current.parse_error_files) - 20} more")
        lines.append("")

    if baseline and gate:
        lines.append("## Baseline Delta")
        lines.append("")
        lines.append(f"- Baseline timestamp: {baseline.generated_at_utc}")
        lines.append(f"- Delta avg_cc: {gate.deltas['avg_cc']}")
        lines.append(f"- Delta p95_cc: {gate.deltas['p95_cc']}")
        lines.append(f"- Delta D/E/F blocks: {gate.deltas['d_or_worse_blocks']}")
        lines.append(f"- Delta F blocks: {gate.deltas['f_blocks']}")
        lines.append(f"- Delta parse-error files: {gate.deltas['parse_error_files']}")
        if "coverage_pct" in gate.deltas:
            lines.append(f"- Delta coverage_pct: {gate.deltas['coverage_pct']}")
        lines.append("")

        if gate.notes:
            lines.append("Notes:")
            for note in gate.notes:
                lines.append(f"- {note}")
        lines.append("")

    lines.append("## Gate Thresholds")
    lines.append("")
    lines.append(f"- max_avg_cc_increase: {thresholds.max_avg_cc_increase}")
    lines.append(f"- max_p95_cc_increase: {thresholds.max_p95_cc_increase}")
    lines.append(f"- max_d_or_worse_increase: {thresholds.max_d_or_worse_increase}")
    lines.append(f"- max_f_increase: {thresholds.max_f_increase}")
    lines.append(f"- max_block_cc_increase: {thresholds.max_block_cc_increase}")
    lines.append(
        "- max_significant_block_regressions: "
        f"{thresholds.max_significant_block_regressions}"
    )
    lines.append(f"- min-coverage-pct: {thresholds.min_coverage_pct}")
    lines.append(f"- max-coverage-drop: {thresholds.max_coverage_drop}")
    lines.append("")

    if gate and gate.significant_regressions:
        lines.append("## Significant Block Regressions")
        lines.append("")
        lines.append("| Delta CC | Rank | Location |")
        lines.append("|---:|---|---|")
        for row in gate.significant_regressions:
            lines.append(
                f"| {row['delta_cc']} | {row['baseline_rank']} -> {row['current_rank']} | "
                f"{row['file']}:{row['line']} {row['name']} |"
            )
        lines.append("")

    lines.append("## Top Complex Blocks")
    lines.append("")
    lines.append("| Rank | CC | Location |")
    lines.append("|---|---:|---|")
    for row in current.top_blocks:
        lines.append(
            f"| {row['rank']} | {row['complexity']} | {row['file']}:{row['line']} {row['name']} |"
        )
    lines.append("")

    lines.append("## Copilot Summary")
    lines.append("")
    warnings_in_notes = gate and [n for n in gate.notes if n.startswith("⚠️")]
    if gate_status == "PASS" and warnings_in_notes:
        lines.append("- Quality gate passed with warnings: small regressions detected (within tolerance).")
        lines.append("- Review warnings above; refactor if the trend continues.")
    elif gate_status == "PASS":
        lines.append("- Quality gate passed: no significant complexity or coverage regression detected.")
    elif gate_status == "FAIL":
        lines.append("- Quality gate failed: significant regression detected.")
        lines.append("- Refactor the listed high-complexity blocks before merge.")
    else:
        lines.append("- No baseline yet. Establish baseline first, then enforce regression gate.")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate complexity report and regression-aware quality gate.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--paths", nargs="+", default=["src", "tests"], help="Paths to scan.")
    parser.add_argument(
        "--baseline-path",
        default="reports/quality/complexity_baseline.json",
        help="Baseline snapshot JSON path.",
    )
    parser.add_argument(
        "--stats-path",
        default="reports/quality/complexity_current.json",
        help="Current snapshot JSON output path.",
    )
    parser.add_argument(
        "--report-path",
        default="reports/quality/complexity_report.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--refresh-baseline",
        action="store_true",
        help="Write current snapshot as new baseline and exit PASS.",
    )
    _d = GateThresholds()  # single source of truth for defaults
    parser.add_argument("--max-avg-cc-increase", type=float, default=_d.max_avg_cc_increase)
    parser.add_argument("--max-p95-cc-increase", type=float, default=_d.max_p95_cc_increase)
    parser.add_argument("--max-d-or-worse-increase", type=int, default=_d.max_d_or_worse_increase)
    parser.add_argument("--max-f-increase", type=int, default=_d.max_f_increase)
    parser.add_argument("--max-block-cc-increase", type=float, default=_d.max_block_cc_increase)
    parser.add_argument("--max-significant-block-regressions", type=int, default=_d.max_significant_block_regressions)
    parser.add_argument("--min-coverage-pct", type=float, default=_d.min_coverage_pct)
    parser.add_argument("--max-coverage-drop", type=float, default=_d.max_coverage_drop)
    parser.add_argument(
        "--coverage-command",
        default="pytest --cov=src/felvi_games --cov-report=json:reports/quality/coverage_current.json -q",
        help="Command used to collect coverage JSON.",
    )
    parser.add_argument(
        "--coverage-json-path",
        default="reports/quality/coverage_current.json",
        help="Coverage JSON path produced by --coverage-command.",
    )
    parser.add_argument(
        "--coverage-data-file",
        default=".coverage",
        help="Coverage data file used for fast JSON export when fresh.",
    )
    parser.add_argument(
        "--coverage-cache-max-age-minutes",
        type=float,
        default=20.0,
        help="Reuse coverage data file when it is newer than this many minutes.",
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Skip coverage collection and coverage gate checks.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status when gate fails or baseline is missing.",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _is_strictly_better(current: Snapshot, baseline: Snapshot) -> bool:
    """Return True only if current is at least as good on every metric and
    strictly better on at least one — no metric may have worsened."""
    worse = (
        current.avg_cc > baseline.avg_cc
        or current.p95_cc > baseline.p95_cc
        or current.d_or_worse_blocks > baseline.d_or_worse_blocks
        or current.f_blocks > baseline.f_blocks
        or len(current.parse_error_files) > len(baseline.parse_error_files)
        or (
            baseline.coverage_pct is not None
            and (current.coverage_pct is None or current.coverage_pct < baseline.coverage_pct)
        )
    )
    if worse:
        return False
    improved = (
        current.avg_cc < baseline.avg_cc
        or current.p95_cc < baseline.p95_cc
        or current.d_or_worse_blocks < baseline.d_or_worse_blocks
        or current.f_blocks < baseline.f_blocks
        or len(current.parse_error_files) < len(baseline.parse_error_files)
        or (
            current.coverage_pct is not None
            and baseline.coverage_pct is not None
            and current.coverage_pct > baseline.coverage_pct
        )
    )
    return improved


def main() -> int:
    args = parse_args()

    repo_root = Path(args.repo_root).resolve()
    scan_paths = [(repo_root / p).resolve() for p in args.paths]
    baseline_path = (repo_root / args.baseline_path).resolve()
    stats_path = (repo_root / args.stats_path).resolve()
    report_path = (repo_root / args.report_path).resolve()

    thresholds = GateThresholds(
        max_avg_cc_increase=float(args.max_avg_cc_increase),
        max_p95_cc_increase=float(args.max_p95_cc_increase),
        max_d_or_worse_increase=int(args.max_d_or_worse_increase),
        max_f_increase=int(args.max_f_increase),
        max_block_cc_increase=float(args.max_block_cc_increase),
        max_significant_block_regressions=int(args.max_significant_block_regressions),
        min_coverage_pct=float(args.min_coverage_pct),
        max_coverage_drop=float(args.max_coverage_drop),
    )

    current = build_snapshot(repo_root, scan_paths)

    coverage_required = not bool(args.no_coverage)
    if coverage_required:
        coverage_json_path = (repo_root / args.coverage_json_path).resolve()
        coverage_data_path = (repo_root / args.coverage_data_file).resolve()
        coverage_error: str | None = None
        age_minutes = _coverage_age_minutes(coverage_data_path)

        reused_cache = (
            age_minutes is not None
            and age_minutes <= float(args.coverage_cache_max_age_minutes)
        )

        if reused_cache:
            coverage_error = _coverage_json_from_data_file(
                repo_root,
                coverage_data_path,
                coverage_json_path,
            )
            if coverage_error is None:
                current.coverage_source = (
                    f"cached {args.coverage_data_file} ({round(age_minutes or 0.0, 2)} min old)"
                )
        else:
            coverage_error = _run_coverage_command(repo_root, str(args.coverage_command))
            if coverage_error is None:
                current.coverage_source = "fresh test run via --coverage-command"

        # Fallback: cache export failed, try full coverage command once.
        if reused_cache and coverage_error is not None:
            coverage_error = _run_coverage_command(repo_root, str(args.coverage_command))
            if coverage_error is None:
                current.coverage_source = "fresh test run via --coverage-command (cache fallback)"

        coverage_snapshot = _load_coverage_snapshot(coverage_json_path, repo_root)
        if coverage_snapshot is not None:
            cov_pct, cov_files, low_files = coverage_snapshot
            current.coverage_pct = cov_pct
            current.coverage_files = cov_files
            current.low_coverage_files = low_files
            if current.coverage_source is None:
                current.coverage_source = "coverage json import"
        else:
            current.coverage_error = (
                coverage_error
                or f"Coverage JSON not found or unreadable: {coverage_json_path}"
            )
        if coverage_error and current.coverage_error is None:
            current.coverage_error = coverage_error

    _write_json(stats_path, asdict(current))

    if args.refresh_baseline:
        _write_json(baseline_path, asdict(current))
        report = render_report(current, None, None, thresholds)
        _write_text(report_path, report)
        print("QUALITY_GATE: PASS")
        print(f"Baseline written: {baseline_path}")
        print(f"Report written:   {report_path}")
        return 0

    baseline: Snapshot | None = None
    gate: GateDecision | None = None

    if baseline_path.exists():
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline = _snapshot_from_json(baseline_payload)
        gate = decide_gate(current, baseline, thresholds, coverage_required=coverage_required)
    else:
        gate = None

    report = render_report(current, baseline, gate, thresholds)
    _write_text(report_path, report)

    if gate is None:
        print("QUALITY_GATE: NO_BASELINE")
        print("Hint: run with --refresh-baseline once.")
        return 2 if args.strict else 0

    print(f"QUALITY_GATE: {gate.status}")
    print(f"Report written: {report_path}")

    # Auto-ratchet: if the run passed and the code genuinely improved on every
    # key metric, lock in the better score so future runs are held to the new bar.
    if gate.status == "PASS" and baseline is not None and _is_strictly_better(current, baseline):
        _write_json(baseline_path, asdict(current))
        print("Baseline auto-updated: current scores are strictly better (ratchet).")

    if gate.status == "FAIL" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
