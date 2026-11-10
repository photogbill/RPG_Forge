"""Sprite-sheet plug-in job types (Night 3, G7, CPU): facings_pack, anim_preview, turnaround_split.
Code: forge/ops/sprites.py, handlers forge/night3/cpu_jobs.py (imported lazily — forge.jobs loads the plug-ins)."""
from __future__ import annotations
from forge.night3 import specs as _specs

DEPENDS = ("forge.night3.specs", "forge.ops.sprites", "forge.night3.cpu_jobs")


def _h(name):
    def run(job, ctx, out):
        from forge.night3 import cpu_jobs
        return getattr(cpu_jobs, name)(job, ctx, out)
    run.__name__ = name
    return run


JOB_TYPES = {"facings_pack": _specs.FACINGS_PACK, "anim_preview": _specs.ANIM_PREVIEW, "turnaround_split": _specs.TURNAROUND_SPLIT}
HANDLERS = {t: _h(t) for t in JOB_TYPES}
