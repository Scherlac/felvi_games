# Code Quality Gate Report

Generated at (UTC): 2026-05-16T17:21:18+00:00
Scope: src, tests

## Gate

QUALITY_GATE: PASS

Reasons:
- No significant regression vs baseline.

## Current Snapshot

- Python files: 46
- LOC: 21681 (SLOC: 16898, Blank: 3199)
- Avg MI: 40.127
- Avg CC: 4.499
- P95 CC: 14.0
- Rank counts: A=652, B=124, C=50, D=14, E=3, F=1
- D/E/F blocks: 18
- F blocks: 1
- Parse-error files: 0
- Unused top-level functions: 71
- Coverage: 57.462%

## Coverage

- Total line coverage: 57.462%
- Files measured: 22
- Coverage source: fresh test run via --coverage-command
- Coverage status: OK

### Lowest Coverage Files

| Coverage % | Covered/Statements | File |
|---:|---:|---|
| 0.0 | 0/432 | src/felvi_games/report.py |
| 0.0 | 0/75 | src/felvi_games/review_chainlit_app.py |
| 0.0 | 0/179 | src/felvi_games/scraper.py |
| 31.062 | 515/1658 | src/felvi_games/cli.py |
| 42.857 | 51/119 | src/felvi_games/ai.py |
| 53.807 | 106/197 | src/felvi_games/review.py |
| 64.113 | 159/248 | src/felvi_games/condition_registry.py |
| 72.222 | 182/252 | src/felvi_games/achievements.py |
| 74.375 | 357/480 | src/felvi_games/progress_check.py |
| 75.0 | 54/72 | src/felvi_games/status.py |

## Code Repetition

- Structural duplicate function pairs: 26

| Clones | Body Size | Location A | Location B |
|---:|---:|---|---|
| 9 | 22 | src/felvi_games/condition_registry.py:341 _count_feladat_count | src/felvi_games/condition_registry.py:344 _count_helyes_count |
| 7 | 27 | src/felvi_games/condition_registry.py:285 _eval_feladat_count | src/felvi_games/condition_registry.py:288 _eval_helyes_count |
| 4 | 27 | src/felvi_games/condition_registry.py:557 _eval_pontossag | src/felvi_games/condition_registry.py:561 _eval_menet_cover |
| 3 | 31 | tests/conftest.py:28 feladat_matek | tests/test_cli_review.py:30 feladat |
| 3 | 27 | src/felvi_games/condition_registry.py:535 _eval_play_days | src/felvi_games/condition_registry.py:543 _eval_day_streak |
| 3 | 26 | tests/test_pdf_parser.py:106 test_matek_feladatlap | tests/test_pdf_parser.py:110 test_magyar_utmutato |
| 3 | 24 | tests/test_medal_assets.py:31 _asset_path | tests/test_medal_assets.py:45 _asset_path |
| 3 | 22 | tests/test_achievements_dynamic_conditions.py:144 wrapped_query | tests/test_achievements_dynamic_conditions.py:199 wrapped_query |
| 3 | 20 | src/felvi_games/condition_registry.py:578 _count_play_days | src/felvi_games/condition_registry.py:584 _count_day_streak |
| 3 | 18 | src/felvi_games/kpi_definitions.py:30 _attempt_timestamp | src/felvi_games/kpi_definitions.py:104 _session_timestamp |
| 2 | 112 | tests/test_review_agent_tools.py:238 test_request_task_update_confirmation_requires_updates_payload | tests/test_review_agent_tools.py:356 test_resolve_task_flag_requires_reviewer |
| 2 | 80 | src/felvi_games/kpi_definitions.py:14 _attempt_query | src/felvi_games/kpi_definitions.py:88 _session_query |
| 2 | 68 | src/felvi_games/kpi_registry.py:605 _kpi_total_count | src/felvi_games/kpi_registry.py:624 _kpi_total_sum |
| 2 | 64 | src/felvi_games/kpi_registry.py:644 _attempt_rows | src/felvi_games/kpi_registry.py:662 _session_rows |
| 2 | 51 | tests/test_db.py:225 test_save_megoldas_helyes | tests/test_db.py:232 test_save_megoldas_helytelen |
| 2 | 46 | tests/test_pdf_parser.py:504 test_single_task_detected | tests/test_pdf_parser.py:511 test_multiple_tasks_split_correctly |
| 2 | 44 | src/felvi_games/db.py:688 get | src/felvi_games/db.py:760 get_csoport |
| 2 | 35 | tests/test_pdf_parser.py:285 test_missing_ut_skipped | tests/test_pdf_parser.py:290 test_ut_only_not_yielded |
| 2 | 28 | src/felvi_games/models.py:195 pdf_source | src/felvi_games/models.py:200 ut_source |
| 2 | 27 | src/felvi_games/db.py:2045 rontas_pct | src/felvi_games/db.py:2075 accuracy_pct |
| 2 | 27 | src/felvi_games/progress_check.py:210 _safe_int | src/felvi_games/progress_check.py:217 _safe_float |
| 2 | 27 | tests/test_achievements_dynamic_conditions.py:15 _make_feladat | tests/test_achievements_repeatable_gating.py:14 _make_feladat |
| 2 | 27 | tests/test_pdf_parser.py:473 test_feladat_tipus_parsed | tests/test_pdf_parser.py:487 test_reszpontozas_parsed |
| 2 | 24 | tests/test_medal_assets.py:68 _asset_path | tests/test_medal_assets.py:91 _asset_path |
| 2 | 19 | src/felvi_games/review_check_shared.py:27 normalized_limit | src/felvi_games/review_check_shared.py:31 normalized_min_hibas |
| 2 | 15 | tests/test_db.py:481 test_get_menetek_empty_for_unknown_user | tests/test_db.py:692 test_get_feladatok_by_csoport_empty |


## Cohesion

- Classes analyzed: 46
- Avg LCOM1: 0.844 (0=cohesive, 1=disconnected)

### Low-Cohesion Classes (LCOM1 > 0.7)

| LCOM1 | Class | File |
|---:|---|---|
| 1.0 | AwardabilityNow | src/felvi_games/achievements.py:334 |
| 1.0 | Ertekeles | src/felvi_games/models.py:312 |
| 1.0 | ReviewQuery | src/felvi_games/review_check_shared.py:17 |
| 1.0 | TestReviewCli | tests/test_cli_review.py:71 |
| 1.0 | TestReviewChatCli | tests/test_cli_review_chat.py:15 |
| 1.0 | TestInit | tests/test_db.py:41 |
| 1.0 | TestUpsert | tests/test_db.py:58 |
| 1.0 | TestGet | tests/test_db.py:84 |
| 1.0 | TestAll | tests/test_db.py:106 |
| 1.0 | TestTtsAssets | tests/test_db.py:153 |


## Interface Complexity

- Public functions analyzed: 479
- Avg parameters: 1.461
- High-parameter functions (> 5 params): 16
- Untyped public functions (no return annotation): 198

### High-Parameter Functions

| Params | Function | File |
|---:|---|---|
| 10 | register | src/felvi_games/kpi_registry.py:220 |
| 8 | check_answer | src/felvi_games/ai.py:124 |
| 8 | refine_daily_medal | src/felvi_games/ai.py:468 |
| 8 | save_megoldas | src/felvi_games/db.py:871 |
| 8 | log_interakcio | src/felvi_games/db.py:1446 |
| 8 | kpi_parameter | src/felvi_games/kpi_registry.py:270 |
| 8 | run | src/felvi_games/pdf_parser.py:711 |
| 7 | eval_condition | src/felvi_games/condition_registry.py:216 |
| 7 | eval_conditions | src/felvi_games/condition_registry.py:238 |
| 7 | kpi_rows | src/felvi_games/kpi_registry.py:300 |
| 6 | evaluate_dynamic_condition_progress | src/felvi_games/achievements.py:259 |
| 6 | check_new_medals | src/felvi_games/achievements.py:396 |
| 6 | resolve_hibajelezes | src/felvi_games/db.py:1139 |
| 6 | get_wrong_feladatok | src/felvi_games/db.py:1747 |
| 6 | extract_feladatok | src/felvi_games/pdf_parser.py:271 |
| 6 | extract_feladatok_batched | src/felvi_games/pdf_parser.py:333 |


## Unused Functions

- Unused top-level functions: 71
- Unused analysis status: OK

| Symbol | File |
|---|---|
| all_conditions | src/felvi_games/condition_registry.py:172 |
| advertise_all | src/felvi_games/condition_registry.py:197 |
| eval_conditions | src/felvi_games/condition_registry.py:238 |
| condition_count | src/felvi_games/condition_registry.py:260 |
| test_eval_dynamic_condition_unknown_type_returns_false | tests/test_achievements_dynamic_conditions.py:50 |
| test_eval_dynamic_condition_feladat_count_respects_valid_from | tests/test_achievements_dynamic_conditions.py:54 |
| test_eval_dynamic_condition_interakcio_exists_with_enum_and_filters | tests/test_achievements_dynamic_conditions.py:81 |
| test_eval_dynamic_condition_respects_simulation_upper_bound | tests/test_achievements_dynamic_conditions.py:108 |
| test_eval_dynamic_condition_reuses_kpi_cache_with_shared_session | tests/test_achievements_dynamic_conditions.py:133 |
| test_eval_dynamic_condition_attempt_count_and_pont_sum_share_attempt_items_cache | tests/test_achievements_dynamic_conditions.py:188 |
| test_eval_dynamic_condition_short_circuits_compound_conditions | tests/test_achievements_dynamic_conditions.py:243 |
| test_non_repeatable_temporary_medal_does_not_get_expiry | tests/test_achievements_expiry_policy.py:41 |
| test_repeatable_temporary_medal_gets_expiry | tests/test_achievements_expiry_policy.py:53 |
| test_bootstrap_conditions_seeded_and_villam_awardable | tests/test_achievements_repeatable_gating.py:57 |
| test_esti_tanulas_requires_new_night_signal | tests/test_achievements_repeatable_gating.py:90 |
| test_villam_repeatable_respects_cooldown | tests/test_achievements_repeatable_gating.py:139 |
| test_generate_daily_insight_prompt_includes_trends_patterns_and_events | tests/test_ai_daily_insight.py:11 |
| test_medals_generator_inputs_shows_payload | tests/test_cli_medals.py:34 |
| test_medals_generator_inputs_requires_user | tests/test_cli_medals.py:93 |
| test_medals_shows_all_earned_dates_for_repeated_medal | tests/test_cli_medals.py:102 |
| test_medal_check_policy_fix_makes_temp_one_time_reearnable | tests/test_cli_medals.py:139 |
| test_medal_edit_can_update_dynamic_condition_json | tests/test_cli_medals.py:215 |
| test_reeval_lenient_open_can_upgrade_score | tests/test_cli_reeval.py:48 |
| test_reeval_without_lenient_open_keeps_strict_score | tests/test_cli_reeval.py:84 |
| test_wrong_issues_lists_flagged_and_keyword_counts | tests/test_cli_wrong_issues.py:52 |
| test_wrong_issues_contains_filter_changes_counts | tests/test_cli_wrong_issues.py:65 |
| test_wrong_issues_writes_ids_dat_file | tests/test_cli_wrong_issues.py:78 |
| test_kpi_registry_item_and_value_share_base_query_cache | tests/test_kpi_registry_reference.py:17 |
| test_kpi_registry_cases_derive_previous_bucket_from_24h_and_48h | tests/test_kpi_registry_reference.py:65 |
| test_kpi_registry_missing_kpi_fails_soft | tests/test_kpi_registry_reference.py:94 |
| test_get_medal_asset_prefers_local_bytes | tests/test_medal_assets.py:28 |
| test_get_medal_asset_falls_back_to_url_or_none | tests/test_medal_assets.py:42 |
| test_medal_asset_exists_reports_presence | tests/test_medal_assets.py:54 |
| test_generate_medal_assets_generates_supported_kinds | tests/test_medal_assets.py:65 |
| test_generate_medal_assets_keeps_existing_when_no_overwrite | tests/test_medal_assets.py:88 |
| test_get_user_stats_includes_trends_patterns_and_events | tests/test_progress_check.py:21 |
| test_daily_check_rejects_overlapping_dynamic_medal | tests/test_progress_check.py:123 |
| test_daily_check_refines_overlapping_dynamic_medal | tests/test_progress_check.py:185 |
| test_normalize_medal_candidate_time_gate_adds_morning_gate | tests/test_progress_check.py:280 |
| test_review_time_gate_alignment_flags_missing_gate | tests/test_progress_check.py:300 |
| test_find_cross_user_medal_clusters_detects_overlap | tests/test_progress_check.py:318 |
| test_find_cross_user_medal_clusters_no_results_below_threshold | tests/test_progress_check.py:337 |
| test_daily_check_blocks_cross_user_duplicate_and_logs_signal | tests/test_progress_check.py:345 |
| test_ratchet_no_improvement_returns_none | tests/test_quality_gate_report.py:67 |
| test_ratchet_updates_only_improved_complexity_metrics | tests/test_quality_gate_report.py:77 |
| test_ratchet_updates_coverage_only_when_it_improves | tests/test_quality_gate_report.py:92 |
| test_ratchet_does_not_lower_coverage_baseline | tests/test_quality_gate_report.py:104 |
| test_main_auto_ratchet_writes_improved_metrics | tests/test_quality_gate_report.py:114 |
| test_extract_page_no_markers_returns_truncated | tests/test_review.py:42 |
| test_extract_page_known_page | tests/test_review.py:48 |
| test_extract_page_last_page_no_trailing_marker | tests/test_review.py:55 |
| test_extract_page_missing_page_returns_fallback | tests/test_review.py:61 |
| test_extract_page_none_page_no | tests/test_review.py:67 |
| test_review_feladatok_accept | tests/test_review.py:79 |
| test_review_feladatok_skip | tests/test_review.py:89 |
| test_review_feladatok_quit_early | tests/test_review.py:96 |
| test_review_feladatok_empty | tests/test_review.py:111 |
| test_edit_feladat_cli_no_changes | tests/test_review.py:121 |
| test_edit_feladat_cli_changes_kerdes | tests/test_review.py:129 |
| test_edit_feladat_cli_invalid_neh_keeps_original | tests/test_review.py:156 |
| test_save_review_sets_review_elvegezve | tests/test_review.py:173 |
| test_save_review_clears_megoldas_hibajelezes | tests/test_review.py:180 |
| test_save_review_unknown_feladat_raises | tests/test_review.py:203 |
| test_review_elvegezve_roundtrips_via_upsert | tests/test_review.py:208 |
| test_build_review_chat_context_includes_attempt_buckets | tests/test_review_chat_context.py:10 |
| test_asset_path_resolution | tests/test_source_search.py:206 |
| test_pdf_summary_empty_dir_prints_hint | tests/test_status.py:8 |
| test_pdf_summary_groups_known_files | tests/test_status.py:14 |
| test_pdf_summary_unrecognized_names_are_reported | tests/test_status.py:29 |
| test_run_missing_paths_prints_missing_hints | tests/test_status.py:38 |
| test_run_calls_pdf_and_db_summaries_when_paths_exist | tests/test_status.py:55 |

## Ruff Lint

- Total violations: 10
- By category: E=7, I=3
- Ruff status: OK

## Baseline Delta

- Baseline timestamp: 2026-05-16T11:19:49+00:00
- Delta avg_cc: 0.122
- Delta p95_cc: 0.0
- Delta D/E/F blocks: 0
- Delta F blocks: 0
- Delta parse-error files: 0
- Delta coverage_pct: 1.13
- Delta ruff_violations: 3
- Delta duplicate_block_pairs: 2
- Delta high_param_count: 1
- Delta unused_function_count: 0

Notes:
- WARNING: Avg CC +0.122 (within tolerance 0.35).
- WARNING: Ruff +3 violations (within tolerance 5).
- WARNING: Duplicate pairs +2 (within tolerance 2).
- WARNING: High-param functions +1 (within tolerance 2).

### New Duplicate Pairs Since Baseline

> **Note:** Baseline snapshot stored only 20 of 24 duplicate pairs — some listed pairs may pre-date the baseline. Re-run the quality gate to update the baseline.

| Clones | Body Size | Location A | Location B |
|---:|---:|---|---|
| 9 | 22 | src/felvi_games/condition_registry.py:341 _count_feladat_count | src/felvi_games/condition_registry.py:344 _count_helyes_count |
| 7 | 27 | src/felvi_games/condition_registry.py:285 _eval_feladat_count | src/felvi_games/condition_registry.py:288 _eval_helyes_count |
| 4 | 27 | src/felvi_games/condition_registry.py:557 _eval_pontossag | src/felvi_games/condition_registry.py:561 _eval_menet_cover |
| 3 | 27 | src/felvi_games/condition_registry.py:535 _eval_play_days | src/felvi_games/condition_registry.py:543 _eval_day_streak |
| 3 | 22 | tests/test_achievements_dynamic_conditions.py:144 wrapped_query | tests/test_achievements_dynamic_conditions.py:199 wrapped_query |
| 3 | 20 | src/felvi_games/condition_registry.py:578 _count_play_days | src/felvi_games/condition_registry.py:584 _count_day_streak |
| 3 | 18 | src/felvi_games/kpi_definitions.py:30 _attempt_timestamp | src/felvi_games/kpi_definitions.py:104 _session_timestamp |
| 2 | 112 | tests/test_review_agent_tools.py:238 test_request_task_update_confirmation_requires_updates_payload | tests/test_review_agent_tools.py:356 test_resolve_task_flag_requires_reviewer |
| 2 | 80 | src/felvi_games/kpi_definitions.py:14 _attempt_query | src/felvi_games/kpi_definitions.py:88 _session_query |
| 2 | 68 | src/felvi_games/kpi_registry.py:605 _kpi_total_count | src/felvi_games/kpi_registry.py:624 _kpi_total_sum |
| 2 | 64 | src/felvi_games/kpi_registry.py:644 _attempt_rows | src/felvi_games/kpi_registry.py:662 _session_rows |
| 2 | 19 | src/felvi_games/review_check_shared.py:27 normalized_limit | src/felvi_games/review_check_shared.py:31 normalized_min_hibas |

### New High-Parameter Functions Since Baseline

> **Note:** Baseline snapshot stored only 10 of 15 high-param functions — some listed functions may pre-date the baseline. Re-run the quality gate to update the baseline.

| Params | Function | File |
|---:|---|---|
| 6 | evaluate_dynamic_condition_progress | src/felvi_games/achievements.py:259 |
| 6 | check_new_medals | src/felvi_games/achievements.py:396 |
| 6 | resolve_hibajelezes | src/felvi_games/db.py:1139 |
| 6 | get_wrong_feladatok | src/felvi_games/db.py:1747 |
| 6 | extract_feladatok | src/felvi_games/pdf_parser.py:271 |
| 6 | extract_feladatok_batched | src/felvi_games/pdf_parser.py:333 |

### New Unused Functions Since Baseline

> **Note:** Baseline snapshot stored only 20 of 71 unused functions — some listed functions may pre-date the baseline. Re-run the quality gate to update the baseline.

| Symbol | File |
|---|---|
| test_medal_check_policy_fix_makes_temp_one_time_reearnable | tests/test_cli_medals.py:139 |
| test_medal_edit_can_update_dynamic_condition_json | tests/test_cli_medals.py:215 |
| test_reeval_lenient_open_can_upgrade_score | tests/test_cli_reeval.py:48 |
| test_reeval_without_lenient_open_keeps_strict_score | tests/test_cli_reeval.py:84 |
| test_wrong_issues_lists_flagged_and_keyword_counts | tests/test_cli_wrong_issues.py:52 |
| test_wrong_issues_contains_filter_changes_counts | tests/test_cli_wrong_issues.py:65 |
| test_wrong_issues_writes_ids_dat_file | tests/test_cli_wrong_issues.py:78 |
| test_kpi_registry_item_and_value_share_base_query_cache | tests/test_kpi_registry_reference.py:17 |
| test_kpi_registry_cases_derive_previous_bucket_from_24h_and_48h | tests/test_kpi_registry_reference.py:65 |
| test_kpi_registry_missing_kpi_fails_soft | tests/test_kpi_registry_reference.py:94 |
| test_get_medal_asset_prefers_local_bytes | tests/test_medal_assets.py:28 |
| test_get_medal_asset_falls_back_to_url_or_none | tests/test_medal_assets.py:42 |
| test_medal_asset_exists_reports_presence | tests/test_medal_assets.py:54 |
| test_generate_medal_assets_generates_supported_kinds | tests/test_medal_assets.py:65 |
| test_generate_medal_assets_keeps_existing_when_no_overwrite | tests/test_medal_assets.py:88 |
| test_get_user_stats_includes_trends_patterns_and_events | tests/test_progress_check.py:21 |
| test_daily_check_rejects_overlapping_dynamic_medal | tests/test_progress_check.py:123 |
| test_daily_check_refines_overlapping_dynamic_medal | tests/test_progress_check.py:185 |
| test_normalize_medal_candidate_time_gate_adds_morning_gate | tests/test_progress_check.py:280 |
| test_review_time_gate_alignment_flags_missing_gate | tests/test_progress_check.py:300 |
| test_find_cross_user_medal_clusters_detects_overlap | tests/test_progress_check.py:318 |
| test_find_cross_user_medal_clusters_no_results_below_threshold | tests/test_progress_check.py:337 |
| test_daily_check_blocks_cross_user_duplicate_and_logs_signal | tests/test_progress_check.py:345 |
| test_ratchet_no_improvement_returns_none | tests/test_quality_gate_report.py:67 |
| test_ratchet_updates_only_improved_complexity_metrics | tests/test_quality_gate_report.py:77 |
| test_ratchet_updates_coverage_only_when_it_improves | tests/test_quality_gate_report.py:92 |
| test_ratchet_does_not_lower_coverage_baseline | tests/test_quality_gate_report.py:104 |
| test_main_auto_ratchet_writes_improved_metrics | tests/test_quality_gate_report.py:114 |
| test_extract_page_no_markers_returns_truncated | tests/test_review.py:42 |
| test_extract_page_known_page | tests/test_review.py:48 |
| test_extract_page_last_page_no_trailing_marker | tests/test_review.py:55 |
| test_extract_page_missing_page_returns_fallback | tests/test_review.py:61 |
| test_extract_page_none_page_no | tests/test_review.py:67 |
| test_review_feladatok_accept | tests/test_review.py:79 |
| test_review_feladatok_skip | tests/test_review.py:89 |
| test_review_feladatok_quit_early | tests/test_review.py:96 |
| test_review_feladatok_empty | tests/test_review.py:111 |
| test_edit_feladat_cli_no_changes | tests/test_review.py:121 |
| test_edit_feladat_cli_changes_kerdes | tests/test_review.py:129 |
| test_edit_feladat_cli_invalid_neh_keeps_original | tests/test_review.py:156 |
| test_save_review_sets_review_elvegezve | tests/test_review.py:173 |
| test_save_review_clears_megoldas_hibajelezes | tests/test_review.py:180 |
| test_save_review_unknown_feladat_raises | tests/test_review.py:203 |
| test_review_elvegezve_roundtrips_via_upsert | tests/test_review.py:208 |
| test_build_review_chat_context_includes_attempt_buckets | tests/test_review_chat_context.py:10 |
| test_asset_path_resolution | tests/test_source_search.py:206 |
| test_pdf_summary_empty_dir_prints_hint | tests/test_status.py:8 |
| test_pdf_summary_groups_known_files | tests/test_status.py:14 |
| test_pdf_summary_unrecognized_names_are_reported | tests/test_status.py:29 |
| test_run_missing_paths_prints_missing_hints | tests/test_status.py:38 |
| test_run_calls_pdf_and_db_summaries_when_paths_exist | tests/test_status.py:55 |

## Gate Thresholds

- max_avg_cc_increase: 0.35
- max_p95_cc_increase: 1.25
- max_d_or_worse_increase: 3
- max_f_increase: 0
- max_block_cc_increase: 4.0
- max_significant_block_regressions: 1
- min-coverage-pct: 0.0
- max-coverage-drop: 1.0
- max_ruff_violations_increase: 5
- max_duplicate_pairs_increase: 2
- max_high_param_increase: 2
- max_unused_function_increase: 0

## Top Complex Blocks

| Rank | CC | Location |
|---|---:|---|
| F | 67.0 | src/felvi_games/progress_check.py:555 get_user_stats |
| E | 35.0 | src/felvi_games/app.py:123 next_feladat |
| E | 34.0 | src/felvi_games/app.py:647 _render_kerdes |
| E | 31.0 | src/felvi_games/cli.py:2958 _medal_promote_candidates_cmd |
| D | 29.0 | src/felvi_games/pdf_parser.py:711 run |
| D | 28.0 | src/felvi_games/app.py:254 _render_sidebar |
| D | 25.0 | src/felvi_games/cli.py:172 usage |
| D | 23.0 | src/felvi_games/achievements.py:396 check_new_medals |
| D | 23.0 | src/felvi_games/app.py:854 _render_eredmeny |
| D | 23.0 | src/felvi_games/cli.py:1488 _medal_check_simulate |
| D | 23.0 | src/felvi_games/cli.py:1608 _medal_check_dry_run |
| D | 23.0 | src/felvi_games/cli.py:2826 review_chat_marked_cmd |
| D | 22.0 | src/felvi_games/app.py:370 _render_settings_page |
| D | 22.0 | src/felvi_games/cli.py:2125 user_stats_cmd |
| D | 22.0 | src/felvi_games/cli.py:3324 _medal_compare_cmd |

## Copilot Summary

- Quality gate passed with warnings: small regressions detected (within tolerance).
- Review warnings above; refactor if the trend continues.
