"""Painted-background jobs (roadmap F1–F3 + the quality stages): scene_paint · repaint · upscale.

    scene_paint  prompt → render (~1 MP, default 1344×768) → [img2img from `init`] → [ControlNet] → upscale model →
                 cover-fit to `target` (default 1920×1080) → [refine: hires-fix repaint] → [face_fix: FaceDetailer]
                 → scene.png + raw.png + prov.json (+ control.png / control_overlay.png when a ControlNet ran)
    repaint      the greybox → painting bridge: `init` is required; the output is the init's exact pixel size (no
                 crop), so the game's walk polygons, doors and spawns stay valid. `denoise` may be a list — one
                 painting per value, same seed, on one contact sheet.
    upscale      any images → upscale model → exact size (`fit`, cover or stretch) or ×`factor`.

Every model that touched the pixels is listed in prov.json → `licences`, and `commercial_ok` is true only when all
of them are known and permitted — that is what `forge approve` checks.
"""
from __future__ import annotations
import io, random
from pathlib import Path

from PIL import Image

from ..engines import graph_ops as go
from ..ops import edges as ed, sheet as sh
from ..log import get
from .common import Context, write_prov, save_png, licence_chain
from .gpu import _client, build_graph

log = get("paint")

UNION_TYPES = {"canny": "canny/lineart/anime_lineart/mlsd", "lineart": "canny/lineart/anime_lineart/mlsd",
               "mlsd": "canny/lineart/anime_lineart/mlsd", "depth": "depth", "normal": "normal", "tile": "tile",
               "openpose": "openpose", "scribble": "hed/pidi/scribble/ted", "segment": "segment"}
# depth preprocessors and the commercial-OK weights each must use (Depth Anything V2 Base/Large/Giant are CC-BY-NC)
DEPTH_NODES = {"DepthAnythingV2Preprocessor": ("ckpt_name", "depth_anything_v2_vits.pth"),
               "MiDaS-DepthMapPreprocessor": (None, "dpt_hybrid-midas-501f0c75.pt")}


def _comfy(ctx: Context, key: str, default=None):
    return ctx.cfg.get("comfy", {}).get(key, default)


def _pick_models(ctx: Context, job: dict) -> dict:
    """checkpoint / loras: job → game's checkpoints_by_job / loras_by_job for this type → game checkpoint → default."""
    j = dict(job)
    g = ctx.game(job)
    t = job.get("type")
    if not j.get("checkpoint"):
        ck = (g.get("checkpoints_by_job") or {}).get(t)
        if ck:
            j["checkpoint"] = ck
    if j.get("loras") is None:
        lo = (g.get("loras_by_job") or {}).get(t)
        j["loras"] = [dict(x) for x in lo] if lo else []
    return j


class _Info:
    """ComfyUI's /object_info, fetched once per job and only if a stage needs it."""
    def __init__(self, client):
        self.client, self._d = client, None

    def get(self) -> dict:
        if self._d is None:
            self._d = self.client.object_info()
        return self._d


def _seed(job: dict) -> int:
    s = int(job.get("seed", -1) if job.get("seed") is not None else -1)
    return random.randint(0, 2**31 - 1) if s < 0 else s


def _prepare_control(ctx: Context, job: dict, client, info: _Info, out: Path, g: dict, default_image: Path | None, notes: list):
    """Add the ControlNet to graph g. Returns (control_edges_image or None, controlnet_file or None)."""
    c = job.get("control")
    if not c:
        return None, None
    ctype = str(c.get("type", "canny")).lower()
    src = ctx.resolve(c["image"]) if c.get("image") else default_image
    if src is None or not Path(src).exists():
        raise FileNotFoundError(f"control image not found: {c.get('image') or '(none, and no init)'}")
    model = c.get("model") or _comfy(ctx, "controlnet_union", "xinsir-union-sdxl-promax.safetensors")
    edges_img = None
    if ctype in ("canny", "lineart", "mlsd") and not c.get("preprocessed"):
        edges_img = ed.canny(Image.open(src), float(c.get("low", 0.08)), float(c.get("high", 0.2)))
        save_png(edges_img, out / "control.png")
        image_ref = go.load_image(g, client.upload_image(out / "control.png", name=f"{job.get('id', 'job')}_control.png"))
    elif ctype == "depth" and not c.get("preprocessed"):
        have = [n for n in DEPTH_NODES if n in info.get()]
        if not have:
            notes.append("control depth SKIPPED: no depth preprocessor node (install comfyui_controlnet_aux) — painted without ControlNet")
            log.warning("job %s: depth ControlNet skipped — comfyui_controlnet_aux not installed", job.get("id"))
            return None, None
        li = go.load_image(g, client.upload_image(src, name=f"{job.get('id', 'job')}_depth_src.png"))
        node = have[0]
        key, weights = DEPTH_NODES[node]
        given = {"image": li, "resolution": 1024}
        if key:
            go.check_choice(info.get(), node, key, weights)
            given[key] = weights
        image_ref = [go.add(g, node, go.node_from_info(info.get(), node, given)), 0]
        edges_img = ed.canny(Image.open(src))
        job.setdefault("_depth_model", weights)
    else:
        image_ref = go.load_image(g, client.upload_image(src, name=f"{job.get('id', 'job')}_control.png"))
        if ctype in ("canny", "lineart", "mlsd"):
            edges_img = Image.open(src).convert("L")
    go.add_controlnet(g, model, image_ref, float(c.get("strength", 0.6)), float(c.get("start", 0.0)), float(c.get("end", 1.0)),
                      UNION_TYPES.get(ctype) if c.get("union", True) else None)
    return edges_img, model


def paint_once(ctx: Context, job: dict, out: Path, *, seed: int, render_size: tuple[int, int], target: tuple[int, int],
               crop: str, init: Path | None, denoise: float | None, suffix: str = "", info: _Info | None = None) -> dict:
    """One painting through the whole chain. Writes scene{suffix}.png and raw{suffix}.png; returns its prov."""
    client = _client(ctx)
    info = info or _Info(client)
    rw, rh = render_size
    tw, th = target
    g, prov = build_graph(ctx, job, rw, rh, seed, count=1)
    notes: list[str] = []
    parts = {"checkpoint": prov["checkpoint"]}
    for i, lo in enumerate(prov.get("loras") or []):
        parts[f"lora{i + 1}"] = lo["name"]
    if init is not None:
        go.to_img2img(g, client.upload_image(init, name=f"{job.get('id', 'job')}_init.png"), float(denoise), rw, rh,
                      crop="disabled" if crop == "disabled" else "center")
    if job.get("freeu"):
        go.add_freeu(g)
    job = dict(job)
    edges_img, cn_model = _prepare_control(ctx, job, client, info, out, g, init, notes)
    if cn_model:
        parts["controlnet"] = cn_model
    if job.get("_depth_model"):
        parts["depth_model"] = job["_depth_model"]
    raw_id = go.add_raw_save(g)
    up = job.get("upscale", True)
    up_model = None
    if up:
        up_model = (up.get("model") if isinstance(up, dict) else None) or _comfy(ctx, "upscale_model", "RealESRGAN_x4plus.pth")
    ref = job.get("refine", True)
    # a refine pass at more than ~4 MP runs a 12 GB card out of memory: refine at a capped size, then upscale again
    max_mp = float(job.get("refine_max_mp") or _comfy(ctx, "refine_max_mp", 4.0))
    staged = bool(ref) and tw * th > max_mp * 1_000_000
    if staged:
        k = (max_mp * 1_000_000 / float(tw * th)) ** 0.5
        mw, mh = max(64, int(tw * k) // 8 * 8), max(64, int(th * k) // 8 * 8)
        go.add_upscale(g, up_model, mw, mh, crop)
        notes.append(f"refined at {mw}x{mh} (refine_max_mp {max_mp}), then upscaled to {tw}x{th}")
    elif up_model or (tw, th) != (rw, rh):
        go.add_upscale(g, up_model, tw, th, crop)
    if up_model:
        parts["upscaler"] = up_model
    if ref:
        rd = float(ref.get("denoise", 0.3)) if isinstance(ref, dict) else (float(ref) if isinstance(ref, (int, float)) and not isinstance(ref, bool) else 0.3)
        rsteps = ref.get("steps") if isinstance(ref, dict) else None
        go.add_refine(g, rd, rsteps)
    if staged:
        go.add_upscale(g, up_model, tw, th, "disabled")
    ff = job.get("face_fix")
    if ff:
        ffo = ff if isinstance(ff, dict) else {}
        det = ffo.get("detector") or _comfy(ctx, "face_detector", "bbox/face_yolov8m.pt")
        go.add_face_detailer(g, info.get(), detector=det, denoise=float(ffo.get("denoise", 0.4)),
                             guide_size=int(ffo.get("guide_size", 1024)), max_size=int(ffo.get("max_size", 1024)),
                             bbox_threshold=float(ffo.get("threshold", 0.5)), cycle=int(ffo.get("cycle", 1)))
        parts["face_detector"] = Path(det).name
    final_id = go.save_node(g)
    res = client.run_by_node(g)
    final = Image.open(io.BytesIO(res[final_id][0])).convert("RGB")
    raw = Image.open(io.BytesIO(res[raw_id][0])).convert("RGB") if raw_id in res else None
    save_png(final, out / f"scene{suffix}.png")
    if raw is not None:
        save_png(raw, out / f"raw{suffix}.png")
    extra = {}
    if edges_img is not None:
        save_png(ed.overlay(final, edges_img), out / f"control_overlay{suffix}.png")
        extra["layout_agreement"] = round(ed.edge_agreement(final, edges_img), 3)
    licences, ok = licence_chain(ctx, parts)
    prov.update({"seed": seed, "render_size": [rw, rh], "target": [tw, th], "crop": crop,
                 "init": str(init) if init else None, "denoise": denoise, "control": job.get("control"),
                 "upscale_model": up_model, "refine": job.get("refine", True), "face_fix": job.get("face_fix") or False,
                 "freeu": bool(job.get("freeu")), "licences": licences, "commercial_ok": ok, "notes": notes,
                 "nodes": sorted(go.required_nodes(g)), **extra})
    return prov


def _contact(out: Path, names: list[str], labels: list[str], title: str | None, target: tuple[int, int]):
    cell = (480, max(120, int(480 * target[1] / max(1, target[0]))))
    save_png(sh.contact_sheet([Image.open(out / n) for n in names], labels, cols=min(len(names), 3), cell=cell, title=title),
             out / "contact.png")


def scene_paint(job: dict, ctx: Context, out: Path) -> dict:
    j = _pick_models(ctx, job)
    tw, th = j.get("target") or ctx.setting(j, "scene_size") or [1920, 1080]
    init = ctx.resolve(j["init"]) if j.get("init") else None
    if init is not None and not init.exists():
        raise FileNotFoundError(f"init image not found: {init}")
    rw, rh = j.get("size") or [1344, 768]
    denoise = (float(j["denoise"]) if j.get("denoise") is not None else 0.55) if init is not None else None
    n = int(j.get("variants") or 1)
    seed = _seed(j)
    info = _Info(_client(ctx))
    provs, names = [], []
    for i in range(n):
        sfx = "" if n == 1 else f"_{i + 1}"
        provs.append(paint_once(ctx, j, out, seed=seed + i, render_size=(int(rw), int(rh)), target=(int(tw), int(th)),
                                crop=str(j.get("crop") or "center"), init=init, denoise=denoise, suffix=sfx, info=info))
        names.append(f"scene{sfx}.png")
    if n > 1:
        _contact(out, names, [f"seed {p['seed']}" for p in provs], j.get("name"), (int(tw), int(th)))
    base = dict(provs[0])
    base.pop("seed", None)
    write_prov(out, j, **base, seeds=[p["seed"] for p in provs], outputs=names, variants=provs if n > 1 else None)
    return {"outputs": names, "seed": seed, "size": [int(tw), int(th)], "commercial_ok": base["commercial_ok"],
            **({"layout_agreement": base["layout_agreement"]} if "layout_agreement" in base else {})}


def repaint(job: dict, ctx: Context, out: Path) -> dict:
    j = _pick_models(ctx, job)
    init = ctx.resolve(j["init"])
    if not init.exists():
        raise FileNotFoundError(f"init image not found: {init}")
    with Image.open(init) as im:
        iw, ih = im.size
    tw, th = j.get("target") or [iw, ih]
    rw, rh = j.get("size") or go.fit_render_size(iw, ih, float(j.get("megapixels") or 1.0))
    d = j.get("denoise") if j.get("denoise") is not None else 0.55
    values = [float(x) for x in d] if isinstance(d, list) else [float(d)]
    seed = _seed(j)
    info = _Info(_client(ctx))
    provs, names, labels = [], [], []
    for v in values:
        sfx = "" if len(values) == 1 else f"_d{int(round(v * 100)):03d}"
        provs.append(paint_once(ctx, j, out, seed=seed, render_size=(int(rw), int(rh)), target=(int(tw), int(th)),
                                crop="disabled", init=init, denoise=v, suffix=sfx, info=info))
        names.append(f"scene{sfx}.png")
        labels.append(f"denoise {v:.2f}" + (f" · layout {provs[-1]['layout_agreement']:.2f}" if "layout_agreement" in provs[-1] else ""))
    if len(values) > 1:
        _contact(out, names, labels, j.get("name"), (int(tw), int(th)))
    base = dict(provs[0])
    base.pop("denoise", None)
    write_prov(out, j, **base, denoise=values, outputs=names, sweep=provs if len(values) > 1 else None)
    return {"outputs": names, "seed": seed, "size": [int(tw), int(th)], "denoise": values, "commercial_ok": base["commercial_ok"]}


def upscale(job: dict, ctx: Context, out: Path) -> dict:
    client = _client(ctx)
    model = job.get("model") or _comfy(ctx, "upscale_model", "RealESRGAN_x4plus.pth")
    crop = str(job.get("crop", "center"))
    outputs = []
    for p in [ctx.resolve(x) for x in job["inputs"]]:
        if not p.exists():
            raise FileNotFoundError(f"input not found: {p}")
        with Image.open(p) as im:
            w, h = im.size
        if job.get("fit"):
            tw, th = [int(x) for x in job["fit"]]
        else:
            f = float(job.get("factor", 2))
            tw, th = int(round(w * f)), int(round(h * f))
        g = go.upscale_graph(client.upload_image(p, name=f"{job.get('id', 'job')}_{p.name}"), model, tw, th, crop)
        res = client.run_by_node(g)
        img = Image.open(io.BytesIO(res[go.save_node(g)][0])).convert("RGB")
        save_png(img, out / f"{p.stem}.png")
        outputs.append(f"{p.stem}.png")
    licences, ok = licence_chain(ctx, {"upscaler": model})
    write_prov(out, job, op="upscale", engine="comfyui", upscale_model=model, crop=crop, inputs=job["inputs"],
               licences=licences, upscaler_commercial_ok=ok, outputs=outputs,
               note="the source images' own provenance still applies — an upscale never makes a picture shippable")
    return {"outputs": outputs, "model": model}
