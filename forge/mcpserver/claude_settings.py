"""Put RPG_Forge in Claude's desktop app settings (BUILD 83) — the last step of mcp_setup.bat, and only if William says yes.

    venv_mcp\\Scripts\\python.exe -m forge.mcpserver.claude_settings          asks first
    … --show                                                                  only shows the lines, changes nothing

    … --after-extension                                                       mcp_extension.bat's last step (below)

With yes: Claude's settings file (claude_desktop_config.json) gets one entry, "rpg-forge", under "mcpServers"; every other
entry in it (Blender's, any other) is kept exactly; a copy of the file as it was is kept beside it first. This is the one
file outside the forge it ever writes, and only when asked. With no: the lines go on the clipboard (Windows) with where
to paste them. Either way, Claude must be quit fully and opened again to see the connector.

BUILD 84 part 4 — two things learned on William's PC (2026-11-19):
  * The Microsoft Store install of Claude had the entry in its settings file and never started the connector, after a
    full quit and restart. It started at once as an extension (mcp_extension.bat). So this step now says which install
    it found, and on a Store install it says to use the extension way.
  * The settings entry and the extension both call the connector "rpg-forge". If an app ever starts both, two connectors
    carry one name. `--after-extension` looks for the settings entry and offers to take it out (a copy of the file kept
    first, every other entry kept exactly).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .server import config_block

NAME = "rpg-forge"


def settings_file() -> Path | None:
    """Where Claude's desktop app keeps its settings on this computer, or None when it can't be found."""
    cands: list[Path] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:                                                  # the Microsoft Store install keeps its own copy
            for pkg in sorted(Path(local, "Packages").glob("*Claude*")):
                cands.append(pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
        if os.environ.get("APPDATA"):
            cands.append(Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json")
    elif sys.platform == "darwin":
        cands.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        cands.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")
    for c in cands:
        if c.exists():
            return c
    for c in cands:
        if c.parent.is_dir():
            return c
    return None


def merge(path: Path, block: dict) -> tuple[str, Path | None]:
    """Add the entry; keep everything else. Returns (what happened, the backup)."""
    data: dict = {}
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        data = json.loads(text) if text else {}
        if not isinstance(data, dict):
            raise ValueError("Claude's settings file is not the shape expected — nothing was changed")
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("\"mcpServers\" in Claude's settings is not the shape expected — nothing was changed")
    if servers.get(NAME) == block[NAME]:
        return "already there — nothing changed", None
    backup = None
    if path.exists():
        backup = path.with_name(f"claude_desktop_config.before-rpg-forge-{datetime.now():%Y%m%d-%H%M%S}.json")
        shutil.copyfile(path, backup)
    servers[NAME] = block[NAME]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return "added", backup


def is_store_install(path: Path | None) -> bool:
    """Whether this settings file belongs to the Microsoft Store install of Claude (…/Packages/<Claude…>/LocalCache/…)."""
    if path is None:
        return False
    parts = [x.lower() for x in Path(path).parts]
    return any(a == "packages" and "claude" in b and c == "localcache" for a, b, c in zip(parts, parts[1:], parts[2:]))


def has_entry(path: Path | None) -> bool:
    """Whether the settings file has the connector's entry (False when it is missing or not readable)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else {}
        return isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) and NAME in data["mcpServers"]
    except (OSError, ValueError):
        return False


def remove(path: Path) -> tuple[str, Path | None]:
    """Take the connector's entry out of the settings file; keep everything else. Returns (what happened, the backup)."""
    if not path.exists():
        return "there is no settings file — nothing changed", None
    text = path.read_text(encoding="utf-8").strip()
    data = json.loads(text) if text else {}
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict) or NAME not in data["mcpServers"]:
        return "not there — nothing changed", None
    backup = path.with_name(f"claude_desktop_config.before-rpg-forge-removed-{datetime.now():%Y%m%d-%H%M%S}.json")
    shutil.copyfile(path, backup)
    del data["mcpServers"][NAME]
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return "removed", backup


EXTENSION_WAY = ("If Claude shows no forge tools after a full quit and restart: double-click mcp_extension.bat. It makes "
                 "the connector an extension file and says where Claude's Install button is.")


def after_extension(path: Path | None, ask=input) -> int:
    """mcp_extension.bat's last step: one name, two ways in — offer to take the settings-file entry out."""
    if not has_entry(path):
        print("Claude's settings file has no rpg-forge entry: the extension is the only way in. Nothing to tidy.")
        return 0
    print(f"Claude's settings file ({path}) also has an rpg-forge entry, from mcp_setup.")
    print("The extension carries the same name. If Claude ever starts both, two connectors answer to one name. Once the "
          "extension is installed, the settings entry is not needed.")
    yes = str(ask("Take the settings entry out now? A copy of the file as it is now is kept beside it. [Y/N] ")).strip().lower()
    if not yes.startswith("y"):
        print("Left as it is. To take it out later: run mcp_extension.bat again, or delete the \"rpg-forge\" entry in "
              "Settings -> Developer -> Edit Config.")
        return 0
    try:
        what, backup = remove(path)
    except (OSError, ValueError) as ex:
        print(f"Not changed: {ex}")
        return 0
    print(f"Done: {what}." + (f" The copy from before: {backup.name}" if backup else ""))
    return 0


def to_clipboard(text: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None, ask=input) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    block = config_block()
    entry = json.dumps(block, indent=2)
    inner = entry.strip()[1:-1].strip()                       # "rpg-forge": {...}, ready to sit inside "mcpServers"
    path = settings_file()
    if "--after-extension" in argv:
        return after_extension(path, ask)
    print("The connector's entry for Claude's settings:\n")
    print(entry + "\n")
    if "--show" in argv:
        return 0
    if path is not None:
        print(f"Claude's settings file on this computer: {path}")
        if is_store_install(path):
            print("This is the Microsoft Store install of Claude. On William's PC that install kept the entry and never "
                  "started the connector; the extension way (mcp_extension.bat) worked at once. You can say N here and go "
                  "straight to mcp_extension.bat.")
        yes = str(ask("Add RPG_Forge to it for you? A copy of the file as it is now is kept beside it. [Y/N] ")).strip().lower()
        if yes.startswith("y"):
            try:
                what, backup = merge(path, block)
            except (OSError, ValueError) as ex:
                print(f"\nNot changed: {ex}")
            else:
                print(f"\nDone: {what}." + (f" The copy from before: {backup.name}" if backup else ""))
                print("Now quit Claude fully (right-click its icon by the clock -> Quit) and open it again. In a new chat, "
                      "Claude can use the forge's tools (forge_status first).")
                print(EXTENSION_WAY)
                return 0
    else:
        print("Claude's settings file was not found on this computer (is the Claude desktop app installed?).")
    pasted = to_clipboard(inner)
    print(("\nThe lines are on the clipboard. " if pasted else "\nCopy the lines above. ") +
          "In Claude: Settings -> Developer -> Edit Config opens the file. Paste them inside \"mcpServers\": { … } "
          "(add a comma after the entry before it, if there is one), save, quit Claude fully and open it again.")
    print(EXTENSION_WAY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
