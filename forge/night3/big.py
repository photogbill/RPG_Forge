"""`scene_big` — paint a scene larger than one diffusion pass (Night 3, G3).

Stages (each writes its picture, so a failure leaves something to look at):
  1  small.png     the whole scene at ~1 MP from the whole greybox (`init`) or the prompt — one composition, one light.
                   Skipped when `source` names an existing painting (that is the GPU proof's path).
  2  upscaled.png  upscale model → the next size (stretch, so pixels stay where the greybox put them), never more
                   than `max_step` (default 2×) per climb; stages 2+3 repeat until `target` (a 4.4× street = 3 climbs).
  3  tiles/        every tile an img2img repaint of its crop at low `denoise`, ControlNet **tile** on the crop itself
                   (the content cannot wander) and **canny** from the greybox crop when there is a greybox; all tiles
                   share prompt, seed and sampler. Merged with a feathered blend across every overlap.
  4  seams.json + seam_sheet.jpg   the colour/gradient disagreement in each overlap; worst seams outlined.
Outputs: scene.png (the painting at `target`), small.png, upscaled.png, tiles/tile_NN.png, seams.json,
seam_sheet.jpg, contact.png, prov.json. It calls the existing paint and graph code as a library; it changes none of it.
"""
from __future__ import annotations
import io, json
from pathlib import Path

from PIL import Image

from ..engines import graph_ops as go
from ..jobs.common import Context, write_prov, save_png, licence_chain
from ..jobs.gpu import _client, build_graph
from ..jobs import paint as _paint
from ..ops import bigtiles as bt, edges as ed, sheet as sh

DEFAULT_TILE = (1344, 768)


def _comfy(ctx: Context, key: str, default=None):
    return ctx.cfg.get("comfy", {}).get(key, default)


def climb_sizes(start, target, max_step: float = 2.0) -> list[tuple[int, int]]:
    """The sizes to climb through from `start` to `target`, each step ≤ max_step× and all steps the same ratio;
    sides rounded to a multiple of 8, the last exactly the target."""
    import math
    sw, sh_ = start
    tw, th = target
    r = max(tw / sw, th / sh_)
    n = max(1, math.ceil(math.log(r) / math.log(max(1.05, max_step)) - 1e-9))
    out = []
    for i in range(1, n + 1):
        k = (i / n)
        w = tw if i == n else int(round(sw * (tw / sw) ** k / 8) * 8)
        h = th if i == n else int(round(sh_ * (th / sh_) ** k / 8) * 8)
        out.append((w, h))
    return out


def tile_graph(ctx: Context, job: dict, tile_name: str, edge_name: str | None, w: int, h: int, seed: int,
               denoise: float, tile_strength: float, canny_strength: float, controlnet: str) -> tuple[dict, dict]:
    """One tile's graph: the job's model, img2img from the tile crop, ControlNet tile (+ canny when a greybox crop
    is given). Pure dict surgery on build_graph's output — tested without a GPU."""
    g, prov = build_graph(ctx, job, w, h, seed, count=1)
    go.to_img2img(g, tile_name, float(denoise), w, h, crop="disabled")
    go.add_controlnet(g, controlnet, tile_name, float(tile_strength), 0.0, 1.0, _paint.UNION_TYPES["tile"])
    if edge_name:
        go.add_controlnet(g, controlnet, edge_name, float(canny_strength), 0.0, 0.8, _paint.UNION_TYPES["canny"])
    if job.get("freeu"):
        go.add_freeu(g)
    return g, prov


def _run_image(client, g: dict) -> Image.Image:
    res = client.run_by_node(g)
    return Image.open(io.BytesIO(res[go.save_node(g)][0])).convert("RGB")


def scene_big(job: dict, ctx: Context, out: Path) -> dict:
    out = Path(out)
    j = _paint._pick_models(ctx, job)
    client = _client(ctx)
    tw, th = [int(x) for x in j["target"]]
    seed = _paint._seed(j)
    tile = tuple(int(x) for x in (j.get("tile") or DEFAULT_TILE))
    overlap = int(j.get("overlap") or 128)
    denoise = float(j.get("denoise") if j.get("denoise") is not None else 0.3)
    up_model = (j.get("upscale_model") or _comfy(ctx, "upscale_model", "RealESRGAN_x4plus.pth"))
    controlnet = (j.get("controlnet") or _comfy(ctx, "controlnet_union", "xinsir-union-sdxl-promax.safetensors"))
    notes: list[str] = []
    parts = {}
    greybox = ctx.resolve(j["init"]) if j.get("init") else None
    if greybox is not None and not greybox.exists():
        raise FileNotFoundError(f"greybox (init) not found: {greybox}")
    source = ctx.resolve(j["source"]) if j.get("source") else None
    if source is not None and not source.exists():
        raise FileNotFoundError(f"source painting not found: {source}")

    # ---- stage 1: the whole scene, small
    if source is not None:
        small_path = source
        notes.append(f"stage 1 skipped: started from an existing painting ({source.name}) — its own prov.json still applies")
        src_prov = source.parent / "prov.json"
        if src_prov.exists():
            try:
                for rec in json.loads(src_prov.read_text(encoding="utf-8")).get("licences") or []:
                    parts.setdefault(f"source_{rec.get('role')}", rec.get("file"))
            except ValueError:
                notes.append("source prov.json unreadable — its models are not in this chain")
        else:
            notes.append("source has no prov.json next to it — its models are unknown, so this cannot be approved")
            parts["source"] = source.name
    else:
        rw, rh = [int(x) for x in (j.get("size") or go.fit_render_size(tw, th, float(j.get("megapixels") or 1.0)))]
        sj = dict(j, upscale=False, refine=False, face_fix=False)
        if greybox is not None and "control" not in j:
            sj["control"] = {"type": "canny", "strength": 0.5}
        sp = _paint.paint_once(ctx, sj, out, seed=seed, render_size=(rw, rh), target=(rw, rh), crop="disabled",
                               init=greybox, denoise=float(j.get("init_denoise") or 0.65) if greybox is not None else None,
                               suffix="_small")
        (out / "scene_small.png").replace(out / "small.png")
        if (out / "raw_small.png").exists():
            (out / "raw_small.png").unlink()
        small_path = out / "small.png"
        for rec in sp.get("licences") or []:
            parts[f"small_{rec['role']}"] = rec["file"]

    # ---- stages 2+3, repeated: never more than `max_step` (default 2×) per climb — a single 4-6× upscale goes soft
    # (William, 2026-11-09: "6X disappoints usually"). Each climb: upscale model → exact size (stretched, so the
    # greybox's pixels land where they were) → tiled img2img refine that paints real detail back in.
    parts["upscaler"] = up_model
    with Image.open(small_path) as im:
        cur = im.convert("RGB").copy()
    sizes = climb_sizes(cur.size, (tw, th), float(j.get("max_step") or 2.0))
    tdir = out / "tiles"
    tdir.mkdir(exist_ok=True)
    rects, done, big = [], [], cur
    for p_i, (sw, shh) in enumerate(sizes, 1):
        save_png(cur, tdir / f"pass{p_i}_from.png")
        g = go.upscale_graph(client.upload_image(tdir / f"pass{p_i}_from.png", name=f"{j.get('id', 'job')}_pass{p_i}.png"),
                             up_model, sw, shh, "disabled")
        big = _run_image(client, g)
        if big.size != (sw, shh):
            big = big.resize((sw, shh), Image.LANCZOS)
        if p_i == len(sizes):
            save_png(big, out / "upscaled.png")
        grey_big = Image.open(greybox).convert("RGB").resize((sw, shh), Image.LANCZOS) if greybox is not None else None
        rects = bt.plan((sw, shh), tile, overlap)
        done = []
        for n, (crop, r) in enumerate(zip(bt.split(big, rects), rects)):
            tag = f"p{p_i}_{n:02d}"
            cp = tdir / f"in_{tag}.png"
            save_png(crop, cp)
            edge_name = None
            if grey_big is not None:
                ep = tdir / f"edges_{tag}.png"
                save_png(ed.canny(grey_big.crop(r)), ep)
                edge_name = client.upload_image(ep, name=f"{j.get('id', 'job')}_edges_{tag}.png")
            w, h = r[2] - r[0], r[3] - r[1]
            tg, prov = tile_graph(ctx, j, client.upload_image(cp, name=f"{j.get('id', 'job')}_tile_{tag}.png"), edge_name,
                                  w, h, seed, denoise, float(j.get("tile_strength") or 0.6),
                                  float(j.get("canny_strength") or 0.4), controlnet)
            t = _run_image(client, tg)
            if t.size != (w, h):
                t = t.resize((w, h), Image.LANCZOS)
            save_png(t, tdir / f"tile_{tag}.png")
            done.append(t)
            if "checkpoint" not in parts:
                parts["checkpoint"] = prov["checkpoint"]
                for i, lo in enumerate(prov.get("loras") or []):
                    parts[f"lora{i + 1}"] = lo["name"]
                parts["controlnet"] = controlnet
        cur = bt.merge(done, rects, (sw, shh))
        notes.append(f"climb {p_i}: {big.width}x{big.height}, {len(rects)} tiles")
    final = cur
    save_png(final, out / "scene.png")

    # ---- stage 4: seams
    sl = bt.seams(done, rects)
    worst = max((s["score"] for s in sl), default=0.0)
    (out / "seams.json").write_text(json.dumps({"tile": list(tile), "overlap": overlap, "rects": rects, "seams": sl,
                                                "worst": worst}, indent=1), encoding="utf-8")
    bt.seam_sheet(final, rects, sl).save(out / "seam_sheet.jpg", "JPEG", quality=88)
    cell = (480, max(120, int(480 * th / tw)))
    pics = [Image.open(small_path), big, final, Image.open(out / "seam_sheet.jpg")]
    labels = ["1 small" + (" (source)" if source else ""), "2 upscaled", "3 tiled refine (scene.png)",
              f"4 seams — worst {worst:.1f}"]
    save_png(sh.contact_sheet(pics, labels, cols=2, cell=cell, title=j.get("name")), out / "contact.png")
    licences, ok = licence_chain(ctx, parts)
    write_prov(out, j, op="scene_big", seed=seed, climbs=[list(x) for x in sizes], target=[tw, th], tile=list(tile), overlap=overlap, denoise=denoise,
               tiles=len(rects), grid=list(bt.grid_shape(rects)), init=str(greybox) if greybox else None,
               source=str(source) if source else None, upscale_model=up_model, controlnet=controlnet,
               seam_worst=worst, licences=licences, commercial_ok=ok, notes=notes,
               outputs=["scene.png", "small.png", "upscaled.png", "seams.json", "seam_sheet.jpg", "contact.png"])
    return {"outputs": ["scene.png", "contact.png", "seam_sheet.jpg"], "size": [tw, th], "tiles": len(rects), "climbs": len(sizes),
            "seam_worst": worst, "seed": seed, "commercial_ok": ok}


from .specs import SCENE_BIG as SPEC  # noqa: E402 (kept here for older callers)
