"""GPU job handlers — diffusion through ComfyUI, then the CPU finish (downscale, alpha, snap)."""
from __future__ import annotations
import io, json, random
from pathlib import Path

from PIL import Image

from ..engines import comfy, sdxl_graph, flux2_graph, flux1_graph
from ..ops import palette as pal, pixelize as pix, alpha as al, sheet as sh, tiles as tl
from .common import Context, write_prov, save_png, full_prompt, negative, model_licence


def _client(ctx: Context):
    if ctx.comfy is None:
        raise RuntimeError("this job needs the GPU worker (run_worker.bat), not the CPU worker")
    if not hasattr(ctx.comfy, "run_by_node"):
        # a worker started before an update holds an old client object; give it the current class (no restart needed)
        old = ctx.comfy
        ctx.comfy = comfy.ComfyClient(old.url, old.timeout, old.poll)
    if not ctx.comfy.is_up():
        raise RuntimeError(f"ComfyUI is not reachable at {ctx.comfy.url} — start it (run_worker.bat does) and retry")
    return ctx.comfy


def _gen(ctx: Context, job: dict, width: int, height: int, batch: int = 1, seed: int | None = None) -> tuple[list[Image.Image], dict]:
    client = _client(ctx)
    wf = job.get("workflow") or ctx.setting(job, "workflow") or ctx.cfg["comfy"]["default_workflow"]
    ckpt = job.get("checkpoint") or ctx.setting(job, "checkpoint") or ctx.cfg["comfy"]["default_checkpoint"]
    if seed is None:
        seed = int(job.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    imgs = comfy.txt2img(client, wf, full_prompt(ctx, job), job.get("negative") or negative(ctx, job), seed,
                         width, height, int(job.get("steps", 28)), float(job.get("cfg", 6.0)), ckpt, batch=batch)
    pil = [Image.open(io.BytesIO(b)).convert("RGBA") for b in imgs]
    prov = {"engine": "comfyui", "workflow": wf, "checkpoint": ckpt, "seed": seed, "width": width, "height": height,
            "steps": int(job.get("steps", 28)), "cfg": float(job.get("cfg", 6.0)), "full_prompt": full_prompt(ctx, job)}
    prov.update(model_licence(ctx, ckpt))
    return pil, prov


def scene_card(job: dict, ctx: Context, out: Path) -> dict:
    cw, ch = ctx.setting(job, "card_size", [288, 162])
    k = int(ctx.setting(job, "render_scale", 4))
    # SDXL likes multiples of 64 around 1 MP; render at k× the card then downscale (sharper than native small)
    rw, rh = (max(512, (cw * k) // 64 * 64), max(512, (ch * k) // 64 * 64))
    n = int(job.get("variants", 1))
    imgs, prov = _gen(ctx, job, rw, rh, batch=n)
    snapper = ctx.snapper(job) if job.get("snap", True) else None
    outputs = []
    for i, im in enumerate(imgs):
        suffix = "" if n == 1 else f"_{i + 1}"
        save_png(im, out / f"raw{suffix}.png")
        card = pix.to_target(im, (int(cw), int(ch)))
        if snapper is not None:
            card, _ = snapper.snap(card, dither="ordered")
        save_png(card, out / f"card{suffix}.png")
        outputs.append(f"card{suffix}.png")
    if n > 1:
        save_png(sh.contact_sheet([Image.open(out / o) for o in outputs], outputs, cols=min(n, 3), cell=(int(cw), int(ch)), title=job.get("name")), out / "contact.png")
    write_prov(out, job, **prov, post=["lanczos_downscale", "palette_snap(ordered)" if snapper else None], palette=ctx.setting(job, "palette") if snapper else None, outputs=outputs)
    return {"outputs": outputs, "seed": prov["seed"], "card_size": [cw, ch]}


def concept(job: dict, ctx: Context, out: Path) -> dict:
    w, h = job.get("size") or [1536, 864]
    n = int(job.get("variants", 2))
    imgs, prov = _gen(ctx, job, int(w), int(h), batch=n)
    outputs = []
    for i, im in enumerate(imgs):
        name = f"concept_{i + 1}.png" if n > 1 else "concept.png"
        save_png(im, out / name)
        outputs.append(name)
    if n > 1:
        save_png(sh.contact_sheet(imgs, outputs, cols=min(n, 2), cell=(480, 270), title=job.get("name")), out / "contact.png")
    write_prov(out, job, **prov, outputs=outputs)
    return {"outputs": outputs, "seed": prov["seed"]}


def portrait(job: dict, ctx: Context, out: Path) -> dict:
    """Seed-locked set: same seed, same base prompt, one appended phrase per expression."""
    w, h = job.get("size") or [768, 768]
    ow, oh = job.get("out_size") or [128, 128]
    seed = int(job.get("seed", 12345))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    base_prompt = str(job["prompt"])
    snapper = ctx.snapper(job) if job.get("snap") else None
    outputs, provs = [], []
    for expr in job["expressions"]:
        j = dict(job)
        j["prompt"] = f"{base_prompt}, {expr}"
        imgs, prov = _gen(ctx, j, int(w), int(h), batch=1, seed=seed)
        slug = "".join(c if c.isalnum() else "_" for c in expr.lower())[:40].strip("_")
        save_png(imgs[0], out / f"raw_{slug}.png")
        small = pix.to_target(imgs[0], (int(ow), int(oh)))
        if snapper is not None:
            small, _ = snapper.snap(small)
        save_png(small, out / f"{slug}.png")
        outputs.append(f"{slug}.png")
        provs.append({"expression": expr, **prov})
    save_png(sh.contact_sheet([Image.open(out / o) for o in outputs], outputs, cols=4, cell=(int(ow) * 2, int(oh) * 2), title=job.get("name")), out / "contact.png")
    write_prov(out, job, seed=seed, renders=provs, outputs=outputs, out_size=[ow, oh])
    return {"outputs": outputs, "seed": seed, "expressions": len(outputs)}


def prop(job: dict, ctx: Context, out: Path) -> dict:
    """Render on a flat key colour, flood the background to alpha, trim, scale to target_h, snap."""
    w, h = job.get("size") or [768, 768]
    key = str(job.get("key_color") or "#ff00ff")
    j = dict(job)
    j["prompt"] = f"{job['prompt']}, isolated on a flat solid {_color_word(key)} background, centered, full object visible"
    n = int(job.get("variants", 3))
    imgs, prov = _gen(ctx, j, int(w), int(h), batch=n)
    snapper = ctx.snapper(job) if job.get("snap", True) else None
    outputs = []
    for i, im in enumerate(imgs):
        suffix = "" if n == 1 else f"_{i + 1}"
        save_png(im, out / f"raw{suffix}.png")
        cut = al.trim(al.remove_flat_background(im, al.hex_to_rgb(key), tolerance=40))
        small = al.scale_to_height(cut, int(job.get("target_h", 64)))
        if snapper is not None:
            small, _ = snapper.snap(small)
        save_png(small, out / f"prop{suffix}.png")
        outputs.append(f"prop{suffix}.png")
    save_png(sh.contact_sheet([Image.open(out / o) for o in outputs], outputs, cols=min(n, 4), cell=(160, 160), title=job.get("name")), out / "contact.png")
    write_prov(out, job, **prov, post=["remove_flat_background", "trim", "scale_to_height", "palette_snap" if snapper else None], key_color=key, outputs=outputs)
    return {"outputs": outputs, "seed": prov["seed"]}


def tile_texture(job: dict, ctx: Context, out: Path) -> dict:
    w, h = job.get("size") or [512, 512]
    j = dict(job)
    j["prompt"] = f"{job['prompt']}, seamless tileable texture, top-down, flat even lighting, no objects, no border"
    imgs, prov = _gen(ctx, j, int(w), int(h), batch=1)
    raw = imgs[0]
    save_png(raw, out / "raw.png")
    seamless = tl.make_seamless(raw)
    ts = int(job.get("tile_size", 32))
    tile = pix.to_target(seamless, (ts, ts), method="box")
    snapper = ctx.snapper(job) if job.get("snap", True) else None
    if snapper is not None:
        tile, _ = snapper.snap(tile)
    save_png(tile, out / "tile.png")
    variants = tl.jitter_variants(tile, n=int(job.get("variants", 4)), seed=prov["seed"])
    if snapper is not None:
        variants, _ = snapper.snap(variants)
    save_png(variants, out / "variants.png")
    # a 4×4 repeat so the eye can judge the tiling
    rep = Image.new("RGBA", (ts * 4, ts * 4))
    for yy in range(4):
        for xx in range(4):
            rep.paste(tile, (xx * ts, yy * ts))
    save_png(rep, out / "repeat_4x4.png")
    score = tl.seam_score(tile)
    write_prov(out, job, **prov, post=["make_seamless", "box_downscale", "palette_snap" if snapper else None, "jitter_variants"], seam_score=score, tile_size=ts)
    return {"outputs": ["tile.png", "variants.png", "repeat_4x4.png"], "seam_score": round(score, 3), "seed": prov["seed"]}


def _color_word(hex_color: str) -> str:
    r, g, b = al.hex_to_rgb(hex_color)
    if r > 200 and b > 200 and g < 80:
        return "magenta"
    if g > 200 and r < 80 and b < 80:
        return "green"
    if r > 230 and g > 230 and b > 230:
        return "white"
    return "grey"


def _model_gb(ctx: Context, name: str) -> float:
    """Size in GB of a checkpoint/diffusion-model file found in any configured model folder (0 if not found)."""
    from .. import config as cfgmod
    for kind in ("diffusion_models", "checkpoints"):
        for d in cfgmod.model_dirs(ctx.cfg, kind):
            p = Path(d) / name
            if p.exists():
                return p.stat().st_size / 1e9
    return 0.0


def _weight_dtype(ctx: Context, name: str) -> str:
    gb = _model_gb(ctx, name)
    limit = float(ctx.cfg.get("comfy", {}).get("fp8_cast_over_gb", 14.0))
    return "fp8_e4m3fn" if gb > limit else "default"


def build_graph(ctx: Context, job: dict, w: int, h: int, seed: int, count: int | None = None) -> tuple[dict, dict]:
    """The engine graph for a job (`graph`: sdxl · flux2_klein · flux1) and its provenance fields.
    Shared by `render` and the paint jobs (scene_paint, repaint, icon, sleeve) so every engine works everywhere."""
    job = dict(job)
    job["size"] = [int(w), int(h)]
    job["seed"] = int(seed)
    if count is not None:
        job["count"] = int(count)
    graph_kind = str(job.get("graph") or "sdxl").lower()
    ckpt = job.get("checkpoint") or ctx.setting(job, "checkpoint") or ctx.cfg["comfy"]["default_checkpoint"]
    loras = [dict(l) for l in (job.get("loras") or [])]
    prompt = full_prompt(ctx, job)
    neg = job.get("negative") if job.get("negative") is not None else negative(ctx, job)
    comfy_cfg = ctx.cfg.get("comfy", {})
    if graph_kind == "flux2_klein":
        fx = comfy_cfg.get("flux2", {})
        distilled = job.get("distilled")
        if distilled is None:
            distilled = flux2_graph.is_distilled(ckpt)
        steps = int(job["steps"]) if job.get("steps") is not None else (4 if distilled else 20)
        cfg = float(job["cfg"]) if job.get("cfg") is not None else (1.0 if distilled else 5.0)
        default_te = fx.get("text_encoder_9b", "qwen_3_8b_fp8mixed.safetensors") if "9b" in ckpt.lower() else fx.get("text_encoder", "qwen_3_4b.safetensors")
        text_encoder = job.get("text_encoder") or default_te
        vae = job.get("vae") or fx.get("vae", "flux2-vae.safetensors")
        wdt = job.get("weight_dtype") or _weight_dtype(ctx, ckpt)
        graph = flux2_graph.build(ckpt, prompt, neg, seed, int(w), int(h), text_encoder=text_encoder, vae=vae, steps=steps, cfg=cfg,
                                  loras=loras, batch=int(job.get("count") or 1), sampler=str(job.get("sampler") or "euler"),
                                  distilled=bool(distilled), weight_dtype=wdt)
        graph_name, extra = "flux2_graph", {"text_encoder": text_encoder, "vae": vae, "distilled": bool(distilled), "weight_dtype": wdt}
        sampler, scheduler = str(job.get("sampler") or "euler"), "flux2"
    elif graph_kind == "krea2":
        from ..engines import krea2_graph
        graph, graph_name, extra, steps, cfg, sampler, scheduler = krea2_graph.from_job(comfy_cfg, job, ckpt, prompt, neg, seed, int(w), int(h), loras)
    elif graph_kind == "flux1":
        fx = comfy_cfg.get("flux1", {})
        steps = int(job["steps"]) if job.get("steps") is not None else (4 if flux1_graph.is_schnell(ckpt) else 20)
        guidance = float(job["guidance"]) if job.get("guidance") is not None else float(fx.get("guidance", 3.5))
        clip_l = job.get("clip_l") or fx.get("clip_l", "clip_l.safetensors")
        t5 = job.get("t5") or fx.get("t5", "t5xxl_fp8_e4m3fn.safetensors")
        vae = job.get("vae") or fx.get("vae", "ae.safetensors")
        all_in_one = bool(job.get("all_in_one", False))
        cfg = float(job["cfg"]) if job.get("cfg") is not None else 1.0   # >1 only for de-distilled fine-tunes
        wdt = job.get("weight_dtype") or _weight_dtype(ctx, ckpt)
        graph = flux1_graph.build(ckpt, prompt, seed, int(w), int(h), clip_l=clip_l, t5=t5, vae=vae, steps=steps, guidance=guidance,
                                  loras=loras, batch=int(job.get("count") or 1), sampler=str(job.get("sampler") or "euler"),
                                  scheduler=str(job.get("scheduler") or "simple"), all_in_one=all_in_one, negative=neg,
                                  cfg=cfg, weight_dtype=wdt)
        graph_name, extra = "flux1_graph", {"clip_l": clip_l, "t5": t5, "vae": vae, "guidance": guidance, "all_in_one": all_in_one, "weight_dtype": wdt}
        sampler, scheduler = str(job.get("sampler") or "euler"), str(job.get("scheduler") or "simple")
    else:
        # None = "use the default" (schema.with_defaults fills unset optional fields with None)
        steps = int(job["steps"]) if job.get("steps") is not None else 25
        cfg = float(job["cfg"]) if job.get("cfg") is not None else 6.0
        sampler, scheduler = str(job.get("sampler") or "dpmpp_2m"), str(job.get("scheduler") or "karras")
        graph = sdxl_graph.build(ckpt, prompt, neg, seed, int(w), int(h), steps, cfg,
                                 loras=loras, batch=int(job.get("count") or 1), sampler=sampler,
                                 scheduler=scheduler, clip_skip=int(job.get("clip_skip") or 0))
        graph_name, extra = "sdxl_graph", {}
    prov = {"engine": "comfyui", "graph": graph_name, "checkpoint": ckpt, "loras": loras, "seed": seed, "width": int(w),
            "height": int(h), "steps": int(steps), "cfg": float(cfg), "sampler": sampler, "scheduler": scheduler,
            "full_prompt": prompt, "negative": neg, **extra}
    prov.update(model_licence(ctx, ckpt))
    return graph, prov


def render(job: dict, ctx: Context, out: Path) -> dict:
    """Raw render through a code-built graph: checkpoint + LoRA chain, nothing after.
    `graph`: "sdxl" (default) · "flux2_klein" (FLUX.2 [klein] 4B) · "flux1" (FLUX.1 dev/schnell and fine-tunes)."""
    client = _client(ctx)
    seed = int(job.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    w, h = job.get("size") or [1024, 1024]
    graph, prov = build_graph(ctx, job, int(w), int(h), seed)
    ckpt, loras = prov["checkpoint"], prov["loras"]
    imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in client.run(graph)]
    outputs = []
    for i, im in enumerate(imgs):
        name = "render.png" if i == 0 else f"render_{i + 1}.png"
        save_png(im, out / name)
        outputs.append(name)
    write_prov(out, job, **prov, outputs=outputs, meta=job.get("meta", {}))
    filed = []
    meta = job.get("meta") or {}
    if meta.get("suite"):
        from .. import bakeoff
        filed = [str(p) for p in bakeoff.file_render(str(meta["suite"]), meta, out / "render.png")]
    return {"outputs": outputs, "seed": seed, "checkpoint": ckpt, "loras": [l["name"] for l in loras], "filed": filed}
