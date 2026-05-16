# Code Quality Gate Report

Generated at (UTC): 2026-05-16T11:19:49+00:00
Scope: src, tests

## Gate

QUALITY_GATE: PASS

Reasons:
- No significant regression vs baseline.

## Current Snapshot

- Python files: 44
- LOC: 20111 (SLOC: 15670, Blank: 2991)
- Avg MI: 40.381
- Avg CC: 4.416
- P95 CC: 14.0
- Rank counts: A=625, B=109, C=46, D=14, E=3, F=1
- D/E/F blocks: 18
- F blocks: 1
- Parse-error files: 0
- Unused top-level functions: 71
- Coverage: 56.332%

## Coverage

- Total line coverage: 56.332%
- Files measured: 21
- Coverage source: fresh test run via --coverage-command
- Coverage status: OK

### Lowest Coverage Files

| Coverage % | Covered/Statements | File |
|---:|---:|---|
| 0.0 | 0/432 | src/felvi_games/report.py |
| 0.0 | 0/73 | src/felvi_games/review_chainlit_app.py |
| 0.0 | 0/179 | src/felvi_games/scraper.py |
| 30.713 | 504/1641 | src/felvi_games/cli.py |
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
| 3 | 26 | tests/test_pdf_parser.py:122 test_matek_feladatlap | tests/test_pdf_parser.py:126 test_magyar_utmutato |
| 3 | 24 | tests/test_medal_assets.py:31 _asset_path | tests/test_medal_assets.py:45 _asset_path |
| 3 | 22 | tests/test_achievements_dynamic_conditions.py:144 wrapped_query | tests/test_achievements_dynamic_conditions.py:199 wrapped_query |
| 3 | 20 | src/felvi_games/condition_registry.py:578 _count_play_days | src/felvi_games/condition_registry.py:584 _count_day_streak |
| 3 | 18 | src/felvi_games/kpi_definitions.py:30 _attempt_timestamp | src/felvi_games/kpi_definitions.py:104 _session_timestamp |


## Cohesion

- Classes analyzed: 41
- Avg LCOM1: 0.826 (0=cohesive, 1=disconnected)

### Low-Cohesion Classes (LCOM1 > 0.7)

| LCOM1 | Class | File |
|---:|---|---|
| 1.0 | AwardabilityNow | src/felvi_games/achievements.py:334 |
| 1.0 | Ertekeles | src/felvi_games/models.py:311 |
| 1.0 | ReviewQuery | src/felvi_games/review_check_shared.py:17 |
| 1.0 | TestReviewCli | tests/test_cli_review.py:71 |
| 1.0 | TestInit | tests/test_db.py:41 |
| 1.0 | TestUpsert | tests/test_db.py:58 |
| 1.0 | TestGet | tests/test_db.py:84 |
| 1.0 | TestAll | tests/test_db.py:106 |
| 1.0 | TestTtsAssets | tests/test_db.py:153 |
| 1.0 | TestMegoldas | tests/test_db.py:224 |


## Interface Complexity

- Public functions analyzed: 442
- Avg parameters: 1.477
- High-parameter functions (> 5 params): 16
- Untyped public functions (no return annotation): 186

### High-Parameter Functions

| Params | Function | File |
|---:|---|---|
| 10 | register | src/felvi_games/kpi_registry.py:220 |
| 8 | check_answer | src/felvi_games/ai.py:124 |
| 8 | refine_daily_medal | src/felvi_games/ai.py:468 |
| 8 | save_megoldas | src/felvi_games/db.py:871 |
| 8 | log_interakcio | src/felvi_games/db.py:1357 |
| 8 | kpi_parameter | src/felvi_games/kpi_registry.py:270 |
| 8 | run | src/felvi_games/pdf_parser.py:711 |
| 7 | eval_condition | src/felvi_games/condition_registry.py:216 |
| 7 | eval_conditions | src/felvi_games/condition_registry.py:238 |
| 7 | kpi_rows | src/felvi_games/kpi_registry.py:300 |


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

## Ruff Lint

- Total violations: 7
- By category: E=7
- Ruff status: OK

## Baseline Delta

- Baseline timestamp: 2026-05-13T22:06:30+00:00
- Delta avg_cc: 0.039
- Delta p95_cc: -1.0
- Delta D/E/F blocks: 0
- Delta F blocks: 0
- Delta parse-error files: 0
- Delta coverage_pct: 1.855
- Delta ruff_violations: 0
- Delta duplicate_block_pairs: 2
- Delta high_param_count: 1
- Delta unused_function_count: -4

Notes:
- WARNING: Avg CC +0.039 (within tolerance 0.35).
- WARNING: Duplicate pairs +2 (within tolerance 2).
- WARNING: High-param functions +1 (within tolerance 2).

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
| E | 31.0 | src/felvi_games/cli.py:2910 _medal_promote_candidates_cmd |
| D | 29.0 | src/felvi_games/pdf_parser.py:711 run |
| D | 28.0 | src/felvi_games/app.py:254 _render_sidebar |
| D | 25.0 | src/felvi_games/cli.py:172 usage |
| D | 23.0 | src/felvi_games/achievements.py:396 check_new_medals |
| D | 23.0 | src/felvi_games/app.py:854 _render_eredmeny |
| D | 23.0 | src/felvi_games/cli.py:1488 _medal_check_simulate |
| D | 23.0 | src/felvi_games/cli.py:1608 _medal_check_dry_run |
| D | 23.0 | src/felvi_games/cli.py:2778 review_chat_marked_cmd |
| D | 22.0 | src/felvi_games/app.py:370 _render_settings_page |
| D | 22.0 | src/felvi_games/cli.py:2125 user_stats_cmd |
| D | 22.0 | src/felvi_games/cli.py:3276 _medal_compare_cmd |

## Copilot Summary

- Quality gate passed with warnings: small regressions detected (within tolerance).
- Review warnings above; refactor if the trend continues.
