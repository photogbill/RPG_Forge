"""Job types and validation.

A job is a JSON object:
    {"type": "scene_card", "name": "gate_law_01_ribbon", ...fields...}

`type` picks the handler (forge/jobs/<type>.py). `name` becomes part of the job id and the output
folder. Every type declares which fields it requires, which are optional (with defaults), and whether
it needs the GPU worker (`gpu`) or runs anywhere (`cpu`). docs/JOB_TYPES.md is generated from this
table (`python -m forge docs`), so the table is the single source of truth.
"""
from __future__ import annotations

JOB_TYPES: dict[str, dict] = {
    # ------------------------------------------------------------------ GPU (diffusion via ComfyUI)
    "scene_card": {
        "needs": "gpu",
        "doc": "A painted scene card (a cutscene vignette, a location card, a record sleeve): text → image via "
               "ComfyUI → downscale to card_size → optional palette snap. Output: card.png, raw.png, prov.json.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "card_size": None, "render_scale": None, "palette": None,
                     "snap": True, "style_prefix": None, "workflow": None, "checkpoint": None, "steps": 28,
                     "cfg": 6.0, "game": None, "variants": 1},
    },
    "concept": {
        "needs": "gpu",
        "doc": "A location concept painting — the single image a kit is derived from (the gas station at dusk, "
               "the inn's common room). Rendered large; no palette snap. Output: concept.png, prov.json.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "size": [1536, 864], "style_prefix": None, "workflow": None,
                     "checkpoint": None, "steps": 30, "cfg": 6.0, "game": None, "variants": 2},
    },
    "portrait": {
        "needs": "gpu",
        "doc": "A seed-locked portrait set: one seed, one base prompt, a list of expression/stance phrases; each "
               "phrase renders once with the same seed so the face holds. Output: <expr>.png ×N + contact sheet.",
        "required": ["prompt", "expressions"],
        "optional": {"negative": None, "seed": 12345, "size": [768, 768], "out_size": [128, 128], "palette": None,
                     "snap": False, "style_prefix": None, "workflow": None, "checkpoint": None, "steps": 30,
                     "cfg": 6.0, "game": None},
    },
    "prop": {
        "needs": "gpu",
        "doc": "A prop sprite (gas pump, bed, counter): rendered on a flat key colour → background removed → "
               "trimmed → downscaled to target_h → palette snap. Output: prop.png (RGBA), raw.png, prov.json.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "size": [768, 768], "target_h": 64, "key_color": "#ff00ff",
                     "palette": None, "snap": True, "style_prefix": None, "workflow": None, "checkpoint": None,
                     "steps": 28, "cfg": 6.0, "game": None, "variants": 3},
    },
    "tile_texture": {
        "needs": "gpu",
        "doc": "A tileable surface (asphalt, siding, grass): rendered → made seamless → downscaled to tile_size → "
               "palette snap → seam score + N jittered variants. Output: tile.png, variants.png, raw.png, prov.json.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "size": [512, 512], "tile_size": 32, "palette": None,
                     "snap": True, "style_prefix": None, "workflow": None, "checkpoint": None, "steps": 28,
                     "cfg": 6.0, "game": None, "variants": 4},
    },
    "render": {
        "needs": "gpu",
        "doc": "A raw render with any checkpoint + LoRA chain, no post-processing — the bake-off's unit and "
               "the thing to reach for when you want to see what a model does. `graph` picks the engine graph: "
               "'sdxl' (default; checkpoint + LoraLoader chain), 'flux2_klein' (FLUX.2 [klein] 4B: `checkpoint` is the "
               "diffusion-model file, `text_encoder`/`vae` default from forge.json comfy.flux2, `distilled` auto from the "
               "name, `cfg`/`steps` default 5/20 base or 1/4 distilled) or 'flux1' (FLUX.1 dev/schnell + fine-tunes: "
               "`clip_l`/`t5`/`vae`/`guidance` from comfy.flux1; `all_in_one` for a checkpoint with CLIP+VAE baked in; "
               "cfg is always 1). Output: render.png (+ _2…), prov.json.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "size": [1024, 1024], "steps": 25, "cfg": 6.0, "sampler": "dpmpp_2m",
                     "scheduler": "karras", "checkpoint": None, "loras": [], "clip_skip": 0, "count": 1,
                     "style_prefix": "", "game": None, "meta": {},
                     "graph": "sdxl", "text_encoder": None, "vae": None, "clip_l": None, "t5": None,
                     "guidance": None, "distilled": None, "all_in_one": False},
    },
    "scene_paint": {
        "needs": "gpu",
        "doc": "A painted scene background at game resolution (roadmap F1): render at `size` (default 1344×768) → "
               "upscale model (`upscale`, default forge.json comfy.upscale_model = RealESRGAN_x4plus, BSD-3) → cover-fit "
               "to `target` (default the game's `scene_size` or 1920×1080; 2560×1080 for a scrolling street) → `refine` "
               "(hires-fix repaint at the final size, denoise 0.3; false to skip) → `face_fix` (Impact Pack FaceDetailer; "
               "true or {denoise, threshold, guide_size}). Optional `init` + `denoise` start from a picture (img2img), "
               "`control` {type: canny|depth|lineart|tile…, image, strength 0.6, start, end} pins the layout with the SDXL "
               "union ControlNet (canny is computed on the CPU), `freeu` true adds FreeU_V2 (SDXL). Any `graph` "
               "(sdxl · flux1 · flux2_klein). Output: scene.png, raw.png, prov.json (+ control.png, control_overlay.png, "
               "contact.png for variants). prov.json lists every model that touched the pixels and `commercial_ok`.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "size": [1344, 768], "target": None, "crop": "center", "init": None,
                     "denoise": None, "control": None, "upscale": True, "refine": True, "face_fix": False, "freeu": False,
                     "graph": "sdxl", "checkpoint": None, "loras": None, "steps": None, "cfg": None, "sampler": None,
                     "scheduler": None, "style_prefix": None, "game": None, "variants": 1},
    },
    "repaint": {
        "needs": "gpu",
        "doc": "Image-to-image from a greybox (roadmap F2): `init` is required and the painting comes back at the "
               "init's exact pixel size (stretched, never cropped) so walk polygons, doors and spawns stay valid. "
               "`denoise` (default 0.55) may be a list, e.g. [0.45, 0.55, 0.65] — one painting per value, same seed, on "
               "one contact sheet labelled with denoise and a layout-agreement score. Takes `control`, `refine`, "
               "`face_fix`, `freeu`, `upscale` like scene_paint. Output: scene[_dNNN].png, raw*.png, contact.png, prov.json.",
        "required": ["prompt", "init"],
        "optional": {"negative": None, "seed": -1, "denoise": 0.55, "size": None, "megapixels": 1.0, "target": None,
                     "control": None, "upscale": True, "refine": True, "face_fix": False, "freeu": False, "graph": "sdxl",
                     "checkpoint": None, "loras": None, "steps": None, "cfg": None, "sampler": None, "scheduler": None,
                     "style_prefix": None, "game": None},
    },
    "upscale": {
        "needs": "gpu",
        "doc": "Upscale images with an upscale model (default comfy.upscale_model) to an exact `fit` [w, h] (crop "
               "'center' = cover-fit, 'disabled' = stretch) or by `factor` (default 2). Output: <name>.png per input. "
               "The inputs' own provenance still decides whether they can ship.",
        "required": ["inputs"],
        "optional": {"model": None, "fit": None, "factor": 2, "crop": "center"},
    },
    "icon": {
        "needs": "gpu",
        "doc": "An inventory icon (roadmap F6): `prop` on a square canvas — render on a key colour → background "
               "removed → trimmed → centred on a transparent `canvas` (256 default; 512 for hi-res) with `padding` → "
               "optional palette snap. Default checkpoint/LoRA from the game's checkpoints_by_job.icon / loras_by_job.icon. "
               "Output: icon.png (+ icon_N.png, contact.png), raw*.png, prov.json.",
        "required": ["prompt"],
        "optional": {"negative": None, "seed": -1, "size": [1024, 1024], "canvas": 256, "padding": 0.08,
                     "key_color": "#ff00ff", "snap": False, "palette": None, "graph": "sdxl", "checkpoint": None,
                     "loras": None, "steps": None, "cfg": None, "style_prefix": None, "game": None, "variants": 1},
    },
    "sleeve": {
        "needs": "gpu",
        "doc": "A record sleeve (roadmap F7): square art by the model (no lettering asked of it) + typography set by "
               "PIL — `title`, `artist`, optional `label` — in `layout` 'band' (a title band across the bottom) or "
               "'corner' (stacked type in the top-left). Fonts: `font` / `font_bold` paths, else the game's assets/fonts, "
               "else a built-in fallback. Output: sleeve.png (`out_size`, default 1024), art.png, prov.json.",
        "required": ["prompt", "title"],
        "optional": {"artist": "", "label": "", "layout": "band", "out_size": 1024, "size": [1024, 1024], "font": None,
                     "font_bold": None, "negative": None, "seed": -1, "graph": "sdxl", "checkpoint": None, "loras": None,
                     "steps": None, "cfg": None, "style_prefix": None, "game": None, "refine": False},
    },
    "pipeline": {
        "needs": "gpu",
        "doc": "A chain of jobs run as one (roadmap F5): `steps` is a list of job objects ({type, …}); a string "
               "'$prev.outputs[0]' (or '$prev.outputs', '$steps[N].outputs[K]') is replaced with the matching output "
               "path of an earlier step. Each step writes to out/<id>/NN_<type>/; the chain stops at the first failing "
               "step and the error names it. `game`, `batch` and `name` are passed down to every step. Needs the GPU "
               "worker only when a step does.",
        "required": ["steps"],
        "optional": {"game": None, "contact": True},
    },
    # ------------------------------------------------------------------ CPU (pure image ops, run anywhere)
    "palette_snap": {
        "needs": "cpu",
        "doc": "Snap one or more images to a palette in OKLab (nearest perceptual colour), alpha preserved. "
               "Output: <name>.png per input + report.json (colour counts).",
        "required": ["inputs"],
        "optional": {"palette": None, "dither": None, "hysteresis": 0.0, "game": None},
    },
    "pixelize": {
        "needs": "cpu",
        "doc": "Turn a large generated image into pixel art: detect the pixel grid (or take `scale`), downscale "
               "cell-by-cell (mode/median/center), optional palette snap. Output: <name>.png + report.json.",
        "required": ["inputs"],
        "optional": {"scale": None, "method": "mode", "palette": None, "snap": False, "target": None, "game": None},
    },
    "remove_bg": {
        "needs": "cpu",
        "doc": "Flood-fill a flat background from the corners to alpha, trim, optionally pad to a size. "
               "Output: <name>.png (RGBA).",
        "required": ["inputs"],
        "optional": {"key_color": None, "tolerance": 28, "trim": True, "pad_to": None, "anchor": "bottom"},
    },
    "contact_sheet": {
        "needs": "cpu",
        "doc": "A labelled grid of images for review (this is how Claude looks at a batch). Output: contact.png.",
        "required": ["inputs"],
        "optional": {"cols": 4, "cell": [288, 162], "labels": None, "title": None},
    },
    "pack_sheet": {
        "needs": "cpu",
        "doc": "Pack frames into a sprite sheet with uniform cells (row-major), e.g. 8 facings × N frames. "
               "Output: sheet.png + sheet.json (cell size, order).",
        "required": ["inputs"],
        "optional": {"cols": 8, "cell": None, "anchor": "bottom"},
    },
    "godot_tileset": {
        "needs": "cpu",
        "doc": "Write a Godot 4 TileSet .tres for a tile strip PNG (which tiles collide). Output: <name>.tres.",
        "required": ["png", "tile_size", "blocking"],
        "optional": {"res_path": None},
    },
    "canny": {
        "needs": "cpu",
        "doc": "Canny edges (white on black) of each input — the ControlNet canny image, computed in numpy. "
               "`low`/`high` are fractions of the strongest gradient. Output: <name>.png.",
        "required": ["inputs"],
        "optional": {"low": 0.08, "high": 0.2, "sigma": 1.2},
    },
    "normal_map": {
        "needs": "cpu",
        "doc": "A tangent-space normal map for the game's `<id>_n.png` slot, OpenGL convention (Godot). `source` "
               "'luminance' (F11: height = brightness) or 'depth' (N1: from a depth map — `depth` is one path per input; "
               "`detail` 0..1 blends the luminance normals back in for brush texture; `smooth` (default 1.0) blurs the height first; "
               "Output: <name>_n.png, <name>_lit.png (a lit-from-the-left preview), contact.png "
               "(with source 'depth', both kinds side by side unless `compare` is false).",
        "required": ["inputs"],
        "optional": {"source": "luminance", "depth": None, "strength": 2.0, "smooth": 1.0, "detail": 0.0,
                     "invert_y": False, "preview": True, "compare": None},
    },
    "emissive_mask": {
        "needs": "cpu",
        "doc": "The glowing parts of each painting — bright AND saturated pixels (screens, neon, cores) plus any near "
               "`colors` — on black, for the game's additive `<id>_e.png` slot (roadmap F11). Output: <name>_e.png + "
               "report.json (fraction lit).",
        "required": ["inputs"],
        "optional": {"threshold": 0.85, "min_saturation": 0.25, "colors": [], "tolerance": 40, "feather": 1.5},
    },
    "depth_map": {
        "needs": "gpu",
        "doc": "A depth map per input (roadmap N1): Depth Anything V2 **Small** (Apache-2.0 — the forge always names it; "
               "the node's own default, Large, is CC-BY-NC) through comfyui_controlnet_aux (install_comfy_aux.bat). "
               "Output: <name>_depth.png, 16-bit grey, white = near, at the input's exact size. `resolution` is the "
               "model's working size (default 1024); `invert` flips near/far.",
        "required": ["inputs"],
        "optional": {"resolution": 1024, "invert": False},
    },
    "scene_layers": {
        "needs": "cpu",
        "doc": "Parallax planes from a painting and its depth map (roadmap N2). `depth`: one path per input. `cuts` "
               "[a, b] (0 < a < b < 1) or 'auto' (Otsu valleys of the depth histogram). Output per input: "
               "<name>_back.png (opaque, holes filled by edge extension, wider by `overscan` px each side), "
               "<name>_over.png (RGBA, soft edge `feather` px), <name>_mid_alpha.png (extra: the mid plane's own pixels), "
               "<name>_slide.png (the planes sliding ±`preview_shift` px; magenta would be a hole), layers.json (cuts, "
               "parallax 0.94/1.0/1.06, coverage). The painting itself is the mid plane and is never changed; a plane "
               "under 2% of the frame is dropped with a note.",
        "required": ["inputs", "depth"],
        "optional": {"cuts": "auto", "feather": 3.0, "overscan": 48, "fill": "extend", "preview_shift": 40},
    },
    "scene_kit": {
        "needs": "gpu",
        "doc": "A whole painted scene as the game's six-file set, in one job (roadmap N3): scene_paint (or repaint when "
               "`init` is given) → depth_map → normal_map (source depth) → emissive_mask → scene_layers. Takes every "
               "scene_paint / repaint field, plus `normals` {strength, smooth, detail}, `glow` {threshold, colors, …}, "
               "`layers` {cuts, overscan, feather}, `depth_resolution`, `slot_name` (default 'scene'). Output at the top "
               "of out/<id>/: scene.png, scene_n.png, scene_e.png, scene_back.png, scene_over.png, scene_depth.png, "
               "layers.json, contact.png (painting · depth · lit · glow · planes); each step's files in NN_<type>/. One "
               "prov.json whose licence chain covers every model, the depth model included. Approve with "
               "`approve <id> --as scenes/<map> --set`.",
        "required": ["prompt"],
        "optional": {"init": None, "denoise": None, "target": None, "size": None, "seed": -1, "control": None,
                     "normals": None, "glow": None, "layers": None, "depth_resolution": None, "slot_name": "scene",
                     "graph": "sdxl", "checkpoint": None, "loras": None, "game": None},
    },
    "overworld": {
        "needs": "cpu",
        "doc": "PLANNED — pull public-domain layers (Natural Earth, TIGER, GNIS, 3DEP, NLCD), compress the scale, "
               "emit a biome/road/town map in the game's format. Submitting one today returns 'not implemented'.",
        "required": ["region"],
        "optional": {"scale": "fe6", "layers": ["naturalearth"]},
    },
}


def validate(job: dict) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems: list[str] = []
    if not isinstance(job, dict):
        return ["job is not an object"]
    t = job.get("type")
    if t not in JOB_TYPES:
        return [f"unknown job type '{t}' (known: {', '.join(sorted(JOB_TYPES))})"]
    spec = JOB_TYPES[t]
    for r in spec["required"]:
        if r not in job or job[r] in (None, "", []):
            problems.append(f"{t}: missing required field '{r}'")
    name = job.get("name", "")
    if name and not all(ch.isalnum() or ch in "-_." for ch in name):
        problems.append(f"name '{name}' may only contain letters, digits, '-', '_' and '.'")
    for key in ("inputs",):
        if key in job and not isinstance(job[key], list):
            problems.append(f"{t}: '{key}' must be a list")
    if "expressions" in job and not isinstance(job["expressions"], list):
        problems.append(f"{t}: 'expressions' must be a list of phrases")
    if t == "pipeline":
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            problems.append("pipeline: 'steps' must be a non-empty list of jobs")
        else:
            for i, st in enumerate(steps):
                if not isinstance(st, dict):
                    problems.append(f"pipeline step {i + 1}: not an object")
                    continue
                if st.get("type") == "pipeline":
                    problems.append(f"pipeline step {i + 1}: pipelines do not nest")
                    continue
                problems += [f"pipeline step {i + 1}: {p}" for p in validate({k: v for k, v in st.items()})]
    if t in ("scene_paint", "repaint") and job.get("control") is not None:
        c = job["control"]
        if not isinstance(c, dict):
            problems.append(f"{t}: 'control' must be an object like {{\"type\": \"canny\", \"image\": \"…\", \"strength\": 0.6}}")
    if t in ("normal_map",) and job.get("source") not in (None, "luminance", "depth"):
        problems.append(f"normal_map: 'source' must be 'luminance' or 'depth', got {job.get('source')!r}")
    if t == "normal_map" and job.get("source") == "depth" and not job.get("depth"):
        problems.append("normal_map: source 'depth' needs 'depth' (one depth map per input)")
    if t == "scene_kit" and isinstance(job.get("denoise"), list):
        problems.append("scene_kit: 'denoise' must be one value (a scene_kit makes one set)")
    if t == "repaint" and isinstance(job.get("denoise"), list) and not job["denoise"]:
        problems.append("repaint: 'denoise' list is empty")
    return problems


def with_defaults(job: dict) -> dict:
    """Fill a validated job's optional fields with the type's defaults (None = 'use config')."""
    spec = JOB_TYPES[job["type"]]
    out = dict(spec["optional"])
    out.update(job)
    return out


def needs_gpu(job: dict) -> bool:
    if job.get("type") == "pipeline":
        return any(needs_gpu(st) for st in job.get("steps") or [] if isinstance(st, dict) and st.get("type") in JOB_TYPES)
    return JOB_TYPES[job["type"]]["needs"] == "gpu"


def render_docs() -> str:
    lines = ["# Job types", "", "Generated from `forge/schema.py` — do not edit by hand.", ""]
    for t, spec in JOB_TYPES.items():
        lines.append(f"## `{t}`  ({spec['needs'].upper()})")
        lines.append("")
        lines.append(spec["doc"])
        lines.append("")
        lines.append("Required: " + ", ".join(f"`{r}`" for r in spec["required"]))
        if spec["optional"]:
            lines.append("")
            lines.append("Optional (default): " + ", ".join(f"`{k}` ({v!r})" for k, v in spec["optional"].items()))
        lines.append("")
    return "\n".join(lines)
