"""The same person, changed (BUILD 74): one job for a new pose, expression, age or style from a picture we already like.

    {"from": <picture>, "change": "pose" | "expression" | "age" | "restyle", "to": <words or a preset>,
     "keep": ["face", "clothes", "hair"], "method": "masked" | "guided" | "instructed", "region": <optional>}

Three ways to keep a person, one contract, so they can be compared and replaced:
  masked      only a region is repainted (the mouth; mouth and brows; the arms and what is behind them), found by the forge's
              own figure finder (the picture gate's), grown and feathered. The only method that can PROVE nothing else moved.
              SDXL (RealVisXL) inpainting through ComfyUI's core nodes.
  guided      the whole picture made again from the reference with a pose guide (an A-pose skeleton drawn here) through the
              SDXL union ControlNet (xinsir, Apache-2.0), the reference carried by image-to-image strength — there is no
              identity adapter on the disk, so likeness is the weakest here.
  instructed  the reference plus a sentence ("the same man, smiling slightly") through FLUX.2 [klein] 4B's own reference
              editing (Apache-2.0; ComfyUI's core ReferenceLatent node).
Every result is checked (`moved`): outside the region the difference from the source, mean and worst block; for guided and
instructed — which change the whole picture — the face measured by the plain measures the gate already has (proportions and
colour), and the report says that is all it is. A result that changed what it was told to keep is refused, and says where.
Pure numpy and Pillow; the graphs are built here, run by whoever starts the bake-off (never by a session).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

CHANGES = ("pose", "expression", "age", "restyle")
METHODS = ("masked", "guided", "instructed")
KEEPS = ("identity", "face", "hair", "clothes", "background", "pose", "expression", "style")
# what each change necessarily alters — asking to keep it is a contradiction
ALTERS = {"pose": {"pose"}, "expression": {"expression"}, "age": {"face", "hair"}, "restyle": {"style"}}
# which methods make sense for which change (masked can't make a person older; guided needs a pose)
FITS = {"pose": ("masked", "guided", "instructed"), "expression": ("masked", "instructed"),
        "age": ("instructed",), "restyle": ("guided", "instructed")}
REGION_FOR = {"expression": "mouth_brows", "pose": "arms"}
STYLE_START = "Fantastic Realism, Hyperrealistic, "        # William, 2026-11-17 13:23 — new pictures start with both
PRESETS = {
    "a_pose": "standing straight in an A-pose, arms held well away from the body at forty-five degrees, hands open, feet a "
              "shoulder's width apart, a full-length photograph, front view",
    "slight_smile": "the same person, a slight closed-mouth smile", "laugh": "the same person, laughing, eyes creased",
    "anger_held": "the same person, anger held in, jaw set, brows drawn down", "grief": "the same person, grief, eyes wet, mouth unsteady",
    "fear": "the same person, afraid, eyes wide", "neutral": "the same person, a calm neutral face, mouth closed",
}
DEFAULTS = {"grow_px": 10, "feather_px": 12, "block": 16, "outside_mean_max": 4.0, "outside_block_max": 18.0,
            "face_ratio_tol": 0.12, "face_colour_tol": 0.18}


class SamePersonError(ValueError):
    pass


def validate(job: dict) -> dict:
    """The contract, checked and filled in; raises SamePersonError with the reason in words."""
    if not job.get("from"):
        raise SamePersonError("say which picture to start from ('from')")
    ch = str(job.get("change") or "")
    if ch not in CHANGES:
        raise SamePersonError(f"'change' must be one of {', '.join(CHANGES)} (not {ch!r})")
    keep = [str(k) for k in job.get("keep") or ["identity", "face", "clothes", "hair"] if str(k)]
    bad = [k for k in keep if k not in KEEPS]
    if bad:
        raise SamePersonError(f"don't know how to keep {', '.join(bad)} (one of {', '.join(KEEPS)})")
    clash = sorted(set(keep) & ALTERS[ch])
    if clash:
        raise SamePersonError(f"a change of {ch} cannot keep its {', '.join(clash)} — take it out of 'keep'")
    m = str(job.get("method") or FITS[ch][0])
    if m not in METHODS:
        raise SamePersonError(f"'method' must be one of {', '.join(METHODS)}")
    if m not in FITS[ch]:
        raise SamePersonError(f"{m} can't change {ch} (it can: {', '.join(c for c, ms in FITS.items() if m in ms)})")
    to = str(job.get("to") or "")
    words = PRESETS.get(to, to)
    if not words:
        raise SamePersonError("say what to change it to ('to': words, or a preset: " + ", ".join(PRESETS) + ")")
    return {**job, "change": ch, "keep": keep, "method": m, "to": to, "words": words,
            "region": job.get("region") or (REGION_FOR.get(ch) if m == "masked" else None), "seed": int(job.get("seed") or 1001)}


# ------------------------------------------------------------------------------------------------ the region
def figure_mask(img, size: int | None = None) -> np.ndarray:
    """The figure in its picture (the gate's own finder: everything unlike the plain border)."""
    from .checks import picture_mask
    w, h = img.size
    m = picture_mask(img, max(w, h) if size is None else size)
    if m.shape != (h, w):
        from PIL import Image
        m = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
    return m


def region_mask(fig: np.ndarray, region: str) -> np.ndarray:
    """A region of a front-on figure: `mouth` (the head's lower middle), `mouth_brows` (with the brows), `face`, `head`,
    `arms` (beside the trunk at arm height, both the arms and the space they will move into)."""
    H, W = fig.shape
    rows = np.nonzero(fig.any(1))[0]
    if not len(rows):
        raise SamePersonError("no figure found in the picture")
    top, bot = int(rows.min()), int(rows.max())
    fh = bot - top
    hb = max(4, int(fh / 7.2))                         # the head, about one seventh of an adult's height
    yy = np.arange(H)[:, None]
    xx = np.arange(W)[None, :]
    head_rows = (yy >= top) & (yy < top + hb)
    hx = np.nonzero(fig[top:top + hb].any(0))[0]
    cx = (hx.min() + hx.max()) / 2 if len(hx) else W / 2
    hw = (hx.max() - hx.min()) if len(hx) else W * 0.1
    out = np.zeros((H, W), bool)
    if region in ("mouth", "mouth_brows"):
        out |= (yy >= top + 0.62 * hb) & (yy < top + 0.90 * hb) & (np.abs(xx - cx) <= 0.24 * hw)
        if region == "mouth_brows":
            out |= (yy >= top + 0.30 * hb) & (yy < top + 0.46 * hb) & (np.abs(xx - cx) <= 0.36 * hw)
    elif region == "face":
        out |= (yy >= top + 0.25 * hb) & (yy < top + hb) & (np.abs(xx - cx) <= 0.40 * hw)
    elif region == "head":
        out |= head_rows & (np.abs(xx - cx) <= 0.6 * hw)
    elif region == "arms":
        trunk_rows = (yy >= top + 1.3 * hb) & (yy < top + 4.2 * hb)
        mid = fig[top + int(2.6 * hb):top + int(3.2 * hb)]
        tx = np.nonzero(mid.sum(0) > 0.5 * mid.shape[0])[0] if mid.size else np.array([])
        if len(tx):
            # the trunk's own columns: the widest run of columns full through the waist
            t0, t1 = int(np.percentile(tx, 20)), int(np.percentile(tx, 80))
        else:
            t0, t1 = int(cx - hw), int(cx + hw)
        side = (xx < t0 - 2) | (xx > t1 + 2)
        out |= trunk_rows & side & (np.abs(xx - cx) <= 3.2 * hw)
    else:
        raise SamePersonError(f"no such region: {region}")
    return out


def grow_feather(mask: np.ndarray, grow: int, feather: int) -> np.ndarray:
    """The region grown by `grow` pixels and feathered over `feather` — a soft mask 0..1, never outside the picture."""
    m = mask.astype(np.float64)
    for _ in range(max(0, int(grow))):
        P = np.pad(m, 1)
        m = np.maximum.reduce([P[1:-1, 1:-1], P[:-2, 1:-1], P[2:, 1:-1], P[1:-1, :-2], P[1:-1, 2:]])
    if feather > 0:
        k = int(feather)
        for _ in range(2):
            for ax in (0, 1):
                P = np.pad(m, [(k, k) if a == ax else (0, 0) for a in range(2)], mode="edge")
                c = np.cumsum(P, axis=ax)
                c = np.concatenate([np.zeros_like(np.take(c, [0], axis=ax)), c], axis=ax)
                n = m.shape[ax]
                m = (np.take(c, np.arange(2 * k + 1, 2 * k + 1 + n), axis=ax) - np.take(c, np.arange(0, n), axis=ax)) / (2 * k + 1)
        m = np.maximum(m, mask.astype(np.float64))
    return np.clip(m, 0.0, 1.0)


def make_mask(img, region: str, s: dict | None = None) -> np.ndarray:
    s = {**DEFAULTS, **(s or {})}
    return grow_feather(region_mask(figure_mask(img), region), s["grow_px"], s["feather_px"])


# ------------------------------------------------------------------------------------------------ nothing else moved
def moved(src, res, region: np.ndarray | None, keep: list[str], method: str, s: dict | None = None) -> dict:
    """The check that nothing else moved: outside the region, the difference from the source (mean, and the worst block);
    the changed region's box. For guided and instructed, which remake the whole picture, the face is held to the plain
    measures the gate has (the head's proportion of the figure and its colour) — said to be all it is."""
    s = {**DEFAULTS, **(s or {})}
    from PIL import Image
    a = np.asarray(src.convert("RGB"), dtype=np.float64)
    b = np.asarray(res.convert("RGB").resize(src.size, Image.LANCZOS), dtype=np.float64)
    d = np.abs(a - b).mean(-1)
    out = {"method": method}
    changed = d > 12
    ys, xs = np.nonzero(changed)
    out["changed_box"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    problems = []
    if method == "masked":
        inside = region > 0.02 if region is not None else np.zeros_like(changed)
        outside = ~inside
        out["outside_mean"] = round(float(d[outside].mean()) if outside.any() else 0.0, 2)
        k = int(s["block"])
        H, W = d.shape
        worst, where = 0.0, None
        for y in range(0, H - k + 1, k):
            for x in range(0, W - k + 1, k):
                blk = outside[y:y + k, x:x + k]
                if blk.mean() < 0.9:
                    continue
                v = float(d[y:y + k, x:x + k][blk].mean())
                if v > worst:
                    worst, where = v, [x, y, x + k, y + k]
        out["outside_worst_block"] = round(worst, 2)
        out["worst_block_at"] = where
        if out["outside_mean"] > s["outside_mean_max"] or worst > s["outside_block_max"]:
            problems.append(f"changed outside the region it was given (worst at {where}, {worst:.0f} of 255)")
        out["measure"] = "pixels outside the region"
    else:
        fa, fb = figure_mask(src), figure_mask(Image.fromarray(b.astype(np.uint8)))
        from .gate import measure
        try:
            ma, mb = measure(src), measure(Image.fromarray(b.astype(np.uint8)))
            ra, rb = ma.get("head_ratio") or 0, mb.get("head_ratio") or 0
            out["head_ratio"] = [round(ra, 3), round(rb, 3)]
            if "face" in keep and ra and abs(rb - ra) / ra > s["face_ratio_tol"]:
                problems.append(f"the face's proportion moved ({ra:.3f} → {rb:.3f} of the height)")
        except Exception:  # noqa: BLE001
            out["head_ratio"] = None
        reg = region_mask(fa, "face") & fa
        regb = region_mask(fb, "face") & fb
        if reg.any() and regb.any():
            ca, cb = a[reg].mean(0), b[regb].mean(0)
            dc = float(np.linalg.norm(ca - cb) / max(np.linalg.norm(ca), 1.0))
            out["face_colour_shift"] = round(dc, 3)
            if "face" in keep and dc > s["face_colour_tol"]:
                problems.append(f"the face's colour moved ({dc * 100:.0f}%)")
        if "background" in keep:
            bg = ~fa & ~fb
            out["background_mean"] = round(float(d[bg].mean()) if bg.any() else 0.0, 2)
            if out["background_mean"] > s["outside_mean_max"] * 2:
                problems.append("the background changed")
        out["measure"] = ("the plain measures only — the face's proportion and colour; no face-likeness model with a "
                          "commercial licence is on the disk")
    out["ok"] = not problems
    out["problems"] = problems
    return out


def check_picture(src, res, region: np.ndarray | None, out_path: Path, note: str = "") -> Path:
    """Three across: the source, the result, what changed in magenta."""
    from PIL import Image, ImageDraw
    from .checks import _font
    font, plain = _font(13)
    a = np.asarray(src.convert("RGB"))
    b = np.asarray(res.convert("RGB").resize(src.size, Image.LANCZOS))
    d = np.abs(a.astype(int) - b.astype(int)).mean(-1) > 12
    c = (a * 0.55).astype(np.uint8)
    c[d] = (255, 0, 220)
    if region is not None:
        edge = (region > 0.5) ^ np.pad(region > 0.5, 1)[1:-1, 2:]
        c[edge] = (120, 255, 255)
    W, H = src.size
    S = Image.new("RGB", (W * 3, H + 24), (24, 24, 30))
    for i, arr in enumerate((a, b, c)):
        S.paste(Image.fromarray(arr), (i * W, 0))
    ImageDraw.Draw(S).text((6, H + 4), plain("the source · the result · what changed (magenta; the region's edge in cyan)  " + note),
                           fill=(230, 230, 230), font=font)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    S.save(out_path)
    return out_path


# ------------------------------------------------------------------------------------------------ the graphs (ComfyUI API)
def graph_masked(image_name: str, mask_name: str, words: str, negative: str, seed: int,
                 ckpt: str = "RealVisXL_V5.0_fp16.safetensors", steps: int = 30, cfg: float = 5.0, denoise: float = 1.0) -> dict:
    """SDXL inpainting of the region only: the source and its soft mask through InpaintModelConditioning with
    DifferentialDiffusion (core nodes), the result composited back over the source by the mask, so pixels outside it are
    the source's own."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "LoadImage", "inputs": {"image": mask_name}},
        "4": {"class_type": "ImageToMask", "inputs": {"image": ["3", 0], "channel": "red"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": words, "clip": ["1", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "7": {"class_type": "DifferentialDiffusion", "inputs": {"model": ["1", 0]}},
        "8": {"class_type": "InpaintModelConditioning", "inputs": {"positive": ["5", 0], "negative": ["6", 0], "vae": ["1", 2],
                                                                    "pixels": ["2", 0], "mask": ["4", 0], "noise_mask": True}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["7", 0], "positive": ["8", 0], "negative": ["8", 1], "latent_image": ["8", 2],
                                                    "seed": int(seed), "steps": int(steps), "cfg": float(cfg), "sampler_name": "dpmpp_2m",
                                                    "scheduler": "karras", "denoise": float(denoise)}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["2", 0], "source": ["10", 0], "x": 0, "y": 0,
                                                                "resize_source": False, "mask": ["4", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "forge_same_person"}},
    }


def graph_guided(image_name: str, pose_name: str, words: str, negative: str, seed: int,
                 ckpt: str = "RealVisXL_V5.0_fp16.safetensors", controlnet: str = "xinsir-union-sdxl-promax.safetensors",
                 strength: float = 0.85, denoise: float = 0.82, steps: int = 30, cfg: float = 5.0) -> dict:
    """The whole picture made again from the reference (image to image at `denoise`) with a pose guide: the A-pose
    skeleton (drawn by `pose_skeleton`) through the union ControlNet set to openpose."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "LoadImage", "inputs": {"image": pose_name}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": words, "clip": ["1", 1]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "6": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": controlnet}},
        "7": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["6", 0], "type": "openpose"}},
        "8": {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["4", 0], "negative": ["5", 0], "control_net": ["7", 0],
                                                                   "image": ["3", 0], "strength": float(strength),
                                                                   "start_percent": 0.0, "end_percent": 0.8, "vae": ["1", 2]}},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
        "10": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["8", 0], "negative": ["8", 1], "latent_image": ["9", 0],
                                                     "seed": int(seed), "steps": int(steps), "cfg": float(cfg), "sampler_name": "dpmpp_2m",
                                                     "scheduler": "karras", "denoise": float(denoise)}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "forge_same_person"}},
    }


def graph_instructed(image_name: str, words: str, seed: int, width: int, height: int, unet: str = "flux-2-klein-4b.safetensors",
                     text_encoder: str = "qwen_3_4b.safetensors", vae: str = "flux2-vae.safetensors") -> dict:
    """FLUX.2 [klein] 4B with the reference picture as a reference latent (ComfyUI's core ReferenceLatent) and the
    sentence — the template's own text-to-image graph with one reference added (distilled: 4 steps, cfg 1)."""
    from ..engines import flux2_graph
    g = flux2_graph.build(unet, words, "", seed, width, height, text_encoder=text_encoder, vae=vae,
                          filename_prefix="forge_same_person")
    g["40"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    g["41"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["40", 0], "upscale_method": "lanczos", "megapixels": 1.0,
                                                                   "resolution_steps": 1}}    # BUILD 84: required by this ComfyUI
    g["42"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["41", 0], "vae": ["3", 0]}}
    g["43"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["4", 0], "latent": ["42", 0]}}
    g["10"]["inputs"]["positive"] = ["43", 0]
    if g["5"]["class_type"] == "ConditioningZeroOut":
        g["5"]["inputs"]["conditioning"] = ["43", 0]
    return g


def pose_skeleton(width: int, height: int, deg: float = 45.0) -> "object":
    """An A-pose skeleton in the OpenPose colours (the guide for `guided`), standing in the middle of the frame."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (width, height), (0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, top = width / 2, height * 0.08
    H = height * 0.86
    hd = H / 7.5
    neck = (cx, top + hd * 1.1)
    hip = (cx, top + H * 0.52)
    sh = H * 0.13
    import math
    lsh, rsh = (cx - sh, neck[1] + hd * 0.2), (cx + sh, neck[1] + hd * 0.2)
    arm = H * 0.36
    a = math.radians(deg)
    lhand = (lsh[0] - arm * math.sin(a), lsh[1] + arm * math.cos(a))
    rhand = (rsh[0] + arm * math.sin(a), rsh[1] + arm * math.cos(a))
    lel = ((lsh[0] + lhand[0]) / 2, (lsh[1] + lhand[1]) / 2)
    rel = ((rsh[0] + rhand[0]) / 2, (rsh[1] + rhand[1]) / 2)
    lhip, rhip = (cx - H * 0.06, hip[1]), (cx + H * 0.06, hip[1])
    lknee, rknee = (cx - H * 0.08, hip[1] + H * 0.24), (cx + H * 0.08, hip[1] + H * 0.24)
    lft, rft = (cx - H * 0.1, top + H), (cx + H * 0.1, top + H)
    nose = (cx, top + hd * 0.55)
    w = max(3, int(height / 180))
    bones = [(neck, rsh, (255, 85, 0)), (rsh, rel, (255, 170, 0)), (rel, rhand, (255, 255, 0)), (neck, lsh, (170, 255, 0)),
             (lsh, lel, (85, 255, 0)), (lel, lhand, (0, 255, 0)), (neck, rhip, (0, 255, 85)), (rhip, rknee, (0, 255, 170)),
             (rknee, rft, (0, 255, 255)), (neck, lhip, (0, 170, 255)), (lhip, lknee, (0, 85, 255)), (lknee, lft, (0, 0, 255)),
             (neck, nose, (85, 0, 255))]
    for p, q, c in bones:
        d.line([p, q], fill=c, width=w * 2)
    for p in (neck, lsh, rsh, lel, rel, lhand, rhand, lhip, rhip, lknee, rknee, lft, rft, nose):
        d.ellipse([p[0] - w * 1.5, p[1] - w * 1.5, p[0] + w * 1.5, p[1] + w * 1.5], fill=(255, 0, 0))
    return im


# ------------------------------------------------------------------------------------------------ the bake-off (BUILD 74 part 4)
NEGATIVE = "cartoon, illustration, drawing, painting, anime, deformed hands, extra fingers, extra limbs, blurry, text, watermark"


def bakeoff(cfg: dict, cases: list[dict], out: Path, root: Path, game_root: Path | None = None, seeds=(1001, 2002),
            art_url: str | None = None, use_lock: bool = True, client=None) -> dict:
    """Every case through every method its change allows, two seeds; each result checked and drawn; one report a person
    can read (report.md) and its numbers (report.json). Run by same_person_bakeoff.bat — the person's to start."""
    import json
    import time
    from PIL import Image
    from .cardlock import CardLock
    from ..engines.comfy import ComfyClient
    url = art_url or ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"
    client = client or ComfyClient(url)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    lock = CardLock(cfg, "the same-person bake-off", art_url=url).acquire() if use_lock else None
    try:
        for c in cases:
            src_path = Path(c["from"])
            if not src_path.is_absolute():
                base = game_root if str(c["from"]).startswith("game:") and game_root else root
                src_path = Path(base) / str(c["from"]).replace("game:", "")
            if not src_path.exists():
                rows.append({"case": c["id"], "error": f"no picture at {src_path}"})
                continue
            src = Image.open(src_path).convert("RGB")
            for method in c.get("methods") or FITS[c["change"]]:
                try:
                    job = validate({**c, "method": method, "from": str(src_path)})
                except SamePersonError as e:
                    rows.append({"case": c["id"], "method": method, "error": str(e)})
                    continue
                for seed in seeds:
                    t0 = time.time()
                    name = f"{c['id']}__{method}__{seed}"
                    words = STYLE_START + job["words"] + (". " + c["also"] if c.get("also") else "")
                    region = None
                    up = client.upload_image(src_path, subfolder="forge_same_person", name=f"{name}__src.png")
                    if method == "masked":
                        region = make_mask(src, job["region"])
                        mp = out / f"{name}__mask.png"
                        Image.fromarray((region * 255).astype(np.uint8)).convert("RGB").save(mp)
                        mu = client.upload_image(mp, subfolder="forge_same_person", name=mp.name)
                        g = graph_masked(up, mu, words, NEGATIVE, seed)
                    elif method == "guided":
                        pp = out / f"{name}__pose.png"
                        pose_skeleton(*src.size).save(pp)
                        pu = client.upload_image(pp, subfolder="forge_same_person", name=pp.name)
                        g = graph_guided(up, pu, words, NEGATIVE, seed)
                    else:
                        w, h = src.size
                        k = (1024 * 1024 / (w * h)) ** 0.5
                        g = graph_instructed(up, words, seed, int(w * k) // 16 * 16, int(h * k) // 16 * 16)
                    try:
                        img = client.run(g)[0]
                    except Exception as e:  # noqa: BLE001 — one failure is written down; the rest go on
                        rows.append({"case": c["id"], "method": method, "seed": seed, "error": f"{type(e).__name__}: {e}"[:300]})
                        continue
                    rp = out / f"{name}.png"
                    rp.write_bytes(img)
                    res = Image.open(rp).convert("RGB")
                    chk = moved(src, res, region, job["keep"], method)
                    check_picture(src, res, region, out / f"{name}__check.png", f"{method}, seed {seed}: "
                                  + ("nothing else moved" if chk["ok"] else "; ".join(chk["problems"])))
                    rows.append({"case": c["id"], "change": c["change"], "method": method, "seed": seed, "ok": chk["ok"],
                                 "check": chk, "picture": rp.name, "check_picture": f"{name}__check.png",
                                 "seconds": round(time.time() - t0, 1), "words": words})
    finally:
        if lock is not None:
            lock.release()
    (out / "report.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    L = ["# The same person, changed — the bake-off", "", f"*{time.strftime('%Y-%m-%d %H:%M')}. Every case, every method its "
         "change allows, two seeds. A result that changed what it was told to keep is refused (the check picture says where). "
         "The winner a row by the check's numbers first, then by eye — Fable's, then William's.*", "",
         "| case | change | masked | guided | instructed |", "|---|---|---|---|---|"]
    for c in cases:
        cell = {}
        for m in METHODS:
            rs = [r for r in rows if r.get("case") == c["id"] and r.get("method") == m]
            cell[m] = (" / ".join(("✓" if r.get("ok") else ("✗ " + "; ".join(r["check"]["problems"])[:60] if r.get("check") else "error"))
                                  for r in rs) or "—")
        L.append(f"| {c['id']} | {c['change']} | {cell['masked']} | {cell['guided']} | {cell['instructed']} |")
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"rows": len(rows), "ok": sum(1 for r in rows if r.get("ok")), "out": str(out)}
