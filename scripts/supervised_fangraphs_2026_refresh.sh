#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE="${NODE:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
PYTHON="${PYTHON:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3}"
EXPORTER="$ROOT/outputs/fangraphs_minor_league_browser_export.mjs"
ANALYTICS="$ROOT/outputs/minor_league_hitter_stars.py"
DASHBOARD="$ROOT/work/build_minor_league_hitter_dashboard.py"
EXPORT_DIR="$ROOT/outputs/minor_league_hitter_stars/fangraphs_exports"
OUTPUT_BASE="$ROOT/outputs/minor_league_hitter_stars"
LOG_DIR="$ROOT/outputs/refresh_logs"
LEAGUES="${LEAGUES:-2,4,5,6,7,11,14,13,8,9,10,16,17,30}"
MIN_DELAY_SEC="${MIN_DELAY_SEC:-30}"
MAX_DELAY_SEC="${MAX_DELAY_SEC:-45}"
YEAR="${YEAR:-2026}"
OVERWRITE="${OVERWRITE:-1}"
HEADFUL="${HEADFUL:-1}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/minor_league_${YEAR}_supervised_refresh_$(date +%Y%m%d_%H%M%S).log"

export_args=(
  --year "$YEAR"
  --leagues "$LEAGUES"
  --out-dir "$EXPORT_DIR"
  --min-delay-sec "$MIN_DELAY_SEC"
  --max-delay-sec "$MAX_DELAY_SEC"
)

if [[ "$HEADFUL" == "1" ]]; then
  export_args+=(--headful)
fi

if [[ "$OVERWRITE" == "1" ]]; then
  export_args+=(--overwrite)
fi

{
  echo "Started supervised FanGraphs minor-league refresh at $(date)"
  echo "Year: $YEAR"
  echo "Leagues: $LEAGUES"
  echo "Delay: ${MIN_DELAY_SEC}-${MAX_DELAY_SEC}s"
  echo "Headful browser: $HEADFUL"
  echo "Overwrite existing exports: $OVERWRITE"
  echo

  echo "Exporting FanGraphs minor-league hitter reports"
  "$NODE" "$EXPORTER" "${export_args[@]}"

  echo
  echo "Building minor-league hitter analytics"
  "$PYTHON" "$ANALYTICS" \
    --year "$YEAR" \
    --leagues "$LEAGUES" \
    --csv-dir "$EXPORT_DIR/$YEAR" \
    --out-dir "$OUTPUT_BASE/$YEAR" \
    --combined-baseline-csv-dirs "$EXPORT_DIR/2025,$EXPORT_DIR/$YEAR"

  echo
  echo "Building minor-league hitter dashboard"
  "$PYTHON" "$DASHBOARD"

  echo
  echo "Finished supervised FanGraphs minor-league refresh at $(date)"
  echo "Log file: $LOG_FILE"
} 2>&1 | tee "$LOG_FILE"
