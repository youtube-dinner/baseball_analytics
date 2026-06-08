#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.fantasy-baseball.fantrax-pickup-audit"
PLIST_SRC="$ROOT/scripts/$LABEL.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DEST"
launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "Scheduled hourly from 5:38 AM through 11:38 PM in the Mac's local timezone."
echo "Logs:"
echo "$ROOT/outputs/fantrax_export/fantrax_pickup_audit_launchd.log"
echo "$ROOT/outputs/fantrax_export/fantrax_pickup_audit_launchd.err"
