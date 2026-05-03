from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path


def _load_quality_gate_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "quality_gate_report.py"
    spec = importlib.util.spec_from_file_location("quality_gate_report", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qgr = _load_quality_gate_module()


def _snapshot(*, generated_at: str = "2026-05-03T00:00:00+00:00", avg_cc: float = 5.0, p95_cc: float = 20.0,
              d_or_worse: int = 10, f_blocks: int = 5, parse_errors: list[str] | None = None,
              coverage_pct: float | None = 50.0, coverage_files: int = 1) -> qgr.Snapshot:
    return qgr.Snapshot(
        schema_version=2,
        generated_at_utc=generated_at,
        paths=["src", "tests"],
        python_files=1,
        total_loc=10,
        total_sloc=8,
        total_blank=1,
        avg_mi=50.0,
        avg_cc=avg_cc,
        p95_cc=p95_cc,
        counts_by_rank={"A": 1, "B": 0, "C": 0, "D": 0, "E": 0, "F": f_blocks},
        d_or_worse_blocks=d_or_worse,
        f_blocks=f_blocks,
        parse_error_files=parse_errors or [],
        blocks=[],
        top_blocks=[],
        coverage_pct=coverage_pct,
        coverage_files=coverage_files,
        low_coverage_files=[{"file": "src/a.py", "coverage_pct": coverage_pct or 0.0, "covered_lines": 1, "num_statements": 2}],
        coverage_error=None,
        coverage_source="test",
    )


def test_ratchet_no_improvement_returns_none() -> None:
    baseline = _snapshot()
    current = _snapshot()

    ratcheted, changed = qgr._ratchet_baseline_individual_metrics(current, baseline)

    assert ratcheted is None
    assert changed == []


def test_ratchet_updates_only_improved_complexity_metrics() -> None:
    baseline = _snapshot(generated_at="2026-05-03T08:00:00+00:00", avg_cc=5.0, p95_cc=18.0, d_or_worse=10, f_blocks=5)
    current = _snapshot(generated_at="2026-05-03T08:30:00+00:00", avg_cc=4.5, p95_cc=18.0, d_or_worse=9, f_blocks=4)

    ratcheted, changed = qgr._ratchet_baseline_individual_metrics(current, baseline)

    assert ratcheted is not None
    assert changed == ["avg_cc", "d_or_worse_blocks", "f_blocks"]
    assert ratcheted.generated_at_utc == "2026-05-03T08:30:00+00:00"
    assert ratcheted.avg_cc == 4.5
    assert ratcheted.p95_cc == 18.0
    assert ratcheted.d_or_worse_blocks == 9
    assert ratcheted.f_blocks == 4


def test_ratchet_updates_coverage_only_when_it_improves() -> None:
    baseline = _snapshot(coverage_pct=50.0, coverage_files=3)
    current = _snapshot(coverage_pct=52.5, coverage_files=4)

    ratcheted, changed = qgr._ratchet_baseline_individual_metrics(current, baseline)

    assert ratcheted is not None
    assert "coverage_pct" in changed
    assert ratcheted.coverage_pct == 52.5
    assert ratcheted.coverage_files == 4


def test_ratchet_does_not_lower_coverage_baseline() -> None:
    baseline = _snapshot(coverage_pct=52.5, coverage_files=4)
    current = _snapshot(coverage_pct=50.0, coverage_files=5)

    ratcheted, changed = qgr._ratchet_baseline_individual_metrics(current, baseline)

    assert ratcheted is None
    assert changed == []


def test_main_auto_ratchet_writes_improved_metrics(tmp_path: Path, monkeypatch, capsys) -> None:
    baseline = _snapshot(generated_at="2026-05-03T08:00:00+00:00", avg_cc=5.0, d_or_worse=10, f_blocks=5, coverage_pct=51.0)
    current = _snapshot(generated_at="2026-05-03T08:40:00+00:00", avg_cc=4.8, d_or_worse=9, f_blocks=5, coverage_pct=50.9)

    baseline_path = tmp_path / "baseline.json"
    stats_path = tmp_path / "current.json"
    report_path = tmp_path / "report.md"
    baseline_path.write_text(json.dumps(asdict(baseline), ensure_ascii=False), encoding="utf-8")

    args = argparse.Namespace(
        repo_root=str(tmp_path),
        paths=["src", "tests"],
        baseline_path=baseline_path.name,
        stats_path=stats_path.name,
        report_path=report_path.name,
        refresh_baseline=False,
        max_avg_cc_increase=0.35,
        max_p95_cc_increase=1.25,
        max_d_or_worse_increase=3,
        max_f_increase=0,
        max_block_cc_increase=4.0,
        max_significant_block_regressions=1,
        min_coverage_pct=0.0,
        max_coverage_drop=1.0,
        max_ruff_violations_increase=5,
        max_duplicate_pairs_increase=2,
        max_high_param_increase=2,
        coverage_command="",
        coverage_json_path="coverage.json",
        coverage_data_file=".coverage",
        coverage_cache_max_age_minutes=10.0,
        no_coverage=True,
        strict=False,
    )

    monkeypatch.setattr(qgr, "parse_args", lambda: args)
    monkeypatch.setattr(qgr, "build_snapshot", lambda repo_root, scan_paths: current)
    monkeypatch.setattr(qgr, "render_report", lambda current, baseline, gate, thresholds: "ok")
    monkeypatch.setattr(
        qgr,
        "decide_gate",
        lambda current, baseline, thresholds, coverage_required: qgr.GateDecision(
            status="PASS", reasons=[], deltas={}, significant_regressions=[], notes=[]
        ),
    )

    exit_code = qgr.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Baseline auto-updated (per-metric ratchet): avg_cc, d_or_worse_blocks" in output

    updated = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert float(updated["avg_cc"]) == 4.8
    assert int(updated["d_or_worse_blocks"]) == 9
    assert int(updated["f_blocks"]) == 5
    assert float(updated["coverage_pct"]) == 51.0
