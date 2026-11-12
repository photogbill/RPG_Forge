"""Tile commands (BUILD 30) — the materials bake-off and the autotile builder.

    python -m forge tiles materials [--game <id>]          the material list (the game's, else the forge's first pass)
    python -m forge tiles plan [--game <id>]               write the bake-off: two txt2img suites + the Filter Forge jobs
    python -m forge tiles submit [--game <id>]             queue the Filter Forge jobs (skips what's already done) — a person runs it
    python -m forge tiles report [--game <id>]             contact sheets, scores, MATERIALS_VERDICT.md → out/bakeoff/materials/
    python -m forge tiles pick <material> <source>         a person's pick (the verdict draft suggests, it never picks)
    python -m forge tiles weathering plan|submit           the War and the After from the picked tiles (img2img vs Filter Forge)
    python -m forge tiles build <name> --floor <m|file> [--edge <m|file>] [--wall <m|file>] [--kind blob47|set16]
                                [--style soft|hard|ragged|crumbly] [--px N | --scale 2] [--variants 6] [--seed 0] [--no-world]
                                                           a tile set → out/tiles/<game>/<name>/ (atlas, normals, decals, manifest)
A material given by id uses the picked tile from the verdict; a file path uses that picture (it must tile).
Baked tiles default to 2x the game's tile size; the world textures keep the material's full resolution (up to 4096 px).
bakeoff_materials.bat runs plan + submit (and report when given "report").
"""
from __future__ import annotations
import json
from pathlib import Path


def _opts(args):
    pos, o, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                o[a[2:]] = args[i + 1]
                i += 2
                continue
            o[a[2:]] = True
        else:
            pos.append(a)
        i += 1
    return pos, o


def _game(cfg, o):
    from . import config as cfgmod
    from .suite import games
    gid = o.get("game") if isinstance(o.get("game"), str) else cfgmod.default_game(cfg)
    adp = games.adapter(cfg, gid) if gid and games.has_adapter(cfg, gid) else None
    return gid, adp


def materials_for(adp) -> list[dict]:
    from .tiles import materials as M
    if adp is not None and hasattr(adp, "material_list"):
        ms = adp.material_list()
        if ms:
            return ms
    return [dict(m) for m in M.DEFAULT]


def refs_for(adp) -> list:
    from PIL import Image
    out = []
    if adp is not None and hasattr(adp, "material_refs"):
        for p in adp.material_refs()[:12]:
            try:
                out.append(Image.open(p).convert("RGB"))
            except Exception:  # noqa: BLE001
                pass
    return out


def materials_dir(cfg) -> Path:
    from . import config as cfgmod
    return cfgmod.path_of(cfg, "out") / "bakeoff" / "materials"


def _listing(cfg):
    try:
        from .night3b import ffdriver
        if not ffdriver.exe_path(cfg):
            return {}, "Filter Forge isn't set up in forge.json (tools.filter_forge.exe) — its side of the bake-off is left out"
        listing = ffdriver.list_filters(cfg)
        if not listing:
            return {}, ("no Filter Forge filters were found (looked in: " + ", ".join(str(d) for _l, d in ffdriver.library_dirs(cfg))
                        + ") — its side of the bake-off is left out" if ffdriver.library_dirs(cfg) else
                        "Filter Forge's filter library wasn't found on this computer — its side of the bake-off is left out")
        return listing, None
    except Exception as e:  # noqa: BLE001
        return {}, f"Filter Forge's filters couldn't be listed ({e}) — its side of the bake-off is left out"


def _image_for(cfg, ref: str):
    from PIL import Image
    p = Path(ref)
    if p.exists():
        return Image.open(p).convert("RGB"), str(p)
    v = materials_dir(cfg) / "verdict.json"
    if v.exists():
        pk = (json.loads(v.read_text(encoding="utf-8")).get("picks") or {}).get(ref)
        if pk and Path(pk["image"]).exists():
            return Image.open(pk["image"]).convert("RGB"), f"{ref} (picked: {pk['source']})"
    raise SystemExit(f"'{ref}' is neither a picture nor a picked material (tiles pick {ref} <source> first)")


def cmd_tiles(cfg: dict, args: list[str]) -> int:
    from .tiles import materials as M
    pos, o = _opts(args)
    sub = pos[0] if pos else ""
    gid, adp = _game(cfg, o)
    if sub == "materials":
        ms = materials_for(adp)
        for m in ms:
            extra = f"  used by: {', '.join(m['used_by'])}" if m.get("used_by") else ""
            print(f"{m['id']:20} {m['name']:28} eras {','.join(m.get('eras') or ['peace', 'war', 'after'])}{extra}")
        need = adp.material_needs() if adp is not None and hasattr(adp, "material_needs") else {}
        for t, roles in need.items():
            print(f"  {t}: " + ", ".join(f"{r} = {m}" for r, m in roles.items()))
        return 0
    if sub == "plan":
        ms = materials_for(adp)
        from .suite import games
        gdir = games.games_dir(cfg) / gid
        paths = M.write_suites(gdir, M.suites(gid, ms))
        listing, why = ({}, "left out (--no-ff)") if o.get("no-ff") else _listing(cfg)
        mp = gdir / "bakeoff" / "materials_ff_map.json"          # {material: [filter file stem or name, …]} by real names
        chosen = json.loads(mp.read_text(encoding="utf-8")).get("materials", {}) if mp.exists() else {}
        jobs, missing = M.ff_jobs(gid, ms, listing, chosen=chosen)
        jp = gdir / "bakeoff" / f"{M.SUITES['ff']}.jobs.json"
        jp.write_text(json.dumps(jobs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(ms)} materials · suites: {', '.join(p.name for p in paths)} · Filter Forge: {len(jobs)} jobs → {jp.name}")
        if why:
            print(f"  {why}")
        elif missing:
            print(f"  no Filter Forge filter's name matches: {', '.join(missing)} (those are SDXL and Klein only)")
        if not jobs and not o.get("no-ff"):
            print("  Filter Forge has no jobs in this bake-off.")
            return 3                                   # bakeoff_materials.bat asks before queuing the rest
        return 0
    if sub == "submit":
        from . import config as cfgmod, dedupe
        from .queue import Queue
        from .suite import games, settings
        who = settings.identity()
        if settings.is_assistant(who):
            print("queuing the bake-off is the person's (bakeoff_materials.bat) — the plan is written, nothing queued")
            return 1
        jp = games.games_dir(cfg) / gid / "bakeoff" / f"{M.SUITES['ff']}.jobs.json"
        jobs = json.loads(jp.read_text(encoding="utf-8")) if jp.exists() else []
        new, skipped = dedupe.filter_new(cfg, jobs, f"bakeoff/{M.SUITES['ff']}")
        q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
        ids = [q.submit(j) for j in new]
        print(f"Filter Forge: queued {len(ids)} ({sum(skipped.values())} already queued or done)")
        return 0
    if sub == "report":
        found = __import__("forge.tiles.report", fromlist=["collect"]).collect(cfg, [M.SUITES["sdxl"], M.SUITES["klein"], M.SUITES["ff"], M.SUITES["weather"]])
        if not found:
            print("nothing has finished yet — run the worker, then this again")
            return 1
        from .tiles import report as R
        names = {m["id"]: m["name"] for m in materials_for(adp)}
        v = R.report(found, materials_dir(cfg), refs_for(adp), names)
        print(f"{len(v['materials'])} materials → {materials_dir(cfg)} (MATERIALS_VERDICT.md, one sheet each)")
        return 0
    if sub == "pick":
        from .suite import settings
        from .tiles import report as R
        if len(pos) < 3:
            print("usage: tiles pick <material> <source>")
            return 2
        who = o.get("who") if isinstance(o.get("who"), str) else settings.identity()
        try:
            p = R.pick(materials_dir(cfg), pos[1], pos[2], who)
        except ValueError as e:
            print(f"not picked: {e}")
            return 1
        print(f"{pos[1]}: {p['source']} (picked by {p['by']})")
        return 0
    if sub == "weathering":
        from . import config as cfgmod, dedupe
        from .queue import Queue
        from .suite import games, settings
        act = pos[1] if len(pos) > 1 else "plan"
        v = materials_dir(cfg) / "verdict.json"
        picks = (json.loads(v.read_text(encoding="utf-8")).get("picks") or {}) if v.exists() else {}
        if not picks:
            print("no picks yet — the weathering pass starts from the Peace tiles you picked")
            return 1
        listing, _why = _listing(cfg)
        mp = games.games_dir(cfg) / gid / "bakeoff" / "materials_ff_map.json"
        wchosen = json.loads(mp.read_text(encoding="utf-8")).get("weathering", {}) if mp.exists() else {}
        jobs, notes = M.weathering_jobs(gid, picks, materials_for(adp), listing, chosen=wchosen)
        jp = games.games_dir(cfg) / gid / "bakeoff" / f"{M.SUITES['weather']}.jobs.json"
        if act == "plan":
            jp.write_text(json.dumps(jobs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            print(f"weathering: {len(jobs)} jobs for {len(picks)} picked materials → {jp.name}")
            for n in notes:
                print(f"  {n}")
            return 0
        if settings.is_assistant(settings.identity()):
            print("queuing is the person's — the plan is written, nothing queued")
            return 1
        new, skipped = dedupe.filter_new(cfg, jobs, f"bakeoff/{M.SUITES['weather']}")
        q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
        print(f"weathering: queued {len([q.submit(j) for j in new])} ({sum(skipped.values())} already queued or done)")
        return 0
    if sub == "build":
        from . import config as cfgmod
        from .tiles import autotile as A
        if len(pos) < 2 or not isinstance(o.get("floor"), str):
            print("usage: tiles build <name> --floor <material|file> [--edge …] [--wall …] [--kind blob47|set16]")
            return 2
        floor, f_from = _image_for(cfg, o["floor"])
        edge, e_from = _image_for(cfg, o["edge"]) if isinstance(o.get("edge"), str) else (None, None)
        wall, w_from = _image_for(cfg, o["wall"]) if isinstance(o.get("wall"), str) else (None, None)
        from .suite import games
        base = int((games.game_cfg(cfg, gid) or {}).get("tile_size") or 96) if gid else 96
        T = int(o.get("px") or base * int(o.get("scale") or 2))        # the game's tile size, at 2x unless told
        if T < base:
            print(f"note: {T} px is below the game's own tile size ({base} px) — it will look soft")
        out = cfgmod.path_of(cfg, "out") / "tiles" / gid / pos[1]
        man = A.build_set(pos[1], out, floor=floor, edge=edge, wall=wall, T=T, style=str(o.get("style") or "ragged"),
                          variants=int(o.get("variants") or 6), seed=int(o.get("seed") or 0),
                          kind=str(o.get("kind") or "blob47"), info={"floor": f_from, "edge": e_from, "wall": w_from},
                          world=not o.get("no-world"))
        w = man.get("world") or {}
        print(f"{pos[1]}: {len(man['tiles'])} tiles + {len(man['decals'])} decals at {T} px → {out}"
              + (f"\n  world textures at full resolution: {w.get('a_px')} px (one period spans {w.get('period_tiles_a')} tiles)"
                 if w else ""))
        return 0
    print(__doc__)
    return 2


COMMANDS = {"tiles": cmd_tiles}
