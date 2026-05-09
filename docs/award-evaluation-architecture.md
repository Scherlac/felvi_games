# Award Evaluation Architecture Analysis

**Date:** 2026-05-09  
**Scope:** achievements.py, condition_registry.py, progress_check.py, cli.py

---

## Overview

Award evaluation is still centralized, but architecture has progressed from the original static-rule + dynamic-rule split.

Current model:

1. **Condition-driven engine** in achievements.py calling condition_registry.
2. **Shared status/progress APIs** for CLI and UI consumers.
3. **Shared "awardable now" dry-run API** that uses the same core decision path.
4. **Time-of-day review and fix tooling** to align generated medal names with condition semantics.

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

### Medium Priority

3. Split check_new_medals into explicit pipeline helpers:
   - eligibility filter
   - condition evaluation
   - result classification (new vs repeat)
   - grant persistence

4. Add targeted tests for awardability_now vs close_medals consistency contracts.

---

## Summary

The architecture is no longer in the original fragmented state described by the first draft.

Big wins completed:

1. Runtime condition evaluation standardized through condition_registry.
2. CLI/UI now consume shared award/progress APIs.
3. Time-of-day normalization and interactive review/fix workflow is in place.

Remaining open work is mainly about:

1. simulation fidelity,
2. reducing hard-coded close-medal heuristics,
3. further modularizing orchestration internals.

