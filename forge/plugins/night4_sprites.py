"""Night 4 plug-in job types for characters: sprite_intake (CPU, F1) and character_set (GPU, F2).
Handlers import lazily — forge.jobs loads the plug-ins, so importing it here at load time would be circular."""
from __future__ import annotations
from forge.night4 import specs as _specs

DEPENDS = ("forge.night4.specs", "forge.night4.cc", "forge.night4.intake", "forge.night4.intake_job",
           "forge.night4.characters", "forge.night4.charset")


def sprite_intake(job, ctx, out):
    from forge.night4 import intake_job
    return intake_job.run(job, ctx, out)


def character_set(job, ctx, out):
    from forge.night4 import charset
    return charset.run(job, ctx, out)


JOB_TYPES = {"sprite_intake": _specs.SPRITE_INTAKE, "character_set": _specs.CHARACTER_SET}
HANDLERS = {"sprite_intake": sprite_intake, "character_set": character_set}
