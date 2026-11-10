"""`inpaint` and `scene_state` plug-in job types (Night 3, G4). Code: forge/night3/inpaint.py (graph, handlers) and
forge/ops/state_mask.py (what changed between two greyboxes; the bit-identical composite). Lazy handler imports
(forge.jobs loads the plug-ins, so a plug-in must not import forge.jobs at load time)."""
from __future__ import annotations
from forge.night3 import specs as _specs

DEPENDS = ("forge.night3.specs", "forge.ops.state_mask", "forge.night3.inpaint")


def inpaint(job, ctx, out):
    from forge.night3 import inpaint as ip
    return ip.inpaint(job, ctx, out)


def scene_state(job, ctx, out):
    from forge.night3 import inpaint as ip
    return ip.scene_state(job, ctx, out)


JOB_TYPES = {"inpaint": _specs.INPAINT, "scene_state": _specs.SCENE_STATE}
HANDLERS = {"inpaint": inpaint, "scene_state": scene_state}
