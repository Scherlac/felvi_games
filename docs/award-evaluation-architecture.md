# Award Evaluation Architecture Analysis

**Date:** 2026-05-09  
**File:** `src/felvi_games/achievements.py`

---

## Overview

Award (medal/érem) evaluation is **centralized but not fully modularized**, with code duplication between different code paths.

**Total Implementations:** 5 distinct evaluation flows in 1 file (achievements.py)

---

## Current Implementations

### 1. **Main Orchestration: `check_new_medals()` (Lines 1002-1174)**

**Purpose:** Primary entry point; evaluates all medals, handles repeatable logic, cooldowns, and grants.

**What it does:**
- Loads catalog (static + private medals)
- Iterates through each medal
- For non-repeatable: checks if already earned → skip
- For repeatable: checks last award time and cooldown (`_REPEATABLE_COOLDOWN_HOURS`)
- Calls static rule or dynamic condition evaluator
- On success: checks fresh signal (repeatable only)
- Calls `repo.grant_erem()` to persist award

**Complexity:** ~170 lines, heavy responsibility

**Called from:** `db.py` `record_session()` after every session

---

### 2. **Static Rules: `_rule_*()` Functions (28+ functions, Lines 421-729)**

**Pattern:**
```python
def _rule_<id>(user: str, session_id: int | None, engine: Engine) -> bool
```

**Examples:**
- `_rule_elso_menet` — first session ever
- `_rule_szaz_feladat` — 100 tasks solved
- `_rule_esti_tanulas` — answer after 22:00 (local time)
- `_rule_sorozat_5` — 5-task streak

**Characteristics:**
- Direct SQL queries via SQLAlchemy
- Mostly isolated (one query per rule)
- No standardized parameter structure
- Use `_simulation_as_of` context var for time testing

**Issues:**
- 28+ functions scattered sequentially (hard to navigate)
- No TypedDict for rule definitions
- Inconsistent query patterns

---

### 3. **Dynamic Condition Evaluators: `_dyn_*()` Functions (12 evaluators, Lines 755-877)**

**Pattern:**
```python
def _dyn_<type>(user: str, condition: dict, n: int, cutoff: datetime, upper: datetime | None, s: Session) -> bool
```

**Examples:**
- `_dyn_feladat_count` — N tasks solved in window
- `_dyn_after_hour` — N tasks after hour H
- `_dyn_before_hour` — N tasks before hour H
- `_dyn_interakcio` — N interaction events of type X

**Characteristics:**
- Operate on LLM-generated JSON conditions
- Share a common signature + dispatch pattern
- Parameterized by condition dict

**Issues:**
- No input validation on condition dict keys (e.g., "hour" could be 0-23 or invalid)
- SQL logic is duplicated across some similar conditions

---

### 4. **Registry & Dispatch (Lines 880-927 and 1315-1384)**

**Static Registry (`SZABALY_REGISTRY`, Lines 970-1000):**
```python
SZABALY_REGISTRY: dict[str, Callable] = {
    "elso_menet": _rule_elso_menet,
    "szaz_feladat": _rule_szaz_feladat,
    ...
}
```

**Dynamic Registry (`_CONDITION_EVALUATORS`, Lines 920-927):**
```python
_CONDITION_EVALUATORS: dict[str, _CondEvalFn] = {
    "feladat_count": _dyn_feladat_count,
    "before_hour": _dyn_before_hour,
    ...
}
```

**Dispatch Functions:**
- `_eval_dynamic_condition()` — returns bool (award eligible)
- `_count_dynamic_condition()` — returns `(current_value, target_n)` for progress display

---

### 5. **Simulation Path: `simulate_medal_rules()` (Lines 1413-1461)**

**Purpose:** Evaluate all rules without granting; used for diagnostics and AI daily insights.

**What it does:**
- Evaluates all static rules
- Evaluates all dynamic medals (not in registry)
- Returns `RuleSimResult` list with error info

**Issues:**
- **Incomplete:** Does NOT apply repeatable cooldowns or "fresh signal" checks
  - A repeatable medal may show `result=True` in simulation even if cooldown not met
  - No way to know if this is "first earn" vs "has cooldown"
- Separate from `check_new_medals()` → code paths diverge
- Only used by CLI `felvi medal-check --simulate`; not called during gameplay

---

## Code Duplication Issues

### **Issue A: Condition Evaluation Duplicated**

Same SQL queries for conditions appear in TWO places:

**Path 1:** `_eval_dynamic_condition()` (returns bool)
- ~40 lines of dispatcher logic
- Each `_dyn_*()` function has its query

**Path 2:** `_count_dynamic_condition()` (returns progress)
- ~75 lines of DUPLICATED query logic for each condition type
- Same SQL filters, but structured to extract counts

**Example (before_hour):**

In `_dyn_before_hour()`:
```python
cnt = s.scalar(
    select(func.count()).select_from(MegoldasRecord)
    .where(
        MegoldasRecord.felhasznalo_nev == user,
        MegoldasRecord.created_at >= cutoff,
        func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) < f"{hour:02d}",
    )
) or 0
return cnt >= n
```

In `_count_dynamic_condition()` (almost identical):
```python
cnt = s.scalar(
    select(func.count()).select_from(MegoldasRecord)
    .where(MegoldasRecord.felhasznalo_nev == user,
           MegoldasRecord.created_at >= cutoff,
           func.strftime("%H", func.datetime(MegoldasRecord.created_at, "localtime")) < f"{hour:02d}")
) or 0
return cnt, n
```

**Fix:** Extract shared query logic into helper; both paths call it.

---

### **Issue B: Repeatable Logic Not Fully Modularized**

In `check_new_medals()` (lines 1265-1285):
```python
if erem.ismetelheto and last_award_at is not None:
    if erem.condition:
        # Complex repeatable logic for dynamic
        from_anchor = last_award_at + timedelta(microseconds=1)
        if cond_anchor_utc is not None and cond_anchor_utc > from_anchor:
            from_anchor = cond_anchor_utc
        fresh_signal = _eval_dynamic_condition(user, erem.condition, engine, valid_from=from_anchor)
    else:
        # Separate logic for static
        fresh_signal = _repeatable_has_fresh_signal(erem_id, user, engine, last_award_at)
    if not fresh_signal:
        continue
```

**Issue:** Repeatable logic is scattered:
1. Cooldown check in `check_new_medals()` line ~1130 (`if now - last_award_at < cooldown_hours...`)
2. Fresh signal logic in lines 1265-1285 (complex time anchor logic)
3. Helper `_repeatable_has_fresh_signal()` for static rules only

**Fix:** Extract repeatable cooldown + fresh signal into standalone module.

---

### **Issue C: Static vs Dynamic Registries Are Separate**

Two registry systems:
- `SZABALY_REGISTRY` (dict) for static rules
- `_CONDITION_EVALUATORS` (dict) for dynamic

**Consequence:**
- `simulate_medal_rules()` has to iterate both separately
- No unified "get evaluator for medal" function
- Harder to add new evaluation types

---

## Modularity Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| **Single responsibility** | ❌ Poor | `check_new_medals()` does: lookup, evaluation, cooldown, grant, logging (~170 lines) |
| **Code reuse** | ❌ Poor | Query logic duplicated between `_eval_dynamic_condition()` and `_count_dynamic_condition()` |
| **Testability** | ⚠️ Fair | Static rules can be tested in isolation; dynamic conditions harder (need condition dict) |
| **Registry design** | ⚠️ Fair | Two separate registries; no unified dispatch |
| **Error handling** | ⚠️ Fair | Catches exceptions but logs, doesn't propagate; hard to debug |
| **Type safety** | ❌ Poor | No TypedDict for rule/condition structures; "hour" in before_hour not validated as 0-23 |
| **Simulation path** | ❌ Poor | Incomplete; doesn't apply cooldown/fresh signal logic |

---

## Recommendations for Refactoring

### **High Priority (Blocks datetime policy work)**

1. **Extract condition query logic:**
   - Create `_get_condition_count(user, condition, cutoff, upper, s) → int`
   - Use in both `_eval_dynamic_condition()` and `_count_dynamic_condition()`
   - Eliminates ~35 lines of duplication

2. **Extract repeatable logic into module:**
   - `def should_award_repeatable(erem: Erem, last_award_at: datetime, now: datetime) → bool`
   - Consolidates cooldown + fresh signal logic
   - Used by both `check_new_medals()` and `simulate_medal_rules()`

3. **Add type validation for time-of-day conditions:**
   - Validate `before_hour.hour` is 0-23 at condition creation
   - Add TypedDict for `BeforeHourCondition`, `AfterHourCondition`

### **Medium Priority (Code quality)**

4. **Unified registry:**
   - Combine `SZABALY_REGISTRY` + `_CONDITION_EVALUATORS` into single `MEDAL_REGISTRY`
   - Reduces code duplication in `simulate_medal_rules()`

5. **Extract `check_new_medals()` into pipeline:**
   - Step 1: filter by eligibility (already earned, cooldown)
   - Step 2: evaluate rule/condition
   - Step 3: check fresh signal (repeatable)
   - Step 4: grant and return

---

## Summary

**Architecture Quality:** Functional but fragmented.

- **Centralization:** ✅ All award logic in `achievements.py`
- **Modularity:** ❌ Code duplication between eval paths; repeatable logic scattered
- **Maintainability:** ⚠️ Hard to add new condition types without duplicating query logic
- **Testing:** ⚠️ Simulation path is incomplete; can't fully validate repeatable logic

**Recommendation:** Before implementing datetime policy refactor, extract the 3 high-priority modules above to reduce complexity. This will make time-of-day rule validation and daily window logic cleaner.

