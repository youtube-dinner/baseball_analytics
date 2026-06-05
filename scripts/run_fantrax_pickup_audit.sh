#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE="/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
PYTHON="/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"

if [[ -f "$ROOT/.env.fantrax_report" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.fantrax_report"
  set +a
fi

export FANTRAX_BROWSER_PROFILE_DIR="${FANTRAX_BROWSER_PROFILE_DIR:-$ROOT/.fantrax-browser-profile}"
export FANTRAX_AUTH_COOKIE_FILE="${FANTRAX_AUTH_COOKIE_FILE:-$ROOT/outputs/fantrax_export/fantrax_auth_cookie_latest.txt}"

if [[ "${FANTRAX_SKIP_BROWSER_REFRESH:-0}" != "1" ]]; then
  "$NODE" "$ROOT/scripts/fantrax_refresh_cookie_from_session.mjs"
fi
"$PYTHON" "$ROOT/outputs/fantrax_transaction_audit.py" "$@"

notify_args=()
if [[ "${FANTRAX_REPORT_EMAIL:-0}" == "1" ]]; then
  notify_args+=(--email)
fi
if [[ "${FANTRAX_REPORT_GROUPME:-0}" == "1" ]]; then
  notify_args+=(--groupme)
fi
if [[ "${#notify_args[@]}" -gt 0 ]]; then
  "$PYTHON" "$ROOT/outputs/send_fantrax_pickup_report.py" "${notify_args[@]}"
fi
