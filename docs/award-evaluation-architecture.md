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

