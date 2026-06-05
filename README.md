# Fantasy Baseball Analytics

Daily fantasy baseball analytics for roster decisions, streaming pitchers, and free-agent hitter/pitcher targets.

## Project Map

Core daily workflow:

- `scripts/refresh_and_publish.sh`: one-command refresh, rebuild, optional commit/push.
- `outputs/fantasy_baseball_analytics_pipeline.py`: main Fantrax, MLB, Baseball Savant, and trend pipeline.
- `outputs/fantrax_daily_export.py`: Fantrax export helper used by the refresh.
- `work/build_sortable_dashboard.py`: mobile-friendly sortable HTML dashboard builder.
- `work/spreadsheet_build/`: formatted Excel workbook build.
- `.github/workflows/morning-fantasy-refresh.yml`: scheduled GitHub refresh/publish workflow.

Active side workflows:

- `outputs/fantrax_transaction_audit.py`, `outputs/send_fantrax_pickup_report.py`, `scripts/run_fantrax_pickup_audit.sh`, and `.github/workflows/fantrax-pickup-audit.yml`: pickup tracking and reporting.
- `outputs/minor_league_hitter_stars.py`, `work/build_minor_league_hitter_dashboard.py`, `scripts/supervised_fangraphs_2026_refresh.sh`, and `outputs/minor_league_hitter_stars/`: minor-league hitter analytics.

## Main Outputs

- [Sortable browser dashboard](outputs/Fantasy_Baseball_Analytics_Sortable.html)
- [Minor League Hitter Analytics dashboard](outputs/Minor_League_Hitter_Analytics.html)
- [Formatted Excel workbook](outputs/Fantasy_Baseball_Analytics_Formatted.xlsx)
- [Stable CSV outputs](outputs/fantasy_baseball_analytics/)
- [Minor-league hitter star baselines](outputs/minor_league_hitter_stars/)
- [Latest refresh status](outputs/last_refresh_status.json)

## Refresh

Run the full local refresh:

```bash
scripts/refresh_and_publish.sh --probable-date auto
```

Run the refresh and publish changed tracked outputs to git:

```bash
scripts/refresh_and_publish.sh --probable-date auto --publish
```

The publish step commits only when tracked files actually changed. It pushes only when a git remote is configured.

The recommended streaming-pitcher mode is `auto`. It checks today's MLB schedule in Central Time. If no MLB game has reached its scheduled start, the refresh uses today's Fantrax probable starters; once any game has reached its scheduled start, it uses tomorrow's probable starters.

Manual overrides are still available:

```bash
scripts/refresh_and_publish.sh --probable-date today --publish
scripts/refresh_and_publish.sh --probable-date tomorrow --publish
scripts/refresh_and_publish.sh --probable-date 2026-06-06 --publish
```

To check whether the latest refresh ran successfully, open:

- `outputs/last_refresh_status.json` for status, timestamps, target probable date, and log path.
- `outputs/refresh_logs/latest_refresh.log` for the full command output from the latest run.

## Fantrax Probable Starters

The streaming-pitcher feed now tries Fantrax's authenticated player UI export first, then falls back to the MLB schedule feed if Fantrax auth is not available. To use the same probable-starter pool shown in Fantrax, set one of these local-only environment variables before the nightly job runs:

```bash
export FANTRAX_AUTH_COOKIE='your Fantrax browser cookie string'
export FANTRAX_OLD_UI_TOKEN='optional old UI token if using mobile/native export links'
```

Optional tuning:

```bash
export FANTRAX_PROBABLE_MISC_DISPLAY_TYPE=7
export FANTRAX_PROBABLE_DATE_PLAYING=2026-06-04
```

Only set `FANTRAX_PROBABLE_DATE_PLAYING` if Fantrax requires a different internal value. Keep these values in a local `.env` or automation environment only; `.env` files are ignored by git.

## Git And Local Files

The repo intentionally tracks the live dashboard, workbook, stable CSVs, and active scripts so GitHub Pages can serve the latest analytics from a phone.

Local-only files are ignored:

- `.env*` and Fantrax browser profiles/cookies.
- Python and Node build caches.
- raw Fantrax export history and refresh logs.
- old exploratory notebooks with local absolute paths.

If the working tree gets noisy, first check:

```bash
git status --short
```

Then commit only intentional code/output changes. Avoid committing local auth files, browser profiles, raw export history, or cache directories.

## Minor-League Hitter Baselines

Build 2025 FanGraphs minor-league hitter player rows and league-age averages. The tool pulls/loads each league separately by default so players who changed leagues do not get blended into one context:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 outputs/minor_league_hitter_stars.py --year 2025
```

If FanGraphs blocks the direct API pull, print per-league export URLs with `--print-export-urls`, export Standard, Advanced, and Batted Ball CSVs for each league, then pass their folder with `--csv-dir`.
