"""The licence line of every tool the 3D workshop puts into a model — written into each model's provenance, so a
model that reaches a game can be traced to what made it and on what terms (the same rule as every picture's prov.json).

A tool's terms are recorded as read when it was brought in; `commercial_ok` False (or unknown) keeps a model out of
Deliver, exactly as approve does for pictures. Nothing non-commercial is ever registered here as a default.
"""
from __future__ import annotations

TOOLS: dict[str, dict] = {
    "flux2_klein_4b": {"name": "FLUX.2 [klein] 4B (Black Forest Labs) — paints the picture", "licence": "Apache-2.0",
                       "commercial_ok": True},
    "trellis2": {"name": "TRELLIS.2 (Microsoft) — picture to 3D model, through ComfyUI's own nodes", "licence": "MIT",
                 "commercial_ok": True},
    "pixal3d": {"name": "Pixal3D — picture to 3D model (buildings), through ComfyUI's own nodes", "licence": "MIT",
                "commercial_ok": True, "note": "its licence was MIT when it was brought in (2026-11-12)"},
    "comfy_template": {"name": "ComfyUI workflow template 3d_pixal3d_trellis2_image_to_model (Comfy-Org workflow_templates)",
                       "licence": "MIT", "commercial_ok": True},
    "mia": {"name": "Make-It-Animatable, in the ComfyUI-UniRig node pack — puts a skeleton into a person",
            "licence": "as published by its authors; recorded with the install",
            "commercial_ok": True, "note": "use accepted by the owner of the games (2026-11-12): the training data is its makers' "
                                           "exposure, not the user's"},
    "unirig": {"name": "UniRig (VAST-AI), in the ComfyUI-UniRig node pack — puts a skeleton into an animal or a thing",
               "licence": "MIT", "commercial_ok": True},
    "comfyui_unirig": {"name": "ComfyUI-UniRig node pack (the nodes around both riggers)", "licence": "as published by its author",
                       "commercial_ok": True},
    "quaternius_ual": {"name": "Quaternius Universal Animation Library — the motions fitted to a body", "licence": "CC0-1.0",
                       "commercial_ok": True},
    "blender": {"name": "Blender (as a Python module or a program) — fits motions, tidies models, grows trees", "licence": "GPL-3.0 "
                "(the program; what it makes belongs to whoever makes it)", "commercial_ok": True},
    "forge_tree": {"name": "the forge's tree grower (space colonisation, pipe rule) — grows a tree from a species sheet",
                   "licence": "the forge's own (MIT)", "commercial_ok": True},
    "filter_forge": {"name": "Filter Forge 15 Professional — renders a cut-out panel's texture (the filter is used from its own "
                             "folder and never copied)",
                     "licence": "commercial licence held by the owner of the games; rendered results may be used "
                                "commercially, the filters themselves are never redistributed (Filter Forge EULA)",
                     "commercial_ok": True,
                     "note": "William, 2026-11-14: the licence is installed on Filter Forge 15, which also renders the "
                             "Filter Forge 9 library it imported"},
    # the rigging pack ships Mixamo test dances for its own tests: never in a game (see motions.TEST_DANCES)
    "mixamo_test_dances": {"name": "the rigging pack's Mixamo test dances", "licence": "Adobe Mixamo terms — test only, never shipped",
                           "commercial_ok": False},
}


def lines(keys) -> list[str]:
    out = []
    for k in keys:
        if not k:
            continue
        t = TOOLS.get(k)
        out.append(f"{t['name']}: {t['licence']}" + (f" ({t['note']})" if t.get("note") else "") if t else f"{k}: not recorded")
    return out


def all_ok(keys) -> bool:
    return all(TOOLS.get(k, {}).get("commercial_ok") is True for k in keys if k)
