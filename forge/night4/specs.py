"""Job-type specs of the Night 4 plug-ins — no imports (a plug-in loads these without pulling in forge.jobs)."""

SPRITE_INTAKE = {
    "needs": "cpu",
    "doc": "A character sheet from any outside tool → the game's sprite contract (plug-in, forge/night4/intake.py). "
           "`input` = the sheet (any grid, any backdrop: flat, white, painted checkerboard or real alpha; labels between "
           "rows are dropped), `character` (+ `variant`). Figures are found as connected shapes, numbered in reading "
           "order and mapped to facings/frames by `mapping` (default games/<game>/intake/<character>[__<variant>]/"
           "<sheet>.intake.json — the first run writes the forge's guess there; a person fixes it and reruns). One "
           "scale, feet on one baseline, centred on the feet. `tool` = \"<name version>\" of the program that made the "
           "sheet (its licence line comes from the tool register). Outputs: sheet.png (one row, 8 facings S…SE, cell "
           "144×216 — the contract), anim.png (rows = facings, columns = frames, when there are frames), numbers.png, "
           "frames/, turntable.gif, anim_<facing>.gif, edges.md, report.json.",
    "required": ["input", "character"],
    "optional": {"variant": None, "mapping": None, "tool": None, "cell": [144, 216], "figure_height": 0.92,
                 "baseline": 6, "scale": "uniform", "key": None, "tolerance": 30},
}

CHARACTER_SET = {
    "needs": "gpu",
    "doc": "One character variant → its set (plug-in, forge/night4/charset.py): portrait moods on the variant's locked "
           "seed (same face, one `{{mood.<m>}}` block each), a battle pose (`{{pose.battle}}`), and a turnaround with "
           "the variant's sheet LoRA(s) → cut and packed through sprite_intake into the same sheet contract as a "
           "drawn sheet. Everything inherits the registry (games/<game>/characters/<id>.json); job keys win. "
           "`parts` picks a subset: [\"moods\", \"battle\", \"turnaround\"]. Outputs: moods/<m>.png, battle.png, "
           "turnaround.png, sheet.png (+ the intake files), contact.png.",
    "required": ["character"],
    "optional": {"variant": None, "parts": None, "moods": None, "portrait_size": [896, 1152], "battle_size": [832, 1216],
                 "turnaround_size": [1536, 768], "sheet_lora": None, "sheet_lora_strength": 0.8, "mapping": None},
}

ICON_BATCH = {
    "needs": "gpu",
    "doc": "Many item icons in one job (plug-in, forge/night4/icons.py): `items` = [{\"id\", \"name\", \"description\", "
           "\"category\"}] (produce/brief fill it from wanted.json), one family seed per category so a category looks "
           "drawn by one hand; each is rendered square, cut out (transparent), saved at `size` and 2×. Prompt template "
           "`prompt` with {name} {description} in it (default: \"{{icon.house}}, {{icon.<category>}}, {name}: "
           "{description}\" — the blocks are Fable's). Outputs: icons/<id>.png, icons@2x/<id>.png, contact_<category>.png.",
    "required": ["items"],
    "optional": {"prompt": None, "size": [256, 256], "render_size": [1024, 1024], "seeds": None, "checkpoint": None,
                 "loras": None, "steps": None, "cfg": None, "sampler": None, "scheduler": None, "negative": None,
                 "key": "#ff00ff", "tolerance": 40},
}

PHOTO_PLATE = {
    "needs": "gpu",
    "doc": "One of William's photographs → a painted plate (plug-in, forge/night4/photo.py). `photo` is a PATH (never "
           "copied into the repo); it must be listed in the git-ignored games/<game>/refs.local.json with `people: "
           "none` or `people: william` (his cameo ruling) or the job refuses. img2img on the scene checkpoint at "
           "`target` with `denoise` and ControlNet depth/canny from the photo, then the kit companions (depth, normals, "
           "glow, layers) so it lights like any painted scene. Provenance: \"William's own photograph\" + the path.",
    "required": ["photo", "prompt"],
    "optional": {"target": [1920, 1080], "denoise": 0.55, "control": "canny", "control_strength": 0.5, "checkpoint": None,
                 "loras": None, "seed": -1, "steps": None, "cfg": None, "sampler": None, "scheduler": None,
                 "negative": None, "companions": True, "graph": "sdxl"},
}

TILEABLE = {
    "needs": "cpu",
    "doc": "Make a texture tile seamlessly (plug-in, forge/night4/tileable.py): offset by half, heal the cross seam — "
           "inpainted on the job's checkpoint when a GPU worker runs it (`heal: inpaint`), a blend otherwise "
           "(`heal: blend`, CPU) — and verify with the wrap-seam score before/after; refused (the input kept) if it "
           "got worse. `input` = picture or a job folder. Outputs: tile.png, tiled_2x2.png, compare.png, report.json.",
    "required": ["input"],
    "optional": {"heal": "auto", "band": 0.12, "prompt": None, "checkpoint": None, "denoise": 0.6, "seed": -1,
                 "limit": 1.5},
}
