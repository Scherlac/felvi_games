# User Story: Achievement Pre-Advertising Window

**ID:** US-AWARD-ADV-001  
**Epic:** Motivation & Progress Feedback  
**Priority:** P2  
**Status:** Planned (with partial prerequisites in place)

**Last Updated:** 2026-05-09

---

## User Story

As a learner,
I want the app to advertise relevant possible medals shortly before their achievement window opens,
so that I can intentionally start the right activity in time.

---

## Current Baseline (Already Implemented)

The app already supports two useful but different signals:

- "Most megszerezhető" style signal (engine dry-run based): medals the user can earn right now.
- "Hamarosan megszerezheted" style signal (close-medal heuristic): medals that look near completion.

What is missing today is explicit local-time window semantics for upcoming/active medal advertising.

This user story defines that missing layer.

---

## Scope

- Advertising should be tied to each medal's active achievement window.
- Pre-advertising window is local-time based.
- Should work for both single-condition and compound-condition medals.
- Core example:
  - Medal: Esti ötös
  - Active window: local 22:00-23:59
  - Advertise window: 6 hours before active window, local 16:00-22:00

---

## Rules

1. If current local time is inside a medal's advertise window and outside the active window, show "upcoming" prompt.
2. If current local time is inside the active window, show "available now" prompt.
3. If current local time is outside both windows, do not advertise.
4. Do not spam: once shown, suppress repeated advertising for a cooldown period (default 60 minutes).
5. Suppress advertising if the user already earned the non-repeatable medal.
6. For repeatable medals, only advertise when cooldown/fresh-signal policy says it is realistically earnable in the upcoming or active window.
7. Window boundaries are local-clock boundaries; storage/evaluation internals remain UTC-safe.

---

## Acceptance Criteria

- [ ] Medal definitions can include advertising metadata:
  - `active_window_local`: start/end local clock-time
  - `advertise_lead_hours`: number of hours before active window
  - `advertise_cooldown_minutes`
- [ ] App computes local "advertise now" deterministically from local clock-time.
- [ ] Esti ötös is advertised only in local 16:00-22:00.
- [ ] Esti ötös changes status to "available now" in local 22:00-23:59.
- [ ] No Esti ötös ad is shown in local 22:00-16:00 (outside advertise and active windows).
- [ ] UI copy distinguishes:
  - "Nemsokára elérhető" (upcoming)
  - "Most megszerezhető" (active)
- [ ] Report/telemetry records ad impressions and conversions (advertised -> earned).

---

## Implementation Status Snapshot

- [x] Shared engine API exists for "awardable now" decisions.
- [x] Shared basis exists for "what to advertise next" payload assembly.
- [x] Time-gating condition semantics are normalized/reviewable for generated medals.
- [ ] No dedicated medal metadata fields yet for advertise windows.
- [ ] No dedicated service yet for local-time advertise-window evaluation.
- [ ] No prompt cooldown tracker yet for advertise impressions.
- [ ] No dedicated impression/conversion telemetry model for this feature.

---

## Example Timeline (Local Time)

- 15:59: No prompt
- 16:00: "Esti ötös hamarosan" appears
- 18:30: prompt may repeat only if cooldown passed
- 22:00: switch to "Esti ötös most aktív"
- 23:59: last minute of active window
- 00:00: no prompt

---

## Implementation Tasks

1. Extend achievement config with optional advertising window fields.
2. Add helper in time policy module:
   - `is_in_local_window(now_local_time, start, end)`
   - `get_advertise_window(active_start, lead_hours)`
3. Add `get_advertisable_achievements(user, now_utc, tz)` service that returns:
   - medal id
   - state: `upcoming` or `active`
   - window boundaries in local time
4. Add anti-spam cooldown storage keying by `(user, medal_id, state)`.
5. UI: add explicit "Upcoming medals" card and retain "Active now" badge hint.
6. Telemetry: log impression and conversion events for A/B tuning and reporting.

---

## Suggested Delivery Slices

### Slice 1: Engine/service foundation

1. Add metadata fields to medal model/config parsing.
2. Implement local-time window helper utilities.
3. Implement `get_advertisable_achievements(...)` without UI wiring.
4. Add deterministic tests for daytime and nighttime windows.

### Slice 2: UI behavior and cooldown

1. Add upcoming/active sections in insight dialog.
2. Add cooldown suppression persistence.
3. Verify copy and state transitions around boundary times.

### Slice 3: Telemetry and reporting

1. Log impression events.
2. Log conversions (advertised medal later earned).
3. Add CLI/report view for conversion metrics.

---

## Definition of Done

1. Esti ötös pre-advertising works in local 16:00-22:00.
2. Active-state switch at local 22:00 works.
3. Cooldown prevents prompt spam.
4. Repeatable vs non-repeatable suppression is respected.
5. Tests cover at least 1 daytime medal and 1 night medal window.
6. Report exposes advertising conversion metrics.
7. State transitions are deterministic on boundary minutes (e.g., 15:59/16:00/22:00/00:00).

---

## Success Metrics

- +15% increase in eligible-window starts after advertising prompts.
- +10% increase in conversion for window-based medals (advertised -> earned).
- No increase in prompt-dismissal rate above baseline.
