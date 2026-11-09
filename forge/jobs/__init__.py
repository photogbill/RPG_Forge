"""Job handlers: one module per job type; `HANDLERS` maps type → callable(job, ctx, out_dir) -> result.

Every handler writes a prov.json (provenance: model, workflow, seed, prompt, post-processing) next to
its outputs. That record is the licensing/disclosure inventory — never skip it.
"""
from __future__ import annotations
from . import cpu, gpu

HANDLERS = {
    # GPU
    "scene_card": gpu.scene_card,
    "concept": gpu.concept,
    "portrait": gpu.portrait,
    "prop": gpu.prop,
    "tile_texture": gpu.tile_texture,
    # CPU
    "palette_snap": cpu.palette_snap,
    "pixelize": cpu.pixelize,
    "remove_bg": cpu.remove_bg,
    "contact_sheet": cpu.contact_sheet,
    "pack_sheet": cpu.pack_sheet,
    "godot_tileset": cpu.godot_tileset,
    "overworld": cpu.overworld,
}
