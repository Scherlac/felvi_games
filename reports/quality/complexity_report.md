# Code Quality Gate Report

Generated at (UTC): 2026-05-09T21:48:37+00:00
Scope: src, tests

## Gate

QUALITY_GATE: PASS

Reasons:
- No significant regression vs baseline.

## Current Snapshot

- Python files: 31
- LOC: 16618 (SLOC: 12702, Blank: 2500)
- Avg MI: 40.013
- Avg CC: 4.457
- P95 CC: 15.0
- Rank counts: A=529, B=81, C=37, D=13, E=4, F=1
- D/E/F blocks: 18
- F blocks: 1
- Parse-error files: 0
- Coverage: 51.172%

## Coverage

- Total line coverage: 51.172%
- Files measured: 16
- Coverage source: fresh test run via --coverage-command
- Coverage status: OK

### Lowest Coverage Files

| Coverage % | Covered/Statements | File |
|---:|---:|---|
| 0.0 | 0/435 | src/felvi_games/report.py |
| 0.0 | 0/187 | src/felvi_games/scraper.py |
| 22.915 | 327/1427 | src/felvi_games/cli.py |
| 42.857 | 51/119 | src/felvi_games/ai.py |
| 50.314 | 80/159 | src/felvi_games/review.py |
| 63.02 | 288/457 | src/felvi_games/condition_registry.py |
| 65.217 | 180/276 | src/felvi_games/achievements.py |
| 75.0 | 54/72 | src/felvi_games/status.py |
| 75.296 | 381/506 | src/felvi_games/progress_check.py |
| 76.471 | 221/289 | src/felvi_games/pdf_parser.py |

## Code Repetition

- Structural duplicate function pairs: 23

| Clones | Body Size | Location A | Location B |
|---:|---:|---|---|
| 3 | 31 | tests/conftest.py:28 feladat_matek | tests/test_cli_review.py:30 feladat |
| 3 | 30 | src/felvi_games/report.py:41 accuracy_pct | src/felvi_games/report.py:55 accuracy_pct |
| 3 | 26 | tests/test_pdf_parser.py:122 test_matek_feladatlap | tests/test_pdf_parser.py:126 test_magyar_utmutato |
| 3 | 24 | tests/test_medal_assets.py:31 _asset_path | tests/test_medal_assets.py:45 _asset_path |
| 2 | 106 | src/felvi_games/condition_registry.py:275 _q_megoldas_count | src/felvi_games/condition_registry.py:308 _q_menet_count |
| 2 | 51 | tests/test_db.py:225 test_save_megoldas_helyes | tests/test_db.py:232 test_save_megoldas_helytelen |
| 2 | 47 | src/felvi_games/condition_registry.py:420 _max_streak | src/felvi_games/progress_check.py:883 _max_streak |
| 2 | 46 | tests/test_pdf_parser.py:520 test_single_task_detected | tests/test_pdf_parser.py:527 test_multiple_tasks_split_correctly |
| 2 | 44 | src/felvi_games/condition_registry.py:485 _eval_before_hour | src/felvi_games/condition_registry.py:489 _eval_after_hour |
| 2 | 44 | src/felvi_games/db.py:688 get | src/felvi_games/db.py:760 get_csoport |


## Cohesion

- Classes analyzed: 36
- Avg LCOM1: 0.815 (0=cohesive, 1=disconnected)

### Low-Cohesion Classes (LCOM1 > 0.7)

| LCOM1 | Class | File |
|---:|---|---|
| 1.0 | AwardabilityNow | src/felvi_games/achievements.py:381 |
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

- Public functions analyzed: 425
- Avg parameters: 1.598
- High-parameter functions (> 5 params): 19
- Untyped public functions (no return annotation): 180

### High-Parameter Functions

| Params | Function | File |
|---:|---|---|
| 16 | medals | src/felvi_games/cli.py:310 |
| 11 | medal_add_cmd | src/felvi_games/cli.py:916 |
| 8 | check_answer | src/felvi_games/ai.py:124 |
| 8 | refine_daily_medal | src/felvi_games/ai.py:468 |
| 8 | parse | src/felvi_games/cli.py:118 |
| 8 | wrong_cmd | src/felvi_games/cli.py:1158 |
| 8 | reeval_cmd | src/felvi_games/cli.py:1783 |
| 8 | save_megoldas | src/felvi_games/db.py:871 |
| 8 | log_interakcio | src/felvi_games/db.py:1357 |
| 8 | run | src/felvi_games/pdf_parser.py:711 |


## Ruff Lint

- Total violations: 7
- By category: E=7
- Ruff status: OK

## Baseline Delta

- Baseline timestamp: 2026-05-09T14:32:48+00:00
- Delta avg_cc: 0.044
- Delta p95_cc: 0.0
- Delta D/E/F blocks: 1
- Delta F blocks: 0
- Delta parse-error files: 0
- Delta coverage_pct: -1.586
- Delta ruff_violations: -15
- Delta duplicate_block_pairs: 3
- Delta high_param_count: 2

Notes:
- ⚠️ WARNING: Avg CC +0.044 (within tolerance 0.35).
- ⚠️ WARNING: D/E/F block count +1 (within tolerance 3).
- ⚠️ WARNING: Coverage -01.586% (within tolerance 1.75%).
- ⚠️ WARNING: Duplicate pairs +3 (within tolerance 3).
- ⚠️ WARNING: High-param functions +2 (within tolerance 2).

## Gate Thresholds

- max_avg_cc_increase: 0.35
- max_p95_cc_increase: 1.25
- max_d_or_worse_increase: 3
- max_f_increase: 0
- max_block_cc_increase: 4.0
- max_significant_block_regressions: 1
- min-coverage-pct: 0.0
- max-coverage-drop: 1.75
- max_ruff_violations_increase: 5
- max_duplicate_pairs_increase: 3
- max_high_param_increase: 2

## Top Complex Blocks

| Rank | CC | Location |
|---|---:|---|
| F | 55.0 | src/felvi_games/progress_check.py:553 get_user_stats |
| E | 35.0 | src/felvi_games/app.py:123 next_feladat |
| E | 35.0 | src/felvi_games/cli.py:1783 reeval_cmd |
| E | 34.0 | src/felvi_games/app.py:647 _render_kerdes |
| E | 31.0 | src/felvi_games/cli.py:2328 _medal_promote_candidates_cmd |
| D | 29.0 | src/felvi_games/pdf_parser.py:711 run |
| D | 28.0 | src/felvi_games/app.py:254 _render_sidebar |
| D | 25.0 | src/felvi_games/cli.py:164 usage |
| D | 23.0 | src/felvi_games/achievements.py:443 check_new_medals |
| D | 23.0 | src/felvi_games/app.py:854 _render_eredmeny |
| D | 23.0 | src/felvi_games/cli.py:1435 _medal_check_simulate |
| D | 23.0 | src/felvi_games/cli.py:1555 _medal_check_dry_run |
| D | 22.0 | src/felvi_games/app.py:370 _render_settings_page |
| D | 22.0 | src/felvi_games/cli.py:1969 user_stats_cmd |
| D | 22.0 | src/felvi_games/cli.py:2694 _medal_compare_cmd |

## Copilot Summary

- Quality gate passed with warnings: small regressions detected (within tolerance).
- Review warnings above; refactor if the trend continues.
