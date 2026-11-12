#!/bin/bash
# RPG_Forge on a Mac — double-click to start the suite in your browser (the same as forge.bat on Windows).
# From Terminal it also runs any forge command: ./forge.command handoff in <name>   (= python -m forge handoff in <name>)
cd "$(dirname "$0")" || exit 1
if [ ! -x venv-mac/bin/python ]; then
  echo "Double-click install_mac.command first (once) — it sets up the suite for this Mac."
  read -r -p "Press Return to close." _; exit 1
fi
if [ $# -eq 0 ]; then
  echo "RPG_Forge suite — keep this window open while you use it; close it to stop the suite."
  exec venv-mac/bin/python -m forge suite
fi
exec venv-mac/bin/python -m forge "$@"
