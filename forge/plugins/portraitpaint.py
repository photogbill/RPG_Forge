"""The painted portraits plug-in (BUILD 93): portrait_paint — a body portrait painted again from the picture its body
was made from, by FLUX.2 [klein] 4B's reference editing. Spec: forge/threed/portraitpaint_specs.py; code:
forge/threed/portraitpaint.py (imported only when a job runs)."""
from __future__ import annotations
from forge.threed import portraitpaint_specs as _specs

DEPENDS = ("forge.threed.portraitpaint_specs", "forge.threed.portraitpaint")


def portrait_paint(job, ctx, out):
    from forge.threed import portraitpaint
    return portraitpaint.paint_job(job, ctx, out)


JOB_TYPES = dict(_specs.JOB_TYPES)
HANDLERS = {"portrait_paint": portrait_paint}
