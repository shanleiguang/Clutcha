#!/bin/bash
# Clutcha Bridge — start the bridge and open the web UI.
set -u
cd "$(dirname "$0")" || exit 1

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

if ! "$PY" -c 'import cryptography, qrcode' >/dev/null 2>&1; then
  printf '\n  Missing packages. Double-click install.command first.\n\n'
  printf '  Press Return to close this window…'
  read -r _
  exit 1
fi

exec "$PY" clutcha_bridge.py "$@"
