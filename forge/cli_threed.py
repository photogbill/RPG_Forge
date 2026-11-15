"""`python -m forge 3d …` — the 3D workshop from a command line (BUILD 36). The screens are the suite's 3D area.

    3d line <list.json> [--only <id>] [--skip-pictures] [--skip-rig] [--skip-fit] [--estimate]
                                     the whole line for a list, unattended (what the overnight cast run did)
    3d check                         what is installed for 3D and what is missing (starts nothing)
    3d install [--dry-run] [--only a,b] [--skip a,b]   install the rigging ComfyUI (engines/rig) and its pack
    3d lock                          who holds the graphics card now
    3d info <model.glb>              size in metres, motions, skeleton - read without Blender
    3d grow <species> [--seed N] [--count 4] [--bare]  grow trees here and now (Blender), into out/3d/trees/
    3d standin [--kind art|rig] [--port 8288] [--root <folder>]   a stand-in ComfyUI for trying things with no card

  BUILD 39 — the world queue and the checks after every model:
    3d world run [--game <id>] [--once] [--until-empty]   make what the world list wants, next thing first, until stopped
                                     (what make_what_we_need.bat runs; it waits whenever the graphics card is someone else's)
    3d world status [--game <id>]    the list, what is made, held and next, and the hours left at today's speed
    3d world stop [--game <id>]      the launcher stops after the thing in hand
    3d world add <entry.json> [--game <id>]   add one entry (or a file of them) to the list
    3d checks <model.glb> [--picture p.png] [--kind prop|building|body] [--tier ...] [--draw out.png] [--json]
                                     the four checks on any model (sits level, loose pieces, blank glass, thin parts)
    3d wreck <in.glb> <out.glb> [--seed 1] [--hits 4] [--strength 0.8]   a wrecked version made from the intact model
    3d glow <in.glb> <out.glb> [--colour amber,red | 255:60:20] [--strength 1]   a glow layer from the model's glow colours
    3d heads <body.glb> <head.glb> <out.glb> [--collar 0.86]             a head joined onto a shared body (Blender)

  BUILD 34 — towns as 3D stages:
    3d place compile <place.json> [--game <id>] [--out <folder>]   the stage model (Blender, no card), the placed-things
                                     list and the place's entries on the world list; starts no generation
    3d place check <place.json>      what is wrong with a place plan, in words
    3d place from-town <plan set folder> [--sheet <sheet.json>] [--metres 1.0] [--out <place.json>]
                                     a town's floor-plan layout written out as a place plan

  BUILD 40 — the picture gate:
    3d gate <picture.png> --words "…" [--expects-arms 1] [--age 9] [--seated] [--json]   the gate on one picture
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _opt(args: list[str], flag: str, default=None):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default


def cmd_3d(cfg: dict, args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    sub, rest = args[0], args[1:]
    if sub == "line":
        from .threed import line
        files = [a for i, a in enumerate(rest) if not a.startswith("--") and (i == 0 or rest[i - 1] != "--only")]
        if not files:
            print("usage: 3d line <list.json> [--only <id>] [--skip-pictures] [--skip-rig] [--skip-fit] [--estimate]")
            return 2
        p = Path(files[0])
        spec = json.loads(p.read_text(encoding="utf-8"))
        spec.setdefault("batch", p.stem)
        out = line.folder(cfg, spec["batch"])
        if "--estimate" in rest:
            e = line.estimate(spec, line.status(cfg, spec, out))
            print(f"'{spec['batch']}': {e['bodies']} bodies; to make: " + ", ".join(f"{v} {k}" for k, v in e["to_make"].items())
                  + f" - {e['words']}")
            return 0
        skip = tuple(s for s, f in (("pictures", "--skip-pictures"), ("rig", "--skip-rig"), ("fit", "--skip-fit")) if f in rest)
        h = line.log_to(out)
        try:
            rows = line.run(cfg, spec, out, only=_opt(rest, "--only"), skip=skip)
        finally:
            h.close()
        return 0 if rows and all(r["motions"] for r in rows) else 2
    if sub == "check":
        from .threed import install
        for ln in install.doctor_lines(cfg):
            print(ln)
        return 0
    if sub == "install":
        from .threed import install
        return install.main(rest, cfg)
    if sub == "lock":
        from .threed import cardlock
        st = cardlock.state(cfg)
        print("the graphics card is free" if not st["held"] else f"held by {st['holder']} since {st['since']} (heartbeat {st['beat_age']} s ago)")
        return 0
    if sub == "info":
        from .threed import glb
        if not rest:
            print("usage: 3d info <model.glb>")
            return 2
        print(json.dumps(glb.info(Path(rest[0])), indent=1))
        return 0
    if sub == "grow":
        import time
        from .threed import trees
        from .threed.env import from_cfg, out_root
        name = rest[0] if rest and not rest[0].startswith("--") else "broadleaf"
        sheet = next((s for s in trees.sheets(Path(cfg.get("_root", ".")) / "games" / (cfg.get("default_game") or "_")) if s["name"] == name), None)
        if sheet is None:
            print(f"no species sheet called {name}; there are: " + ", ".join(s["name"] for s in trees.sheets()))
            return 2
        out = out_root(cfg) / "trees" / time.strftime("%Y%m%d-%H%M%S")
        seed, n = int(_opt(rest, "--seed", 11)), int(_opt(rest, "--count", 1))
        ok = 0
        for k in range(n):
            r = trees.grow(from_cfg(cfg), out, sheet, seed + k, bare="--bare" in rest)
            print(("grown: " + r["glb"]) if r["ok"] else ("failed: " + r["error"]))
            ok += bool(r["ok"])
        return 0 if ok == n else 2
    if sub == "standin":
        from .threed import standin
        return standin.main(rest)
    if sub == "place":                                   # BUILD 34
        return _cmd_place(cfg, rest)
    if sub == "gate":                                    # BUILD 40
        from .threed import gate
        if not rest:
            print("usage: 3d gate <picture.png> --words \"…\" [--expects-arms 1] [--age 9] [--seated] [--json]")
            return 2
        entry = {"prompt": _opt(rest, "--words", "")}
        if _opt(rest, "--expects-arms"):
            entry["expects"] = {"arms": int(_opt(rest, "--expects-arms"))}
        if _opt(rest, "--age"):
            entry["age"] = int(_opt(rest, "--age"))
        if "--seated" in rest:
            entry["seated"] = True
        j = gate.judge(rest[0], entry, cfg)
        if "--json" in rest:
            print(json.dumps({k: v for k, v in j.items()}, indent=1, default=str))
        else:
            print("\n".join(j["lines"]))
            print("passes" if j["ok"] else "MISSES — the world queue would paint it again")
        return 0 if j["ok"] else 1
    if sub == "world":
        return _world(cfg, rest)
    if sub == "checks":
        from .threed import checks
        return checks.main(rest)
    if sub == "wreck":
        from .threed import damage
        if len(rest) < 2:
            print("usage: 3d wreck <in.glb> <out.glb> [--seed 1] [--hits 4] [--strength 0.8]")
            return 2
        r = damage.wreck(rest[0], rest[1], seed=int(_opt(rest, "--seed", 1)), hits=int(_opt(rest, "--hits", 4)),
                         strength=float(_opt(rest, "--strength", 0.8)))
        print(json.dumps(r, indent=1))
        return 0
    if sub == "glow":
        from .threed import damage
        if len(rest) < 2:
            print("usage: 3d glow <in.glb> <out.glb> [--colour amber,red] [--strength 1]")
            return 2
        cols = tuple(c.strip() for c in str(_opt(rest, "--colour", "amber")).split(",") if c.strip())   # names, or r:g:b
        r = damage.glow(rest[0], rest[1], colours=cols, strength=float(_opt(rest, "--strength", 1.0)))
        print(r["line"])
        return 0
    if sub == "heads":
        from .threed import heads
        from .threed.env import from_cfg
        if len(rest) < 3:
            print("usage: 3d heads <body.glb> <head.glb> <out.glb> [--collar 0.86]")
            return 2
        r = heads.join(from_cfg(cfg), Path(rest[0]), Path(rest[1]), Path(rest[2]),
                       collar=float(_opt(rest, "--collar")) if _opt(rest, "--collar") else None)
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 2
    print(f"unknown: 3d {sub}\n{__doc__}")
    return 2


def _world(cfg: dict, rest: list[str]) -> int:
    from . import config as cfgmod
    from .threed import world
    what = rest[0] if rest and not rest[0].startswith("--") else "status"
    gid = _opt(rest, "--game") or cfgmod.default_game(cfg)
    if what == "run":
        import logging
        import sys as _sys
        lg = logging.getLogger("forge.threed")
        if not any(isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is _sys.stdout for h in lg.handlers):
            h = logging.StreamHandler(_sys.stdout)
            h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
            lg.addHandler(h)
        lg.setLevel(logging.INFO)
        if world.launcher_state(cfg, gid)["running"]:
            print(f"The world queue for {gid} is already running (see 3D -> Runs). Nothing was started.")
            return 1
        print(f"The world queue for {gid}: making what the list wants, next thing first. Close this window or choose "
              "'Stop after this one' in 3D -> Runs to stop; closing loses at most the thing in hand.")
        t = world.run(cfg, gid, once="--once" in rest, until_empty="--until-empty" in rest)
        print(f"Stopped ({t['stopped_by']}): {t['made']} made, {t['held']} held back, {t['failed']} failed.")
        return 0
    if what == "status":
        s = world.status(cfg, gid)
        ln = s["launcher"]
        print(f"The world list for {gid}: " + ", ".join(f"{n} {k}" for k, n in sorted(s["counts"].items())) or "empty")
        print(("  the launcher is running: " + (ln.get("item") or "-") + f" ({ln.get('step')})" + (f" — waiting: {ln['waiting']}" if ln.get("waiting") else ""))
              if ln["running"] else "  the launcher is not running")
        print(f"  still to make: {s['estimate']['to_make']} — {s['estimate']['words']} at {s['estimate']['basis']}")
        print(f"  next: {s['next'] or '-'}")
        for i in s["items"]:
            if i["shown"] in ("held", "failed"):
                print(f"  {i['shown'].upper():<7} {i['id']}: " + "; ".join(i["why"] or [i.get("error") or ""])[:300])
        for p in s["problems"]:
            print(f"  problem: {p}")
        return 0
    if what == "stop":
        world.ask_stop(cfg, gid, "the command line")
        print("Asked: the launcher stops after the thing in hand.")
        return 0
    if what == "add":
        files = [a for a in rest[1:] if not a.startswith("--") and a != gid]
        if not files:
            print("usage: 3d world add <entry.json> [--game <id>]")
            return 2
        data = json.loads(Path(files[0]).read_text(encoding="utf-8"))
        items = data.get("entries") if isinstance(data, dict) and "entries" in data else (data if isinstance(data, list) else [data])
        defaults = data.get("defaults") if isinstance(data, dict) else None
        n = 0
        for raw in items:
            try:
                world.add_entry(cfg, gid, {**(defaults or {}), **raw}, who="the command line")
                n += 1
            except world.WorldError as e:
                print(f"  not added: {e}")
        print(f"Added {n} entr{'y' if n == 1 else 'ies'} to the world list for {gid}.")
        return 0
    if what == "report":
        print(world.write_report(cfg, gid).read_text(encoding="utf-8"))
        return 0
    print("usage: 3d world run|status|stop|add|report [--game <id>]")
    return 2


def _cmd_place(cfg: dict, rest: list[str]) -> int:
    from .threed import place
    what = rest[0] if rest else ""
    files = [a for a in rest[1:] if not a.startswith("--")]
    if what == "check" and files:
        probs = place.check(place.load(files[0]))
        print("\n".join(probs) if probs else "The place plan is sound.")
        return 1 if probs else 0
    if what == "compile" and files:
        from .threed import world
        gid = _opt(rest, "--game") or _default_game(cfg)
        pl = place.load(files[0])
        out = Path(_opt(rest, "--out") or (world.root_of(cfg) / "out" / "3d" / "places" / str(pl.get("id") or "place")))
        rep = place.compile_place(cfg, gid, files[0], out, games_root=world.games_dir(cfg) if gid else None)
        if not rep["ok"]:
            print("not compiled: " + rep["error"])
            return 1
        print("\n".join(rep["lines"]))
        print(f"Into {out}.")
        return 0
    if what == "from-town" and files:
        from .layout import store
        top, pset = store.load_set(Path(files[0]))
        sheet = dict(pset.get("sheet") or {})
        if _opt(rest, "--sheet"):
            sheet.update(json.loads(Path(_opt(rest, "--sheet")).read_text(encoding="utf-8")))
        pl = place.from_town(top.layout_record(), top.grid.c, sheet, float(_opt(rest, "--metres", 1.0)), top.entities)
        dst = Path(_opt(rest, "--out") or f"{pl['id']}.place.json")
        dst.write_text(json.dumps(pl, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {dst}: {len(pl['things'])} buildings, {len(pl['ground'])} ground pieces, {len(pl['solids'])} fence runs.")
        for u in pl.get("unknowns") or []:
            print("  ask: " + u)
        return 0
    print("usage: 3d place compile|check <place.json> [--game <id>] [--out <folder>] · 3d place from-town <layout> --sheet <s.json>")
    return 2


def _default_game(cfg: dict) -> str:
    from . import config as cfgmod
    try:
        return cfgmod.default_game(cfg) or ""
    except Exception:  # noqa: BLE001
        return ""


COMMANDS = {"3d": cmd_3d}
