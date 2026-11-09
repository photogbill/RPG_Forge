"""The painted-scene set (roadmap N1–N3): depth_map · normal_map (luminance|depth) · scene_layers · scene_kit.

A scene is a set of six files, named for the game's slots (the contract, `21_Build_Plan_Night_2.md §3b`):

    <id>.png        the painting — the walkable mid plane, never altered after painting
    <id>_n.png      tangent-space normals, OpenGL convention (green = up)
    <id>_e.png      additive glow (emissive colours on black)
    <id>_back.png   far parallax plane, opaque, wider than the painting by its overscan on each side
    <id>_over.png   walk-behind plane, RGBA
    <id>_depth.png  16-bit grey, white = near

Every file is the painting's pixel size except `_back` (wider by 2 × overscan).

    depth_map     GPU  inputs → <stem>_depth.png through comfyui_controlnet_aux's Depth Anything V2 **Small** (Apache-2.0).
                       The node's default is the Large model, which is CC-BY-NC: the forge always names Small and
                       refuses to build the graph without it.
    normal_map    CPU  `source: "luminance"` (F11, unchanged) or `"depth"` (+ `depth`: a path or list of paths,
                       `detail` 0..1 of luminance normals blended back in). Writes a lit-from-the-left preview too.
    scene_layers  CPU  painting + depth → <stem>_back.png, <stem>_over.png, <stem>_mid_alpha.png, layers.json, slide.png
    scene_kit     GPU  scene_paint (or repaint when `init` is given) → depth → normals → glow → layers, one job id,
                       the six slot files at the top of out/<id>/ and one contact sheet. A pipeline preset.
"""
from __future__ import annotations
import io, json, shutil
from pathlib import Path

from PIL import Image

from ..engines import graph_ops as go
from ..ops import depth as dp, layers as ly, lighting as lt, sheet as sh
from ..log import get
from .common import Context, write_prov, save_png, licence_chain

log = get("scene")

DEPTH_NODE = "DepthAnythingV2Preprocessor"
DEPTH_WEIGHTS = "depth_anything_v2_vits.pth"          # Small, Apache-2.0. Base/Large/Giant are CC-BY-NC.
DEPTH_REMEDY = "install_comfy_aux.bat (comfyui_controlnet_aux), then restart run_worker.bat"
SLOTS = ("", "_n", "_e", "_back", "_over", "_depth")    # the six files, as suffixes of the scene's name


class SceneError(RuntimeError):
    pass


def _f(job: dict, key: str, default):
    """A field's value, treating None (what schema.with_defaults fills in) as 'use the default'."""
    v = job.get(key)
    return default if v is None else v


def _inputs(ctx: Context, items) -> list[Path]:
    items = [items] if isinstance(items, str) else list(items or [])
    paths = [ctx.resolve(p) for p in items]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("inputs not found: " + ", ".join(missing))
    return paths


def _paired(ctx: Context, job: dict, key: str, paintings: list[Path]) -> list[Path]:
    """`depth` (or another per-painting field): one path for every painting, or a single path for one painting."""
    v = job.get(key)
    if v is None:
        raise SceneError(f"'{key}' is required (one {key} map per input)")
    got = _inputs(ctx, v)
    if len(got) != len(paintings):
        raise SceneError(f"{len(paintings)} input(s) but {len(got)} {key} map(s) — give one per input, in the same order")
    return got


# ------------------------------------------------------------------ depth_map (GPU)
def depth_graph(info: dict, image_name: str, resolution: int = 1024) -> dict:
    """LoadImage → DepthAnythingV2Preprocessor (Small weights, always named) → SaveImage. Pure dict; `info` is
    ComfyUI's /object_info (the node's inputs are filled from it so pack updates don't break the graph)."""
    if DEPTH_NODE not in info:
        raise SceneError(f"ComfyUI has no {DEPTH_NODE} node — run {DEPTH_REMEDY}")
    go.check_choice(info, DEPTH_NODE, "ckpt_name", DEPTH_WEIGHTS)
    g: dict = {"1": {"class_type": "LoadImage", "inputs": {"image": image_name}}}
    inputs = go.node_from_info(info, DEPTH_NODE, {"image": ["1", 0], "ckpt_name": DEPTH_WEIGHTS, "resolution": int(resolution)})
    if inputs.get("ckpt_name") != DEPTH_WEIGHTS:      # never let the node fall back to its (non-commercial) default
        raise SceneError(f"{DEPTH_NODE} would not take ckpt_name={DEPTH_WEIGHTS}; refusing to run a non-commercial default")
    g["2"] = {"class_type": DEPTH_NODE, "inputs": inputs}
    g["3"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "forge_depth", "images": ["2", 0]}}
    return g


def depth_map(job: dict, ctx: Context, out: Path) -> dict:
    from .gpu import _client
    client = _client(ctx)
    info = client.object_info()
    res = int(_f(job, "resolution", 1024))
    outputs, previews, labels = [], [], []
    for p in _inputs(ctx, job["inputs"]):
        with Image.open(p) as im:
            size = im.size
        g = depth_graph(info, client.upload_image(p, name=f"{job.get('id', 'job')}_{p.name}"), res)
        got = client.run_by_node(g)
        raw = Image.open(io.BytesIO(got["3"][0]))
        d = dp.load_depth(raw, size)                     # back to the painting's exact size, float
        if job.get("invert"):
            d = 1.0 - d
        name = f"{p.stem}_depth.png"
        save_png(dp.depth_image16(d), out / name)
        outputs.append(name)
        previews.append(dp.depth_preview(d))
        labels.append(p.stem)
    if len(previews) > 1:
        save_png(sh.contact_sheet(previews, labels, cols=min(3, len(previews)), cell=(480, 270), title=job.get("name")), out / "contact.png")
    licences, ok = licence_chain(ctx, {"depth_model": DEPTH_WEIGHTS})
    write_prov(out, job, op="depth_map", engine="comfyui", node=DEPTH_NODE, depth_model=DEPTH_WEIGHTS, resolution=res,
               convention="16-bit grey, white = near", inputs=[str(p) for p in _inputs(ctx, job["inputs"])],
               licences=licences, depth_commercial_ok=ok, outputs=outputs,
               note="the source paintings' own provenance still applies")
    return {"outputs": outputs, "depth_model": DEPTH_WEIGHTS, "commercial_ok": ok}


# ------------------------------------------------------------------ normal_map (CPU, N1 version)
def normal_map(job: dict, ctx: Context, out: Path) -> dict:
    source = str(_f(job, "source", "luminance"))
    paintings = _inputs(ctx, job["inputs"])
    depths = _paired(ctx, job, "depth", paintings) if source == "depth" else [None] * len(paintings)
    strength = float(_f(job, "strength", 2.0))
    smooth = float(_f(job, "smooth", 1.5 if source == "depth" else 1.0))
    detail = float(_f(job, "detail", 0.0))
    outputs, sheet, labels = [], [], []
    for p, dpath in zip(paintings, depths):
        img = Image.open(p).convert("RGB")
        d = dp.load_depth(dpath, img.size) if dpath is not None else None
        n = dp.normal_map(img, source=source, depth=d, strength=strength, smooth=smooth, detail=detail,
                          invert_y=bool(job.get("invert_y")))
        save_png(n, out / f"{p.stem}_n.png")
        outputs.append(f"{p.stem}_n.png")
        if _f(job, "preview", True):
            lit = dp.relight(img, n)
            save_png(lit, out / f"{p.stem}_lit.png")
            sheet += [n, lit]
            labels += [f"{p.stem} normals ({source})", "lit from the left"]
            if _f(job, "compare", source == "depth"):
                nl = dp.normals_from_luminance(img, 2.0, 1.0, bool(job.get("invert_y")))
                sheet += [nl, dp.relight(img, nl)]
                labels += ["normals (luminance)", "lit from the left"]
    if sheet:
        cols = 4 if len(sheet) % 4 == 0 else 2
        save_png(sh.contact_sheet(sheet, labels, cols=cols, cell=(480, 270), title=job.get("name")), out / "contact.png")
    write_prov(out, job, op="normal_map", source=source, strength=strength, smooth=smooth, detail=detail,
               convention="OpenGL (green = up)", inputs=[str(p) for p in paintings],
               depth=[str(x) for x in depths] if source == "depth" else None, outputs=outputs)
    return {"outputs": outputs, "source": source}


# ------------------------------------------------------------------ scene_layers (CPU)
def scene_layers(job: dict, ctx: Context, out: Path) -> dict:
    paintings = _inputs(ctx, job["inputs"])
    depths = _paired(ctx, job, "depth", paintings)
    outputs, report = [], {}
    shift = int(_f(job, "preview_shift", 40))
    for p, dpath in zip(paintings, depths):
        img = Image.open(p).convert("RGB")
        d = dp.load_depth(dpath, img.size)
        L = ly.split_layers(img, d, cuts=_f(job, "cuts", "auto"), feather=float(_f(job, "feather", 3.0)),
                            overscan=int(_f(job, "overscan", 48)), fill=str(_f(job, "fill", "extend")))
        made = []
        if L["back"] is not None:
            save_png(L["back"], out / f"{p.stem}_back.png")
            made.append(f"{p.stem}_back.png")
        if L["over"] is not None:
            save_png(L["over"], out / f"{p.stem}_over.png")
            made.append(f"{p.stem}_over.png")
        save_png(L["mid_alpha"], out / f"{p.stem}_mid_alpha.png")
        frames = ly.slide_frames(img, L, shift)
        save_png(sh.contact_sheet(frames, [f"camera {-shift:+d} px", "rest", f"camera {shift:+d} px"], cols=3,
                                  cell=(480, max(120, int(480 * img.size[1] / img.size[0]))), title=f"{p.stem} — layers sliding"),
                 out / f"{p.stem}_slide.png")
        outputs += made
        report[p.stem] = L["info"]
    (out / "layers.json").write_text(json.dumps(report if len(report) > 1 else next(iter(report.values())), indent=1), encoding="utf-8")
    write_prov(out, job, op="scene_layers", inputs=[str(p) for p in paintings], depth=[str(x) for x in depths],
               layers=report, outputs=outputs)
    return {"outputs": outputs, "layers": "layers.json"}


# ------------------------------------------------------------------ scene_kit (pipeline preset)
PAINT_KEYS = ("prompt", "negative", "seed", "size", "target", "crop", "init", "denoise", "control", "upscale", "refine",
              "refine_max_mp", "face_fix", "freeu", "graph", "checkpoint", "loras", "steps", "cfg", "sampler", "scheduler",
              "style_prefix", "megapixels", "all_in_one")


def kit_steps(job: dict) -> list[dict]:
    """The step list scene_kit runs. Pure — tested as data."""
    paint_type = "repaint" if job.get("init") else "scene_paint"
    paint = {"type": paint_type, **{k: job[k] for k in PAINT_KEYS if job.get(k) is not None}}
    if paint_type == "repaint" and isinstance(paint.get("denoise"), list):
        raise SceneError("scene_kit makes one set: give `denoise` as one value (sweep with a plain repaint first)")
    n = dict(job.get("normals") or {})
    e = dict(job.get("glow") or {})
    lay = dict(job.get("layers") or {})
    return [
        paint,
        {"type": "depth_map", "inputs": ["$steps[1].outputs[0]"], **({"resolution": job["depth_resolution"]} if job.get("depth_resolution") else {})},
        {"type": "normal_map", "inputs": ["$steps[1].outputs[0]"], "source": "depth", "depth": ["$steps[2].outputs[0]"],
         "strength": n.get("strength", 2.0), "smooth": n.get("smooth", 1.5), "detail": n.get("detail", 0.35), "compare": False},
        {"type": "emissive_mask", "inputs": ["$steps[1].outputs[0]"], **{k: v for k, v in e.items()
                                                                        if k in ("threshold", "min_saturation", "colors", "tolerance", "feather")}},
        {"type": "scene_layers", "inputs": ["$steps[1].outputs[0]"], "depth": ["$steps[2].outputs[0]"],
         **{k: v for k, v in lay.items() if k in ("cuts", "feather", "overscan", "fill", "preview_shift")}},
    ]


def _find(step_dir: Path, suffix: str) -> Path | None:
    hits = sorted(step_dir.glob(f"*{suffix}.png"))
    return hits[0] if hits else None


def scene_kit(job: dict, ctx: Context, out: Path) -> dict:
    from .. import pipeline
    from . import HANDLERS, get_handlers
    handlers = {**(HANDLERS or get_handlers()), **SCENE_HANDLERS}     # this module's steps, whatever the table says
    base = str(job.get("slot_name") or "scene")
    pjob = {**job, "type": "pipeline", "steps": kit_steps(job)}
    res = pipeline.run(pjob, ctx, out, handlers)
    steps = res["steps"]
    paint_dir, depth_dir, n_dir, e_dir, l_dir = (out / s["dir"] for s in steps)
    painting = Path(steps[0]["outputs"][0])
    found = {"": painting, "_depth": Path(steps[1]["outputs"][0]), "_n": Path(steps[2]["outputs"][0]),
             "_e": Path(steps[3]["outputs"][0]), "_back": _find(l_dir, "_back"), "_over": _find(l_dir, "_over")}
    slots, missing = {}, []
    for sfx in SLOTS:
        src = found.get(sfx)
        if src is None or not src.exists():
            missing.append(f"{base}{sfx}.png")
            continue
        dst = out / f"{base}{sfx}.png"
        shutil.copyfile(src, dst)
        slots[sfx or "_main"] = dst.name
    if (l_dir / "layers.json").exists():
        shutil.copyfile(l_dir / "layers.json", out / "layers.json")
    mid_alpha = _find(l_dir, "_mid_alpha")
    if mid_alpha is not None:
        shutil.copyfile(mid_alpha, out / f"{base}_mid_alpha.png")

    # the contact sheet: painting · depth · relit · glow · layers
    img = Image.open(painting).convert("RGB")
    cell = (480, max(120, int(480 * img.size[1] / img.size[0])))
    tiles, labels = [img], ["painting"]
    d = dp.load_depth(found["_depth"], img.size)
    tiles.append(dp.depth_preview(d)); labels.append("depth (white = near)")
    lit = n_dir.glob("*_lit.png")
    lit = next(iter(sorted(lit)), None)
    tiles.append(Image.open(lit) if lit else dp.relight(img, Image.open(found["_n"]))); labels.append("lit from the left")
    tiles.append(Image.open(found["_e"]).convert("RGB")); labels.append("glow")
    if found["_back"] is not None:
        tiles.append(Image.open(found["_back"]).convert("RGB")); labels.append("back plane")
    if found["_over"] is not None:
        ov = Image.open(found["_over"]).convert("RGBA")
        chk = Image.new("RGBA", ov.size, (255, 0, 255, 255)); chk.alpha_composite(ov)
        tiles.append(chk.convert("RGB")); labels.append("over plane (magenta = clear)")
    save_png(sh.contact_sheet(tiles, labels, cols=3, cell=cell, title=job.get("name")), out / "contact.png")

    # one prov for the set: every model that touched the pixels — the paint chain plus the depth model
    paint_prov = json.loads((paint_dir / "prov.json").read_text(encoding="utf-8")) if (paint_dir / "prov.json").exists() else {}
    licences = list(paint_prov.get("licences") or [])
    d_lic, _ = licence_chain(ctx, {"depth_model": DEPTH_WEIGHTS})
    licences += d_lic
    ok = bool(licences) and all(r.get("commercial_ok") is True for r in licences)
    layers_info = json.loads((out / "layers.json").read_text(encoding="utf-8")) if (out / "layers.json").exists() else None
    write_prov(out, job, op="scene_kit", set=True, slot_name=base, slots=slots, missing_slots=missing,
               paint=paint_prov, licences=licences, commercial_ok=ok, layers=layers_info,
               steps=[{"step": s["step"], "type": s["type"], "dir": s["dir"]} for s in steps],
               contract="six files: <id>.png, _n, _e, _back, _over, _depth — OpenGL normals, depth white = near, "
                        "all at the painting's size except _back (wider by its overscan)")
    outs = [slots[k] for k in ("_main", "_n", "_e", "_back", "_over", "_depth") if k in slots]
    return {"outputs": outs, "slots": slots, "missing_slots": missing, "commercial_ok": ok,
            "size": list(img.size), "step_dirs": [s["dir"] for s in steps]}


SCENE_HANDLERS = {"depth_map": depth_map, "normal_map": normal_map, "scene_layers": scene_layers, "scene_kit": scene_kit}
