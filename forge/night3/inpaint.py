"""Inpaint, and with it states of a room (Night 3, G4).

  inpaint_graph(...)   pure dict: the job's own checkpoint, LoadImage(crop) → ImageScale → VAEEncode →
                       SetLatentNoiseMask(LoadImageMask, red channel) → KSampler (denoise < 1) → VAEDecode → SaveImage.
                       Node names checked against the installed ComfyUI (nodes.py): VAEEncode, SetLatentNoiseMask,
                       LoadImageMask(image, channel). This route needs no inpaint model, so no new licence.
                       `method: "encode_for_inpaint"` uses VAEEncodeForInpaint instead (denoise 1.0; best with an
                       inpaint checkpoint).
  inpaint  (job)       init + mask (+ prompt for the masked part) → the repainted picture; outside the mask it is
                       bit-identical to the init (composited back after the sampler, never trusted to the sampler).
  scene_state (job)    a base painting + (mask, or two greyboxes → mask by forge.ops.state_mask) + a prompt for only
                       what changed → the state painting; when the base is a scene_kit folder, the kit's companions are
                       rebuilt on the state painting and composited into the base's companions only where the mask is.
Both repaint only the mask's padded bounding box, scaled to about 1 MP, so a 1080p (or larger) room never runs out of
memory and the new thing is painted at a size SDXL is good at.
"""
from __future__ import annotations
import io, json, shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..engines import graph_ops as go
from ..jobs.common import Context, write_prov, save_png, licence_chain
from ..jobs.gpu import _client, build_graph
from ..jobs import paint as _paint
from ..ops import state_mask as smk, sheet as sh, edges as ed

SLOT_FILES = ("scene_n.png", "scene_e.png", "scene_depth.png", "scene_over.png", "scene_back.png", "scene_mid_alpha.png")


def inpaint_graph(ctx: Context, job: dict, image_name: str, mask_name: str, w: int, h: int, seed: int,
                  denoise: float = 0.9, method: str = "noise_mask", grow: int = 0, edge_name: str | None = None,
                  controlnet: str | None = None, canny_strength: float = 0.5) -> tuple[dict, dict]:
    g, prov = build_graph(ctx, job, w, h, seed, count=1)
    empties = go.nodes_of(g, *go.EMPTY_LATENTS)
    if len(empties) != 1:
        raise go.GraphError(f"expected one empty-latent node, found {len(empties)}")
    eid = empties[0]
    img = go.load_image(g, image_name)
    sc = go.add(g, "ImageScale", {"image": img, "upscale_method": "lanczos", "width": int(w), "height": int(h), "crop": "disabled"})
    mk = go.add(g, "LoadImageMask", {"image": mask_name, "channel": "red"})
    if method == "encode_for_inpaint":
        enc = go.add(g, "VAEEncodeForInpaint", {"pixels": [sc, 0], "vae": go.vae_ref(g), "mask": [mk, 0], "grow_mask_by": int(grow)})
        latent = [enc, 0]
        denoise = 1.0
    else:
        enc = go.add(g, "VAEEncode", {"pixels": [sc, 0], "vae": go.vae_ref(g)})
        nm = go.add(g, "SetLatentNoiseMask", {"samples": [enc, 0], "mask": [mk, 0]})
        latent = [nm, 0]
    go.rewire(g, [eid, 0], latent)
    del g[eid]
    s = go.main_sampler(g)
    if g[s]["class_type"] != "KSampler":
        raise go.GraphError("inpaint is built for the SDXL (KSampler) graph")
    if not 0.0 < float(denoise) <= 1.0:
        raise go.GraphError(f"denoise must be in (0, 1], got {denoise}")
    g[s]["inputs"]["denoise"] = float(denoise)
    if edge_name and controlnet:
        go.add_controlnet(g, controlnet, edge_name, float(canny_strength), 0.0, 0.8, _paint.UNION_TYPES["canny"])
    if job.get("freeu"):
        go.add_freeu(g)
    return g, prov


def _work_size(w: int, h: int, mp: float = 1.0) -> tuple[int, int]:
    k = (mp * 1_000_000 / float(w * h)) ** 0.5
    k = min(k, 1.5)                                  # never blow a small crop up more than 1.5×
    return max(64, int(round(w * k / 8)) * 8), max(64, int(round(h * k / 8)) * 8)


def repaint_masked(ctx: Context, job: dict, base: Image.Image, mask: Image.Image, out: Path, seed: int,
                   edges: Image.Image | None = None, tag: str = "inpaint") -> tuple[Image.Image, dict, dict]:
    """Repaint the mask's padded bounding box; return (full-size composited picture, prov, info)."""
    client = _client(ctx)
    box = smk.bbox_for(mask, int(job.get("pad") or 96), int(job.get("min_side") or 768))
    crop, mcrop = base.crop(box).convert("RGB"), mask.crop(box)
    w, h = _work_size(crop.width, crop.height, float(job.get("megapixels") or 1.0))
    cp, mp = out / f"{tag}_crop.png", out / f"{tag}_crop_mask.png"
    save_png(crop, cp)
    save_png(Image.merge("RGB", [mcrop.resize((w, h), Image.LANCZOS)] * 3), mp)
    edge_name = None
    cn = None
    if edges is not None:
        ep = out / f"{tag}_crop_edges.png"
        save_png(edges.crop(box).resize((w, h), Image.LANCZOS), ep)
        edge_name = client.upload_image(ep, name=f"{job.get('id', 'job')}_{tag}_edges.png")
        cn = job.get("controlnet") or ctx.cfg.get("comfy", {}).get("controlnet_union", "xinsir-union-sdxl-promax.safetensors")
    g, prov = inpaint_graph(ctx, job, client.upload_image(cp, name=f"{job.get('id', 'job')}_{tag}_crop.png"),
                            client.upload_image(mp, name=f"{job.get('id', 'job')}_{tag}_mask.png"), w, h, seed,
                            float(job.get("denoise") if job.get("denoise") is not None else 0.9),
                            str(job.get("method") or "noise_mask"), int(job.get("grow_mask_by") or 0), edge_name, cn,
                            float(job.get("canny_strength") or 0.5))
    res = client.run_by_node(g)
    painted = Image.open(io.BytesIO(res[go.save_node(g)][0])).convert("RGB").resize(crop.size, Image.LANCZOS)
    full = base.convert("RGB").copy()
    full.paste(painted, box[:2])
    result = smk.composite(base.convert("RGB"), full, mask)          # bit-identical outside the mask
    parts = {"checkpoint": prov["checkpoint"]}
    for i, lo in enumerate(prov.get("loras") or []):
        parts[f"lora{i + 1}"] = lo["name"]
    if cn:
        parts["controlnet"] = cn
    return result, prov, {"box": list(box), "work_size": [w, h], "parts": parts, "nodes": sorted(go.required_nodes(g))}


def _contact(out: Path, base: Image.Image, mask: Image.Image, result: Image.Image, name: str | None) -> float:
    diff, _ = smk.difference(base, result)
    outside = np.asarray(mask.convert("L")) == 0
    d = np.abs(np.asarray(base.convert("RGB"), dtype=np.int16) - np.asarray(result.convert("RGB"), dtype=np.int16)).max(axis=2)
    outside_max = float(d[outside].max()) if outside.any() else 0.0
    cell = (480, max(120, int(480 * base.height / base.width)))
    save_png(sh.contact_sheet([base, mask.convert("RGB"), result, diff],
                              ["base", "mask", "result", f"difference ×4 — outside the mask: max {outside_max:.0f}"],
                              cols=2, cell=cell, title=name), out / "contact.png")
    save_png(diff, out / "difference.png")
    return outside_max


def _load_mask(ctx: Context, j: dict, size) -> Image.Image:
    m = Image.open(ctx.resolve(j["mask"])).convert("L")
    if m.size != tuple(size):
        raise ValueError(f"mask is {m.size}, the picture is {tuple(size)} — they must match")
    if j.get("mask_grow") or j.get("mask_feather"):
        m = smk.grow_feather(m.point(lambda v: 255 if v > 127 else 0), int(j.get("mask_grow") or 0), float(j.get("mask_feather") or 0))
    return m


def inpaint(job: dict, ctx: Context, out: Path) -> dict:
    out = Path(out)
    j = _paint._pick_models(ctx, job)
    src = ctx.resolve(j["init"])
    base = Image.open(src).convert("RGB")
    mask = _load_mask(ctx, j, base.size)
    seed = _paint._seed(j)
    result, prov, info = repaint_masked(ctx, j, base, mask, out, seed)
    save_png(result, out / "inpaint.png")
    save_png(mask, out / "mask.png")
    outside = _contact(out, base, mask, result, j.get("name"))
    licences, ok = licence_chain(ctx, info["parts"])
    write_prov(out, j, op="inpaint", seed=seed, init=str(src), box=info["box"], work_size=info["work_size"],
               outside_mask_max_diff=outside, licences=licences, commercial_ok=ok, nodes=info["nodes"],
               note="the init picture's own provenance still applies")
    return {"outputs": ["inpaint.png", "mask.png", "contact.png", "difference.png"], "outside_mask_max_diff": outside,
            "seed": seed, "commercial_ok": ok}


def _base_paths(ctx: Context, j: dict) -> tuple[Path, Path | None]:
    """`base` may be a painting file or a scene_kit output folder (then its scene.png and its companions)."""
    p = ctx.resolve(j["base"])
    if p.is_dir():
        return p / "scene.png", p
    return p, (p.parent if (p.parent / "scene_n.png").exists() else None)


def rebuild_companions(ctx: Context, state_png: Path, kit_dir: Path, mask: Image.Image, out: Path, job: dict) -> list[str]:
    """Run the kit's companion steps on the state painting, then keep the base's companions everywhere outside the
    mask (bit-identical there) — so a state differs from its base only where the room changed."""
    from ..jobs import scene as sc, cpu
    made = []
    work = out / "_companions"
    work.mkdir(exist_ok=True)
    dd = work / "depth"; dd.mkdir(exist_ok=True)
    r = sc.depth_map({"id": f"{job.get('id', 'job')}_d", "inputs": [str(state_png)]}, ctx, dd)
    depth = dd / r["outputs"][0]
    nd = work / "normals"; nd.mkdir(exist_ok=True)
    rn = sc.normal_map({"inputs": [str(state_png)], "source": "depth", "depth": [str(depth)], "detail": 0.35,
                        "preview": False}, ctx, nd)
    ed_ = work / "glow"; ed_.mkdir(exist_ok=True)
    re_ = cpu.emissive_mask({"inputs": [str(state_png)]}, ctx, ed_)
    ld = work / "layers"; ld.mkdir(exist_ok=True)
    cuts = "auto"
    lj = kit_dir / "layers.json"
    if lj.exists():
        try:
            cuts = json.loads(lj.read_text(encoding="utf-8")).get("cuts") or "auto"
        except ValueError:
            pass
    sc.scene_layers({"inputs": [str(state_png)], "depth": [str(depth)], "cuts": cuts}, ctx, ld)
    fresh = {"scene_depth.png": depth, "scene_n.png": nd / rn["outputs"][0], "scene_e.png": ed_ / re_["outputs"][0],
             "scene_over.png": ld / f"{state_png.stem}_over.png", "scene_back.png": ld / f"{state_png.stem}_back.png",
             "scene_mid_alpha.png": ld / f"{state_png.stem}_mid_alpha.png"}
    for name, new in fresh.items():
        old = kit_dir / name
        if not new.exists():
            continue
        if not old.exists():
            shutil.copyfile(new, out / name)
            made.append(name)
            continue
        o, n = Image.open(old), Image.open(new)
        m = mask
        if o.size != mask.size:                       # _back is wider by the overscan on each side
            pad = (o.size[0] - mask.size[0]) // 2
            m = Image.new("L", o.size, 0)
            m.paste(mask, (pad, (o.size[1] - mask.size[1]) // 2))
        if n.size != o.size:
            n = n.resize(o.size, Image.LANCZOS)
        if o.mode in ("I;16", "I"):
            a = np.asarray(o).astype(np.float64)
            b = np.asarray(n.convert(o.mode) if n.mode != o.mode else n).astype(np.float64)
            mm = np.asarray(m).astype(np.float64) / 255.0
            res = np.round(a * (1 - mm) + b * mm)
            res[mm == 0] = a[mm == 0]
            Image.fromarray(res.astype(np.uint16)).save(out / name)
        else:
            smk.composite(o, n.convert(o.mode), m).save(out / name)
        made.append(name)
    return made


def scene_state(job: dict, ctx: Context, out: Path) -> dict:
    out = Path(out)
    j = _paint._pick_models(ctx, job)
    base_png, kit_dir = _base_paths(ctx, j)
    if not base_png.exists():
        raise FileNotFoundError(f"base painting not found: {base_png}")
    base = Image.open(base_png).convert("RGB")
    report = {}
    edges = None
    if j.get("mask"):
        mask = _load_mask(ctx, j, base.size)
    else:
        if not (j.get("greybox_base") and j.get("greybox_state")):
            raise ValueError("scene_state needs `mask`, or `greybox_base` + `greybox_state` (two greybox renders of the map)")
        gb = Image.open(ctx.resolve(j["greybox_base"])).convert("RGB")
        gs = Image.open(ctx.resolve(j["greybox_state"])).convert("RGB")
        if gb.size != base.size:
            gb, gs = gb.resize(base.size, Image.NEAREST), gs.resize(base.size, Image.NEAREST)
        mask, _binary, _share, report = smk.state_mask(gb, gs, int(j.get("threshold") or 12), int(j.get("grow") or 24),
                                                       float(j.get("feather") or 12.0), float(j.get("max_share") or smk.MAX_SHARE))
        if j.get("control", True):
            edges = ed.canny(gs)
    seed = _paint._seed(j)
    result, prov, info = repaint_masked(ctx, j, base, mask, out, seed, edges=edges, tag="state")
    save_png(result, out / "scene.png")
    save_png(mask, out / "mask.png")
    outside = _contact(out, base, mask, result, j.get("name"))
    made = []
    if kit_dir is not None and j.get("companions", True):
        made = rebuild_companions(ctx, out / "scene.png", kit_dir, mask, out, j)
        info["parts"]["depth_model"] = "depth_anything_v2_vits.pth"
    if kit_dir is not None:
        src_prov = kit_dir / "prov.json"
        if src_prov.exists():
            try:
                for rec in json.loads(src_prov.read_text(encoding="utf-8")).get("licences") or []:
                    info["parts"].setdefault(f"base_{rec.get('role')}", rec.get("file"))
            except ValueError:
                pass
    licences, ok = licence_chain(ctx, info["parts"])
    write_prov(out, j, op="scene_state", seed=seed, base=str(base_png), kit=str(kit_dir) if kit_dir else None,
               mask_report=report, box=info["box"], work_size=info["work_size"], outside_mask_max_diff=outside,
               companions=made, licences=licences, commercial_ok=ok, nodes=info["nodes"])
    return {"outputs": ["scene.png", "mask.png", "contact.png", "difference.png"] + made,
            "outside_mask_max_diff": outside, "companions": made, "seed": seed, "commercial_ok": ok}


from .specs import INPAINT as INPAINT_SPEC, SCENE_STATE as STATE_SPEC  # noqa: E402
