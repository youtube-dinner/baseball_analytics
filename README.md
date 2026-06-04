# Fantasy Baseball Analytics

Daily fantasy baseball analytics for roster decisions, streaming pitchers, and free-agent hitter/pitcher targets.

## Main Outputs

- [Sortable browser dashboard](outputs/Fantasy_Baseball_Analytics_Sortable.html)
- [Formatted Excel workbook](outputs/Fantasy_Baseball_Analytics_Formatted.xlsx)
- [Stable CSV outputs](outputs/fantasy_baseball_analytics/)
- [Minor-league hitter star baselines](outputs/minor_league_hitter_stars/)

## Refresh

Run the full local refresh:

```bash
scripts/refresh_and_publish.sh
```

Run the refresh and publish changed tracked outputs to git:

```bash
scripts/refresh_and_publish.sh --publish
```

The publish step commits only when tracked files actually changed. It pushes only when a git remote is configured.

The default refresh targets tomorrow's probable starters. For a same-day morning refresh, run:

```bash
scripts/refresh_and_publish.sh --probable-date today --publish
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

By default, the nightly refresh computes `datePlaying` as the next Central Time date after the refresh date. For example, a June 3 nightly refresh queries Fantrax with `datePlaying=2026-06-04`. The morning refresh uses the current Central Time date instead. Only set `FANTRAX_PROBABLE_DATE_PLAYING` if Fantrax requires a different internal value. Keep these values in a local `.env` or automation environment only; `.env` files are ignored by git.

## Minor-League Hitter Baselines

Build 2025 FanGraphs minor-league hitter player rows and league-age averages. The tool pulls/loads each league separately by default so players who changed leagues do not get blended into one context:

```bash
/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 outputs/minor_league_hitter_stars.py --year 2025
```

If FanGraphs blocks the direct API pull, print per-league export URLs with `--print-export-urls`, export Standard, Advanced, and Batted Ball CSVs for each league, then pass their folder with `--csv-dir`.
