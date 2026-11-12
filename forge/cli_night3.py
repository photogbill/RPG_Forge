"""Night 3 commands (kept apart from cli.py so each stays readable). Registered in cli.COMMANDS.

  report night [--since T] [--until T] [--hours 12] [--all] [--open]   the morning report → out/reports/night_<date>.html
"""
from __future__ import annotations
from . import config as cfgmod
import os
from datetime import datetime


def _opt(args, flag, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def _positional(args, flags_with_values=()):
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in flags_with_values:
            skip = True
            continue
        if not a.startswith("--"):
            out.append(a)
    return out


def _open(path) -> None:
    from .suite import osopen
    try:
        osopen.open_path(path)           # the default browser / viewer, on any computer
    except OSError:
        pass


def _when(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"not a time: {s!r} (use 2026-11-09T21:00)")


# ------------------------------------------------------------------ G1
def cmd_report(cfg: dict, args: list[str]) -> int:
    from . import night_report
    pos = _positional(args, ("--since", "--until", "--hours"))
    if not pos or pos[0] != "night":
        print("usage: report night [--since 2026-11-09T21:00] [--until …] [--hours 12] [--all] [--open]"); return 2
    ht, md, rep = night_report.build(cfg, since=_when(_opt(args, "--since")), until=_when(_opt(args, "--until")),
                                     hours=float(_opt(args, "--hours", 12)), everything="--all" in args)
    t = rep["totals"]
    print(f"report: {ht}\n        {md}")
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(t.items())))
    for n in rep["next"]:
        print(f"  next: {n}")
    if "--open" in args:
        _open(ht)
    return 0


# ------------------------------------------------------------------ G2 / G11
def cmd_review_compact(cfg: dict, args: list[str]) -> int:
    from . import review_compact as rc
    pos = _positional(args, ("--pairs", "--cells", "--max-side", "--crop", "--prompt", "--family", "--by", "--thumb"))
    try:
        if "--family" in args:
            out, idx = rc.build_family(cfg, _opt(args, "--family"), pos[0] if pos else None)
            print(f"family sheet: {out / idx['sheet']}  ({len(idx['cells'])} members)")
            if "--open" in args:
                _open(out / idx["sheet"])
            return 0
        if not pos:
            print("usage: review <suite-or-batch> --compact [--prompt P] [--cells 12]  |  --pairs A,B [--crop 640]  |  --family <template>")
            return 2
        if "--pairs" in args:
            ab = (_opt(args, "--pairs") or "").split(",")
            if len(ab) != 2:
                print("--pairs needs two names: A,B (two categories of the suite, or two job ids)"); return 2
            out, idx = rc.build_pairs(cfg, pos[0], ab[0].strip(), ab[1].strip(), int(_opt(args, "--crop", 640)),
                                      int(_opt(args, "--max-side", 2000)))
        else:
            out, idx = rc.build_compact(cfg, pos[0], int(_opt(args, "--cells", 12)), int(_opt(args, "--max-side", 2000)),
                                        prompt=_opt(args, "--prompt"))
    except ValueError as e:
        print(e); return 1
    big = max((s["bytes"] for s in idx["sheets"]), default=0)
    print(f"{len(idx['sheets'])} sheet(s) in {out}  (largest {big / 1e6:.2f} MB) · index: {out / 'review_index.json'}")
    if "--open" in args:
        _open(out)
    return 0


# ------------------------------------------------------------------ op: every new CPU op as a direct command
def _op_tiles_demo(cfg, args):
    from pathlib import Path
    from PIL import Image
    from . import config as cfgmod
    from .ops import bigtiles as bt
    W, H = [int(x) for x in (_opt(args, "--size", "6144x3072")).lower().split("x")]
    tile = [int(x) for x in (_opt(args, "--tile", "1344x768")).lower().split("x")]
    out = Path(_opt(args, "--out") or (cfgmod.path_of(cfg, "out") / "_tests" / "night3" / "tiles_demo"))
    out.mkdir(parents=True, exist_ok=True)
    src = Image.open(_opt(args, "--in")).convert("RGB") if _opt(args, "--in") else bt.test_picture((W, H))
    merged, rects, seams, naive = bt.demo(src, tile, int(_opt(args, "--overlap", 128)))
    merged.save(out / "merged.png")
    bt.seam_sheet(merged, rects, seams).save(out / "seam_sheet.jpg", quality=88)
    bt.seam_sheet(naive, rects, bt.seams([naive.crop(r) for r in rects], rects)).save(out / "naive_paste.jpg", quality=88)
    import json
    worst = max((x["score"] for x in seams), default=0)
    (out / "seams.json").write_text(json.dumps({"size": list(src.size), "tile": tile, "rects": rects, "seams": seams,
                                                "worst": worst}, indent=1), encoding="utf-8")
    print(f"{src.size[0]}x{src.size[1]} → {len(rects)} tiles {bt.grid_shape(rects)}; seams: {len(seams)}, worst {worst:.2f}")
    print(f"wrote {out}  (merged.png, seam_sheet.jpg, naive_paste.jpg for comparison, seams.json)")
    return 0


def _op_state_mask(cfg, args):
    from pathlib import Path
    from PIL import Image
    from .ops import state_mask as smk
    a, b, o = _opt(args, "--base"), _opt(args, "--state"), _opt(args, "--out")
    if not (a and b and o):
        print("usage: op state-mask --base greybox_base.png --state greybox_state.png --out mask.png [--grow 24] [--feather 12]")
        return 2
    try:
        mask, binary, share, rep = smk.state_mask(Image.open(a), Image.open(b), int(_opt(args, "--threshold", 12)),
                                                  int(_opt(args, "--grow", 24)), float(_opt(args, "--feather", 12)),
                                                  float(_opt(args, "--max-share", smk.MAX_SHARE)))
    except ValueError as e:
        print(f"refused: {e}"); return 1
    Path(o).parent.mkdir(parents=True, exist_ok=True)
    mask.save(o)
    binary.save(str(Path(o).with_name(Path(o).stem + "_changed.png")))
    print(f"mask: {o} — changed {rep['changed_share']:.1%} of the frame, mask {rep['mask_share']:.1%} (grown + feathered)")
    return 0


def _cpu_op(job_type):
    """Run a CPU plug-in job type directly: python -m forge op <name> --in X --out folder [--field value …]."""
    def run(cfg, args):
        import json
        from pathlib import Path
        from .jobs import get_handlers
        from .jobs.common import Context
        from . import config as cfgmod, schema
        src, out = _opt(args, "--in"), _opt(args, "--out")
        if not (src and out):
            print(f"usage: op {job_type.replace('_', '-')} --in <file or folder> --out <folder> [--mirror W>E,NW>NE] "
                  "[--margins l,t,r,b] [--fps 8] [--cell 144x216]"); return 2
        job = {"type": job_type, "id": f"op_{job_type}", "name": f"op_{job_type}", "input": str(Path(src).resolve())}
        if _opt(args, "--mirror"):
            job["mirror"] = _opt(args, "--mirror").split(",")
        if _opt(args, "--margins"):
            l, t, r, b = [int(x) for x in _opt(args, "--margins").split(",")]
            job["margins"] = {"left": l, "top": t, "right": r, "bottom": b}
        if _opt(args, "--cell"):
            job["cell"] = [int(x) for x in _opt(args, "--cell").lower().split("x")]
        for f in ("fps", "scale"):
            if _opt(args, f"--{f}"):
                job[f] = float(_opt(args, f"--{f}"))
        if _opt(args, "--key"):
            job["key"] = _opt(args, "--key")
        handlers = get_handlers()
        job = schema.with_defaults(job)
        o = Path(out).resolve()
        o.mkdir(parents=True, exist_ok=True)
        res = handlers[job_type](job, Context(cfg=cfg, root=cfgmod.ROOT, palettes_dir=cfgmod.ROOT / "palettes"), o)
        print(json.dumps({k: v for k, v in res.items()}, ensure_ascii=False, default=str))
        print(f"wrote {o}")
        return 0
    return run


OPS = {"tiles-demo": _op_tiles_demo, "state-mask": _op_state_mask,
       "facings-pack": _cpu_op("facings_pack"), "anim-preview": _cpu_op("anim_preview"),
       "turnaround-split": _cpu_op("turnaround_split"), "nine-slice": _cpu_op("nine_slice"),
       "button-states": _cpu_op("button_states")}


def cmd_op(cfg: dict, args: list[str]) -> int:
    if not args or args[0] not in OPS:
        print("usage: op <name> [--in …] [--out …]   ops: " + ", ".join(sorted(OPS))); return 2
    return OPS[args[0]](cfg, args[1:])


# ------------------------------------------------------------------ G5
def _kit_dir(cfg, ref):
    from pathlib import Path
    from . import config as cfgmod
    p = Path(ref)
    if p.is_dir():
        return p
    d = cfgmod.path_of(cfg, "out") / ref
    if d.is_dir():
        return d
    hits = sorted(x for x in cfgmod.path_of(cfg, "out").glob(f"*{ref}*") if x.is_dir())
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f"no single kit matches '{ref}'" + (f" ({len(hits)} do — give more of the id)" if hits else ""))


def cmd_kit(cfg: dict, args: list[str]) -> int:
    from . import kitcheck
    pos = _positional(args, ("--map", "--game"))
    if len(pos) < 2 or pos[0] != "check":
        print("usage: kit check <job-id or folder> [--map <map id>] [--game <id>]"); return 2
    kd = _kit_dir(cfg, pos[1])
    rep = kitcheck.check(cfg, kd, _opt(args, "--map"), (_opt(args, "--game") or cfgmod.default_game(cfg)))
    mark = {"pass": "ok  ", "warn": "WARN", "fail": "FAIL"}
    for l in rep["lines"]:
        print(f"  {mark[l['status']]} {l['check']:22s} {l['message']}")
    print(f"kit check: {rep['verdict'].upper()}  → {kd / 'check.png'}")
    if "--open" in args:
        _open(kd / "check.png")
    return 1 if rep["verdict"] == "fail" else 0


# ------------------------------------------------------------------ G6
def cmd_prompts(cfg: dict, args: list[str]) -> int:
    import json
    from . import prompts as pl
    pos = _positional(args, ("--game", "--on", "--n"))
    game = (_opt(args, "--game") or cfgmod.default_game(cfg))
    sub = pos[0] if pos else "list"
    try:
        lib = pl.load(cfg, game)
    except pl.PromptError as e:
        print(e); return 1
    if sub == "list":
        print(f"prompt library for {game} — version {lib['version']}, {len(lib['blocks'])} block(s); "
              f"never-list: {len(pl.never_words(lib))} word(s)")
        for name in sorted(lib["blocks"]):
            t = lib["blocks"][name]
            print(f"  {{{{{name}}}}}  {t[:70]}{'…' if len(t) > 70 else ''}   ({lib['files'][name]})")
        return 0
    if sub == "show" and len(pos) > 1:
        if pos[1] not in lib["blocks"]:
            print(f"no block '{pos[1]}'"); return 1
        print(lib["blocks"][pos[1]])
        try:
            print("expanded: " + pl.expand_text("{{" + pos[1] + "}}", lib["blocks"]))
        except pl.PromptError as e:
            print(f"(cannot expand: {e})")
        return 0
    if sub == "where-used" and len(pos) > 1:
        hits = pl.where_used(cfg, pos[1])
        for h in hits:
            print(f"  {h['where']:10s} {h['name']}  {h['batch'] or ''}  {h['id'] or ''}")
        print(f"{len(hits)} use(s) of {{{{{pos[1]}}}}}")
        return 0
    if sub == "check":
        probs = pl.check_library(lib)
        for f in pos[1:]:
            data = json.loads(open(f, encoding="utf-8").read())
            jobs = data["jobs"] if isinstance(data, dict) and "jobs" in data else [data]
            d = data.get("defaults", {}) if isinstance(data, dict) else {}
            try:
                pl.prepare(cfg, [{**d, **j} for j in jobs], game)
            except pl.PromptError as e:
                probs.append(f"{f}: {e}")
        for p_ in probs:
            print(f"  ✗ {p_}")
        print("prompt library: OK" if not probs else f"{len(probs)} problem(s)")
        return 1 if probs else 0
    if sub == "ab" and len(pos) > 1 and _opt(args, "--on"):
        try:
            out = pl.ab_drafts(cfg, pos[1], _opt(args, "--on"), int(_opt(args, "--n", 4)), game)
        except pl.PromptError as e:
            print(e); return 1
        print(f"wrote {out} — a same-seed pair (with / without {{{{{pos[1]}}}}}) per picture. Check, delete the _draft line, submit.")
        return 0
    print("usage: prompts list | show <block> | where-used <block> | check [batch.json …] | ab <block> --on <batch> [--n 4]")
    return 2


# ------------------------------------------------------------------ G10 / G11
def cmd_brief_missing(cfg: dict, args: list[str]) -> int:
    from . import brief_missing as bm
    game = (_opt(args, "--game") or cfgmod.default_game(cfg))
    try:
        p, rep, r = bm.write(cfg, game, refresh="--no-refresh" not in args)
    except (FileNotFoundError, ValueError) as e:
        print(e); return 1
    for n in r["notes"]:
        print(f"note: {n}")
    w = max([len(t["map"]) for t in r["table"]] + [3])
    print(f"{'map':{w}s}  {'size':10s} {'job type':12s} why / waits on")
    for t in r["table"]:
        print(f"{t['map']:{w}s}  {t['size']:10s} {t['type']:12s} {t['why']}" + (f"  — waits on: {t['waits_on']}" if t["waits_on"] else ""))
    print(f"\n{len(r['draft']['jobs'])} draft job(s) → {p}\ntable → {rep}\nNothing was submitted.")
    return 0


# ------------------------------------------------------------------ G8
def cmd_credits(cfg: dict, args: list[str]) -> int:
    from . import credits
    p, g = credits.write(cfg, (_opt(args, "--game") or cfgmod.default_game(cfg)))
    print(f"credits: {p}  ({g['approved']} approved file(s), {len(g['models'])} model(s); source: {g['source']})")
    for pr in g["problems"]:
        print(f"  ⚠ {pr}")
    if "--open" in args:
        _open(p)
    return 1 if g["problems"] else 0


COMMANDS = {"report": cmd_report, "op": cmd_op, "kit": cmd_kit, "prompts": cmd_prompts, "credits": cmd_credits}
