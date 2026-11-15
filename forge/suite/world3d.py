"""The world list in the suite (BUILD 39): 3D -> World list (the whole list, what is made, held and next) and the world
queue's card in 3D -> Runs (is it running, what it is on, hours left at today's speed, start and stop).

Adding to the list, holding a thing, making it again and straightening a leaning one are anyone's (signed). The order of
need when two things tie, letting a held thing through past its checks, and starting the launcher are the person's.
Approving is never here: a made thing goes to Art -> Review & approve like any 3D model.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from .. import config as cfgmod
from ..log import get
from ..threed import world
from .threed import ThreeDRefused, _need, _person, _sign, file_url

log = get("suite")
_busy_cache: dict = {}


def _url(rel_path: str | None) -> str | None:
    return file_url(rel_path) if rel_path else None


def machine(cfg: dict) -> str:
    """Why the graphics card isn't free for the world queue right now ('' when it is) — asked at most every 30 s."""
    if time.time() - _busy_cache.get("at", 0) > 30:
        try:
            _busy_cache.update(why=world.machine_busy(cfg), at=time.time())
        except Exception as e:  # noqa: BLE001
            _busy_cache.update(why=f"can't tell ({e})", at=time.time())
    return _busy_cache.get("why", "")


def view(cfg: dict, gid: str, with_machine: bool = True) -> dict:
    s = world.status(cfg, gid)
    for i in s["items"]:
        i["urls"] = {"checks": _url(i.get("check_picture")), "model": _url(i.get("model")), "picture": _url(i.get("picture")),
                     "colour": _url(i.get("colour_picture")),
                     "gate": _url((i.get("gate") or {}).get("side_by_side")),
                     "gate_tries": [_url(t.get("picture")) for t in (i.get("gate") or {}).get("tries") or []]}
    s["launcher_bat"] = (cfgmod.ROOT / "make_what_we_need.bat").exists()
    s["kinds"] = list(world.KINDS)
    s["tier_names"] = list(world.TIERS)
    s["machine"] = machine(cfg) if with_machine and not s["launcher"]["running"] else ""
    return s


def summary(cfg: dict, gid: str) -> dict:
    """The world queue's card in Runs."""
    s = world.status(cfg, gid)
    return {"launcher": s["launcher"], "counts": s["counts"], "estimate": s["estimate"], "next": s["next"],
            "held": [{"id": i["id"], "why": i["why"][:2], "checks": _url(i.get("check_picture"))} for i in s["items"] if i["state"] == "held"][:12],
            "problems": s["problems"][:10], "log": s["log"], "stop_asked": s["stop_asked"], "total": len(s["items"])}


def start(cfg: dict, gid: str, who: str | None) -> dict:
    """Open make_what_we_need.bat in its own window (it starts ComfyUI first if needed)."""
    _person(who, "starting the world queue")
    from . import worker
    if not worker.here():
        from . import runwords
        return {"ok": False, "message": f"The world queue makes 3D models on {runwords.worker_pc()} — it can't start on this computer."}
    if world.launcher_state(cfg, gid)["running"]:
        return {"ok": False, "message": "The world queue is already running — Runs shows what it is on."}
    bat = cfgmod.ROOT / "make_what_we_need.bat"
    if os.name == "nt":
        if not bat.exists():
            return {"ok": False, "message": "make_what_we_need.bat is missing from the forge folder"}
        subprocess.Popen(f'start "RPG_Forge world queue" "{bat}"', shell=True, cwd=str(cfgmod.ROOT))
    else:
        subprocess.Popen([sys.executable, "-m", "forge", "3d", "world", "run", "--game", gid], cwd=str(cfgmod.ROOT),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    _sign(cfg, gid, who, "queue", "3d:world", note="started the world queue")
    return {"ok": True, "message": "The world queue is starting in its own window (ComfyUI first if it isn't up). Close that window, "
                                   "or choose Stop after this one, to stop it."}


def act(cfg: dict, gid: str, action: str, body: dict, who: str | None) -> dict:
    eid = world.slug(str(body.get("id") or ""))
    try:
        if action == "threed_world_add":
            _need(who, "adding to the world list")
            e = world.add_entry(cfg, gid, dict(body.get("entry") or {}), who=who or "")
            _sign(cfg, gid, who, "add", f"3d:world:{e['id']}", note=f"added {e['id']} ({e['kind']}, {e['tier']}) to the world list")
            return {"ok": True, "message": f"{e['id']} is on the list; the queue takes it in its turn.", "id": e["id"]}
        if action == "threed_world_hold":
            _need(who, "holding a thing")
            on = bool(body.get("hold", True))
            world.set_fields(cfg, gid, eid, {"hold": True if on else None})
            _sign(cfg, gid, who, "edit", f"3d:world:{eid}", note=("put on hold" if on else "taken off hold"))
            return {"ok": True, "message": f"{eid} is {'on hold' if on else 'back in the queue'}."}
        if action == "threed_world_rank":
            _person(who, "the order of need")
            r = float(body.get("rank") or 0)
            world.set_fields(cfg, gid, eid, {"rank": r if r else None})
            _sign(cfg, gid, who, "edit", f"3d:world:{eid}", note=f"rank {r:g} (lower is made first among things that first appear together)")
            return {"ok": True, "message": f"{eid}: rank {r:g}."}
        if action == "threed_world_again":
            _need(who, "making a thing again")
            r = world.make_again(cfg, gid, eid, who or "")
            _sign(cfg, gid, who, "queue", f"3d:world:{eid}", note="make again (a fresh picture)")
            return r
        if action == "threed_world_straighten":
            _need(who, "straightening a model")
            from ..threed.env import from_cfg
            r = world.straighten(cfg, gid, eid, who or "", env=from_cfg(cfg))
            _sign(cfg, gid, who, "edit", f"3d:world:{eid}", note=r["message"])
            return r
        if action == "threed_world_colours":        # BUILD 40: a person chooses the matched colours for a held thing
            _person(who, "choosing the matched colours")
            from ..threed.env import from_cfg
            r = world.use_colours(cfg, gid, eid, who or "", env=from_cfg(cfg))
            _sign(cfg, gid, who, "review", f"3d:world:{eid}", note=r["message"])
            return r
        if action == "threed_world_gate":           # BUILD 40: a person overrules the picture gate for one try's picture
            _person(who, "overruling the picture gate")
            r = world.gate_anyway(cfg, gid, eid, who or "", body.get("pick"))
            _sign(cfg, gid, who, "review", f"3d:world:{eid}", note=r["message"])
            return r
        if action == "threed_world_through":
            _person(who, "letting a held thing past its checks")
            from ..threed.env import from_cfg
            r = world.let_through(cfg, gid, eid, who or "", env=from_cfg(cfg))
            _sign(cfg, gid, who, "review", f"3d:world:{eid}", note="let through past its checks")
            return r
        if action == "threed_world_start":
            return start(cfg, gid, who)
        if action == "threed_world_stop":
            _need(who, "stopping the world queue")
            world.ask_stop(cfg, gid, who or "")
            _sign(cfg, gid, who, "queue", "3d:world", note="asked the world queue to stop after the thing in hand")
            return {"ok": True, "message": "Asked: the world queue stops after the thing in hand."}
    except world.WorldError as e:
        return {"ok": False, "message": str(e)}
    except ThreeDRefused as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}
