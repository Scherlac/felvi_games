#!/usr/bin/env python3
"""Generate a Copilot-friendly code quality report with a regression-aware gate.

The script focuses on complexity regressions relative to a repository baseline.
It allows improvements and small fluctuations, but fails on significant regressions.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
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
    max_avg_cc_increase: float = 0.35
    max_p95_cc_increase: float = 1.25
    max_d_or_worse_increase: int = 3
    max_f_increase: int = 0
    max_block_cc_increase: float = 4.0
    max_significant_block_regressions: int = 1


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
    )


def decide_gate(current: Snapshot, baseline: Snapshot, thresholds: GateThresholds) -> GateDecision:
    deltas = {
        "avg_cc": round(current.avg_cc - baseline.avg_cc, 3),
        "p95_cc": round(current.p95_cc - baseline.p95_cc, 3),
        "d_or_worse_blocks": current.d_or_worse_blocks - baseline.d_or_worse_blocks,
        "f_blocks": current.f_blocks - baseline.f_blocks,
        "parse_error_files": len(current.parse_error_files) - len(baseline.parse_error_files),
    }

    notes: list[str] = []

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
    if deltas["avg_cc"] > thresholds.max_avg_cc_increase:
        reasons.append(
            f"Average CC increased by {deltas['avg_cc']} (> {thresholds.max_avg_cc_increase})."
        )
    if deltas["p95_cc"] > thresholds.max_p95_cc_increase:
        reasons.append(
            f"P95 CC increased by {deltas['p95_cc']} (> {thresholds.max_p95_cc_increase})."
        )
    if deltas["d_or_worse_blocks"] > thresholds.max_d_or_worse_increase:
        reasons.append(
            "Count of D/E/F blocks increased by "
            f"{deltas['d_or_worse_blocks']} (> {thresholds.max_d_or_worse_increase})."
        )
    if deltas["f_blocks"] > thresholds.max_f_increase:
        reasons.append(
            f"Count of F blocks increased by {deltas['f_blocks']} (> {thresholds.max_f_increase})."
        )
    if len(significant_regressions) > thresholds.max_significant_block_regressions:
        reasons.append(
            "Significant per-block regressions: "
            f"{len(significant_regressions)} (> {thresholds.max_significant_block_regressions})."
        )
    if deltas["parse_error_files"] > 0:
        reasons.append(
            f"Parse-error files increased by {deltas['parse_error_files']} (baseline comparison)."
        )

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
    if gate_status == "PASS":
        lines.append("- Quality gate passed: no significant complexity regression detected.")
    elif gate_status == "FAIL":
        lines.append("- Quality gate failed: significant complexity regression detected.")
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
    parser.add_argument("--max-avg-cc-increase", type=float, default=0.35)
    parser.add_argument("--max-p95-cc-increase", type=float, default=1.25)
    parser.add_argument("--max-d-or-worse-increase", type=int, default=3)
    parser.add_argument("--max-f-increase", type=int, default=0)
    parser.add_argument("--max-block-cc-increase", type=float, default=4.0)
    parser.add_argument("--max-significant-block-regressions", type=int, default=1)
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
    )
    if worse:
        return False
    improved = (
        current.avg_cc < baseline.avg_cc
        or current.p95_cc < baseline.p95_cc
        or current.d_or_worse_blocks < baseline.d_or_worse_blocks
        or current.f_blocks < baseline.f_blocks
        or len(current.parse_error_files) < len(baseline.parse_error_files)
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
    )

    current = build_snapshot(repo_root, scan_paths)
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
        gate = decide_gate(current, baseline, thresholds)
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
