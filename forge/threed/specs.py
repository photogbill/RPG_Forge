"""The 3D workshop's job types (BUILD 36), for the queue. No imports: forge/plugins/threed.py loads this while the
worker runs, and a plug-in must not pull in forge.jobs at load time. The handlers are forge/threed/jobs.py.

Two ComfyUIs must never hold the card at once: model_3d and rig_body take the card lock (cardlock.py) before they put
work on it. fit_motions and grow_tree run Blender on the processor. Every output carries a prov.json: the words as
expanded, seeds, model, settings, tool versions and the licence line of every tool that touched it.
"""

MODEL_3D = {
    "needs": "gpu",
    "doc": "A picture or a description -> one 3D model, through the art ComfyUI's own TRELLIS.2 / Pixal3D nodes (✦ 1024; "
           "TRELLIS.2 for people and everyday things, Pixal3D for buildings). With `image` (a path under the forge, e.g. a "
           "picture you picked from a render job) that picture is used; otherwise the picture is painted first with FLUX.2 "
           "klein from `prompt` + `always` (default: the game's pose.threed_body / layout.threed_thing block, else the "
           "forge's). `kind` body|prop|building picks those defaults. `real_size_m` {height|width|depth} with `tidy` (default "
           "true for props and buildings) welds it, removes loose scraps and sets its real size (Blender). Holds the card "
           "lock. Output: <name>__<model>.glb, picture.png, prov.json, report.json (+ <name>__<model>_raw.glb when tidied).",
    "required": [],
    "optional": {"image": None, "prompt": "", "always": None, "negative": None, "kind": "body", "model": None, "seed": 1001,
                 "size": 1024, "unet": "flux-2-klein-4b.safetensors", "resolutions": [1024], "faces": 60000, "texture": 2048,
                 "seed3d": None, "minutes": 60, "real_size_m": None, "tidy": None, "scraps": 0.02, "game": None,
                 "character": None, "try_id": None},
}

RIG_BODY = {
    "needs": "gpu",
    "doc": "A 3D body -> a skeleton (Mixamo-named), in the rigging ComfyUI (engines/rig, port 8189), which it starts and "
           "stops itself. `kind` people (default): Make-It-Animatable with the finger bones kept; animal: the seams are "
           "welded first (Blender), then UniRig. `glb` is the body (a path under the forge, e.g. a model_3d job's .glb). "
           "Holds the card lock (and asks the art ComfyUI to put its models away first). Output: <name>__<rigger>.fbx, "
           "<name>__<rigger>_preview.glb, <name>__orientation.png, prov.json, report.json.",
    "required": ["glb"],
    "optional": {"kind": "people", "use_normal": False, "no_fingers": False, "minutes": 30, "game": None, "character": None,
                 "try_id": None},
}

FIT_MOTIONS = {
    "needs": "cpu",
    "doc": "A rigged body (`fbx`, from rig_body) -> the motion library fitted to it: one .glb with every motion by name, "
           "standing on the floor in metres, and a sheet of each motion's length, loop and ground speed (metres a second, "
           "measured from the library's root motion and scaled to the body's legs). `height` in metres. `skip`: motions "
           "this character never does. `library` / `travel` default to forge.json threed.motion_library / motion_travel "
           "(the Quaternius Universal Animation Library, CC0). Blender's Python (the rigging environment's) or "
           "threed.blender_exe. Output: <name>_moves.glb, <name>_moves.json, prov.json.",
    "required": ["fbx"],
    "optional": {"height": 1.72, "skip": [], "clips": [], "library": None, "travel": None, "minutes": 20, "game": None,
                 "character": None, "try_id": None},
}

GROW_TREE = {
    "needs": "cpu",
    "doc": "A tree grown by rule from a species sheet and a seed (one seed = one tree, the next seed its sibling). "
           "`species`: a sheet's name (the forge's species/ or the game's games/<id>/threed/species/) or a sheet itself "
           "({\"name\", \"numbers\": {...}}). `count` trees from `seed` up; `bare` leaves the leaves off. Blender on the "
           "processor. Output: <name>_seed<N>[_bare].glb and a picture of each, prov.json.",
    "required": [],
    "optional": {"species": "broadleaf", "seed": 11, "count": 1, "bare": False, "views": 1, "size": 360, "samples": 16,
                 "minutes": 20, "game": None},
}

LINE_3D = {
    "needs": "gpu",
    "doc": "The whole 3D line for a list, unattended (what the overnight cast run did): picture -> 3D body -> skeleton -> "
           "motions for every body in `list` (a list file, the same format the 2026-11-13 runs read), one report. A body "
           "that fails a step is left out of the next; every step skips what is made, so it can be run again. Writes into "
           "out/3d/<batch>/ (pictures, models, rig, moves, run.log, REPORT.txt); the job's own folder gets result.json. "
           "Approves nothing.",
    "required": ["list"],
    "optional": {"only": None, "skip": [], "game": None},
}

JOB_TYPES = {"model_3d": MODEL_3D, "rig_body": RIG_BODY, "fit_motions": FIT_MOTIONS, "grow_tree": GROW_TREE, "line_3d": LINE_3D}
