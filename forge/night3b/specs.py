"""Job-type specs of the Night 3B plug-ins — no imports (a plug-in loads these without pulling in forge.jobs).
Kept apart from forge/night3/specs.py on purpose: one broken specs file must not take both nights' types down."""

HANDOFF_FILE = {
    "needs": "cpu",
    "doc": "File a picture that came back from an outside tool (plug-in, forge/night3b/handoff_jobs.py; made by "
           "`handoff in`): `input` = the returned picture, `source_job` = the forge job it was made from, `tool` = the "
           "tool's key in the tool register (`handoff tool add`). The picture becomes this job's own output under the "
           "source's file name; provenance follows the source's models and adds the tool as a licence line. Outputs: "
           "<name>.png, contact.png (the forge's own version beside the tool's).",
    "required": ["input", "source_job", "tool"],
    "optional": {"slot_name": None, "target": None},
}
HANDOFF_KIT = {
    "needs": "gpu",
    "doc": "A scene kit rebuilt on a picture that came back from an outside tool (plug-in; made by `handoff in` when "
           "the source was a scene_kit): the returned picture is the painting; depth (Depth Anything V2 Small), normals, "
           "glow and layers are built from it with the source kit's settings. Same six files as a kit, so `kit check` "
           "and `approve --set` work on it. Provenance: the source's models + the depth model + the tool.",
    "required": ["input", "source_job", "tool"],
    "optional": {"slot_name": None, "target": None, "depth_resolution": None},
}
FILTER_FORGE = {
    "needs": "cpu",
    "doc": "Render with Filter Forge's command-line renderer (plug-in, forge/night3b/ffdriver.py; needs "
           "forge.json tools.filter_forge.exe — the public repo works without it, the job then fails with a plain "
           "message). `filter` = path of an .ffxml (never copied — the forge stores paths), `preset` = the preset number "
           "(0 = the filter's first preset), `input` = a picture for an effect filter (omit for a texture filter), "
           "`size` [w, h] for a texture (default [1024, 1024]). A channel (normal, height, …) is a preset you save in "
           "Filter Forge with that channel chosen in its Render Channels menu: `channels` {\"final\": 0, \"normal\": 9} "
           "renders one task per channel (a list like [\"final\"] uses `preset`). `seamless: true` checks the preset has "
           "Seamless Tiling on (when the forge can read it) and measures the wrap seam of the result. Normal maps come "
           "out in OpenGL convention (NormalMapFlipY true; checked against the height/bump channel when one is "
           "rendered too) and are also written as <slot>_n.png. `tileable: true` (Night 4) makes every channel tile in the "
           "forge afterwards (offset + heal, the same geometry for all channels) → <file>_tile.png, measured before/after. Outputs: <slot>_<channel>.png (16-bit), <slot>_n.png, "
           "tasks.xml, render.log, contact.png.",
    "required": ["filter"],
    "optional": {"preset": 0, "input": None, "size": [1024, 1024], "channels": ["final"], "seamless": False,
                 "slot_name": "texture", "normal_flip_y": True, "bit_depth": 16, "timeout_sec": 900,
                 "seam_limit": 1.5, "tileable": False, "tile_band": 0.12},
}
