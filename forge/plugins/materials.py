"""The materials plug-in (BUILD 87): ff_channel_proof, ff_channels (CPU, Filter Forge), mm_material (the card, Material
Maker, under the forge's card lock), material_mix, material_decal (CPU, numpy). Specs: forge/materials/specs.py;
the code is imported only when a job runs, so a running worker picks up a fix without a restart."""
from __future__ import annotations
from forge.materials import specs as _specs

DEPENDS = ("forge.materials.specs", "forge.materials.look", "forge.materials.ffchannels", "forge.materials.mm",
           "forge.materials.mix", "forge.night3b.ffdriver")


def ff_channel_proof(job, ctx, out):
    from forge.materials import ffchannels
    return ffchannels.proof(job, ctx, out)


def ff_channels(job, ctx, out):
    from forge.materials import ffchannels
    return ffchannels.render_set(job, ctx, out)


def mm_material(job, ctx, out):
    from forge.materials import mm
    return mm.render(job, ctx, out)


def material_mix(job, ctx, out):
    from forge.materials import mix
    return mix.mix_job(job, ctx, out)


def material_decal(job, ctx, out):
    from forge.materials import mix
    return mix.decal_job(job, ctx, out)


JOB_TYPES = dict(_specs.JOB_TYPES)
HANDLERS = {"ff_channel_proof": ff_channel_proof, "ff_channels": ff_channels, "mm_material": mm_material,
            "material_mix": material_mix, "material_decal": material_decal}
