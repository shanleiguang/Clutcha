#!/bin/bash
# Clutcha Bridge — one-time setup. Creates .venv and installs two packages.
set -u
cd "$(dirname "$0")" || exit 1

say() { printf '%s\n' "$1"; }
pause() { printf '\nPress Return to close this window…'; read -r _; }

say "Clutcha Bridge — setup"
say "----------------------"

if ! command -v python3 >/dev/null 2>&1; then
  say ""
  say "python3 was not found."
  say "Install the Command Line Tools first:  xcode-select --install"
  pause
  exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
say "Found python3 $PY_VERSION"

if [ -x ".venv/bin/python" ] && .venv/bin/python -c 'import cryptography, qrcode' >/dev/null 2>&1; then
  say "Already installed — nothing to do."
  pause
  exit 0
fi

say "Creating .venv …"
if python3 -m venv .venv >/dev/null 2>&1 && [ -x ".venv/bin/python" ]; then
  .venv/bin/python -m pip install --quiet --upgrade pip >/dev/null 2>&1
  say "Installing cryptography and qrcode …"
  if .venv/bin/python -m pip install --quiet cryptography qrcode; then
    say ""
    say "Done. Now double-click start.command."
  else
    say ""
    say "Install failed. Try running this by hand and read the error:"
    say "  .venv/bin/python -m pip install cryptography qrcode"
  fi
else
  # Some Python builds ship without ensurepip. Fall back to the user site.
  say "Virtualenv unavailable — installing into your user site-packages instead."
  if pip3 install --user cryptography qrcode; then
    say ""
    say "Done. Now double-click start.command."
  else
    say ""
    say "Install failed. On newer Homebrew Python, try:"
    say "  pip3 install --user --break-system-packages cryptography qrcode"
  fi
fi

pause
