"""More connector operations (BUILD 98 Part 12, Claude Opus 2026-11-21): the slice, its measure, and the forge's tools.

✦ William, 2026-11-21: "By incorporating things into RPG Force, since we have a mcp connector for it, we can empower you
with access to even greater tools."

Loaded by forge/mcpserver/ops.py (every ops_*.py beside it), which calls install(ns) with its own namespace, so these
register in the same table whether ops.py runs as a module or as __main__. The one rule of ops.py holds here too: no new
rules — every change goes through a forge function William's own .bat files use (focus, blenderrun, library), signed.

    focus.status · focus.set · focus.resume          the art's focus (forge/focus.py; focus_linden_mills.bat)
    blender.profiles · blender.run · blender.status   William's Blender with one add-on profile (forge/blenderrun.py)
    tools.list                                        every outside tool: where, version, licence, the doctor's check
    library.search · library.import                   the Libraries shelf (forge/library.py), licence kept with each
    areas.board · slice.board                         checks 6 and 7 on every place; the slice and how far it is
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

SLICES = {
    "linden_mills": ["linden_mills_court", "bills_house", "linden_mills_street", "linden_mills_gas", "linden_mills_store",
                     "linden_mills_diner", "gun_store", "hobby_shop", "school_street", "sarahs_workshop", "uncle_workshop"],
}


def install(ns) -> None:
    op, done, error, refused = ns.op, ns.done, ns.error, ns.refused

    # -------------------------------------------------------------------------------------------- focus
    @op("focus.status", "read", "The art's focus: which place the world queue is working on, how many things it holds "
        "back for later and how many are for the focus.")
    def _focus_status(c, inp):
        from ..threed import world
        fs = sorted(world.list_dir(c.cfg, c.gid).glob("_focus_*.json"))
        rows = []
        for p in fs:
            d = json.loads(p.read_text(encoding="utf-8"))
            rows.append({"focus": d.get("focus"), "since": d.get("at"), "held": len(d.get("held") or []),
                         "kept": len(d.get("kept") or []), "said": d.get("said"), "file": c.rel(p)})
        return done({"foci": rows, "focused": bool(rows)},
                    "focus.resume (or resume_all_art.bat) takes exactly these holds off when William says the slice is "
                    "finished" if rows else "")

    def _focus_set_dry(c, inp):
        from .. import focus as f
        name = str(inp.get("place") or "linden_mills")
        if name not in f.FOCI:
            return error("not_found", f"no focus {name!r}; known: {', '.join(f.FOCI)}", "add it to forge/focus.py FOCI")
        with redirect_stdout(io.StringIO()):
            r = f.focus(name, dry=True)
        return {"status": "dry_run", "would": f"hold {len(r['hold'])} things not for {name}; {len(r['keep'])} stay",
                "files_written": 0}

    @op("focus.set", "change", "Focus the world queue on one place (holds everything else, writes exactly what it held). "
        "Known: linden_mills.", {"place": "optional: the focus name (default linden_mills)"}, dry=_focus_set_dry)
    def _focus_set(c, inp):
        from .. import focus as f
        name = str(inp.get("place") or "linden_mills")
        if name not in f.FOCI:
            return error("not_found", f"no focus {name!r}", "known: " + ", ".join(f.FOCI))
        with redirect_stdout(io.StringIO()):
            r = f.focus(name)
        return done({"held": len(r.get("held") or []), "kept": len(r.get("keep") or [])})

    def _focus_resume_dry(c, inp):
        from ..threed import world
        n = sum(len(json.loads(p.read_text(encoding="utf-8")).get("held") or [])
                for p in world.list_dir(c.cfg, c.gid).glob("_focus_*.json"))
        return {"status": "dry_run", "would": f"take {n} things off hold (every focus ends)", "files_written": 0}

    @op("focus.resume", "change", "End the focus: take off hold exactly the things the focus held (resume_all_art.bat). "
        "Only when William says the slice is finished.", {}, dry=_focus_resume_dry)
    def _focus_resume(c, inp):
        from .. import focus as f
        with redirect_stdout(io.StringIO()):
            n = f.resume()
        return done({"back_in_the_queue": n})

    # -------------------------------------------------------------------------------------------- Blender
    @op("blender.profiles", "read", "Blender add-on profiles (trees, buildings, interiors, ruins, terrain, osm, materials, "
        "retopo_bake, godot_export, animals, cloth, hard_surface, sky, people, painterly, uv, scatter) and their add-ons.")
    def _blender_profiles(c, inp):
        from .. import blenderrun
        p = blenderrun.load_profiles()
        return done({"program": blenderrun.blender_program(c.cfg, p),
                     "profiles": {k: v["modules"] for k, v in sorted(p["profiles"].items())},
                     "licences": p.get("licences")})

    def _blender_dry(c, inp):
        from .. import blenderrun
        try:
            cmd = blenderrun.command(str(inp["script"]), str(inp.get("profile") or ""), str(inp.get("blend") or ""),
                                     Path("<run folder>"), list(inp.get("args") or []))
        except blenderrun.RunError as ex:
            return error("invalid_input", str(ex), "blender.profiles lists them")
        return {"status": "dry_run", "would": "run " + " ".join(cmd), "files_written": 0}

    @op("blender.run", "change", "Run a Python script in William's Blender 5.3 in the background (--factory-startup) with "
        "only one profile's add-ons enabled. Its folder out/blender/<id>/ gets the log, boot.json and what the script "
        "writes (the script gets --out <folder> and FORGE_RUN_DIR). Runs on the processor; answers at once with the run id.",
        {"script": "required: a .py path (absolute, or inside the forge folder)",
         "profile": "optional: one of blender.profiles (none = factory, no add-ons)",
         "blend": "optional: a .blend to open first", "args": "optional: a list of arguments for the script",
         "name": "optional: a short name for the run folder"}, dry=_blender_dry)
    def _blender_run(c, inp):
        from .. import blenderrun
        try:
            r = blenderrun.start(str(inp["script"]), str(inp.get("profile") or ""), str(inp.get("blend") or ""),
                                 list(inp.get("args") or []), str(inp.get("name") or ""), c.who, c.cfg)
        except blenderrun.RunError as ex:
            return error("invalid_input", str(ex), "blender.profiles; tools.list says where Blender is")
        r["folder"] = c.rel(r["folder"])
        return done(r, "blender.status with this id (the run goes on after this call)")

    @op("blender.status", "read", "One Blender run (or the last 20): running, done or failed, which add-ons came up, the "
        "script's result, the files it wrote and the end of its log if it failed.", {"id": "optional: the run id"})
    def _blender_status(c, inp):
        from .. import blenderrun
        try:
            return done(blenderrun.status(str(inp.get("id") or ""), c.cfg))
        except blenderrun.RunError as ex:
            return error("not_found", str(ex), "blender.status with no id lists the runs")

    # -------------------------------------------------------------------------------------------- tools
    @op("tools.list", "read", "Every outside tool the forge drives or hands to William: where it is, whether the doctor "
        "finds it, its licence, what it is for and the connector op that drives it.",
        {"versions": "optional: true to ask each program its version (slower)"})
    def _tools_list(c, inp):
        from .. import toolsreg
        rows = toolsreg.listing(c.cfg, with_version=bool(inp.get("versions")))
        return done({"tools": rows, "missing": [r["name"] for r in rows if r["state"] == "not installed"]})

    # -------------------------------------------------------------------------------------------- the Libraries shelf
    @op("library.search", "read", "Search the Libraries shelf (every asset with its licence), or Poly Haven itself with "
        "online: true (CC0; read only).", {"words": "required", "kind": "optional: texture | model | hdri",
                                           "online": "optional: true to search Poly Haven's list"})
    def _library_search(c, inp):
        from .. import library
        if inp.get("online"):
            return done({"online": library.search_online(str(inp["words"]), str(inp.get("kind") or "texture"))},
                        "library.import {source: polyhaven, id} puts one on the shelf with its licence")
        return done({"shelf": library.search(str(inp["words"]), str(inp.get("kind") or ""), c.cfg)})

    def _lib_dry(c, inp):
        return {"status": "dry_run", "would": f"put {inp.get('source')} {inp.get('id')} on the shelf (library/) with its "
                "licence line", "files_written": 0}

    @op("library.import", "change", "Put one asset on the Libraries shelf with its licence: polyhaven or ambientcg by id "
        "(CC0, downloaded at res), or folder: a path already on disk (a Fab download, a scan) with its licence line.",
        {"source": "required: polyhaven | ambientcg | folder", "id": "required: the asset id, or the folder's path",
         "res": "optional: 1k / 2k / 4k (default 2k)", "licence": "folder only: the asset's licence line",
         "as": "folder only: the shelf's source name (fab, scan, blenderkit)", "name": "optional"}, dry=_lib_dry)
    def _library_import(c, inp):
        from .. import library
        try:
            src = str(inp["source"])
            if src == "polyhaven":
                r = library.import_polyhaven(str(inp["id"]), str(inp.get("res") or "2k"), c.who, c.cfg)
            elif src == "ambientcg":
                r = library.import_ambientcg(str(inp["id"]), str(inp.get("res") or "2K").upper(), c.who, c.cfg)
            elif src == "folder":
                r = library.import_folder(str(inp["id"]), str(inp.get("as") or "own"), str(inp.get("licence") or ""),
                                          str(inp.get("name") or ""), "", c.who, c.cfg)
            else:
                return error("invalid_input", f"no source {src!r}", "polyhaven, ambientcg or folder")
        except library.LibraryError as ex:
            return refused(str(ex))
        return done(r)

    # -------------------------------------------------------------------------------------------- the measure
    def _measure_paths(c):
        from ..suite import games, places3d
        from ..threed import world
        gdir = places3d.places_dir(c.cfg, c.gid)
        game_dir = gdir.parent
        root = None
        try:
            root = games.game_root(c.cfg, c.gid)
        except Exception:  # noqa: BLE001
            root = None
        stage = (Path(root) / "project" / "data" / "stage.json") if root else None
        from .. import config as cfgmod
        out = cfgmod.path_of(c.cfg, "out") / "areas" / c.gid
        return gdir, game_dir / "area_rules.json", world.list_dir(c.cfg, c.gid), stage, out

    @op("areas.board", "read", "The areas board: checks 6 (repeats in one map-camera view) and 7 (dressing: things per "
        "100 m² a zone against its target, the largest empty stretch) on every place, or on the places named. Writes its "
        "reports and a zones picture a place (out/areas/<game>/).", {"places": "optional: a list of place ids"})
    def _areas_board(c, inp):
        from ..threed import areacheck_dressing as ad
        gdir, rules_p, wanted, stage, out = _measure_paths(c)
        rules = ad.load_rules(rules_p)
        res = ad.board(gdir, rules, ad.load_sizes(wanted), ad.camera_view(stage, rules), out,
                       list(inp.get("places") or []) or None)
        return done({"board": c.rel(out / "board.md"), "rows": res["rows"], "view_m": res["view_m"]})

    @op("slice.board", "read", "Every place of a slice (default linden_mills) and how far it is from finished: dressing and "
        "repeats (checks 6–7), delivered and people (checks 8, 10), with what is not measured yet said plainly.",
        {"slice": "optional: linden_mills"})
    def _slice_board(c, inp):
        from ..threed import areacheck, areacheck_dressing as ad, world
        name = str(inp.get("slice") or "linden_mills")
        if name not in SLICES:
            return error("not_found", f"no slice {name!r}", "known: " + ", ".join(SLICES))
        gdir, rules_p, wanted, stage, out = _measure_paths(c)
        rules = ad.load_rules(rules_p)
        sizes = ad.load_sizes(wanted)
        view = ad.camera_view(stage, rules)
        st = world.status(c.cfg, c.gid)
        rows = []
        for pid in SLICES[name]:
            if not (gdir / f"{pid}.place.json").exists():
                rows.append({"place": pid, "state": "no place plan"})
                continue
            r = ad.check_place(gdir, pid, rules, sizes, view, out, picture=True)
            base = areacheck.check(c.cfg, c.gid, pid, status=st, write=False)
            rep, dres = r["checks"][0], r["checks"][1]
            rows.append({"place": pid, "dressing": dres["line"], "repeats": rep["line"],
                         "checks": {x["id"]: x["ok"] for x in base["checks"]} | {"repeats": rep["ok"], "dressing": dres["ok"]},
                         "lines": [x["line"] for x in base["checks"]],
                         "not_measured_yet": ["scale", "stretch", "grounding", "clipping", "sharpness", "the look holds",
                                              "life (Part 6)", "sound (Part 10)", "vista (Part 5)", "hero things (Part 2)",
                                              "William has played it"]})
        return done({"slice": name, "places": rows})
