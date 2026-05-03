# Technical Debt Register

Last updated: 2026-05-03  
Source: `reports/quality/complexity_report.md` (quality gate baseline, CC = Cyclomatic Complexity)

---

## Overview

| Severity | Count | Threshold |
|---|---|---|
| **F** (critical, CC ≥ 50) | 2 | Must not grow |
| **E** (high, CC 26–49) | 5 | Must not grow |
| **D** (medium, CC 16–25) | 11 | Track only |
| Avg CC (all blocks) | 4.522 | Baseline |
| P95 CC | 16.0 | Baseline |

The quality gate enforces **no regression**; items below are candidates for active refactoring.

---

## Critical (Rank F)

### ~~TD-001 · `cli.py` — `medals` (CC 78)~~
Resolved on 2026-05-03 by extracting command-mode branches into helper dispatch functions. No longer F-rank.

---

### ~~TD-002 · `cli.py` — `medal_check_cmd` (CC 76)~~
Resolved on 2026-05-03 by splitting policy-fix/simulate/dry-run/clear/default flows into dedicated helper functions. No longer F-rank.

---

### TD-003 · `report.py` — `generate_charts` (CC 60)
**File:** [src/felvi_games/report.py](../src/felvi_games/report.py#L271)  
**Root cause:** All five chart types (overall summary, accuracy-by-subject, daily activity, daily points, subject distribution) generated sequentially inside one function. Each chart adds multiple nested loops, conditionals, and matplotlib config.  
**Impact:** Adding a new chart type or adjusting an existing one risks breaking adjacent ones; function is ~300 LOC.  
**Fix:** Extract each chart into its own `_chart_<name>(data, output_dir, …) → str` function. `generate_charts` becomes a list-builder that calls them all.

---

### TD-004 · `progress_check.py` — `get_user_stats` (CC 55)
**File:** [src/felvi_games/progress_check.py](../src/felvi_games/progress_check.py#L397)  
**Root cause:** All user aggregate queries (attempts, accuracy, sessions, streaks, 7-day window, subject/level usage, hint stats, elapsed time, interaction events) run inside a single `with Session` block and a single function. Result dict construction is intermixed with query code.  
**Impact:** N+1-style structure makes it hard to add new stats without re-reading the whole function; untestable in isolation.  
**Fix:** Group queries into cohesive sub-collectors (`_fetch_attempt_stats`, `_fetch_session_stats`, `_fetch_streak_stats`, `_fetch_recent_window_stats`) each returning typed dicts, merged by the parent.

---

### ~~TD-005 · `achievements.py` — `_eval_dynamic_condition` (CC 51)~~
Resolved on 2026-05-03 by introducing condition evaluator registry dispatch. No longer F-rank.

---

## High (Rank E)

### TD-006 · `app.py` — `next_feladat` (CC 35)
**File:** [src/felvi_games/app.py](../src/felvi_games/app.py#L123)  
**Root cause:** Question-selection logic combines group eligibility, standalone fallback, force-enqueue fallback, and least-seen tie-breaking in a single function with multiple early-returns and nested loops.  
**Impact:** Hard to unit-test selection strategies in isolation.  
**Fix:** Extract `_pick_from_groups`, `_pick_standalone`, `_force_enqueue_smallest_group` as pure functions operating on pre-built data structures.

---

### TD-007 · `cli.py` — `reeval_cmd` (CC 35)
**File:** [src/felvi_games/cli.py](../src/felvi_games/cli.py#L1635)  
**Root cause:** Combines `--pending` early-return path, `--list` path, single-ID GPT call path, and bulk-evaluation path in one handler. GPT call, DB writes, and display formatting are co-located.  
**Fix:** Extract `_reeval_pending`, `_reeval_list`, `_reeval_single`, `_reeval_bulk` helpers; separate I/O from evaluation logic.

---

### TD-008 · `app.py` — `_render_kerdes` (CC 34)
**File:** [src/felvi_games/app.py](../src/felvi_games/app.py#L647)  
**Root cause:** UI rendering function that also handles TTS generation, cache staleness detection, session state mutation, and DB writes for TTS asset persistence — all inline.  
**Impact:** UI/backend binding violation — a render function should not write to the DB or compute audio.  
**Fix:** Extract TTS staleness check + generation into `_ensure_tts_kerdes(feladat, gs)` (DB-aware); `_render_kerdes` consumes the result only.

---

### TD-009 · `cli.py` — `medal_recheck_cmd` (CC 34)
**File:** [src/felvi_games/cli.py](../src/felvi_games/cli.py#L1981)  
**Root cause:** Similar God-command pattern to TD-002; handles multiple re-check modes with nested session management.  
**Fix:** Same approach as TD-002 — sub-function dispatch.

---

### TD-010 · `cli.py` — `medal_promote_candidates_cmd` (CC 31)
**File:** [src/felvi_games/cli.py](../src/felvi_games/cli.py#L2220)  
**Root cause:** Candidate collection, filtering, scoring, and display all in one body.  
**Fix:** Extract query + scoring into a reusable service function in `achievements.py` or `progress_check.py`; CLI handler formats and prints only.

---

## Medium (Rank D) — Track Only

| ID | Function | File | CC | Debt note |
|---|---|---|---|---|
| TD-011 | `pdf_parser.run` | [pdf_parser.py:711](../src/felvi_games/pdf_parser.py#L711) | 29 | Monolithic parse-loop with inline filter, skip, extract, review, and save phases. Extract phase handlers. |
| TD-012 | `achievements.check_new_medals` | [achievements.py:1176](../src/felvi_games/achievements.py#L1176) | 28 | Catalog iteration + skip-reason counters + dynamic/static branching. Extract `_try_award_medal` helper. |
| TD-013 | `app._render_sidebar` | [app.py:254](../src/felvi_games/app.py#L254) | 28 | Stats fetch + session display + navigation buttons + settings page toggle all in one. Separate stat-display from navigation. |
| TD-014 | `cli.usage` | [cli.py:164](../src/felvi_games/cli.py#L164) | 25 | DB aggregation queries inlined in CLI handler. Move to a `UsageReport` service. |
| TD-015 | `app._render_eredmeny` | [app.py:849](../src/felvi_games/app.py#L849) | 23 | Result display + TTS generation + DB save for TTS asset mixed together. Same UI/backend binding violation as TD-008. |

---

## UI / Backend Binding Violations

These are architectural issues independent of CC score.

| ID | Location | Issue |
|---|---|---|
| TD-008 | `app._render_kerdes` | Render function generates TTS audio and writes TTS assets to DB. |
| TD-015 | `app._render_eredmeny` | Render function generates TTS audio and writes TTS assets to DB. |
| TD-013 | `app._render_sidebar` | Render function calls `get_repo().get_today_stats()` directly; repo access should flow through a state/service layer. |

**Recommended pattern:** Streamlit render functions should be pure display — receive data, emit widgets. Side-effects (DB reads/writes, AI calls) belong in `app.py`'s top-level page handler or a dedicated service function called before rendering.

---

## Structural / Duplication Debt

### TD-016 · Count-threshold rules in `achievements.py`
There are 8+ nearly identical `_rule_X_feladat` / `_rule_X_pont` functions (10, 25, 50, 100, 500, 1000 tasks; 100, 500 points) that share the same SELECT + threshold pattern. Should be collapsed into a parametric factory:

```python
def _count_rule(threshold: int, model) -> RuleFn:
    def _rule(user, session_id, engine):
        ...return count >= threshold
    return _rule
```

### TD-017 · Lazy imports inside CLI handlers
Every CLI command does `from felvi_games.X import Y` inside the function body. This was done to reduce startup time, but it defeats static analysis and makes dependency tracking invisible. Consider a lazy-import module wrapper or accept the startup cost now that the CLI is mature.

---

## Maintenance Notes

- The quality gate (`tools/quality_gate_report.py`) tracks CC regressions automatically. TD items here are pre-existing debt; the gate prevents them from getting worse.
- Refresh the **Avg CC / P95 CC / D/E/F counts** row in this document whenever `--refresh-baseline` is run intentionally.
- When a TD item is resolved, mark it ~~strikethrough~~ and note the commit.
