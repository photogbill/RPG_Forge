"""`python -m forge terrain …` — real ground from DTED Level 0 (BUILD 77). The screen is 3D → Terrain.

    terrain status                    the folder, whether it was found, cells counted, levels skipped
    terrain check <lat> <lon>         the height there and which cell answered
    terrain proof [--json]            the reader against known ground (summits, low points) — before anything is baked
    terrain bake [--game <id>] [--only <window>]   bake the game's windows: heights (16-bit), shaded relief, how each
                                      height was produced, water (when the Natural Earth files are there), a contact sheet
    terrain profile <lat>,<lon> (--to <lat>,<lon> | --bearing <deg> --length <m>) [--grade 0.02] [--step 100]
                    [--from-height <m>] [--title "..."] [--out <png>]
    terrain profile --story [--game <id>]   every line the game's own terrain file asks for

The data stays where it is kept: forge.json -> "dted_dir" (default local/dted, git-ignored); cells are read straight from
a zip. Nothing here uses the graphics card.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import config as cfgmod


def dted_dir(cfg: dict) -> Path:
    p = Path(str(cfg.get("dted_dir") or "local/dted"))
    return p if p.is_absolute() else cfgmod.ROOT / p


def library(cfg: dict):
    from .terrain.dted import Library
    return Library.open(dted_dir(cfg))


def _opt(args, flag, d=None):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else d


def _pt(s: str) -> tuple[float, float]:
    a, b = s.split(",")
    return float(a), float(b)


def default_game(cfg: dict) -> str:
    """The game the forge is set to (forge.json -> default_game), as the other commands take it."""
    return cfgmod.default_game(cfg)


def world_file(cfg: dict, gid: str) -> dict:
    """The game's windows (games/<id>/terrain/world.json — geography only, public) merged with its story's edits and lines
    (the game's own folder: terrain/story.json — never in the forge)."""
    w = {}
    p = cfgmod.ROOT / "games" / gid / "terrain" / "world.json"
    if p.exists():
        w = json.loads(p.read_text(encoding="utf-8"))
    try:
        from .suite.games import game_root
        root = game_root(cfg, gid)
    except Exception:  # noqa: BLE001
        root = None
    story = {}
    if root is not None and (Path(root) / "terrain" / "story.json").exists():
        story = json.loads((Path(root) / "terrain" / "story.json").read_text(encoding="utf-8"))
    edits = story.get("edits") or []
    for win in w.get("windows") or []:
        win["edits"] = [e for e in edits if e.get("at") is not None and win["south"] <= e["at"][0] <= win["north"]
                        and win["west"] <= e["at"][1] <= win["east"]]
    w["profiles"] = story.get("profiles") or []
    w["story_file"] = str(Path(root) / "terrain" / "story.json") if root is not None else None
    w["out"] = str(cfgmod.ROOT / "out" / "terrain" / gid)
    return w


def bake_all(cfg: dict, gid: str, only: str | None = None, log=print) -> dict:
    from PIL import Image, ImageDraw
    from .terrain import bake
    lib = library(cfg)
    if not lib.found:
        return {"ok": False, "message": f"No DTED cells in {dted_dir(cfg)} — put the Level 0 folder or its zip there (forge.json -> dted_dir)."}
    w = world_file(cfg, gid)
    out = Path(w["out"])
    out.mkdir(parents=True, exist_ok=True)
    done, sheet = [], []
    ne = cfgmod.ROOT / "local" / "natural_earth"
    for win in w.get("windows") or []:
        if only and win["id"] != only:
            continue
        t0 = time.time()
        dials = dict(win.get("dials") or {})
        hp = bake.terrain_window(lib, win, out / f"{win['id']}_height.png", dials)
        sp = bake.terrain_shade(lib, win, out / f"{win['id']}_shade.png", {**dials, "posts": int(dials.get("shade_posts", 900))},
                                layers_out=out / f"{win['id']}_how.png")
        wr = bake.terrain_water(out / f"{win['id']}_shade.png", win, ne, out / f"{win['id']}_water.png")
        log(f"{win['id']}: {hp['size_m']['width'] / 1000:.0f} x {hp['size_m']['height'] / 1000:.0f} km, {hp['cells']} cells, "
            f"heights {hp['base_m']:.0f} to {hp['base_m'] + hp['range_m']:.0f} m, {len(win.get('edits') or [])} edit(s), "
            f"water: {'drawn' if wr.get('ok') else 'no files yet'} — {time.time() - t0:.0f} s")
        done.append({"id": win["id"], "height": hp, "water": wr.get("ok", False)})
        sheet.append((win, out / f"{win['id']}_shade.png", out / f"{win['id']}_how.png",
                      out / f"{win['id']}_water.png" if wr.get("ok") else None))
    if sheet:
        from .threed.checks import _font
        font, plain = _font(15)
        T = 360
        rows = []
        for win, a, b, c in sheet:
            ims = [Image.open(p).convert("RGB") for p in (a, b, c) if p is not None and Path(p).exists()]
            for im in ims:
                im.thumbnail((T, T))
            rows.append((win, ims, max([im.height for im in ims] or [T])))
        S = Image.new("RGB", (T * 3, sum(hh + 30 for _, _, hh in rows)), (20, 22, 28))
        d = ImageDraw.Draw(S)
        y = 0
        for k, (win, ims, hh) in enumerate(rows):
            for i, im in enumerate(ims):
                S.paste(im, (i * T, y))
            d.text((6, y + hh + 6), plain(f"{win['id']} — {win.get('name', '')}   (shaded · how each height was made: "
                                                        "blue measured, amber invented, red edited · with water)"),
                   fill=(255, 220, 150), font=font)
            y += hh + 30
        S.save(out / "contact_sheet.png")
    return {"ok": True, "windows": done, "out": str(out), "contact_sheet": str(out / "contact_sheet.png") if sheet else None}


def cmd_terrain(cfg: dict, args: list[str]) -> int:
    sub = args[0] if args else "status"
    if sub == "status":
        lib = library(cfg)
        s = lib.summary()
        print(json.dumps({**s, "dted_dir": str(dted_dir(cfg)), "found": lib.found, "skipped_examples": lib.skipped[:5]}, indent=1))
        return 0 if lib.found else 1
    if sub == "check":
        lat, lon = float(args[1]), float(args[2])
        h, cell = library(cfg).height_at(lat, lon)
        print(f"{lat}, {lon}: " + (f"{h:.1f} m (cell {cell})" if h is not None else "no data here (DTED has no sea)"))
        return 0
    if sub == "proof":
        from .terrain import proof
        t = proof.table(library(cfg))
        print(json.dumps(t, indent=1) if "--json" in args else proof.markdown(t))
        return 1 if t["stop"] else 0
    if sub == "bake":
        r = bake_all(cfg, _opt(args, "--game") or default_game(cfg), _opt(args, "--only"))
        print(r.get("message") or f"baked {len(r['windows'])} window(s) into {r['out']}; contact sheet: {r['contact_sheet']}")
        return 0 if r["ok"] else 1
    if sub == "profile":
        from .terrain import bake
        lib = library(cfg)
        if "--game" in args or "--story" in args:
            w = world_file(cfg, _opt(args, "--game") or default_game(cfg))
            out = Path(w["out"])
            out.mkdir(parents=True, exist_ok=True)
            for pr in w["profiles"]:
                p = bake.profile(lib, tuple(pr["start"]), tuple(pr["end"]) if pr.get("end") else None, pr.get("bearing"),
                                 pr.get("length_m"), float(pr.get("step_m", 100)), float(pr.get("grade", 0.0)), pr.get("start_height_m"))
                (out / f"{pr['id']}_profile.json").write_text(json.dumps(p, indent=1), encoding="utf-8")
                bake.profile_picture(p, out / f"{pr['id']}_profile.png", pr.get("title", pr["id"]))
                co = p["comes_out"]
                print(f"{pr['id']}: highest {p['highest']['m']} m at {p['highest']['km']} km; "
                      + (f"a {float(pr.get('grade', 0)) * 100:.1f}% line goes in at {p['goes_in']['km']} km and comes out at {co['km']} km "
                         f"({co['bore_miles']} miles of rock) at {co['m']} m" if co else "the line does not come out"))
            return 0
        start = _pt(args[1])
        end = _pt(_opt(args, "--to")) if "--to" in args else None
        p = bake.profile(lib, start, end, float(_opt(args, "--bearing", 90)), float(_opt(args, "--length", 20000)),
                         float(_opt(args, "--step", 100)), float(_opt(args, "--grade", 0.0)),
                         float(_opt(args, "--from-height")) if "--from-height" in args else None)
        o = Path(_opt(args, "--out", str(cfgmod.ROOT / "out" / "terrain" / "profile.png")))
        bake.profile_picture(p, o, _opt(args, "--title", ""))
        o.with_suffix(".json").write_text(json.dumps(p, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in p.items() if k != "samples"}, indent=1))
        return 0
    print(__doc__)
    return 2


COMMANDS = {"terrain": cmd_terrain}
