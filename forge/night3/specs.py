"""Job-type specs of the Night 3 plug-ins — no imports, so a plug-in file can load them without pulling in
forge.jobs (which itself loads the plug-ins: importing the handler modules here would be circular)."""

SCENE_BIG = {
    "needs": "gpu",
    "doc": "A painting larger than one pass (plug-in, forge/night3/big.py): small whole-scene paint from the greybox "
           "(`init`) or prompt — or start from `source`, an existing painting — → upscale to `target` → tiled img2img "
           "refine (ControlNet tile, + canny from the greybox) → feathered merge → seam scores. Outputs: scene.png, "
           "small.png, upscaled.png, tiles/, seams.json, seam_sheet.jpg, contact.png.",
    "required": ["prompt", "target"],
    "optional": {"init": None, "source": None, "size": None, "megapixels": 1.0, "init_denoise": 0.65, "tile": [1344, 768],
                 "overlap": 128, "max_step": 2.0, "denoise": 0.3, "tile_strength": 0.6, "canny_strength": 0.4, "checkpoint": None,
                 "loras": None, "seed": -1, "steps": None, "cfg": None, "sampler": None, "scheduler": None,
                 "negative": None, "graph": "sdxl", "freeu": False, "upscale_model": None, "controlnet": None,
                 "control": None, "style_prefix": None},
}


_COMMON = {"checkpoint": None, "loras": None, "seed": -1, "steps": None, "cfg": None, "sampler": None, "scheduler": None,
           "negative": None, "graph": "sdxl", "freeu": False, "denoise": 0.9, "method": "noise_mask", "grow_mask_by": 0,
           "pad": 96, "min_side": 768, "megapixels": 1.0, "style_prefix": None, "controlnet": None, "canny_strength": 0.5}
INPAINT = {
    "needs": "gpu",
    "doc": "Repaint only the masked part of a picture (plug-in, forge/night3/inpaint.py): `init` + `mask` (white = "
           "repaint; `mask_grow`/`mask_feather` optional) + a prompt for that part. SDXL with the job's own checkpoint "
           "(SetLatentNoiseMask; `method: encode_for_inpaint` for inpaint checkpoints). Outside the mask the output is "
           "bit-identical to the init. Outputs: inpaint.png, mask.png, contact.png (base · mask · result · difference).",
    "required": ["init", "mask", "prompt"],
    "optional": {**_COMMON, "mask_grow": 0, "mask_feather": 0},
}
SCENE_STATE = {
    "needs": "gpu",
    "doc": "A state of a painted room (plug-in): `base` (a painting, or a scene_kit folder) + `mask` or `greybox_base` "
           "+ `greybox_state` (the mask is what changed, grown and feathered; refused over 35 % of the frame) + a prompt "
           "for only the changed part. Outside the mask the state is bit-identical to the base; for a kit, the "
           "companions are rebuilt and changed only inside the mask. Outputs: scene.png, mask.png, contact.png, "
           "difference.png (+ scene_n/_e/_depth/_over/_back/_mid_alpha for a kit).",
    "required": ["base", "prompt"],
    "optional": {**_COMMON, "mask": None, "greybox_base": None, "greybox_state": None, "threshold": 12, "grow": 24,
                 "feather": 12.0, "max_share": 0.35, "control": True, "companions": True, "mask_grow": 0, "mask_feather": 0},
}


# ------------------------------------------------------------------ G7: sprite-sheet tools (CPU)
FACINGS_PACK = {
    "needs": "cpu",
    "doc": "Single-pose pictures → one facings sheet (plug-in, forge/ops/sprites.py): `input` = a folder of poses named by "
           "facing (…_S.png, …_NW.png) or exactly eight in S,SW,W,NW,N,NE,E,SE order. Background removed, one common "
           "figure height, feet on one baseline, centred per cell (default 144×216), `mirror` fills a facing from its "
           "opposite (['W→E']). Outputs: sheet.png (1152×216), report.json (edge touches), turntable.gif.",
    "required": ["input"],
    "optional": {"cell": [144, 216], "mirror": None, "figure_height": 0.92, "baseline": 6, "key": None, "tolerance": 28},
}
ANIM_PREVIEW = {
    "needs": "cpu",
    "doc": "A sprite sheet → GIF per facing (rows) and a turntable (plug-in). `input` = the sheet, `cell`, `layout` "
           "auto|rows|facings, `fps`. Outputs: anim_<facing>.gif, turntable.gif.",
    "required": ["input"],
    "optional": {"cell": [144, 216], "layout": "auto", "fps": 8.0, "turntable_fps": 2.0},
}
TURNAROUND_SPLIT = {
    "needs": "cpu",
    "doc": "A 3- or 8-view turnaround sheet → the separate views (plug-in), cut at empty columns. Outputs: view_NN.png.",
    "required": ["input"],
    "optional": {"min_gap": 6, "min_width": 12, "key": None, "tolerance": 28},
}


# ------------------------------------------------------------------ G12: UI pieces (CPU)
NINE_SLICE = {
    "needs": "cpu",
    "doc": "A painted panel or frame → a nine-slice (plug-in, forge/ops/ui_pieces.py): trimmed, corners/edges detected "
           "(or `margins` {left,top,right,bottom}), centre made tileable, `key` (auto or [r,g,b]) removes a flat background first, margins snapped to a multiple of 3 (UI is "
           "640×360 ×3), `scale` to resize. Outputs: piece.png, piece.json (Godot NinePatchRect patch_margin_*), "
           "preview.png (stretched to three sizes).",
    "required": ["input"],
    "optional": {"margins": None, "scale": 1.0, "snap": 3, "tileable": True, "key": None},
}
BUTTON_STATES = {
    "needs": "cpu",
    "doc": "One button picture → normal / hover / pressed / disabled by tone only (plug-in). Outputs: <name>_normal.png … "
           "and states.png.",
    "required": ["input"],
    "optional": {},
}
