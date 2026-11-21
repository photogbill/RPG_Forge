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
    3d place compile <place.json> [--game <id>] [--out <folder>] [--hold]   the stage model (Blender, no card), the
                                     placed-things list and the place's entries on the world list (--hold: written held,
                                     so the world queue makes none of them until a person releases them); starts no
                                     generation. Into the game's <asset_root>/stages/<id>/ unless --out says otherwise
    3d place check <place.json>      what is wrong with a place plan, in words
    3d place from-town <plan set folder> [--sheet <sheet.json>] [--metres 1.0] [--out <place.json>]
                                     a town's floor-plan layout written out as a place plan

  BUILD 63 — the look:
    3d relief <folder or pictures…> [--force] [--strength 6] [--broad 0]   a normal map beside every library picture
                                     (<name>_n.png; a Filter Forge Normal render or a Material Maker normal beside it wins);
                                     what was decided goes in relief.json in the folder

  BUILD 60 — the outdoors:
    3d terrain <place.json> [--out <folder>]   a place's land (its `terrain` block: rules or a height picture) → a
                                     16-bit height picture + its numbers beside the stage (compile_place does this too)
    3d pack-terrain <pictures…> [--roughness 0.85] [--size 1024]   a surface as the terrain's two packed pictures
                                     (<name>_t3d_albedo.png: colour + height; <name>_t3d_normal.png: normal + roughness)

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
    if sub == "same-person":                             # BUILD 74: the same person, changed
        return _cmd_same_person(cfg, rest)
    if sub == "relief":                                  # BUILD 63
        from .threed import relief
        targets = [a for i, a in enumerate(rest) if not a.startswith("--") and (i == 0 or rest[i - 1] not in ("--strength", "--broad"))]
        if not targets:
            print("usage: 3d relief <folder or pictures…> [--force] [--strength 6] [--broad 0]")
            return 2
        r = relief.run(targets, force="--force" in rest, strength=float(_opt(rest, "--strength", 6.0)),
                       broad=float(_opt(rest, "--broad", 0.0)))
        for row in r["rows"]:
            print(f"  {row['picture']} -> {row['relief']}  ({row['source']}{'' if row['written'] else ', unchanged'})")
        print(f"relief: {r['pictures']} pictures, {r['written']} written, {r['kept']} kept")
        return 0
    if sub == "terrain":                                 # BUILD 60
        from .threed import ground as land, place as placemod
        if not rest or rest[0].startswith("--"):
            print("usage: 3d terrain <place.json> [--out <folder>]")
            return 2
        pl = placemod.load(rest[0])
        probs = land.check(pl)
        if probs:
            print("\n".join(probs))
            return 1
        out = _opt(rest, "--out", str(Path(rest[0]).parent))
        b = land.make(pl, out, place_dir=Path(rest[0]).parent)
        print(f"terrain: {b['height']} ({b['pixels'][0]}×{b['pixels'][1]}, {b['size_m'][0]:.0f} × {b['size_m'][1]:.0f} m, "
              f"{b['range_m'][0]:.2f} to {b['range_m'][1]:.2f} m, levelled under {b['flat']}) in {out}")
        return 0
    if sub == "pack-terrain":                            # BUILD 60
        from .threed import ground as land
        pics = [a for i, a in enumerate(rest) if not a.startswith("--") and (i == 0 or rest[i - 1] not in ("--roughness", "--size"))]
        if not pics:
            print("usage: 3d pack-terrain <pictures…> [--roughness 0.85] [--size 1024]")
            return 2
        for p in pics:
            r = land.pack_for_terrain(Path(p), roughness=float(_opt(rest, "--roughness", 0.85)), size=int(_opt(rest, "--size", 1024)))
            print(f"  {Path(p).name} -> {Path(r['albedo']).name}, {Path(r['normal']).name} (normal from {r['normal_from']})")
        return 0
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
        out = Path(_opt(rest, "--out") or place.stage_dir(cfg, gid, str(pl.get("id") or "place"))
                   or (world.root_of(cfg) / "out" / "3d" / "places" / str(pl.get("id") or "place")))
        rep = place.compile_place(cfg, gid, files[0], out, games_root=world.games_dir(cfg) if gid else None,
                                  hold="--hold" in rest)
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
    print("usage: 3d place compile|check <place.json> [--game <id>] [--out <folder>] [--hold] · 3d place from-town <layout> --sheet <s.json>")
    return 2


def _default_game(cfg: dict) -> str:
    from . import config as cfgmod
    try:
        return cfgmod.default_game(cfg) or ""
    except Exception:  # noqa: BLE001
        return ""


def _cmd_same_person(cfg: dict, rest: list[str]) -> int:
    """3d same-person bakeoff [--game <id>] [--only <case>]   the bake-off (uses the card — the person's to start)
       3d same-person check <from.png> <result.png> [--region mouth_brows|arms|face] [--method masked] [--out check.png]"""
    import json
    import time
    from . import config as cfgmod
    from .threed import same_person as sp
    sub = rest[0] if rest else ""
    opt = lambda f, d=None: rest[rest.index(f) + 1] if f in rest else d
    if sub == "bakeoff":
        gid = opt("--game") or cfgmod.default_game(cfg)
        cases = json.loads((cfgmod.ROOT / "games" / gid / "same_person_bakeoff.json").read_text(encoding="utf-8"))["cases"]
        if opt("--only"):
            cases = [c for c in cases if c["id"] == opt("--only")]
        try:
            from .suite.games import game_root
            groot = game_root(cfg, gid)
        except Exception:  # noqa: BLE001
            groot = None
        out = cfgmod.ROOT / "out" / "same_person" / gid / time.strftime("%Y%m%d-%H%M")
        r = sp.bakeoff(cfg, cases, out, cfgmod.ROOT, groot)
        print(f"{r['rows']} results, {r['ok']} kept what they were told to keep — {Path(r['out']) / 'report.md'}")
        return 0
    if sub == "check":
        from PIL import Image
        a, b = Image.open(rest[1]).convert("RGB"), Image.open(rest[2]).convert("RGB")
        region = sp.make_mask(a, opt("--region")) if opt("--region") else None
        r = sp.moved(a, b, region, ["identity", "face", "clothes", "hair", "background"], opt("--method", "masked"))
        if opt("--out"):
            sp.check_picture(a, b, region, Path(opt("--out")))
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 1
    print(_cmd_same_person.__doc__)
    return 2


COMMANDS = {"3d": cmd_3d}
