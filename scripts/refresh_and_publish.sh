#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3}"
NODE="${NODE:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
PUBLISH=0
PROBABLE_DATE_MODE=""

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

"$PYTHON" outputs/fantasy_baseball_analytics_pipeline.py
"$PYTHON" work/spreadsheet_build/build_workbook_data.py
"$NODE" work/spreadsheet_build/build_fantasy_workbook.mjs
"$PYTHON" work/build_sortable_dashboard.py

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
