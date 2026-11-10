"""character_set (Night 4, F2): one character variant → portrait moods on its locked seed, a battle pose, and a
turnaround cut and packed by sprite_intake into the same sheet contract as a sheet William draws himself.

Two halves, because the worker only ever sees plain text:
  expand_set(cfg, job)   at SUBMIT (the shim in forge/cli_night4.py): registry → one plain-text render per part;
                         every {{block}} expanded now — a TODO block refuses the submit and names itself
  run(job, ctx, out)     in the WORKER: the renders as a pipeline (same seed = same face), then sprite_intake on the
                         turnaround; the parts copied to the top of the job folder with one contact sheet
"""
from __future__ import annotations
import json
import logging
import shutil
from pathlib import Path

from PIL import Image

from ..jobs.common import Context, save_png, write_prov

log = logging.getLogger("forge.charset")

PARTS = ("moods", "battle", "turnaround")
RENDER_KEYS = ("checkpoint", "sampler", "scheduler", "steps", "cfg", "graph", "loras")


class CharsetError(ValueError):
    pass


def expand_set(cfg: dict, job: dict, game: str | None = None) -> dict:
    from . import characters as chmod
    from .. import prompts as pl
    g = job.get("game") or game or "turing_accords"
    ch = chmod.load(cfg, g, str(job["character"]))
    vname, v = chmod.variant(ch, job.get("variant"))
    lib = pl.load(cfg, g)
    base = job.get("prompt") or v.get("prompt")
    if not base:
        raise CharsetError(f"{ch['id']}/{vname}: the registry has no prompt for this variant")
    neg = job.get("negative") if job.get("negative") is not None else v.get("negative")
    seed = job.get("seed") if job.get("seed") is not None else v.get("seed")
    if seed in (None, -1):
        raise CharsetError(f"{ch['id']}/{vname}: no locked seed in the registry — the moods would be different faces")
    parts = list(job.get("parts") or PARTS)
    bad = [p for p in parts if p not in PARTS]
    if bad:
        raise CharsetError(f"parts {bad}: use {', '.join(PARTS)}")
    moods = list(job.get("moods") or (v.get("wanted") or {}).get("portrait_moods") or ["neutral"])
    common = {k: (job.get(k) if job.get(k) is not None else v.get(k)) for k in RENDER_KEYS}
    common = {k: val for k, val in common.items() if val is not None}
    plan = []
    if "moods" in parts:
        for m in moods:
            plan.append(("mood:" + m, f"{base}, {{{{pose.portrait}}}}, {{{{mood.{m}}}}}",
                         job.get("portrait_size") or [896, 1152], {}))
    if "battle" in parts:
        plan.append(("battle", f"{base}, {{{{pose.battle}}}}", job.get("battle_size") or [832, 1216], {}))
    if "turnaround" in parts:
        lora = job.get("sheet_lora") or (v.get("sheet_loras") or [None])[0]
        extra = {}
        if lora:
            extra["loras"] = list(common.get("loras") or []) + [{"name": lora, "strength": float(job.get("sheet_lora_strength") or 0.8)}]
        plan.append(("turnaround", f"{base}, {{{{pose.turnaround}}}}", job.get("turnaround_size") or [1536, 768], extra))
    used: list[str] = []
    renders = []
    for part, text, size, extra in plan:
        try:
            p = pl.expand_text(text, lib["blocks"], used)
            n = pl.expand_text(neg, lib["blocks"], used) if neg else None
        except pl.PromptError as e:
            raise CharsetError(f"{ch['id']}/{vname} {part}: {e}")
        r = {"part": part, "prompt": p, "negative": n, "seed": int(seed), "size": list(size), **common, **extra}
        hits = pl.never_hits(r, pl.never_words(lib))
        if hits:
            raise CharsetError(f"{ch['id']}/{vname} {part}: the prompt contains {', '.join(hits)} (never-list)")
        renders.append(r)
    out = {k: val for k, val in job.items() if k not in ("prompt", "negative")}
    out.update({"renders": renders, "variant": vname, "character_registry": ch["_hash"], "prompt_blocks": used,
                "prompt_library": lib["version"], "prompt_template": {"prompt": base, "negative": neg}})
    out.setdefault("name", f"{ch['id']}_{vname}_set")
    return out


def run(job: dict, ctx: Context, out: Path) -> dict:
    from .. import pipeline
    from ..jobs import get_handlers
    out = Path(out)
    renders = job.get("renders")
    if not renders:
        raise CharsetError("this character_set job was not expanded — submit it with submit.bat (the registry and "
                           "prompt blocks are read at submit time)")
    steps = []
    for r in renders:
        st = {"type": "render", **{k: v for k, v in r.items() if k != "part"}}
        st["meta"] = {"part": r["part"], "character": job.get("character"), "variant": job.get("variant")}
        steps.append(st)
    turn = next((i for i, r in enumerate(renders) if r["part"] == "turnaround"), None)
    if turn is not None:
        steps.append({"type": "sprite_intake", "input": f"$steps[{turn + 1}].outputs[0]", "character": job["character"],
                      "variant": job.get("variant"), "game": job.get("game") or "turing_accords",
                      **({"mapping": job["mapping"]} if job.get("mapping") else {})})
    res = pipeline.run({**job, "type": "pipeline", "steps": steps}, ctx, out, get_handlers())
    made, tiles, labels, licences = [], [], [], []
    for s, r in zip(res["steps"], renders):
        src = Path(s["outputs"][0])
        part = r["part"]
        name = (f"moods/{part.split(':', 1)[1]}.png" if part.startswith("mood:") else f"{part}.png")
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out / name)
        made.append(name)
        tiles.append(Image.open(src).convert("RGB")); labels.append(part)
        pp = out / s["dir"] / "prov.json"
        if pp.exists():
            p = json.loads(pp.read_text(encoding="utf-8"))
            for k in ("checkpoint",):
                if p.get(k):
                    licences.append({"role": k, "file": Path(str(p[k])).name})
            for lo in p.get("loras") or []:
                if isinstance(lo, dict) and lo.get("name"):
                    licences.append({"role": "lora", "file": lo["name"]})
    warnings = []
    if turn is not None:
        idir = out / res["steps"][-1]["dir"]
        for f in ("sheet.png", "anim.png", "numbers.png", "turntable.gif", "edges.md"):
            if (idir / f).exists():
                shutil.copyfile(idir / f, out / f)
                made.append(f)
        warnings = (res["steps"][-1]["result"] or {}).get("warnings") or []
        if (out / "sheet.png").exists():
            sh = Image.open(out / "sheet.png").convert("RGBA")
            bg = Image.new("RGBA", sh.size, (40, 40, 46, 255)); bg.alpha_composite(sh)
            tiles.append(bg.convert("RGB")); labels.append("sheet (contract)")
    from ..ops import sheet as shmod
    save_png(shmod.contact_sheet(tiles, labels, cols=4, cell=(360, 460), title=job.get("name")), out / "contact.png")
    from ..jobs.common import licence_chain
    chain, ok = licence_chain(ctx, {f"{l['role']}#{i}": l["file"] for i, l in enumerate(licences)})
    write_prov(out, job, op="character_set", character=job.get("character"), variant=job.get("variant"),
               parts=[r["part"] for r in renders], seed=renders[0]["seed"], licences=chain, commercial_ok=ok,
               outputs=made, steps=[{"step": s["step"], "type": s["type"], "dir": s["dir"]} for s in res["steps"]])
    return {"outputs": made + ["contact.png"], "parts": [r["part"] for r in renders], "commercial_ok": ok,
            "warnings": warnings}
