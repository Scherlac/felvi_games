# Progress Report

Last updated: 2026-05-09
Data sources:
- [reports/20260509_7d/report.md](../reports/20260509_7d/report.md)
- [reports/20260509_30d/report.md](../reports/20260509_30d/report.md)
- CLI snapshots: felvi stats, felvi usage --limit 10, felvi wrong --detail, felvi medals --list, felvi medals --user "Lori" --expired, felvi medals --user "Lacko" --expired

---

## 1) Latest Usage Snapshot

### Global
- Total tasks: 536
- Reviewed tasks: 4 / 536 (0.75%)
- Attempts: 207
- Correct answers: 135 (65.2%)
- Users in DB: 5
- Sessions: 68

### Last 30 days (active users)
- Bencus: 9 attempts, 66.7% accuracy
- Juli: 25 attempts, 76.0% accuracy
- Lacko: 24 attempts, 62.5% accuracy
- Lori: 149 attempts, 63.8% accuracy

### Subject-level weak spots
- Lori: Hungarian 54.8% (104 attempts) vs Math 85.0% (40 attempts)
- Lacko: Math 57.1% (21 attempts)
- Global wrong-list concentration is heavily Hungarian language-focused in the current top errors.

### Momentum
- Last 7 days show high engagement from Lori only (57 attempts, 70.2%, 9 new medals).
- Multi-user activity dropped in the most recent week.

---

## 2) Key Issues Identified

### ISSUE-001 (P1) Medal catalog inconsistency
- Symptom: report output includes medals not visible in medal catalog list (examples: "Esti otos", "Reggeli rajt", "Esti lendulet").
- Evidence:
  - Present in [reports/20260509_7d/report.md](../reports/20260509_7d/report.md)
  - Not present in general output of felvi medals --list
- Risk: users and admins see inconsistent progression rules, support/debug becomes unreliable.

### ISSUE-002 (P1) Session progress can exceed target
- Symptom: usage report contains entries like 14/10 progress in one session.
- Risk: scoring and completion logic trust can degrade; analytics KPIs become noisy.
- Suspected area: session close/progress update path in app/session state integration.
- Investigation update (2026-05-09): this is primarily a semantics mismatch, not always data corruption. `MenetRecord.feladat_limit` is currently used as a point target in runtime, while usage output historically labeled it like task progress.

### ISSUE-003 (P2) Wrong-answer ranking overweights one-shot misses
- Symptom: many top wrong items are 1/1 (100%), mixed together with repeated misses.
- Risk: weak-spot prioritization is noisy; repeated misconceptions are not highlighted enough.
- Recommendation: add minimum attempts threshold and separate "repeated misses" leaderboard.

### ISSUE-004 (P2) Low reviewed-content ratio
- Symptom: only 4 reviewed tasks out of 536.
- Risk: stale accepted-answer variants and prompt wording can hurt evaluation quality and learner trust.
- Recommendation: schedule ongoing AI review for most-missed items first.

### ISSUE-005 (P3) Usage summary hides at least one user in per-user section
- Symptom: usage header shows 5 users, detailed section currently displays 4 active users.
- Risk: can be interpreted as missing data.
- Recommendation: explicitly show "inactive users" block (0 sessions) for clarity.

### ISSUE-006 (P2) Reward timestamp precision can be misleading in report
- Symptom: multiple medal awards appear with the same displayed timestamp.
- Root cause: report used minute-level formatting (`YYYY-MM-DD HH:MM`) and can hide second-level differences.
- Investigation update (2026-05-09): CLI/report upgraded to second-level timestamps and same-minute cluster diagnostics.

### ISSUE-007 (P1) Reward time is grant time, not exact qualifying event time
- Symptom: users can interpret medal time as the exact moment the achievement happened.
- Root cause: `szerzett_at` is written when the medal is granted/evaluated, not when the earliest qualifying action occurred.
- Impact: clustered timestamps are expected for batch evaluation, but misleading if not labeled.

### ISSUE-008 (P1) Reward times need explicit timezone semantics
- Symptom: user-facing report/CLI can be read as local-time activity, while stored/displayed reward times are UTC-style grant timestamps.
- Root cause: outputs historically showed timestamps without timezone labeling, while some medal rules rely on local-time logic.
- Impact: morning/evening style medals are especially easy to misread.

### ISSUE-009 (P1) Reward timeline is not the primary learning timeline
- Symptom: reports can make medal timestamps feel like core progress data.
- Root cause: medals are derived system outputs layered on top of learning behavior, not the learning behavior itself.
- Impact: readers can over-focus on reward issuance rather than attempts, errors, mastery, and persistence.

### ISSUE-010 (P1) Gamification is currently over-visible in reporting
- Symptom: reward sections are prominent even when the real product goal is exam practice and personal growth.
- Root cause: current report structure gives medals a strong narrative role, while weak spots, recovery, and mastery change are less emphasized.
- Impact: psychologically, this can shift motivation toward collecting badges instead of improving understanding.

---

## 3) Bugfix Requests (Engineering Backlog)

### BUG-001 (P1) Unify medal source of truth across commands
- Scope:
  - Ensure report generator and medal listing use the same medal catalog / registry.
  - Add integrity check command: detect medals awarded but not in catalog.
- Acceptance criteria:
  - Every medal shown in report also appears in felvi medals --list (or is marked legacy with explicit flag).
  - Automated test covers catalog/report parity.

### BUG-002 (P1) Fix session progress overflow (> planned task count)
- Scope:
  - Reproduce and patch progress accounting in session lifecycle.
  - Align naming and reporting between task counters and point target counters.
- Acceptance criteria:
  - Usage output clearly separates `tasks_solved` and `points/point_target`.
  - No ambiguous `x/y` progress label remains where denominator is actually a point target.

### BUG-005 (P2) Increase reward time precision in user-facing reports
- Scope:
  - Show second-level timestamps in medal CLI and markdown report.
  - Add same-minute cluster diagnostics so batch award events are explicit.
- Acceptance criteria:
  - Report medal lines include `HH:MM:SS`.
  - Medal CLI includes `HH:MM:SS` and prints cluster summary when multiple awards share a minute.

### BUG-006 (P1) Label reward timestamps as grant-time UTC, not event-time
- Scope:
  - Clarify in CLI/report that displayed medal time is the grant/recording time.
  - Explicitly label timezone in user-facing medal outputs.
- Acceptance criteria:
  - Medal CLI uses `Kiosztva (UTC)` wording.
  - Report section note states that timestamps are grant-time, not necessarily causal event-time.

### FEAT-006 (P1) Split learning report from reward audit
- What:
  - Learner/coach report should foreground mastery, weak spots, recovery, consistency, and trend.
  - Reward timeline should move to a secondary section or a separate admin/debug report.
- Why:
  - Keeps the product aligned with its core educational purpose.

### FEAT-007 (P1) Explain rewards as reinforcement, not outcome
- What:
  - Add one-line framing in UI/report: medals are supportive reinforcement signals derived from learning activity.
  - When possible, link each reward to the underlying behavior summary (e.g. 3 study days, 5 fast correct answers, 10 play days).
- Why:
  - Reduces misinterpretation and keeps motivation tied to learning behaviors.

### BUG-003 (P2) Improve wrong-list signal quality
- Scope:
  - Add weighted ranking: (wrong_count, total_attempts, confidence interval).
  - Add default filter: total_attempts >= 3 for "priority weak spots" view.
- Acceptance criteria:
  - felvi wrong supports --min-attempts and --sort repeated.
  - Top list prioritizes repeated misses over one-shot misses.

### BUG-004 (P2) Improve accepted-answer normalization for open text
- Scope:
  - Handle punctuation, separator, whitespace, and common morphological variants better.
  - Add optional semantic fallback for near-miss short answers.
- Acceptance criteria:
  - Existing wrong examples around spelling and formatting (comma/space/diacritics variants) are re-evaluated correctly in tests.

---

## 4) Feature Requests For Personal Growth Support

### FEAT-001 (P1) Personal Weak-Spot Coach
- What:
  - Per-user weak-skill map by subject, topic tag, and question type.
  - After each session: "Top 3 focus areas" and recommended next drill set.
- Why:
  - Current data shows strong per-user asymmetry (example: Lori Hungarian vs Math gap).

### FEAT-002 (P1) Adaptive Recovery Mode
- What:
  - Auto-generate short recovery sessions from repeatedly missed patterns.
  - Mix: 60% weak-spot practice, 30% reinforcement, 10% challenge.
- Why:
  - Repeated mistakes should immediately feed targeted practice loops.

### FEAT-003 (P2) Mastery Trend Dashboard
- What:
  - Skill trend over time (7d/30d), confidence bands, and streak health.
  - "At-risk" detector when accuracy drops below moving baseline.
- Why:
  - Supports long-term growth, not just one-off performance.

### FEAT-004 (P2) Reflection + Metacognition Prompt
- What:
  - After wrong answers, ask one short reflection question and store learning notes.
  - Show "what changed" on next retry.
- Why:
  - Encourages transfer and error-correction thinking.

### FEAT-005 (P3) Goal Planning and Habit Nudges
- What:
  - Weekly personal goals (attempt count, accuracy target, subject balance).
  - Nudge engine for inactive users and unbalanced subject practice.
- Why:
  - Last 7 days indicate single-user concentration and drop in multi-user consistency.

---

## 5) User Stories

### US-001 (P1)
As a learner with uneven subject performance,
I want the app to recommend a personalized next session based on my weakest topic,
so that I can improve faster where I struggle most.

### US-002 (P1)
As a learner who repeatedly misses similar tasks,
I want a focused recovery mini-session right away,
so that I can correct misconceptions before they become habits.

### US-003 (P1)
As a parent/coach,
I want to see weekly improvement trends per subject and skill,
so that I can support consistent growth rather than only checking scores.

### US-004 (P2)
As a learner,
I want clear and consistent medal rules across all screens and reports,
so that I trust the gamification feedback.

### US-005 (P2)
As a learner,
I want the wrong-answer list to highlight repeated mistakes first,
so that my next practice targets high-impact gaps.

### US-006 (P3)
As a learner,
I want micro-reflection prompts after mistakes,
so that I remember the reasoning and avoid repeating the same error.

### US-007 (P1) — Critical Path
**Establish unified datetime/timezone handling policy**

As a system maintainer and coach,
I want all datetime handling to follow a single, explicit policy across persistence, logic, and display,
so that I can trust metrics, avoid timezone bugs, and correctly interpret when badges are granted and what "daily" means.

**Key rules:**
- Persistence: UTC always
- Display (UI/report): local time with timezone labeling
- LLM prompt context: local time in, local time out (no zone concern)
- Logic: store UTC instants; evaluate daily and before/after rules in local clock-time
- Daily report/data windows: local-day sensitive, converted to UTC for queries
- Code naming: use `utc_*` prefix for UTC values, `lt_*` prefix for local-time values (zero persistence changes)

**Detailed spec:** See [docs/user-story-datetime-policy.md](user-story-datetime-policy.md)

**Related bugs:** BUG-005 (timestamp precision), ISSUE-006 (grant-time semantics)

### US-008 (P2)
As a learner,
I want the app to advertise upcoming medals shortly before their active achievement window,
so that I can start the right session in time to earn them.

**Key rule example:**
- "Esti ötös" advertise window: local 16:00-22:00
- "Esti ötös" active window: local 22:00-23:59

**Detailed spec:** See [docs/user-story-award-advertising-window.md](user-story-award-advertising-window.md)

---

## 6) Suggested Next Sprint Focus

1. Fix data trust issues first: BUG-001 and BUG-002.
2. Improve weak-spot signal quality: BUG-003 and FEAT-001.
3. Launch growth loop MVP: FEAT-002 + US-001/US-002 flow.
4. Add trend visibility for parents/coaches: FEAT-003 + US-003.

---

## 7) Notes

- This report is intended to be maintained after each major usage snapshot (weekly recommended).
- Update with fresh CLI evidence before reprioritization.
