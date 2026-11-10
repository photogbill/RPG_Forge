"""Night 4 commands (kept apart from cli.py; registered in cli.COMMANDS).

  intake <sheet | folder> <character> [variant] [--tool "<name version>"] [--queue] [--mapping f] [--game g]
                                    a drawn character sheet → the game's sprite contract (sprite_intake.bat)
  characters list | show <id> | check [<id>] | stubs | set <id> [variant] [--parts moods,battle,turnaround]
                                    the character registry (characters.bat)
  submit …                          as before; jobs with "character" inherit the registry (Night 4 shim)
  review --character <id>           every variant and mood of one face on one compact sheet
  review --town <id> | --atlas      one town's paintings on one sheet | one painting per town side by side
  produce plan | queue | status     wanted → planned queue (produce.bat)
  deliver [--dry] [--only <name>] | deliver undo <name> | deliver ledger      approved pictures → the game
  feedback-in [art_feedback.json]   the game's F9 notes → redo drafts (feedback_in.bat)
  models-report                     the model shelf: kept / dropped / safe to delete (models_report.bat)
  housekeeping                      out/ — what could be archived (report only)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from . import config as cfgmod
from .cli_night3 import _opt, _positional

IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:  # noqa: BLE001
        return False


def _safe(s: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in s)[:60]


# ------------------------------------------------------------------ F1 intake
def _intake_tool(cfg: dict, game: str, given: str | None) -> str | None:
    """The program that made the sheets: --tool, else the last one used for this game, else ask once. A tool with
    no licence on file is asked about there and then (the G13 register) — nothing in the code names a product."""
    from . import handoff as ho
    memo = cfgmod.path_of(cfg, "games") / game / "intake" / "tool.json"
    tool = given
    if not tool and memo.exists():
        try:
            tool = json.loads(memo.read_text(encoding="utf-8")).get("last")
        except ValueError:
            tool = None
        if tool:
            print(f"(program that made the sheets: {tool} — as last time; --tool \"<name version>\" to change)")
    if not tool and _tty():
        tool = input("Which program made these sheets? Name and version, e.g. as its About box shows "
                     "(Enter to skip — approve will ask later): ").strip() or None
    if not tool:
        return None
    known = ho.load_tools()
    if tool not in known:
        name, _, version = tool.rpartition(" ")
        if not name:
            name, version = tool, ""
        if _tty():
            print(f"'{tool}' has no licence line on file yet — one question at a time:")
            key = ho.ask_tool(name=name, version=version)
            tool = key or tool
        else:
            print(f"note: '{tool}' has no licence line on file — run handoff_tool_add.bat \"{name}\" \"{version}\" yes|no "
                  "\"<condition>\" \"<where checked>\" (approve refuses the sheets until it is recorded)")
    memo.parent.mkdir(parents=True, exist_ok=True)
    memo.write_text(json.dumps({"last": tool}, indent=1), encoding="utf-8")
    return tool


def ask_mapping(mp: Path, character: str, asym: bool | None, ask=input, out=print) -> bool:
    """Fix the guess by answering questions instead of editing the file. Returns True if anything changed."""
    from .night4.intake import FACINGS
    m = json.loads(mp.read_text(encoding="utf-8"))
    out(f"\nThe forge guessed: {m.get('guess')}  [confidence: {m.get('confidence')}]  (numbers are on numbers.png)")
    a = ask("Is that right? Enter = yes, n = let me fix it: ").strip().lower()
    changed = False
    if a in ("n", "no"):
        out("For each figure type its facing (S SW W NW N NE E SE), optionally a frame number (e.g. 'W 2'), "
            "'-' to leave it out, or just Enter to keep what it says.")
        for e in m["figures"]:
            now = "skip" if e.get("skip") else (f"{e.get('facing')} {e.get('frame', 0)}" if e.get("facing") else "?")
            while True:
                r = ask(f"  figure {e['n']} (now {now}): ").strip().upper()
                if not r:
                    break
                if r == "-":
                    e.update(skip=True); changed = True; break
                parts = r.split()
                if parts[0] in FACINGS and (len(parts) == 1 or parts[1].isdigit()):
                    e.update(facing=parts[0], frame=int(parts[1]) if len(parts) > 1 else 0, skip=False); changed = True; break
                out(f"    '{r}' — use one of {' '.join(FACINGS)}, optionally a number, or '-'")
    have = {e.get("facing") for e in m["figures"] if e.get("facing") and not e.get("skip")}
    missing = [f for f in FACINGS if f not in have]
    opp = {"W": "E", "E": "W", "NW": "NE", "NE": "NW", "SW": "SE", "SE": "SW"}
    can = [f"{opp[f]}→{f}" for f in missing if f in opp and opp[f] in have]
    if can and not m.get("mirror"):
        warn = " — CAREFUL: the registry says this character is asymmetric (a holster on one hip ends up on the wrong side)" if asym else ""
        r = ask(f"Missing {', '.join(missing)}. Fill {', '.join(can)} by flipping{warn}? y / Enter = no: ").strip().lower()
        if r in ("y", "yes"):
            m["mirror"] = can; changed = True
    if changed or a in ("", "y", "yes"):
        m["checked_by_person"] = True
        mp.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return changed


def cmd_intake(cfg: dict, args: list[str]) -> int:
    pos = _positional(args, ("--tool", "--mapping", "--game", "--priority"))
    if len(pos) < 2:
        print(__doc__.split("\n\n")[1].split("\n")[0]); print("usage: intake <sheet | folder> <character> [variant] "
              "[--tool \"<name version>\"] [--queue]"); return 2
    target, character = Path(pos[0]), pos[1]
    variant = pos[2] if len(pos) > 2 else None
    game = _opt(args, "--game", "turing_accords")
    if not target.exists():
        print(f"not found: {target}"); return 1
    sheets = sorted(p for p in target.iterdir() if p.suffix.lower() in IMG_EXTS) if target.is_dir() else [target]
    if not sheets:
        print(f"no pictures in {target}"); return 1
    if _opt(args, "--mapping") and len(sheets) > 1:
        print("--mapping names ONE sheet's mapping file — give one sheet with it"); return 2
    tool = _intake_tool(cfg, game, _opt(args, "--tool"))
    from .night4.inline import run_now
    from .queue import Queue
    rc = 0
    for s in sheets:
        job = {"type": "sprite_intake", "input": str(s.resolve()), "character": character, "game": game,
               "batch": f"intake/{character}" + (f"__{variant}" if variant else ""),
               "name": _safe(f"intake_{character}_{variant or ''}_{s.stem}".replace("__", "_"))}
        if variant:
            job["variant"] = variant
        if tool:
            job["tool"] = tool
        if _opt(args, "--mapping"):
            job["mapping"] = _opt(args, "--mapping")
        if "--queue" in args:
            job["priority"] = int(_opt(args, "--priority", "10"))
            jid = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out")).submit(job)
            print(f"{s.name}: queued {jid} (the worker runs it next)")
            continue
        jid, res, err = run_now(cfg, job)
        out = cfgmod.path_of(cfg, "out") / jid
        if err:
            print(f"✗ {s.name}: {err}   (jobs/failed/{jid}.json)"); rc = 1; continue
        if _tty() and "--no-ask" not in args and (res["first_run"] or "--ask" in args):
            print(f"\nLook at {out / 'numbers.png'} (and {out / 'sheet.png'}).")
            asym = None
            try:
                from .night4 import characters as _chm
                asym = _chm.is_asymmetric(_chm.load(cfg, game, character), variant)
            except Exception:  # noqa: BLE001
                pass
            if ask_mapping(Path(res["mapping"]), character, asym):
                print("…running it again with your answers")
                jid, res, err = run_now(cfg, job)
                out = cfgmod.path_of(cfg, "out") / jid
                if err:
                    print(f"✗ {s.name}: {err}"); rc = 1; continue
        print(f"\n✓ {s.name} → {out}")
        print(f"  found {res['found']} figure(s); mapping: {res['guess']} [confidence: {res['confidence']}]")
        print(f"  {'FIRST RUN — check the guess:' if res['first_run'] else 'used the mapping:'} {res['mapping']}")
        print(f"  numbered picture: {out / 'numbers.png'}   packed: {out / 'sheet.png'}"
              + (f"   frames: {out / 'anim.png'}" if (out / 'anim.png').exists() else ""))
        if res["missing"]:
            print(f"  missing facings: {', '.join(res['missing'])}")
        for w in res["warnings"]:
            print(f"  ⚠ {w}")
        print(f"  edge report: {out / 'edges.md'}")
    if "--queue" not in args:
        print("\nNext: if something is still wrong, run the same line again with --ask (or edit the mapping file). "
              "When the packed sheet is right: approve.bat <job id> --as placeholder/hero_<name>")
    return rc


# ------------------------------------------------------------------ F2 characters
def cmd_characters(cfg: dict, args: list[str]) -> int:
    from .night4 import characters as chm
    game = _opt(args, "--game", "turing_accords")
    pos = _positional(args, ("--game", "--parts"))
    sub = pos[0] if pos else "list"
    try:
        if sub == "list":
            rows = chm.summary(cfg, game)
            if not rows:
                print(f"no characters yet in games/{game}/characters/ — characters.bat stubs makes one per cast member"); return 0
            for r in rows:
                if r.get("error"):
                    print(f"  {r['id']:16s} ERROR {r['error']}"); continue
                w = ", ".join(f"{k}={v}" for k, v in r["wanted"].items() if isinstance(v, str))
                print(f"  {r['id']:16s} {r['variant']:10s} {'stub ' if r['stub'] else '     '}seed={r['seed']}  "
                      f"{r['checkpoint'] or '-'}  {'ASYMMETRIC ' if r['asymmetric'] else ''}{w}")
            return 0
        if sub == "show":
            ch = chm.load(cfg, game, pos[1])
            print(json.dumps({k: v for k, v in ch.items() if not k.startswith("_") or k in ("_comment",)}, indent=1, ensure_ascii=False))
            return 0
        if sub == "check":
            probs = chm.check(cfg, game, pos[1] if len(pos) > 1 else None)
            for p in probs:
                print(f"  - {p}")
            print(f"{len(probs)} note(s)" if probs else "all clear")
            return 0
        if sub == "stubs":
            made = chm.stubs(cfg, game)
            print(f"made {len(made)} stub(s): {', '.join(made) or '(none — every cast member has a file)'}")
            return 0
        if sub == "set":
            if len(pos) < 2:
                print("usage: characters set <id> [variant] [--parts moods,battle,turnaround]"); return 2
            job = {"type": "character_set", "character": pos[1], "game": game}
            if len(pos) > 2:
                job["variant"] = pos[2]
            if _opt(args, "--parts"):
                job["parts"] = _opt(args, "--parts").split(",")
            p = cfgmod.path_of(cfg, "games") / game / "batches" / f"charset_{pos[1]}_{pos[2] if len(pos) > 2 else 'default'}.json"
            p.write_text(json.dumps({"batch": p.stem, "jobs": [job]}, indent=1), encoding="utf-8", newline="\n")
            from .night4 import charset
            try:
                charset.expand_set(cfg, job)
                print(f"wrote {p} — ready: submit.bat {p}")
            except Exception as e:  # noqa: BLE001
                print(f"wrote {p}, but it will not submit yet: {e}")
            return 0
    except (chm.CharacterError, IndexError) as e:
        print(e if str(e) else "usage: characters list | show <id> | check [<id>] | stubs | set <id> [variant]"); return 1
    print("usage: characters list | show <id> | check [<id>] | stubs | set <id> [variant]"); return 2


# ------------------------------------------------------------------ the submit shim (F2 inheritance)
def cmd_submit(cfg: dict, args: list[str]) -> int:
    """Night 4 shim: files whose jobs name a `character` are resolved against the registry (and character_set jobs
    expanded) into _incoming/, then submitted by the usual submit. WIRE_NIGHT_4.md moves this into submit."""
    from . import cli as _cli
    from .night4 import characters as chm, charset
    new_args = []
    for a in args:
        if a.startswith("--"):
            new_args.append(a); continue
        p = Path(a)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            new_args.append(a); continue
        jobs = data.get("jobs") if isinstance(data, dict) and "jobs" in data else [data]
        defaults = data.get("defaults", {}) if isinstance(data, dict) and "jobs" in data else {}
        if not any(isinstance(j, dict) and ({**defaults, **j}.get("character")) for j in jobs or []):
            new_args.append(a); continue
        if isinstance(data, dict) and data.get("_draft"):
            new_args.append(a); continue                 # the usual submit refuses drafts with its own message
        try:
            g = (data.get("game") if isinstance(data, dict) else None) or defaults.get("game")
            out_jobs = []
            for j in jobs:
                full = {**defaults, **j}
                if full.get("type") == "character_set":
                    out_jobs.append(charset.expand_set(cfg, full, g))
                elif full.get("character"):
                    out_jobs.append(chm.resolve(cfg, full, g))
                else:
                    out_jobs.append(full)
        except Exception as e:  # noqa: BLE001
            print(f"{p.name}: refused — {e}"); return 2
        resolved = {**data, "defaults": {}, "jobs": out_jobs} if isinstance(data, dict) and "jobs" in data else out_jobs[0]
        inc = Path(cfg.get("incoming_dir") or (cfgmod.ROOT / "_incoming")) / f"resolved_{p.stem}.json"
        inc.parent.mkdir(parents=True, exist_ok=True)
        inc.write_text(json.dumps(resolved, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        print(f"{p.name}: {sum(1 for j in out_jobs if j.get('character'))} character job(s) resolved from the registry")
        new_args.append(str(inc))
    return _cli.cmd_submit(cfg, new_args)


# ------------------------------------------------------------------ review wrapper
def cmd_review(cfg: dict, args: list[str]) -> int:
    from . import cli as _cli
    if "--character" in args:
        from .night4 import reviews
        cid = _opt(args, "--character")
        try:
            paths, n = reviews.character_sheet(cfg, cid)
        except ValueError as e:
            print(e); return 1
        print(f"{n} picture(s) of {cid}:"); [print(f"  {p}") for p in paths]
        return 0
    if "--town" in args or "--atlas" in args:
        from .night4 import reviews
        try:
            paths, n = reviews.town_sheet(cfg, _opt(args, "--town")) if "--town" in args else reviews.atlas_sheet(cfg)
        except ValueError as e:
            print(e); return 1
        print(f"{n} painting(s):"); [print(f"  {p}") for p in paths]
        return 0
    return _cli.cmd_review(cfg, args)


COMMANDS = {"intake": cmd_intake, "characters": cmd_characters, "submit": cmd_submit, "review": cmd_review}


# ------------------------------------------------------------------ F3 production
def cmd_produce(cfg: dict, args: list[str]) -> int:
    from .night4 import produce
    game = _opt(args, "--game", "turing_accords")
    pos = _positional(args, ("--game", "--lanes", "--kinds"))
    sub = pos[0] if pos else "status"
    if sub == "plan":
        p = produce.plan(cfg, game, refresh="--no-refresh" not in args, generate_sprites="--generate-sprites" in args)
        e = p["_estimate"]
        for n in p["_notes"]:
            print(f"> {n}")
        print(f"\nplanned {e['jobs']} job(s): about {e['gpu_hours']} GPU hours and {e['disk_gb']} GB (free: {e['free_gb']} GB)")
        lanes: dict[str, int] = {}
        for j in p["jobs"]:
            lanes[j["batch"]] = lanes.get(j["batch"], 0) + 1
        for b, n in lanes.items():
            print(f"  {b:18s} {n}")
        print(f"rendered already, waiting for your approve: {len(p['_rendered'])} · waiting on something: "
              f"{len(p['_waiting'])} · yours by hand: {len(p['_by_hand'])}")
        if p["_new_blocks"]:
            print(f"added {len(p['_new_blocks'])} placeholder block(s) to prompts/night4.json for Fable to write")
        print(f"the plan: {p['_file']}  (and .md beside it)\nnext: produce.bat queue   (it refuses until the blocks are written)")
        return 0
    if sub == "queue":
        lanes = _opt(args, "--lanes"); kinds = _opt(args, "--kinds")
        r = produce.queue(cfg, game, lanes.split(",") if lanes else None, kinds.split(",") if kinds else None,
                          dry="--dry" in args, force_disk="--force-disk" in args)
        if r.get("refused"):
            print(f"REFUSED — nothing queued. {r.get('jobs', 0)} job(s) selected; what must be written first:")
            for why, who in sorted(r["refused"].items(), key=lambda kv: -len(kv[1])):
                print(f"  - {why}" + (f"   ({len(who)} job(s): {', '.join(who[:4])}{' …' if len(who) > 4 else ''})" if who else ""))
            print("Fill the blocks in games/<game>/prompts/*.json (Fable's), or queue part of the plan: --lanes first,story "
                  "or --kinds scene_kit,prop")
            return 1
        if r.get("dry"):
            print(f"would queue {r['would_queue']} job(s) — {r['estimate']['gpu_hours']} GPU h, {r['estimate']['disk_gb']} GB"); return 0
        print(r.get("note") or f"queued {r['queued']} job(s) — produce.bat status shows progress")
        return r.get("rc", 0) or 0
    if sub == "status":
        st = produce.status(cfg)
        c = st["counts"]
        print(f"production: done {c.get('done', 0)} · running {c.get('running', 0)} · left {c.get('pending', 0) + c.get('paused', 0)}"
              f" (paused {c.get('paused', 0)}) · failed {c.get('failed', 0)} · ETA {st['eta_hours']} h · free {st['free_gb']} GB")
        for cause_, n in sorted(st["failed_by_cause"].items(), key=lambda kv: -kv[1]):
            print(f"  ✗ {n} × {cause_}")
        if (st.get("guard") or {}).get("message"):
            print(f"  ⚠ {st['guard']['message']}")
        return 0
    if sub == "watch":
        from .night4 import guard
        print("watching: disk guard every 5 min, the 24-hour report while a queue runs. Ctrl+C stops (nothing is lost).")
        try:
            guard.watch(cfg, float(_opt(args, "--every", "300")))
        except KeyboardInterrupt:
            print("stopped")
        return 0
    print("usage: produce plan [--no-refresh] [--generate-sprites] | queue [--lanes a,b] [--kinds t1,t2] [--dry] | status | watch")
    return 2


def cmd_deliver(cfg: dict, args: list[str]) -> int:
    from .night4 import deliver as dl
    game = _opt(args, "--game", "turing_accords")
    pos = _positional(args, ("--game", "--only", "--as", "--pick", "--file"))
    try:
        if pos and pos[0] == "hold":
            if len(pos) < 2 or not _opt(args, "--as"):
                print("usage: deliver hold <job id> --as <wanted name> [--pick N | --file f]"); return 2
            h = dl.hold(cfg, pos[1], _opt(args, "--as"), game, _opt(args, "--file"),
                        int(_opt(args, "--pick")) if _opt(args, "--pick") else None)
            print(f"approved (held for delivery): {_opt(args, '--as')} ← {pos[1]}  {Path(h['file']).name}"); return 0
        if pos and pos[0] == "undo":
            r = dl.undo(cfg, game, pos[1]); print(f"undone {r['wanted']}: {r['what']} (kept: {r['kept']})"); return 0
        if pos and pos[0] == "ledger":
            for e in dl.ledger(cfg, game)[-40:]:
                print(f"  {e['time']}  {e['action']:9s} {e['wanted']:40s} {e.get('job_id') or ''}")
            return 0
        if pos and pos[0] == "record":
            print(f"recorded {dl.record_listed(cfg, pos[1])} delivery(ies)"); return 0
        r = dl.run(cfg, game, dry="--dry" in args, only=_opt(args, "--only"), fit="--fit" in args)
    except Exception as e:  # noqa: BLE001
        print(f"refused: {e}"); return 1
    for m in r["moved"]:
        print(f"  {'would deliver' if r['dry'] else '✓ delivered'} {m['wanted']} ← {m['job_id']} ({m['why']})"
              + (f" — {m['fitted']}" if m.get("fitted") else ""))
    for x in r["refused"]:
        print(f"  ✗ {x['wanted']}: {x['reason']}")
    if r.get("listed"):
        print(f"the game folder is not reachable from here — run this on the PC with the game: {r['listed']}")
    if not r["moved"] and not r["refused"] and not r.get("listed"):
        print("nothing to deliver: every approval is already in the game")
    return 0


def cmd_housekeeping(cfg: dict, args: list[str]) -> int:
    from .night4 import housekeeping
    p, rep = housekeeping.report(cfg, int(_opt(args, "--days", "14")))
    print(f"could be archived: {rep['gb']} GB — bake-off {rep['bakeoff']}, failed {rep['failed']}, other {rep['other_old']} "
          f"folder(s). Nothing was moved. Report: {p}")
    return 0


COMMANDS.update({"produce": cmd_produce, "deliver": cmd_deliver, "housekeeping": cmd_housekeeping})


# ------------------------------------------------------------------ F5 verdicts back
def cmd_feedback_in(cfg: dict, args: list[str]) -> int:
    from .night4 import feedback
    pos = _positional(args, ("--game",))
    try:
        r = feedback.take_in(cfg, pos[0] if pos else None, _opt(args, "--game", "turing_accords"))
    except FileNotFoundError as e:
        print(e); return 1
    for f in r["filed"]:
        print(f"  ✎ {f['wanted']}: \"{f['note']}\" → draft(s) {', '.join(Path(d).name for d in f['drafts'])}")
    for b in r["bumped"]:
        print(f"  ↑ {b['wanted']}: \"{b['note']}\" — a stand-in; painted sooner next produce plan")
    print(f"filed {len(r['filed'])}, bumped {len(r['bumped'])}, already seen {r['skipped']}. Notes: {r['md']}\n"
          "The drafts are NOT queued — the dashboard's Called out section approves, dismisses or hands them to you.")
    return 0


COMMANDS.update({"feedback-in": cmd_feedback_in})


# ------------------------------------------------------------------ F8 model shelf
def cmd_models_report(cfg: dict, args: list[str]) -> int:
    from .night4 import models_shelf
    p, r = models_shelf.build(cfg, _opt(args, "--game", "turing_accords"), scan="--no-scan" not in args)
    print(f"{r['files']} model file(s). Safe to delete: {r['safe_gb']} GB — {r['verdict_gb']} GB dropped by a verdict, "
          f"{r['cant_run_gb']} GB that nothing here can run today (your call). Nothing was deleted.\nReport: {p}")
    return 0


COMMANDS.update({"models-report": cmd_models_report})
