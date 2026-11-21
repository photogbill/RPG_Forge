#!/bin/bash
# The connector for Claude on a Mac (BUILD 83): venv_mcp, the MCP library, the self-test, Claude's settings.
cd "$(dirname "$0")" || exit 1
if [ ! -x venv-mac/bin/python ] && [ ! -x venv/bin/python ]; then echo "Run install_mac.command first."; read -r -p "Press Return to close."; exit 1; fi
BASE=venv-mac/bin/python; [ -x "$BASE" ] || BASE=venv/bin/python
[ -x venv_mcp/bin/python ] || "$BASE" -m venv venv_mcp || { echo "Could not make venv_mcp."; read -r -p "Press Return to close."; exit 1; }
venv_mcp/bin/python -m pip install --upgrade pip >/dev/null
venv_mcp/bin/python -m pip install -r requirements-mcp.txt || { echo "The install did not finish."; read -r -p "Press Return to close."; exit 1; }
venv_mcp/bin/python -m forge.mcpserver --check || { echo "The self-test did not pass."; read -r -p "Press Return to close."; exit 1; }
venv_mcp/bin/python -m forge.mcpserver.claude_settings
read -r -p "Press Return to close."
