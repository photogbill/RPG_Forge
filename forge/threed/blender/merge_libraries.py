"""Join motion libraries that share one skeleton into one library file (BUILD 43 part 3a: Quaternius UAL1 + UAL2).

    blender --background --factory-startup --python merge_libraries.py -- <out.glb> <first.glb> <second.glb> [...]

The Universal Animation Library 2 is the first library's companion: the same mannequin, the same bones, 43 more motions
(sword block, dash, the regular and heavy combos, the ninja jump, climb up, knockback, the overhand throw, folded arms
…). The fitting (`fit_motions.py`) reads one library, so the two are joined here into one file: the first file's
skeleton, every motion of every file by its own name (a name already taken - both carry A_TPose - keeps the first).
Writes `<out>.json` beside it: each motion and which file it came from. CC0 in, CC0 out.
"""
from __future__ import annotations

import json
import os
import sys

import bpy


def _clean(name: str, owner: str) -> str:
    return name[: -len(owner) - 1] if owner and name.endswith("_" + owner) else name


def merge(out: str, sources: list[str]) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    keep_arm = None
    taken: dict[str, str] = {}
    for k, src in enumerate(sources):
        before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
        bpy.ops.import_scene.gltf(filepath=src)
        new_o = [o for o in bpy.data.objects if o not in before_o]
        new_a = [a for a in bpy.data.actions if a not in before_a]
        arm = next((o for o in new_o if o.type == "ARMATURE"), None)
        if arm is None:
            raise RuntimeError(f"{src} has no skeleton")
        if keep_arm is None:
            keep_arm = arm
        else:
            mine = {b.name for b in keep_arm.data.bones}
            theirs = {b.name for b in arm.data.bones}
            if mine != theirs:
                missing = sorted(theirs - mine)[:8]
                raise RuntimeError(f"{os.path.basename(src)} has a different skeleton (bones not in the first: {missing})")
        for a in new_a:
            nm = _clean(a.name, arm.name)
            if nm in taken:
                bpy.data.actions.remove(a)
                continue
            a.name = nm
            a.use_fake_user = True
            taken[nm] = os.path.basename(src)
        if arm is not keep_arm:
            for o in new_o:
                bpy.data.objects.remove(o, do_unlink=True)
    # every action becomes a strip on the kept skeleton so the exporter writes each one as a named animation
    ad = keep_arm.animation_data or keep_arm.animation_data_create()
    ad.action = None
    for a in bpy.data.actions:
        tr = ad.nla_tracks.new()
        tr.name = a.name
        tr.strips.new(a.name, int(a.frame_range[0]), a)
        tr.mute = True
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_animations=True,
                              export_animation_mode="NLA_TRACKS", export_force_sampling=True)
    sheet = {"_about": "Motions in this joined library and the file each came from (forge merge_libraries.py).",
             "sources": [os.path.basename(s) for s in sources], "motions": taken}
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(sheet, f, indent=1)
    print("MERGED", len(taken), "motions into", out)
    return sheet


if __name__ == "__main__":
    ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if len(ARGV) >= 3:
        merge(ARGV[0], ARGV[1:])
    else:
        print(__doc__)
