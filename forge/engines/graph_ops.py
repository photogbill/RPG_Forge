"""Graph surgery: add stages to any graph the builders make (sdxl_graph / flux1_graph / flux2_graph).

The builders stay simple — checkpoint, LoRAs, prompt, sampler, decode, save. Everything a painting needs on top
of that is a function here that takes the graph dict and splices nodes in:

    to_img2img(g, image, denoise, w, h)        start from a picture instead of noise (the greybox → painting bridge)
    add_controlnet(g, cn, image, strength)     pin the layout with a ControlNet (SDXL union: canny / depth …)
    add_freeu(g)                               FreeU_V2 — a free detail boost on SDXL UNets (core node)
    add_upscale(g, model, w, h, crop)          upscale model (RealESRGAN …) then an exact resize / cover-fit
    add_refine(g, denoise, w, h)               "hires fix": re-encode the bigger picture and repaint it lightly
    add_face_detailer(g, info, …)              Impact Pack FaceDetailer: find faces, repaint each at high res, paste back
    add_raw_save(g)                            a second SaveImage on the first decode, so raw.png comes back too

All are pure functions on dicts (tested without ComfyUI). New node ids start at 100 so they never collide with a
builder's ids (builders use 1–13 and 10/20+ for LoRA chains). The custom-node stage (face detailer) fills every input they do not set from ComfyUI's own /object_info, so a node-pack update that adds an input
does not break the graph.
"""
from __future__ import annotations

from typing import Any

EMPTY_LATENTS = ("EmptyLatentImage", "EmptySD3LatentImage", "EmptyFlux2LatentImage")
RAW_PREFIX = "forge_raw"


class GraphError(ValueError):
    pass


# ------------------------------------------------------------------ finding things
def new_id(g: dict, start: int = 100) -> str:
    n = start
    while str(n) in g:
        n += 1
    return str(n)


def add(g: dict, class_type: str, inputs: dict, start: int = 100) -> str:
    nid = new_id(g, start)
    g[nid] = {"class_type": class_type, "inputs": dict(inputs)}
    return nid


def nodes_of(g: dict, *class_types: str) -> list[str]:
    return [k for k, v in g.items() if v.get("class_type") in class_types]


def save_node(g: dict) -> str:
    """The main SaveImage (not the raw one)."""
    ids = [k for k in nodes_of(g, "SaveImage") if g[k]["inputs"].get("filename_prefix") != RAW_PREFIX]
    if not ids:
        raise GraphError("graph has no SaveImage node")
    return ids[0]


def final_image_ref(g: dict) -> list:
    return g[save_node(g)]["inputs"]["images"]


def set_final_image(g: dict, ref: list) -> None:
    g[save_node(g)]["inputs"]["images"] = ref


def first_decode(g: dict) -> str:
    ids = nodes_of(g, "VAEDecode")
    if not ids:
        raise GraphError("graph has no VAEDecode node")
    return sorted(ids, key=lambda k: (len(k), k))[0]


def vae_ref(g: dict) -> list:
    return g[first_decode(g)]["inputs"]["vae"]


def sampler_kind(g: dict) -> str:
    """'ksampler' (sdxl, flux1) or 'custom' (flux2: SamplerCustomAdvanced + CFGGuider)."""
    if nodes_of(g, "KSampler"):
        return "ksampler"
    if nodes_of(g, "SamplerCustomAdvanced"):
        return "custom"
    raise GraphError("graph has no KSampler or SamplerCustomAdvanced")


def main_sampler(g: dict) -> str:
    ids = nodes_of(g, "KSampler") or nodes_of(g, "SamplerCustomAdvanced")
    if not ids:
        raise GraphError("graph has no sampler")
    return sorted(ids, key=lambda k: (len(k), k))[0]


def cond_holder(g: dict) -> str:
    """The node that holds positive/negative: the KSampler, or flux2's CFGGuider."""
    if sampler_kind(g) == "ksampler":
        return main_sampler(g)
    guiders = nodes_of(g, "CFGGuider")
    if not guiders:
        raise GraphError("custom-sampler graph has no CFGGuider")
    return sorted(guiders, key=lambda k: (len(k), k))[0]


def model_holder(g: dict) -> str:
    return cond_holder(g)


def clip_ref(g: dict) -> list:
    for k in nodes_of(g, "CLIPTextEncode"):
        return g[k]["inputs"]["clip"]
    raise GraphError("graph has no CLIPTextEncode")


def rewire(g: dict, old: list, new: list, skip: set | None = None) -> int:
    n = 0
    for k, node in g.items():
        if skip and k in skip:
            continue
        for name, v in node["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and v == old:
                node["inputs"][name] = list(new)
                n += 1
    return n


def load_image(g: dict, image_name: str) -> list:
    """LoadImage of a file already in ComfyUI's input folder (the handler uploads it first)."""
    return [add(g, "LoadImage", {"image": image_name}), 0]


def _image(g: dict, image: str | list) -> list:
    return load_image(g, image) if isinstance(image, str) else image


# ------------------------------------------------------------------ stages
def to_img2img(g: dict, image: str | list, denoise: float, width: int, height: int, crop: str = "disabled") -> dict:
    """Replace the empty latent with the encoded picture; sample from part-way (denoise < 1)."""
    if not 0.0 < float(denoise) <= 1.0:
        raise GraphError(f"denoise must be in (0, 1], got {denoise}")
    empties = nodes_of(g, *EMPTY_LATENTS)
    if len(empties) != 1:
        raise GraphError(f"expected one empty-latent node, found {len(empties)}")
    eid = empties[0]
    batch = int(g[eid]["inputs"].get("batch_size", 1))
    img = _image(g, image)
    sc = add(g, "ImageScale", {"image": img, "upscale_method": "lanczos", "width": int(width), "height": int(height), "crop": crop})
    enc = add(g, "VAEEncode", {"pixels": [sc, 0], "vae": vae_ref(g)})
    latent = [enc, 0]
    if batch > 1:
        latent = [add(g, "RepeatLatentBatch", {"samples": latent, "amount": batch}), 0]
    rewire(g, [eid, 0], latent)
    del g[eid]
    s = main_sampler(g)
    if g[s]["class_type"] == "KSampler":
        g[s]["inputs"]["denoise"] = float(denoise)
    else:
        sig = g[s]["inputs"]["sigmas"]
        split = add(g, "SplitSigmasDenoise", {"sigmas": sig, "denoise": float(denoise)})
        g[s]["inputs"]["sigmas"] = [split, 1]       # low_sigmas: the tail of the schedule
    return g


def add_controlnet(g: dict, controlnet: str, image: str | list, strength: float = 0.6, start: float = 0.0,
                   end: float = 1.0, union_type: str | None = None) -> dict:
    """ControlNetLoader (→ SetUnionControlNetType) → ControlNetApplyAdvanced on the sampler's conditioning.
    union_type for the xinsir union model: 'canny/lineart/anime_lineart/mlsd', 'depth', … (ComfyUI's
    UNION_CONTROLNET_TYPES) or None to let the model guess."""
    h = cond_holder(g)
    pos, neg = g[h]["inputs"]["positive"], g[h]["inputs"]["negative"]
    cn = [add(g, "ControlNetLoader", {"control_net_name": controlnet}), 0]
    if union_type:
        cn = [add(g, "SetUnionControlNetType", {"control_net": cn, "type": union_type}), 0]
    ap = add(g, "ControlNetApplyAdvanced", {"positive": pos, "negative": neg, "control_net": cn, "image": _image(g, image),
                                            "strength": float(strength), "start_percent": float(start),
                                            "end_percent": float(end), "vae": vae_ref(g)})
    g[h]["inputs"]["positive"] = [ap, 0]
    g[h]["inputs"]["negative"] = [ap, 1]
    return g


def add_freeu(g: dict, b1: float = 1.3, b2: float = 1.4, s1: float = 0.9, s2: float = 0.2) -> dict:
    """FreeU_V2 on the UNet (SDXL defaults). UNet models only — FLUX is a transformer, so it is refused there."""
    if sampler_kind(g) != "ksampler" or nodes_of(g, "FluxGuidance"):
        raise GraphError("FreeU is for SDXL UNets; this graph is FLUX")
    h = model_holder(g)
    fu = add(g, "FreeU_V2", {"model": g[h]["inputs"]["model"], "b1": b1, "b2": b2, "s1": s1, "s2": s2})
    g[h]["inputs"]["model"] = [fu, 0]
    return g


def add_raw_save(g: dict) -> str:
    """Save the first decode as well (raw.png) — the render before any upscale / refine / face work."""
    return add(g, "SaveImage", {"filename_prefix": RAW_PREFIX, "images": [first_decode(g), 0]}, start=190)


def add_upscale(g: dict, model: str | None, width: int, height: int, crop: str = "center") -> dict:
    """[upscale model] → ImageScale to exactly width×height. crop 'center' = cover-fit (fills the frame, trims the
    long side); 'disabled' = stretch to the size (for repaints, where pixels must land where the init's did)."""
    ref = final_image_ref(g)
    if model:
        ld = add(g, "UpscaleModelLoader", {"model_name": model})
        ref = [add(g, "ImageUpscaleWithModel", {"upscale_model": [ld, 0], "image": ref}), 0]
    sc = add(g, "ImageScale", {"image": ref, "upscale_method": "lanczos", "width": int(width), "height": int(height), "crop": crop})
    set_final_image(g, [sc, 0])
    return g


def add_refine(g: dict, denoise: float = 0.3, steps: int | None = None, seed_offset: int = 1) -> dict:
    """Hires fix: VAEEncode the current final image → sample again from part-way → VAEDecode. Run after add_upscale
    so it repaints at the larger size; uses the same model and conditioning (and ControlNet, if one is on)."""
    if not 0.0 < float(denoise) < 1.0:
        raise GraphError(f"refine denoise must be in (0, 1), got {denoise}")
    vae = vae_ref(g)
    enc = add(g, "VAEEncode", {"pixels": final_image_ref(g), "vae": vae})
    s = main_sampler(g)
    if g[s]["class_type"] == "KSampler":
        ins = dict(g[s]["inputs"])
        ins.update({"latent_image": [enc, 0], "denoise": float(denoise), "seed": int(ins["seed"]) + seed_offset})
        if steps:
            ins["steps"] = int(steps)
        k2 = add(g, "KSampler", ins)
        out = [k2, 0]
    else:                                                        # flux2: its own noise + schedule at the new size
        base = g[s]["inputs"]
        noise = add(g, "RandomNoise", {"noise_seed": int(g[base["noise"][0]]["inputs"]["noise_seed"]) + seed_offset})
        sched_id = base["sigmas"][0]
        while g[sched_id]["class_type"] != "Flux2Scheduler":      # walk back past a SplitSigmasDenoise from img2img
            sched_id = g[sched_id]["inputs"]["sigmas"][0]
        sched_in = dict(g[sched_id]["inputs"])
        if steps:
            sched_in["steps"] = int(steps)
        # the new size: whatever the final ImageScale made
        sc = g[final_image_ref(g)[0]]
        if sc["class_type"] == "ImageScale":
            sched_in["width"], sched_in["height"] = sc["inputs"]["width"], sc["inputs"]["height"]
        sched = add(g, "Flux2Scheduler", sched_in)
        split = add(g, "SplitSigmasDenoise", {"sigmas": [sched, 0], "denoise": float(denoise)})
        k2 = add(g, "SamplerCustomAdvanced", {"noise": [noise, 0], "guider": base["guider"], "sampler": base["sampler"],
                                              "sigmas": [split, 1], "latent_image": [enc, 0]})
        out = [k2, 0]
    dec = add(g, "VAEDecode", {"samples": out, "vae": vae})
    set_final_image(g, [dec, 0])
    return g


# ------------------------------------------------------------------ custom-node stages (filled from /object_info)
def _spec_options(spec: Any) -> list | None:
    """A combo's choices in either object_info shape: [[a, b, …], {…}] or ["COMBO", {"options": [a, b, …]}]."""
    if isinstance(spec, (list, tuple)) and spec:
        if isinstance(spec[0], list):
            return spec[0]
        if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
            return spec[1].get("options")
    return None


def node_from_info(info: dict, class_type: str, given: dict) -> dict:
    """Inputs for a node: `given` first; every other *required* input from its default (or first combo choice).
    A required input with no default that is not given (a link like IMAGE) raises GraphError."""
    if class_type not in info:
        raise GraphError(f"ComfyUI has no '{class_type}' node — install its node pack (see doctor.bat)")
    spec = info[class_type].get("input", {})
    req, opt = spec.get("required", {}), spec.get("optional", {})
    out: dict = {}
    for name, s in req.items():
        if name in given:
            out[name] = given[name]
            continue
        choices = _spec_options(s)
        meta = s[1] if isinstance(s, (list, tuple)) and len(s) > 1 and isinstance(s[1], dict) else {}
        if "default" in meta:
            out[name] = meta["default"]
        elif choices:
            out[name] = choices[0]
        else:
            raise GraphError(f"{class_type}: required input '{name}' has no default and was not given")
    for name in opt:
        if name in given:
            out[name] = given[name]
    for name, v in given.items():
        if name not in out and name not in req and name not in opt:
            pass  # an input this version does not know: dropped rather than rejected by ComfyUI
    return out


def check_choice(info: dict, class_type: str, name: str, value: str) -> None:
    spec = info.get(class_type, {}).get("input", {})
    s = spec.get("required", {}).get(name) or spec.get("optional", {}).get(name)
    choices = _spec_options(s) if s is not None else None
    if choices is not None and value not in choices:
        shown = ", ".join(map(str, choices[:8])) or "(none)"
        raise GraphError(f"{class_type}.{name} = '{value}' is not installed; ComfyUI has: {shown}")


def add_face_detailer(g: dict, info: dict, detector: str = "bbox/face_yolov8m.pt", denoise: float = 0.4,
                      guide_size: int = 1024, max_size: int = 1024, steps: int | None = None, bbox_threshold: float = 0.5,
                      crop_factor: float = 3.0, feather: int = 5, cycle: int = 1) -> dict:
    """Impact Pack FaceDetailer on the current final image, using the graph's own model, CLIP, VAE and prompts —
    so repainted faces keep the picture's style. Needs ComfyUI-Impact-Pack + Impact-Subpack (install_comfy_faces.bat)
    and a face detector in models/ultralytics/bbox (pull_quality.bat)."""
    if sampler_kind(g) != "ksampler":
        raise GraphError("face_fix needs a KSampler graph (SDXL or FLUX.1), not FLUX.2 klein")
    check_choice(info, "UltralyticsDetectorProvider", "model_name", detector)
    det = add(g, "UltralyticsDetectorProvider", node_from_info(info, "UltralyticsDetectorProvider", {"model_name": detector}))
    s = g[main_sampler(g)]["inputs"]
    given = {"image": final_image_ref(g), "model": s["model"], "clip": clip_ref(g), "vae": vae_ref(g),
             "positive": s["positive"], "negative": s["negative"], "bbox_detector": [det, 0],
             "guide_size": int(guide_size), "max_size": int(max_size), "seed": int(s["seed"]) + 7,
             "steps": int(steps or s["steps"]), "cfg": float(s["cfg"]), "sampler_name": s["sampler_name"],
             "scheduler": s["scheduler"], "denoise": float(denoise), "feather": int(feather), "noise_mask": True,
             "force_inpaint": True, "bbox_threshold": float(bbox_threshold), "bbox_crop_factor": float(crop_factor),
             "drop_size": 10, "wildcard": "", "cycle": int(cycle), "guide_size_for": True}
    fd = add(g, "FaceDetailer", node_from_info(info, "FaceDetailer", given))
    set_final_image(g, [fd, 0])
    return g


# ------------------------------------------------------------------ standalone graphs
def upscale_graph(image_name: str, model: str | None, width: int, height: int, crop: str = "center") -> dict:
    """LoadImage → [upscale model] → ImageScale → SaveImage: the `upscale` job type's graph."""
    g: dict = {"1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
               "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "forge", "images": ["1", 0]}}}
    return add_upscale(g, model, width, height, crop)


def required_nodes(g: dict) -> set[str]:
    return {v["class_type"] for v in g.values()}


def fit_render_size(width: int, height: int, megapixels: float = 1.0, multiple: int = 64) -> tuple[int, int]:
    """A render size with the aspect of width×height at about `megapixels`, sides a multiple of `multiple`."""
    import math
    aspect = width / float(height)
    h = math.sqrt(megapixels * 1_000_000 / aspect)
    w = h * aspect
    rw = max(multiple, int(round(w / multiple)) * multiple)
    rh = max(multiple, int(round(h / multiple)) * multiple)
    return rw, rh
