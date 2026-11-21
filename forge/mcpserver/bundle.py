"""RPG_Forge's connector as an extension file for Claude's desktop app (BUILD 83) — the other way in.

    venv_mcp\\Scripts\\python.exe -m forge.mcpserver.bundle        writes local/mcp/rpg-forge.mcpb and says how to install it

Why: mcp_setup.bat puts the connector in Claude's settings file (claude_desktop_config.json). On William's PC (the Microsoft
Store install, 2026-11-19) the entry was in the file and the app never started it, after a full quit and restart: the forge's
log had no "the connector started" line. The app does start local connectors that are installed as extensions (Blender is
one), and it has a button for installing one from a file. This makes that file.

An extension file (.mcpb) is a zip with a manifest.json. Ours holds no code of the forge: it only says how to start the
connector that is already in this folder — the same command, arguments and PYTHONPATH that mcp_setup.bat's self-test runs.
So the paths in it belong to THIS computer; the file is written under local/ (never pushed) and is made again on any other
computer with the same command. Nothing outside the forge folder is written.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

NAME = "rpg-forge"
VERSION = "0.1.0"
TOOLS = [
    ("forge_status", "Everything at a glance: the art queue, the world queue and its backlog in hours, the never-stop "
                     "launcher, ComfyUI, the disk, and what waits for approval. Start here."),
    ("forge_search", "Finds the operation for what you want, with its exact input."),
    ("forge_call", "Runs one operation: op, input, who, dry_run, idempotency_key."),
    ("forge_job", "One art job, with its contact sheet as a picture."),
    ("forge_wait", "Waits up to 50 s for an art job, then shows it."),
    ("forge_area", "A place: its things on the world list and the game's own pictures of it."),
    ("forge_pictures", "Any picture inside the forge folder by path, downsized."),
]


def python_of(root: str, win: bool) -> str:
    """The connector's own Python (venv_mcp) under the forge folder, written the way that computer writes paths."""
    return root.rstrip("\\/") + ("\\venv_mcp\\Scripts\\python.exe" if win else "/venv_mcp/bin/python")


def manifest(root: str, win: bool) -> dict:
    """The extension's manifest: literal paths, no settings to fill in — the same start as server.config_block()."""
    return {
        "manifest_version": "0.3",
        "name": NAME,
        "display_name": "RPG Forge",
        "version": VERSION,
        "description": "Work the RPG_Forge art pipeline from a chat: the queues, the world list, places, approvals and the Mail.",
        "long_description": ("RPG_Forge as a connector. Claude can check the art queue and the world queue, add to the world "
                             "list, look at what was made, compile a place, approve (Claude Fable only, while allowed) and "
                             "write to the Mail. Every change goes through a function the Workbench already uses and is "
                             "signed by a Claude. It starts the connector that is in this computer's forge folder ("
                             + root + "); run mcp_setup.bat there once first."),
        "author": {"name": "William (photogbill) and Claude"},
        "license": "MIT",
        "server": {
            "type": "python",
            "entry_point": "server/launch.py",
            "mcp_config": {
                "command": python_of(root, win),
                "args": ["-m", "forge.mcpserver"],
                "env": {"PYTHONPATH": root},
            },
        },
        "tools": [{"name": n, "description": d} for n, d in TOOLS],
        "compatibility": {"platforms": ["win32"] if win else ["darwin", "linux"]},
    }


def launcher(root: str) -> str:
    """The bundle's entry point: starts the same connector by file, for an app that starts an extension that way."""
    return ('"""RPG_Forge\'s connector, started from the forge folder this extension was made for (forge/mcpserver/bundle.py).\n'
            'The extension\'s own settings start it directly (python -m forge.mcpserver); this file does the same thing."""\n'
            "import os\nimport runpy\nimport sys\n\n"
            f"ROOT = {root!r}\n"
            "sys.path.insert(0, ROOT)\n"
            'os.environ.setdefault("PYTHONPATH", ROOT)\n'
            'runpy.run_module("forge.mcpserver", run_name="__main__", alter_sys=True)\n')


def build(out: Path, root: str, win: bool) -> Path:
    """Write the extension file. Made whole beside its place, then moved in, so a half-made file is never left."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(root, win), indent=2))
        z.writestr("server/launch.py", launcher(root))
    with zipfile.ZipFile(tmp) as z:                              # read it back before it counts
        json.loads(z.read("manifest.json").decode("utf-8"))
        compile(z.read("server/launch.py").decode("utf-8"), "launch.py", "exec")
    tmp.replace(out)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    here = Path(__file__).resolve().parents[2]
    root, win = str(here), sys.platform == "win32"
    if "--root" in argv:                                         # made on one computer for another (a test, or a hand-over)
        root = argv[argv.index("--root") + 1]
        win = "--win" in argv or (":" in root[:3] and "--posix" not in argv)
    out = here / "local" / "mcp" / f"{NAME}.mcpb"
    if not win and "--root" not in argv and sys.platform != "darwin":
        print("Claude's desktop app installs extensions on Windows and macOS.")
    py = python_of(root, win)
    if "--root" not in argv and not Path(py).exists():
        print(f"The connector's own Python is not there yet ({py}). Run mcp_setup first.")
        return 1
    build(out, root, win)
    print(f"Made: {out}")
    print(f"It starts: {py} -m forge.mcpserver   (PYTHONPATH={root})\n")
    print("To install it in Claude's desktop app:")
    print("  1. Settings -> Desktop app -> Manage (beside Extensions).   Older layout: Settings -> Extensions.")
    print("  2. Advanced settings -> Extension Developer -> Install Extension...")
    print("  3. Pick this file: " + str(out))
    print("  4. Install. If its tools do not show, quit Claude fully and open it again.")
    print("\nThe same page has a 'Local MCP servers' section: RPG Forge should be listed there once it is running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
