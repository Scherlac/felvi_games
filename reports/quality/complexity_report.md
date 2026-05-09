# Code Quality Gate Report

Generated at (UTC): 2026-05-09T21:35:58+00:00
Scope: src, tests

## Gate

QUALITY_GATE: FAIL

Reasons:
- Coverage dropped by 1.546 (> 1.0).
- Ruff violations increased by 20 (> 5).
- Duplicate code pairs increased by 3 (> 2).
- High-parameter functions increased by 4 (> 2).

## Current Snapshot

- Python files: 31
- LOC: 16495 (SLOC: 12582, Blank: 2497)
- Avg MI: 40.044
- Avg CC: 4.453
- P95 CC: 15.0
- Rank counts: A=529, B=81, C=37, D=13, E=4, F=1
- D/E/F blocks: 18
- F blocks: 1
- Parse-error files: 0
- Coverage: 51.212%

## Coverage

- Total line coverage: 51.212%
- Files measured: 16
- Coverage source: fresh test run via --coverage-command
- Coverage status: OK

### Lowest Coverage Files

| Coverage % | Covered/Statements | File |
|---:|---:|---|
| 0.0 | 0/435 | src/felvi_games/report.py |
| 0.0 | 0/187 | src/felvi_games/scraper.py |
| 22.921 | 328/1431 | src/felvi_games/cli.py |
| 42.857 | 51/119 | src/felvi_games/ai.py |
| 50.314 | 80/159 | src/felvi_games/review.py |
| 64.126 | 286/446 | src/felvi_games/condition_registry.py |
| 65.091 | 179/275 | src/felvi_games/achievements.py |
| 75.0 | 54/72 | src/felvi_games/status.py |
| 75.296 | 381/506 | src/felvi_games/progress_check.py |
| 76.471 | 221/289 | src/felvi_games/pdf_parser.py |

## Code Repetition

- Structural duplicate function pairs: 23

| Clones | Body Size | Location A | Location B |
|---:|---:|---|---|
| 3 | 31 | tests/conftest.py:28 feladat_matek | tests/test_cli_review.py:30 feladat |
| 3 | 30 | src/felvi_games/report.py:41 accuracy_pct | src/felvi_games/report.py:55 accuracy_pct |
| 3 | 27 | src/felvi_games/condition_registry.py:814 _eval_play_days | src/felvi_games/condition_registry.py:823 _eval_day_streak |
| 3 | 26 | tests/test_pdf_parser.py:122 test_matek_feladatlap | tests/test_pdf_parser.py:126 test_magyar_utmutato |
| 3 | 24 | src/felvi_games/condition_registry.py:454 _eval_feladat_count | src/felvi_games/condition_registry.py:464 _eval_pont_sum |
| 3 | 24 | tests/test_medal_assets.py:31 _asset_path | tests/test_medal_assets.py:45 _asset_path |
| 3 | 20 | src/felvi_games/condition_registry.py:931 _count_play_days | src/felvi_games/condition_registry.py:938 _count_day_streak |
| 3 | 19 | src/felvi_games/condition_registry.py:551 _count_feladat_count | src/felvi_games/condition_registry.py:558 _count_pont_sum |
| 2 | 106 | src/felvi_games/condition_registry.py:274 _q_megoldas_count | src/felvi_games/condition_registry.py:307 _q_menet_count |
| 2 | 51 | tests/test_db.py:225 test_save_megoldas_helyes | tests/test_db.py:232 test_save_megoldas_helytelen |


## Cohesion

- Classes analyzed: 36
- Avg LCOM1: 0.815 (0=cohesive, 1=disconnected)

### Low-Cohesion Classes (LCOM1 > 0.7)

| LCOM1 | Class | File |
|---:|---|---|
| 1.0 | AwardabilityNow | src/felvi_games/achievements.py:380 |
| 1.0 | Ertekeles | src/felvi_games/models.py:311 |
| 1.0 | TestInit | tests/test_db.py:41 |
| 1.0 | TestUpsert | tests/test_db.py:58 |
| 1.0 | TestGet | tests/test_db.py:84 |
| 1.0 | TestAll | tests/test_db.py:106 |
| 1.0 | TestTtsAssets | tests/test_db.py:153 |
| 1.0 | TestMegoldas | tests/test_db.py:224 |
| 1.0 | TestDynamicEventConditions | tests/test_db.py:263 |
| 1.0 | TestFeladatWithAssets | tests/test_db.py:391 |


## Interface Complexity

- Public functions analyzed: 428
- Avg parameters: 1.645
- High-parameter functions (> 5 params): 21
- Untyped public functions (no return annotation): 180

### High-Parameter Functions

| Params | Function | File |
|---:|---|---|
| 16 | medals | src/felvi_games/cli.py:310 |
| 13 | medal_edit_cmd | src/felvi_games/cli.py:936 |
| 11 | medal_add_cmd | src/felvi_games/cli.py:899 |
| 10 | medal_promote_candidates_cmd | src/felvi_games/cli.py:2287 |
| 8 | check_answer | src/felvi_games/ai.py:124 |
| 8 | refine_daily_medal | src/felvi_games/ai.py:468 |
| 8 | parse | src/felvi_games/cli.py:118 |
| 8 | wrong_cmd | src/felvi_games/cli.py:1139 |
| 8 | reeval_cmd | src/felvi_games/cli.py:1745 |
| 8 | save_megoldas | src/felvi_games/db.py:871 |


## Ruff Lint

- Total violations: 42
- By category: E=31, F=6, I=5
- Ruff status: OK

## Baseline Delta

- Baseline timestamp: 2026-05-09T14:32:48+00:00
- Delta avg_cc: 0.04
- Delta p95_cc: 0.0
- Delta D/E/F blocks: 1
- Delta F blocks: 0
- Delta parse-error files: 0
- Delta coverage_pct: -1.546
- Delta ruff_violations: 20
- Delta duplicate_block_pairs: 3
- Delta high_param_count: 4

Notes:
- ⚠️ WARNING: Avg CC +0.04 (within tolerance 0.35).
- ⚠️ WARNING: D/E/F block count +1 (within tolerance 3).

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

## Top Complex Blocks

| Rank | CC | Location |
|---|---:|---|
| F | 55.0 | src/felvi_games/progress_check.py:542 get_user_stats |
| E | 35.0 | src/felvi_games/app.py:123 next_feladat |
| E | 35.0 | src/felvi_games/cli.py:1745 reeval_cmd |
| E | 34.0 | src/felvi_games/app.py:647 _render_kerdes |
| E | 31.0 | src/felvi_games/cli.py:2287 medal_promote_candidates_cmd |
| D | 29.0 | src/felvi_games/pdf_parser.py:711 run |
| D | 28.0 | src/felvi_games/app.py:254 _render_sidebar |
| D | 25.0 | src/felvi_games/cli.py:164 usage |
| D | 23.0 | src/felvi_games/achievements.py:442 check_new_medals |
| D | 23.0 | src/felvi_games/app.py:854 _render_eredmeny |
| D | 23.0 | src/felvi_games/cli.py:1413 _medal_check_simulate |
| D | 23.0 | src/felvi_games/cli.py:1533 _medal_check_dry_run |
| D | 22.0 | src/felvi_games/app.py:370 _render_settings_page |
| D | 22.0 | src/felvi_games/cli.py:1931 user_stats_cmd |
| D | 22.0 | src/felvi_games/cli.py:2653 medal_compare_cmd |

## Copilot Summary

- Quality gate failed: significant regression detected.
- Refactor the listed high-complexity blocks before merge.
