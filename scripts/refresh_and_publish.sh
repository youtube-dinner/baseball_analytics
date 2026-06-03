#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3}"
NODE="${NODE:-/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
PUBLISH=0

if [[ "${1:-}" == "--publish" ]]; then
  PUBLISH=1
fi

cd "$ROOT"

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

git push origin HEAD
