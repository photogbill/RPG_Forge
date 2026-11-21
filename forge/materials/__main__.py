"""The materials commands the .bat files run (BUILD 87). `python -m forge.materials <command> [--game <id>]`.

    ff-proof      prove, by rendering three filters small, which preset number is which Filter Forge channel
    ff-library    a true channel set for every picture of the game's texture library that Filter Forge made
    ff-picks      the same for every kept pick of the game's cull file   [--limit N] [--tiles]
    ff-seeds      two more seeds of every ground the game lists, and the three mixed (no repeats)
    mm-lint       check the forge's Material Maker graphs against the installed node library
    mm-first      export every forge graph in every state the game names (Material Maker, under the card lock)
    decals        make every decal the game's places name (colour, normal, roughness)
    sheets        one sheet a town, and every place's ground with its wear on and off
    graphs        write forge/materials/graphs again from forge/materials/mmgraph.py

Each command queues its jobs under its own batch and runs only those, here in this window — it does not start, stop
or feed the art worker, and other people's waiting jobs are left exactly where they are. Run one again and it carries
on: what is already made is skipped. Everything it did is in logs/materials.log.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path

from .. import config as cfgmod

log = logging.getLogger("forge.materials")


def _setup_log(cfg: dict) -> Path:
    p = cfgmod.path_of(cfg, "logs") / "materials.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(p, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("forge")
    root.addHandler(h)
    root.setLevel(logging.INFO)
    return p


def _queue(cfg: dict):
    from ..queue import Queue
    return Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))


def _done_names(cfg: dict, batch: str) -> set[str]:
    """Names of finished and waiting jobs (from the folders' file names alone — no file is opened). The names these
    commands give their jobs are their own (channels_…, seed1_…, mm_…, decal_…), so a name is enough."""
    names = set()
    for sub in ("done", "pending"):                 # waiting from a run that was closed counts too: never queued twice
        for f in (cfgmod.path_of(cfg, "jobs") / sub).glob("*.json"):
            parts = f.stem.split("-")
            if len(parts) >= 4:
                names.add("-".join(parts[2:-1]))
    return names


def _safe(name: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in (name or "job"))[:48]


def submit_and_run(cfg: dict, jobs: list[dict], batch: str, skip_done: bool = True) -> list[dict]:
    """Queue `jobs` under `batch` and run every pending job of that batch, in this process. Returns one row a job run:
    {id, name, ok, result | error}."""
    from ..jobs.common import Context
    from ..plugins import materials as plug
    from .. import schema
    schema.validate({"type": "ff_channels", "filter": "x.ffxml"})          # makes the schema learn the plug-in's types
    q = _queue(cfg)
    done = _done_names(cfg, batch) if skip_done else set()
    queued = 0
    for j in jobs:
        j = {**j, "batch": batch}
        if skip_done and _safe(j.get("name") or j["type"]) in done:
            continue
        q.submit(j)
        queued += 1
    print(f"  queued {queued} job(s) in batch '{batch}'" + (f" ({len(jobs) - queued} already done)" if queued != len(jobs) else ""), flush=True)
    ctx = Context(cfg=cfg, palettes_dir=cfgmod.path_of(cfg, "palettes"), root=cfgmod.ROOT)
    rows = []
    while True:
        got = q.claim(lambda job: job.get("batch") == batch and job.get("type") in plug.HANDLERS and not job.get("tombstone"))
        if got is None:
            break
        jid, job = got
        job = schema.with_defaults(job)
        out = q.out_dir(jid)
        t0 = time.time()
        print(f"  {time.strftime('%H:%M:%S')}  {job.get('name')} ...", end=" ", flush=True)
        try:
            res = plug.HANDLERS[job["type"]](job, ctx, out) or {}
            res["seconds"] = round(time.time() - t0, 1)
            q.finish(jid, result=res)
            rows.append({"id": jid, "name": job.get("name"), "ok": True, "result": res, "job": job})
            print(f"done in {res['seconds']:.0f} s", flush=True)
            log.info("done %s (%s): %s", jid, job.get("name"), json.dumps({k: res.get(k) for k in ("verdict", "true_channels", "notes", "delivered")}, default=str)[:900])
        except Exception as e:  # noqa: BLE001 - every failure is written down and the run goes on
            q.finish(jid, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc())
            rows.append({"id": jid, "name": job.get("name"), "ok": False, "error": f"{type(e).__name__}: {e}", "job": job})
            print("FAILED", flush=True)
            print("      " + str(e).replace("\n", "\n      ")[:1200], flush=True)
            log.error("FAILED %s (%s): %s", jid, job.get("name"), e)
        except BaseException:                      # 2026-11-20: Ctrl+C - the job in hand is not left in jobs/running
            q.finish(jid, error="stopped before it finished (Ctrl+C)")
            raise
    return rows


def _report(cfg: dict, game: str, name: str, lines: list[str]) -> Path:
    p = cfgmod.path_of(cfg, "out") / "materials" / game / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _game(cfg: dict, args) -> tuple[str, dict]:
    from . import sheets
    game = args.game or cfgmod.default_game(cfg)
    return game, sheets.load_game(cfgmod.ROOT, game)


# ------------------------------------------------------------------ Filter Forge
def cmd_ff_proof(cfg: dict, args) -> int:
    from ..night3b import ffdriver
    from . import ffchannels as F
    game, g = _game(cfg, args)
    root = cfgmod.ROOT
    cands: list[dict] = []
    if args.filter:
        cands = [{"filter": f, "preset": 0} for f in args.filter]
    else:
        plan = F.library_plan(root, root / g["library"])["jobs"]
        if g.get("cull"):
            try:
                plan += F.picks_plan(root, Path(g["cull"]), only_tiles=True)["jobs"][:60]
            except (OSError, ValueError):
                pass
        seen, by_type = set(), {}
        for j in plan:
            if j["filter"] in seen:
                continue
            seen.add(j["filter"])
            try:
                t = ffdriver.read_filter(Path(j["filter"]))["filter_type"]
            except (OSError, ValueError):
                continue
            by_type.setdefault(t, []).append({"filter": j["filter"], "preset": j["preset"]})
        for t in ("legacy surface", "PBR surface"):
            cands += by_type.get(t, [])[:2 if t == "legacy surface" else 1]
        if len(cands) < 3:
            cands += by_type.get("legacy surface", [])[2:5 - len(cands)]
        print("filter types among the planned renders: " + ", ".join(f"{t}: {len(v)}" for t, v in sorted(by_type.items())))
    if not cands:
        print("No Filter Forge filter to prove on (the library has none and none was named).")
        return 1
    jobs = [{"type": "ff_channel_proof", "name": f"ffproof_{Path(c['filter']).stem}", "filter": c["filter"], "preset": c["preset"],
             "priority": 5} for c in cands[:3]]
    rows = submit_and_run(cfg, jobs, "materials/ff_proof", skip_done=False)
    lines = [f"# Filter Forge channel proof - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    good = 0
    for r in rows:
        if r["ok"]:
            res = r["result"]
            good += res["verdict"] == "yes"
            lines += [f"- **{r['name']}** ({res['filter_type']}): **{res['verdict'].upper()}** - {res['evidence']}",
                      f"  numbers: `{json.dumps(res.get('numbers'))}` - picture: `out/{r['id']}/proof.png`"]
        else:
            lines += [f"- **{r['name']}**: FAILED - {r['error'][:600]}"]
    store = F.load_store(root).get("types", {})
    lines += ["", "On file now (local/ff_channels.json):"] + [f"- {t}: {v.get('verdict')} {json.dumps(v.get('numbers'))}" + (" - CONFLICT between proofs" if v.get("conflict") else "") for t, v in store.items()]
    p = _report(cfg, game, "ff_proof", lines)
    print("\n".join(lines[2:]))
    print(f"\nReport: {p}")
    if good:
        print("\nPROVED: Filter Forge renders a channel from a preset number in a working copy. The channel sets can be made.")
        return 0
    if any(r["ok"] and r["result"]["verdict"] == "partial" for r in rows):
        print("\nPARTLY: normal and height can be told; look at the proof pictures before the long run. Tell Claude.")
        return 0
    print("\nNOT PROVED: tell Claude what this window says - the proof pictures are in the folders named above.")
    return 2


def _channel_report(cfg: dict, game: str, name: str, plan: dict, rows: list[dict], extra: list[str]) -> Path:
    lines = [f"# {name} - {time.strftime('%Y-%m-%d %H:%M')}", ""] + extra + [""]
    for r in rows:
        if not r["ok"]:
            lines.append(f"- {r['name']}: FAILED - {r['error'][:500]}")
            continue
        res = r["result"]
        d = res.get("delivered") or {}
        lines.append(f"- {r['name']}: true {', '.join(res.get('true_channels') or []) or 'NONE'}; "
                     + ("beside the picture: " + ", ".join(d.get("written") or []) if d.get("written") else
                        "NOT put beside the picture: " + str(d.get("refused") or "nothing new to write"))
                     + f" - `out/{r['id']}/contact.png`")
        for ch, how in (res.get("channels") or {}).items():
            if not str(how).startswith("true"):
                lines.append(f"    - {ch}: {how}")
        for n in res.get("notes") or []:
            lines.append(f"    - note: {n}")
    return _report(cfg, game, name, lines)


def cmd_ff_library(cfg: dict, args) -> int:
    from . import ffchannels as F
    game, g = _game(cfg, args)
    plan = F.library_plan(cfgmod.ROOT, cfgmod.ROOT / g["library"])
    print(f"library {g['library']}: {len(plan['jobs'])} to render, {len(plan['already'])} already have a true set, "
          f"{len(plan['no_filter'])} were not made by Filter Forge")
    rows = submit_and_run(cfg, plan["jobs"], "materials/ff_channels", skip_done=False)
    extra = [f"Not made by Filter Forge (they keep the brightness guess): " + ", ".join(x["picture"] for x in plan["no_filter"])] if plan["no_filter"] else []
    p = _channel_report(cfg, game, "library_channels", plan, rows, extra)
    print(f"Report: {p}")
    return 0 if all(r["ok"] for r in rows) else 1


def towns_first(jobs: list[dict], game: dict) -> list[dict]:
    """The picks a town's sheet is waiting for go first (the rest keep the cull file's order), so a run that is cut
    short has still filled the sheets."""
    wanted = {str(pid) for t in (game.get("towns") or {}).values() for m in t.get("materials") or [] for pid in m.get("picks") or []}
    for spec in (game.get("places") or {}).values():
        wanted |= {str(m.get("pick")) for m in (spec.get("materials") or {}).values() if m.get("pick")}
    return sorted(jobs, key=lambda j: str(j.get("name", "")).replace("channels_pick_", "") not in wanted)


def cmd_ff_picks(cfg: dict, args) -> int:
    from . import ffchannels as F
    game, g = _game(cfg, args)
    if not g.get("cull"):
        print("The game's materials.json names no cull file.")
        return 1
    plan = F.picks_plan(cfgmod.ROOT, Path(g["cull"]), only_tiles=bool(args.tiles))
    ordered = towns_first(plan["jobs"], g)
    jobs = ordered[: args.limit] if args.limit else ordered
    print(f"kept picks: {len(plan['jobs'])} to render ({len(jobs)} this run), {len(plan['already'])} already have a true set, "
          f"{len(plan['skipped'])} skipped (no picture in use)")
    rows = submit_and_run(cfg, jobs, "materials/ff_picks_channels", skip_done=False)
    extra = ["Skipped: " + "; ".join(f"#{x['id']} ({x['why']})" for x in plan["skipped"])] if plan["skipped"] else []
    p = _channel_report(cfg, game, "picks_channels", plan, rows, extra)
    print(f"Report: {p}")
    return 0 if all(r["ok"] for r in rows) else 1


def cmd_ff_seeds(cfg: dict, args) -> int:
    from ..night3b import ffdriver
    from . import ffchannels as F
    game, g = _game(cfg, args)
    root = cfgmod.ROOT
    lib = root / g["library"]
    try:
        src = json.loads((lib / "_sources.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        src = {}
    jobs, firsts = [], {}
    for name in g.get("grounds") or []:
        pic = lib / f"{name}.png"
        frm = (src.get(name) or {}).get("from")
        base = F.job_for_picture(root, pic, ffdriver._resolve(root, frm).parent, "materials/ff_seeds") if (pic.is_file() and frm) else None
        if base is None:
            print(f"  {name}: no Filter Forge job behind it - no seeds")
            continue
        info = ffdriver.read_filter(Path(base["filter"]))
        pr = info["presets"][base["preset"]] if base["preset"] < len(info["presets"]) else {}
        v0 = int(pr.get("variation") or 1)
        firsts[name] = pic
        for k in (1, 2):
            v = (v0 + k * 7919 - 1) % 30000 + 1
            jobs.append({**base, "name": f"seed{k}_{name}", "slot_name": f"{name}_seed{k}", "variation": v, "beside": None,
                         "beside_stem": None, "match": None, "tileable": True})
    submit_and_run(cfg, jobs, "materials/ff_seeds")
    mixes = []
    out = cfgmod.path_of(cfg, "out")
    for name, first in firsts.items():
        seeds = []
        for k in (1, 2):
            hits = sorted(out.glob(f"*-seed{k}_{_safe(name)}-*/{name}_seed{k}.png"))
            if hits:
                seeds.append(hits[-1])
        if len(seeds) == 2:
            mixes.append({"type": "material_mix", "name": f"mix_{name}", "inputs": [str(first), str(seeds[0]), str(seeds[1])],
                          "slot_name": f"{name}_mix", "repeat": 2})
        else:
            print(f"  {name}: its two extra seeds are not both rendered - no mix yet")
    rows = submit_and_run(cfg, mixes, "materials/mix")
    lines = [f"# Three seeds and a mix - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for r in rows:
        lines.append(f"- {r['name']}: " + (f"repeats {r['result']['measured']['repeat_of_one_seed']} -> {r['result']['measured']['repeat_of_the_mix']} - `out/{r['id']}/contact.png`" if r["ok"] else "FAILED - " + r["error"][:400]))
    print(f"Report: {_report(cfg, game, 'mixes', lines)}")
    return 0


# ------------------------------------------------------------------ Material Maker
def cmd_mm_lint(cfg: dict, args) -> int:
    from . import mm
    exe = mm.exe_path(cfg)
    lib = mm.node_library(exe.parent)
    if not lib:
        print(f"Material Maker's node library is not at {exe.parent / 'nodes'} - nothing to check against.")
        return 1
    bad = 0
    for p in sorted(mm.GRAPHS.glob("*.ptex")):
        probs = mm.lint(json.loads(p.read_text(encoding="utf-8")), lib)
        stops = [x for x in probs if not x.startswith("note:")]
        bad += bool(stops)
        print(f"{p.name}: " + ("fits" if not probs else "; ".join(probs)))
    print(f"\n{len(lib)} node types in {exe.parent / 'nodes'}; " + ("every graph fits." if not bad else f"{bad} graph(s) do NOT fit."))
    return 1 if bad else 0


def cmd_mm_first(cfg: dict, args) -> int:
    from . import mm
    game, g = _game(cfg, args)
    states = g.get("states") or {"": None}
    jobs = []
    for p in sorted(mm.GRAPHS.glob("*.ptex")):
        if args.only and p.stem not in args.only:
            continue
        side = mm.side_file(p)
        for era, setting in states.items():
            if setting and setting not in (side.get("settings") or {}):
                continue
            slot = p.stem + (f"_{setting}" if setting else "")
            jobs.append({"type": "mm_material", "name": f"mm_{slot}", "graph": p.stem, "setting": setting, "size": int(args.size),
                         "slot_name": slot, "meta": {"suite": "materials", "category": "material_maker", "prompt_id": f"{p.stem} ({era}: {setting})",
                                                     "checkpoint": "material_maker", "lora": None, "seed": 0}})
    print(f"{len(jobs)} material(s) to export at {args.size} px. A small Material Maker window opens for each and closes by itself;\n"
          "each waits for the graphics card (the 3D queue keeps it while it makes a model, then lends it).")
    rows = submit_and_run(cfg, jobs, "materials/mm_first")
    lines = [f"# Material Maker, first graphs - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for r in rows:
        if r["ok"]:
            res = r["result"]
            lines.append(f"- {r['name']}: {', '.join(sorted(res['channels']))} in {res['seconds']:.0f} s (waited {res['measured'].get('waited_for_card', 0):.0f} s for the card), "
                         f"seam x {res['measured']['seam']['x']} y {res['measured']['seam']['y']} - `out/{r['id']}/contact.png`")
            lines += [f"    - note: {n}" for n in res.get("notes") or []]
        else:
            lines.append(f"- {r['name']}: FAILED - {r['error'][:700]}")
    print(f"Report: {_report(cfg, game, 'material_maker_first', lines)}")
    return 0 if rows and all(r["ok"] for r in rows) else (0 if not rows else 1)


# ------------------------------------------------------------------ decals, sheets
def cmd_decals(cfg: dict, args) -> int:
    from . import sheets
    game, g = _game(cfg, args)
    index = sheets.pick_index(cfgmod.ROOT, Path(g["cull"]) if g.get("cull") else None)
    jobs = []
    for place, spec in (g.get("places") or {}).items():
        for name, d in (spec.get("decals") or {}).items():
            rec = index.get(str(d.get("pick")))
            src = d.get("picture") or ((rec or {}).get("picture"))
            if not src:
                print(f"  decal '{name}' ({place}): its picture is not there")
                continue
            jobs.append({"type": "material_decal", "name": f"decal_{name}", "input": str(src), "slot_name": name,
                         **{k: d[k] for k in ("alpha_from", "tint", "relief", "strength", "edge", "depth", "rough_value", "seed") if k in d}})
    rows = submit_and_run(cfg, jobs, "materials/decals")
    for r in rows:
        print(f"  {r['name']}: " + (f"covers {r['result']['covers']:.0%} - out/{r['id']}/contact.png" if r["ok"] else "FAILED " + r["error"][:300]))
    return 0


def cmd_sheets(cfg: dict, args) -> int:
    from . import sheets
    game, g = _game(cfg, args)
    root = cfgmod.ROOT
    index = sheets.pick_index(root, Path(g["cull"]) if g.get("cull") else None)
    dest = cfgmod.path_of(cfg, "out") / "materials" / game
    (dest / "towns").mkdir(parents=True, exist_ok=True)
    lines = [f"# Material sheets - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for town in sorted(g.get("towns") or {}):
        if args.only and town not in args.only:
            continue
        img, missing = sheets.town_sheet(root, g, town, index, int(args.size))
        if img is None:
            lines.append(f"- {town}: nothing to show yet ({len(missing)} missing)")
            continue
        p = dest / "towns" / f"{town}.png"
        img.save(p)
        lines.append(f"- {town}: `{p.relative_to(root)}`" + (f" - missing: " + "; ".join(f"{m['word']} ({m['why']})" for m in missing) if missing else ""))
        print(f"  {town}: {p}", flush=True)
    for place in sorted(g.get("places") or {}):
        try:
            views, top, notes = sheets.place_pictures(root, g, place, index)
        except Exception as e:  # noqa: BLE001
            lines.append(f"- place {place}: could not be drawn - {e}")
            continue
        for layer, im in views.items():
            p = dest / f"{place}_{layer.lower()}.png"
            im.save(p)
            print(f"  {place} ({layer}): {p}", flush=True)
        top.save(dest / f"{place}_from_above.png")
        lines.append(f"- place {place}: " + ", ".join(f"`{place}_{k.lower()}.png`" for k in views) + (" - " + "; ".join(notes) if notes else ""))
    print(f"Report: {_report(cfg, game, 'sheets', lines)}")
    return 0


def cmd_graphs(cfg: dict, args) -> int:
    from . import mmgraph
    for p in mmgraph.build_all():
        print(f"wrote {p}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m forge.materials", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["ff-proof", "ff-library", "ff-picks", "ff-seeds", "mm-lint", "mm-first", "decals", "sheets", "graphs"])
    ap.add_argument("--game", default=None)
    ap.add_argument("--filter", action="append", help="ff-proof: an .ffxml to prove on (up to three)")
    ap.add_argument("--limit", type=int, default=0, help="ff-picks: at most this many this run")
    ap.add_argument("--tiles", action="store_true", help="ff-picks: tiles only (leave the single pictures)")
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--only", action="append", help="mm-first: a graph; sheets: a town")
    args = ap.parse_args(argv)
    if args.size is None:
        args.size = 2048 if args.command == "mm-first" else 512
    cfg = cfgmod.load()
    cfgmod.ensure_dirs(cfg)
    logfile = _setup_log(cfg)
    log.info("command %s %s", args.command, {k: v for k, v in vars(args).items() if v and k != "command"})
    try:
        return {"ff-proof": cmd_ff_proof, "ff-library": cmd_ff_library, "ff-picks": cmd_ff_picks, "ff-seeds": cmd_ff_seeds,
                "mm-lint": cmd_mm_lint, "mm-first": cmd_mm_first, "decals": cmd_decals, "sheets": cmd_sheets,
                "graphs": cmd_graphs}[args.command](cfg, args)
    except Exception as e:  # noqa: BLE001
        log.error("command %s failed: %s\n%s", args.command, e, traceback.format_exc())
        print(f"\nIt stopped: {e}\nThe whole story is in {logfile}. Tell Claude what this says.")
        return 3


if __name__ == "__main__":
    sys.exit(main())
