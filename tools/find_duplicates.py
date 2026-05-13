"""
Structural duplication detector for achievements.py.

Compares function bodies (ignoring docstrings, comments, and names)
using token-level normalization to surface near-identical implementations.

Usage:
    python tools/find_duplicates.py [--threshold 0.75] [--prefix _rule_]
"""

from __future__ import annotations

import ast
import io
import re
import sys
import textwrap
import tokenize
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

TARGET = Path("src/felvi_games/achievements.py")


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Remove leading docstring from a function body."""
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return body[1:]
    return body


def _body_source(func: ast.FunctionDef, source_lines: list[str]) -> str:
    """Return the raw source of the function body (excluding signature + docstring)."""
    body = _strip_docstring(func.body)
    if not body:
        return ""
    start = body[0].lineno - 1
    end = func.end_lineno  # inclusive
    raw = "\n".join(source_lines[start:end])
    return textwrap.dedent(raw)


# ---------------------------------------------------------------------------
# Token normalization
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"\b[a-zA-Z_]\w*\b")


def _normalize_tokens(code: str) -> str:
    """
    Produce a normalized token string for comparison:
    - collapse all whitespace to single space
    - remove comments
    - keep structural tokens (keywords, operators, punctuation)
    - replace string literals with STR, number literals with NUM
    """
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        parts: list[str] = []
        for tok_type, tok_val, _, _, _ in tokens:
            if tok_type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                            tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
                continue
            if tok_type == tokenize.STRING:
                parts.append("STR")
            elif tok_type == tokenize.NUMBER:
                parts.append("NUM")
            elif tok_type == tokenize.NAME:
                parts.append(tok_val)
            else:
                parts.append(tok_val)
        return " ".join(parts)
    except tokenize.TokenError:
        return code.strip()


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Collect functions
# ---------------------------------------------------------------------------

def collect_functions(source: str, prefix: str | None = None) -> dict[str, tuple[ast.FunctionDef, str, str]]:
    """
    Returns {name: (node, raw_body, normalized_body)} for all matching functions.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    result: dict[str, tuple[ast.FunctionDef, str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if prefix and not node.name.startswith(prefix):
                continue
            raw = _body_source(node, lines)
            norm = _normalize_tokens(raw)
            result[node.name] = (node, raw, norm)
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def find_duplicates(
    source: str,
    prefix: str | None = None,
    threshold: float = 0.70,
) -> list[tuple[str, str, float]]:
    """Return list of (name_a, name_b, similarity) pairs above threshold."""
    funcs = collect_functions(source, prefix)
    names = list(funcs.keys())
    pairs: list[tuple[str, str, float]] = []
    for a, b in combinations(names, 2):
        _, _, norm_a = funcs[a]
        _, _, norm_b = funcs[b]
        sim = _similarity(norm_a, norm_b)
        if sim >= threshold:
            pairs.append((a, b, sim))
    pairs.sort(key=lambda t: t[2], reverse=True)
    return pairs


def diff_bodies(name_a: str, name_b: str, funcs: dict) -> str:
    """Show side-by-side diff of two function bodies."""
    import difflib
    _, raw_a, _ = funcs[name_a]
    _, raw_b, _ = funcs[name_b]
    diff = difflib.unified_diff(
        raw_a.splitlines(),
        raw_b.splitlines(),
        fromfile=name_a,
        tofile=name_b,
        lineterm="",
    )
    return "\n".join(diff)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Find near-duplicate functions in achievements.py")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="Similarity threshold (0–1, default 0.70)")
    parser.add_argument("--prefix", default=None,
                        help="Only compare functions whose names start with this prefix")
    parser.add_argument("--diff", action="store_true",
                        help="Show unified diff for each pair")
    parser.add_argument("--file", default=str(TARGET),
                        help=f"Target file (default: {TARGET})")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    source = path.read_text(encoding="utf-8")
    funcs = collect_functions(source, prefix=args.prefix)
    print(f"Analysing {len(funcs)} functions in {path}")
    print(f"Similarity threshold: {args.threshold:.0%}\n")

    pairs = find_duplicates(source, prefix=args.prefix, threshold=args.threshold)

    if not pairs:
        print("No duplicate pairs found above threshold.")
        return

    print(f"{'Function A':<40} {'Function B':<40} {'Similarity':>10}")
    print("-" * 94)
    for a, b, sim in pairs:
        print(f"{a:<40} {b:<40} {sim:>10.1%}")

    if args.diff:
        for a, b, sim in pairs:
            print(f"\n{'='*70}")
            print(f"DIFF: {a} vs {b}  (similarity {sim:.1%})")
            print("=" * 70)
            print(diff_bodies(a, b, funcs))


if __name__ == "__main__":
    main()
