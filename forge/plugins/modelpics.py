"""The model pictures plug-in (BUILD 91): model_icon and model_portrait — icons and portraits taken from made 3D models by
Blender's Cycles on the processor. Specs: forge/threed/modelpics_specs.py; code: forge/threed/modelpics.py (imported
only when a job runs)."""
from __future__ import annotations
from forge.threed import modelpics_specs as _specs

DEPENDS = ("forge.threed.modelpics_specs", "forge.threed.modelpics")


def model_icon(job, ctx, out):
    from forge.threed import modelpics
    return modelpics.icon_job(job, ctx, out)


def model_portrait(job, ctx, out):
    from forge.threed import modelpics
    return modelpics.portrait_job(job, ctx, out)


JOB_TYPES = dict(_specs.JOB_TYPES)
HANDLERS = {"model_icon": model_icon, "model_portrait": model_portrait}
