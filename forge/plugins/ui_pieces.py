"""UI-piece plug-in job types (Night 3, G12, CPU): nine_slice, button_states.
Code: forge/ops/ui_pieces.py, handlers forge/night3/cpu_jobs.py (imported lazily)."""
from __future__ import annotations
from forge.night3 import specs as _specs

DEPENDS = ("forge.night3.specs", "forge.ops.ui_pieces", "forge.night3.cpu_jobs")


def _h(name):
    def run(job, ctx, out):
        from forge.night3 import cpu_jobs
        return getattr(cpu_jobs, name)(job, ctx, out)
    run.__name__ = name
    return run


JOB_TYPES = {"nine_slice": _specs.NINE_SLICE, "button_states": _specs.BUTTON_STATES}
HANDLERS = {t: _h(t) for t in JOB_TYPES}
