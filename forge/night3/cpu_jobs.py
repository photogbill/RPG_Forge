"""Handlers for the Night 3 CPU plug-in job types (sprite tools, UI pieces). Thin: the work is in forge/ops/."""
from __future__ import annotations
import json
from pathlib import Path

from PIL import Image

from ..jobs.common import write_prov, save_png
from ..ops import sprites as sp


def _hexkey(v):
    if not v:
        return None
    from ..ops.alpha import hex_to_rgb
    return hex_to_rgb(v) if isinstance(v, str) else tuple(v)


def facings_pack(job: dict, ctx, out: Path) -> dict:
    out = Path(out)
    src = ctx.resolve(job["input"])
    poses = sp.load_poses(src)
    sheet, rep = sp.facings_pack(poses, job.get("cell") or sp.CELL, job.get("mirror"), float(job.get("figure_height") or 0.92),
                                 int(job.get("baseline") if job.get("baseline") is not None else 6), _hexkey(job.get("key")),
                                 int(job.get("tolerance") or 28))
    save_png(sheet, out / "sheet.png")
    prev = sp.anim_preview(sheet, out, job.get("cell") or sp.CELL, "facings")
    (out / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    write_prov(out, job, op="facings_pack", input=str(src), report=rep, outputs=["sheet.png", "turntable.gif"],
               note="the poses' own provenance still applies")
    return {"outputs": ["sheet.png", "turntable.gif", "report.json"], "size": list(sheet.size),
            "missing": rep["missing"], "touches_edge": rep["touches_edge"]}


def anim_preview(job: dict, ctx, out: Path) -> dict:
    out = Path(out)
    src = ctx.resolve(job["input"])
    r = sp.anim_preview(Image.open(src).convert("RGBA"), out, job.get("cell") or sp.CELL, str(job.get("layout") or "auto"),
                        float(job.get("fps") or 8), float(job.get("turntable_fps") or 2))
    names = [Path(f).name for f in r["files"]]
    write_prov(out, job, op="anim_preview", input=str(src), outputs=names)
    return {"outputs": names, "layout": r["layout"]}


def turnaround_split(job: dict, ctx, out: Path) -> dict:
    out = Path(out)
    src = ctx.resolve(job["input"])
    views = sp.turnaround_split(Image.open(src), int(job.get("min_gap") or 6), int(job.get("min_width") or 12),
                                _hexkey(job.get("key")), int(job.get("tolerance") or 28))
    names = []
    for i, v in enumerate(views, 1):
        save_png(v, out / f"view_{i:02d}.png")
        names.append(f"view_{i:02d}.png")
    write_prov(out, job, op="turnaround_split", input=str(src), views=len(views), outputs=names)
    return {"outputs": names, "views": len(views)}


def nine_slice(job: dict, ctx, out: Path) -> dict:
    from ..ops import ui_pieces as ui
    out = Path(out)
    src = ctx.resolve(job["input"])
    piece, m, rep = ui.nine_slice(Image.open(src), job.get("margins"), float(job.get("scale") or 1.0),
                                  int(job.get("snap") if job.get("snap") is not None else 3), bool(job.get("tileable", True)),
                                  job.get("key"))
    save_png(piece, out / "piece.png")
    (out / "piece.json").write_text(json.dumps(rep["godot"] | {"size": rep["size"]}, indent=1), encoding="utf-8")
    save_png(ui.stretch_preview(piece, m), out / "preview.png")
    write_prov(out, job, op="nine_slice", input=str(src), report=rep, outputs=["piece.png", "piece.json", "preview.png"],
               note="the input picture's own provenance still applies")
    return {"outputs": ["piece.png", "piece.json", "preview.png"], "margins": m}


def button_states(job: dict, ctx, out: Path) -> dict:
    from ..ops import ui_pieces as ui
    from ..ops import sheet as sh
    out = Path(out)
    src = ctx.resolve(job["input"])
    st = ui.button_states(Image.open(src))
    stem = Path(src).stem
    names = []
    for k, im in st.items():
        save_png(im, out / f"{stem}_{k}.png")
        names.append(f"{stem}_{k}.png")
    w, h = st["normal"].size
    save_png(sh.contact_sheet(list(st.values()), list(st), cols=4, cell=(max(96, w), max(48, h))), out / "states.png")
    write_prov(out, job, op="button_states", input=str(src), outputs=names + ["states.png"])
    return {"outputs": names + ["states.png"]}
