"""Night 3B commands (kept apart from cli.py; registered in cli.COMMANDS).

  handoff out <batch | job ids …> --to out/handoff/<name>/in      hand pictures to an outside tool (handoff_out.bat)
  handoff in <name> [--tool "<name version>"] [--priority 10] [--no-submit]   file what came back (handoff_in.bat)
  handoff tool add ["<name>" "<version>" yes|no "<condition>" "<where checked>"]   one licence line per tool
  handoff tool list
  filter-forge list [--all]          the .ffxml filters the forge can see (install folder + your own library), read-only
  filter-forge presets <filter>      a filter's presets: number, seamless, size, which channel it renders
  filter-forge check                 is Filter Forge configured? (forge.json tools.filter_forge.exe)
  filter-forge task <job.json>       write the task XML a filter_forge job would run, without running it
"""
from __future__ import annotations
import json
from pathlib import Path

from .cli_night3 import _opt, _positional


def cmd_handoff(cfg: dict, args: list[str]) -> int:
    from . import handoff as ho
    if not args or args[0] not in ("out", "in", "tool"):
        print(ho.__doc__); return 2
    sub, rest = args[0], args[1:]
    try:
        if sub == "out":
            refs = _positional(rest, ("--to", "--name"))
            if not refs:
                print("usage: handoff out <batch | job ids …> --to out/handoff/<name>/in"); return 2
            man = ho.hand_out(cfg, refs, to=_opt(rest, "--to"), name=_opt(rest, "--name"))
            print(f"handed out {len(man['entries'])} picture(s) → {man['in']}")
            for e in man["entries"]:
                print(f"  {e['file']:70s} make it {e['target_size'][0]}x{e['target_size'][1]}" + ("  (kit)" if e["kit"] else ""))
            for n in man["notes"]:
                print(f"  note: {n}")
            print(f"Run your tool on that folder, save the results into {man['done']} keeping the start of each name, "
                  f"then: handoff_in.bat {man['name']}   (instructions: README.txt beside it)")
            return 0
        if sub == "in":
            pos = _positional(rest, ("--tool", "--priority"))
            if not pos:
                print('usage: handoff in <name> [--tool "<name version>"] [--priority 10] [--no-submit]'); return 2
            rep = ho.hand_in(cfg, pos[0], tool=_opt(rest, "--tool"), submit="--no-submit" not in rest,
                             priority=int(_opt(rest, "--priority", "10")))
            print(f"hand-off '{rep['name']}' — tool: {rep['tool']}")
            for f in rep["filed"]:
                print(f"  ✓ {f['returned']} → job {f['job']}")
            for m in rep["missing"]:
                print(f"  ✗ MISSING: nothing came back for {m}")
            for w in rep["wrong_size"]:
                print(f"  ✗ WRONG SIZE: {w}")
            for x in rep["extra"]:
                print(f"  ? not from this hand-off (left alone): {x}")
            for n in rep["notes"]:
                print(f"  note: {n}")
            for w in rep["warnings"]:
                print(f"  ⚠ {w}")
            if rep["jobs"]:
                print(f"queued {len(rep['jobs'])} job(s) in batch handoff/{rep['name']} — the worker builds each kit / picture from them")
            elif rep["filed"]:
                print(f"not queued (--no-submit): submit.bat {rep['batch_file']}")
            return 0 if not (rep["missing"] or rep["wrong_size"]) else 1
        # tool
        if not rest or rest[0] not in ("add", "list"):
            print('usage: handoff tool add ["<name>" "<version>" yes|no "<condition>" "<where checked>"] | handoff tool list'); return 2
        if rest[0] == "list":
            tools = ho.load_tools()
            if not tools:
                print("no outside tools on file — handoff_tool_add.bat records one")
            for k, r in sorted(tools.items()):
                print(f"  {k:40s} commercial: {'yes' if r.get('commercial_ok') else 'NO'}"
                      + (f"   condition: {r['licence_condition']}" if r.get("licence_condition") else "") + f"   checked {r.get('checked')}")
            return 0
        a = rest[1:]
        if not a:
            return 0 if ho.ask_tool() else 2
        if len(a) < 3 or a[2].lower() not in ("yes", "no"):
            print('usage: handoff tool add "<name>" "<version>" yes|no ["<condition>"] ["<where checked>"]'); return 2
        key = ho.add_tool(a[0], a[1], a[2].lower() == "yes", a[3] if len(a) > 3 else "", a[4] if len(a) > 4 else "")
        print(f"recorded '{key}' in {ho.register_path()}")
        return 0
    except ho.HandoffError as e:
        print(f"✗ {e}"); return 1


def cmd_filter_forge(cfg: dict, args: list[str]) -> int:
    from .night3b import ffdriver as ff
    if not args or args[0] not in ("list", "presets", "check", "task"):
        print(__doc__); return 2
    sub, rest = args[0], args[1:]
    if sub == "check":
        for line in ff.doctor_lines(cfg):
            print(line)
        return 0
    if sub == "list":
        rows = ff.list_filters(cfg)
        if not rows:
            print("no Filter Forge filters found — " + ff.doctor_lines(cfg)[0]); return 1
        for where, items in rows.items():
            print(f"{where}  ({len(items)} filters)")
            show = items if "--all" in rest else items[:400]
            for r in show:
                print(f"  {r['file']:28s} {r['kind']:8s} {r['presets']:3d} presets  seamless: {r['seamless_presets'] or '-'}  {r['name']}")
        print("(read-only: the forge stores the path of a filter, never a copy of it)")
        return 0
    if sub == "presets":
        if not rest:
            print("usage: filter-forge presets <filter path or Library_NNN-N>"); return 2
        try:
            path = ff.find_filter(cfg, rest[0])
            info = ff.read_filter(path)
        except (FileNotFoundError, ValueError) as e:
            print(f"✗ {e}"); return 1
        print(f"{info['name']} — {path}  ({info['kind']}, library id {info['library_id'] or '-'})")
        for p in info["presets"]:
            print(f"  preset {p['index']:2d}: seamless {'yes' if p['seamless'] else 'no '}  size ×{p['size_factor']:.3g}  "
                  f"variation {p['variation']}  channel: {'final' if p['map_type'] == 0 else 'map type ' + str(p['map_type'])}"
                  + (f"  — {p['note']}" if p.get("note") else ""))
        print("Presets you add in Filter Forge are numbered after these. A normal / height / … map is a preset saved with that "
              "channel chosen (Render Channels menu).")
        return 0
    if sub == "task":
        if not rest:
            print("usage: filter-forge task <job.json>"); return 2
        job = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
        out = Path(_opt(rest, "--out") or ".")
        try:
            print(ff.task_xml(job, out, ff.root_for(job))[0])
        except (ValueError, FileNotFoundError) as e:
            print(f"✗ {e}"); return 1
        return 0
    return 2


COMMANDS = {"handoff": cmd_handoff, "filter-forge": cmd_filter_forge}
