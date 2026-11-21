"""Job-type specs of the model pictures plug-in (BUILD 91) — no imports."""

MODEL_ICON = {
    "needs": "cpu",
    "doc": "An icon of a made 3D model (plug-in, forge/threed/modelpics.py; Blender's Cycles on the processor — no graphics "
           "card): `model` = a .glb. Clear background, `size` 512, three-quarter view (`az` 35, `el` 22), one fixed key "
           "light — the same for every thing. `auto_view` (on) applies one rule to all: the longer ground side is laid "
           "across the frame (a long thing along its diagonal), and a thing lying flat is looked at from above. Give "
           "`az` / `el` with `auto_view: false` for one thing's own view. `world_id` + `game` record which world-list "
           "thing it is, so the picture carries that model's licence lines. Outputs: <slot>.png (RGBA), contact.png "
           "(on dark, on light, and at 64 and 32 pixels).",
    "required": ["model"],
    "optional": {"size": 512, "slot_name": "icon", "az": 35.0, "el": 22.0, "auto_view": True, "margin": 0.07, "samples": 40,
                 "light": None, "world_id": None, "minutes": 15},
}
MODEL_PORTRAIT = {
    "needs": "cpu",
    "doc": "A head-and-shoulders portrait of a made body (plug-in, forge/threed/modelpics.py; Cycles on the processor): "
           "`model` = a rigged .glb. The body is put at rest (`clip`, default its idle motion, first frame), its head "
           "set upright (`level_head`), its faces smoothed, and framed by its head bone. Light: one warm key close to "
           "the face falling off to dark, and a faint rim behind in `rim` [r, g, b] (a character's own colour, where it "
           "has one). One more picture for every expression (shape key) the body carries, if any. Outputs: <slot>.png "
           "(RGBA, `size` 768), <slot>_<expression>.png, contact.png.",
    "required": ["model"],
    "optional": {"size": 768, "slot_name": "portrait", "rim": None, "light": None, "clip": "Idle_Loop", "frame": 0, "az": 14.0,
                 "el": 2.0, "level_head": True, "smooth": True, "expressions": None, "margin": 0.06, "samples": 48,
                 "world_id": None, "minutes": 15},
}
JOB_TYPES = {"model_icon": MODEL_ICON, "model_portrait": MODEL_PORTRAIT}
