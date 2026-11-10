"""Filter Forge plug-in job type (Night 3B, G14, CPU): filter_forge — Filter Forge's command-line renderer driven by
a task XML the forge writes into the job's own folder. Code: forge/night3b/ffdriver.py (imported lazily)."""
from __future__ import annotations
from forge.night3b import specs as _specs

DEPENDS = ("forge.night3b.specs", "forge.night3b.ffdriver", "forge.night3b.handoff_jobs")


def filter_forge(job, ctx, out):
    from forge.night3b import ffdriver
    return ffdriver.render(job, ctx, out)


JOB_TYPES = {"filter_forge": _specs.FILTER_FORGE}
HANDLERS = {"filter_forge": filter_forge}
