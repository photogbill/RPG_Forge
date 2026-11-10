"""Handlers of the hand-off plug-in job types (G13): handoff_file (CPU) and handoff_kit (GPU — the depth model).
Loaded lazily by forge/plugins/handoff.py."""
from __future__ import annotations
import json
import shutil
from pathlib import Path

from PIL import Image

from ..jobs.common import Context, licence_chain, model_licence, save_png, write_prov
from ..ops import sheet as sh


def _source(job: dict, out: Path) -> tuple[Path, dict]:
    src_dir = Path(out).parent / str(job["source_job"])
    if not src_dir.is_dir():
        raise FileNotFoundError(f"source job folder not found: {src_dir} (the hand-off names job {job['source_job']})")
    p = src_dir / "prov.json"
    try:
        prov = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        prov = {}
    return src_dir, prov


def _picture(ctx: Context, job: dict) -> Image.Image:
    p = ctx.resolve(job["input"])
    if not p.exists():
        raise FileNotFoundError(f"the returned picture is missing: {p}")
    im = Image.open(p)
    im.load()
    if job.get("target") and list(im.size) != list(job["target"]):
        raise ValueError(f"{p.name} is {im.size[0]}x{im.size[1]}, the job expects {job['target'][0]}x{job['target'][1]} — "
                         "run `handoff in` again (it resizes same-shape pictures)")
    return im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")


def tool_line(ctx: Context, tool: str) -> dict:
    r = model_licence(ctx, tool)
    rec = {"role": "outside_tool", "file": tool, "model": r.get("model"), "license": r.get("license"),
           "commercial_ok": r.get("commercial_ok")}
    if r.get("commercial_ok") is None:
        rec["license"] = "licence not on file — record it with handoff_tool_add.bat"
    return rec


def _source_inputs(src_dir: Path) -> list[str]:
    from ..handoff import find_main, find_raw
    raw = find_raw(src_dir) or find_main(src_dir)
    return [str(raw)] if raw else []


def _side_by_side(src_main: Path | None, new: Image.Image, tool: str, out: Path, title: str | None) -> None:
    tiles, labels = [], []
    if src_main is not None and src_main.exists():
        tiles.append(Image.open(src_main).convert("RGB")); labels.append("the forge's own")
    tiles.append(new.convert("RGB")); labels.append(tool)
    w, h = new.size
    cw = 640
    ch = max(120, int(cw * h / max(1, w)))
    # a 1:1 crop from the centre of each, where the difference between upscalers shows
    cs = min(320, w, h)
    box = ((w - cs) // 2, (h - cs) // 2, (w - cs) // 2 + cs, (h - cs) // 2 + cs)
    for t, lab in list(zip(tiles, labels)):
        tiles.append(t.resize(new.size).crop(box) if t.size != new.size else t.crop(box)); labels.append(lab + " · 1:1 centre")
    save_png(sh.contact_sheet(tiles, labels, cols=len(labels) // 2, cell=(cw, ch), title=title), out / "contact.png")


def handoff_file(job: dict, ctx: Context, out: Path) -> dict:
    from ..handoff import find_main
    out = Path(out)
    src_dir, src_prov = _source(job, out)
    pic = _picture(ctx, job)
    main = find_main(src_dir)
    slot = str(job.get("slot_name") or (main.stem if main else "picture"))
    save_png(pic, out / f"{slot}.png")
    tool = str(job["tool"])
    licences = list(src_prov.get("licences") or []) + [tool_line(ctx, tool)]
    ok = bool(licences) and all(r.get("commercial_ok") is True for r in licences)
    _side_by_side(main, pic, tool, out, job.get("name"))
    write_prov(out, job, op="handoff_file", tool=tool, source_job=job["source_job"], returned=str(job["input"]),
               returned_file=job.get("returned_file"), inputs=_source_inputs(src_dir), licences=licences,
               commercial_ok=ok, size=list(pic.size))
    return {"outputs": [f"{slot}.png", "contact.png"], "commercial_ok": ok, "tool": tool, "size": list(pic.size)}


def handoff_kit(job: dict, ctx: Context, out: Path) -> dict:
    """The returned picture becomes the kit's painting; its companions are rebuilt from it with the source kit's
    settings (the same steps scene_kit runs after painting)."""
    from ..jobs import scene as sc, cpu
    from ..ops import depth as dp
    out = Path(out)
    src_dir, src_prov = _source(job, out)
    pic = _picture(ctx, job).convert("RGB")
    base = str(job.get("slot_name") or src_prov.get("slot_name") or "scene")
    painting = out / f"{base}.png"
    save_png(pic, painting)
    src_job = {}
    if (src_dir / "job.json").exists():
        try:
            src_job = json.loads((src_dir / "job.json").read_text(encoding="utf-8"))
        except ValueError:
            src_job = {}
    n = dict(src_job.get("normals") or {})
    e = dict(src_job.get("glow") or {})
    lay = dict(src_job.get("layers") or {})
    cuts = lay.get("cuts") or "auto"
    if (src_dir / "layers.json").exists():
        try:
            cuts = json.loads((src_dir / "layers.json").read_text(encoding="utf-8")).get("cuts") or cuts
        except ValueError:
            pass
    work = out / "_steps"
    dd, nd, ed, ld = (work / x for x in ("01_depth", "02_normals", "03_glow", "04_layers"))
    for d in (dd, nd, ed, ld):
        d.mkdir(parents=True, exist_ok=True)
    dres = job.get("depth_resolution") or src_job.get("depth_resolution")
    r = sc.depth_map({"id": f"{job.get('id', 'job')}_d", "inputs": [str(painting)], **({"resolution": dres} if dres else {})}, ctx, dd)
    depth = dd / r["outputs"][0]
    rn = sc.normal_map({"inputs": [str(painting)], "source": "depth", "depth": [str(depth)],
                        "strength": n.get("strength", 2.0), "smooth": n.get("smooth", 1.5), "detail": n.get("detail", 0.35),
                        "flatten": n.get("flatten", 0.85), "compare": False}, ctx, nd)
    re_ = cpu.emissive_mask({"inputs": [str(painting)], **{k: v for k, v in e.items()
                                                          if k in ("threshold", "min_saturation", "colors", "tolerance", "feather")}}, ctx, ed)
    sc.scene_layers({"inputs": [str(painting)], "depth": [str(depth)], "cuts": cuts,
                     **{k: v for k, v in lay.items() if k in ("feather", "overscan", "fill", "preview_shift")}}, ctx, ld)
    found = {"_depth": depth, "_n": nd / rn["outputs"][0], "_e": ed / re_["outputs"][0],
             "_back": ld / f"{painting.stem}_back.png", "_over": ld / f"{painting.stem}_over.png"}
    slots, missing = {"_main": painting.name}, []
    for sfx in ("_n", "_e", "_back", "_over", "_depth"):
        src = found[sfx]
        if not src.exists():
            missing.append(f"{base}{sfx}.png")
            continue
        shutil.copyfile(src, out / f"{base}{sfx}.png")
        slots[sfx] = f"{base}{sfx}.png"
    if (ld / "layers.json").exists():
        shutil.copyfile(ld / "layers.json", out / "layers.json")
    mid = ld / f"{painting.stem}_mid_alpha.png"
    if mid.exists():
        shutil.copyfile(mid, out / f"{base}_mid_alpha.png")
    # contact: painting · depth · glow · normals
    tiles, labels = [pic], [f"painting ({job['tool']})"]
    tiles.append(dp.depth_preview(dp.load_depth(depth, pic.size))); labels.append("depth (white = near)")
    tiles.append(Image.open(found["_e"]).convert("RGB")); labels.append("glow")
    tiles.append(Image.open(found["_n"]).convert("RGB")); labels.append("normals")
    cell = (480, max(120, int(480 * pic.size[1] / pic.size[0])))
    save_png(sh.contact_sheet(tiles, labels, cols=2, cell=cell, title=job.get("name")), out / "contact.png")
    tool = str(job["tool"])
    d_lic, _ = licence_chain(ctx, {"depth_model": sc.DEPTH_WEIGHTS})
    licences = list(src_prov.get("licences") or []) + d_lic + [tool_line(ctx, tool)]
    ok = bool(licences) and all(r.get("commercial_ok") is True for r in licences)
    layers_info = json.loads((out / "layers.json").read_text(encoding="utf-8")) if (out / "layers.json").exists() else None
    write_prov(out, job, op="handoff_kit", set=True, slot_name=base, slots=slots, missing_slots=missing,
               tool=tool, source_job=job["source_job"], returned=str(job["input"]), returned_file=job.get("returned_file"),
               inputs=_source_inputs(src_dir), licences=licences, commercial_ok=ok, layers=layers_info,
               contract="six files: <id>.png, _n, _e, _back, _over, _depth — as scene_kit")
    outs = [slots[k] for k in ("_main", "_n", "_e", "_back", "_over", "_depth") if k in slots]
    return {"outputs": outs + ["contact.png"], "slots": slots, "missing_slots": missing, "commercial_ok": ok,
            "tool": tool, "size": list(pic.size)}
