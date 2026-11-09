"""CPU job handlers — pure image operations over files already on disk."""
from __future__ import annotations
import json
from pathlib import Path

from PIL import Image

from ..ops import palette as pal, pixelize as pix, alpha as al, sheet as sh, godot
from .common import Context, write_prov, save_png


def _inputs(ctx: Context, job: dict) -> list[Path]:
    paths = [ctx.resolve(p) for p in job["inputs"]]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("inputs not found: " + ", ".join(missing))
    return paths


def palette_snap(job: dict, ctx: Context, out: Path) -> dict:
    snapper = ctx.snapper(job)
    if snapper is None:
        raise ValueError("palette_snap needs a palette (job.palette, the game's forge.game.json, or forge.json defaults)")
    report = {}
    prev = None
    for p in _inputs(ctx, job):
        im = Image.open(p)
        snapped, idx = snapper.snap(im, dither=job.get("dither"), prev_idx=prev, hysteresis=float(job.get("hysteresis") or 0.0))
        if job.get("hysteresis"):
            prev = idx.reshape(-1)
        save_png(snapped, out / p.name)
        report[p.name] = {"before": pal.report(im), "after": pal.report(snapped, snapper.rgb)}
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    write_prov(out, job, op="palette_snap", palette=ctx.setting(job, "palette"), inputs=[str(p) for p in _inputs(ctx, job)])
    return {"files": len(report), "report": "report.json"}


def pixelize(job: dict, ctx: Context, out: Path) -> dict:
    report = {}
    snapper = ctx.snapper(job) if job.get("snap") else None
    for p in _inputs(ctx, job):
        im = Image.open(p).convert("RGBA")
        if job.get("target"):
            small = pix.to_target(im, tuple(job["target"]))
            info = {"mode": "resize", "target": job["target"]}
        else:
            scale = job.get("scale")
            if scale:
                s, ox, oy, conf = int(scale), 0, 0, None
            else:
                s, ox, oy, conf = pix.detect_grid(im)
                if s == 1:
                    raise ValueError(f"{p.name}: no pixel grid detected (confidence {conf:.2f}); pass 'scale' or 'target'")
            small = pix.downscale_cells(im, s, ox, oy, method=job.get("method", "mode"))
            info = {"mode": "grid", "scale": s, "offset": [ox, oy], "confidence": conf}
        if snapper is not None:
            small, _ = snapper.snap(small)
        save_png(small, out / p.name)
        info["size"] = list(small.size)
        info["colors"] = pal.report(small)["colors"]
        report[p.name] = info
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    write_prov(out, job, op="pixelize", palette=ctx.setting(job, "palette") if snapper else None)
    return {"files": len(report)}


def remove_bg(job: dict, ctx: Context, out: Path) -> dict:
    n = 0
    key = al.hex_to_rgb(job["key_color"]) if job.get("key_color") else None
    for p in _inputs(ctx, job):
        im = al.remove_flat_background(Image.open(p), key, int(job.get("tolerance", 28)))
        if job.get("trim", True):
            im = al.trim(im)
        if job.get("pad_to"):
            im = al.pad_to(im, tuple(job["pad_to"]), job.get("anchor", "bottom"))
        save_png(im, out / p.name)
        n += 1
    write_prov(out, job, op="remove_bg")
    return {"files": n}


def contact_sheet(job: dict, ctx: Context, out: Path) -> dict:
    paths = _inputs(ctx, job)
    images = sh.load_images(paths)
    labels = job.get("labels") or [p.stem for p in paths]
    cs = sh.contact_sheet(images, labels, cols=int(job.get("cols", 4)), cell=tuple(job.get("cell", [288, 162])), title=job.get("title"))
    save_png(cs, out / "contact.png")
    return {"files": 1, "contact": "contact.png", "images": len(images)}


def pack_sheet(job: dict, ctx: Context, out: Path) -> dict:
    paths = _inputs(ctx, job)
    frames = sh.load_images(paths)
    sheet, meta = sh.pack_frames(frames, cols=int(job.get("cols", 8)), cell=tuple(job["cell"]) if job.get("cell") else None,
                                 anchor=job.get("anchor", "bottom"))
    save_png(sheet, out / "sheet.png")
    meta["order"] = [p.name for p in paths]
    (out / "sheet.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    write_prov(out, job, op="pack_sheet", frames=meta["order"])
    return meta


def godot_tileset(job: dict, ctx: Context, out: Path) -> dict:
    png = ctx.resolve(job["png"])
    if not png.exists():
        raise FileNotFoundError(str(png))
    im = Image.open(png)
    ts = int(job["tile_size"])
    count = im.width // ts
    res_path = job.get("res_path") or f"res://{png.name}"
    text = godot.tileset_tres(res_path, ts, count, [bool(b) for b in job["blocking"]])
    name = job.get("name") or png.stem
    godot.write(out / f"{name}.tres", text)
    return {"tiles": count, "tres": f"{name}.tres"}


def overworld(job: dict, ctx: Context, out: Path) -> dict:
    raise NotImplementedError(
        "overworld: planned — pulls Natural Earth / TIGER / GNIS / 3DEP / NLCD, compresses the scale and emits "
        "the game's map format. Design: docs/ROADMAP.md. Nothing was generated.")
