"""Per-install settings for the suite: who is using this install, which game opens first, local folder overrides.

Kept in `local/suite.json` beside the forge (git-ignored — it is this PC's, not the public repo's). Nothing is written
to C: or a user-profile folder.

- **identity** — "who am I": the name every journal line, approval and letter is signed with (the person at this PC,
  each assistant session, later anyone else). The environment variable FORGE_IDENTITY wins, so a session signs as itself
  on William's install without changing his setting.
- **default_game / last_game** — which game the suite and the commands open when not told (`--game`).
- **timezone** — an IANA name (e.g. "America/New_York"). On Windows the clock is already local and this is unused;
  a session's Linux shell runs on UTC, and this keeps its journal lines in the same local time as the GUI's.
- **game_roots** — where a game's folder is on *this* machine when it differs from `forge.game.json` → `game_root`
  (the environment variable FORGE_GAME_ROOTS, a JSON object, wins; used by sessions that see the folder elsewhere).
"""
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod

PATH = cfgmod.ROOT / "local" / "suite.json"


def load(path: Path | None = None) -> dict:
    p = path or PATH
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d: dict, path: Path | None = None) -> None:
    p = path or PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def update(path: Path | None = None, **kv) -> dict:
    d = load(path)
    d.update(kv)
    save(d, path)
    return d


def identity(path: Path | None = None) -> str | None:
    who = (os.environ.get("FORGE_IDENTITY") or "").strip()
    if who:
        return who
    who = str(load(path).get("identity") or "").strip()
    return who or None


def set_identity(name: str, path: Path | None = None) -> str:
    name = " ".join(str(name).split())
    if not name or len(name) > 60:
        raise ValueError("a name is 1–60 characters")
    update(path, identity=name)
    return name


def is_assistant(who: str | None) -> bool:
    """An AI collaborator (signs 'Claude …'). Assistants propose changes to anything a person approved."""
    return bool(who) and str(who).strip().lower().startswith("claude")


def game_root_override(game_id: str, path: Path | None = None) -> str | None:
    env = os.environ.get("FORGE_GAME_ROOTS")
    if env:
        try:
            v = json.loads(env).get(game_id)
            if v:
                return str(v)
        except (ValueError, AttributeError):
            pass
    v = (load(path).get("game_roots") or {}).get(game_id)
    return str(v) if v else None


def now(path: Path | None = None) -> datetime:
    """Local wall-clock time for journal lines, backups and proposals — the same on William's PC and in a session's
    Linux shell (which runs on UTC). FORGE_TZ, then `timezone` in local/suite.json; Windows needs neither."""
    if os.name == "nt":
        return datetime.now()
    tz = os.environ.get("FORGE_TZ") or load(path).get("timezone")
    if tz:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(str(tz))).replace(tzinfo=None)
        except Exception:  # noqa: BLE001 — an unknown zone falls back to the machine's clock
            pass
    return datetime.now()


# ---------------------------------------------------------------- BUILD 27: this computer's answers (Settings → This computer)
KEYS = ("timezone", "godot", "worker_pc")


def set_game_root(game_id: str, folder: str | None, path: Path | None = None) -> dict:
    """Where a game's folder is on *this* computer ('' or None forgets it, back to forge.game.json's answer)."""
    d = load(path)
    roots = dict(d.get("game_roots") or {})
    folder = str(folder or "").strip().strip('"')
    if folder:
        roots[str(game_id)] = folder
    else:
        roots.pop(str(game_id), None)
    d["game_roots"] = roots
    save(d, path)
    return roots


def set_value(key: str, value: str | None, path: Path | None = None) -> dict:
    if key not in KEYS:
        raise ValueError(f"no setting called {key}")
    value = str(value or "").strip()
    if key == "timezone" and value:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(value)
        except Exception:  # noqa: BLE001
            raise ValueError(f"'{value}' isn't a time zone this computer knows (try e.g. America/New_York)")
    d = load(path)
    if value:
        d[key] = value
    else:
        d.pop(key, None)
    save(d, path)
    return d
