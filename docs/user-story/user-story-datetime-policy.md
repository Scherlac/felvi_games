# User Story: Unified DateTime Handling Policy

**ID:** US-DT-001  
**Epic:** Data Integrity & Clarity  
**Priority:** P1 (Critical Path)  
**Status:** Draft

---

## User Story

**As a** system maintainer and coach,  
**I want** all datetime handling to follow a single, explicit policy:
- **Persistence**: UTC always
- **Display (UI/Report/CLI)**: local time
- **Logic**: UTC for stored instants, local clock-time for day/time rules
- **LLM Prompts**: local time in, local time out (no zone concern)

**So that** I can trust metrics, avoid timezone bugs, and correctly interpret when badges are granted and what "before 8 AM" or "daily" means across timezones.

---

## Critical Path Definition

### 1. **Persistence (Database)**
```
RULE: All datetime columns store UTC-only.
- No naive datetimes; always `datetime.now(timezone.utc)`
- Schema: `szerzett_at TIMESTAMP DEFAULT (datetime('now', 'utc'))`
- ORM: `grant_erem()` enforces tz-aware UTC on write
```

**Acceptance:**
- [ ] `MenetRecord.kezdes`, `vege` stored as UTC
- [ ] `FelhasznaloEremRecord.szerzett_at` stored as UTC
- [ ] All new timestamps use `datetime.now(timezone.utc)`
- [ ] ORM read/write helpers normalize timezone context

---

### 2. **Display (UI, Report, CLI)**
```
RULE: All timestamps shown to users are in local time.
- Report/CLI: "2026-05-08 15:12:45 CEST"
- UI badge popover: "Awarded at 3:12 PM (local time)"
- Report header: "All times below are local time (Europe/Budapest unless overridden)"
```

**Acceptance:**
- [ ] `report.py` renders all user-facing timestamps in local time
- [ ] `cli.py` medals/stats commands show `YYYY-MM-DD HH:MM:SS <LOCAL_TZ>`
- [ ] Medal clusters documented as "Batch awarded at [local time]"
- [ ] Report metadata states: "Displayed timestamps are local; storage is UTC"

---

### 3. **LLM Prompt Context**
```
RULE: LLM receives and returns local-time values only.
- "Today is 2026-05-09"
- "Current local time is 15:12"
- "Before 08:00" is interpreted as local clock-time
```

**Acceptance:**
- [ ] `check_new_medals()` prompt includes local timestamp values only
- [ ] Dynamic condition prompts define "today" as local date
- [ ] No natural-language-only time references for system-critical rules

---

### 4. **Logic: Daily & Time-of-Day Rules**
```
RULE: Calendar/day-time logic is local-time sensitive, while persistence stays UTC.
- "Daily" means calendar day in target timezone (default: Europe/Budapest)
- "Before 8 AM" / "After 10 PM" are interpreted as local clock-time rules
- Store only UTC instants; derive local date/time during evaluation and display

EXAMPLE:
  Stored UTC instant: 2026-05-09 06:15:00 UTC
  Local (Budapest): 2026-05-09 08:15:00 CEST
  → Does NOT qualify for "before 8 AM" (local clock 08:15)
  → Counts in 2026-05-09 local daily summary
```

**Acceptance:**
- [ ] `achievements.py` rules accept injected `timezone` context
- [ ] `get_today_stats()` uses explicit timezone for day boundary
- [ ] `_eval_dynamic_condition()` converts UTC instant to local date/time before prompt
- [ ] Time helpers in `time_policy.py`:
  - `to_local_date(dt: datetime, tz: str) → date`: get calendar date in timezone
  - `to_local_time(dt: datetime, tz: str) → time`: get clock time in timezone
  - `is_in_time_range(dt: datetime, start_hour, end_hour, tz: str) → bool`

---

### 5. **Special Case: Report Daily Windows**
```
RULE: When selecting "daily" or "7-day" data, the window boundary is timezone-sensitive.
- "Report last 7 days" = from 00:00 to 23:59:59 in local timezone
- Convert to UTC range for DB query
- Display: show local timestamps; include timezone label in metadata

EXAMPLE:
  Report for last 7 days, user in Budapest (UTC+2):
  Local window: 2026-05-03 00:00 CEST to 2026-05-09 23:59:59 CEST
  UTC window: 2026-05-02 22:00 UTC to 2026-05-09 21:59:59 UTC
  Query: WHERE feladat.id IN (SELECT ... WHERE kezdes BETWEEN '2026-05-02 22:00:00' AND '2026-05-09 21:59:59')
```

**Acceptance:**
- [ ] `report.py` accepts optional `timezone` parameter (default: `Europe/Budapest`)
- [ ] Report window helper: `get_utc_range_for_local_days(days: int, tz: str) → (start_utc, end_utc)`
- [ ] Report metadata: "Last 7 days (local calendar, Europe/Budapest): 2026-05-03 to 2026-05-09"
- [ ] Test: same report run from different timezones produces timezone-appropriate local windows and consistent UTC query conversion

---

## Implementation Tasks

### Phase 1: Policy Definition & Helpers
- [ ] Create `src/felvi_games/time_policy.py` with:
  - `to_utc(dt)` — normalize any datetime to UTC-aware
  - `to_local_date(dt, tz)` — calendar date in timezone
  - `to_local_time(dt, tz)` — clock time in timezone
  - `is_in_time_range(dt, start_h, end_h, tz)` — time-of-day rule eval
  - `get_utc_range_for_local_days(days, tz)` — daily window to UTC range
  - `format_local_display(dt, tz, include_zone=True)` — user-facing local timestamp
- [ ] `docs/swe.md` add "Time Handling Policy" section with examples
- [ ] `docs/swe.md` document app-wide default timezone (Hungary → `Europe/Budapest`)

### Phase 2: Database & ORM
- [ ] Audit `db.py` for all datetime column definitions
- [ ] Add tz-aware checks to `grant_erem()`, `record_attempt()`
- [ ] Update `get_today_stats()` to accept timezone parameter
- [ ] Backfill test DB with UTC-aware fixtures

### Phase 3: Business Logic
- [ ] Refactor `achievements.py`:
  - Pass `timezone` to `check_new_medals(user, now_utc, timezone)`
  - Update calendar/time-of-day rules to use `time_policy` helpers
  - Update `_eval_dynamic_condition()` to build prompt with local date/time values only
- [ ] Update streak logic to use UTC instants, reset on local calendar boundary

### Phase 4: Display & Reports
- [ ] Refactor `report.py`:
  - Accept `timezone` parameter
  - Use `time_policy.format_local_display()` for all timestamps
  - Add report metadata showing window definition (local → UTC conversion)
  - Add section: "Time Zone Sensitive Data" explaining daily window
- [ ] Refactor `cli.py`:
  - Upgrade all timestamp output to use `time_policy.format_local_display()`
  - Add `--tz` option for timezone override
  - Diagnostics: show local display plus stored UTC instant for auditing

### Phase 5: Tests & Validation
- [ ] Add `@freezegun` decorator to all time-sensitive tests
- [ ] Test same medal rule under UTC, CEST (Budapest +1), and EST (US -5)
- [ ] Test DST boundary transitions (e.g., March 31 spring forward)
- [ ] Test report window boundaries in multiple timezones
- [ ] Validate: medal "Szerezve" timestamp + eligible window = grant semantics match

---

## Acceptance Criteria (High-Level)

**Persistence:**
- [ ] All new timestamps use `datetime.now(timezone.utc)`
- [ ] DB schema audit complete; legacy records documented as UTC-assumed

**Display:**
- [ ] Every user-facing timestamp is local-time and includes explicit local timezone label
- [ ] Medal report shows "Granted at [local]" and "Stored instant [UTC]"
- [ ] Daily report windows show conversion math: local days → UTC range

**Logic:**
- [ ] Time-of-day rules (before 8, after 22) evaluate in local timezone
- [ ] Daily streaks/summaries use calendar day in local timezone
- [ ] Medal checks inject local date/time values into condition evals

**LLM Prompts:**
- [ ] All timestamp inputs use local time only
- [ ] "Today" references use local date only

**Tests:**
- [ ] All time-sensitive tests frozen with `@freezegun`
- [ ] Timezone coverage: UTC, CEST, EST
- [ ] DST edge cases covered

---

## Code Naming Convention

To avoid persistence layer changes, use naming prefixes to signal local-time vs UTC values:

| Pattern | Meaning | Storage | Example |
|---------|---------|---------|---------|
| `utc_*` | UTC-aware datetime | DB (unchanged) | `utc_now = datetime.now(timezone.utc)` |
| `lt_*` | Local-time converted from UTC | Variables/returns only | `lt_time = to_local_time(utc_now, tz)` |
| no prefix | Ambiguous; avoid | — | ❌ `now` or `timestamp` |

**Rules:**
1. All stored values (in DB, returned from `db.py`) remain UTC; use `utc_` prefix at point of retrieval.
2. When converting to local time, use `lt_` prefix immediately:
   ```python
   utc_now = datetime.now(timezone.utc)
   lt_now = time_policy.to_local_time(utc_now, "Europe/Budapest")
   lt_hour = lt_now.hour  # clear intent: local hour
   ```
3. Function parameters and returns:
   - `def check_medals(user: str, utc_now: datetime, timezone: str) → bool`
   - `def format_display(utc_dt: datetime, tz: str, include_zone=True) → str`
   - (No prefix for timezone strings; they're always unambiguous)
4. Refactor existing code incrementally; no bulk rename required.
5. Code review: watch for missing `utc_` or `lt_` prefix as a warning sign.

**Benefit:** Zero persistence changes; clear intent at code review time; easy to audit during implementation.

---

## Type Clarity for Time-of-Day Rules

Time-of-day rules (e.g., "before 8:00", "after 22:00") must be clearly distinguished from full datetime values by type:

**Current state (implicit, needs clarity):**
```python
# Ambiguous: is this hour-of-day or a full timestamp?
condition = {"type": "before_hour", "hour": 8, "n": 5}
hour = int(condition.get("hour", 8))  # No validation; could be 0-23 or could be misunderstood
```

**Improved (explicit type):**
```python
from typing import Literal, TypedDict

class BeforeHourCondition(TypedDict):
    type: Literal["before_hour"]
    hour: int  # 0-23 (hour-of-day, not full datetime)
    n: int
    window_hours: int

# Validation at creation:
def validate_before_hour(cond: dict) -> BeforeHourCondition:
    hour = int(cond.get("hour", 8))
    if not (0 <= hour <= 23):
        raise ValueError(f"hour must be 0-23, got {hour}")
    return {"type": "before_hour", "hour": hour, "n": int(cond["n"]), "window_hours": int(cond["window_hours"])}
```

**Rules:**
1. Use `int` (0-23) for hour-of-day; the limited range makes type intent clear.
2. Use `datetime` only for full timestamps; never pass `datetime` to a time-of-day rule.
3. Add type hints and docstrings to condition evaluators:
   ```python
   def _dyn_before_hour(
       user: str,
       condition: dict,  # Contains "hour": int (0-23)
       n: int,
       cutoff: datetime,  # Full UTC instant
       upper: datetime | None,
       s: Session
   ) -> bool:
       """Evaluate: N tasks solved before hour H (local time).
       
       Args:
           condition: Must have "hour" key with int value 0-23 (hour-of-day, not timestamp)
       """
   ```
4. Add validation in config parsing: reject any hour value outside 0-23.
5. Use TypedDict for condition structures in code review checklist.

**Benefit:** Type system catches mistakes; clear at review time that `before_hour.hour` is never a full timestamp.

---

## Definition of Done

1. ✅ `time_policy.py` implemented, tested, documented
2. ✅ `db.py` refactored to enforce UTC on read/write
3. ✅ `achievements.py` uses timezone context for rules
4. ✅ `report.py` displays local-time labels + window definitions
5. ✅ `cli.py` timestamps show `YYYY-MM-DD HH:MM:SS <LOCAL_TZ>`
6. ✅ `docs/swe.md` has comprehensive Time Policy section with code examples
7. ✅ All tests frozen with `@freezegun`, covering 3+ timezones + DST
8. ✅ Code review: all datetime usage audit complete and policy-compliant

---

## Success Metrics

- **Zero timezone bugs** in production over 60 days post-implementation
- **100% of timestamps** in report/UI/CLI are local-time with timezone label
- **Coach feedback**: "Medal timestamps and daily summaries now make sense across regions"
- **Test determinism**: No time-based test flakiness

---

## Related Issues/Bugs

- BUG-005: Reward time precision (second-level, clusters) — prerequisite ✅
- ISSUE-006: Grant-time semantics in report — addressed by this story
- Session overflow: feladat_limit semantics tied to "daily boundary" — will be clarified

---

## Notes

- Default timezone for Hungary context: `Europe/Budapest` (IANA)
- Consider: future per-user timezone setting in preferences
- Logging/telemetry: store UTC instants; render local only in user-facing surfaces
- Migrations: document legacy naive datetime assumption (UTC-assumed) in migration notes

