# Code Quality Gate Report

Generated at (UTC): 2026-05-03T11:12:03+00:00
Scope: src, tests

## Gate

QUALITY_GATE: PASS

Reasons:
- No significant regression vs baseline.

## Current Snapshot

- Python files: 29
- LOC: 15421 (SLOC: 11832, Blank: 2299)
- Avg MI: 40.353
- Avg CC: 4.487
- P95 CC: 15.0
- Rank counts: A=494, B=64, C=33, D=11, E=5, F=1
- D/E/F blocks: 17
- F blocks: 1
- Parse-error files: 0
- Coverage: 52.47%

## Coverage

- Total line coverage: 52.47%
- Files measured: 14
- Coverage source: fresh test run via --coverage-command
- Coverage status: OK

### Lowest Coverage Files

| Coverage % | Covered/Statements | File |
|---:|---:|---|
| 0.0 | 0/422 | src/felvi_games/report.py |
| 0.0 | 0/187 | src/felvi_games/scraper.py |
| 25.162 | 311/1236 | src/felvi_games/cli.py |
| 46.667 | 49/105 | src/felvi_games/ai.py |
| 50.314 | 80/159 | src/felvi_games/review.py |
| 66.775 | 412/617 | src/felvi_games/achievements.py |
| 75.0 | 54/72 | src/felvi_games/status.py |
| 76.471 | 221/289 | src/felvi_games/pdf_parser.py |
| 76.499 | 319/417 | src/felvi_games/progress_check.py |
| 80.364 | 221/275 | src/felvi_games/models.py |

## Code Repetition

- Structural duplicate function pairs: 20

| Clones | Body Size | Location A | Location B |
|---:|---:|---|---|
| 6 | 103 | src/felvi_games/achievements.py:464 _rule_szaz_feladat | src/felvi_games/achievements.py:476 _rule_otszaz_feladat |
| 4 | 44 | src/felvi_games/achievements.py:614 _rule_het_egymas_utan | src/felvi_games/achievements.py:620 _rule_harom_het_egymas_utan |
| 3 | 31 | tests/conftest.py:28 feladat_matek | tests/test_cli_review.py:30 feladat |
| 3 | 30 | src/felvi_games/report.py:40 accuracy_pct | src/felvi_games/report.py:54 accuracy_pct |
| 3 | 27 | src/felvi_games/achievements.py:521 _rule_sorozat_5 | src/felvi_games/achievements.py:525 _rule_sorozat_10 |
| 3 | 26 | tests/test_pdf_parser.py:122 test_matek_feladatlap | tests/test_pdf_parser.py:126 test_magyar_utmutato |
| 3 | 24 | tests/test_medal_assets.py:31 _asset_path | tests/test_medal_assets.py:45 _asset_path |
| 2 | 102 | src/felvi_games/achievements.py:771 _rule_szaz_pont | src/felvi_games/achievements.py:783 _rule_otszaz_pont |
| 2 | 94 | src/felvi_games/achievements.py:847 _dyn_feladat_count | src/felvi_games/achievements.py:904 _dyn_session_count |
| 2 | 51 | tests/test_db.py:225 test_save_megoldas_helyes | tests/test_db.py:232 test_save_megoldas_helytelen |


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

- Public functions analyzed: 397
- Avg parameters: 1.622
- High-parameter functions (> 5 params): 17
- Untyped public functions (no return annotation): 179

### High-Parameter Functions

| Params | Function | File |
|---:|---|---|
| 13 | medal_edit_cmd | src/felvi_games/cli.py:812 |
| 12 | medals | src/felvi_games/cli.py:308 |
| 11 | medal_add_cmd | src/felvi_games/cli.py:775 |
| 10 | medal_promote_candidates_cmd | src/felvi_games/cli.py:2220 |
| 8 | check_answer | src/felvi_games/ai.py:124 |
| 8 | refine_daily_medal | src/felvi_games/ai.py:468 |
| 8 | parse | src/felvi_games/cli.py:118 |
| 8 | wrong_cmd | src/felvi_games/cli.py:1015 |
| 8 | reeval_cmd | src/felvi_games/cli.py:1635 |
| 8 | save_megoldas | src/felvi_games/db.py:867 |


## Ruff Lint

- Total violations: 46
- By category: E=22, F=2, U=22
- Ruff status: OK

## Baseline Delta

- Baseline timestamp: 2026-05-03T10:46:31+00:00
- Delta avg_cc: -0.035
- Delta p95_cc: -1.0
- Delta D/E/F blocks: -1
- Delta F blocks: -1
- Delta parse-error files: 0
- Delta coverage_pct: -0.135
- Delta ruff_violations: 0
- Delta duplicate_block_pairs: 0
- Delta high_param_count: 0

Notes:
- ⚠️ WARNING: Coverage -00.135% (within tolerance 1.0%).

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
| E | 35.0 | src/felvi_games/cli.py:1635 reeval_cmd |
| E | 34.0 | src/felvi_games/app.py:647 _render_kerdes |
| E | 34.0 | src/felvi_games/cli.py:1981 medal_recheck_cmd |
| E | 31.0 | src/felvi_games/cli.py:2220 medal_promote_candidates_cmd |
| D | 29.0 | src/felvi_games/pdf_parser.py:711 run |
| D | 28.0 | src/felvi_games/achievements.py:1228 check_new_medals |
| D | 28.0 | src/felvi_games/app.py:254 _render_sidebar |
| D | 26.0 | src/felvi_games/cli.py:1289 _medal_check_simulate |
| D | 25.0 | src/felvi_games/cli.py:164 usage |
| D | 25.0 | src/felvi_games/cli.py:1416 _medal_check_dry_run |
| D | 23.0 | src/felvi_games/app.py:849 _render_eredmeny |
| D | 22.0 | src/felvi_games/app.py:370 _render_settings_page |
| D | 22.0 | src/felvi_games/cli.py:1821 user_stats_cmd |

## Copilot Summary

- Quality gate passed with warnings: small regressions detected (within tolerance).
- Review warnings above; refactor if the trend continues.
