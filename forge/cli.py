"""Command line: python -m forge <command>

  submit <job.json | batch.json> [...]   validate and queue jobs (a batch file holds many)
  worker [--gpu] [--once]                run jobs from the queue (GPU worker needs ComfyUI up)
  status                                 queue counts
  requeue                                move crashed running/ jobs back to pending/
  validate <job.json>                    check a job file without queueing it
  validate-workflow <name>               check a ComfyUI workflow template's placeholders
  palette pull <lospec-slug>             download a palette from lospec.com into palettes/
  palette list                           palettes on disk
  palette swatch <name> [out.png]        render a palette as a swatch image
  models list                            the model registry with licences
  models pull <name>                     download a registered model into models/ (Hugging Face)
  docs                                   regenerate docs/JOB_TYPES.md from the schema
  doctor                                 check Python, Pillow, numpy, ComfyUI, GPU
"""
from __future__ import annotations
import json, shutil, subprocess, sys
from pathlib import Path

from . import config as cfgmod, schema, log as logmod
from .queue import Queue, run_worker


def _queue(cfg: dict) -> Queue:
    cfgmod.ensure_dirs(cfg)
    return Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))


def cmd_submit(cfg: dict, args: list[str]) -> int:
    if not args:
        print("usage: submit <job.json | batch.json> [...]"); return 2
    q = _queue(cfg)
    total = 0
    for a in args:
        p = Path(a)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "jobs" in data:
            ids = q.submit_batch(data)
            print(f"{p.name}: queued {len(ids)} jobs" + (f" (batch '{data.get('batch')}')" if data.get("batch") else ""))
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
    from .jobs import HANDLERS
    from .jobs.common import Context
    ctx = Context(cfg=cfg, palettes_dir=cfgmod.path_of(cfg, "palettes"), root=cfgmod.ROOT)
    if gpu:
        from .engines.comfy import ComfyClient
        ctx.comfy = ComfyClient(cfg["comfy"]["url"], int(cfg["comfy"]["timeout_sec"]), float(cfg["comfy"]["poll_sec"]))
        print(f"GPU worker — ComfyUI at {ctx.comfy.url}: {'up' if ctx.comfy.is_up() else 'NOT reachable (GPU jobs will fail until it is)'}")
    else:
        print("CPU worker — GPU job types will be left in the queue for a GPU worker")
    q = _queue(cfg)
    n = run_worker(q, HANDLERS, ctx, gpu=gpu, once=once, poll_sec=float(cfg["worker"]["poll_sec"]))
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
    if args[0] == "pull":
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            print("pip install huggingface_hub (install.bat does)"); return 1
        for name in args[1:]:
            m = reg["models"][name]
            dest = cfgmod.path_of(cfg, "models") / m.get("dest", "")
            dest.mkdir(parents=True, exist_ok=True)
            if not m.get("commercial_ok"):
                print(f"NOTE: {name} is {m.get('license')} — fine for experiments, not for shipped assets.")
            for fname in m["files"]:
                print(f"  downloading {m['repo']}/{fname} → {dest}")
                hf_hub_download(repo_id=m["repo"], filename=fname, local_dir=str(dest))
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
    return 0


COMMANDS = {
    "submit": cmd_submit, "worker": cmd_worker, "status": cmd_status, "requeue": cmd_requeue,
    "validate": cmd_validate, "validate-workflow": cmd_validate_workflow, "palette": cmd_palette,
    "models": cmd_models, "docs": cmd_docs, "doctor": cmd_doctor,
}


def main(argv: list[str] | None = None) -> int:
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
