# Award Evaluation Architecture Analysis

**Date:** 2026-05-10  
**Scope:** achievements.py, condition_registry.py, progress_check.py, cli.py

---

## Overview

Award evaluation is still centralized, but architecture has progressed from the original static-rule + dynamic-rule split.

Current model:

1. **Condition-driven engine** in achievements.py calling condition_registry.
2. **Shared status/progress APIs** for CLI and UI consumers.
3. **Shared "awardable now" dry-run API** that uses the same core decision path.
4. **Time-of-day review and fix tooling** to align generated medal names with condition semantics.

Target model (in progress):

1. **KPI parameter-first evaluation**: condition evaluators are built on reusable parameter calculators.
2. **Unified evaluator/count path**: the same KPI calculator feeds both `evaluator` and `count_fn` progress reporting.
3. **Lazy relevant-only execution**: only condition branches that are reached are evaluated (AND short-circuit).
4. **Shared cached stats during medal pass**: repeated condition fragments across medals reuse one computed KPI value.

---

## What Has Been Completed

### 1) Static rule registry split removed from runtime path

The older `SZABALY_REGISTRY` / `_rule_*` architecture is no longer the core runtime path.

- check_new_medals() evaluates `erem.condition` with `_eval_dynamic_condition()`.
- Condition types and SQL evaluator/count logic are delegated to condition_registry.

Status: **Completed**.

### 2) Shared dynamic progress helper added

`evaluate_dynamic_condition_progress()` now provides:

- fulfillment (`ok`)
- progress (`current`, `target`)
- normalized `valid_from`

CLI and UI call this shared helper instead of duplicating parse/eval/count logic.

Status: **Completed**.

### 3) Shared "next award basis" API added

`get_next_award_basis()` now centralizes the payload basis used for "what to advertise next":

- stats
- close medals
- earned count

Used from CLI and daily insight path.

Status: **Completed**.

### 4) Shared "awardable now" API added

`get_awardability_now()` wraps `check_new_medals(... dry_run=True, details=...)` and returns:

- awardable_now
- would_repeat_now

This made it explicit that "close" and "awardable now" are separate signals.

Status: **Completed**.

### 5) window_hours behavior corrected

`_window_bounds()` now combines anchors correctly:

- rolling window (`now - window_hours`)
- `valid_from` floor

It uses the stricter bound and is simulation-aware via `_sim_now()`.

Status: **Completed**.

### 6) Time-of-day normalization + review tooling

Added in progress_check + CLI:

- normalize_medal_candidate_time_gate()
- review_time_gate_alignment()
- CLI switches:
  - `--review-time-gating`
  - `--review-time-gating-llm`
  - `--review-time-gating-fix`
  - `--review-time-gating-interactive`

This closes the gap where names like "Reggeli" / "Esti" had no before/after gate.

Status: **Completed**.

### 7) Conditions CLI progress bar improved

`felvi medals --conditions` progress bars are now log-scaled to avoid extremely long terminal lines on large targets.

Status: **Completed**.

### 8) KPI parameter registry + shared cache (phase 1)

Implemented in `condition_registry.py` + `achievements.py`:

- Added `KPIParamDef` registry with explicit parameter calculators.
- Added `kpi_parameter_value(...)` session-local cache keyed by:
  - user
  - KPI name
  - time bounds (`cutoff`, `upper`)
  - KPI-specific condition fields (for example `hour`, `subject`, interaction filters)
- Refactored high-traffic condition types to use KPI calculators for both evaluate and progress count paths:
  - `feladat_count`
  - `helyes_count`
  - `pont_sum`
  - `villam`
  - `feladat_subject`
  - `before_hour`
  - `after_hour`
  - `session_count`
  - `interakcio_count`
  - `interakcio_exists`
- `check_new_medals()` now runs rule checks with one shared SQLAlchemy Session, so repeated KPI queries can be reused across medals.

Status: **Started (Phase 1 done)**.

---

## Current Implementations (As-Is)

### 1) Main orchestration: check_new_medals()

Responsibilities:

1. Load catalog (global + private targeted medals).
2. Apply eligibility filters (already earned, cooldown, no-condition).
3. Evaluate condition through `_eval_dynamic_condition()`.
4. Grant, or in dry-run classify into awardable_now / would_repeat.

Still sizable and multi-responsibility, but no longer split across static/dynamic rule systems.

### 2) Condition evaluation dispatch

`_eval_dynamic_condition()` and `_count_dynamic_condition()` in achievements call into condition_registry specs.

condition_registry now owns:

- condition schema (ParamSpec)
- parameter validation/coercion
- evaluator function
- count function

New in-progress layer:

- KPI parameter definitions + cached KPI calculators used by both evaluator and count paths.

### 3) Simulation path

`simulate_medal_rules()` remains available, but still differs from check_new_medals semantics.

Notably, it does not apply all orchestration filters and repeatability semantics from check_new_medals.

---

## Open Items (Progress Check Still Open)

### A) Close-medal estimator remains heuristic and hard-coded

`estimate_close_medals()` in progress_check is still a manually curated list of medal IDs and formulas.

Impact:

- Fast and interpretable
- But not fully data-driven from registry definitions

Priority: **High** for long-term maintainability.

### A2) get_user_stats is still outside KPI parameter registry

`get_user_stats()` currently computes trend/pattern/event blocks directly with dedicated queries.

Impact:

- Works correctly today
- But not yet aligned with the new KPI parameter interface

Priority: **High** for unification.

### B) Simulation and runtime path divergence

`simulate_medal_rules()` does not fully mirror check_new_medals filtering/cooldown/fresh-signal semantics.

Impact:

- CLI simulation can disagree with runtime grant behavior

Priority: **High** if simulation is used for diagnostics or policy checks.

### C) check_new_medals still does multiple concerns

It still combines filtering, evaluation, dry-run classification, and grant persistence.

Priority: **Medium** (refactor for readability/test isolation).

### D) No fully unified registry abstraction for all external consumers

Engine runtime uses condition_registry well, but "close medals" and some reporting flows are still partially custom.

Priority: **Medium**.

---

## Updated Modularity Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| Centralization | ✅ Good | Runtime awarding path is centralized in achievements.py |
| Condition typing/validation | ✅ Improved | ParamSpec validation in condition_registry |
| Shared evaluation APIs | ✅ Improved | evaluate_dynamic_condition_progress, get_next_award_basis, get_awardability_now |
| Time-of-day policy tooling | ✅ Improved | Review/fix/interactive CLI flow implemented |
| Code reuse | ⚠️ Mixed | Runtime paths improved, but close estimator remains heuristic |
| Simulation fidelity | ❌ Open | simulate_medal_rules still diverges from check_new_medals semantics |
| Single responsibility | ⚠️ Mixed | check_new_medals still broad but cleaner than before |

---

## Recommended Next Steps

### High Priority

1. Align simulate_medal_rules with check_new_medals decision policy (or deprecate one path).
2. Replace hard-coded estimate_close_medals rules with a registry-driven progress estimator where possible.
3. Continue KPI migration for remaining condition types (streak/session-special cases) and route close-medal progress through the same KPI-backed path.
4. Migrate `get_user_stats()` trend/pattern/event aggregations to named KPI parameters where practical.

### Medium Priority

1. Split check_new_medals into explicit pipeline helpers:
   - eligibility filter
   - condition evaluation
   - result classification (new vs repeat)
   - grant persistence

2. Add targeted tests for awardability_now vs close_medals consistency contracts.
3. Add KPI-cache hit/miss telemetry for architecture validation under realistic catalogs.

---

## Summary

The architecture is no longer in the original fragmented state described by the first draft.

Big wins completed:

1. Runtime condition evaluation standardized through condition_registry.
2. CLI/UI now consume shared award/progress APIs.
3. Time-of-day normalization and interactive review/fix workflow is in place.

Remaining open work is mainly about:

1. simulation fidelity,
2. completing KPI unification for stats and close-medal estimation,
3. reducing hard-coded close-medal heuristics,
4. further modularizing orchestration internals.

---

## Iteration Log: Quality Gate and Cleanup (2026-05-13)

This section tracks incremental quality work and intentionally avoids a one-shot refactor.

### Iteration 1 Baseline

Commands executed:

1. `python tools/quality_gate_report.py`
2. `python tools/find_unused.py`
3. `ruff check src/felvi_games tools tests`

Observed gate outcome:

- `QUALITY_GATE: FAIL`
- Regression deltas were reported for ruff, duplicate pairs, high-parameter functions, and unused functions.

### Iteration 1a Result (After Tooling Fix)

Applied:

1. `tools/quality_gate_report.py` import fallback for `find_unused.py`
2. compatibility guard for `max_unused_function_increase` when tests monkeypatch `parse_args()`

Validation:

1. `pytest tests/test_quality_gate_report.py -q` -> passed
2. `python tools/quality_gate_report.py` -> coverage command now runs successfully

Current gate still fails due non-tooling metrics:

- ruff violations delta
- duplicate pair delta
- high-parameter function delta
- unused function delta

### Important Interpretation Note (Unused Detection)

The current unused-symbol detector is AST-name based and does not model decorator-based runtime wiring.
This creates false positives for:

- Typer command functions (`@app.command(...)`) in `cli.py`
- pytest test functions/methods (`test_*`) discovered by pytest, not by in-code calls

Result: removal decisions must be manually reviewed; do not bulk-delete from the report output.

### Safe Candidate Buckets (Review-First)

1. **Likely false positives, keep**
  - CLI command handlers in `cli.py`
  - Test functions/methods under `tests/`

2. **Potential real candidates, review in code**
  - internal helpers in `achievements.py` flagged as unused
  - helper methods/functions in `condition_registry.py` that no longer have callsites after KPI migration
  - threshold helpers in `kpi_registry.py` (`_kpi_total_count_gt`, `_kpi_total_count_gte`) if no callsites remain

Reviewed in this iteration (grep/callsite check):

1. likely removable after a focused test run:
  - `src/felvi_games/achievements.py`: `_nap`, `_has_new_attempt_after`, `_repeatable_has_fresh_signal`
  - `src/felvi_games/kpi_registry.py`: `_kpi_total_count_gt`, `_kpi_total_count_gte`

2. likely public API helpers, keep unless formally deprecating API:
  - `src/felvi_games/condition_registry.py`: `all_conditions`, `advertise_all`, `eval_conditions`, `condition_count`

### Iteration 2 Result (2026-05-13)

Applied:

1. Removed 3 confirmed dead helpers from `achievements.py`: `_nap`, `_has_new_attempt_after`, `_repeatable_has_fresh_signal`
2. Removed 2 confirmed dead helpers from `kpi_registry.py`: `_kpi_total_count_gt`, `_kpi_total_count_gte`
3. Fixed `condition_registry.py` lint: removed unused `sqlalchemy.select` import, restored `KPI_ENGINE as _KPI_ENGINE` with `# noqa: F401` (required for test access via module attribute), sorted imports
4. Fixed `kpi_registry.py` lint: `Callable` moved from `typing` to `collections.abc` (UP035), removed quoted type annotations on `_kpi_play_days`, `_kpi_max_correct_streak`, `_kpi_perfect_session_count` (UP037 × 9), sorted imports
5. Fixed `progress_check.py` lint: 6 B009 (`getattr` with constant) auto-fixed, B007 loop variable `segitseg_kert` → `_segitseg_kert` manually fixed
6. Fixed 5 auto-fixable I001/UP035 violations in `tests/test_achievements_dynamic_conditions.py`, `tools/find_duplicates.py`, `tools/find_unused.py`
7. Fixed baseline inconsistency: `d_or_worse_blocks` stored as 17 in baseline but D+E+F counts summed to 18 → corrected to 18

Validation:
- `pytest tests/ -q` → 227 passed
- `python tools/quality_gate_report.py` → gate still FAIL but reduced regressions

Gate status after Iteration 2:

| Metric | Delta | Status |
|--------|-------|--------|
| avg CC | -0.037 | ✅ ok |
| F blocks | 0 | ✅ ok |
| D/E/F | 0 | ✅ ok (fixed baseline inconsistency) |
| ruff | 0 | ✅ ok (was +22 in Iteration 1) |
| coverage | +1.53 | ✅ ok |
| dup pairs | +5 | ❌ pre-existing |
| hi-param | +5 | ❌ pre-existing |
| unused | +102 | ❌ pre-existing (mostly false positives) |

Remaining regression causes (for next iteration):
- **dup pairs +5**: structural clones in the codebase — requires deduplication refactoring
- **hi-param +5**: functions with >5 params — requires interface simplification
- **unused +102**: 102 symbols above baseline count — mostly false positives (CLI command handlers, test functions, public API helpers); real removals require per-file review

### Iteration 3 Result (2026-05-13)

Applied:

1. Improved `tools/find_unused.py` false-positive handling:
  - decorator-registered functions are now treated as implicitly referenced
  - supported decorator attrs: `command`, `callback`, `fixture`, `mark`
  - dunder methods are skipped from candidate definitions
2. Removed 2 confirmed dead helpers:
  - `src/felvi_games/achievements.py`: `_has_new_activity_after`
  - `src/felvi_games/scraper.py`: `ev_szam`
3. Cleaned resulting import fallout in `achievements.py` (unused `func`/`select` imports)

Validation:

1. `ruff check src/felvi_games/achievements.py tools/find_unused.py` -> passed
2. `pytest tests/test_achievements_dynamic_conditions.py tests/test_achievements_repeatable_gating.py tests/test_achievements_expiry_policy.py tests/test_db.py tests/test_quality_gate_report.py -q` -> 104 passed
3. `python tools/quality_gate_report.py` -> gate still FAIL, but unused regression reduced

Gate delta after Iteration 3:

| Metric | Iteration 2 | Iteration 3 | Delta trend |
|--------|-------------|-------------|-------------|
| avg CC | -0.037 | -0.037 | stable ✅ |
| F blocks | 0 | 0 | stable ✅ |
| D/E/F | 0 | 0 | stable ✅ |
| ruff | 0 | 0 | stable ✅ |
| coverage | +1.53 | +1.68 | improved ✅ |
| dup pairs | +5 | +5 | unchanged ❌ |
| hi-param | +5 | +5 | unchanged ❌ |
| unused | +102 | +76 | improved ✅ (still failing) |

Interpretation:

- The unused regression was partially reduced by improving detection quality plus two real removals.
- Remaining gate failures are now concentrated in structural duplication and high-parameter interfaces.
- Unused still fails relative to baseline because baseline predates the unused metric and effectively stores 0.

### Incremental Fix Plan (Do Not Batch)

1. **Fix tooling/runtime first**
  - Resolve quality tool import path issue for `find_unused` in `quality_gate_report.py`.
  - Re-run gate to ensure coverage command executes cleanly.

2. **Fix low-risk lint items**
  - import sorting / unused imports
  - line-length breaks in touched files
  - simple variable renames for explicit unused loop vars

3. **Then review removals one file at a time**
  - verify callsites (including decorator/discovery paths)
  - remove only confirmed dead helpers
  - run targeted tests after each removal batch

4. **Keep KPI work and cleanup linked**
  - when KPI helper migration replaces old code paths, remove obsolete helpers in the same small PR slice
  - update this document after each iteration with actual gate delta

