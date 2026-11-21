"""`python -m forge approvals …` and `python -m forge world-fix …` — approvals made easy, from a command line (BUILD 78).
The screens are 3D → World list and Art → Review & approve ("Approve everything here"), and Settings → Approvals.

    approvals plan  --page world|review [--game <id>]           what Approve everything here would do, one line a group
    approvals all   --page world|review [--game <id>] [--who <name>] [--only id,id,…]
                                                              do it (signed; an assistant only under the setting, and
                                                              then written as "<assistant>, for <person>")
    approvals undo  <uid> [--game <id>] [--who <name>]          put one thing back as it was (see `approvals log`)
    approvals log   [--game <id>]                               what was approved, newest first, with each uid
    approvals setting [--game <id>]                             whether an assistant may approve for the person (only a
                                                              person changes it, on Settings → Approvals)

    world-fix try-again   <id> [<id> …] [--game <id>]         failed things back in line, keeping what they had
    world-fix try-again   --failed-with "<words>"              … every failed thing whose error has those words in it
    world-fix place-again <id> [<id> …] [--game <id>]         made props placed again from the forge (tidied); the try in
                                                              Review & approve is withdrawn and a new one sent
    world-fix as-made     <id> [<id> …] [--game <id>] [--who <name>]   held for colours alone → released as made
    world-fix animal-again <id> [<id> …] [--game <id>]        BUILD 84: animals made with a person's skeleton made again as animals
                                                              (the body kept; the try withdrawn; skeleton and motions set aside)
    world-fix unhold      <id> [<id> …] [--game <id>]         take things off hold on the list (their entry's "hold" set false)
    world-fix check-again <id> [<id> …] [--game <id>]         BUILD 84 (2f): held props and buildings checked again with the
                                                              forge as it is now (no card): a loose piece under the floor
                                                              taken off, one a little through it stood on it, a small lean
                                                              straightened — what passes goes to Review & approve
    world-fix regate      [<id> …] [--game <id>]              BUILD 84: bodies held by the picture gate judged again with its
                                                              numbers as they are now; a try that passes goes back in line
                                                              (no picture painted again). No ids = every one the gate holds
    world-fix one-gain    <id> [<id> …] [--game <id>] [--who <name>]   BUILD 84: bodies released with a curve on their colours,
                                                              put right at one gain (released again, or the made body's
                                                              colour picture swapped); each in the undo log

`--who` defaults to who this install signs as (FORGE_IDENTITY wins, as everywhere). Nothing here starts a job or uses the
graphics card; place-again uses the forge's own Blender (a minute or two a thing).
"""
from __future__ import annotations

import json


def _opt(args, flag, d=None):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else d


def _game(cfg, args) -> str:
    from . import config as cfgmod
    return _opt(args, "--game") or cfgmod.default_game(cfg)


def _who(args) -> str | None:
    from .suite import settings
    return _opt(args, "--who") or settings.identity()


def _ids(args) -> list[str]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ("--game", "--who", "--page", "--only", "--failed-with", "--note"):
            skip = True
            continue
        out.append(a)
    return out


def cmd_approve(cfg: dict, args: list[str]) -> int:
    from .suite import approve_all as ap
    if not args:
        print(__doc__)
        return 2
    sub, rest = args[0], args[1:]
    gid = _game(cfg, rest)
    try:
        if sub == "plan":
            p = ap.plan(cfg, gid, _opt(rest, "--page", "world"))
            print(f"{p['count']} waiting ({p['page']}). {p['setting']['said']}")
            for ln in p["lines"]:
                print("  → " + ln)
            for ln in p["left"]:
                print("  · " + ln)
            return 0
        if sub == "all":
            from .threed.env import from_cfg
            only = [x for x in (_opt(rest, "--only") or "").split(",") if x] or None
            r = ap.approve_everything(cfg, gid, _opt(rest, "--page", "world"), _who(rest), ids=only, env=from_cfg(cfg))
            print(r["message"])
            for d in r["done"]:
                print(f"  ✓ {d['id']} — {d['what']}  (undo: {d['uid']})")
            return 0 if r["ok"] else 1
        if sub == "undo":
            r = ap.undo(cfg, gid, _ids(rest)[0] if _ids(rest) else "", _who(rest))
            print(r["message"])
            return 0 if r["ok"] else 1
        if sub == "log":
            for h in ap.history(cfg, gid):
                print(f"{h['at']}  {h['uid']}  {h.get('page')}  {h['id']}  {h.get('what')}  {h.get('by')}{'  (undone)' if h['undone'] else ''}")
            return 0
        if sub == "setting":
            print(json.dumps(ap.setting(cfg, gid), indent=1, ensure_ascii=False))
            return 0
    except ap.ApproveRefused as e:
        print(f"refused: {e}")
        return 1
    print(f"unknown: approvals {sub}\n{__doc__}")
    return 2


def cmd_world_fix(cfg: dict, args: list[str]) -> int:
    from .threed import world
    from .threed.env import from_cfg
    if not args:
        print(__doc__)
        return 2
    sub, rest = args[0], args[1:]
    gid, ids, who = _game(cfg, rest), _ids(rest), _who(rest) or "the forge"
    words = _opt(rest, "--failed-with")
    if words:                                 # BUILD 78: e.g. every body the night's "ndarray" fault failed
        ids += [e["id"] for e in world.merged(cfg, gid)[0]
                if e["state"] == "failed" and words.lower() in str(e["st"].get("error") or "").lower() and e["id"] not in ids]
        if not ids:
            print(f"no failed thing has \"{words}\" in its error")
            return 0
    if not ids and sub != "regate":
        print("name the things (their ids)")
        return 2
    try:
        if sub == "regate":
            r = world.regate(cfg, gid, ids or None, who)
            for d in r["passed"]:
                print(f"  ✓ {d['id']} — try {d['try']}: {d['line']}")
            for d in r["still"]:
                print(f"  · {d['id']} — {d['why']}")
        elif sub == "animal-again":
            r = world.animal_again(cfg, gid, ids, who)
        elif sub == "check-again":
            r = world.check_again(cfg, gid, ids, who, env=from_cfg(cfg))
            for d in r["made"]:
                print(f"  ✓ {d['id']}" + "".join(f"\n      {ln}" for ln in d["said"]))
            for d in r["still"]:
                print(f"  · {d['id']} — still held: " + " ".join(d["why"]))
            for d in r["left"]:
                print(f"  · {d['id']} — left: {d['why']}")
        elif sub == "unhold":
            done = []
            for i in ids:
                world.set_fields(cfg, gid, world.slug(i), {"hold": False})
                done.append(i)
            r = {"ok": True, "message": f"{len(done)} off hold: {', '.join(done)}."}
        elif sub == "try-again":
            r = world.try_again(cfg, gid, ids, who)
        elif sub == "place-again":
            r = world.place_again(cfg, gid, ids, who, env=from_cfg(cfg))
        elif sub == "one-gain":
            from .suite import approve_all as ap
            r = ap.world_one_gain(cfg, gid, who, ids, note=_opt(rest, "--note") or "")
            for d in r["done"]:
                print(f"  ✓ {d['id']} — {d.get('how')}  → {d.get('to')}  (undo: {d['uid']})")
        elif sub == "as-made":
            from .suite import approve_all as ap
            r = world.release_as_made(cfg, gid, ids, ap.signer(cfg, gid, who, "releasing things as made"), env=from_cfg(cfg))
        else:
            print(f"unknown: world-fix {sub}\n{__doc__}")
            return 2
    except Exception as e:  # noqa: BLE001 — said plainly, never a traceback for the person
        print(f"refused: {e}")
        return 1
    print(r["message"])
    return 0 if r.get("ok") else 1


COMMANDS = {"approvals": cmd_approve, "world-fix": cmd_world_fix}   # not "approve": that is a picture's (approve.bat)
