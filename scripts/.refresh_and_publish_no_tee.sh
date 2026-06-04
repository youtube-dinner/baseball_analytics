#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3}"
NODE="${NODE:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
PUBLISH=0
PROBABLE_DATE_MODE=""
RUN_STARTED_AT="$(TZ=America/Chicago date '+%Y-%m-%dT%H:%M:%S%z')"
RUN_ID="$(TZ=UTC date '+%Y%m%dT%H%M%SZ')"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --publish)
      PUBLISH=1
      shift
      ;;
    --probable-date)
      PROBABLE_DATE_MODE="${2:?Missing value for --probable-date}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$ROOT"

LOG_DIR="$ROOT/outputs/refresh_logs"
LOG_FILE="$LOG_DIR/latest_refresh.log"
STATUS_FILE="$ROOT/outputs/last_refresh_status.json"
mkdir -p "$LOG_DIR"
# sandbox-disabled: exec > >(tee "$LOG_FILE") 2>&1

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PROBABLE_DATE_MODE="${PROBABLE_DATE_MODE:-${FANTRAX_PROBABLE_DATE:-tomorrow}}"

case "$PROBABLE_DATE_MODE" in
  today)
    export FANTRAX_PROBABLE_DATE="$(TZ=America/Chicago date +%F)"
    ;;
  tomorrow)
    export FANTRAX_PROBABLE_DATE="$(TZ=America/Chicago date -v+1d +%F)"
    ;;
  *)
    export FANTRAX_PROBABLE_DATE="$PROBABLE_DATE_MODE"
    ;;
esac

GIT_HEAD_START="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

write_refresh_status() {
  local status="$1"
  local exit_code="$2"
  local message="$3"
  local ended_at
  local git_head_end
  ended_at="$(TZ=America/Chicago date '+%Y-%m-%dT%H:%M:%S%z')"
  git_head_end="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  "$PYTHON" -c 'import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = {
    "run_id": sys.argv[2],
    "status": sys.argv[3],
    "exit_code": int(sys.argv[4]),
    "message": sys.argv[5],
    "started_at_local": sys.argv[6],
    "ended_at_local": sys.argv[7],
    "probable_date_mode": sys.argv[8],
    "fantrax_probable_date": sys.argv[9],
    "publish_requested": sys.argv[10] == "1",
    "log_file": sys.argv[11],
    "git_head_start": sys.argv[12],
    "git_head_end": sys.argv[13],
}
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
' "$STATUS_FILE" "$RUN_ID" "$status" "$exit_code" "$message" "$RUN_STARTED_AT" "$ended_at" "$PROBABLE_DATE_MODE" "$FANTRAX_PROBABLE_DATE" "$PUBLISH" "outputs/refresh_logs/latest_refresh.log" "$GIT_HEAD_START" "$git_head_end" || true
}

finish_refresh() {
  local exit_code=$?
  if [[ "$exit_code" -ne 0 ]]; then
    write_refresh_status "failed" "$exit_code" "Refresh failed before outputs completed. See latest_refresh.log."
  fi
  exit "$exit_code"
}
trap finish_refresh EXIT

echo "Refresh run id: $RUN_ID"
echo "Started local: $RUN_STARTED_AT"
echo "Probable date mode: $PROBABLE_DATE_MODE"
echo "Fantrax probable date: $FANTRAX_PROBABLE_DATE"

"$PYTHON" outputs/fantasy_baseball_analytics_pipeline.py
"$PYTHON" work/spreadsheet_build/build_workbook_data.py
"$NODE" work/spreadsheet_build/build_fantasy_workbook.mjs
"$PYTHON" work/build_sortable_dashboard.py

write_refresh_status "success" 0 "Outputs rebuilt successfully. If publish is requested, commit/push happens after this status is written."

if [[ "$PUBLISH" -eq 0 ]]; then
  exit 0
fi

git add README.md index.html .gitignore scripts work outputs

if git diff --cached --quiet; then
  echo "No tracked refresh changes to commit."
  exit 0
fi

git commit -m "Refresh fantasy baseball analytics outputs"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "No git remote named origin is configured; skipping push."
  exit 0
fi

if ! git push origin HEAD; then
  echo "Git push failed; local refresh and commit completed."
  exit 0
fi
