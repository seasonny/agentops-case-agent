#!/usr/bin/env bash
# Install mcp-shell-server for Case Agent exec provider (requires Python 3.11+).
set -euo pipefail

PYTHON="${PYTHON:-python3.11}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON not found. Install Python 3.11+ first." >&2
  exit 1
fi

"$PYTHON" -m pip install 'mcp-shell-server>=1.1.0'
echo "Installed: $($PYTHON -m pip show mcp-shell-server | awk '/^Version:/ {print $2}')"
echo "Entry point: $(command -v mcp-shell-server || echo '(not on PATH; reinstall or use full path)')"
echo "Config should use: {\"command\": \"$(command -v mcp-shell-server || echo /usr/local/bin/mcp-shell-server)\", \"args\": []}"
