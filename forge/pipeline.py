"""Pipelines (roadmap F5): one job that runs a chain of jobs, each step's output feeding the next.

    {"type": "pipeline", "name": "house_paint", "game": "<game id>",
     "steps": [
       {"type": "render", "prompt": "…", "size": [1344, 768]},
       {"type": "upscale", "inputs": ["$prev.outputs[0]"], "fit": [1920, 1080]},
       {"type": "palette_snap", "inputs": ["$prev.outputs[0]"]}
     ]}

References (whole strings only): `$prev.outputs` (every output of the step before — inside a list it expands in
place), `$prev.outputs[K]`, `$steps[N].outputs[K]` (N counts from 1). Each step writes to out/<id>/NN_<type>/; a
failing step fails the chain with its number and type in the error. One receipt, one prov.json, one contact
sheet showing the first image of every step.
"""
from __future__ import annotations
import re
from pathlib import Path

from PIL import Image

from . import schema
from .log import get

log = get("pipeline")
REF = re.compile(r"^\$(?:prev|steps\[(\d+)\])\.outputs(?:\[(\d+)\])?$")
SKIP_NAMES = ("contact.png", "control.png")


class PipelineError(RuntimeError):
    pass


def resolve_ref(text: str, results: list[dict]):
    """'$prev.outputs[0]' → a path string; '$prev.outputs' → a list of path strings; anything else → unchanged."""
    m = REF.match(text)
    if not m:
        return text
    if not results:
        raise PipelineError(f"'{text}' used in the first step — there is no earlier step")
    if m.group(1) is not None:
        n = int(m.group(1))
        if not 1 <= n <= len(results):
            raise PipelineError(f"'{text}': there is no step {n} before this one")
        outs = results[n - 1]["outputs"]
    else:
        outs = results[-1]["outputs"]
    if m.group(2) is None:
        return list(outs)
    k = int(m.group(2))
    if k >= len(outs):
        raise PipelineError(f"'{text}': that step made only {len(outs)} output(s)")
    return outs[k]


def substitute(value, results: list[dict]):
    if isinstance(value, str):
        return resolve_ref(value, results)
    if isinstance(value, list):
        out = []
        for v in value:
            r = substitute(v, results)
            if isinstance(v, str) and isinstance(r, list):
                out.extend(r)                  # "$prev.outputs" inside a list expands in place
            else:
                out.append(r)
        return out
    if isinstance(value, dict):
        return {k: substitute(v, results) for k, v in value.items()}
    return value


def step_outputs(step_dir: Path, result: dict) -> list[str]:
    """Absolute paths of what a step made: its result's `outputs` if it lists them, else the PNGs it wrote
    (minus contact sheets, raw renders and control images)."""
    names = result.get("outputs")
    if names:
        return [str(step_dir / n) for n in names]
    files = sorted(p for p in step_dir.glob("*.png")
                   if p.name not in SKIP_NAMES and not p.name.startswith(("raw", "control_overlay")))
    return [str(p) for p in files]


def run(job: dict, ctx, out: Path, handlers: dict) -> dict:
    results: list[dict] = []
    for i, raw_step in enumerate(job["steps"]):
        n = i + 1
        stype = raw_step.get("type")
        step = {k: job[k] for k in ("game", "batch") if job.get(k) is not None}
        try:
            step.update(substitute(raw_step, results))
        except PipelineError as e:
            raise PipelineError(f"step {n} ({stype}): {e}") from None
        step.setdefault("name", f"{job.get('name') or 'pipeline'}_{n}")
        step["id"] = f"{job.get('id') or 'pipeline'}_s{n:02d}"
        problems = schema.validate(step)
        if problems:
            raise PipelineError(f"step {n} ({stype}): " + "; ".join(problems))
        if stype not in handlers:
            raise PipelineError(f"step {n}: no handler for type '{stype}'")
        if schema.needs_gpu(step) and getattr(ctx, "comfy", None) is None:
            raise PipelineError(f"step {n} ({stype}) needs the GPU worker")
        step = schema.with_defaults(step)
        d = out / f"{n:02d}_{stype}"
        d.mkdir(parents=True, exist_ok=True)
        log.info("pipeline %s: step %d/%d %s", job.get("id"), n, len(job["steps"]), stype)
        try:
            res = handlers[stype](step, ctx, d) or {}
        except Exception as e:  # noqa: BLE001 — re-raised with the step named
            raise PipelineError(f"step {n} ({stype}) failed: {type(e).__name__}: {e}") from e
        outs = step_outputs(d, res)
        results.append({"step": n, "type": stype, "dir": d.name, "outputs": outs, "result": res})
    return {"steps": results}


def handler(job: dict, ctx, out: Path) -> dict:
    from .jobs import HANDLERS, get_handlers
    from .jobs.common import write_prov, save_png
    from .ops import sheet as sh
    handlers = HANDLERS or get_handlers()
    res = run(job, ctx, out, handlers)
    steps = res["steps"]
    if job.get("contact", True):
        imgs, labels = [], []
        for st in steps:
            first = next((p for p in st["outputs"] if p.lower().endswith(".png")), None)
            if first and Path(first).exists():
                imgs.append(Image.open(first).convert("RGBA"))
                labels.append(f"{st['step']} {st['type']}")
        if imgs:
            save_png(sh.contact_sheet(imgs, labels, cols=min(len(imgs), 4), cell=(384, 216), title=job.get("name")), out / "contact.png")
    rel = lambda p: str(Path(p).relative_to(out)).replace("\\", "/") if Path(p).is_relative_to(out) else p
    write_prov(out, job, op="pipeline", steps=[{"step": s["step"], "type": s["type"], "outputs": [rel(p) for p in s["outputs"]]} for s in steps])
    last = steps[-1]
    return {"outputs": [rel(p) for p in last["outputs"]], "steps": len(steps),
            "step_dirs": [s["dir"] for s in steps], "commercial_ok": last["result"].get("commercial_ok")}
