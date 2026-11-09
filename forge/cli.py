"""Command line: python -m forge <command>

  submit <job.json | batch.json> [...] [--skip-done]   validate and queue jobs (a batch file holds many);
                                         --skip-done leaves out jobs of the same batch+name already queued or done
  eta                                    what is queued and how long it should take
  ui [--port 8765]                       the dashboard in your browser (http://127.0.0.1:8765) — ui.bat
  worker [--gpu] [--once]                run jobs from the queue (GPU worker needs ComfyUI up)
  status                                 queue counts
  requeue                                move crashed running/ jobs back to pending/
  retry [batch-prefix]                   move failed jobs back to pending (e.g. retry bakeoff/sdxl_v1)
  pause [batch-prefix] / resume [batch-prefix]   park pending jobs in jobs/paused/ and bring them back
  (a job's "priority": 10 runs before priority 0; same priority = oldest first)
  comfy-up                               exit 0 if ComfyUI answers at its url (used by run_worker.bat)
  validate <job.json>                    check a job file without queueing it
  validate-workflow <name>               check a ComfyUI workflow template's placeholders
  palette pull <lospec-slug>             download a palette from lospec.com into palettes/
  palette list                           palettes on disk
  palette swatch <name> [out.png]        render a palette as a swatch image
  models list                            the model registry with licences
  models pull <name>                     download a registered model into models/ (Hugging Face)
  models scan                            inspect every checkpoint/LoRA in the model folders → models/INVENTORY.md
  comfy-paths                            write engines/ComfyUI/extra_model_paths.yaml from forge.json model_dirs
  bakeoff plan|submit|report|rate …      every checkpoint × LoRA × test prompt, then one report (see forge/bakeoff.py)
  models licence <file> "<licence>" yes|no [note]   record a licence you checked yourself (models/licences.json)
  wanted [--refresh] [--kind K] [--missing] [--all]  what the game wants vs. what is approved (games/<game>/wanted.json)
  approve <job-id> --as <wanted-name> [--file F | --pick N] [--dry-run]   copy an output into the game, with provenance
  approve <job-id> --as scenes/<map> --set [--dry-run]   a scene_kit's six files as one set (all or nothing)
  licences                               the licence chain of every approved asset → out/licences_<game>.md
  review <suite-or-batch> [--by category|model|type] [--thumb N]   labelled sheets + index.html with ratings export
  rate <suite-or-batch> --import <ratings.json>                    merge the ratings the review page exported
  brief maps|sleeves|icons               write an editable batch draft from the game's data (games/<game>/batches/draft_*.json)
  docs                                   regenerate docs/JOB_TYPES.md from the schema
  doctor                                 check Python, Pillow, numpy, ComfyUI, GPU, graph nodes, queued models
  (most commands take --game <name>; default turing_accords)
"""
from __future__ import annotations
import json
import shutil, subprocess, sys
from pathlib import Path

from . import config as cfgmod, schema, log as logmod
from .queue import Queue, run_worker


def _queue(cfg: dict) -> Queue:
    cfgmod.ensure_dirs(cfg)
    return Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))


def cmd_submit(cfg: dict, args: list[str]) -> int:
    if not args:
        print("usage: submit <job.json | batch.json> [...] [--skip-done]"); return 2
    q = _queue(cfg)
    total = 0
    for a in [x for x in args if not x.startswith("--")]:
        p = Path(a)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("_draft"):
            print(f"{p.name}: is a DRAFT (made by `brief`) — edit the prompts, delete the \"_draft\" line, then submit"); return 2
        if isinstance(data, dict) and "jobs" in data:
            note = ""
            if "--skip-done" in args:
                from . import dedupe
                defaults = data.get("defaults", {})
                full = [{**defaults, **j, **({"batch": j.get("batch") or data["batch"]} if data.get("batch") else {})} for j in data["jobs"]]
                keep, skipped = dedupe.filter_new(cfg, full)
                data = {**data, "jobs": keep, "defaults": {}}
                note = ("  " + dedupe.describe(skipped)) if skipped else ""
            ids = q.submit_batch(data)
            print(f"{p.name}: queued {len(ids)} jobs" + (f" (batch '{data.get('batch')}')" if data.get("batch") else "") + note)
            total += len(ids)
        else:
            jid = q.submit(data)
            print(f"{p.name}: queued {jid}")
            total += 1
    print(f"queued {total} job(s); status: {q.status()}")
    return 0


def cmd_worker(cfg: dict, args: list[str]) -> int:
    gpu = "--gpu" in args or bool(cfg["worker"].get("gpu"))
    once = "--once" in args
    from .jobs import get_handlers
    from .jobs.common import Context
    ctx = Context(cfg=cfg, palettes_dir=cfgmod.path_of(cfg, "palettes"), root=cfgmod.ROOT)
    handlers = (lambda: get_handlers(reload=True))   # pick up code fixes without restarting
    if gpu:
        from .engines.comfy import ComfyClient
        ctx.comfy = ComfyClient(cfg["comfy"]["url"], int(cfg["comfy"]["timeout_sec"]), float(cfg["comfy"]["poll_sec"]))
        print(f"GPU worker — ComfyUI at {ctx.comfy.url}: {'up' if ctx.comfy.is_up() else 'NOT reachable (GPU jobs will fail until it is)'}")
    else:
        print("CPU worker — GPU job types will be left in the queue for a GPU worker")
    q = _queue(cfg)
    n = run_worker(q, handlers, ctx, gpu=gpu, once=once, poll_sec=float(cfg["worker"]["poll_sec"]))
    print(f"ran {n} job(s); status: {q.status()}")
    return 0


def cmd_status(cfg: dict, args: list[str]) -> int:
    q = _queue(cfg)
    print(json.dumps(q.status(), indent=1))
    for p in q.pending()[:20]:
        with open(p, "r", encoding="utf-8") as f:
            j = json.load(f)
        print(f"  pending  {j.get('id')}  {j.get('type')}  {j.get('name', '')}")
    return 0


def cmd_requeue(cfg: dict, args: list[str]) -> int:
    print(f"requeued {_queue(cfg).requeue_running()} job(s)")
    return 0


def cmd_retry(cfg: dict, args: list[str]) -> int:
    prefix = args[0] if args else None
    n = _queue(cfg).retry_failed(prefix)
    print(f"moved {n} failed job(s) back to pending" + (f" (batch prefix '{prefix}')" if prefix else ""))
    return 0


def cmd_pause(cfg: dict, args: list[str]) -> int:
    n = _queue(cfg).pause(args[0] if args else None)
    print(f"paused {n} job(s) → jobs/paused/ (resume.bat brings them back)")
    return 0


def cmd_resume(cfg: dict, args: list[str]) -> int:
    n = _queue(cfg).resume(args[0] if args else None)
    print(f"resumed {n} job(s)")
    return 0


def cmd_comfy_up(cfg: dict, args: list[str]) -> int:
    from .engines.comfy import ComfyClient
    up = ComfyClient(cfg["comfy"]["url"]).is_up()
    print(("ComfyUI is up at " if up else "ComfyUI is not reachable at ") + cfg["comfy"]["url"])
    return 0 if up else 1


def cmd_validate(cfg: dict, args: list[str]) -> int:
    rc = 0
    for a in args:
        with open(a, "r", encoding="utf-8") as f:
            data = json.load(f)
        jobs = data["jobs"] if isinstance(data, dict) and "jobs" in data else [data]
        defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
        for i, j in enumerate(jobs):
            job = dict(defaults); job.update(j)
            probs = schema.validate(job)
            tag = f"{a}[{i}] {job.get('name', job.get('type'))}"
            if probs:
                rc = 1
                print(f"✗ {tag}: " + "; ".join(probs))
            else:
                print(f"✓ {tag}: ok ({job['type']}, {schema.JOB_TYPES[job['type']]['needs']})")
    return rc


def cmd_validate_workflow(cfg: dict, args: list[str]) -> int:
    from .engines import comfy
    for name in args or comfy.list_workflows():
        wf = comfy.load_workflow(name)
        text = json.dumps(wf)
        needed = ["prompt", "negative", "seed", "width", "height", "steps", "cfg", "checkpoint"]
        missing = [k for k in needed if "{{" + k not in text]
        print(f"{name}: " + ("ok" if not missing else "missing placeholders: " + ", ".join(missing)))
    return 0


def cmd_palette(cfg: dict, args: list[str]) -> int:
    from .ops import palette as pal
    pdir = cfgmod.path_of(cfg, "palettes")
    if not args or args[0] == "list":
        for p in sorted(pdir.glob("*")):
            if p.suffix in (".hex", ".gpl", ".json"):
                print(f"  {p.stem:24s} {len(pal.load_palette(p))} colours")
        return 0
    if args[0] == "pull":
        for slug in args[1:]:
            out = pal.pull_lospec(slug, pdir)
            print(f"pulled {slug} → {out} ({len(pal.load_palette(out))} colours)")
        return 0
    if args[0] == "swatch":
        from PIL import Image, ImageDraw
        name = args[1]
        rgb = pal.load_palette(pal.find_palette(name, pdir))
        cell, cols = 24, 16
        rows = (len(rgb) + cols - 1) // cols
        im = Image.new("RGB", (cols * cell, rows * cell), (0, 0, 0))
        dr = ImageDraw.Draw(im)
        for i, c in enumerate(rgb.tolist()):
            r, cc = divmod(i, cols)
            dr.rectangle([cc * cell, r * cell, cc * cell + cell - 1, r * cell + cell - 1], fill=tuple(c))
        out = Path(args[2]) if len(args) > 2 else pdir / f"{name}_swatch.png"
        im.save(out)
        print(f"wrote {out}")
        return 0
    print(__doc__); return 2


def _licence_ask(cfg: dict, ask=input) -> int:
    """N9a: licence.bat with no arguments — the questions one at a time, the file offered from the list of models
    whose licence is unknown."""
    from . import manifest, model_report
    try:
        _, groups = model_report.report(cfg)
        unknown = sorted(f for f, *_ in groups["licence unknown"])
    except FileNotFoundError:
        unknown = []
    print("Record a licence you have checked yourself (for example on the model's Civitai or Hugging Face page).")
    print("The forge never guesses a licence. Press Enter on an empty line to stop.\n")
    if unknown:
        print("Models with no licence on record:")
        for i, f in enumerate(unknown, 1):
            print(f"  {i:2d}. {f}")
    ans = ask("\n1) Which model? (its number above, or the file name): ").strip().strip('"')
    if not ans:
        print("Nothing recorded."); return 0
    if ans.isdigit() and unknown and 1 <= int(ans) <= len(unknown):
        file = unknown[int(ans) - 1]
    else:
        file = ans
    name = ask(f"2) Licence name as the page shows it (e.g. CreativeML Open RAIL++-M) for {file}: ").strip().strip('"')
    if not name or "<" in name or ">" in name:
        print("No licence name — nothing recorded."); return 2
    yn = ""
    while yn not in ("yes", "no"):
        yn = ask("3) Does it allow commercial use of the pictures it makes? (yes/no): ").strip().lower()
        yn = {"y": "yes", "n": "no"}.get(yn, yn)
        if not yn:
            print("Nothing recorded."); return 0
    where = ask("4) Where did you check? (e.g. 'Civitai page v8, permissions icons'): ").strip()
    p = manifest.record_licence(cfg, file, name, yn == "yes", where)
    print(f"\nrecorded {Path(file).name}: {name} — commercial OK: {yn} → {p}")
    return 0


def cmd_models(cfg: dict, args: list[str]) -> int:
    reg_path = cfgmod.ROOT / "models" / "models.json"
    with open(reg_path, "r", encoding="utf-8") as f:
        reg = json.load(f)
    if not args or args[0] == "list":
        for name, m in reg["models"].items():
            ok = "commercial OK" if m.get("commercial_ok") else "NON-COMMERCIAL — experiments only"
            print(f"  {name:28s} {m.get('license', '?'):36s} {ok}")
            print(f"  {'':28s} {m.get('repo', '')}  →  models/{m.get('dest', '')}")
        return 0
    if args[0] == "scan":
        from . import bakeoff
        recs = bakeoff.inventory(cfg, refresh=True)
        from .ops import safetensors_meta as sm
        print(sm.render_markdown(recs))
        print(f"{len(recs)} files → models/inventory.json + models/INVENTORY.md")
        return 0
    if args[0] == "unusable":
        from . import model_report
        try:
            text, groups = model_report.report(cfg)
        except FileNotFoundError as e:
            print(e); return 1
        out = cfgmod.path_of(cfg, "out") / "unusable_models.md"
        out.write_text(text, encoding="utf-8", newline="\n")
        print(text)
        print(f"→ {out}   (report only — nothing was deleted)")
        return 0
    if args[0] == "licence" and (len(args) == 1 or args[1] == "--ask"):
        return _licence_ask(cfg)
    if args[0] == "licence":
        if len(args) < 4 or args[3].lower() not in ("yes", "no"):
            print('usage: models licence <file> "<licence name>" yes|no [where you checked]'); return 2
        if not args[2].strip() or "<" in args[2] or ">" in args[2]:
            print(f'"{args[2]}" is the placeholder from the instructions, not a licence name. Type the name shown on the '
                  'model\'s page, e.g. "CreativeML Open RAIL++-M". Nothing was recorded.'); return 2
        from . import manifest
        p = manifest.record_licence(cfg, args[1], args[2], args[3].lower() == "yes", " ".join(args[4:]))
        print(f"recorded {Path(args[1]).name}: {args[2]} — commercial OK: {args[3].lower()} → {p}")
        return 0
    if args[0] == "pull":
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            print("pip install huggingface_hub (install.bat does)"); return 1
        for name in args[1:]:
            if name not in reg["models"]:
                print(f"unknown model '{name}' — models list shows the names"); return 2
            m = reg["models"][name]
            dest = cfgmod.path_of(cfg, "models") / m.get("dest", "")
            dest.mkdir(parents=True, exist_ok=True)
            if not m.get("commercial_ok"):
                print(f"NOTE: {name} is {m.get('license')} — fine for experiments, not for shipped assets.")
            save_as = m.get("save_as") or {}
            for idx, fname in enumerate(m["files"]):
                target = dest / save_as.get(Path(fname).name, Path(fname).name)
                if target.exists() and target.stat().st_size > 1_000_000:
                    print(f"  have {target.name} already ({target.stat().st_size / 1e9:.2f} GB) — skipping")
                    continue
                print(f"  downloading {m['repo']}/{fname} → {dest}")
                try:
                    got = Path(hf_hub_download(repo_id=m["repo"], filename=fname, local_dir=str(dest)))
                except Exception as e:  # noqa: BLE001 — fall back to the registered direct URL
                    urls = m.get("urls") or []
                    if idx >= len(urls):
                        raise
                    print(f"  Hugging Face failed ({type(e).__name__}); trying {urls[idx]}")
                    import urllib.request
                    tmp = target.with_suffix(target.suffix + ".part")
                    urllib.request.urlretrieve(urls[idx], tmp)
                    tmp.replace(target)
                    got = target
                if m.get("sha256") and len(m["files"]) == 1:
                    import hashlib
                    h = hashlib.sha256(got.read_bytes()).hexdigest()
                    if h != m["sha256"]:
                        print(f"  ✗ checksum mismatch for {got.name} — delete it and pull again"); return 1
                    print("  ✓ checksum matches")
                if got.name != target.name and got.resolve().parent == dest.resolve():
                    shutil.move(str(got), str(target))
                    got = target
                # repackaged repos keep files under split_files/<kind>/ — ComfyUI wants them flat in the kind folder
                if got.resolve().parent != dest.resolve():
                    shutil.move(str(got), str(target))
                    try:
                        for parent in [got.parent, got.parent.parent]:
                            if parent.resolve() != dest.resolve() and parent.exists() and not any(parent.iterdir()):
                                parent.rmdir()
                    except OSError:
                        pass
                    print(f"  → {target}")
            print(f"pulled {name}")
        return 0
    print(__doc__); return 2


def cmd_docs(cfg: dict, args: list[str]) -> int:
    out = cfgmod.ROOT / "docs" / "JOB_TYPES.md"
    out.write_text(schema.render_docs(), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


def cmd_doctor(cfg: dict, args: list[str]) -> int:
    print(f"Python {sys.version.split()[0]} at {sys.executable}")
    print(f"repo   {cfgmod.ROOT}")
    for mod in ("PIL", "numpy", "huggingface_hub"):
        try:
            m = __import__(mod)
            print(f"✓ {mod} {getattr(m, '__version__', '')}")
        except ImportError:
            print(f"✗ {mod} missing (run install.bat)")
    try:
        import torch  # noqa — only present if the ComfyUI env is shared; not required here
        print(f"✓ torch {torch.__version__} cuda={torch.cuda.is_available()}")
    except Exception:
        print("· torch not in this environment (fine — ComfyUI has its own)")
    nvsmi = shutil.which("nvidia-smi")
    if nvsmi:
        try:
            out = subprocess.run([nvsmi, "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
            print("✓ GPU " + out.stdout.strip())
        except Exception as e:
            print(f"· nvidia-smi failed: {e}")
    else:
        print("· nvidia-smi not found (no NVIDIA GPU on this machine, or drivers missing)")
    from .engines.comfy import ComfyClient
    c = ComfyClient(cfg["comfy"]["url"])
    print(("✓ ComfyUI reachable at " if c.is_up() else "· ComfyUI not running at ") + c.url)
    comfy_root = cfgmod.path_of(cfg, "comfy_root")
    print(("✓ " if comfy_root.exists() else "· ") + f"ComfyUI folder {comfy_root}" + ("" if comfy_root.exists() else " (run install_comfy.bat)"))
    q = _queue(cfg)
    print(f"queue  {q.status()}")
    from . import doctor
    for line in doctor.report(cfg, c):
        print(line)
    return 0


def _opt(args: list[str], flag: str, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def _positional(args: list[str], flags_with_values: tuple = ()) -> list[str]:
    out, skip = [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a in flags_with_values:
            skip = True
            continue
        if a.startswith("--"):
            continue
        out.append(a)
    return out


def cmd_wanted(cfg: dict, args: list[str]) -> int:
    from . import manifest
    game = _opt(args, "--game", "turing_accords")
    if "--refresh" in args:
        try:
            d = manifest.refresh_wanted(cfg, game, _opt(args, "--game-root"))
        except (FileNotFoundError, ValueError) as e:
            print(f"✗ {e}\n  (the game folder is set in games/{game}/forge.game.json → game_root)"); return 1
        print(f"exported {d['count']} wanted files from {d.get('scanned_from') or d['game_root']}")
    try:
        rows = manifest.status(cfg, game)
    except FileNotFoundError as e:
        print(e); return 1
    kind = _opt(args, "--kind")
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    elif "--all" not in args:
        hidden = sum(1 for r in rows if r.get("optional"))
        rows = [r for r in rows if not r.get("optional")]
        if hidden:
            print(f"({hidden} optional scene-set companions hidden — _n/_e/_back/_over/_depth; --all or --kind scene_slot shows them)")
    from collections import Counter
    by = Counter((r["kind"], r["state"]) for r in rows)
    kinds = sorted({k for k, _ in by})
    print(f"{'kind':14s} {'wanted':>7s} {'approved':>9s} {'stale':>6s} {'missing':>8s}")
    for k in kinds:
        print(f"{k:14s} {sum(v for (kk, _), v in by.items() if kk == k):7d} {by[(k, 'approved')]:9d} {by[(k, 'stale')]:6d} {by[(k, 'missing')]:8d}")
    tot = Counter(r["state"] for r in rows)
    print(f"{'total':14s} {len(rows):7d} {tot['approved']:9d} {tot['stale']:6d} {tot['missing']:8d}")
    show = rows if "--all" in args else [r for r in rows if r["state"] != "approved"] if "--missing" in args else []
    for r in show[:400]:
        ts = r.get("target_size")
        size = f"{ts[0]}x{ts[1]}" if ts else "?"
        print(f"  {r['state']:8s} {r['name']:48s} {size:>10s}  {r['path']}")
    if not show:
        print("(--missing lists what still needs art; --all lists everything; --kind scene filters)")
    return 0


def cmd_approve(cfg: dict, args: list[str]) -> int:
    from . import manifest
    pos = _positional(args, ("--as", "--file", "--pick", "--game"))
    name = _opt(args, "--as")
    if not pos or not name:
        print("usage: approve <job-id> --as <wanted-name> [--file F | --pick N | --set] [--dry-run] [--game G]"); return 2
    pick = _opt(args, "--pick")
    if "--set" in args:
        try:
            r = manifest.approve_set(cfg, pos[0], name, game=_opt(args, "--game"), dry_run="--dry-run" in args)
        except (manifest.ApproveError, FileNotFoundError) as e:
            print(f"✗ {e}"); return 1
        print(("DRY RUN — would copy this set of " if r.get("dry_run") else "✓ approved the set of ") + f"{len(r['rows'])} file(s) for {name}:")
        for row in r["rows"]:
            ts = row.get("target_size")
            note = "" if not ts or row["size"] == ts else f"  (target {ts[0]}x{ts[1]})"
            print(f"  {row['slot']:11s} {Path(row['file']).name:22s} {row['size'][0]}x{row['size'][1]:<5d} → {row['dest']}"
                  + ("  [replaces]" if row["replaces"] else "") + note)
        print("  licence chain (checked once for the whole set):")
        for c in r["licences"]:
            print(f"    {c['role']:16s} {c['file']:48s} {c.get('license')}")
        for cond in r.get("conditions") or []:
            print(f"  ⚠ condition: {cond}")
        if r.get("missing_slots"):
            print("  not in this job (optional): " + ", ".join(r["missing_slots"]))
        if r.get("size_note"):
            print(f"  note: {r['size_note']}")
        return 0
    try:
        r = manifest.approve(cfg, pos[0], name, game=_opt(args, "--game"), file=_opt(args, "--file"),
                             pick=int(pick) if pick else None, dry_run="--dry-run" in args)
    except (manifest.ApproveError, FileNotFoundError) as e:
        print(f"✗ {e}"); return 1
    print(("DRY RUN — would copy " if r.get("dry_run") else "✓ approved ") + f"{Path(r['file']).name} → {r['dest']}")
    print(f"  provenance → {r['provenance']}")
    for c in r["licences"]:
        print(f"  {c['role']:16s} {c['file']:48s} {c.get('license')}")
    for cond in manifest.licence_conditions(cfg, r["licences"]):
        print(f"  ⚠ condition: {cond}")
    if r.get("size_note"):
        print(f"  note: {r['size_note']}")
    return 0


def cmd_licences(cfg: dict, args: list[str]) -> int:
    from . import manifest
    game = _opt(args, "--game", "turing_accords")
    text = manifest.licence_report(cfg, game)
    out = cfgmod.path_of(cfg, "out") / f"licences_{game}.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(f"wrote {out}")
    return 0


def cmd_review(cfg: dict, args: list[str]) -> int:
    from . import review
    pos = _positional(args, ("--by", "--thumb"))
    if not pos:
        print("usage: review <suite-or-batch> [--by category|model|type] [--thumb 256]"); return 2
    try:
        out = review.build(cfg, pos[0], _opt(args, "--by", "category"), int(_opt(args, "--thumb", 256)))
    except ValueError as e:
        print(e); return 1
    print(f"review: {out / 'index.html'}")
    if "--open" in args:
        import os
        if hasattr(os, "startfile"):
            os.startfile(str(out / "index.html"))   # Windows: open the page in the default browser
    return 0


def cmd_rate(cfg: dict, args: list[str]) -> int:
    from . import review
    pos = _positional(args, ("--import",))
    f = _opt(args, "--import")
    if not pos or not f:
        print("usage: rate <suite-or-batch> --import <ratings.json>   (bakeoff rate <suite> <job> <1-5> rates one)"); return 2
    rf, n = review.import_ratings(cfg, pos[0], f)
    print(f"merged {n} rating(s) into {rf}")
    return 0


def cmd_brief(cfg: dict, args: list[str]) -> int:
    from . import brief
    pos = _positional(args, ("--game",))
    if not pos or pos[0] not in brief.KINDS:
        print("usage: brief maps|sleeves|icons [--game G]"); return 2
    out, n = brief.write(cfg, _opt(args, "--game", "turing_accords"), pos[0])
    print(f"wrote {out} — {n} draft job(s). Edit the prompts, delete the \"_draft\" line, then submit.")
    return 0


def cmd_comfy_paths(cfg: dict, args: list[str]) -> int:
    text = cfgmod.extra_model_paths_yaml(cfg)
    comfy_root = cfgmod.path_of(cfg, "comfy_root")
    if comfy_root.exists():
        out = comfy_root / "extra_model_paths.yaml"
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out}:\n{text}")
    else:
        print(f"ComfyUI not installed at {comfy_root}; this is what it would get:\n{text}")
    return 0


def cmd_ui(cfg: dict, args: list[str]) -> int:
    from . import ui
    port = int(_opt(args, "--port", str(ui.PORT)))
    ui.serve(cfg, port)
    return 0


def cmd_eta(cfg: dict, args: list[str]) -> int:
    from . import eta
    for line in eta.lines(cfg):
        print(line)
    return 0


def cmd_bakeoff(cfg: dict, args: list[str]) -> int:
    from . import bakeoff
    if not args or args[0] not in ("plan", "submit", "report", "rate"):
        print(bakeoff.__doc__); return 2
    sub = args[0]
    if sub in ("plan", "submit"):
        if len(args) < 2:
            print("usage: bakeoff plan|submit <suite.json> [--quick] [--force]"); return 2
        with open(args[1], "r", encoding="utf-8") as f:
            suite = json.load(f)
        if "--quick" in args:
            # a smoke run: first checkpoint, no-LoRA + the first two LoRAs, first prompt of each category
            suite = dict(suite)
            inv = bakeoff.inventory(cfg)
            cks = sorted(r["file"] for r in inv if r.get("kind") == "checkpoint")
            los = sorted(r["file"] for r in inv if r.get("kind") in ("lora", "lycoris") and r.get("base") == "sdxl")
            suite["checkpoints"] = cks[:1]
            suite["loras"] = los[:2]
            suite["categories"] = {c: {**d, "prompts": dict(list(d["prompts"].items())[:1])} for c, d in suite["categories"].items()}
            suite["suite"] = suite["suite"] + "_quick"
        inv = bakeoff.inventory(cfg, refresh=("--rescan" in args))
        p = bakeoff.plan(suite, inv, cfg)
        print(f"suite {p['suite']}: {len(p['checkpoints'])} checkpoints × ({len(p['loras'])} LoRAs + none) → {len(p['jobs'])} renders, ~{p['estimate_min']} min at {suite.get('seconds_per_render', 9)} s each")
        for lo, tr in p["triggers"].items():
            print(f"  LoRA {lo:55s} trigger: {tr or '(none known)'}")
        if p["skipped"]:
            seen = set()
            for sk in p["skipped"]:
                if sk["lora"] in seen:
                    continue
                seen.add(sk["lora"])
                print(f"  SKIP {sk['lora']}: {sk['reason']}")
        new_jobs, skipped = p["jobs"], {}
        if "--force" not in args:
            from . import dedupe
            new_jobs, skipped = dedupe.filter_new(cfg, p["jobs"], f"bakeoff/{p['suite']}")
            per = p["estimate_min"] / max(1, len(p["jobs"]))
            print(f"  {len(new_jobs)} new, ~{round(per * len(new_jobs), 1)} min" + (f"; {dedupe.describe(skipped)}" if skipped else ""))
        if sub == "submit":
            if not new_jobs:
                print(f"0 new — every cell of {p['suite']} is already queued or finished (bakeoff report {p['suite']} to look; --force to run again)")
                return 0
            ids = bakeoff.submit({**p, "jobs": new_jobs, "skipped_existing": skipped}, _queue(cfg))
            print(f"queued {len(ids)} renders under batch bakeoff/{p['suite']} — start run_worker.bat; then: python -m forge bakeoff report {p['suite']}")
        return 0
    if sub == "report":
        if len(args) < 2 or args[1].startswith("--"):
            print("usage: bakeoff report <suite-name> [--detail-at <prompt>=x,y[,size]]... [--detail-auto]"); return 2
        from . import detail
        for i, a in enumerate(args):
            if a == "--detail-at" and i + 1 < len(args):
                try:
                    pid, rec = detail.set_at(args[1], args[i + 1])
                except ValueError as e:
                    print(f"✗ {e}"); return 2
                print(f"detail crop for {pid}: centred at {rec['at']}" + (f", {rec['size']} px" if rec.get("size") else "") + f" (saved to {detail.path(args[1])})")
        if "--detail-auto" in args:
            from .engines.comfy import ComfyClient
            q = _queue(cfg)
            rows = bakeoff._collect(args[1], q)
            for line in detail.auto(args[1], rows, ComfyClient(cfg["comfy"]["url"])):
                print(line)
        if not getattr(bakeoff, "DETAIL_OVERRIDES", False):
            print("note: this forge's bakeoff.report does not read detail_at.json yet (wired after the queue empties) — "
                  "the review page (review.bat) already uses it")
        out = bakeoff.report(args[1], _queue(cfg))
        print(f"report: {out}")
        return 0
    if sub == "rate":
        if len(args) < 4:
            print("usage: bakeoff rate <suite-name> <job-id> <1-5> [note]"); return 2
        bakeoff.rate(args[1], args[2], int(args[3]), " ".join(args[4:]))
        print("rated")
        return 0
    return 2


COMMANDS = {
    "submit": cmd_submit, "worker": cmd_worker, "status": cmd_status, "requeue": cmd_requeue,
    "validate": cmd_validate, "validate-workflow": cmd_validate_workflow, "palette": cmd_palette,
    "models": cmd_models, "docs": cmd_docs, "doctor": cmd_doctor, "comfy-paths": cmd_comfy_paths, "bakeoff": cmd_bakeoff, "eta": cmd_eta, "ui": cmd_ui,
    "retry": cmd_retry, "comfy-up": cmd_comfy_up,
    "wanted": cmd_wanted, "approve": cmd_approve, "licences": cmd_licences, "review": cmd_review, "rate": cmd_rate,
    "brief": cmd_brief, "pause": cmd_pause, "resume": cmd_resume,
}


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often run cp1252, which cannot print → × · ★ — never let a print crash a command
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = cfgmod.load()
    cfgmod.ensure_dirs(cfg)
    logmod.setup(cfgmod.path_of(cfg, "logs"))
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return 0
    cmd, args = argv[0], argv[1:]
    if cmd not in COMMANDS:
        print(f"unknown command '{cmd}'\n{__doc__}"); return 2
    return COMMANDS[cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
