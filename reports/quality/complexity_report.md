# Code Quality Gate Report

Generated at (UTC): 2026-05-09T15:22:24+00:00
Scope: src, tests

## Gate

QUALITY_GATE: PASS

Reasons:
- No significant regression vs baseline.

## Current Snapshot

- Python files: 30
- LOC: 15469 (SLOC: 11793, Blank: 2351)
- Avg MI: 41.413
- Avg CC: 4.455
- P95 CC: 15.0
- Rank counts: A=500, B=69, C=32, D=11, E=5, F=1
- D/E/F blocks: 17
- F blocks: 1
- Parse-error files: 0
- Coverage: 52.196%

## Coverage

- Total line coverage: 52.196%
- Files measured: 15
- Coverage source: cached .coverage (2.52 min old)
- Coverage status: OK

### Lowest Coverage Files

| Coverage % | Covered/Statements | File |
|---:|---:|---|
| 0.0 | 0/435 | src/felvi_games/report.py |
| 0.0 | 0/187 | src/felvi_games/scraper.py |
| 25.84 | 323/1250 | src/felvi_games/cli.py |
| 46.667 | 49/105 | src/felvi_games/ai.py |
| 50.314 | 80/159 | src/felvi_games/review.py |
| 62.951 | 401/637 | src/felvi_games/achievements.py |
| 75.0 | 54/72 | src/felvi_games/status.py |
| 76.471 | 221/289 | src/felvi_games/pdf_parser.py |
| 76.499 | 319/417 | src/felvi_games/progress_check.py |
| 80.364 | 221/275 | src/felvi_games/models.py |

## Code Repetition

- Structural duplicate function pairs: 20

| Clones | Body Size | Location A | Location B |
|---:|---:|---|---|
| 3 | 34 | src/felvi_games/achievements.py:292 _make_megoldas_count_rule | src/felvi_games/achievements.py:298 _make_pont_sum_rule |
| 3 | 31 | tests/conftest.py:28 feladat_matek | tests/test_cli_review.py:30 feladat |
| 3 | 30 | src/felvi_games/report.py:41 accuracy_pct | src/felvi_games/report.py:55 accuracy_pct |
| 3 | 26 | src/felvi_games/achievements.py:293 _rule | src/felvi_games/achievements.py:299 _rule |
| 3 | 26 | tests/test_pdf_parser.py:122 test_matek_feladatlap | tests/test_pdf_parser.py:126 test_magyar_utmutato |
| 3 | 24 | tests/test_medal_assets.py:31 _asset_path | tests/test_medal_assets.py:45 _asset_path |
| 2 | 120 | src/felvi_games/achievements.py:686 _query_megoldas_count | src/felvi_games/achievements.py:724 _query_menet_count |
| 2 | 53 | src/felvi_games/achievements.py:316 _make_streak_rule | src/felvi_games/achievements.py:324 _make_longest_streak_rule |
| 2 | 51 | tests/test_db.py:225 test_save_megoldas_helyes | tests/test_db.py:232 test_save_megoldas_helytelen |
| 2 | 46 | tests/test_pdf_parser.py:520 test_single_task_detected | tests/test_pdf_parser.py:527 test_multiple_tasks_split_correctly |


## Cohesion

- Classes analyzed: 34
- Avg LCOM1: 0.833 (0=cohesive, 1=disconnected)

### Low-Cohesion Classes (LCOM1 > 0.7)

| LCOM1 | Class | File |
|---:|---|---|
| 1.0 | Ertekeles | src/felvi_games/models.py:311 |
| 1.0 | TestInit | tests/test_db.py:41 |
| 1.0 | TestUpsert | tests/test_db.py:58 |
| 1.0 | TestGet | tests/test_db.py:84 |
| 1.0 | TestAll | tests/test_db.py:106 |
| 1.0 | TestTtsAssets | tests/test_db.py:153 |
| 1.0 | TestMegoldas | tests/test_db.py:224 |
| 1.0 | TestDynamicEventConditions | tests/test_db.py:263 |
| 1.0 | TestFeladatWithAssets | tests/test_db.py:391 |
| 1.0 | TestFelhasznalo | tests/test_db.py:414 |


## Interface Complexity

- Public functions analyzed: 398
- Avg parameters: 1.621
- High-parameter functions (> 5 params): 17
- Untyped public functions (no return annotation): 179

### High-Parameter Functions

| Params | Function | File |
|---:|---|---|
| 13 | medal_edit_cmd | src/felvi_games/cli.py:838 |
| 12 | medals | src/felvi_games/cli.py:310 |
| 11 | medal_add_cmd | src/felvi_games/cli.py:801 |
| 10 | medal_promote_candidates_cmd | src/felvi_games/cli.py:2246 |
| 8 | check_answer | src/felvi_games/ai.py:124 |
| 8 | refine_daily_medal | src/felvi_games/ai.py:468 |
| 8 | parse | src/felvi_games/cli.py:118 |
| 8 | wrong_cmd | src/felvi_games/cli.py:1041 |
| 8 | reeval_cmd | src/felvi_games/cli.py:1661 |
| 8 | save_megoldas | src/felvi_games/db.py:867 |


## Ruff Lint

- Total violations: 22
- By category: E=21, F=1
- Ruff status: OK

## Baseline Delta

- Baseline timestamp: 2026-05-09T14:32:48+00:00
- Delta avg_cc: 0.042
- Delta p95_cc: 0.0
- Delta D/E/F blocks: 0
- Delta F blocks: 0
- Delta parse-error files: 0
- Delta coverage_pct: -0.562
- Delta ruff_violations: 0
- Delta duplicate_block_pairs: 0
- Delta high_param_count: 0

Notes:
- ⚠️ WARNING: Avg CC +0.042 (within tolerance 0.35).
- ⚠️ WARNING: Coverage -00.562% (within tolerance 1.0%).

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
| F | 55.0 | src/felvi_games/progress_check.py:397 get_user_stats |
| E | 35.0 | src/felvi_games/app.py:123 next_feladat |
| E | 35.0 | src/felvi_games/cli.py:1661 reeval_cmd |
| E | 34.0 | src/felvi_games/app.py:647 _render_kerdes |
| E | 34.0 | src/felvi_games/cli.py:2007 medal_recheck_cmd |
| E | 31.0 | src/felvi_games/cli.py:2246 medal_promote_candidates_cmd |
| D | 29.0 | src/felvi_games/pdf_parser.py:711 run |
| D | 28.0 | src/felvi_games/app.py:254 _render_sidebar |
| D | 26.0 | src/felvi_games/cli.py:1315 _medal_check_simulate |
| D | 25.0 | src/felvi_games/cli.py:164 usage |
| D | 25.0 | src/felvi_games/cli.py:1442 _medal_check_dry_run |
| D | 23.0 | src/felvi_games/achievements.py:1165 check_new_medals |
| D | 23.0 | src/felvi_games/app.py:854 _render_eredmeny |
| D | 22.0 | src/felvi_games/app.py:370 _render_settings_page |
| D | 22.0 | src/felvi_games/cli.py:1847 user_stats_cmd |

## Copilot Summary

- Quality gate passed with warnings: small regressions detected (within tolerance).
- Review warnings above; refactor if the trend continues.
