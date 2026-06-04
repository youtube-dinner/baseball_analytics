# Minor League Hitter Stars

This tool builds a 2025 minor-league hitter baseline by league and age, using FanGraphs minor-league hitter leaderboards.

By default it treats each league as a separate pull/export unit. That matters because players can move levels during a season, and an all-leagues leaderboard can blend their context.

## Outputs

- `minor_league_hitters_2025.csv`: player/team/league rows with FanGraphs Standard columns, plus requested Advanced and Batted Ball fields.
- `league_age_hitter_baselines_2025.csv`: average numeric metrics grouped by `League` and `Age`.
- `league_hitter_baselines_2025.csv`: overall weighted league averages without age splits.
- `wrc_metric_correlations_2025.csv`: league-agnostic player-row correlations between each standard analytic and `wRC+`.
- `wrc_metric_scatterplots_2025.html`: league-agnostic scatterplot grid for each standard analytic vs `wRC+`.
- `metric_pair_correlations_2025.csv`: league-agnostic player-row correlations for selected metric pairs, currently `LD%` vs `2B_3B_pct`.
- `metric_pair_scatterplots_2025.html`: scatterplots for selected metric pairs.
- `combined_league_hitter_baselines_through_2026.csv`: combined weighted league baselines from the complete 2025 exports plus the current 2026 exports.
- `combined_league_age_hitter_baselines_through_2026.csv`: combined weighted league-age baselines from the complete 2025 exports plus the current 2026 exports.
- `minor_league_hitters_2026_plus_vs_combined_baseline.csv`: 2026 player/league rows with plus-style scores against the combined league-age baseline.
- `minor_league_hitter_analytics_dashboard.csv`: curated dashboard data for the sortable minor-league hitter table.
- `../../Minor_League_Hitter_Analytics.html`: sortable and filterable browser dashboard.

## Run

Use the bundled Python runtime from Codex, because the system Python may not have pandas:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 outputs/minor_league_hitter_stars.py --year 2025
```

FanGraphs may return `403 Forbidden` for direct API calls. If that happens, print the per-league export URLs:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 outputs/minor_league_hitter_stars.py --year 2025 --print-export-urls
```

For each league, export these three reports:

- Standard
- Advanced
- Batted Ball

Save them in a folder with names like:

- `2_standard.csv`
- `2_advanced.csv`
- `2_batted.csv`
- `4_standard.csv`
- `4_advanced.csv`
- `4_batted.csv`

Then run:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 outputs/minor_league_hitter_stars.py \
  --year 2025 \
  --csv-dir /path/to/fangraphs-per-league-exports
```

For a current 2026 refresh that compares against the complete 2025 data plus whatever 2026 exports are present, run:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 outputs/minor_league_hitter_stars.py \
  --year 2026 \
  --csv-dir outputs/minor_league_hitter_stars/fangraphs_exports/2026 \
  --out-dir outputs/minor_league_hitter_stars/2026 \
  --combined-baseline-csv-dirs outputs/minor_league_hitter_stars/fangraphs_exports/2025,outputs/minor_league_hitter_stars/fangraphs_exports/2026
```

If you really do want an all-leagues combined leaderboard, pass `--combined-leagues` with `--standard-csv`, `--advanced-csv`, and `--batted-csv`.

The merged player output keeps all Standard report columns and adds `League Name`, `League Level`, `BB/K`, `Spd`, `wRC+`, `HR/FB%`, `IFFB%`, `LD%`, and `FB%` when present. If the Standard inputs include the Fantrax hitting scoring categories, the script also adds `1B`, `FGPts_est`, and `FGPts_per_game`.

## Standard Analytics

The player output adds these derived analytics:

- `FGPts_per_game`: estimated Fantrax fantasy points divided by games, using the same category-based hitter scoring logic as `fantasy_baseball_analytics_pipeline.py`.
- `BB_K_ratio`: walks divided by strikeouts.
- `Speed_score`: FanGraphs `Spd`.
- `HR_IFFB_ratio`: `HR/FB%` divided by `IFFB%`, which estimates how many home runs a hitter produces per infield fly ball. FanGraphs CSV exports already store these rate columns as decimal rates, so the tool only divides by 100 when the raw CSV value literally contains a `%` character.
- `LD%`: FanGraphs line-drive rate, normalized as a decimal rate.
- `2B_3B_pct`: doubles plus triples divided by at-bats.

The league-age and overall league baseline outputs are weighted instead of a straight average of player rows:

- `FGPts_per_game`: total estimated Fantrax fantasy points divided by total games.
- `BB_K_ratio`: total walks divided by total strikeouts.
- `Speed_score`: PA-weighted average.
- `HR_IFFB_ratio`: PA-weighted `HR/FB%` divided by PA-weighted `IFFB%`, which keeps the two shared-denominator rate components on the same weighting basis.
- `LD%`: PA-weighted average.
- `2B_3B_pct`: total doubles plus triples divided by total at-bats.
- `wRC+`: PA-weighted average.
- `Average Age`: PA-weighted average age.

The `wRC+` correlation outputs are league agnostic: they use all finite player rows together instead of grouping by league.

The metric-pair correlation outputs are also league agnostic.

## Combined Baseline Comparisons

When `--combined-baseline-csv-dirs` is supplied, the script rebuilds weighted baselines from every complete league/report set in those folders. This keeps the complete 2025 season as the larger baseline source while letting current 2026 data contribute in proportion to its current playing-time totals.

The player comparison output uses the combined league baseline. Scores are plus-style indexes where `100` is the matching league average:

- `Age_Plus`: inverse age index, so younger than the baseline age is above `100`.
- `FGPts_per_game_Plus`, `BB_K_ratio_Plus`, `Speed_score_Plus`, `HR_IFFB_ratio_Plus`, `LD%_Plus`, `2B_3B_pct_Plus`: player metric divided by baseline metric, multiplied by `100`.
- `wRC+_Score`: raw player `wRC+`, because `wRC+` is already indexed.
- `5 Tool+`: average of `Age_Plus`, `BB_K_ratio_Plus`, `Speed_score_Plus`, `HR_IFFB_ratio_Plus`, and `LD%_Plus`.
- `Slugger Plus`: average of `Age_Plus`, `BB_K_ratio_Plus`, and `HR_IFFB_ratio_Plus`.
- `Contact+`: average of `Age_Plus`, `Speed_score_Plus`, and `LD%_Plus`.
- `Team League Max G`: maximum games played by any player on that team in that league.
- `Player Team Game Share`: player games divided by `Team League Max G`.

Zero-valued player metrics are excluded when building the league-average denominator for plus scores. Players with a zero metric still receive a `0` plus score for that metric.

The sortable dashboard has two views:

- `All Players`: concise view for every 2026 player/league row.
- `Bobby and the NitWitts`: roster-only view sorted by league, then `FP/G` descending, with every retained FanGraphs Advanced and Batted Ball export column appended after `OPS`.

Build the dashboard after refreshing 2026:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/build_minor_league_hitter_dashboard.py
```

## Fantasy Points Formula

The main fantasy analytics pipeline calculates hitter points from Fantrax league scoring settings, not from the FanGraphs standard points constants. This tool now uses the same category logic:

```text
1B, 2B, 3B, HR, R, RBI, BB, SO, SB, CS, HBP, GIDP, SH
```

By default it reads the latest local Fantrax `league_info.json`; pass `--league-info-json` to use a specific file. If no local league settings are available, it falls back to the most recent local weights:

```text
1B=2.5, 2B=4, 3B=6, HR=8, R=2, RBI=4, BB=2, SO=-1, SB=5, CS=-2, HBP=1, GIDP=-1, SH=2
```

FanGraphs exports the double-play column as `GDP`; this tool maps it to the Fantrax `GIDP` scoring category.

## League Reference

The script adds `League Name` and `League Level` from the FanGraphs minor-league leaderboard links:

```text
2=International League (AAA)
4=Pacific Coast League (AAA)
5=Eastern League (AA)
6=Southern League (AA)
7=Texas League (AA)
11=Midwest League (A+)
14=South Atlantic League (A+)
13=Northwest League (A+)
8=California League (A)
9=Carolina League (A)
10=Florida State League (A)
16=Arizona Complex League (CPX)
17=Florida Complex League (CPX)
30=Dominican Summer League (R)
```

## Browser Automation Notes

Direct Python requests to FanGraphs returned `403 Forbidden`, but a real browser session can load the minor-league leaderboard and expose the `Export Data` link as an in-page CSV payload.

The browser export experiment successfully saved per-league CSVs for league IDs `2`, `4`, and `5`, then FanGraphs/Cloudflare switched the browser to a security verification page on league ID `6`. The partial browser exports were saved in:

```text
outputs/minor_league_hitter_stars/fangraphs_browser_exports_2025/
```

Those three leagues processed end to end into:

```text
outputs/minor_league_hitter_stars/browser_test_outputs/
```

The browser test output includes `BB/K`, `Spd`, `HR/FB%`, `IFFB%`, `LD%`, and `FGPts_est`.

A standalone Playwright exporter exists at:

```text
outputs/fangraphs_minor_league_browser_export.mjs
```

It is resumable, skips existing files by default, and waits a random 30-45 seconds between FanGraphs page loads:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node outputs/fangraphs_minor_league_browser_export.mjs \
  --years 2025,2026 \
  --out-dir outputs/minor_league_hitter_stars/fangraphs_exports \
  --min-delay-sec 30 \
  --max-delay-sec 45
```

The full pull-and-process wrapper is:

```bash
scripts/run_minor_league_delayed_pull.sh
```

That wrapper completes 2025 exports and analytics first, then starts 2026 with the same delay settings.

For the current season, use the supervised 2026-only refresh job:

```bash
scripts/supervised_fangraphs_2026_refresh.sh
```

It opens a headful browser by default, overwrites the existing 2026 exports, waits a random 30-45 seconds between FanGraphs page loads, then rebuilds the 2026 analytics outputs and `Minor_League_Hitter_Analytics.html`. Logs are written to:

```text
outputs/refresh_logs/minor_league_2026_supervised_refresh_*.log
```

Useful overrides:

```bash
MIN_DELAY_SEC=45 MAX_DELAY_SEC=75 scripts/supervised_fangraphs_2026_refresh.sh
OVERWRITE=0 scripts/supervised_fangraphs_2026_refresh.sh
LEAGUES=11,14 scripts/supervised_fangraphs_2026_refresh.sh
```

It needs a local Playwright browser binary before it can run outside the Codex in-app browser. In this workspace, Playwright was available but its Chromium binary was not installed, and the browser install was blocked by the local approval/usage limit.
