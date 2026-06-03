# Fantasy Baseball Analytics

Daily fantasy baseball analytics for roster decisions, streaming pitchers, and free-agent hitter/pitcher targets.

## Main Outputs

- [Sortable browser dashboard](outputs/Fantasy_Baseball_Analytics_Sortable.html)
- [Formatted Excel workbook](outputs/Fantasy_Baseball_Analytics_Formatted.xlsx)
- [Stable CSV outputs](outputs/fantasy_baseball_analytics/)

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
