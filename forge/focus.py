"""Focus the world queue on one place, and put everything back after (Opus, 2026-11-21).

William, 2026-11-21 01:11: "Lets stop the mass production of art we have going 24/7 and pause that, and start one for
only Linden Mills." Focus holds every thing still to make that is NOT for the focus (the queue skips held things), and
writes exactly which it held to wanted_3d/_focus_<name>.json — so resume takes off hold only those, and never a thing
someone held for its own reasons.
  python -m forge.focus linden_mills [--dry]      hold everything else
  python -m forge.focus resume [--dry]            take those holds off again
  python -m forge.focus status
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

from . import config as cfgmod
from .log import get
from .threed import world

log = get("focus")
WHO = "Claude Opus, for William (focus)"

FOCI = {
    "linden_mills": {
        "places": {"linden_mills_court", "linden_mills_street", "linden_mills_gas", "linden_mills_store", "linden_mills_diner",
                   "gun_store", "hobby_shop", "bills_house", "school_street", "sarahs_workshop", "uncle_workshop"},
        "prefixes": ("lm_", "linden_mills_", "bills_house"),
        "where": ("linden mills", "bill's house", "bills house", "sarah's workshop", "chloe's school"),
        "not_where": ("the war road",),
        "said": "William 2026-11-21 01:11: \"start one for only Linden Mills\"",
    },
}


def _in(e: dict, f: dict) -> bool:
    w = ((e.get("first") or {}).get("where") or "").lower()
    if any(x in w for x in f["not_where"]):
        return False
    return (e["id"].startswith(f["prefixes"]) or e.get("from_place") in f["places"] or any(x in w for x in f["where"]))


def _file(cfg, gid, name):
    return world.list_dir(cfg, gid) / f"_focus_{name}.json"


def focus(name: str, dry: bool = False) -> dict:
    from .suite import world3d
    cfg = cfgmod.load(); gid = cfgmod.default_game(cfg); f = FOCI[name]
    items, _ = world.merged(cfg, gid)
    todo = [e for e in items if e["state"] in ("wanted", "failed") and not e["hold"]]
    keep = [e["id"] for e in todo if _in(e, f)]
    hold = [e["id"] for e in todo if not _in(e, f)]
    print(f"{gid}: {len(keep)} for {name} stay in the queue; {len(hold)} others {'would be' if dry else 'are'} held.")
    if dry:
        return {"keep": keep, "hold": hold}
    p = _file(cfg, gid, name)
    prev = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"held": []}
    done = list(prev.get("held") or [])

    def save():   # written as it goes, so a stop part-way still records exactly what was held
        p.write_text(json.dumps({"focus": name, "said": f["said"], "at": datetime.now().isoformat(timespec="seconds"),
                                 "kept": keep, "held": sorted(set(done))}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for i, eid in enumerate(hold, 1):
        r = world3d.act(cfg, gid, "threed_world_hold", {"id": eid, "hold": True}, WHO)
        if r.get("ok"):
            done.append(eid)
        else:
            log.warning("focus: could not hold %s: %s", eid, r)
        if i % 25 == 0:
            save()
            print(f"  {i}/{len(hold)}")
    save()
    log.info("focus %s: held %d, kept %d (%s)", name, len(hold), len(keep), p)
    print(f"Done. Held {len(hold)}. resume_all_art.bat takes exactly these off hold again.")
    return {"keep": keep, "held": done}


def resume(dry: bool = False) -> int:
    from .suite import world3d
    cfg = cfgmod.load(); gid = cfgmod.default_game(cfg)
    n = 0
    for p in sorted(world.list_dir(cfg, gid).glob("_focus_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        ids = d.get("held") or []
        print(f"{p.name}: {len(ids)} {'would come' if dry else 'come'} off hold")
        if dry:
            continue
        for eid in ids:
            world3d.act(cfg, gid, "threed_world_hold", {"id": eid, "hold": False}, WHO)
            n += 1
        p.rename(p.with_name(p.stem.replace("_focus_", "_focus_done_") + f"_{datetime.now():%Y%m%d%H%M}.json"))
    log.info("focus resume: %d taken off hold", n)
    print(f"Done. {n} back in the queue." if not dry else "")
    return n


def status() -> None:
    cfg = cfgmod.load(); gid = cfgmod.default_game(cfg)
    fs = sorted(world.list_dir(cfg, gid).glob("_focus_*.json"))
    if not fs:
        print("No focus: the queue makes everything in order.")
    for p in fs:
        d = json.loads(p.read_text(encoding="utf-8"))
        print(f"Focus '{d['focus']}' since {d['at']}: {len(d['held'])} held, {len(d['kept'])} for the focus.")


if __name__ == "__main__":
    a = sys.argv[1:]
    dry = "--dry" in a
    a = [x for x in a if x != "--dry"]
    cmd = a[0] if a else "status"
    if cmd == "resume":
        resume(dry)
    elif cmd == "status":
        status()
    else:
        focus(cmd, dry)
