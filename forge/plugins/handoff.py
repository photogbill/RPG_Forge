"""Hand-off plug-in job types (Night 3B, G13): handoff_file (CPU) and handoff_kit (GPU — the depth model).
Made by `python -m forge handoff in`; handlers in forge/night3b/handoff_jobs.py (imported lazily)."""
from __future__ import annotations
from forge.night3b import specs as _specs

DEPENDS = ("forge.night3b.specs", "forge.night3b.handoff_jobs", "forge.handoff")


def _h(name):
    def run(job, ctx, out):
        from forge.night3b import handoff_jobs
        return getattr(handoff_jobs, name)(job, ctx, out)
    run.__name__ = name
    return run


JOB_TYPES = {"handoff_file": _specs.HANDOFF_FILE, "handoff_kit": _specs.HANDOFF_KIT}
HANDLERS = {t: _h(t) for t in JOB_TYPES}
