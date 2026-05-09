# User Story: Achievement Pre-Advertising Window

**ID:** US-AWARD-ADV-001  
**Epic:** Motivation & Progress Feedback  
**Priority:** P2  
**Status:** Draft

---

## User Story

As a learner,
I want the app to advertise relevant possible medals shortly before their achievement window opens,
so that I can intentionally start the right activity in time.

---

## Scope

- Advertising should be tied to each medal's active achievement window.
- Pre-advertising window is local-time based.
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
4. UI: add "Upcoming medals" card and "Active now" badge hint.
5. Telemetry: log impression and click/engagement events for A/B tuning.

---

## Definition of Done

1. Esti ötös pre-advertising works in local 16:00-22:00.
2. Active-state switch at local 22:00 works.
3. Cooldown prevents prompt spam.
4. Repeatable vs non-repeatable suppression is respected.
5. Tests cover at least 1 daytime medal and 1 night medal window.
6. Report exposes advertising conversion metrics.

---

## Success Metrics

- +15% increase in eligible-window starts after advertising prompts.
- +10% increase in conversion for window-based medals (advertised -> earned).
- No increase in prompt-dismissal rate above baseline.
