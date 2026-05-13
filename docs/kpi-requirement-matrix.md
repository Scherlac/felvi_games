# KPI Requirement Matrix

## Scope
This matrix defines:
- Base KPI parameters (registry-level primitives)
- Derived stats (computed from base KPI outputs)
- Supported time windows and comparison cases
- Output shape and cache requirements
- Mapping to current user-stats contract

## Window Model
| Window ID | Definition | Typical Usage |
|---|---|---|
| all_time | From epoch to `upper` | Lifetime totals, exploration coverage |
| rolling_24h | `upper-24h` to `upper` | Daily trend current bucket |
| rolling_48h | `upper-48h` to `upper` | Source for previous 24h via cases |
| rolling_7d | `upper-7d` to `upper` | Weekly activity/outcomes/events |
| rolling_custom_h | `upper-h` to `upper` | Dynamic medals and ad-hoc KPI stats |

## Base KPI Parameters
| KPI Name | Category | Output Type | Key Fields | Windows | Required Stats | Current Consumer |
|---|---|---|---|---|---|---|
| attempt_count | volume | int | none | all | values,cases,total,min,max,trend,count | total attempts, trends |
| correct_count | volume | int | none | all | values,cases,total,min,max,trend,count | total correct, trends |
| points_sum | volume | int | none | all | values,cases,total,min,max,trend,count | points trends |
| session_count | volume | int | none | all | values,cases,total,min,max,trend,count | total sessions |
| completed_session_count | volume | int | none | all | values,cases,total,min,max,trend,count | completed sessions |
| fast_correct_count | condition | int | none | all | values,cases,total,min,max,trend,count | medal evaluator/count |
| subject_attempt_count | condition | int | subject | all | values,cases,total,min,max,trend,count | medal evaluator/count |
| before_hour_count | condition | int | hour | all | values,cases,total,min,max,trend,count | medal evaluator/count |
| after_hour_count | condition | int | hour | all | values,cases,total,min,max,trend,count | medal evaluator/count |
| interaction_count | condition | int | event_type,targy,szint,feladat_id,meta_contains | all | values,cases,total,min,max,trend,count | medal evaluator/count |
| recent_play_days_count | consistency | int | none | 7d/custom | values,cases,total,min,max,trend,count | recent_days_7d |
| play_day_streak_current | consistency | int | none | all_time | values,total,min,max,count | current_streak_days |
| best_correct_streak | consistency | int | none | all_time | values,total,min,max,count | best_correct_streak |
| current_correct_streak | consistency | int | none | all_time | values,total,min,max,count | current_correct_streak |
| subjects_used | pattern | list[str] | time_scope | all_time/window | values,count | subjects_used |
| levels_used | pattern | list[str] | time_scope | all_time/window | values,count | levels_used |
| dimension_session_counts | pattern | dict[str,int] | dimension,time_scope | all_time/window | values,count | subject/level counts |
| attempt_task_type_counts | pattern | dict[str,int] | time_scope | all_time/window | values,count | attempt task-type counts |
| hint_stats_last_n_correct | quality | dict | n | all_time/window | values,count | help_usage_last20 |
| hint_uses_count | quality | int | none | all | values,cases,total,min,max,trend,count | hint trends |
| avg_elapsed_sec_correct | quality | float\|None | none | all_time/window | values,min,max,count | avg_elapsed_sec |
| daily_attempts | trend_detail | list[dict] | none | 7d/custom | values,count | daily_attempts_7d |
| answer_outcomes | trend_detail | dict[str,int] | none | 7d/custom | values,count | answer_outcomes_7d |
| event_count_by_type | events | dict[str,int] | none | all | values,count | event counts |
| recent_events | events | list[dict] | limit | 7d/custom | values,count | recent events feed |
| reevaluations_count | operations | int | none | all | values,cases,total,min,max,trend,count | reevaluations_last_7d |
| reevaluations_improved_count | operations | int | none | all | values,cases,total,min,max,trend,count | reevaluation_improved_last_7d |
| pending_reward_attempts | operations | int | none | all | values,cases,total,min,max,trend,count | pending_reward_attempts |

## Derived Stats Matrix
| Derived Stat | Formula / Source | Window Inputs | Output Type | Target Field |
|---|---|---|---|---|
| accuracy_pct | `correct / total_attempts * 100` | all_time | float | accuracy_pct |
| attempts_prev_24h | `cases[24<-48].previous` from `attempt_count` | 24h,48h | int | trends.attempts_prev_24h |
| correct_prev_24h | `cases[24<-48].previous` from `correct_count` | 24h,48h | int | trends.correct_prev_24h |
| points_prev_24h | `cases[24<-48].previous` from `points_sum` | 24h,48h | int | trends.points_prev_24h |
| accuracy_last_24h | `correct_last_24h / attempts_last_24h * 100` | 24h | float\|None | trends.accuracy_last_24h |
| accuracy_prev_24h | `correct_prev_24h / attempts_prev_24h * 100` | prev 24h | float\|None | trends.accuracy_prev_24h |
| activity_trend | compare attempts_last_24h vs attempts_prev_24h | 24h,prev24h | str | trends.activity_trend |
| accuracy_trend | compare accuracy_last_24h vs accuracy_prev_24h | 24h,prev24h | str | trends.accuracy_trend |
| hint_free_correct_last20 | `hint_stats_last_n_correct.hint_free` | all_time/window | int | hint_free_correct_last20 |
| hint_used_correct | `hint_stats_last_n_correct.hint_used` | all_time/window | int | patterns.help_usage_last20.hint_used_correct |

## KPI Stats Requirements
| Requirement ID | Requirement | Applies To |
|---|---|---|
| R1 | KPI output must be deterministic for `(user,kpi,condition,cutoff,upper)` within one DB snapshot | all KPIs |
| R2 | Every behavior-changing condition field must be listed in `key_fields` | base KPIs |
| R3 | Windowed KPI must honor both `cutoff` and `upper` | all window-aware KPIs |
| R4 | Returned payload must be JSON-safe (`int`, `float`, `str`, `dict`, `list`, `None`) | all KPIs |
| R5 | `kpi_parameter_value` must cache by `(kpi,user,cutoff,upper,key_fields)` | scalar/structured KPIs |
| R6 | `kpi_parameter_window_stats` must only compute requested stats | stats API |
| R7 | `cases` must derive previous bucket from cumulative windows | window stats for trend |
| R8 | Missing/unknown KPI must fail soft (`None` or empty payload) | all consumers |
| R9 | get_user_stats shape should remain stable while KPI internals evolve | integration contract |
| R10 | Derived fields should not run extra DB queries if source KPI already computed in-session | integration efficiency |

## Current get_user_stats Mapping (Contract Level)
| Output Field | Source |
|---|---|
| total_attempts | attempt_count(all_time) |
| correct | correct_count(all_time) |
| total_sessions | session_count(all_time) |
| completed_sessions | completed_session_count(all_time) |
| subjects_used | subjects_used(time_scope=all_time) |
| levels_used | levels_used(time_scope=all_time) |
| recent_days_7d | recent_play_days_count(7d) |
| current_streak_days | play_day_streak_current(all_time) |
| best_correct_streak | best_correct_streak(all_time) |
| current_correct_streak | current_correct_streak(all_time) |
| hint_free_correct_last20 | hint_stats_last_n_correct(n=20).hint_free |
| avg_elapsed_sec | avg_elapsed_sec_correct(all_time) |
| trends.* attempts/correct/points | window_stats(values,cases) on attempt_count/correct_count/points_sum |
| trends.hint_uses_* | window_stats(values,cases) on hint_uses_count |
| trends.daily_attempts_7d | daily_attempts(7d) |
| trends.answer_outcomes_7d | answer_outcomes(7d) |
| patterns.subject_session_counts* | dimension_session_counts(dimension=subject, time_scope=all_time/window) |
| patterns.level_session_counts* | dimension_session_counts(dimension=level, time_scope=all_time/window) |
| patterns.attempt_task_type_counts | attempt_task_type_counts(all_time) |
| events.counts_last_24h | event_count_by_type(24h) |
| events.counts_last_7d | event_count_by_type(7d) |
| events.reevaluations_last_7d | reevaluations_count(7d) |
| events.reevaluation_improved_last_7d | reevaluations_improved_count(7d) |
| events.pending_reward_attempts | pending_reward_attempts(all_time) |
| events.recent | recent_events(7d, limit=8) |

## Extension Guidance
To add a new stat:
1. Add one base KPI with clear `name`, `calc_fn`, and `key_fields`.
2. Register with accurate `stats_supported`.
3. Use `kpi_parameter_window_stats` if 24h/48h comparisons are needed.
4. Add only one derived transform in consumer layer.
5. Add tests for cache hit, window behavior, and payload shape.
