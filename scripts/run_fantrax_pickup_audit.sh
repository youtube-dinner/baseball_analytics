#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE="/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
PYTHON="/Users/emet_macbook_air/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"

export FANTRAX_BROWSER_PROFILE_DIR="${FANTRAX_BROWSER_PROFILE_DIR:-$ROOT/.fantrax-browser-profile}"
export FANTRAX_AUTH_COOKIE_FILE="${FANTRAX_AUTH_COOKIE_FILE:-$ROOT/outputs/fantrax_export/fantrax_auth_cookie_latest.txt}"

"$NODE" "$ROOT/scripts/fantrax_refresh_cookie_from_session.mjs"
"$PYTHON" "$ROOT/outputs/fantrax_transaction_audit.py" "$@"
