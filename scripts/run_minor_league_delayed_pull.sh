#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE="${NODE:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
PYTHON="${PYTHON:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3}"
EXPORTER="$ROOT/outputs/fangraphs_minor_league_browser_export.mjs"
ANALYTICS="$ROOT/outputs/minor_league_hitter_stars.py"
EXPORT_DIR="$ROOT/outputs/minor_league_hitter_stars/fangraphs_exports"
OUTPUT_BASE="$ROOT/outputs/minor_league_hitter_stars"
LEAGUES="${LEAGUES:-2,4,5,6,7,11,14,13,8,9,10,16,17,30}"
MIN_DELAY_SEC="${MIN_DELAY_SEC:-60}"
MAX_DELAY_SEC="${MAX_DELAY_SEC:-90}"

run_year() {
  local year="$1"
  echo "Exporting FanGraphs minor-league hitter reports for $year"
  "$NODE" "$EXPORTER" \
    --year "$year" \
    --leagues "$LEAGUES" \
    --out-dir "$EXPORT_DIR" \
    --min-delay-sec "$MIN_DELAY_SEC" \
    --max-delay-sec "$MAX_DELAY_SEC"

  echo "Building minor-league hitter analytics for $year"
  "$PYTHON" "$ANALYTICS" \
    --year "$year" \
    --leagues "$LEAGUES" \
    --csv-dir "$EXPORT_DIR/$year" \
    --out-dir "$OUTPUT_BASE/$year"
}

run_year 2025
run_year 2026
