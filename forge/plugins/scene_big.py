"""`scene_big` plug-in job type (Night 3, G3): a painting larger than one diffusion pass. The code is in
forge/night3/big.py (reloaded with this file); forge/ops/bigtiles.py does the tiling and the seams.
The handler imports lazily: forge.jobs loads the plug-ins, so a plug-in must not import forge.jobs at load time."""
from __future__ import annotations
from forge.night3 import specs as _specs

DEPENDS = ("forge.night3.specs", "forge.ops.bigtiles", "forge.night3.big")


def scene_big(job, ctx, out):
    from forge.night3 import big
    return big.scene_big(job, ctx, out)


JOB_TYPES = {"scene_big": _specs.SCENE_BIG}
HANDLERS = {"scene_big": scene_big}
