"""The 3D workshop's job types (BUILD 36): model_3d, rig_body (GPU, each holding the card lock), fit_motions,
grow_tree (CPU, Blender), line_3d (the whole line for a list). Specs: forge/threed/specs.py; handlers: forge/threed/jobs.py,
imported only when a job runs, so a running worker picks up a fix without a restart."""
from __future__ import annotations
from forge.threed import specs as _specs

DEPENDS = ("forge.threed.specs", "forge.threed.jobs", "forge.threed.bodies", "forge.threed.rig", "forge.threed.motions",
           "forge.threed.tidy", "forge.threed.trees", "forge.threed.line", "forge.threed.cardlock", "forge.threed.comfyapi",
           "forge.threed.template", "forge.threed.env", "forge.threed.glb", "forge.threed.licences")


def _handler(kind: str):
    def run(job, ctx, out):
        from forge.threed import jobs
        return jobs.HANDLERS[kind](job, ctx, out)
    run.__name__ = kind
    return run


JOB_TYPES = dict(_specs.JOB_TYPES)
HANDLERS = {k: _handler(k) for k in JOB_TYPES}
