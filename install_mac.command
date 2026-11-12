#!/bin/bash
# RPG_Forge on a Mac — double-click once in Finder. It makes the forge's own Python environment beside the code
# (venv-mac/, so a folder shared with Windows never mixes the two) and installs only what the suite needs.
# It installs nothing system-wide. The art worker (making pictures) runs on the Windows PC with the NVIDIA card.
cd "$(dirname "$0")" || exit 1
echo "== RPG_Forge — installing the suite for this Mac =="
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo
  echo "Python 3.11 or newer isn't on this Mac. Get the macOS installer from https://www.python.org/downloads/macos/ , run it, then double-click this file again."
  read -r -p "Press Return to close." _; exit 1
fi
echo "Using $("$PY" --version) ($(command -v "$PY"))"
if [ ! -x venv-mac/bin/python ]; then
  "$PY" -m venv venv-mac || { echo "Couldn't make venv-mac/."; read -r -p "Press Return to close." _; exit 1; }
fi
venv-mac/bin/python -m pip install --upgrade pip >/dev/null
venv-mac/bin/python -m pip install -r requirements-suite.txt || { echo "Installing the suite's packages failed (above)."; read -r -p "Press Return to close." _; exit 1; }
mkdir -p local logs
echo
echo "Done. Double-click forge.command to start the suite."
read -r -p "Press Return to close." _
