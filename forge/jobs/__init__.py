"""Job handlers: one module per job type; `get_handlers()` maps type → callable(job, ctx, out_dir) -> result.

Every handler writes a prov.json (provenance: model, workflow, seed, prompt, post-processing) next to
its outputs. That record is the licensing/disclosure inventory — never skip it.

`get_handlers(reload=True)` re-imports the handler modules first, so a fix saved to disk reaches a
worker that is already running — no restart while a batch is in flight.
"""
from __future__ import annotations
import importlib
from . import common, cpu, gpu, paint, assets, scene

HANDLERS = {}


def _pipeline_handler(job, ctx, out):
    from .. import pipeline
    return pipeline.handler(job, ctx, out)


def get_handlers(reload: bool = False) -> dict:
    global HANDLERS
    if reload:
        from .. import bakeoff as _bakeoff, pipeline as _pipeline
        from ..engines import sdxl_graph as _graph, comfy as _comfy, flux1_graph as _f1, flux2_graph as _f2, graph_ops as _go
        from ..engines import krea2_graph as _k2
        from ..ops import edges as _ed, lighting as _lt, depth as _dp, layers as _ly
        # dependencies first, then the handler modules that import them
        for mod in (_graph, _f1, _f2, _k2, _go, _comfy, _ed, _lt, _dp, _ly, _bakeoff, common, cpu, gpu, paint, assets, scene, _pipeline):
            try:
                importlib.reload(mod)
            except Exception:  # a half-saved file: keep the last good version
                pass
    HANDLERS = {
        # GPU
        "scene_card": gpu.scene_card,
        "concept": gpu.concept,
        "portrait": gpu.portrait,
        "prop": gpu.prop,
        "tile_texture": gpu.tile_texture,
        "render": gpu.render,
        "scene_paint": paint.scene_paint,
        "repaint": paint.repaint,
        "upscale": paint.upscale,
        "icon": assets.icon,
        "sleeve": assets.sleeve,
        "pipeline": _pipeline_handler,
        "depth_map": scene.depth_map,
        "scene_kit": scene.scene_kit,
        # CPU
        "palette_snap": cpu.palette_snap,
        "pixelize": cpu.pixelize,
        "remove_bg": cpu.remove_bg,
        "contact_sheet": cpu.contact_sheet,
        "pack_sheet": cpu.pack_sheet,
        "godot_tileset": cpu.godot_tileset,
        "canny": cpu.canny,
        "normal_map": scene.normal_map,          # N1: source luminance (F11, unchanged) or depth
        "scene_layers": scene.scene_layers,
        "emissive_mask": cpu.emissive_mask,
        "overworld": cpu.overworld,
    }
    return HANDLERS


get_handlers()
