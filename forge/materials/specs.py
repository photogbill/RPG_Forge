"""Job-type specs of the materials plug-in (BUILD 87) — no imports, so a running worker can load them cheaply."""

FF_CHANNEL_PROOF = {
    "needs": "cpu",
    "doc": "Find out, by rendering, which number in a Filter Forge preset chooses which render channel (plug-in, "
           "forge/materials/ffchannels.py). For `filter` + `preset` it writes working copies of the filter in this job's "
           "own folder — one a number, every preset's `map_type` set to it — renders each small, and names what came "
           "back by what the picture is (a normal map is blue, a height map's slopes agree with the normal map, …) "
           "checked against the order of Filter Forge's own Render Channels menu. The result is kept in "
           "local/ff_channels.json for this filter type; `ff_channels` jobs use it. Outputs: proof.png (every number's "
           "picture with its name), proof.json, tasks.xml, render.log. The working copies are removed afterwards.",
    "required": ["filter"],
    "optional": {"preset": 0, "size": [256, 256], "numbers": 12, "timeout_sec": 1800, "keep_copy": False,
                 "slot_name": "proof"},
}
FF_CHANNELS = {
    "needs": "cpu",
    "doc": "A true channel set from Filter Forge (plug-in, forge/materials/ffchannels.py): the final picture plus its "
           "normal, height, roughness and occlusion channels (metal too where the filter has any), all from one preset "
           "at one size, so they sit exactly on each other. Needs the proof for the filter's type (job type "
           "ff_channel_proof, or materials_ff_channels.bat); without it the job proves the filter itself first. "
           "`variation` renders another seed of the same preset. `tileable: true` heals the wrap seam of every channel "
           "with ONE geometry taken from the final picture. A legacy surface filter has no roughness channel: it is "
           "worked out from its two specular channels and the report says so. `beside` + `beside_stem`: also put the "
           "set beside an existing picture (<stem>_ffnormal.png, _height.png, _rough.png, _ao.png) — only when this "
           "job's final picture matches the one already there, and never over a file that exists. Outputs: "
           "<slot>.png, <slot>_n.png (OpenGL), <slot>_height.png, <slot>_rough.png, <slot>_ao.png, channels.json "
           "(which channel is true, worked out, or missing), contact.png, moving_light.png.",
    "required": ["filter"],
    "optional": {"preset": 0, "size": [1024, 1024], "variation": None, "seamless": True, "tileable": False,
                 "tile_band": 0.12, "slot_name": "material", "want": ["normal", "height", "roughness", "ambient_occlusion"],
                 "beside": None, "beside_stem": None, "match": None, "timeout_sec": 14400, "keep_copy": False,
                 "bit_depth": 16, "map_types": None},
}
MM_MATERIAL = {
    "needs": "gpu",
    "doc": "A material from a Material Maker graph (plug-in, forge/materials/mm.py; needs Material Maker in "
           "engines/material_maker or forge.json tools.material_maker.exe). `graph` = a .ptex file, or the name of one "
           "of the forge's own graphs (forge/materials/graphs/). `setting` picks one of the graph's named states (its "
           "side file <graph>.json lists them); `parameters` {name: 0..1} sets named parameters one by one; `seed` "
           "moves every random node together. The graph is checked against the installed node library before anything "
           "runs, a patched copy is written into this job's folder, and Material Maker exports it at `size` — holding "
           "the forge's card lock, so it runs between the 3D queue's items. Outputs: <slot>.png (colour), <slot>_n.png "
           "(OpenGL), <slot>_height.png, <slot>_rough.png, <slot>_ao.png, <slot>_metal.png / <slot>_emission.png when "
           "the graph has them, <slot>.ptex (what was exported), channels.json, contact.png, moving_light.png.",
    "required": ["graph"],
    "optional": {"setting": None, "parameters": {}, "seed": 0.0, "size": 2048, "slot_name": None,
                 "target": "Godot/Godot 4 ORM", "timeout_sec": 900, "wait_card_minutes": 720, "use_card_lock": True},
}
MATERIAL_MIX = {
    "needs": "cpu",
    "doc": "No repeats (plug-in, forge/materials/mix.py): three seeds of one material — `inputs`, three colour pictures "
           "whose channel files sit beside them — mixed by a smooth noise mask into one set `repeat` times as wide, so "
           "the eye finds no tile. The mask follows the height where there is one (the higher surface wins the edge). "
           "Also writes the mask itself (<slot>_mixmask.png: red, green, blue = the three seeds' share) for an engine "
           "that would rather mix live. Outputs: <slot>.png and its channels, <slot>_mixmask.png, contact.png "
           "(one tile against the mix, both laid out 3 by 3).",
    "required": ["inputs"],
    "optional": {"repeat": 2, "seed": 7, "blobs": 3.0, "softness": 0.18, "slot_name": "mix", "size": None},
}
MATERIAL_DECAL = {
    "needs": "cpu",
    "doc": "Wear as a layer (plug-in, forge/materials/mix.py): one picture of scorch, cracks, grime or rust becomes a "
           "decal — colour with see-through (<slot>_decal.png), its own normal map (<slot>_decal_n.png) and roughness "
           "(<slot>_decal_rough.png) — that fades to nothing at its edge, so it can be laid over any ground and taken "
           "off again. `alpha_from`: 'alpha' (the picture's own), 'dark' (soot and grime: darker than its surroundings "
           "is more solid), 'light' (smoke on black, ash, chalk), 'key' (how far from the border colour), 'streaks' (runs the "
           "forge draws itself, trailing down: rust under a bolt). `tint` [r, g, b] gives the whole decal one colour "
           "(soot is black whatever colour the smoke was). `relief`: 'cut' (cracks: cut into the ground), 'raised' (ash, "
           "mud: lying on it), 'picture', 'flat'; `height` / `normal`: true channel files when there are any. "
           "Outputs: the three files, decal.json, contact.png (the decal alone, and over a mid-grey ground under a "
           "raking light).",
    "required": ["input"],
    "optional": {"alpha_from": "dark", "strength": 1.0, "edge": 0.18, "height": None, "normal": None,
                 "roughness": None, "rough_value": 0.9, "slot_name": "wear", "size": None, "depth": 6.0, "tint": None,
                 "relief": "cut", "seed": 3},
}
JOB_TYPES = {"ff_channel_proof": FF_CHANNEL_PROOF, "ff_channels": FF_CHANNELS, "mm_material": MM_MATERIAL,
             "material_mix": MATERIAL_MIX, "material_decal": MATERIAL_DECAL}
