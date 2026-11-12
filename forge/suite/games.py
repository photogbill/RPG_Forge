"""Which games this install has, and each game's adapter.

A game is a folder `games/<id>/` with a `forge.game.json`. Its Story side needs `workbench_adapter.py` there too
(class `Adapter`). Its content lives in its own folder (`game_root`), outside this repo. A relative `game_root` hangs
off the game's `games/<id>/` folder (the `_example` game keeps its tiny made-up content in `games/_example/game/`).
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from . import settings
from .adapter import CONTRACT, AdapterError, GameAdapter

log = get("suite")
_loaded: dict[str, tuple[float, GameAdapter]] = {}


def games_dir(cfg: dict) -> Path:
    return cfgmod.path_of(cfg, "games")


def game_ids(cfg: dict) -> list[str]:
    d = games_dir(cfg)
    if not d.is_dir():
        return []
    ids = [p.name for p in d.iterdir() if p.is_dir() and (p / "forge.game.json").exists()]
    return sorted(ids, key=lambda i: (i.startswith("_"), i))


def game_cfg(cfg: dict, game_id: str) -> dict:
    p = games_dir(cfg) / game_id / "forge.game.json"
    return json.loads(p.read_text(encoding="utf-8-sig"))


def game_root(cfg: dict, game_id: str) -> Path | None:
    over = settings.game_root_override(game_id)
    raw = over or game_cfg(cfg, game_id).get("game_root")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_absolute() and not (len(str(raw)) > 1 and str(raw)[1] == ":"):
        p = games_dir(cfg) / game_id / p
    return p


def has_adapter(cfg: dict, game_id: str) -> bool:
    return (games_dir(cfg) / game_id / "workbench_adapter.py").exists()


def adapter(cfg: dict, game_id: str) -> GameAdapter:
    """The game's adapter (re-imported when its file changes)."""
    src = games_dir(cfg) / game_id / "workbench_adapter.py"
    if not src.exists():
        raise AdapterError(f"games/{game_id} has no workbench_adapter.py yet — its Story side is not set up")
    mt = src.stat().st_mtime
    root = game_root(cfg, game_id)
    hit = _loaded.get(game_id)
    if hit and hit[0] == mt and hit[1].root == root:
        return hit[1]
    name = f"forge_game_adapter_{game_id.strip('_') or 'example'}"
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    cls = getattr(mod, "Adapter", None)
    if cls is None or not issubclass(cls, GameAdapter):
        raise AdapterError(f"games/{game_id}/workbench_adapter.py must define class Adapter(GameAdapter)")
    if getattr(cls, "contract", None) != CONTRACT:
        raise AdapterError(f"games/{game_id} adapter speaks contract {getattr(cls, 'contract', None)}; the suite speaks {CONTRACT}")
    a = cls(game_id, root or Path("."), game_cfg(cfg, game_id))
    _loaded[game_id] = (mt, a)
    log.info("suite: adapter for %s loaded (%s)", game_id, root)
    return a


def listing(cfg: dict) -> list[dict]:
    """For the game picker: every game, its folder, whether it is reachable and has a Story adapter."""
    out = []
    for gid in game_ids(cfg):
        e = {"id": gid, "name": gid, "root": None, "root_exists": False, "adapter": has_adapter(cfg, gid), "error": None}
        try:
            r = game_root(cfg, gid)
            e["root"] = str(r) if r else None
            e["root_exists"] = bool(r and r.is_dir())
            if e["adapter"]:
                a = adapter(cfg, gid)
                e["name"] = a.name
        except Exception as ex:  # noqa: BLE001 — the picker must come up whatever one game's state
            e["error"] = f"{type(ex).__name__}: {ex}"
        out.append(e)
    return out


def check_root(cfg: dict, game_id: str, folder: str) -> dict:
    """Settings → This computer → Check: load the game's adapter against `folder` and say what it found, or exactly
    what is missing. Writes nothing."""
    raw = str(folder or "").strip().strip('"')
    if not raw:
        return {"ok": False, "message": "Type the folder first."}
    p = Path(raw).expanduser()
    if not p.is_dir():
        return {"ok": False, "message": f"There's no folder at {p} on this computer."}
    if not has_adapter(cfg, game_id):
        return {"ok": True, "message": f"The folder is there. (This game has no adapter, so there's nothing more to check.)", "found": {}}
    src = games_dir(cfg) / game_id / "workbench_adapter.py"
    name = f"forge_game_adapter_check_{game_id.strip('_') or 'example'}"
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        a = mod.Adapter(game_id, p, game_cfg(cfg, game_id))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"The folder is there, but the game's adapter couldn't load: {type(e).__name__}: {e}"}
    found, missing = {}, []
    for what, fn in (("places", a.places), ("lines", a.lines), ("music slots", a.music_slots), ("people", a.people)):
        try:
            found[what] = len(fn())
        except Exception as e:  # noqa: BLE001 — say which part is missing; don't stop at the first
            missing.append(f"{what}: {type(e).__name__}: {e}")
    if missing and not any(found.values()):
        return {"ok": False, "message": "That folder doesn't look like this game — " + "; ".join(missing), "found": found}
    words = ", ".join(f"{n} {w}" for w, n in found.items())
    return {"ok": True, "message": f"Found it: {words}." + (" Missing: " + "; ".join(missing) if missing else ""), "found": found,
            "missing": missing}
