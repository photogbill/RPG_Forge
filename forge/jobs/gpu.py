"""GPU job handlers — diffusion through ComfyUI, then the CPU finish (downscale, alpha, snap)."""
from __future__ import annotations
import io, json, random
from pathlib import Path

from PIL import Image

from ..engines import comfy
from ..ops import palette as pal, pixelize as pix, alpha as al, sheet as sh, tiles as tl
from .common import Context, write_prov, save_png, full_prompt, negative, model_licence


def _client(ctx: Context):
    if ctx.comfy is None:
        raise RuntimeError("this job needs the GPU worker (run_worker.bat), not the CPU worker")
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
