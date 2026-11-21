"""The world list in the suite (BUILD 39): 3D -> World list (the whole list, what is made, held and next) and the world
queue's card in 3D -> Runs (is it running, what it is on, hours left at today's speed, start and stop).

Adding to the list, holding a thing, making it again and straightening a leaning one are anyone's (signed). The order of
need when two things tie and starting the launcher are the person's. Releasing a held thing (matched, as made, past its
checks, past the picture gate) is the person's — or, with "<assistant> may approve for me" on, an assistant's for the
person, signed "<assistant>, for <person>" (BUILD 78). Approving is never here: a made thing goes to Art -> Review & approve.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from .. import config as cfgmod
from ..log import get
from ..threed import world
from .threed import ThreeDRefused, _approver, _need, _person, _sign, file_url

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
    # BUILD 73: what one button would release (colours matched) or straighten, and the things whose up a person picks
    try:
        rel = world.release_lists(cfg, gid)
        for k in ("match", "straighten", "unclear_up"):
            for r in rel[k]:
                r["urls"] = {"colour": _url(r.get("colour_picture")), "head": _url(r.get("head_picture")),
                             "checks": _url(r.get("check_picture")), "picture": _url(r.get("picture"))}
        s["release"] = rel
    except Exception as e:  # noqa: BLE001
        s["release"] = {"match": [], "straighten": [], "unclear_up": [], "error": str(e)}
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
            who = _approver(cfg, gid, who, "choosing the matched colours")
            from ..threed.env import from_cfg
            r = world.use_colours(cfg, gid, eid, who, env=from_cfg(cfg))
            _sign(cfg, gid, who, "review", f"3d:world:{eid}", note=r["message"])
            return r
        if action == "threed_world_gate":           # BUILD 40: a person overrules the picture gate for one try's picture
            who = _approver(cfg, gid, who, "overruling the picture gate")
            r = world.gate_anyway(cfg, gid, eid, who, body.get("pick"))
            _sign(cfg, gid, who, "review", f"3d:world:{eid}", note=r["message"])
            return r
        if action == "threed_world_through":
            who = _approver(cfg, gid, who, "letting a held thing past its checks")
            from ..threed.env import from_cfg
            r = world.let_through(cfg, gid, eid, who, env=from_cfg(cfg))
            _sign(cfg, gid, who, "review", f"3d:world:{eid}", note="let through past its checks")
            return r
        if action == "threed_world_match_release":   # BUILD 73: the person's — releases what only needs matching
            who = _approver(cfg, gid, who, "releasing things with their colours matched")
            from ..threed.env import from_cfg
            ids = [world.slug(str(i)) for i in body.get("ids") or []]
            r = world.match_and_release(cfg, gid, ids, who, env=from_cfg(cfg))
            for d in r["released"]:
                _sign(cfg, gid, who, "review", f"3d:world:{d['id']}", note=f"Match and release → {d['to']}")
            return r
        if action == "threed_world_as_made":          # BUILD 78: the match was worse than the thing as made
            who = _approver(cfg, gid, who, "releasing things as made")
            from ..threed.env import from_cfg
            ids = [world.slug(str(i)) for i in body.get("ids") or [eid]]
            r = world.release_as_made(cfg, gid, ids, who, env=from_cfg(cfg))
            for d in r["released"]:
                _sign(cfg, gid, who, "review", f"3d:world:{d['id']}", note=f"Release as made → {d['to']}")
            return r
        if action == "threed_world_try_again":        # BUILD 78: a failed thing back in line, keeping what it had
            _need(who, "trying a thing again")
            ids = [world.slug(str(i)) for i in body.get("ids") or [eid]]
            r = world.try_again(cfg, gid, ids, who or "")
            for i in r["again"]:
                _sign(cfg, gid, who, "queue", f"3d:world:{i}", note="try again (keeping what it had)")
            return r
        if action == "threed_world_place_again":      # BUILD 78: placed again from the forge (tidied), nothing remade
            _need(who, "placing a thing again")
            from ..threed.env import from_cfg
            ids = [world.slug(str(i)) for i in body.get("ids") or [eid]]
            r = world.place_again(cfg, gid, ids, who or "", env=from_cfg(cfg))
            for i in r["placed"]:
                _sign(cfg, gid, who, "edit", f"3d:world:{i}", note="placed again from the forge (tidied)")
            return r
        if action == "threed_world_straighten_release":
            _need(who, "straightening and releasing")
            from ..threed.env import from_cfg
            ids = [world.slug(str(i)) for i in body.get("ids") or []]
            r = world.straighten_and_release(cfg, gid, ids, who or "", env=from_cfg(cfg))
            for d in r["released"] + r["still_held"]:
                _sign(cfg, gid, who, "edit", f"3d:world:{d['id']}", note="Straighten and release: " + d["message"])
            return r
        if action == "threed_world_up_choices":
            r = world.up_choices(cfg, gid, eid)
            for c in r["choices"]:
                c["url"] = _url(c["picture"])
            return {"ok": True, **r}
        if action == "threed_world_up_pick":
            _need(who, "saying which way is up")
            from ..threed.env import from_cfg
            r = world.pick_up(cfg, gid, eid, str(body.get("choice") or ""), who or "", env=from_cfg(cfg))
            _sign(cfg, gid, who, "edit", f"3d:world:{eid}", note=r["message"])
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
