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
    return problems


def with_defaults(job: dict) -> dict:
    """Fill a validated job's optional fields with the type's defaults (None = 'use config')."""
    spec = JOB_TYPES[job["type"]]
    out = dict(spec["optional"])
    out.update(job)
    return out


def needs_gpu(job: dict) -> bool:
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
