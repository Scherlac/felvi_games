"""
Unused function detector with quality-gate integration.

Scans Python files for functions and class methods that are never referenced
elsewhere in the scanned scope.  Produces a human-readable report and (when
--gate is given) compares against a stored baseline, failing with a non-zero
exit code if the number of unused symbols has *increased*.

Usage:
    # Standalone report
    python tools/find_unused.py

    # Restrict to one file or folder
    python tools/find_unused.py --file src/felvi_games/condition_registry.py

    # Only compare symbols with a given prefix (e.g. private KPI helpers)
    python tools/find_unused.py --prefix _kpi_

    # Quality-gate mode (compare to baseline JSON produced by --save-baseline)
    python tools/find_unused.py --gate --baseline reports/quality/unused_baseline.json

    # Update (ratchet) baseline after confirmed clean-up
    python tools/find_unused.py --save-baseline reports/quality/unused_baseline.json

Exit codes:
    0   – no violations  (or gate passed)
    1   – gate failed (unused count increased above tolerance)
    2   – usage error / file not found
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_SCAN_PATHS: list[str] = ["src/felvi_games", "tests", "tools"]
SKIP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)

# Functions whose names match these prefixes are auto-excluded (always "private")
# but we still report them if they are unreferenced.
_DUNDER_PREFIX = ("__",)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class UnusedSymbol:
    file: str          # repo-relative path
    name: str          # function / method name
    line: int          # definition line
    end_line: int      # definition end line
    kind: str          # "function" | "method"
    owner: str | None  # enclosing class name (for methods)

    def display(self) -> str:
        location = f"{self.file}:{self.line}"
        owner_str = f" (in {self.owner})" if self.owner else ""
        return f"{location}  {self.kind}  {self.name}{owner_str}"


@dataclass
class UnusedReport:
    generated_at_utc: str
    scanned_paths: list[str]
    python_files: int
    symbols_defined: int
    symbols_unused: int
    prefix_filter: str | None
    unused: list[dict]          # list of UnusedSymbol as dicts


@dataclass
class GateThresholds:
    max_unused_increase: int = 0   # gate fails if unused count goes up by more than this


@dataclass
class GateDecision:
    status: str                    # "PASS" | "FAIL"
    delta: int                     # current - baseline unused count
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _iter_py_files(roots: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            rp = root.resolve()
            if rp not in seen:
                seen.add(rp)
                result.append(rp)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            rp = path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            result.append(rp)
    return result


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# AST analysis — collect definitions and call-site / reference names
# ---------------------------------------------------------------------------

def _collect_definitions(
    tree: ast.AST,
    rel_path: str,
    prefix: str | None,
) -> list[UnusedSymbol]:
    """Walk the AST and return every function / method definition."""
    defs: list[UnusedSymbol] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._class_stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._class_stack.append(node.name)
            self.generic_visit(node)
            self._class_stack.pop()

        def _add(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            name = node.name
            if prefix and not name.startswith(prefix):
                return
            kind = "method" if self._class_stack else "function"
            owner = self._class_stack[-1] if self._class_stack else None
            defs.append(
                UnusedSymbol(
                    file=rel_path,
                    name=name,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    kind=kind,
                    owner=owner,
                )
            )

        visit_FunctionDef = _add         # type: ignore[assignment]
        visit_AsyncFunctionDef = _add    # type: ignore[assignment]

    _Visitor().visit(tree)
    return defs


def _collect_references(tree: ast.AST) -> set[str]:
    """
    Collect every name that appears in a *non-definition* context:
    calls, attribute accesses, variable loads, decorator names, etc.
    This is necessarily over-approximate (no type resolution), but gives
    very good signal for private helpers that are never mentioned.
    """
    refs: set[str] = set()

    class _RefVisitor(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Load, ast.Del)):
                refs.add(node.id)
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            # record the attribute name itself (covers obj.method calls)
            refs.add(node.attr)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            # Also capture bare function calls
            if isinstance(node.func, ast.Name):
                refs.add(node.func.id)
            self.generic_visit(node)

        # Decorators: @register_kpi_param(KPIParamDef(calc_fn=_fn))
        def visit_keyword(self, node: ast.keyword) -> None:
            self.generic_visit(node)

    _RefVisitor().visit(tree)
    return refs


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyse(
    py_files: list[Path],
    repo_root: Path,
    prefix: str | None = None,
) -> tuple[list[UnusedSymbol], int]:
    """
    Return (unused_symbols, total_defined_count).

    Strategy:
    1. Parse every file, collect definitions and references separately.
    2. A symbol is *potentially unused* if its name never appears in any
       reference set across the entire scanned corpus.
    3. Note: this is name-based (not semantic), so a same-named symbol in a
       different module will suppress a false-positive report — which is
       intentional (conservative / low-noise).
    """
    all_defs: list[UnusedSymbol] = []
    all_refs: set[str] = set()

    parse_errors = 0
    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            parse_errors += 1
            continue

        rel = _rel(py_file, repo_root)
        defs = _collect_definitions(tree, rel, prefix)
        all_defs.extend(defs)
        all_refs |= _collect_references(tree)

    # A definition is unused if its name never appears in references across
    # all scanned files.  Exclude the name collected from its *own* definition
    # node (the Name in the def statement itself) — these are already filtered
    # out because _collect_references only picks up Load/Del contexts.
    def_names = {d.name for d in all_defs}
    unused = [d for d in all_defs if d.name not in all_refs]

    return unused, len(all_defs)


# ---------------------------------------------------------------------------
# Evaluation / quality gate
# ---------------------------------------------------------------------------

def evaluate(
    unused: list[UnusedSymbol],
    total_defined: int,
    baseline_path: Path | None,
    thresholds: GateThresholds,
) -> GateDecision:
    """Compare current unused count against a stored baseline."""
    current_count = len(unused)

    if baseline_path is None or not baseline_path.exists():
        return GateDecision(
            status="NO_BASELINE",
            delta=0,
            notes=["No baseline file found — run with --save-baseline to create one."],
        )

    try:
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_count: int = int(payload.get("symbols_unused", 0))
    except Exception as exc:
        return GateDecision(
            status="ERROR",
            delta=0,
            reasons=[f"Could not read baseline: {exc}"],
        )

    delta = current_count - baseline_count
    reasons: list[str] = []
    notes: list[str] = []

    if delta > thresholds.max_unused_increase:
        reasons.append(
            f"Unused symbol count increased by {delta} "
            f"(baseline={baseline_count}, current={current_count}, "
            f"tolerance={thresholds.max_unused_increase})."
        )
        status = "FAIL"
    elif delta > 0:
        notes.append(
            f"Unused symbols +{delta} (within tolerance {thresholds.max_unused_increase})."
        )
        status = "PASS"
    elif delta < 0:
        notes.append(f"Unused symbols reduced by {abs(delta)} — improvement!")
        status = "PASS"
    else:
        status = "PASS"

    return GateDecision(status=status, delta=delta, reasons=reasons, notes=notes)


# ---------------------------------------------------------------------------
# Baseline persistence
# ---------------------------------------------------------------------------

def save_baseline(report: UnusedReport, baseline_path: Path) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "generated_at_utc": report.generated_at_utc,
                "scanned_paths": report.scanned_paths,
                "symbols_defined": report.symbols_defined,
                "symbols_unused": report.symbols_unused,
                "prefix_filter": report.prefix_filter,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Baseline saved → {baseline_path}")


def _remove_unused_functions(
    unused: list[UnusedSymbol],
    repo_root: Path,
    *,
    backup: bool,
) -> int:
    """Remove detected unused top-level functions from source files.

    Safety rules:
    - methods are never removed (only top-level functions)
    - only symbols in scanned files are removed
    - removals are applied from bottom to top per file
    """
    removable = [s for s in unused if s.kind == "function" and s.owner is None]
    by_file: dict[str, list[UnusedSymbol]] = {}
    for sym in removable:
        by_file.setdefault(sym.file, []).append(sym)

    removed = 0
    for rel_path, symbols in by_file.items():
        target = repo_root / Path(rel_path)
        if not target.exists():
            continue

        text = target.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)

        if backup:
            backup_path = target.with_suffix(target.suffix + ".bak")
            backup_path.write_text(text, encoding="utf-8")

        for sym in sorted(symbols, key=lambda s: s.line, reverse=True):
            start = max(1, sym.line)
            end = max(start, sym.end_line)
            # Expand upward to include one preceding blank line for cleaner spacing.
            while start > 1 and lines[start - 2].strip() == "":
                start -= 1
            del lines[start - 1 : end]
            removed += 1

        target.write_text("".join(lines), encoding="utf-8")

    return removed


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_report(
    report: UnusedReport,
    gate: GateDecision | None = None,
    verbose: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("UNUSED SYMBOL REPORT")
    lines.append("=" * 70)
    lines.append(f"Generated : {report.generated_at_utc}")
    lines.append(f"Scanned   : {', '.join(report.scanned_paths)}")
    lines.append(f"Prefix    : {report.prefix_filter or '(all)'}")
    lines.append(f"Files     : {report.python_files}")
    lines.append(f"Defined   : {report.symbols_defined}")
    lines.append(f"Unused    : {report.symbols_unused}")
    lines.append("")

    if report.unused:
        lines.append(f"{'File:Line':<50}  {'Kind':<8}  {'Name'}")
        lines.append("-" * 90)
        for sym_dict in report.unused:
            sym = UnusedSymbol(**sym_dict)
            loc = f"{sym.file}:{sym.line}"
            owner_str = f" (in {sym.owner})" if sym.owner else ""
            lines.append(f"{loc:<50}  {sym.kind:<8}  {sym.name}{owner_str}")
    else:
        lines.append("No unused symbols detected.")

    if gate is not None:
        lines.append("")
        lines.append("-" * 70)
        lines.append(f"QUALITY_GATE: {gate.status}  (delta={gate.delta:+d})")
        for r in gate.reasons:
            lines.append(f"  FAIL  {r}")
        for n in gate.notes:
            lines.append(f"  NOTE  {n}")

    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find unused functions and report against a quality-gate baseline."
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Scan a single file or folder instead of the default paths.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Only consider symbols whose names start with this prefix.",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Enable quality-gate mode: compare against baseline and fail on regression.",
    )
    parser.add_argument(
        "--baseline",
        default="reports/quality/unused_baseline.json",
        help="Path to the baseline JSON file (default: reports/quality/unused_baseline.json).",
    )
    parser.add_argument(
        "--save-baseline",
        metavar="PATH",
        default=None,
        help="Save the current results as a new baseline (ratchet down).",
    )
    parser.add_argument(
        "--max-unused-increase",
        type=int,
        default=0,
        help="Gate fails if unused count rises by more than this (default: 0).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full report as JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional detail in text output.",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove detected unused top-level functions from scanned files.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create .bak backups before applying --remove edits.",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()

    # Determine scan roots
    if args.file:
        scan_roots = [Path(args.file)]
    else:
        scan_roots = [Path(p) for p in DEFAULT_SCAN_PATHS]

    py_files = _iter_py_files(scan_roots)
    if not py_files:
        print("ERROR: no Python files found in the specified paths.", file=sys.stderr)
        sys.exit(2)

    # Analyse
    unused, total_defined = analyse(py_files, repo_root, prefix=args.prefix)

    report = UnusedReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        scanned_paths=[str(r) for r in scan_roots],
        python_files=len(py_files),
        symbols_defined=total_defined,
        symbols_unused=len(unused),
        prefix_filter=args.prefix,
        unused=[asdict(s) for s in unused],
    )

    # Quality gate evaluation
    gate: GateDecision | None = None
    if args.gate:
        thresholds = GateThresholds(max_unused_increase=args.max_unused_increase)
        gate = evaluate(unused, total_defined, Path(args.baseline), thresholds)

    # Output
    if args.json:
        output: dict = asdict(report) if hasattr(report, "__dataclass_fields__") else {}
        output = {
            "generated_at_utc": report.generated_at_utc,
            "scanned_paths": report.scanned_paths,
            "python_files": report.python_files,
            "symbols_defined": report.symbols_defined,
            "symbols_unused": report.symbols_unused,
            "prefix_filter": report.prefix_filter,
            "unused": report.unused,
        }
        if gate:
            output["gate"] = {
                "status": gate.status,
                "delta": gate.delta,
                "reasons": gate.reasons,
                "notes": gate.notes,
            }
        print(json.dumps(output, indent=2))
    else:
        print(render_report(report, gate=gate, verbose=args.verbose))

    # Save baseline (ratchet)
    if args.save_baseline:
        save_baseline(report, Path(args.save_baseline))

    # Optional auto-removal workflow
    if args.remove:
        removed = _remove_unused_functions(unused, repo_root, backup=args.backup)
        print(f"Removed {removed} unused top-level function(s).")

    # Exit code
    if gate and gate.status == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
