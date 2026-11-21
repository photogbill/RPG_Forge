#!/bin/bash
# Rhubarb Lip Sync for the voice bench (BUILD 71), the macOS build, into tools/rhubarb/.
cd "$(dirname "$0")"
[ -d venv-mac ] || { echo "Run install_mac.command first."; read -r; exit 1; }
venv-mac/bin/python -m forge voice get rhubarb
read -r -p "Press Return to close."
